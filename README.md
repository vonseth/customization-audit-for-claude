# Customization Audit for Claude

A toolkit and working method to audit and tidy the customizations of your Claude setup: plugins, skills and MCP servers. It takes stock of what is installed, checks it for security risks, measures how much permanent context each item costs, finds overlaps and unused items, and checks for new versions. Claude does the work with you in your own session. Nothing is changed without your explicit yes, and a backup is made first.

**Unofficial: not affiliated with Anthropic.**

## Features

| Area | What it does |
|---|---|
| **Inventory** | Lists every plugin, skill, MCP server and connector: local, in the desktop app (per organization) and on claude.ai. |
| **Security review** | Checks hooks, network access, executed code and data flows of each customization, with a risk level and evidence. |
| **Token cost** | Measures how much permanent context your customizations take in every session, before and after the audit. |
| **Overlaps** | Groups customizations that do the same job and rates each one: core, complement or replaceable. |
| **Usage** | Counts how often skills, commands, agents and MCP tools were actually used in your sessions. |
| **Version check** | Looks for newer versions of what you have installed and summarizes the changes; updates only on your request. Local plugins are checked offline by `check_versions.py`. |
| **Changes since the last audit** | `diff_inventory.py` compares what is installed now with your overview page: new, gone, changed status, noticeably changed token cost. |
| **MCP cost** | `mcp_cost.py` turns the output of your own `/context` run into the measured context cost of MCP servers, shown on the token card and in each server's details. |
| **History** | `history.py` stores a snapshot of your key numbers after each audit; from two snapshots on the token card shows a timeline. |
| **Backup and restore** | `backup.py` copies what you are about to change to `~/.claude/backups/` with a manifest, and restores it after your confirmation. |
| **Guided decisions** | Claude explains one customization at a time in a fixed structure and asks before it changes anything; a backup comes first. |
| **Candidates** | Keeps a list of things you might install later, researched but not installed, until you decide. |
| **Overview page** | One self-contained HTML file (`audit-overview.html`) with status, tokens, overlaps and open items; offline, without JavaScript, also on a phone; English or German by browser language, with a DE \| EN toggle. |
| **Export and import** | Saves all audit data to one JSON file and brings it into a fresh or newer download, so you never redo the first review. |
| **Sample data** | Fictional entries to see a filled page before your first audit; removable with one command. |
| **Checks** | Scripts that rebuild the page from its data and verify it (counts, links, both languages, no external resources). |

## Download

1. Open <https://github.com/vonseth/customization-audit-for-claude/releases/latest>.
2. Download **Source code (zip)** and unzip it.

Or, if you know git: `git clone https://github.com/vonseth/customization-audit-for-claude.git`

## Quick start

1. Check that Python 3.9 or newer is installed (`python3 --version`).
2. Download and unzip the project (see above).
3. Open the folder in Claude Code (desktop app: Code tab, then choose the folder; command line: `cd` into the folder and run `claude`).
4. Tell Claude: "Start the customization audit." Claude first asks whether you want to see the sample overview or begin the first audit.
5. Open `audit-overview.html` in your browser. For your first real audit say: "Run the audit following docs/review-guide.md."

The full walkthrough, including troubleshooting, is in [docs/getting-started.md](docs/getting-started.md). Everything about using the project day to day is in the [user manual](docs/manual.md).

## Export and import

All data of your overview page, including the history of your audits, fits into one JSON file. Use it as a backup, or to move your audit into a fresh or newer download without repeating the first review.

1. **Export** in your current copy (open a terminal in the project folder):
   `python3 -I tools/import_data.py --export my-audit.json`
2. **Download** the new version and unzip it (see Download).
3. **Import** in the new copy:
   `python3 -I tools/import_data.py ../path/to/my-audit.json`
   The tool checks the file on a temporary copy first, then writes the data and rebuilds the page. If the page already holds data (for example the sample), add `--replace`.
4. **Check** the result: `python3 -I tools/check_overview.py`, then open `audit-overview.html`.

