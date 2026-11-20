#!/usr/bin/env python3
"""Self-check for the audit tools.

Usage:
    python3 -I tools/selftest.py

Builds a fake home directory in a temporary folder (minimal ~/.claude with one
plugin, settings.json, one skill and one transcript; on macOS also a fake
desktop-app folder with two organizations), runs every tool via subprocess
with CUSTOMIZATION_AUDIT_HOME pointing to it, and checks exit codes and rows.
Also runs every tool against a completely empty fake home (must exit 0).
Only the temporary folder is written; it is removed afterwards.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
ORG_A = "aaaaaaaa-1111-2222-3333-444444444444"
ORG_B = "bbbbbbbb-1111-2222-3333-444444444444"
SESSION = "12345678-1234-1234-1234-123456789abc"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_home(home):
    c = home / ".claude"
    plugin = c / "plugins" / "cache" / "demo" / "demo-plugin" / "1.0"
    write(plugin / "skills" / "demo" / "SKILL.md", "---\nname: demo\ndescription: A demo skill.\n---\nbody\n")
    write(c / "plugins" / "installed_plugins.json", json.dumps(
        {"version": 2, "plugins": {"demo-plugin@demo": [{"installPath": str(plugin)}]}}))
    write(c / "settings.json", json.dumps({"enabledPlugins": {"demo-plugin@demo": True}}))
    write(c / "skills" / "my-skill" / "SKILL.md",
          "---\nname: my-skill\ndescription: My own skill for testing.\n---\nbody\n")
    lines = [
        {"type": "assistant", "timestamp": "2026-01-02T10:00:00Z", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "my-skill"}},
            {"type": "tool_use", "id": "t2", "name": "mcp__demo-server__do_thing", "input": {}}]}},
        {"type": "user", "timestamp": "2026-01-02T10:01:00Z",
         "message": {"role": "user", "content": "<command-name>/my-command</command-name>"}},
    ]
    write(c / "projects" / "proj" / (SESSION + ".jsonl"), "\n".join(json.dumps(x) for x in lines) + "\n")
    if sys.platform == "darwin":
        sess = home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
        for org, name in ((ORG_A, "Alpha"), (ORG_B, "Beta")):
            rpm = sess / "user-1" / org / "rpm"
            write(rpm / "manifest.json", json.dumps({"plugins": [
                {"id": "plugin_" + name.lower(), "displayName": name, "installedBy": "user"}]}))
            write(rpm / ("plugin_" + name.lower()) / ".claude-plugin" / "plugin.json",
                  json.dumps({"name": name.lower() + "-inner"}))
            write(rpm / ("plugin_" + name.lower()) / "skills" / "s" / "SKILL.md",
                  "---\nname: s\ndescription: d\n---\n")
        write(sess / "skills-plugin" / ORG_A / "user-1" / "skills" / "web-skill" / "SKILL.md",
              "---\nname: web-skill\ndescription: A web skill.\n---\n")


def run(tool, home, *args):
    env = dict(os.environ, CUSTOMIZATION_AUDIT_HOME=str(home))
    p = subprocess.run([sys.executable, "-I", str(HERE / tool), *args], env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, "%s exited %d: %s" % (tool, p.returncode, p.stderr)
    return p.stdout, p.stderr


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        build_home(home)
        out, _ = run("inventory.py", home)
        assert "local-plugin\t\tdemo-plugin@demo\tactive\t1" in out, out
        assert "own-skill\t\tmy-skill\tok" in out, out
        if sys.platform == "darwin":
            assert "desktop-plugin\taaaaaaaa\tAlpha (alpha-inner)" in out, out
            assert "desktop-plugin\tbbbbbbbb\tBeta (beta-inner)" in out, out
            assert "claude-ai-skill\taaaaaaaa\tweb-skill" in out, out
        out, _ = run("count_usage.py", home)
        assert "  my-skill\t1\t2026-01-02" in out, out
        assert "/my-command" in out and "custom" in out, out
        assert "demo-server\t1" in out, out
        out, _ = run("count_mcp_usage.py", home, SESSION)
        assert "demo-server\t1\t" in out and "do_thing 1" in out, out
        out, _ = run("check_desktop_plugin.py", home, "alpha")
        if sys.platform == "darwin":
            assert "Organization aaaaaaaa" in out and "No, it was not removed." in out, out
            out, _ = run("check_desktop_plugin.py", home, "gone")
            assert "Yes, it was removed." in out, out
        out_file = Path(tmp) / "inv.tsv"
        run("inventory.py", home, str(out_file))
        assert out_file.read_text(encoding="utf-8").startswith("source\torganization"), "no output file"
        print("fake home: OK")

        empty = Path(tmp) / "empty"
        empty.mkdir()
        for tool in ("inventory.py", "check_desktop_plugin.py", "count_usage.py", "count_mcp_usage.py"):
            _, err = run(tool, empty)
            print("empty home: %s OK (stderr notes: %d)" % (tool, len(err.splitlines())))
    print("selftest passed")


if __name__ == "__main__":
    main()
