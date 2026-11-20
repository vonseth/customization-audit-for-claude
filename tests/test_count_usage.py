"""Tests for tools/count_usage.py. Run: python3 -I tests/test_count_usage.py
Uses a fake home (CUSTOMIZATION_AUDIT_HOME) in a temp dir; the real home is never touched."""
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
TOOL = str(ROOT / "tools" / "count_usage.py")
sys.path.insert(0, str(ROOT / "tools"))
import count_usage  # noqa: E402


def run(home, *args):
    env = dict(os.environ, CUSTOMIZATION_AUDIT_HOME=str(home))
    p = subprocess.run([sys.executable, "-I", TOOL] + list(args), capture_output=True, text=True, env=env)
    return p.returncode, p.stdout, p.stderr


def slash(out):
    """{command: count} from the SLASH section."""
    rows, on = {}, False
    for line in out.splitlines():
        if line == "SLASH":
            on = True
        elif not line.startswith("  "):
            on = False
        elif on:
            c = line.split("\t")
            rows[c[0].strip()] = int(c[1])
    return rows


def ms(iso):
    return int(datetime.datetime.fromisoformat(iso).replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)


# 5. timestamps: fractions of any length (Python 3.9 fromisoformat only knows 3 or 6 digits)
for v in ("2026-11-20T10:00:00.1234567Z", "2026-11-20T10:00:00.1Z", "2026-11-20T10:00:00.12Z",
          "2026-11-20T10:00:00.123456789+00:00", "2026-11-20T10:00:00Z"):
    t = count_usage.parse_ts(v)
    assert t is not None and t.replace(microsecond=0) == datetime.datetime(2026, 11, 20, 10, 0, 0,
                                                                          tzinfo=datetime.timezone.utc), v
assert count_usage.parse_ts("2026-11-20T10:00:00.1234567Z").microsecond == 123456
assert count_usage.parse_ts("not a date") is None and count_usage.parse_ts("") is None
assert count_usage.parse_ts(None) is None and count_usage.parse_ts([1]) is None

with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp).resolve() / "home"
    c = home / ".claude"
    (c / "projects" / "p").mkdir(parents=True)
    pasted = "Why does this show <command-name>/pasted</command-name> in my log?"
    lines = [
        # real invocations (as Claude Code writes them), one with a 7-digit fraction
        {"type": "user", "timestamp": "2026-11-20T10:00:00.1234567Z", "message": {"role": "user", "content":
            "<command-message>foo</command-message>\n<command-name>/foo</command-name>\n<command-args>x</command-args>"}},
        {"type": "user", "timestamp": "2026-11-20T11:00:00.000Z", "message": {"role": "user", "content": [
            {"type": "text", "text": "<command-name>/foo</command-name>"}]}},
        # tags inside pasted text, a quote, a tool result and a skill-expansion record: not invocations
        {"type": "user", "timestamp": "2026-11-20T12:00:00Z", "message": {"role": "user", "content": pasted}},
        {"type": "user", "timestamp": "2026-11-20T12:01:00Z", "message": {"role": "user", "content":
            "> quoted:\n> <command-name>/quoted</command-name>"}},
        {"type": "user", "timestamp": "2026-11-20T12:02:00Z", "toolUseResult": "x", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t", "content": "<command-name>/fromtool</command-name>"}]}},
        {"type": "user", "timestamp": "2026-11-20T12:03:00Z", "isMeta": True, "message": {"role": "user", "content":
            "<command-name>/meta</command-name>"}},
        {"type": "assistant", "timestamp": "2026-11-20T12:04:00Z", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "<command-name>/assistant</command-name>"}]}},
        # a record with an unparsable timestamp is still read, only its time is unknown
        {"type": "user", "timestamp": "garbage", "message": {"role": "user", "content": "<command-name>/odd</command-name>"}},
    ]
    (c / "projects" / "p" / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    hist = [
        {"display": "/foo", "timestamp": ms("2026-11-20T10:00:00") + 500},   # twin of the first record
        {"display": "/foo", "timestamp": ms("2026-11-20T11:00:02")},         # twin of the second
        {"display": "/foo", "timestamp": ms("2026-11-20T15:00:00")},         # no transcript twin: counts
        {"display": "/bar", "timestamp": ms("2026-11-20T09:00:00")},         # history only: counts
        {"display": "/foo bar baz", "timestamp": ms("2026-11-20T09:00:00")},  # not a bare command
    ]
    (c / "history.jsonl").write_text("\n".join(json.dumps(x) for x in hist) + "\n", encoding="utf-8")

    rc, out, err = run(home)
    assert rc == 0, err
    got = slash(out)
    assert got == {"/foo": 3, "/bar": 1, "/odd": 1}, got  # was: /foo 5 and /pasted, /quoted counted too
    assert "PERIOD 2026-11-20 2026-11-20" in out

    # -h / --help: usage on stdout, exit 0, nothing read; unknown argument: exit 2 on stderr
    rc, out, err = run(home, "--help")
    assert rc == 0 and "Usage:" in out and "SLASH" not in out.split("Usage:")[0] and err == "", (rc, err)
    rc, out, err = run(home, "-h")
    assert rc == 0 and "PERIOD" not in out.splitlines()[0]
    rc, out, err = run(home, "whatever")
    assert rc == 2 and out == "" and "usage" in err

print("test_count_usage: OK")
