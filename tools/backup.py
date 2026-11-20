#!/usr/bin/env python3
"""Backups before changes, and restore.

Usage:
    python3 -I tools/backup.py create <reason> <path> [<path> ...]
    python3 -I tools/backup.py list
    python3 -I tools/backup.py show <folder-name>
    python3 -I tools/backup.py restore <folder-name> [--yes]

WRITES OUTSIDE THE PROJECT FOLDER. This is the only tool in the repository that
does. It writes only to:
  - ~/.claude/backups/<reason>-<YYYY-MM-DD>[-N]/   (create, and the automatic
    safety backup "before-restore" made by restore), and
  - on restore, after you confirmed, the original paths listed in the backup's
    manifest.json (files are overwritten, folders are merged into).
It never deletes your files: files that are not in the manifest stay untouched. The only
thing it ever removes is its own unfinished backup folder, and only when a create fails
half-way (the folder that this very run just made).
A manifest whose original paths lie outside your home directory (symlinks are resolved
first) is refused.

Commands:
  create   Copies files/folders into a new backup folder and writes manifest.json
           (created, reason, tool version, entries with original path, stored
           path, type, sha256 and size). <reason>: lowercase letters, digits and
           hyphens only. Paths that do not exist are refused, and so is any path that equals, lies
           inside or contains the backups folder (it would copy the backup into itself).
           Prints the folder.
  list     Lists backups with date, reason and number of entries. Old-style
           folders without manifest.json are marked "no manifest (restore by hand)".
  show     Prints the entries of one backup.
  restore  First verifies the stored files against the sha256 values of the manifest;
           if one does not match, it refuses ("backup is damaged") before writing
           anything. Then prints what would be written or overwritten (and which originals
           differ from the backup, by sha256), then asks
           "Restore these N items? [y/N]". Only "y" or "yes" proceeds.
           --yes skips the question (for scripts and tests only; do not use it
           interactively). Before overwriting, the current originals are saved
           in a safety backup (reason "before-restore"). After restoring, the
           sha256 of every restored file is verified.

The environment variable CUSTOMIZATION_AUDIT_HOME replaces the home directory
(for testing with a fake home).

Exit codes: 0 ok, 1 refused or cancelled, 2 error.
Standard library only, Python 3.9+.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

def _read_version():
    """Version of this project from the VERSION file next to tools/ ("unknown" if missing)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip() or "unknown"
    except OSError:
        return "unknown"


TOOL_VERSION = _read_version()
MANIFEST = "manifest.json"
REASON_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class Refused(Exception):
    pass


def backups_dir():
    return paths.claude_dir() / "backups"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inside(child, parent):
    try:
        Path(child).relative_to(parent)
        return True
    except ValueError:
        return False


def dir_files(d):
    """Relative posix path -> sha256 for all files below d."""
    out = {}
    for root, _dirs, files in os.walk(d):
        for n in files:
            p = Path(root) / n
            out[p.relative_to(d).as_posix()] = sha256(p)
    return out


def new_folder(reason):
    base = backups_dir()
    base.mkdir(parents=True, exist_ok=True)
    stem = "%s-%s" % (reason, datetime.date.today().isoformat())
    n, name = 1, stem
    while (base / name).exists():
        n += 1
        name = "%s-%d" % (stem, n)
    folder = base / name
    folder.mkdir()
    return folder


def create_backup(reason, targets):
    if not REASON_RE.match(reason or ""):
        raise Refused("reason must contain only lowercase letters, digits and hyphens")
    if not targets:
        raise Refused("no paths given")
    resolved = []
    for t in targets:
        p = Path(os.path.abspath(os.path.expanduser(str(t))))
        if not p.exists():
            raise Refused("path does not exist: %s" % p)
        resolved.append(p)
    bk = os.path.realpath(backups_dir())
    for p in resolved:
        rp = os.path.realpath(p)
        if rp == bk or inside(rp, bk) or inside(bk, rp):
            raise Refused("path contains or lies inside the backups folder: %s" % p)
    folder = new_folder(reason)
    try:
        entries = []
        for i, p in enumerate(resolved, 1):
            stored = "%d/%s" % (i, p.name or "root")
            dest = folder / stored
            dest.parent.mkdir(parents=True)
            if p.is_dir():
                shutil.copytree(p, dest)
                entries.append({"original": str(p), "stored": stored, "type": "dir",
                                "size": sum(os.path.getsize(dest / r) for r in dir_files(dest)),
                                "files": dir_files(dest)})
            else:
                shutil.copy2(p, dest)
                entries.append({"original": str(p), "stored": stored, "type": "file",
                                "sha256": sha256(dest), "size": dest.stat().st_size})
        manifest = {"created": datetime.datetime.now().replace(microsecond=0).isoformat(),
                    "reason": reason, "tool_version": TOOL_VERSION, "entries": entries}
        (folder / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)  # only the folder this run just made
        raise
    return folder


def folder_for(name):
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise Refused("invalid backup folder name: %r" % name)
    f = backups_dir() / name
    if not f.is_dir():
        raise Refused("no such backup: %s" % name)
    return f


