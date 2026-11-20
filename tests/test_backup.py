"""Tests for tools/backup.py. Run: python3 -I tests/test_backup.py
Uses a fake home (CUSTOMIZATION_AUDIT_HOME) in a temp dir; the real home is never touched."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
TOOL = str(ROOT / "tools" / "backup.py")
TMP = tempfile.TemporaryDirectory()
HOME = Path(TMP.name).resolve() / "home"
HOME.mkdir()
ENV = dict(os.environ, CUSTOMIZATION_AUDIT_HOME=str(HOME))
BK = HOME / ".claude" / "backups"


def run(*args, stdin=""):
    p = subprocess.run([sys.executable, "-I", TOOL] + list(args), input=stdin,
                       capture_output=True, text=True, env=ENV)
    return p.returncode, p.stdout, p.stderr


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


f = HOME / ".claude" / "settings.json"
f.parent.mkdir(parents=True)
f.write_text('{"a": 1}')
d = HOME / ".claude" / "skills" / "demo"
(d / "sub").mkdir(parents=True)
(d / "SKILL.md").write_text("skill")
(d / "sub" / "x.txt").write_text("x")
orig_sha = sha(f)

# create: bad reason, missing path, ok
assert run("create", "Bad Reason", str(f))[0] == 1
assert run("create", "t", str(HOME / "nope"))[0] == 1
rc, out, _ = run("create", "test-run", str(f), str(d))
assert rc == 0, out
folder = Path(out.strip())
assert folder.parent == BK and folder.name.startswith("test-run-")
m = json.loads((folder / "manifest.json").read_text())
assert m["reason"] == "test-run" and len(m["entries"]) == 2
assert m["entries"][0]["sha256"] == orig_sha and m["entries"][1]["type"] == "dir"
rc, out2, _ = run("create", "test-run", str(f))
assert Path(out2.strip()).name == folder.name + "-2"

# list / show
rc, out, _ = run("list")
assert rc == 0 and "test-run" in out and "2 entries" in out
rc, out, _ = run("show", folder.name)
assert rc == 0 and str(f) in out

# old-style folder
(BK / "old-style-2026-01-01").mkdir()
assert "no manifest (restore by hand)" in run("list")[1]
assert run("restore", "old-style-2026-01-01", "--yes")[0] == 1

# modify, restore declined
f.write_text('{"a": 2}')
(d / "sub" / "x.txt").write_text("changed")
(d / "extra.txt").write_text("keep me")
rc, out, _ = run("restore", folder.name, stdin="n\n")
assert rc == 1 and "OVERWRITE" in out and "Restore these 2 items? [y/N]" in out
assert f.read_text() == '{"a": 2}' and (d / "sub" / "x.txt").read_text() == "changed"
assert run("restore", folder.name, stdin="")[0] == 1  # EOF = cancel

# restore confirmed
before = set(os.listdir(BK))
rc, out, _ = run("restore", folder.name, stdin="y\n")
assert rc == 0, out
assert sha(f) == orig_sha and (d / "sub" / "x.txt").read_text() == "x"
assert (d / "extra.txt").read_text() == "keep me"  # never deletes
new = set(os.listdir(BK)) - before
assert any(n.startswith("before-restore-") for n in new), new
safety = next(n for n in new if n.startswith("before-restore-"))
assert json.loads((BK / safety / "manifest.json").read_text())["entries"][0]["sha256"] != orig_sha

# manifest with outside-home path refused
bad = BK / "evil-2026-01-01"
(bad / "1").mkdir(parents=True)
(bad / "1" / "x").write_text("pwn")
outside = Path(TMP.name).resolve() / "outside.txt"
(bad / "manifest.json").write_text(json.dumps({"created": "2026-01-01T00:00:00", "reason": "evil",
    "tool_version": "x", "entries": [{"original": str(outside), "stored": "1/x",
                                      "type": "file", "sha256": "0", "size": 4}]}))
rc, _, err = run("restore", "evil-2026-01-01", "--yes")
assert rc == 1 and "outside your home" in err and not outside.exists()

# 1. recursion: backups folder, its parent and a folder inside it are refused, nothing created
before = sorted(os.listdir(BK))
for bad_path in (BK, BK.parent, folder):
    rc, _, err = run("create", "loop", str(bad_path))
    assert rc == 1 and "backups folder" in err, (bad_path, rc, err)
assert sorted(os.listdir(BK)) == before
link = HOME / "bklink"
link.symlink_to(BK)
rc, _, err = run("create", "loop", str(link))
assert rc == 1 and "backups folder" in err  # symlink to the backups folder is caught by realpath
link.unlink()

# 1b. failed copy removes only its own unfinished folder
if os.geteuid() != 0:
    broken = HOME / "broken"
    broken.mkdir()
    (broken / "ok.txt").write_text("ok")
    (broken / "secret.txt").write_text("no")
    (broken / "secret.txt").chmod(0)
    before = sorted(os.listdir(BK))
    rc, _, err = run("create", "failing", str(broken))
    (broken / "secret.txt").chmod(0o600)
    assert rc != 0 and sorted(os.listdir(BK)) == before, (rc, err)
    assert (broken / "ok.txt").exists()  # originals untouched

# 2. manifest original that is a symlink pointing outside home is refused
out_dir = Path(TMP.name).resolve() / "elsewhere"
out_dir.mkdir()
(HOME / "sneaky").symlink_to(out_dir)
sn = BK / "sneaky-2026-01-01"
(sn / "1").mkdir(parents=True)
(sn / "1" / "x").write_text("pwn")
(sn / "manifest.json").write_text(json.dumps({"created": "2026-01-01T00:00:00", "reason": "sneaky",
    "tool_version": "x", "entries": [{"original": str(HOME / "sneaky" / "x"), "stored": "1/x",
                                      "type": "file", "sha256": sha(sn / "1" / "x"), "size": 3}]}))
rc, _, err = run("restore", "sneaky-2026-01-01", "--yes")
assert rc == 1 and "outside your home" in err and not (out_dir / "x").exists()

# 3. damaged backup: tampered stored file (single and in folder) refused before writing anything
rc, out, _ = run("create", "damage", str(f), str(d))
dmg = Path(out.strip())
f.write_text('{"a": 3}')
(d / "sub" / "x.txt").write_text("current")
(dmg / "1" / "settings.json").write_text("tampered")
rc, out, err = run("restore", dmg.name, "--yes")
assert rc == 1 and "backup is damaged" in err and f.read_text() == '{"a": 3}'
(dmg / "1" / "settings.json").write_text('{"a": 1}')  # repair first item
(dmg / "2" / "demo" / "sub" / "x.txt").write_text("tampered")
rc, out, err = run("restore", dmg.name, "--yes")
assert rc == 1 and "backup is damaged" in err
assert (d / "sub" / "x.txt").read_text() == "current" and f.read_text() == '{"a": 3}'

print("all backup tests passed")
