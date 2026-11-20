#!/usr/bin/env python3
"""Count MCP tool calls per server from session transcripts (read-only).

Usage:
    python3 -I tools/count_mcp_usage.py [current_session_id]

What it reads (it writes nothing): ~/.claude/projects/**/*.jsonl (same layout
on all OSes). CUSTOMIZATION_AUDIT_HOME replaces the home directory (for
testing). If no transcripts exist, a note goes to stderr and the exit code is 0.

The optional argument is the id of the running session; its share is reported
separately (column in_current), so the audit session itself does not distort
the numbers.

Output: header lines (FILES, PERIOD, MCP_CALLS_UNIQUE), then a tab-separated
table, one row per server, sorted by calls:
  server, calls, last_30_days, sessions, in_current, first_call, last_call, top_tools
Calls are de-duplicated by their tool_use id; only assistant tool_use blocks
whose name starts with "mcp__" count.
"""
import collections
import datetime
import glob
import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def ts_of(v):
    try:
        t = datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def fmt(t):
    return t.strftime("%Y-%m-%d") if t else "-"


def main():
    current = sys.argv[1] if len(sys.argv) > 1 else None
    cut30 = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    base = paths.claude_dir() / "projects"
    files = sorted(glob.glob(glob.escape(str(base)) + "/**/*.jsonl", recursive=True))
    if not files:
        paths.note("no transcripts found in %s" % base)
    seen = {}
    all_ts = []
    for f in files:
        m = UUID.findall(f)
        sess = m[-1] if m else os.path.basename(f)
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError as exc:
            paths.note("cannot read %s (%s), skipped" % (f, exc))
            continue
        with fh:
            for i, line in enumerate(fh):
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                t = ts_of(rec.get("timestamp"))
                if t:
                    all_ts.append(t)
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message")
                content = msg.get("content") if isinstance(msg, dict) else None
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    name = b.get("name") or ""
                    if not name.startswith("mcp__"):
                        continue
                    key = b.get("id") or "%s:%d:%s" % (f, i, name)
                    if key not in seen:
                        seen[key] = (name, t, sess, f)
    agg = collections.defaultdict(lambda: {"n": 0, "n30": 0, "sess": set(), "cur": 0,
                                           "first": None, "last": None,
                                           "tools": collections.Counter()})
    for _key, (name, t, sess, f) in seen.items():
        parts = name.split("__")
        a = agg[parts[1] if len(parts) > 1 else "?"]
        a["n"] += 1
        a["tools"][name] += 1
        a["sess"].add(sess)
        if current and current in f:
            a["cur"] += 1
        if t:
            if t >= cut30:
                a["n30"] += 1
            if a["first"] is None or t < a["first"]:
                a["first"] = t
            if a["last"] is None or t > a["last"]:
                a["last"] = t
    print("FILES", len(files))
    print("PERIOD", fmt(min(all_ts)) if all_ts else "-", fmt(max(all_ts)) if all_ts else "-")
    print("MCP_CALLS_UNIQUE", len(seen))
    print("\t".join(["server", "calls", "last_30_days", "sessions", "in_current",
                     "first_call", "last_call", "top_tools"]))
    for s, a in sorted(agg.items(), key=lambda kv: -kv[1]["n"]):
        top = "; ".join("%s %d" % (n.split("__", 2)[-1], c) for n, c in a["tools"].most_common(3))
        print("\t".join(map(str, [s, a["n"], a["n30"], len(a["sess"]), a["cur"],
                                  fmt(a["first"]), fmt(a["last"]), top])))


if __name__ == "__main__":
    main()
