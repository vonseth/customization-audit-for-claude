#!/usr/bin/env python3
"""Offline version check for installed Claude Code plugins (read-only, no network).

Usage:
    python3 -I tools/check_versions.py [--json]

Compares what is installed (~/.claude/plugins/installed_plugins.json) with the
local marketplace copies (~/.claude/plugins/marketplaces/<marketplace>/, listed
in known_marketplaces.json). The app refreshes these copies itself; this tool
never fetches anything, so "latest" means "latest in the local copy".

How "latest" is determined, per plugin:
  1. Marketplace entry "source" is a relative path -> plugin folder is local.
     External sources (objects) cannot be checked -> unknown.
  2. Version field: the marketplace entry's "version", else the plugin.json
     "version" in the plugin folder. Compared numerically with the installed
     version (installed newer or equal -> up to date). Build metadata ("+build")
     is ignored, missing parts count as zero ("1.2" equals "1.2.0"), and a
     pre-release ("2.0.0-beta.1") is older than the release of the same base
     version ("2.0.0").
  3. No version field: commits. If the marketplace copy is a git checkout, the
     latest commit touching the plugin folder is read with read-only git. The
     plugin counts as up to date when the installed commit equals it or when
     the plugin folder is identical between both commits. If the copy has no
     git history but a .gcs-sha file (snapshot id): equal to the installed
     commit -> up to date, different -> unknown (cannot tell whether this
     plugin changed).
  4. Anything else (git missing, commit not in the copy, ...) -> unknown, with
     the reason.

Not covered: desktop-app plugins and claude.ai skills (no local version source).

Output: one block per plugin (name, marketplace, installed, latest, status,
history link) plus the last update time of each marketplace copy; --json
prints the same data as JSON. If installed_plugins.json does not exist (no local
plugins, e.g. only the desktop app is used), a note goes to stderr, the result is
empty (also with --json) and the exit code is 0. Exit code 0, or 2 on an error
(installed_plugins.json exists but is unreadable).

The environment variable CUSTOMIZATION_AUDIT_HOME replaces the home directory.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

UP, NEWER, UNKNOWN = "up to date", "newer available", "unknown"


def load(path):
    """Read a JSON file; return None if missing or broken."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def git_run(repo, *args):
    """Run a read-only git command (env, timeout); return the CompletedProcess or None."""
    try:
        return subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True,
                              text=True, timeout=30, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    except (OSError, subprocess.SubprocessError):
        return None


def git(repo, *args):
    """Run a read-only git command; return stdout (stripped) or None on failure."""
    r = git_run(repo, *args)
    return r.stdout.strip() if r is not None and r.returncode == 0 else None


def vkey(v):
    """Sortable key of a version string, or None if it has no numbers.

    Build metadata after "+" is dropped; a suffix after "-" marks a pre-release,
    which sorts before the release of the same base version.
    """
    base, _, pre = str(v).split("+")[0].partition("-")
    nums = [int(n) for n in re.findall(r"\d+", base)]
    if not nums:
        return None
    return (tuple(nums), 0 if pre else 1)


def older(a, b):
    """True if version key a is older than b (both from vkey); shorter tuples are zero-padded."""
    n = max(len(a[0]), len(b[0]))
    pa, pb = a[0] + (0,) * (n - len(a[0])), b[0] + (0,) * (n - len(b[0]))
    return (pa, a[1]) < (pb, b[1])


def is_commit_like(v):
    """True for version strings that are just an abbreviated commit hash."""
    return bool(re.fullmatch(r"[0-9a-f]{12}", str(v or "")))


def find_entry(market, name):
    """Return the marketplace.json entry for a plugin name, or None."""
    data = load(Path(market) / ".claude-plugin" / "marketplace.json") or {}
    for p in data.get("plugins", []):
        if p.get("name") == name:
            return p
    return None


def history_link(src, sha_old, sha_new, rel, ref):
    """GitHub history/compare URL for a github marketplace source, else None."""
    if not isinstance(src, dict) or src.get("source") != "github" or not src.get("repo"):
        return None
    base = "https://github.com/" + src["repo"]
    if sha_old and sha_new and sha_old != sha_new:
        return "%s/compare/%s...%s" % (base, sha_old, sha_new)
    return "%s/commits/%s%s" % (base, ref or "HEAD", "/" + rel if rel else "")


