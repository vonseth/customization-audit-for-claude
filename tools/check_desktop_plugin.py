#!/usr/bin/env python3
"""Check whether a desktop-app plugin or claude.ai skill is really removed (read-only).

Usage:
    python3 -I tools/check_desktop_plugin.py "<display name, plugin name or skill name>"
    python3 -I tools/check_desktop_plugin.py          # list all desktop plugins and claude.ai skills
    python3 -I tools/check_desktop_plugin.py -h       # this text

What it reads: rpm/manifest.json and plugin_*/.claude-plugin/plugin.json (plugins) and
skills-plugin/<org>/<user>/skills/<name>/ (claude.ai skills) below the Claude desktop
app's local-agent-mode-sessions folder (macOS tested, Windows untested, not scanned on
Linux). It writes nothing.
CUSTOMIZATION_AUDIT_HOME replaces the home directory (for testing).

Output per organization: number of plugins, timestamp of the plugin list, whether the
name is still in the list, whether a plugin folder or a skill folder with that name
still exists, then a final answer "Yes, it was removed." / "No, it was not removed." /
"Unknown: <reason>" (a plugin list or plugin.json could not be read, so nothing can be
confirmed). Missing desktop-app data is reported on stderr, exit code 0.
Exit codes: 0 answered (also "No"), 1 "Unknown" for at least one organization, 2 usage error.
"""
import glob
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402


def load_json(path):
    """Parsed JSON, or None if the file cannot be read or parsed (a note goes to stderr)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        paths.note("cannot read %s (%s), skipped" % (path, exc))
        return None


def collect(root):
    """Return {org: {"lists": [...], "skills": [...]}} for one local-agent-mode-sessions folder.

    lists:  dicts with names [(display, inner)], stamp, folders [plugin.json name], errors [reason]
    skills: skill folder names (claude.ai skills)
    """
    orgs = {}
    for man in sorted(glob.glob(glob.escape(str(root)) + "/*/*/rpm/manifest.json")):
        org = paths.short(Path(man).parts[-3])
        rpm = os.path.dirname(man)
        rec = {"names": [], "folders": [], "errors": [], "count": 0,
               "stamp": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(man)))}
        d = load_json(man)
        if d is None:
            rec["errors"].append("plugin list %s could not be read" % man)
        items = d if isinstance(d, list) else (d.get("plugins", []) if isinstance(d, dict) else [])
        items = [it for it in items if isinstance(it, dict) and "id" in it]
        rec["count"] = len(items)
        for it in items:
            pj = os.path.join(rpm, str(it["id"]), ".claude-plugin", "plugin.json")
            inner = "?"
            if os.path.exists(pj):
                data = load_json(pj)
                if data is None:
                    rec["errors"].append("%s could not be read" % pj)
                else:
                    inner = (data if isinstance(data, dict) else {}).get("name")
            rec["names"].append((str(it.get("displayName")), str(inner)))
        for pj in glob.glob(glob.escape(rpm) + "/plugin_*/.claude-plugin/plugin.json"):
            data = load_json(pj)
            if data is None:
                rec["errors"].append("%s could not be read" % pj)
            elif isinstance(data, dict):
                rec["folders"].append(str(data.get("name", "")))
        orgs.setdefault(org, {"lists": [], "skills": []})["lists"].append(rec)
    for sk in sorted(glob.glob(glob.escape(str(root)) + "/skills-plugin/*/*/skills")):
        org = paths.short(Path(sk).parts[-3])
        names = sorted(n for n in os.listdir(sk) if os.path.isdir(os.path.join(sk, n)))
        orgs.setdefault(org, {"lists": [], "skills": []})["skills"].extend(names)
    return orgs


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    args = sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        return 0
    if len(args) > 1 or (args and args[0].startswith("-")):
        print("usage: check_desktop_plugin.py [<name>]   (see -h)", file=sys.stderr)
        return 2
    target = args[0].lower() if args else None
    data_dirs, why = paths.desktop_data_dirs()
    if why:
        paths.note(why)
    orgs = {}
    for root in paths.sessions_roots(data_dirs):
        for org, v in collect(root).items():
            o = orgs.setdefault(org, {"lists": [], "skills": []})
            o["lists"].extend(v["lists"])
            o["skills"].extend(v["skills"])
    unknown = False
    for org in sorted(orgs):
        lists, skills = orgs[org]["lists"], orgs[org]["skills"]
        n_plugins = sum(r["count"] for r in lists)
        stamps = ", ".join(r["stamp"] for r in lists)
        print("Organization %s: %d plugins%s, %d claude.ai skills" % (
            org, n_plugins, ", list updated " + stamps if lists else " (no plugin list)", len(skills)))
        if target is None:
            for r in lists:
                for a, b in r["names"]:
                    print("  - %s (%s) [plugin]" % (a, b))
            for n in sorted(set(skills)):
                print("  - %s [claude.ai skill]" % n)
            continue
        in_list = [n for r in lists for n in r["names"] if target in (n[0].lower(), n[1].lower())]
        folders = [f for r in lists for f in r["folders"] if f.lower() == target]
        skill_hit = [n for n in skills if n.lower() == target]
        errors = [e for r in lists for e in r["errors"]]
        print("  in the plugin list: %s | plugin folder present: %s | claude.ai skill folder present: %s" % (
            "YES" if in_list else "no", "YES" if folders else "no", "YES" if skill_hit else "no"))
        if in_list or folders or skill_hit:
            print("  Result: No, it was not removed.")
        elif errors:
            unknown = True
            print("  Result: Unknown: " + "; ".join(errors))
        else:
            print("  Result: Yes, it was removed.")
    if not orgs:
        paths.note("no desktop-app plugin lists or claude.ai skills found, nothing to check")
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
