#!/usr/bin/env python3
"""Usage counter for skills, slash commands, agents and MCP tools (read-only).

Usage:
    python3 -I tools/count_usage.py
    python3 -I tools/count_usage.py -h        # this text

What it reads (it writes nothing):
  - transcripts:   ~/.claude/projects/**/*.jsonl      (all OSes)
  - history:       ~/.claude/history.jsonl            (all OSes)
  - desktop-app sessions: claude-code-sessions and local-agent-mode-sessions in
    the Claude desktop app data folder (*.jsonl only, plugin code folders are
    skipped). macOS tested, Windows untested, not scanned on Linux.
CUSTOMIZATION_AUDIT_HOME replaces the home directory (for testing).
Missing files or folders are skipped with a note on stderr; exit code 0 (2 for a usage error).

Output (sections, tab-separated rows):
  PERIOD / TRANSCRIPT_FILES / DESKTOP_FILES / HISTORY_LINES / TOOL_USES_UNIQUE
  SKILLS           skill, calls, last use      (tool_use "Skill")
  SLASH            command, count, last use, builtin|custom
  AGENTS           subagent type, calls, last use
  MCP_SERVERS      server, calls, last use
  MCP_TOOLS        tool, calls (top 60)
  OTHER_TOOLS_TOP  tool, calls (top 25)
Tool calls are de-duplicated by their tool_use id.
Slash commands: only real invocation records count in the transcripts (a user record whose text
STARTS with <command-name> / <command-message>, once per record; the same tag inside pasted text,
a quote or a tool result does not count). The history file records the same invocations again,
so a history line is skipped when a transcript record of the same command lies within 60 seconds
(matched one to one); history lines without a match (transcript deleted, no timestamp) are counted.
"""
import collections
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

BUILTIN = {"clear", "help", "model", "config", "mcp", "init", "compact",
           "resume", "login", "logout", "exit", "doctor", "cost", "status",
           "memory", "permissions", "review", "add-dir", "bug", "vim",
           "terminal-setup", "upgrade", "release-notes", "agents", "hooks",
           "ide", "pr-comments", "todos", "bashes", "export", "rewind",
           "stats", "usage", "plugin", "plugins", "output-style", "statusline", "skills", "context",
           "theme", "fast", "effort", "privacy-settings", "sandbox", "tasks"}

CMD_TAG = re.compile(r"<command-name>\s*/?([^<\s]+)\s*</command-name>")
# a real invocation record starts with the tags (optionally <command-message> first)
CMD_START = re.compile(r"\s*(?:<command-message>[^<]*</command-message>\s*)?<command-name>")
MATCH_SECONDS = 60
CMD_LINE = re.compile(r"^/([A-Za-z][\w:.-]*)\s*$")

tool_uses = {}         # key -> (name, input, ts)
slash_transcript = []  # (cmd, ts)
slash_history = []     # (cmd, ts)
all_ts = []


def parse_ts(v):
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.datetime.fromtimestamp(v / 1000.0, datetime.timezone.utc)
        text = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], str(v).strip(), count=1)
        t = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return t
    except (ValueError, OSError, OverflowError, TypeError):
        return None


def walk(obj, ts, out):
    if isinstance(obj, dict):
        if obj.get("type") == "tool_use" and "name" in obj:
            out.append((obj.get("id"), obj.get("name"), obj.get("input") or {}, ts))
        for v in obj.values():
            walk(v, ts, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, ts, out)


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content
                         if isinstance(b, dict) and isinstance(b.get("text"), str))
    return ""


def scan_file(path):
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError as exc:
        paths.note("cannot read %s (%s), skipped" % (path, exc))
        return
    with fh:
        for idx, line in enumerate(fh):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            ts = parse_ts(rec.get("timestamp"))
            if ts:
                all_ts.append(ts)
            found = []
            walk(rec, ts, found)
            for tid, name, inp, t in found:
                key = tid or "%s:%d:%s" % (path, idx, name)
                tool_uses.setdefault(key, (name, inp, t or ts))
            # slash commands only from user-side records
            msg = rec.get("message")
            if rec.get("type") == "user" or (isinstance(msg, dict) and msg.get("role") == "user"):
                txt = text_of(msg.get("content") if isinstance(msg, dict) else rec.get("content"))
                if rec.get("isMeta") or "toolUseResult" in rec:
                    continue
                if CMD_START.match(txt):
                    m = CMD_TAG.search(txt)
                    if m:
                        slash_transcript.append(("/" + m.group(1), ts))
                else:
                    m2 = CMD_LINE.match(txt.strip())
                    if m2:
                        slash_transcript.append(("/" + m2.group(1), ts))


