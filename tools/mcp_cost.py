#!/usr/bin/env python3
"""Measures the context cost of MCP servers from the output of Claude Code's /context command.

IMPORTANT: the USER runs /context in Claude Code (desktop app or CLI) and pastes or saves the output.
Claude never runs /context itself, and this script never starts Claude or touches ~/.claude.

Usage:  python3 -I tools/mcp_cost.py <file | -> [--write [page]] [--date YYYY-MM-DD] [--no-resolve]
        "-" reads the text from stdin (paste, then Ctrl-D). Put the input file BEFORE --write
        (--write takes the next argument as the page). Default page: ../audit-overview.html.

Input (both formats are understood, mixed spacing, separators and languages are tolerated):
  (a) Desktop app, copied text. Summary lines "MCP tools 18.442 1,8 %", "MCP server instructions 4.136 0,4 %",
      "MCP tools (deferred) 132.468 -" and a section "MCP-Tools 150.910 253" (German label; the third column is a
      plain count) followed by one line per tool: "Linear · Create attachment (deprecated) 1.345"
      (server · tool name, tokens). Lines of other sections (memory files, agents, skills, messages, system
      tools ...) are ignored; the tool section ends at the next heading with a number. Text copied from the app
      with every column on its own line ("MCP tools" / "27.378" / "2,7 %") is joined back into such lines.
  (b) CLI text: "MCP tools: 18.4k tokens (1.8%)", "MCP tools (deferred): ..." and tool lines
      "mcp__linear__create_issue (linear): 1,345 tokens" or "mcp__server__tool: 1.3k tokens".
  Numbers: thousands separators ".", ",", apostrophe or (narrow) no-break space, or none; with the suffix k the
  last "." or "," is the decimal mark (18.4k = 18,400). Percent columns, "tokens", the dash column and leading
  symbols or box characters are ignored.

Connector IDs: in the CLI format claude.ai connectors appear with their UUID as server name
  (mcp__0a1b2c3d-...__list_issues). The desktop app keeps the connector lists in its local session files
  (<desktop data folder>/claude-code-sessions/**/*.json, objects with "uuid" and "name"). The script reads these
  files read-only (newest first, at most 200 files, files over 20 MB and unreadable files skipped, stops once all
  UUIDs are known), takes only the pairs uuid -> name from them, prints nothing else from them, and shows and
  matches the servers by that name. It prints "Connector IDs resolved from local app data: N". Unknown UUIDs stay
  as they are. --no-resolve skips this. The desktop data folder follows CUSTOMIZATION_AUDIT_HOME (tools/paths.py).

Output (stdout):
  permanent MCP cost per session = loaded MCP tools + MCP server instructions (measured),
  deferred total (loaded only on demand), and a table per server: number of tools and the total tokens of
  ALL its tools, sorted by tokens. The per-server totals cannot be split into loaded and deferred: /context
  lists every tool of a server with its own size, but not which tools are loaded.
  Exit 1 with a message if the text holds no MCP lines at all.

--write [page]  (1) sets data-tokens "mcp" = {"permanent", "deferred", "measured_on"} (--date, default today);
                (2) sets "context_tokens" (all tools of the server) on every data-mcp entry whose name matches a
                server: case-insensitive, spaces, punctuation and symbols such as "®" ignored. Failing that, the part
                before " (" is tried, but only for entries that are not removed, only if no entry matches the server
                exactly, and only if it points to one entry (a connected one wins over the rest); otherwise the
                entries are listed and left unchanged. Then builds the page; if the build fails the page is restored. Needs a measured data-tokens
                block (data-tokens is null on an empty page: replace null in the data-tokens block of the page by
                {"now": <approx. tokens from tools/inventory.py>, "measured_on": "YYYY-MM-DD"} first; the error message says how). Unmatched servers are listed;
                entries that were not measured keep their old value.
Standard library only.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
BUILDER = os.path.join(HERE, "build_overview.py")
DEFAULT_PAGE = os.path.join(HERE, "..", "audit-overview.html")

SEP = "[.,'’  ]"
NUM = r"(\d+(?:%s\d+)*)([kK])?" % SEP
DOT = "[·•∙]"
PERCENT_TAIL = re.compile(r"\s*\(?\s*\d+(?:[.,]\d+)?\s*%\s*\)?\s*$")
DASH_TAIL = re.compile(r"\s+[—–-]\s*$")
TOKENS_TAIL = re.compile(r"\s+tokens?\s*$", re.I)
DEFER_WORDS = ("defer", "zurückgestellt", "zurueckgestellt", "aufgesch", "verzöger", "nachgeladen", "bedarf",
               "demand", "lazy")

SUMMARY = re.compile(r"^(mcp[\s-]*tools?|mcp[\s-]*server[\s-]*(?:instructions?|anweisungen))\s*(?:\(([^)]*)\))?\s*:?\s+%s(?:\s+(\d+))?$"
                     % NUM, re.I)
DESKTOP_TOOL = re.compile(r"^(.+?)\s+%s\s+(.+?)\s+%s$" % (DOT, NUM))
CLI_TOOL = re.compile(r"^(mcp__.+?)\s*(?:\(([^)]*)\))?\s*:\s*%s$" % NUM, re.I)
GENERIC = re.compile(r"^[^\d].*?\s%s(?:\s+\S+)?$" % NUM)
VALUE_ONLY = re.compile(r"^(?:%s|\(?\d+(?:[.,]\d+)?\s*%%\)?|[—–-])$" % NUM)


UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
MAX_FILES = 200
MAX_BYTES = 20 * 1024 * 1024


def collect_names(node, wanted, found):
    """Walks parsed JSON (iteratively) and records name for every object with a wanted uuid."""
    stack = [node]
    while stack and len(found) < len(wanted):
        n = stack.pop()
        if isinstance(n, dict):
            u, name = n.get("uuid"), n.get("name")
            if isinstance(u, str) and isinstance(name, str) and u.lower() in wanted and name.strip():
                found.setdefault(u.lower(), name.strip())
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(v for v in n if isinstance(v, (dict, list)))


def lookup_connectors(uuids):
    """Read-only lookup uuid -> name in the desktop app's claude-code-sessions/**/*.json (newest first)."""
    wanted = {u.lower() for u in uuids}
    found = {}
    dirs, _ = paths.desktop_data_dirs()
    files = []
    for d in dirs:
        for dp, _, fn in os.walk(str(d / "claude-code-sessions")):
            for f in fn:
                if f.endswith(".json"):
                    fp = os.path.join(dp, f)
                    try:
                        files.append((os.path.getmtime(fp), fp))
                    except OSError:
                        pass
    files.sort(reverse=True)
    for _, fp in files[:MAX_FILES]:
        if len(found) >= len(wanted):
            break
        try:
            if os.path.getsize(fp) > MAX_BYTES:
                continue
            with open(fp, encoding="utf-8") as f:
                collect_names(json.load(f), wanted, found)
        except (OSError, ValueError, RecursionError, MemoryError):
            continue
    return found


