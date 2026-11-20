#!/usr/bin/env python3
"""Check whether a desktop-app plugin is really removed (read-only).

Usage:
    python3 -I tools/check_desktop_plugin.py "<display name or plugin name>"
    python3 -I tools/check_desktop_plugin.py          # list all desktop plugins

What it reads: rpm/manifest.json and plugin_*/.claude-plugin/plugin.json below
the Claude desktop app's local-agent-mode-sessions folder (macOS tested,
Windows untested, not scanned on Linux). It writes nothing.
CUSTOMIZATION_AUDIT_HOME replaces the home directory (for testing).

Output per organization: number of plugins, timestamp of the plugin list,
whether the name is still in the list and whether a plugin folder with that
name still exists, then a final answer "Yes, it was removed." / "No, it was
not removed." Missing desktop-app data is reported on stderr, exit code 0.
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
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        paths.note("cannot read %s (%s), skipped" % (path, exc))
        return None


def main():
    target = sys.argv[1].lower() if len(sys.argv) > 1 else None
    data_dirs, why = paths.desktop_data_dirs()
    if why:
        paths.note(why)
    found_any = False
    for root in paths.sessions_roots(data_dirs):
        for man in sorted(glob.glob(glob.escape(str(root)) + "/*/*/rpm/manifest.json")):
            found_any = True
            org = paths.short(Path(man).parts[-3])
            rpm = os.path.dirname(man)
            d = load_json(man)
            items = d if isinstance(d, list) else (d or {}).get("plugins", [])
            items = [it for it in items if isinstance(it, dict) and "id" in it]
            names = []
            for it in items:
                pj = os.path.join(rpm, it["id"], ".claude-plugin", "plugin.json")
                inner = (load_json(pj) or {}).get("name") if os.path.exists(pj) else "?"
                names.append((str(it.get("displayName")), str(inner)))
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(man)))
            print("Organization %s: %d plugins, list updated %s" % (org, len(items), stamp))
            if target is None:
                for a, b in names:
                    print("  - %s (%s)" % (a, b))
                continue
            in_list = [n for n in names if target in (n[0].lower(), n[1].lower())]
            folders = []
            for pj in glob.glob(glob.escape(rpm) + "/plugin_*/.claude-plugin/plugin.json"):
                data = load_json(pj) or {}
                if str(data.get("name", "")).lower() == target:
                    folders.append(pj)
            print("  in the list: %s | folder present: %s" % (
                "YES" if in_list else "no", "YES" if folders else "no"))
            print("  Result:", "No, it was not removed." if (in_list or folders)
                  else "Yes, it was removed.")
    if not found_any:
        paths.note("no desktop-app plugin lists found, nothing to check")


if __name__ == "__main__":
    main()
