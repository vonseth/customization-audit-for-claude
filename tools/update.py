#!/usr/bin/env python3
"""Updates this copy of the project to the newest version without losing your data.

Usage:
    python3 -I tools/update.py check
    python3 -I tools/update.py apply [<release.zip>] [--yes] [--allow-downgrade]
    python3 -I tools/update.py rollback [--yes]
    python3 -I tools/update.py migrate [--yes]

NETWORK: this is the only tool that uses the network, and only for `check` and for `apply` without a ZIP
file. It sends read-only GET requests to api.github.com (the latest release of
vonseth/customization-audit-for-claude) and downloads that release's ZIP from there. Nothing is ever
uploaded. For a private repository set the environment variable GITHUB_TOKEN (it is sent only to
api.github.com, never printed). Without network use `apply <release.zip>` with a ZIP you downloaded by hand.

Commands:
  check     Reads VERSION, asks GitHub for the latest release, prints installed and latest version and the
            release notes. Offline or any HTTP error: a calm message, exit 0.
  apply     Unpacks the ZIP (the latest release if none is given) into a temporary folder and shows a
            preview: managed files that are replaced, added or removed; what is kept (reports/, the user
            sections of CLAUDE.md, the data of the page); extra files of yours (listed, never touched). Asks
            "Update from X to Y? [y/N]" (--yes skips the question, for tests). Then: full backup of the
            project folder with tools/backup.py (reason before-update-<old>-to-<new>), replace the managed
            files, carry over your page data (migrated to the current schema) and the CLAUDE.md user
            sections, build the page, run check_overview.py and selftest.py. If anything fails, the backup is
            restored automatically (exit 1). The name of the backup goes to .update-state.json.
            Refused: a git checkout (use `git pull`, then `migrate`), a downgrade (unless
            --allow-downgrade), a ZIP that is not a release of this project or tries to write outside the
            work folder.
  rollback  Restores the project folder from the backup of the last update (after a confirmation and a
            safety backup of the current state). Files created since the update are removed.
  migrate   For git users after `git pull`: only migrates the data format of the page (schema_version) and
            adds the USER markers to CLAUDE.md. No files are replaced. Backs up the two files first.

Managed paths (replaced by an update): tools/ tests/ assets/ docs/ examples/ README.md LICENSE CHANGELOG.md
DESIGN.md VERSION .gitignore, the page template audit-overview.html and the rules part of CLAUDE.md; .github/
and .gitattributes if the ZIP has them. Kept: reports/, the sections between <!-- USER:START name --> and
<!-- USER:END name --> in CLAUDE.md (old copies without markers: the sections "Decisions (kept deliberately)"
and "Status and open items", found by heading), the data blocks of the page, and every other file.

Writes outside the project folder only through tools/backup.py (~/.claude/backups/). The environment variable
CUSTOMIZATION_AUDIT_HOME replaces the home directory (for tests).

Exit codes: 0 ok or nothing to do, 1 refused, cancelled, or failed (and restored), 2 usage error.
Standard library only, Python 3.9+.
"""
import datetime
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True  # an update must not leave __pycache__ folders behind
HERE = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(HERE))
import backup  # noqa: E402

REPO = "vonseth/customization-audit-for-claude"
API_LATEST = "https://api.github.com/repos/%s/releases/latest" % REPO
API_HOST = "api.github.com"
MAX_ZIP_BYTES = 200 * 1024 * 1024  # download and unpacked size limit
MAX_ZIP_MEMBERS = 10000
USER_AGENT = "customization-audit-for-claude-updater"
STATE = ".update-state.json"
PAGE = "audit-overview.html"
RULES = "CLAUDE.md"
MANAGED_DIRS = ["tools", "tests", "assets", "docs", "examples"]
MANAGED_FILES = ["README.md", "LICENSE", "CHANGELOG.md", "DESIGN.md", "VERSION", ".gitignore"]
OPTIONAL_MANAGED = [".github", ".gitattributes"]  # replaced if the ZIP has them (zipballs leave them out), never deleted
KEPT_TOP = {"reports", ".git", STATE, ".DS_Store", "__pycache__"}
NOISE = {"__pycache__", ".DS_Store"}
USER_SECTIONS = {"decisions": "## Decisions (kept deliberately)", "status": "## Status and open items"}
MARK_RE = r"<!-- USER:START (%s) -->\n(.*?)<!-- USER:END \1 -->\n?"


