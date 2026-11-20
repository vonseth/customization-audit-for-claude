"""Tests for tools/mcp_cost.py. Run: python3 -I tests/test_mcp_cost.py
Works on a copy of the page in a temp dir; the real page is never touched."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
PY = [sys.executable, "-I"]
TMP = tempfile.TemporaryDirectory()
W = Path(TMP.name).resolve()
shutil.copytree(ROOT / "assets", W / "assets")
# an empty page, independent of whatever data the real page holds
EMPTY_PAGE = W / "empty-template.html"
shutil.copyfile(ROOT / "audit-overview.html", EMPTY_PAGE)
(W / "nothing.json").write_text("{}", encoding="utf-8")
assert subprocess.run(PY + [str(ROOT / "tools" / "import_data.py"), str(W / "nothing.json"), "--replace", str(EMPTY_PAGE)],
                      capture_output=True).returncode == 0


def run(script, *args, stdin=None, env=None):
    p = subprocess.run(PY + [str(ROOT / "tools" / script)] + [str(a) for a in args], capture_output=True, text=True,
                       input=stdin, env=env)
    return p.returncode, p.stdout + p.stderr


# (a) desktop app: German UI, "." thousands, "," decimals, percent columns, memory sections that must be ignored
DESKTOP = """Kontextnutzung
System tools 11.208 1,1 %
MCP tools 18.442 1,8 %
MCP server instructions 4.136 0,4 %
MCP tools (deferred) 132.468 —
Skills 2.100 0,2 %

Gedächtnisdateien 5.321 3
Projekt · CLAUDE.md 4.000
Global · CLAUDE.md 1.321

MCP-Tools 150.910 253
Linear · Create attachment (deprecated) 1.345
Linear · List issues 2.210
Linear · Save issue 3.001
Gamma · Generate 4.500 0,4 %
Gamma · Get themes 1.250
Gamma · Edit gamma 2.750
Gamma · Search templates 1.900
Wolfram · WolframAlpha 600
Wolfram · WolframContext 450
Wolfram · Language 1.000
Benutzerdefinierte Agents 1.200 4
Plugin · my-agent 300
"""
DESKTOP_TOTAL = 1345 + 2210 + 3001 + 4500 + 1250 + 2750 + 1900 + 600 + 450 + 1000  # 19006
# header says 253 tools / 150.910 tokens: deliberately inconsistent with the 10 lines -> a Note, not an error

# (b) CLI: k suffixes, "," thousands, box characters
CLI = """ ⛁ System tools: 11.2k tokens (1.1%)
 ⛁ MCP tools: 18.4k tokens (1.8%)
 ⛁ MCP server instructions: 4.1k tokens (0.4%)
 ⛁ MCP tools (deferred): 132.5k tokens
 ⛁ Memory files: 5,321 tokens