def resolve_tools(tools):
    """Replaces UUID server names by connector names. Returns (new tools, number of IDs resolved or None)."""
    ids = {s for s, _, _ in tools if UUID.match(s)}
    if not ids:
        return tools, None
    names = lookup_connectors(ids)
    out = [(names.get(s.lower(), s) if s in ids else s, t, n) for s, t, n in tools]
    return out, len(names)


def to_int(digits, k):
    if k:
        t = digits.replace(",", ".")
        parts = re.split(r"[.'’  ]", t)
        t = "".join(parts[:-1]) + "." + parts[-1] if len(parts) > 1 else t
        return int(round(float(t) * 1000))
    return int(re.sub(r"\D", "", digits))


def clean(line):
    s = re.sub(r"^[^\w]+", "", line.strip())
    s = PERCENT_TAIL.sub("", s)
    s = DASH_TAIL.sub("", s)
    s = TOKENS_TAIL.sub("", s)
    return PERCENT_TAIL.sub("", s).strip()


def table_row(s):
    """Turns a Markdown table row of the CLI /context output into the plain line format parse() reads.

    "| MCP tools | 27.4k | 2.7% |" becomes "MCP tools 27.4k 2.7%"; "| mcp__srv__tool | srv | 3.1k |" becomes
    "mcp__srv__tool (srv): 3.1k"; separator rows ("|---|---|") become empty lines. Other lines stay unchanged.
    """
    if not (s.startswith("|") and s.endswith("|")):
        return s
    cells = [c.strip() for c in s.strip("|").split("|")]
    if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
        return ""
    if len(cells) >= 3 and cells[0].lower().startswith("mcp__"):
        return "%s (%s): %s" % (cells[0], cells[1], cells[2])
    return " ".join(c for c in cells if c)


def join_columns(text):
    """Joins lines that hold only a value (number, percent, dash) onto the line before (desktop app copy)."""
    out = []
    for raw in text.splitlines():
        s = table_row(raw.strip())
        if s and VALUE_ONLY.match(s) and out and out[-1]:
            out[-1] += " " + s
        else:
            out.append(s)
    return out