def check(key, inst, known):
    """Check one installed plugin entry; return a result dict."""
    name, _, mkt = key.partition("@")
    ver, sha = inst.get("version"), inst.get("gitCommitSha") or ""
    if not sha and is_commit_like(ver):
        sha = ver
    res = {"name": name, "marketplace": mkt, "installed_version": ver,
           "installed_commit": sha[:8] or None, "latest_version": None,
           "latest_commit": None, "status": UNKNOWN, "reason": None, "history": None}
    km = known.get(mkt)
    if not km:
        res["reason"] = "marketplace not listed in known_marketplaces.json"
        return res
    src = km.get("source")
    mdir = Path(km.get("installLocation") or "")
    ref = src.get("ref") if isinstance(src, dict) else None
    entry = find_entry(mdir, name) if mdir.is_dir() else None
    if entry is None:
        res["reason"] = "plugin not found in the local marketplace copy"
        return res
    psrc = entry.get("source")
    if not isinstance(psrc, str):
        res["reason"] = "plugin comes from an external source, not in the local copy"
        return res
    rel = os.path.normpath(psrc)
    rel = "" if rel == "." else rel
    pdir = mdir / rel
    res["history"] = history_link(src, None, None, rel, ref)
    meta = load(pdir / ".claude-plugin" / "plugin.json") or {}
    latest = entry.get("version") or meta.get("version")
    if latest and not is_commit_like(ver):
        res["latest_version"] = str(latest)
        a, b = vkey(ver), vkey(latest)
        if a is None or b is None:
            res["status"] = UP if str(ver) == str(latest) else UNKNOWN
            res["reason"] = None if res["status"] == UP else "versions not comparable"
        else:
            res["status"] = NEWER if older(a, b) else UP
        return res
    # commit-based
    if (mdir / ".git").exists():
        top = git(mdir, "log", "-1", "--format=%H", "--", rel or ".")
        if top is None:
            res["reason"] = "git not available or unreadable history"
            return res
        res["latest_commit"] = top[:8]
        if not sha:
            res["reason"] = "installed commit unknown"
        elif top.startswith(sha) or sha.startswith(top):
            res["status"] = UP
        elif git(mdir, "cat-file", "-t", sha) != "commit":
            res["reason"] = "installed commit not in the local marketplace copy"
        else:
            r = git_run(mdir, "diff", "--quiet", sha, top, "--", rel or ".")
            if r is None or r.returncode not in (0, 1):
                res["reason"] = "git diff failed"
                return res
            res["status"] = UP if r.returncode == 0 else NEWER
            if res["status"] == NEWER:
                full = git(mdir, "rev-parse", sha)
                res["history"] = history_link(src, full, top, rel, ref)
        return res
    gcs = (mdir / ".gcs-sha")
    if gcs.is_file():
        snap = gcs.read_text().strip()
        res["latest_commit"] = snap[:8]
        if sha and (snap.startswith(sha) or sha.startswith(snap)):
            res["status"] = UP
        elif sha:
            res["reason"] = "marketplace snapshot differs and has no history; cannot tell if this plugin changed"
        else:
            res["reason"] = "installed commit unknown"
        return res
    res["reason"] = "no version field and no git history in the local copy"
    return res


def run():
    """Collect results for all installed plugins and marketplaces."""
    pdir = paths.claude_dir() / "plugins"
    if not (pdir / "installed_plugins.json").exists():
        print("no local plugins found; desktop-app plugins and claude.ai skills are not covered "
              "by this tool", file=sys.stderr)
        return {"plugins": [], "marketplaces": []}
    inst = load(pdir / "installed_plugins.json")
    if not isinstance(inst, dict) or not isinstance(inst.get("plugins"), dict):
        print("error: cannot read %s" % (pdir / "installed_plugins.json"), file=sys.stderr)
        return None
    known = load(pdir / "known_marketplaces.json") or {}
    results = []
    for key in sorted(inst["plugins"]):
        for i in inst["plugins"][key] or []:
            results.append(check(key, i, known))
    used = sorted({r["marketplace"] for r in results})
    marks = [{"marketplace": m, "last_updated": (known.get(m) or {}).get("lastUpdated")} for m in used]
    return {"plugins": results, "marketplaces": marks}


def main(argv):
    """Entry point."""
    if any(a not in ("--json",) for a in argv):
        print(__doc__)
        return 2 if any(a not in ("-h", "--help") for a in argv) else 0
    out = run()
    if out is None:
        return 2
    if "--json" in argv:
        print(json.dumps(out, indent=2))
        return 0
    for r in out["plugins"]:
        inst = "%s (%s)" % (r["installed_version"] or "?", r["installed_commit"] or "no commit")
        lat = r["latest_version"] or r["latest_commit"] or "?"
        print("%s @ %s" % (r["name"], r["marketplace"]))
        print("  installed: %s" % inst)
        print("  latest in local marketplace copy: %s" % lat)
        print("  status: %s%s" % (r["status"], " - " + r["reason"] if r["reason"] else ""))
        if r["history"]:
            print("  history: %s" % r["history"])
    print("\nMarketplace copies, last updated:")
    for m in out["marketplaces"]:
        print("  %s: %s" % (m["marketplace"], m["last_updated"] or "unknown"))
    counts = {}
    for r in out["plugins"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\nSummary: " + ", ".join("%d %s" % (n, s) for s, n in sorted(counts.items())))
    print("Note: the app refreshes the marketplace copies itself; this check is offline and only "
          "as current as they are.")
    print("Not covered: desktop-app plugins and claude.ai skills.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