class Stop(Exception):
    """A refusal or failure with a message for the user (exit 1)."""


# ---------------------------------------------------------------- network

class _SameHostAuth(urllib.request.HTTPRedirectHandler):
    """Refuses redirects to anything but https; drops the Authorization header when a redirect leaves the host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise OSError("refusing a redirect to a non-https URL")
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).hostname != urllib.parse.urlsplit(req.full_url).hostname:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


def http_fetch(url, accept="application/vnd.github+json", timeout=10):  # fetcher(url, accept, timeout) -> bytes
    """GET url and return the bytes. Raises OSError (also for HTTP errors) with a calm message."""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise OSError("refusing a non-https URL")
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    token = os.environ.get("GITHUB_TOKEN")
    if token and urllib.parse.urlsplit(url).hostname == API_HOST:
        headers["Authorization"] = "Bearer " + token  # never printed
    opener = urllib.request.build_opener(_SameHostAuth)
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            data = r.read(MAX_ZIP_BYTES + 1)
            if len(data) > MAX_ZIP_BYTES:
                raise OSError("the download is larger than %d MB" % (MAX_ZIP_BYTES // 1024 // 1024))
            return data
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise OSError("GitHub answered %d (no release found, no access to a private repository, or a "
                          "rate limit; for a private repository set GITHUB_TOKEN)" % e.code)
        raise OSError("GitHub answered HTTP %d" % e.code)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise OSError("no connection (%s)" % getattr(e, "reason", e))


def latest_release(fetcher):
    """Returns the parsed release dict; raises OSError."""
    raw = fetcher(API_LATEST, "application/vnd.github+json", 10)
    try:
        rel = json.loads(raw.decode("utf-8"))
        assert isinstance(rel, dict) and rel.get("tag_name")
    except Exception:
        raise OSError("unexpected answer from GitHub")
    return rel


# ---------------------------------------------------------------- versions

def parse_version(text):
    """'1.4.0' -> sortable tuple; a pre-release suffix ('-beta') sorts before the release. None if unparsable."""
    m = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(-[0-9A-Za-z.-]+)?(?:\+.*)?$", (text or "").strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0), 0 if m.group(4) else 1)


def installed_version(root):
    try:
        v = (Path(root) / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return v or None


# ---------------------------------------------------------------- files

def walk_files(base, rels=None):
    """Relative posix paths of all files below base (noise ignored)."""
    out = {}
    for cur, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in NOISE]
        for n in files:
            if n in NOISE or n.endswith(".pyc"):
                continue
            p = Path(cur) / n
            out[p.relative_to(base).as_posix()] = p
    return out


def managed_files(base, new_tree=None):
    """Map relative path -> Path of the managed files below base. Optional ones only if present."""
    out = {}
    for d in MANAGED_DIRS + OPTIONAL_MANAGED:
        p = Path(base) / d
        if p.is_dir():
            for rel, fp in walk_files(p).items():
                out["%s/%s" % (d, rel)] = fp
    for f in MANAGED_FILES + [x for x in OPTIONAL_MANAGED if (Path(base) / x).is_file()]:
        if (Path(base) / f).is_file():
            out[f] = Path(base) / f
    return out


def rd(path):
    """Text of a file with line endings untouched (Path.read_text has no newline argument before 3.13)."""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def wr(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def same_bytes(a, b):
    try:
        return Path(a).read_bytes() == Path(b).read_bytes()
    except OSError:
        return False


def safe_extract(zip_path, dest):
    """Unpacks into dest, refusing members that escape it; returns the single top folder."""
    dest = Path(dest).resolve()
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as e:
        raise Stop("not a readable ZIP file: %s" % e)
    with zf:
        tops = set()
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise Stop("the ZIP is refused: more than %d members" % MAX_ZIP_MEMBERS)
        if sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
            raise Stop("the ZIP is refused: more than %d MB uncompressed" % (MAX_ZIP_BYTES // 1024 // 1024))
        for info in infos:
            name = info.filename
            parts = name.replace("\\", "/").split("/")
            if name.startswith(("/", "\\")) or ".." in parts or re.match(r"^[A-Za-z]:", name):
                raise Stop("the ZIP is refused: member %r would be written outside the work folder" % name)
            target = (dest / name).resolve()
            if target != dest and dest not in target.parents:
                raise Stop("the ZIP is refused: member %r would be written outside the work folder" % name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise Stop("the ZIP is refused: member %r is a symbolic link" % name)
            tops.add(parts[0])
        tops.discard("")
        if len(tops) != 1:
            raise Stop("the ZIP must hold exactly one top folder (a GitHub release ZIP does)")
        zf.extractall(dest)
    top = dest / tops.pop()
    if not top.is_dir():
        raise Stop("the ZIP must hold one top folder")
    for need in ("VERSION", PAGE, "tools/update.py", "tools/build_overview.py"):
        if not (top / need).exists():
            raise Stop("this ZIP is not a release of this project (%s is missing)" % need)
    return top


# ---------------------------------------------------------------- user sections of CLAUDE.md

def extract_user_sections(text):
    """name -> raw text between the markers; old copies: found by heading. Returns (sections, how)."""
    found, how = {}, {}
    for name in USER_SECTIONS:
        m = re.search(MARK_RE % re.escape(name), text, re.S)
        if m:
            found[name], how[name] = m.group(2), "markers"
            continue
        head = USER_SECTIONS[name]
        m = re.search(r"^%s[ \t]*\n.*?(?=^## |\Z)" % re.escape(head), text, re.S | re.M)
        if m:
            found[name], how[name] = m.group(0).rstrip("\n") + "\n\n", "heading"
    return found, how


def merge_user_sections(new_text, sections):
    """Puts the user's sections into the new CLAUDE.md (inside its markers; appended if it has none)."""
    for name, raw in sections.items():
        pat = re.compile(MARK_RE % re.escape(name), re.S)
        block = "<!-- USER:START %s -->\n%s<!-- USER:END %s -->\n" % (name, raw if raw.endswith("\n") else raw + "\n", name)
        if pat.search(new_text):
            new_text = pat.sub(lambda m: block, new_text, count=1)
        else:
            new_text = new_text.rstrip("\n") + "\n\n" + block
    return new_text