def parse(text):
    """Returns dict: loaded, instructions, deferred (int|None), tools: [(server, tool, tokens)], notes [str]."""
    res = {"loaded": None, "instructions": None, "deferred": None, "tools": [], "notes": []}
    in_section, header_total, header_count = False, None, None
    for raw in join_columns(text):
        s = clean(raw)
        if not s:
            continue
        m = SUMMARY.match(s)
        if m:
            label, paren, digits, k, count = m.group(1).lower(), m.group(2), m.group(3), m.group(4), m.group(5)
            value = to_int(digits, k)
            if "instr" in label or "anweis" in label:
                res["instructions"] = value
                in_section = False
            elif paren and any(w in paren.lower() for w in DEFER_WORDS):
                res["deferred"] = value
                in_section = False
            elif count is not None and not paren and not k:
                in_section, header_total, header_count = True, value, int(count)
            else:
                res["loaded"] = value
                in_section = False
            continue
        m = CLI_TOOL.match(s)
        if m:
            server = m.group(2) or (m.group(1)[5:].split("__", 1)[0])
            res["tools"].append((server.strip(), m.group(1), to_int(m.group(3), m.group(4))))
            continue
        m = DESKTOP_TOOL.match(s)
        if m and in_section:
            res["tools"].append((m.group(1).strip(), m.group(2).strip(), to_int(m.group(3), m.group(4))))
            continue
        if in_section and GENERIC.match(s) and not re.search(r"\s%s\s" % DOT, s):
            in_section = False  # next section heading
    if header_total is not None:
        got = sum(t for _, _, t in res["tools"])
        if res["tools"] and (got != header_total or len(res["tools"]) != header_count):
            res["notes"].append("section header says %d tokens in %d tools, the tool lines add up to %d tokens in %d tools"
                                % (header_total, header_count, got, len(res["tools"])))
    return res


def servers(tools):
    acc = {}
    for server, _, tokens in tools:
        n, t = acc.get(server, (0, 0))
        acc[server] = (n + 1, t + tokens)
    return sorted(((s, n, t) for s, (n, t) in acc.items()), key=lambda x: (-x[2], x[0].lower()))


def permanent(res):
    if res["loaded"] is None and res["instructions"] is None:
        return None
    return (res["loaded"] or 0) + (res["instructions"] or 0)


def report(res):
    perm = permanent(res)
    out = ["MCP context cost (measured with /context)", ""]
    if perm is None:
        out.append("Permanent MCP cost per session:  not found (no summary lines 'MCP tools' / 'MCP server instructions')")
    else:
        out.append("Permanent MCP cost per session:  %s tokens" % format(perm, ",d"))
        out.append("  loaded MCP tools:              %s" % ("%s" % format(res["loaded"], ",d") if res["loaded"] is not None else "not found"))
        out.append("  MCP server instructions:       %s" % ("%s" % format(res["instructions"], ",d") if res["instructions"] is not None else "not found"))
    out.append("Deferred (loaded only on demand): %s" % (format(res["deferred"], ",d") + " tokens" if res["deferred"] is not None else "not found"))
    rows = servers(res["tools"])
    if rows:
        out += ["", "Per server: number of tools and tokens of ALL its tools. Loaded and deferred tools cannot be",
                "told apart in this list, so the per-server totals cannot be split into loaded and deferred.", ""]
        w = max(len(r[0]) for r in rows + [("server", 0, 0)])
        out.append("%-*s  %6s  %10s" % (w, "server", "tools", "tokens"))
        for s, n, t in rows:
            out.append("%-*s  %6d  %10s" % (w, s, n, format(t, ",d")))
        out.append("%-*s  %6d  %10s" % (w, "total", sum(r[1] for r in rows), format(sum(r[2] for r in rows), ",d")))
    for n in res["notes"]:
        out.append("Note: " + n)
    return "\n".join(out)


def err(msg):
    print(msg, file=sys.stderr)


def norm(name):
    return re.sub(r"[\W_]+", "", name).lower()


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def block_pattern(name):
    return re.compile(r'(<script type="application/json" id="data-%s">)(.*?)(</script>)' % re.escape(name), re.S)


def dump(v):
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