MCP tools · /mcp
└ mcp__linear__create_issue (linear): 1,345 tokens
└ mcp__linear__list_issues (linear): 2.2k tokens
└ mcp__gamma__generate: 1.3k tokens
└ mcp__gamma__get_themes: 900 tokens
└ mcp__plugin_demo_wolfram__ask: 450 tokens
"""


def table(out):
    rows = {}
    for m in re.finditer(r"^(\S.*?)\s{2,}(\d+)\s{2,}([\d,]+)$", out, re.M):
        rows[m.group(1)] = (int(m.group(2)), int(m.group(3).replace(",", "")))
    return rows


def write(name, text):
    p = W / name
    p.write_text(text, encoding="utf-8")
    return p


# ---- desktop format
rc, out = run("mcp_cost.py", write("desktop.txt", DESKTOP))
assert rc == 0, out
assert "Permanent MCP cost per session:  22,578 tokens" in out, out
assert "loaded MCP tools:              18,442" in out and "MCP server instructions:       4,136" in out, out
assert "Deferred (loaded only on demand): 132,468 tokens" in out, out
assert "cannot be split into loaded and deferred" in " ".join(out.split()), out
t = table(out)
assert t["Gamma"] == (4, 4500 + 1250 + 2750 + 1900), t
assert t["Linear"] == (3, 1345 + 2210 + 3001), t
assert t["Wolfram"] == (3, 2050), t
assert "Plugin" not in t and "Projekt" not in t and "Global" not in t, t   # other sections ignored
assert t["total"] == (10, DESKTOP_TOTAL), t
assert out.index("Gamma ") < out.index("Linear ") < out.index("Wolfram "), out  # sorted by tokens, descending
assert "Note: section header says 150910 tokens in 253 tools" in out, out

# ---- stdin, English separators, no percent column
rc, out = run("mcp_cost.py", "-", stdin="MCP tools 18,442\nMCP server instructions 4,136\n"
              "MCP tools (deferred) 132,468\nMCP tools 150 2\nLinear · A 100\nLinear · B 50\n")
assert rc == 0 and "22,578 tokens" in out and "132,468 tokens" in out, out
assert table(out)["Linear"] == (2, 150), out
assert "Note:" not in out, out   # header (150 tokens, 2 tools) matches the lines

# ---- CLI format
rc, out = run("mcp_cost.py", write("cli.txt", CLI))
assert rc == 0, out
assert "22,500 tokens" in out and "loaded MCP tools:              18,400" in out, out   # 18.4k + 4.1k
assert "Deferred (loaded only on demand): 132,500 tokens" in out, out
t = table(out)
assert t["linear"] == (2, 1345 + 2200), t
assert t["gamma"] == (2, 1300 + 900), t
assert t["plugin_demo_wolfram"] == (1, 450), t
assert "Memory" not in out and "System" not in out, out

# ---- connector IDs: UUID server names resolved from the desktop app's local session files (fake home)
if sys.platform in ("darwin", "win32"):
    FH = W / "fakehome"
    base = FH / ("Library/Application Support/Claude" if sys.platform == "darwin" else "AppData/Roaming/Claude")
    (base / "claude-code-sessions" / "acct" / "org").mkdir(parents=True)
    (base / "claude-code-sessions" / "acct" / "org" / "local_1.json").write_text(json.dumps(
        {"sessionId": "x", "mcp": {"connectors": [
            {"uuid": "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d", "name": "Linear", "url": "https://example.test/mcp",
             "tools": [{"name": "list_issues"}]}]}}), encoding="utf-8")
    (base / "claude-code-sessions" / "acct" / "org" / "broken.json").write_text("{not json", encoding="utf-8")
    ENV = dict(os.environ, CUSTOMIZATION_AUDIT_HOME=str(FH))
    UU = ("MCP tools: 2.0k tokens (0.2%)\nmcp__0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d__list_issues: 1,200 tokens\n"
          "mcp__0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d__save_issue: 800 tokens\n"
          "mcp__11111111-2222-3333-4444-555555555555__ping: 50 tokens\n")
    rc, out = run("mcp_cost.py", write("uuid.txt", UU), env=ENV)
    assert rc == 0, out
    assert "Connector IDs resolved from local app data: 1" in out, out
    t = table(out)
    assert t["Linear"] == (2, 2000) and "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d" not in out, out
    assert "11111111-2222-3333-4444-555555555555" in t, t   # unknown ID stays
    assert "/Users" not in out and "local_1" not in out
    rc, out = run("mcp_cost.py", W / "uuid.txt", "--no-resolve", env=ENV)
    assert rc == 0 and "resolved" not in out and "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d" in table(out), out
    # matched to a data-mcp entry "Linear (Connector)"
    pg3 = W / "page3.html"
    shutil.copyfile(EMPTY_PAGE, pg3)
    assert run("sample_data.py", "load", pg3)[0] == 0
    t3 = pg3.read_text(encoding="utf-8")
    m = re.search(r'(id="data-mcp">)(.*?)(</script>)', t3, re.S)
    rows = json.loads(m.group(2))
    rows[0]["name"] = "Linear (Connector)"
    rows[0]["status"] = "connected"
    pg3.write_text(t3[:m.start(2)] + json.dumps(rows, ensure_ascii=False).replace("</", "<\\/") + t3[m.end(2):],
                   encoding="utf-8")
    assert run("build_overview.py", pg3)[0] == 0
    rc, out = run("mcp_cost.py", W / "uuid.txt", "--write", pg3, "--date", "2026-03-01", env=ENV)
    assert rc == 0, out
    got = {r["name"]: r.get("context_tokens")
           for r in json.loads(re.search(r'id="data-mcp">(.*?)</script>', pg3.read_text(encoding="utf-8"), re.S).group(1))}
    assert got["Linear (Connector)"] == 2000, got
    assert "Servers without a matching data-mcp entry" in out and "11111111-2222" in out, out

# ---- desktop app text copied with every column on its own line (as the app copies it)
COLS = ("Kontextfenster\n662.547 / 1 Mio. (66%)\nMessages\n568.184\n56,8 %\nMCP tools\n18.442\n1,8 %\n"
        "MCP server instructions\n4.136\n0,4 %\nMCP tools (deferred)\n132.468\n\u2014\nSkills\n2.100\n0,2 %\n\n"
        "MCP-Tools\n6.710\n2\nLinear \u00b7 List issues\n2.210\nGamma \u00b7 Generate\n4.500\n\n"
        "Benutzerdefinierte Agents\n1.200\n4\nPlugin \u00b7 my-agent\n300\n")
rc, out = run("mcp_cost.py", write("cols.txt", COLS))
assert rc == 0, out
assert "Permanent MCP cost per session:  22,578 tokens" in out, out
assert "Deferred (loaded only on demand): 132,468 tokens" in out, out
t = table(out)
assert t["Linear"] == (1, 2210) and t["Gamma"] == (1, 4500) and "Plugin" not in t, t
assert t["total"] == (2, 6710) and "Note:" not in out, out

# ---- no MCP lines -> message, exit 1
rc, out = run("mcp_cost.py", write("none.txt", "System tools 11.208 1,1 %\nSkills 2.100 0,2 %\nGedächtnisdateien 5.321 3\n"
                                   "Projekt \u00b7 CLAUDE.md 4.000\n"))
assert rc == 1 and "No MCP lines found" in out and "/context" in out, out
rc, out = run("mcp_cost.py", "-", stdin="")
assert rc == 1 and "No MCP lines found" in out, out

# ---- --write on a copy of the page with sample data
page = W / "page.html"
shutil.copyfile(EMPTY_PAGE, page)
assert run("sample_data.py", "load", page)[0] == 0
# fixture for the fictional servers: names as on the page ("weather-widget-mcp" is matched via ignoring hyphens)
FICT = (
    "MCP tools 1.800 0,2 %\nMCP server instructions 620 0,1 %\nMCP tools (deferred) 12.500 \u2014\n"
    "MCP-Tools 14.920 4\n"
    "Acme CRM Connector \u00b7 Search 4.000\nAcme CRM Connector \u00b7 Create 3.000\n"
    "Project-Board-Connector \u00b7 List 5.000\nWeather Widget MCP \u00b7 Forecast 2.920\n"
    "Other Server \u00b7 Thing 100\n")
src = write("fict.txt", FICT.replace("14.920 4", "15.020 5"))
rc, out = run("mcp_cost.py", src, "--write", page, "--date", "2026-03-01")
assert rc == 0, out
assert "context_tokens set on 3 of 8 MCP entries" in out and "Other Server" in out, out
html = page.read_text(encoding="utf-8")
tok = json.loads(re.search(r'id="data-tokens">(.*?)</script>', html, re.S).group(1))
assert tok["mcp"] == {"permanent": 2420, "deferred": 12500, "measured_on": "2026-03-01"}, tok["mcp"]
assert tok["now"] == 4200   # nothing else touched
mcp = {r["name"]: r.get("context_tokens") for r in json.loads(re.search(r'id="data-mcp">(.*?)</script>', html, re.S).group(1))}
assert mcp["acme-crm-connector"] == 7000 and mcp["project-board-connector"] == 5000 and mcp["weather-widget-mcp"] == 2920, mcp
assert mcp["docs-search-ext"] == 1150 and mcp["acme-chat"] is None, mcp   # not measured: old value kept / still unset
assert ('<span lang="en">MCP servers add ~2,420 tokens per session (measured 1 March 2026); another ~12,500 load only '
        'when needed.</span><span lang="de">MCP-Server kosten zusätzlich ~2.420 Tokens je Sitzung (gemessen am 1. März '
        '2026); weitere ~12.500 werden nur bei Bedarf geladen.</span>') in html
assert "Context size (all tools)" in html and "Kontextgröße (alle Werkzeuge)" in html and "7,000 tokens" in html
rc, out = run("check_overview.py", page)
assert rc == 0 and "PASS 15  MCP cost (4 context sizes)" in out and "FAIL" not in out, out
rc, out = run("build_overview.py", page)
assert rc == 0 and "unchanged" in out, out

# ---- matching: the name before " (" counts only for one entry (a connected one wins over not signed in;
#      removed entries never get it); symbols such as "\u00ae" are ignored
pg2 = W / "page2.html"
shutil.copyfile(EMPTY_PAGE, pg2)
assert run("sample_data.py", "load", pg2)[0] == 0
t2 = pg2.read_text(encoding="utf-8")
m = re.search(r'(id="data-mcp">)(.*?)(</script>)', t2, re.S)
rows = json.loads(m.group(2))
ren = {"project-board-connector": "Board (Connector)", "acme-chat": "Board (Plugin)",
       "old-translate-connector": "Board (old)", "acme-crm-connector": "Chat (Connector)",
       "weather-widget-mcp": "Chat (Widget)"}
for r in rows:
    r["name"] = ren.get(r["name"], r["name"])
pg2.write_text(t2[:m.start(2)] + json.dumps(rows, ensure_ascii=False).replace("</", "<\\/") + t2[m.end(2):],
               encoding="utf-8")
assert run("build_overview.py", pg2)[0] == 0
src2 = write("match.txt", "MCP tools 1.000\nMCP-Tools 6.000 3\nBoard \u00b7 List 5.000\nChat \u00b7 Send 700\nDocs Search Ext\u00ae \u00b7 Find 300\n")
rc, out = run("mcp_cost.py", src2, "--write", pg2, "--date", "2026-03-01")
assert rc == 0, out
mcp2 = {r["name"]: r.get("context_tokens")
        for r in json.loads(re.search(r'id="data-mcp">(.*?)</script>', pg2.read_text(encoding="utf-8"), re.S).group(1))}
assert mcp2["Board (Connector)"] == 5000, mcp2
assert mcp2["Board (Plugin)"] is None and mcp2["Board (old)"] is None, mcp2
assert mcp2["docs-search-ext"] == 300, mcp2
assert mcp2["Chat (Connector)"] == 6120 and mcp2["Chat (Widget)"] == 410, mcp2   # two connected: left unchanged
assert "context_tokens set on 2 of 8 MCP entries" in out, out
assert "Chat -> Chat (Connector), Chat (Widget)" in out, out

# check_overview notices a wrong line
bad = page.read_text(encoding="utf-8").replace("~12.500 werden", "~12.501 werden")
(W / "bad.html").write_text(bad, encoding="utf-8")
rc, out = run("check_overview.py", W / "bad.html")
assert rc == 1 and "FAIL 15  MCP cost" in out, out

# validation of the new keys
for old, new in (('"permanent": 2420', '"permanent": -1'), ('"deferred": 12500', '"deferred": "x"'),
                 ('"context_tokens": 7000', '"context_tokens": 1.5')):
    (W / "inv.html").write_text(page.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    rc, out = run("build_overview.py", W / "inv.html")
    assert rc == 1 and "ERROR" in out, (old, out)

# empty page: no data-tokens -> clear refusal, page unchanged
empty = W / "empty.html"
shutil.copyfile(EMPTY_PAGE, empty)
before = empty.read_bytes()
rc, out = run("mcp_cost.py", write("fict2.txt", FICT), "--write", empty)
assert rc == 1 and "data-tokens is empty" in out and empty.read_bytes() == before, out
# the message names the concrete step (which block, which keys, which tool), and that step really works
for needle in ('id="data-tokens"', '"now"', "tools/inventory.py", "tools/import_data.py", "replace null"):
    assert needle in out, (needle, out)
assert "ERROR" in subprocess.run(PY + [str(ROOT / "tools" / "mcp_cost.py"), str(W / "fict2.txt"), "--write", str(empty)],
                                 capture_output=True, text=True).stderr  # errors go to stderr
t = empty.read_text(encoding="utf-8")
m = re.search(r'(id="data-tokens">)(.*?)(</script>)', t, re.S)
assert m.group(2).strip() == "null"
empty.write_text(t[:m.start(2)] + '{"now": 5000, "measured_on": "2026-11-20"}' + t[m.end(2):], encoding="utf-8")
rc, out = run("mcp_cost.py", W / "fict2.txt", "--write", empty)
assert rc == 0 and "Page updated" in out, out
rc, out = run("mcp_cost.py", "--help")
assert rc == 0 and "usage:" in out.lower()

# a page whose data-tokens has no mcp key shows no MCP line and the check passes
nomcp = W / "nomcp.html"
t = page.read_text(encoding="utf-8")
m = re.search(r'(id="data-tokens">)(.*?)(</script>)', t, re.S)
d = json.loads(m.group(2))
del d["mcp"]
nomcp.write_text(t[:m.start(2)] + json.dumps(d, ensure_ascii=False) + t[m.end(2):], encoding="utf-8")
assert run("build_overview.py", nomcp)[0] == 0
assert 'class="mcp-line"' not in nomcp.read_text(encoding="utf-8")
rc, out = run("check_overview.py", nomcp)
assert rc == 0 and "PASS 15  MCP cost" in out, out
# ---- CLI /context output as Markdown tables (current Claude Code format)
MD = ("## Context Usage\n| Category | Tokens | Percentage |\n|---|---|---|\n| MCP tools | 27.4k | 2.7% |\n"
      "| MCP server instructions | 727 | 0.1% |\n| MCP tools (deferred) | 123.5k | 12.4% |\n| Memory files | 21.6k | 2.2% |\n"
      "### MCP Tools\n| Tool | Server | Tokens |\n|------|--------|--------|\n"
      "| mcp__linear__save_issue | linear | 3.1k |\n| mcp__linear__list_issues | linear | 1.4k |\n| mcp__easel__chart | easel | 1.5k |\n"
      "### Custom Agents\n| Agent Type | Source | Tokens |\n|---|---|---|\n| some:agent | Plugin | 404 |\n")
rc, out = run("mcp_cost.py", write("md.txt", MD), "--no-resolve")
assert rc == 0, out
assert "Permanent MCP cost per session:  28,127 tokens" in out, out
assert "Deferred (loaded only on demand): 123,500 tokens" in out, out
t = table(out)
assert t["linear"] == (2, 4500) and t["easel"] == (1, 1500) and t["total"] == (3, 6000), t

print("test_mcp_cost: OK")
