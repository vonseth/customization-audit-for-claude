# Customization Audit for Claude

A toolkit and working method to audit and tidy the customizations of your Claude setup: plugins, skills and MCP servers. It takes stock of what is installed, checks it for security risks, measures how much permanent context each item costs, finds overlaps and unused items, and checks for new versions. Claude does the work with you in your own session. Nothing is changed without your explicit yes, and a backup is made first.

**Unofficial: not affiliated with Anthropic.**

## What you get

- **An overview page** (`audit-overview.html`): one self-contained HTML file with all your customizations, their status, token cost, overlaps and open items. It works offline and without JavaScript, also on a phone. It shows English or German depending on your browser language (there is a DE | EN toggle).
- **Tools** (`tools/`): small read-only Python scripts for the inventory, usage counts and checks, plus the scripts that build and check the overview page.
- **A review guide** (`docs/review-guide.md`): the audit method, step by step, so you can repeat it every few months in the same scope.
- **Sample data**: fictional entries you can load to see how a filled page looks, and remove again.

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

Already have audit data from an earlier download? Move it in with `python3 -I tools/import_data.py <file.json>` instead of repeating the first review (see "Moving existing data in" in [docs/getting-started.md](docs/getting-started.md)).

The full walkthrough, including troubleshooting, is in [docs/getting-started.md](docs/getting-started.md).

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

The tools only read local files and write nothing outside this folder. They use no network. Reports and the overview page stay on your computer; what you share is up to you. Claude itself runs in your own session as usual.

## Folder overview

| Path | Content |
|---|---|
| `audit-overview.html` | The overview page (generated parts plus your data) |
| `CLAUDE.md` | Project memory for Claude: working rules and your own decisions |
| `docs/getting-started.md` | Set up and run the first audit |
| `docs/review-guide.md` | The audit method |
| `docs/explanation-template.md` | Fixed structure of each explanation of a customization |
| `docs/overview-structure.md` | How the page is built, data blocks, rebuild and check |
| `docs/agent-briefs.md` | Reusable briefs for sub-agents |
| `tools/` | Python scripts (inventory, usage counters, build and check) |
| `assets/` | Stylesheet and fonts of the overview page |
| `examples/` | Fictional sample data |
| `reports/` | Your audit report and sub-agent reports (created during the first audit) |
| `DESIGN.md` | Design basis of the overview page |
| `CHANGELOG.md` | Versions and changes |

## Support

If this saved you time and you would like to say thanks, you can [support the project](https://paypal.me/vonseth). Entirely optional.

## Author

Created by vonseth.

## License

MIT, see [LICENSE](LICENSE). The fonts in `assets/fonts/` are under their own licenses (Roboto Slab: Apache License 2.0; Roboto and JetBrains Mono: SIL Open Font License 1.1; the license files are next to the fonts).