def add_markers(text):
    """Wraps the two user sections of an old CLAUDE.md in markers (no-op where markers exist)."""
    for name, raw_head in USER_SECTIONS.items():
        if re.search(MARK_RE % re.escape(name), text, re.S):
            continue
        m = re.search(r"^%s[ \t]*\n.*?(?=^## |\Z)" % re.escape(raw_head), text, re.S | re.M)
        if m:
            sec = m.group(0)
            text = text[:m.start()] + "<!-- USER:START %s -->\n%s<!-- USER:END %s -->\n" % (
                name, sec if sec.endswith("\n") else sec + "\n", name) + text[m.end():]
    return text


# ---------------------------------------------------------------- page data

def load_modules(tools_dir):
    """sample_data.py (block helpers) and its schema module of the given tools folder."""
    spec = importlib.util.spec_from_file_location("sample_data_upd", str(Path(tools_dir) / "sample_data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_blocks_lenient(sd, html):
    """Data blocks of a page; a missing block (older version) is empty, broken JSON is an error."""
    out = {}
    for name in sd.BLOCKS:
        m = sd.pattern(name).search(html)
        if not m:
            out[name] = sd.EMPTY[name]
            continue
        try:
            out[name] = json.loads(m.group(2))
        except ValueError as e:
            raise Stop("data block #data-%s of the page is not valid JSON: %s" % (name, e))
    return out


def migrated(sd, blocks):
    try:
        return sd.SCHEMA.migrate(blocks, sd.SCHEMA.version_of(blocks))
    except ValueError as e:
        raise Stop(str(e))


def strip_version(blocks):
    b = dict(blocks)
    if isinstance(b.get("meta"), dict):
        b["meta"] = {k: v for k, v in b["meta"].items() if k != "schema_version"}
    return b


# ---------------------------------------------------------------- tools run

def run_tool(root, script, *args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-I", "-B", str(Path(root) / "tools" / script)] + list(args),
                       capture_output=True, text=True, env=env, cwd=str(root))
    return p.returncode, (p.stdout + p.stderr).strip()


def verify(root, expect_blocks):
    """Build, check and self-test the project; returns a problem text or None."""
    rc, out = run_tool(root, "build_overview.py")
    if rc != 0:
        return "build_overview.py failed:\n" + out
    rc, out = run_tool(root, "check_overview.py")
    if rc != 0:
        return "check_overview.py failed:\n" + out
    rc, out = run_tool(root, "selftest.py")
    if rc != 0:
        return "selftest.py failed:\n" + out
    if expect_blocks is not None:
        sd = load_modules(Path(root) / "tools")
        got = read_blocks_lenient(sd, (Path(root) / PAGE).read_text(encoding="utf-8"))
        if strip_version(got) != strip_version(expect_blocks):
            return "the data of the page changed during the update"
    return None


# ---------------------------------------------------------------- backup and restore

def make_backup(root, reason, targets):
    try:
        return backup.create_backup(reason, targets)
    except backup.Refused as e:
        raise Stop("no backup could be made, nothing was changed: %s" % e)
    except OSError as e:
        raise Stop("no backup could be made, nothing was changed: %s" % e)


def _sync_dir(src, dst):
    """Makes dst byte-identical to src (files and folders that are not in src are removed)."""
    src, dst = Path(src), Path(dst)
    keep_files, keep_dirs = set(), set()
    for cur, dirs, files in os.walk(src):
        rel = Path(cur).relative_to(src).as_posix()
        for d in dirs:
            keep_dirs.add((Path(rel) / d).as_posix() if rel != "." else d)
        for f in files:
            keep_files.add((Path(rel) / f).as_posix() if rel != "." else f)
    for cur, dirs, files in os.walk(dst):
        rel = Path(cur).relative_to(dst)
        for d in list(dirs):
            r = (rel / d).as_posix()
            if r not in keep_dirs:
                p = dst / r
                shutil.rmtree(p) if not p.is_symlink() else p.unlink()
                dirs.remove(d)
        for f in files:
            if (rel / f).as_posix() not in keep_files:
                (dst / rel / f).unlink()
    for d in sorted(keep_dirs):
        (dst / d).mkdir(parents=True, exist_ok=True)
    for f in sorted(keep_files):
        s, t = src / f, dst / f
        if not t.is_file() or t.is_symlink() or not same_bytes(s, t):
            if t.is_symlink() or t.exists():
                t.unlink()
            shutil.copy2(s, t)


def restore_backup(name, expected_originals):
    """Restores a backup made by this tool, without any question (callers ask first)."""
    folder = backup.folder_for(name)
    try:
        entries = json.loads((folder / backup.MANIFEST).read_text(encoding="utf-8"))["entries"]
    except Exception as e:
        raise Stop("the backup manifest is unreadable: %s" % e)
    got = sorted(os.path.abspath(e["original"]) for e in entries)
    if got != sorted(os.path.abspath(p) for p in expected_originals):
        raise Stop("the backup %s does not belong to this project folder" % name)
    backup.verify_stored(folder, entries)
    for e in entries:
        src, orig = folder / e["stored"], Path(e["original"])
        if e["type"] == "dir":
            _sync_dir(src, orig)
            if backup.dir_files(orig) != e["files"]:
                raise Stop("restore verification failed for %s" % orig)
        else:
            shutil.copy2(src, orig)
            if backup.sha256(orig) != e["sha256"]:
                raise Stop("restore verification failed for %s" % orig)


def read_state(root):
    try:
        st = json.loads((Path(root) / STATE).read_text(encoding="utf-8"))
        assert isinstance(st, dict) and st.get("backup")
        return st
    except Exception:
        return None


def ask(prompt, stdin, yes):
    if yes:
        return True
    print(prompt + " [y/N] ", end="", flush=True)
    try:
        answer = stdin.readline().strip().lower()
    except Exception:
        answer = ""
    return answer in ("y", "yes")


def slug(v):
    return re.sub(r"[^a-z0-9]+", "-", (v or "unknown").lower()).strip("-") or "unknown"


# ---------------------------------------------------------------- commands

def cmd_check(root, fetcher):
    cur = installed_version(root)
    print("Installed version: %s" % (cur or "unknown (no VERSION file; before 1.4.0)"))
    try:
        rel = latest_release(fetcher)
    except OSError as e:
        print("Could not check for a newer version: %s.\nNothing was changed; try again later, or download the "
              "latest release by hand and run: python3 -I tools/update.py apply <release.zip>" % e)
        return 0
    latest = str(rel["tag_name"]).lstrip("v")
    print("Latest release:    %s%s" % (latest, (" (%s)" % rel["published_at"][:10]) if rel.get("published_at") else ""))
    a, b = parse_version(cur), parse_version(latest)
    if b is None:
        print("The latest release has an unusual version number (%s); compare by hand." % latest)
        return 0
    if a is not None and a >= b:
        print("You are up to date.")
        return 0
    print("A newer version is available.")
    notes = (rel.get("body") or "").strip()
    if notes:
        lines = notes.splitlines()
        print("\nRelease notes:\n" + "\n".join("  " + l for l in lines[:60]))
        if len(lines) > 60:
            print("  ... (%d more lines: %s)" % (len(lines) - 60, rel.get("html_url", "see the release page")))
    print("\nUpdate with: python3 -I tools/update.py apply")
    return 0


def plan(root, new_top):
    """Compares the managed files of the project with the new version."""
    old = managed_files(root)
    new = managed_files(new_top)
    replaced = sorted(r for r in new if r in old and not same_bytes(old[r], new[r]))
    added = sorted(r for r in new if r not in old)
    unchanged = sorted(r for r in new if r in old and r not in replaced)
    removed = sorted(r for r in old if r not in new
                     and not r.startswith(tuple(x + "/" for x in OPTIONAL_MANAGED)) and r not in OPTIONAL_MANAGED)
    managed_top = set(MANAGED_DIRS + MANAGED_FILES + OPTIONAL_MANAGED)
    extras = sorted(n for n in os.listdir(root)
                    if n not in managed_top and n not in KEPT_TOP and n not in (PAGE, RULES))
    return {"replaced": replaced, "added": added, "unchanged": unchanged, "removed": removed, "extras": extras,
            "old": old, "new": new}


def show_plan(p, old_v, new_v, sections_how, nblocks):
    def lst(title, items, limit=12):
        if items:
            print("  %s (%d):" % (title, len(items)))
            for i in items[:limit]:
                print("      " + i)
            if len(items) > limit:
                print("      ... and %d more" % (len(items) - limit))
    print("Update from %s to %s" % (old_v or "unknown", new_v))
    print("\nManaged files:")
    lst("replaced", p["replaced"])
    lst("added", p["added"])
    lst("removed (managed files that are gone in the new version, or files you added inside managed folders; "
        "they are in the backup)", p["removed"])
    print("  unchanged: %d" % len(p["unchanged"]))
    print("  %s: new template; your data blocks (%d with content) are carried over and migrated" % (PAGE, nblocks))
    print("  %s: new rules; your sections are kept (%s)" % (RULES, ", ".join(
        "%s via %s" % (k, v) for k, v in sorted(sections_how.items())) or "none found"))
    print("    Only text between the USER markers in CLAUDE.md is kept; put your own additions there. "
          "Text outside the markers is replaced.")
    print("\nKept as they are: reports/")
    if p["extras"]:
        print("Other files of yours (listed, never touched): " + ", ".join(p["extras"]))
    print()


def cmd_apply(root, fetcher, stdin, args):
    yes = "--yes" in args
    downgrade = "--allow-downgrade" in args
    rest = [a for a in args if not a.startswith("--")]
    if len(rest) > 1 or any(a.startswith("--") and a not in ("--yes", "--allow-downgrade") for a in args):
        print(__doc__)
        return 2
    if (root / ".git").exists():
        raise Stop("this folder is a git checkout. Update it with `git pull` (replacing files here would "
                   "fight with git), then run `python3 -I tools/update.py migrate` to bring the page data and "
                   "CLAUDE.md to the current format.")
    for need in (PAGE, "tools/build_overview.py"):
        if not (root / need).exists():
            raise Stop("this does not look like a copy of the project (%s is missing)" % need)
    work = Path(tempfile.mkdtemp(prefix="audit-update-"))
    try:
        if rest:
            zpath = Path(rest[0])
            if not zpath.is_file():
                raise Stop("ZIP file not found: %s" % zpath)
        else:
            try:
                rel = latest_release(fetcher)
                url = rel.get("zipball_url") or ""
                if urllib.parse.urlsplit(url).hostname != API_HOST:
                    raise OSError("the release has no usable download address")
                print("Downloading %s ..." % rel["tag_name"])
                data = fetcher(url, "application/vnd.github+json", 120)
                if len(data) > MAX_ZIP_BYTES:
                    raise OSError("the download is larger than %d MB" % (MAX_ZIP_BYTES // 1024 // 1024))
            except OSError as e:
                raise Stop("could not download the latest release: %s. Download it by hand and run: "
                           "python3 -I tools/update.py apply <release.zip>" % e)
            zpath = work / "release.zip"
            zpath.write_bytes(data)
        new_top = safe_extract(zpath, work / "new")
        new_v = installed_version(new_top)
        old_v = installed_version(root)
        a, b = parse_version(old_v), parse_version(new_v)
        if b is None:
            raise Stop("the ZIP has an unusable VERSION: %r" % new_v)
        if a is not None and a == b:
            print("Already at version %s. Nothing to do." % new_v)
            return 0
        if a is not None and a > b and not downgrade:
            raise Stop("the ZIP (%s) is older than this copy (%s). Use --allow-downgrade if you really want that "
                       "(the data format of newer versions may not fit)." % (new_v, old_v))
        old_html = rd(root / PAGE)
        old_rules = rd(root / RULES) if (root / RULES).is_file() else ""
        sections, how = extract_user_sections(old_rules)
        sd_old = load_modules(root / "tools")
        old_blocks = read_blocks_lenient(sd_old, old_html)
        nblocks = sum(1 for n in sd_old.BLOCKS if n != "meta" and old_blocks[n] != sd_old.EMPTY[n])
        p = plan(root, new_top)
        show_plan(p, old_v, new_v, how, nblocks)
        if not ask("Update from %s to %s?" % (old_v or "unknown", new_v), stdin, yes):
            print("Cancelled. Nothing was changed.")
            return 1
        bk = make_backup(root, "before-update-%s-to-%s" % (slug(old_v), slug(new_v)), [root])
        print("Backup: %s" % bk)
        try:
            problem = _do_update(root, new_top, p, old_blocks, old_html, sections)
        except BaseException as e:  # restore on anything, including Ctrl-C
            problem = "%s: %s" % (type(e).__name__, e)
            if isinstance(e, KeyboardInterrupt):
                problem = "interrupted"
        if problem:
            print("The update failed:\n%s\nRestoring the backup ..." % problem)
            try:
                restore_backup(bk.name, [root])
            except BaseException as e:
                raise Stop("the automatic restore failed (%s). Your backup is intact: %s. Restore it by hand with "
                           "python3 -I tools/backup.py restore %s" % (e, bk, bk.name))
            print("Restored: the project folder is as it was before the update.")
            return 1
        (root / STATE).write_text(json.dumps({"backup": bk.name, "from": old_v, "to": new_v,
                                              "date": datetime.date.today().isoformat()}, indent=2) + "\n",
                                  encoding="utf-8")
        print("Updated from %s to %s. Backup: %s\nUndo with: python3 -I tools/update.py rollback\n"
              "Start a new session so Claude reads the new CLAUDE.md. What changed: CHANGELOG.md." % (
                  old_v or "unknown", new_v, bk.name))
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _do_update(root, new_top, p, old_blocks, old_html, sections):
    """Replaces files and carries data over; returns a problem text or None."""
    for rel in p["removed"]:
        (root / rel).unlink()
    for d in MANAGED_DIRS + OPTIONAL_MANAGED:  # prune folders emptied by the removals
        base = root / d
        if base.is_dir():
            for cur, dirs, files in os.walk(base, topdown=False):
                if not os.listdir(cur) and Path(cur) != base:
                    os.rmdir(cur)
    for rel, src in p["new"].items():
        dst = root / rel
        if dst.is_symlink():
            dst.unlink()  # never write through a symlink
        elif dst.is_file() and same_bytes(src, dst):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    # page: new template, old data
    for f in (root / PAGE, root / RULES):
        if f.is_symlink():
            f.unlink()
    shutil.copy2(new_top / PAGE, root / PAGE)
    sd = load_modules(root / "tools")
    values = migrated(sd, {n: old_blocks[n] for n in sd.BLOCKS})
    html = rd(root / PAGE)
    wr(root / PAGE, sd.write_blocks(html, values))
    # rules: new text, old user sections
    new_rules = rd(new_top / RULES) if (new_top / RULES).is_file() else ""
    wr(root / RULES, merge_user_sections(new_rules, sections))
    return verify(root, values)


def cmd_rollback(root, stdin, args):
    """Restores the backup of the last update. Note: .update-state.json is part of the backup and is restored
    with it, so a second rollback would revert an earlier update (after a confirmation)."""
    yes = "--yes" in args
    if [a for a in args if a != "--yes"]:
        print(__doc__)
        return 2
    st = read_state(root)
    if not st:
        raise Stop("nothing to roll back: %s does not exist or has no backup entry" % STATE)
    name = st["backup"]
    folder = backup.folder_for(name)
    try:
        entries = json.loads((folder / backup.MANIFEST).read_text(encoding="utf-8"))["entries"]
    except Exception as e:
        raise Stop("the backup manifest is unreadable: %s" % e)
    if len(entries) != 1 or os.path.abspath(entries[0]["original"]) != os.path.abspath(root):
        raise Stop("the backup %s does not belong to this project folder" % name)
    backup.verify_stored(folder, entries)
    src = folder / entries[0]["stored"]
    old, cur = backup.dir_files(src), walk_all(root)
    n_remove = sum(1 for r in cur if r not in old)
    n_diff = sum(1 for r, h in old.items() if r in cur and cur[r] != h)
    n_new = sum(1 for r in old if r not in cur)
    print("Rollback to the state before the update from %s to %s (backup %s):\n"
          "  %d files are restored, %d recreated, %d files created since then are removed "
          "(a safety backup of the current state is made first)." % (
              st.get("from") or "unknown", st.get("to"), name, n_diff, n_new, n_remove))
    if not ask("Roll back?", stdin, yes):
        print("Cancelled. Nothing was changed.")
        return 1
    safety = make_backup(root, "before-rollback", [root])
    print("Safety backup of the current state: %s" % safety)
    restore_backup(name, [root])
    print("Rolled back to version %s." % (st.get("from") or "the previous one"))
    return 0


def walk_all(root):
    return backup.dir_files(root)


def cmd_migrate(root, stdin, args):
    yes = "--yes" in args
    if [a for a in args if a != "--yes"]:
        print(__doc__)
        return 2
    page, rules = root / PAGE, root / RULES
    if not page.is_file():
        raise Stop("%s not found" % PAGE)
    sd = load_modules(root / "tools")
    html = rd(page)
    blocks = read_blocks_lenient(sd, html)
    new_blocks = migrated(sd, blocks)
    new_html = sd.write_blocks(html, new_blocks)
    old_rules = rd(rules) if rules.is_file() else None
    new_rules = add_markers(old_rules) if old_rules is not None else None
    todo = []
    if new_html != html:
        todo.append("page data: schema %d -> %d" % (sd.SCHEMA.version_of(blocks), sd.SCHEMA.CURRENT))
    if new_rules is not None and new_rules != old_rules:
        todo.append("CLAUDE.md: add USER markers around the user sections")
    if not todo:
        print("Nothing to migrate: the data format is current and CLAUDE.md has its markers.")
        return 0
    print("Migration (no files are replaced):\n  " + "\n  ".join(todo))
    if not ask("Migrate?", stdin, yes):
        print("Cancelled. Nothing was changed.")
        return 1
    targets = [page] + ([rules] if new_rules is not None and new_rules != old_rules else [])
    bk = make_backup(root, "before-migrate", targets)
    print("Backup: %s" % bk)
    try:
        wr(page, new_html)
        if new_rules is not None and new_rules != old_rules:
            wr(rules, new_rules)
        problem = verify(root, new_blocks)
    except BaseException as e:
        problem = "%s: %s" % (type(e).__name__, e)
    if problem:
        print("The migration failed:\n%s\nRestoring the backup ..." % problem)
        restore_backup(bk.name, targets)
        print("Restored.")
        return 1
    print("Migrated. Backup: %s" % bk.name)
    return 0


def main(argv=None, root=None, fetcher=None, stdin=None):
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(root).resolve() if root else HERE.parent
    fetcher = fetcher or http_fetch
    stdin = stdin or sys.stdin
    if not args or args[0] in ("-h", "--help") or args[0] not in ("check", "apply", "rollback", "migrate"):
        print(__doc__)
        return 0 if args and args[0] in ("-h", "--help") else 2
    cmd, rest = args[0], args[1:]
    try:
        if cmd == "check":
            if rest:
                print(__doc__)
                return 2
            return cmd_check(root, fetcher)
        if cmd == "apply":
            return cmd_apply(root, fetcher, stdin, rest)
        if cmd == "rollback":
            return cmd_rollback(root, stdin, rest)
        return cmd_migrate(root, stdin, rest)
    except Stop as e:
        print("refused: %s" % e, file=sys.stderr)
        return 1
    except backup.Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