def merge_slash(transcript, history):
    """Transcript commands plus the history commands that have no transcript twin (see the module text)."""
    tol = datetime.timedelta(seconds=MATCH_SECONDS)
    by_cmd = {}
    for cmd, ts in transcript:
        by_cmd.setdefault(cmd, ([], []))[0].append(ts)
    out = list(transcript)
    for cmd, ts in history:
        by_cmd.setdefault(cmd, ([], []))[1].append(ts)
    for cmd, (tr, hi) in by_cmd.items():
        t = sorted(x for x in tr if x)
        i = 0
        for h in sorted(x for x in hi if x):
            while i < len(t) and t[i] < h - tol:
                i += 1
            if i < len(t) and t[i] <= h + tol:
                i += 1  # twin found in the transcript, already counted
            else:
                out.append((cmd, h))
        out.extend((cmd, None) for x in hi if not x)
    return out


def fmt(ts):
    return ts.strftime("%Y-%m-%d") if ts else "-"


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        return 0
    if args:
        print("usage: count_usage.py   (no arguments; see -h)", file=sys.stderr)
        return 2
    claude = paths.claude_dir()
    projects_glob = glob.escape(str(claude / "projects")) + "/**/*.jsonl"
    history = claude / "history.jsonl"

    # 1) transcripts
    transcripts = glob.glob(projects_glob, recursive=True)
    if not transcripts:
        paths.note("no transcripts found in %s" % (claude / "projects"))
    for f in transcripts:
        scan_file(f)

    # 2) desktop-app sessions
    data_dirs, why = paths.desktop_data_dirs()
    if why:
        paths.note(why)
    desktop_files = []
    for d in data_dirs:
        for sub in ("claude-code-sessions", "local-agent-mode-sessions"):
            for dp, _dn, fn in os.walk(str(d / sub), followlinks=True):
                parts = dp.split(os.sep)
                if "rpm" in parts or "skills-plugin" in parts:
                    continue
                desktop_files.extend(os.path.join(dp, x) for x in fn if x.endswith(".jsonl"))
    for f in desktop_files:
        scan_file(f)

    # 3) history.jsonl
    hist_total = 0
    if history.exists():
        with open(history, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                hist_total += 1
                ts = parse_ts(rec.get("timestamp"))
                if ts:
                    all_ts.append(ts)
                m = CMD_LINE.match((rec.get("display") or "").strip())
                if m:
                    slash_history.append(("/" + m.group(1), ts))
    else:
        paths.note("%s not found, skipped" % history)

    # aggregate
    skill_counts, skill_last = collections.Counter(), {}
    agent_counts, agent_last = collections.Counter(), {}
    mcp_server_counts, mcp_tool_counts, mcp_last = collections.Counter(), collections.Counter(), {}
    other = collections.Counter()
    for _key, (name, inp, ts) in tool_uses.items():
        if name == "Skill":
            s = (inp or {}).get("skill") or "(unknown)"
            skill_counts[s] += 1
            if ts and (s not in skill_last or ts > skill_last[s]):
                skill_last[s] = ts
        elif name in ("Agent", "Task"):
            s = (inp or {}).get("subagent_type") or "(no type)"
            agent_counts[s] += 1
            if ts and (s not in agent_last or ts > agent_last[s]):
                agent_last[s] = ts
        elif name.startswith("mcp__"):
            parts = name.split("__")
            server = parts[1] if len(parts) > 1 else "?"
            mcp_server_counts[server] += 1
            mcp_tool_counts[name] += 1
            if ts and (server not in mcp_last or ts > mcp_last[server]):
                mcp_last[server] = ts
        else:
            other[name] += 1

    slash_counts, slash_last = collections.Counter(), {}
    for cmd, ts in merge_slash(slash_transcript, slash_history):
        slash_counts[cmd] += 1
        if ts and (cmd not in slash_last or ts > slash_last[cmd]):
            slash_last[cmd] = ts

    print("PERIOD", fmt(min(all_ts)) if all_ts else "-", fmt(max(all_ts)) if all_ts else "-")
    print("TRANSCRIPT_FILES", len(transcripts))
    print("DESKTOP_FILES", len(desktop_files))
    print("HISTORY_LINES", hist_total)
    print("TOOL_USES_UNIQUE", len(tool_uses))
    print("SKILLS")
    for s, c in skill_counts.most_common():
        print("  %s\t%d\t%s" % (s, c, fmt(skill_last.get(s))))
    print("SLASH")
    for cmd, c in slash_counts.most_common():
        tag = "builtin" if cmd.lstrip("/") in BUILTIN else "custom"
        print("  %s\t%d\t%s\t%s" % (cmd, c, fmt(slash_last.get(cmd)), tag))
    print("SLASH_SOURCES transcript=%d history=%d" % (len(slash_transcript), len(slash_history)))
    print("AGENTS")
    for s, c in agent_counts.most_common():
        print("  %s\t%d\t%s" % (s, c, fmt(agent_last.get(s))))
    print("MCP_SERVERS")
    for s, c in mcp_server_counts.most_common():
        print("  %s\t%d\t%s" % (s, c, fmt(mcp_last.get(s))))
    print("MCP_TOOLS")
    for s, c in mcp_tool_counts.most_common(60):
        print("  %s\t%d" % (s, c))
    print("OTHER_TOOLS_TOP")
    for s, c in other.most_common(25):
        print("  %s\t%d" % (s, c))


if __name__ == "__main__":
    sys.exit(main())
