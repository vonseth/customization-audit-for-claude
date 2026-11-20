#!/usr/bin/env python3
"""Inventory of all installed Claude skills and plugins (read-only).

Usage:
    python3 -I tools/inventory.py [output.tsv]

What it reads (nothing is written, except the optional output file argument):
  - local Claude Code plugins: ~/.claude/plugins/installed_plugins.json,
    enabled/disabled state from ~/.claude/settings.json ("enabledPlugins")
  - desktop-app plugins per organization (rpm/manifest.json below
    local-agent-mode-sessions) - macOS tested, Windows untested, not scanned on Linux
  - claude.ai skills per organization (skills-plugin folder) - same OS tiers
  - your own skills and agents: ~/.claude/skills, ~/.claude/agents

The environment variable CUSTOMIZATION_AUDIT_HOME replaces the home directory
(for testing with a fake home). Missing files or folders are skipped with a
short note on stderr; the exit code stays 0.

Output: tab-separated table, columns:
  source               local-plugin | desktop-plugin | claude-ai-skill | own-skill | own-agent
  organization         shortened organization id (desktop sources only)
  name                 plugin / skill / agent name
  status               active|disabled (local), installer (desktop), ok|BROKEN (own skills)
  skills               number of skills
  agents               number of agents
  commands             number of slash commands
  description_chars    characters in the descriptions (approx. permanent context)
  hooks                True if the plugin defines hooks
  mcp                  names of MCP servers the plugin ships
  path                 location on disk
Followed by a summary of description characters per source
(approx. tokens = characters / 3.7).
"""
import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402


def load_json(path):
    """Read a JSON file; on any problem print a note and return None."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        paths.note("%s not found, skipped" % path)
    except (OSError, ValueError) as exc:
        paths.note("cannot read %s (%s), skipped" % (path, exc))
    return None


def descr_len(path):
    """Length of the frontmatter description of a SKILL.md / agent / command file."""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return 0
    fm = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not fm:
        return 0
    m = re.search(r"^description:\s*(.*?)(?=^\S[^\n]*:|\Z)", fm.group(1), re.M | re.S)
    if not m:
        return 0
    d = m.group(1).strip()
    return len(re.sub(r"\s+", " ", d.lstrip("|>").strip()))


def scan(root):
    """Count skills, agents, commands, description chars, hooks and MCP servers below root."""
    esc = glob.escape(str(root))
    skills = glob.glob(esc + "/**/SKILL.md", recursive=True)
    agents = glob.glob(esc + "/agents/*.md")
    cmds = glob.glob(esc + "/commands/*.md")
    chars = sum(descr_len(p) for p in skills + agents + cmds)
    hooks = False
    for hj in glob.glob(esc + "/hooks/hooks.json"):
        try:
            hooks = bool(json.load(open(hj, encoding="utf-8")).get("hooks"))
        except (OSError, ValueError, AttributeError):
            pass
    mcp = []
    mj = os.path.join(str(root), ".mcp.json")
    if os.path.exists(mj):
        try:
            d = json.load(open(mj, encoding="utf-8"))
            mcp = list((d.get("mcpServers") or d).keys())
        except (OSError, ValueError, AttributeError):
            pass
    return len(skills), len(agents), len(cmds), chars, hooks, mcp


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    if len(sys.argv) > 1 and sys.argv[1].startswith("-"):
        print(__doc__)
        sys.exit(0)
    claude = paths.claude_dir()
    rows = []

    # 1) local Claude Code plugins
    settings = load_json(claude / "settings.json") or {}
    enabled = settings.get("enabledPlugins", {})
    installed = (load_json(claude / "plugins" / "installed_plugins.json") or {}).get("plugins", {})
    for key, entries in installed.items():
        try:
            p = entries[0]["installPath"]
        except (IndexError, KeyError, TypeError):
            paths.note("plugin %s has no installPath, skipped" % key)
            continue
        s, a, c, ch, hk, mcp = scan(p)
        rows.append(["local-plugin", "", key, "active" if enabled.get(key) else "disabled",
                     s, a, c, ch, hk, ",".join(mcp), p])

    # 2) + 3) desktop-app plugins and claude.ai skills (per organization)
    data_dirs, why = paths.desktop_data_dirs()
    if why:
        paths.note(why)
    for root in paths.sessions_roots(data_dirs):
        for man in sorted(glob.glob(glob.escape(str(root)) + "/*/*/rpm/manifest.json")):
            org = paths.short(Path(man).parts[-3])
            rpm = os.path.dirname(man)
            d = load_json(man)
            items = d if isinstance(d, list) else (d or {}).get("plugins", [])
            for it in items:
                if not isinstance(it, dict) or "id" not in it:
                    continue
                p = os.path.join(rpm, it["id"])
                name = it.get("displayName")
                pj = os.path.join(p, ".claude-plugin", "plugin.json")
                if os.path.exists(pj):
                    inner = (load_json(pj) or {}).get("name")
                    name = "%s (%s)" % (it.get("displayName"), inner)
                s, a, c, ch, hk, mcp = scan(p)
                rows.append(["desktop-plugin", org, name, it.get("installedBy", ""),
                             s, a, c, ch, hk, ",".join(mcp), p])
        for sk in sorted(glob.glob(glob.escape(str(root)) + "/skills-plugin/*/*/skills")):
            org = paths.short(Path(sk).parts[-3])
            for s in sorted(os.listdir(sk)):
                p = os.path.join(sk, s, "SKILL.md")
                if os.path.exists(p):
                    rows.append(["claude-ai-skill", org, s, "", 1, 0, 0, descr_len(p), False, "",
                                 os.path.dirname(p)])

    # 4) own skills and agents
    for p in sorted(glob.glob(glob.escape(str(claude)) + "/skills/*")):
        real = os.path.realpath(p)
        ok = os.path.exists(os.path.join(real, "SKILL.md"))
        rows.append(["own-skill", "", os.path.basename(p), "ok" if ok else "BROKEN (target missing)",
                     int(ok), 0, 0, descr_len(os.path.join(real, "SKILL.md")), False, "", real])
    for p in sorted(glob.glob(glob.escape(str(claude)) + "/agents/*.md")):
        rows.append(["own-agent", "", os.path.basename(p), "", 0, 1, 0, descr_len(p), False, "", p])

    head = ["source", "organization", "name", "status", "skills", "agents", "commands",
            "description_chars", "hooks", "mcp", "path"]
    out = "\n".join("\t".join(map(str, r)) for r in [head] + rows)
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], "w", encoding="utf-8") as fh:
                fh.write(out + "\n")
        except OSError as exc:
            paths.note("cannot write %s (%s)" % (sys.argv[1], exc))
    print(out)
    total = {}
    for r in rows:
        total[r[0]] = total.get(r[0], 0) + int(r[7])
    print("\nDescription characters per source (approx. tokens = characters / 3.7):")
    for k, v in total.items():
        print("  %s: %d characters = approx. %d tokens" % (k, v, round(v / 3.7)))


if __name__ == "__main__":
    main()
