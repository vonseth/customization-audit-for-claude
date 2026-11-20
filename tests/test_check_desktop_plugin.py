"""Tests for tools/check_desktop_plugin.py. Run: python3 -I tests/test_check_desktop_plugin.py
Uses a fake home (CUSTOMIZATION_AUDIT_HOME) in a temp dir; the real home is never touched."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
TOOL = str(ROOT / "tools" / "check_desktop_plugin.py")
ORG = "aaaaaaaa-1111-2222-3333-444444444444"
ORG2 = "bbbbbbbb-1111-2222-3333-444444444444"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(home, *args):
    env = dict(os.environ, CUSTOMIZATION_AUDIT_HOME=str(home))
    p = subprocess.run([sys.executable, "-I", TOOL] + list(args), capture_output=True, text=True, env=env)
    return p.returncode, p.stdout, p.stderr


if sys.platform != "darwin":
    print("test_check_desktop_plugin: skipped (fake desktop folder layout is macOS only)")
    sys.exit(0)

with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp).resolve() / "home"
    sess = home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
    rpm = sess / "u1" / ORG / "rpm"
    write(rpm / "manifest.json", json.dumps({"plugins": [{"id": "plugin_a", "displayName": "Alpha"}]}))
    write(rpm / "plugin_a" / ".claude-plugin" / "plugin.json", json.dumps({"name": "alpha-inner"}))
    write(sess / "skills-plugin" / ORG / "u1" / "skills" / "web-skill" / "SKILL.md", "---\nname: web-skill\n---\n")

    # --help: usage on stdout, exit 0, nothing else
    rc, out, err = run(home, "--help")
    assert rc == 0 and "Usage:" in out and err == "", (rc, out, err)
    rc, out, _ = run(home, "-h", "alpha")
    assert rc == 0 and "Usage:" in out and "Organization" not in out
    assert run(home, "--bogus")[0] == 2 and run(home, "a", "b")[0] == 2

    # a claude.ai skill that is installed is NOT reported as removed (was a false "removed")
    rc, out, _ = run(home, "web-skill")
    assert rc == 0 and "No, it was not removed." in out and "Yes, it was removed." not in out, out
    assert "claude.ai skill folder present: YES" in out
    rc, out, _ = run(home, "WEB-SKILL")
    assert "No, it was not removed." in out
    # plugin still found, unknown name is removed
    assert "No, it was not removed." in run(home, "alpha")[1]
    rc, out, _ = run(home, "gone")
    assert rc == 0 and "Yes, it was removed." in out, out

    # listing mode labels both kinds
    rc, out, _ = run(home)
    assert rc == 0 and "Alpha (alpha-inner) [plugin]" in out and "web-skill [claude.ai skill]" in out, out

    # a skills-only organization is reported too
    write(sess / "skills-plugin" / ORG2 / "u2" / "skills" / "other" / "SKILL.md", "x")
    out = run(home, "other")[1]
    assert "Organization bbbbbbbb" in out and "No, it was not removed." in out, out

    # unreadable manifest: Unknown, exit 1 (was a false "Yes, it was removed.")
    (rpm / "manifest.json").write_text("{ not json", encoding="utf-8")
    rc, out, _ = run(home, "alpha")
    assert rc == 1 and "Unknown:" in out and "Yes, it was removed." not in out.split("Organization aaaaaaaa")[1].split("Organization bbbbbbbb")[0], out
    # ... but a skill that is present still wins over the unreadable list
    rc, out, _ = run(home, "web-skill")
    assert "Result: No, it was not removed." in out.split("Organization aaaaaaaa")[1].split("Organization bbbbbbbb")[0], out
    # unreadable plugin.json also gives Unknown
    write(rpm / "manifest.json", json.dumps({"plugins": [{"id": "plugin_a", "displayName": "Alpha"}]}))
    (rpm / "plugin_a" / ".claude-plugin" / "plugin.json").write_text("nope", encoding="utf-8")
    rc, out, _ = run(home, "gone")
    assert rc == 1 and "Unknown:" in out, out

print("test_check_desktop_plugin: OK")