def load_manifest(folder):
    mf = folder / MANIFEST
    if not mf.is_file():
        raise Refused("no manifest (restore by hand): %s" % folder)
    try:
        m = json.loads(mf.read_text(encoding="utf-8"))
        entries = m["entries"]
        assert isinstance(entries, list)
    except Exception as e:
        raise Refused("manifest is unreadable: %s" % e)
    home = Path(os.path.realpath(paths.home()))
    for e in entries:
        try:
            orig, stored, typ = e["original"], e["stored"], e["type"]
        except (KeyError, TypeError):
            raise Refused("manifest entry is incomplete")
        if typ not in ("file", "dir"):
            raise Refused("manifest entry has an unknown type: %r" % (typ,))
        if not os.path.isabs(orig) or not inside(os.path.realpath(orig), home):
            raise Refused("manifest refused: original path outside your home: %s" % orig)
        sp = os.path.normpath(stored)
        if os.path.isabs(stored) or sp.startswith(".."):
            raise Refused("manifest refused: stored path escapes the backup: %s" % stored)
        if not (folder / sp).exists():
            raise Refused("manifest refers to a missing stored item: %s" % stored)
    return m


def verify_stored(folder, entries):
    """Check the stored files against the manifest checksums; raise Refused if damaged."""
    for e in entries:
        src = folder / e["stored"]
        if e["type"] == "file":
            ok = src.is_file() and e.get("sha256") == sha256(src)
        else:
            files = e.get("files")
            ok = src.is_dir() and isinstance(files, dict) and dir_files(src) == files
        if not ok:
            raise Refused("backup is damaged: stored item does not match the manifest checksum: %s"
                          % e["stored"])


def cmd_create(args):
    if len(args) < 2:
        print("usage: backup.py create <reason> <path> [<path> ...]", file=sys.stderr)
        return 2
    folder = create_backup(args[0], args[1:])
    print(folder)
    return 0


def cmd_list(_args):
    base = backups_dir()
    if not base.is_dir():
        print("no backups (%s does not exist)" % base)
        return 0
    rows = 0
    for f in sorted(base.iterdir()):
        if not f.is_dir():
            continue
        rows += 1
        mf = f / MANIFEST
        if mf.is_file():
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
                print("%-45s %s  %-20s %d entries" % (f.name, m["created"][:10],
                                                      m["reason"], len(m["entries"])))
                continue
            except Exception:
                print("%-45s manifest unreadable" % f.name)
                continue
        print("%-45s no manifest (restore by hand)" % f.name)
    if not rows:
        print("no backups")
    return 0


def cmd_show(args):
    if len(args) != 1:
        print("usage: backup.py show <folder-name>", file=sys.stderr)
        return 2
    folder = folder_for(args[0])
    m = load_manifest(folder)
    print("%s  created %s  reason %s  tool %s" % (folder.name, m["created"], m["reason"],
                                                  m.get("tool_version", "?")))
    for e in m["entries"]:
        extra = e.get("sha256", "%d files" % len(e.get("files", {})))
        print("  %-4s %s\n       stored: %s  size: %s  %s" % (e["type"], e["original"], e["stored"],
                                                              e.get("size", "?"), extra))
    return 0


def plan_entry(folder, e):
    """Return (lines describing what would happen, count of differing items)."""
    src, orig = folder / e["stored"], Path(e["original"])
    if e["type"] == "file":
        if not orig.exists():
            return ["  create     %s" % orig], 0
        same = orig.is_file() and sha256(orig) == sha256(src)
        return (["  unchanged  %s (identical)" % orig] if same
                else ["  OVERWRITE  %s (differs from backup)" % orig]), 0 if same else 1
    lines, diff = [], 0
    for rel, h in sorted(dir_files(src).items()):
        t = orig / rel
        if not t.exists():
            lines.append("  create     %s" % t)
        elif t.is_file() and sha256(t) == h:
            lines.append("  unchanged  %s (identical)" % t)
        else:
            lines.append("  OVERWRITE  %s (differs from backup)" % t)
            diff += 1
    return lines or ["  (empty folder) %s" % orig], diff


def cmd_restore(args):
    yes = "--yes" in args
    rest = [a for a in args if a != "--yes"]
    if len(rest) != 1:
        print("usage: backup.py restore <folder-name> [--yes]", file=sys.stderr)
        return 2
    folder = folder_for(rest[0])
    entries = load_manifest(folder)["entries"]
    verify_stored(folder, entries)
    print("Restore from %s would write to:" % folder.name)
    total_diff = 0
    for e in entries:
        lines, d = plan_entry(folder, e)
        total_diff += d
        print("\n".join(lines))
    print("%d originals differ from the backup. Nothing is deleted." % total_diff)
    if not yes:
        print("Restore these %d items? [y/N] " % len(entries), end="", flush=True)
        try:
            answer = sys.stdin.readline().strip().lower()
        except Exception:
            answer = ""
        if answer not in ("y", "yes"):
            print("Cancelled. Nothing was changed.")
            return 1
    existing = [e["original"] for e in entries if Path(e["original"]).exists()]
    if existing:
        safety = create_backup("before-restore", existing)
        print("Safety backup of the current state: %s" % safety)
    for e in entries:
        src, orig = folder / e["stored"], Path(e["original"])
        orig.parent.mkdir(parents=True, exist_ok=True)
        if e["type"] == "file":
            shutil.copy2(src, orig)
        else:
            shutil.copytree(src, orig, dirs_exist_ok=True)
    for e in entries:
        src, orig = folder / e["stored"], Path(e["original"])
        pairs = ([(src, orig)] if e["type"] == "file"
                 else [(src / r, orig / r) for r in dir_files(src)])
        for s, o in pairs:
            if not o.is_file() or sha256(o) != sha256(s):
                print("error: verification failed for %s" % o, file=sys.stderr)
                return 2
    print("Restored %d items; sha256 verified." % len(entries))
    return 0


def main(argv):
    cmds = {"create": cmd_create, "list": cmd_list, "show": cmd_show, "restore": cmd_restore}
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in cmds:
        print(__doc__)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    try:
        return cmds[argv[0]](argv[1:])
    except Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
