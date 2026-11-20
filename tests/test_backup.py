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

def fake_backup(name, entries, files=None):
    """A hand-made backup folder with the given manifest entries and stored files {relative: text}."""
    b = BK / name
    for rel, text in (files or {}).items():
        (b / rel).parent.mkdir(parents=True, exist_ok=True)
        (b / rel).write_text(text)
    (b / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (b / "manifest.json").write_text(json.dumps({"created": "2026-01-01T00:00:00", "reason": "evil",
                                                 "tool_version": "x", "entries": entries}))
    return name


# 3. outside the home folder: restorable only after an extra warning and the normal confirmation
outside = Path(TMP.name).resolve() / "proj" / "outside.txt"
outside.parent.mkdir()
(BK / "outside-2026-01-01" / "1").mkdir(parents=True)
(BK / "outside-2026-01-01" / "1" / "x").write_text("data")
fake_backup("outside-2026-01-01", [{"original": str(outside), "stored": "1/x", "type": "file",
                                    "sha256": hashlib.sha256(b"data").hexdigest(), "size": 4}])
rc, out, _ = run("restore", "outside-2026-01-01", stdin="n\n")
assert rc == 1 and "outside your home folder" in out and "WARNING" in out and not outside.exists(), out
rc, out, _ = run("restore", "outside-2026-01-01", stdin="y\n")
assert rc == 0 and outside.read_text() == "data" and "outside your home folder" in out, out
assert "outside your home folder" not in run("restore", folder.name, "--yes")[1]  # normal restore: no warning
# a path inside the home folder reached through a symlink to outside is outside too
out_dir = Path(TMP.name).resolve() / "elsewhere"
out_dir.mkdir()
(HOME / "sneaky").symlink_to(out_dir)
(BK / "sneaky-2026-01-01" / "1").mkdir(parents=True)
(BK / "sneaky-2026-01-01" / "1" / "x").write_text("pwn")
fake_backup("sneaky-2026-01-01", [{"original": str(HOME / "sneaky" / "x"), "stored": "1/x", "type": "file",
                                   "sha256": sha(BK / "sneaky-2026-01-01" / "1" / "x"), "size": 3}])
rc, out, _ = run("restore", "sneaky-2026-01-01", stdin="n\n")
assert rc == 1 and "outside your home folder" in out and not (out_dir / "x").exists()
# still refused: relative paths, "..", system locations
for n, o in (("rel", "relative/x.txt"), ("dots", str(HOME / ".." / "x.txt")), ("root", "/"),
             ("etc", "/etc/hosts"), ("usr", "/usr/local/x"), ("sys", "/System/x")) + (
             (("lib", "/Library/x"),) if sys.platform == "darwin" else ()):
    (BK / ("bad-%s-2026-01-01" % n) / "1").mkdir(parents=True)
    (BK / ("bad-%s-2026-01-01" % n) / "1" / "x").write_text("pwn")
    fake_backup("bad-%s-2026-01-01" % n, [{"original": o, "stored": "1/x", "type": "file", "sha256": "0", "size": 3}])
    rc, _, err = run("restore", "bad-%s-2026-01-01" % n, "--yes")
    assert rc == 1 and "manifest refused" in err, (n, rc, err)

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

# 4. symlinks are stored and restored as links, never followed
lk = HOME / "linky"
(lk / "real").mkdir(parents=True)
(lk / "real" / "a.txt").write_text("A")
(lk / "valid").symlink_to("real/a.txt")
(lk / "dangling").symlink_to("does-not-exist")
(lk / "dirlink").symlink_to("real")
top_dangling = HOME / "topdangling"
top_dangling.symlink_to("nowhere")
rc, out, err = run("create", "links", str(lk), str(top_dangling))  # a dangling link used to crash create
assert rc == 0, err
lf = Path(out.strip())
m = json.loads((lf / "manifest.json").read_text())
e0, e1 = m["entries"]
assert e0["links"] == {"valid": "real/a.txt", "dangling": "does-not-exist", "dirlink": "real"}, e0
assert list(e0["files"]) == ["real/a.txt"], e0  # links are not counted as files
assert e1["type"] == "symlink" and e1["target"] == "nowhere" and "sha256" not in e1, e1
assert (lf / "1" / "linky" / "valid").is_symlink() and (lf / "1" / "linky" / "dirlink").is_symlink()
assert "-> nowhere" in run("show", lf.name)[1]
# damage the folder, then restore: links come back as links
for n in ("valid", "dangling", "dirlink"):
    (lk / n).unlink()
(lk / "valid").write_text("a plain file now")
(lk / "dirlink").mkdir()
top_dangling.unlink()
(lk / "real" / "a.txt").write_text("A2")
rc, out, err = run("restore", lf.name, "--yes")
# (the folder in place of the link "dirlink" must be refused, not replaced)
assert rc == 1 and "cannot replace a folder" in err, (rc, out, err)
(lk / "dirlink").rmdir()
rc, out, err = run("restore", lf.name, "--yes")
assert rc == 0, (out, err)
assert os.readlink(lk / "valid") == "real/a.txt" and os.readlink(lk / "dangling") == "does-not-exist"
assert os.readlink(lk / "dirlink") == "real" and os.readlink(top_dangling) == "nowhere"
assert (lk / "real" / "a.txt").read_text() == "A"  # the real file is restored, not written through a link
# restore never writes through a symlink in the way: a link where the backup has a folder is refused
shutil_target = Path(TMP.name).resolve() / "linktarget"
shutil_target.mkdir()
(lk / "real").rename(lk / "real-moved")
(lk / "real").symlink_to(shutil_target)
bk_before = sorted(os.listdir(BK))
rc, out, err = run("restore", lf.name, "--yes")
assert rc == 1 and "symlink" in err and not any(shutil_target.iterdir()), (rc, out, err)
assert sorted(os.listdir(BK)) == bk_before, "refused before the safety backup, nothing half-done"

# 5. -h / --help anywhere: usage on stdout, exit 0, nothing else
before = sorted(os.listdir(BK))
for a in (["-h"], ["--help"], ["create", "--help"], ["restore", "x", "-h"]):
    rc, out, err = run(*a)
    assert rc == 0 and "Usage:" in out and err == "", (a, rc, err)
assert sorted(os.listdir(BK)) == before
rc, out, err = run("bogus")
assert rc == 2 and out == "" and "Usage:" in err

print("all backup tests passed")