def write_page(path, res, date):
    html = read(path)
    blocks = {}
    for n in ("tokens", "mcp"):
        m = block_pattern(n).search(html)
        if not m:
            err("ERROR: JSON block #data-%s not found in the page. Nothing was changed." % n)
            return 1
        try:
            blocks[n] = json.loads(m.group(2))
        except ValueError as e:
            err("ERROR: JSON block #data-%s is not valid JSON: %s. Nothing was changed." % (n, e))
            return 1
    if not isinstance(blocks["tokens"], dict) or not isinstance(blocks["mcp"], list):
        err("ERROR: data-tokens is empty (null): the page has no measured token total yet. Nothing was changed. "
            "Set it first: run 'python3 -I tools/inventory.py' and add up the approx. tokens per source; then in "
            "audit-overview.html replace null in <script type=\"application/json\" id=\"data-tokens\"> with "
            "{\"now\": <that total>, \"measured_on\": \"YYYY-MM-DD\"} (or import a JSON file with a \"tokens\" block "
            "using tools/import_data.py); then run this command again.")
        return 1
    perm = permanent(res)
    if perm is None:
        err("ERROR: no summary lines ('MCP tools', 'MCP server instructions') in the input, so data-tokens \"mcp\" "
              "cannot be set. Nothing was changed.")
        return 1
    blocks["tokens"]["mcp"] = {"permanent": perm, "deferred": res["deferred"] or 0, "measured_on": date}
    by = {norm(s): (s, t) for s, _, t in servers(res["tools"])}
    sums = {}
    for s, _, t in servers(res["tools"]):
        sums[norm(s)] = sums.get(norm(s), 0) + t
    used, set_n, done, base, ambiguous = set(), 0, set(), {}, []
    for row in blocks["mcp"]:
        k = norm(row.get("name", ""))
        if k in sums:
            row["context_tokens"] = sums[k]
            used.add(k)
            done.add(id(row))
            set_n += 1
    for row in blocks["mcp"]:
        name = row.get("name", "")
        if id(row) in done or row.get("status") == "removed" or " (" not in name:
            continue
        k = norm(name.split(" (")[0])
        if k in sums and k not in used:
            base.setdefault(k, []).append(row)
    for k, rows in base.items():
        if len(rows) > 1:
            rows = [r for r in rows if r.get("status") == "connected"] or rows
        if len(rows) == 1:
            rows[0]["context_tokens"] = sums[k]
            used.add(k)
            set_n += 1
        else:
            ambiguous.append("%s -> %s" % (by[k][0], ", ".join(r.get("name", "") for r in rows)))
    new = html
    for n in ("tokens", "mcp"):
        new = block_pattern(n).sub(lambda m, n=n: m.group(1) + dump(blocks[n]) + m.group(3), new, count=1)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    r = subprocess.run([sys.executable, "-I", BUILDER, path], capture_output=True, text=True)
    if r.returncode != 0:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(html)
        err("ERROR: the build failed; the page was restored.\n" + r.stdout.strip() + r.stderr.strip())
        return 1
    print("\nPage updated: data-tokens mcp = permanent %s, deferred %s, measured %s; context_tokens set on %d of %d MCP entries."
          % (format(perm, ",d"), format(res["deferred"] or 0, ",d"), date, set_n, len(blocks["mcp"])))
    if ambiguous:
        print("Not set, several entries fit one server (rename one like the server): " + "; ".join(ambiguous))
    unmatched = [s for k, (s, _) in by.items() if k not in used and k not in base]
    if unmatched:
        print("Servers without a matching data-mcp entry (name them like the server, or add the entry): " + ", ".join(unmatched))
    print("Build: " + r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "Build: done")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="MCP context cost from the output of /context (run by the user).",
                                 usage="python3 -I tools/mcp_cost.py <file | -> [--write [page]] [--date YYYY-MM-DD] [--no-resolve]")
    ap.add_argument("input")
    ap.add_argument("--write", nargs="?", const=DEFAULT_PAGE, default=None, metavar="page")
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-resolve", action="store_true", help="do not map connector IDs to names")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = ap.parse_args(argv)
    date = args.date or datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(date)
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise ValueError
    except ValueError:
        err("ERROR: --date must be a valid date like 2026-11-20.")
        return 1
    try:
        text = sys.stdin.read() if args.input == "-" else read(args.input)
    except (OSError, UnicodeDecodeError) as e:
        err("ERROR: cannot read %s: %s" % (args.input, e))
        return 1
    res = parse(text)
    if permanent(res) is None and res["deferred"] is None and not res["tools"]:
        err("No MCP lines found. Run /context in Claude Code yourself and paste its output; the text must hold lines "
              "like 'MCP tools 18.442 ...' or 'mcp__server__tool: 1,345 tokens'.")
        return 1
    if not args.no_resolve:
        res["tools"], n_resolved = resolve_tools(res["tools"])
        if n_resolved is not None:
            print("Connector IDs resolved from local app data: %d\n" % n_resolved)
    print(report(res))
    if args.write is not None:
        page = os.path.abspath(args.write)
        if not os.path.isfile(page):
            err("ERROR: %s not found." % page)
            return 1
        return write_page(page, res, date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