The export file describes your personal setup. Keep it private; never commit it to a public repository. You can also simply tell Claude "Export my audit data" or "Import my audit data from …".

## Platform support

| System | Support |
|---|---|
| macOS | Full and tested. |
| Windows | `~/.claude` (your user folder) is scanned. The desktop-app folder is taken from the official documentation but untested. |
| Linux | `~/.claude` only. Desktop-app data is not scanned. |

## Requirements

- Python 3.9 or newer (standard library only, nothing to install with pip).
- Claude Code, either in the Claude desktop app or as the command line tool.

## Privacy

The tools only read local files. Everything they write stays inside this project folder, with one exception: `backup.py` writes backups to `~/.claude/backups/` and, when you restore a backup and confirm, to the original paths recorded in that backup. No tool uses the network. Reports and the overview page stay on your computer; what you share is up to you. Claude itself runs in your own session as usual.

## Folder overview

| Path | Content |
|---|---|
| `audit-overview.html` | The overview page (generated parts plus your data) |
| `CLAUDE.md` | Project memory for Claude: working rules and your own decisions |
| `docs/manual.md` | User manual: reading the page, audits, decisions, candidates, export and import, FAQ |
| `docs/getting-started.md` | Set up and run the first audit |
| `docs/review-guide.md` | The audit method |
| `docs/explanation-template.md` | Fixed structure of each explanation of a customization |
| `docs/overview-structure.md` | How the page is built, data blocks, rebuild and check |
| `docs/agent-briefs.md` | Reusable briefs for sub-agents |
| `tools/` | Python scripts, see the table below |
| `assets/` | Stylesheet and fonts of the overview page |
| `examples/` | Fictional sample data |
| `reports/` | Your audit report and sub-agent reports (created during the first audit) |
| `DESIGN.md` | Design basis of the overview page |
| `CHANGELOG.md` | Versions and changes |

## Tools

All scripts are in `tools/`, use only the Python standard library and are started like `python3 -I tools/<name>.py`. Claude runs them for you; `--help` or the first lines of each file explain the options.

| Tool | Writes | What it does |
|---|---|---|
| `inventory.py` | optional TSV file | Lists all plugins, skills, agents and MCP servers with description size and hooks. |
| `check_desktop_plugin.py` | nothing | Checks whether a desktop plugin or claude.ai skill is still installed. |
| `count_usage.py` | nothing | Counts skill, command and agent calls in your session transcripts (names and numbers only). |
| `count_mcp_usage.py` | nothing | Counts calls per MCP server in your session transcripts. |
| `diff_inventory.py` | nothing | Shows what changed since the last audit: new, gone, status, token change. |
| `check_versions.py` | nothing | Offline version check of local plugins against the local marketplace copies. |
| `mcp_cost.py` | the page, with `--write` | Reads the text of your own `/context` run and measures the context cost of MCP servers. |
| `history.py` | the page | Appends a snapshot of your key numbers; `list` shows them. |
| `backup.py` | `~/.claude/backups/`; on restore the original paths | Backs up files before a change, lists backups, restores them after confirmation. |
| `build_overview.py` | the page | Rebuilds the generated parts of `audit-overview.html` from its data. |
| `check_overview.py` | nothing | Verifies the page (15 checks), including the documentation of the tools. |
| `sample_data.py` | the page | Loads, removes or reports the fictional sample data. |
| `import_data.py` | the page | Imports audit data from a JSON file or exports it. |
| `selftest.py` | temporary folder | Runs every tool against a fake home folder. |

## Support

If this saved you time and you would like to say thanks, you can [support the project](https://paypal.me/vonseth). Entirely optional.

## Author

Created by vonseth.

## License

MIT, see [LICENSE](LICENSE). The fonts in `assets/fonts/` are under their own licenses (Roboto Slab: Apache License 2.0; Roboto and JetBrains Mono: SIL Open Font License 1.1; the license files are next to the fonts).
