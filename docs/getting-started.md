# Getting started

This walkthrough assumes you start from zero. You do not need to write code. Claude does the technical work; you decide.

## 1. Check that Python is installed

Open a terminal (macOS: Terminal app; Windows: PowerShell; Linux: your terminal) and run:

```text
python3 --version
```

You need version 3.9 or newer. On Windows the command may be `py -3 --version`.

If Python is missing:

- **macOS:** install from <https://www.python.org/downloads/> or with Homebrew (`brew install python`).
- **Windows:** install from <https://www.python.org/downloads/>; tick "Add python.exe to PATH" in the installer, or use the `py -3` launcher.
- **Linux:** use your package manager, for example `sudo apt install python3`.

## 2. Download the project

Either:

1. Open <https://github.com/vonseth/customization-audit-for-claude/releases/latest>.
2. Download **Source code (zip)**.
3. Unzip it somewhere you will find again (for example your Documents folder).

Or with git: `git clone https://github.com/vonseth/customization-audit-for-claude.git`

Keep the folder: your overview page, reports and decisions will live in it. The file `VERSION` shows which version you have. From 1.4.0 on, use `python3 -I tools/update.py check` and `apply` for later updates (see [Updating in the manual](manual.md#updating-to-a-new-version)); you do not need to download again by hand.

## 3. Open the folder in Claude Code

- **Desktop app:** open the Code tab and choose the project folder.
- **Command line:** `cd` into the folder and run `claude`.

## 4. Say hello

Type, for example:

```text
Start the customization audit.
```

Claude reads `CLAUDE.md`, sees that the overview is still empty and asks you once: do you want to see the sample overview first, or start the first audit?

### About the sample data

The sample data is fictional. It fills every block of the overview page so you can see what a finished audit looks like. Claude loads it with:

```text
python3 -I tools/sample_data.py load
```

and removes it again with:

```text
python3 -I tools/sample_data.py remove
```

`python3 -I tools/sample_data.py status` tells you whether sample data is currently on the page. While it is loaded, the page shows a notice at the top. **Remove the sample before your real audit**, otherwise fictional entries mix with yours.

### Moving existing data in

If you already did an audit in an earlier copy of this project, you do not have to redo it. If that copy has `tools/update.py` (version 1.4.0 or newer), simply update it there. Copies of version 1.3.0 or older do not contain `update.py` yet: for the first move to 1.4.0 use the manual path below once; from 1.4.0 on, `update.py` does this for you. Export the data from the old copy and import it into the new one:

```text
python3 -I tools/import_data.py --export my-audit.json     # in the OLD copy: writes the data of audit-overview.html
python3 -I tools/import_data.py ../my-audit.json           # in the NEW copy: validates, writes the blocks, builds the page
```

The import checks the file against the schema first (in a temporary copy) and changes nothing if anything is wrong. It refuses to run while the page holds data, sample or your own; add `--replace` to overwrite it (remove the sample this way). The file is never modified, so it doubles as a backup. The file contains your own data: keep it out of any public repository. Afterwards run `python3 -I tools/check_overview.py`. Your reports in `reports/`, `CLAUDE.md` decisions and `assets/` are not part of the file; copy them by hand if you want them in the new copy.

## 5. Open the overview page

Open `audit-overview.html` in your browser (double-click the file). The key figures are at the top; click an entry in the list to see its details and the recommendation. The page shows English or German depending on your browser language; the DE | EN toggle in the top bar switches it.

## 6. Run your first real audit

Tell Claude:

```text
Run the audit following docs/review-guide.md.
```

## 7. What happens next

- Claude first shows what changed since the last audit (`python3 -I tools/diff_inventory.py`; on your first audit everything counts as new), takes an inventory of what is installed and runs read-only checks (security, usage, overlaps, new versions), often with several helper agents in parallel. Versions of local plugins are checked offline with `tools/check_versions.py`.
- If you want to know what your MCP servers cost, Claude asks you to run `/context` in a new Claude Code session, expand "MCP tools" and paste the text; Claude then measures it with `tools/mcp_cost.py`. Claude never runs `/context` itself.
- It consolidates the findings in a report (`reports/audit-report.md`) and fills the overview page.
- Then it goes through the customizations **one at a time**, in a fixed structure (see [explanation-template.md](explanation-template.md)), and waits for your decision after each one.
- **Nothing is changed without your OK.** Before any change Claude makes a backup with `tools/backup.py create` in `~/.claude/backups/<reason>-<date>/`. A restore (`backup.py restore`) asks for your confirmation first.
- Some things you do yourself in the Claude app (removing desktop-app plugins and claude.ai skills); Claude tells you where to click and then checks that it worked.
- Changes take effect from the next session.

## 8. Update the overview afterwards

After each decision Claude updates the matching data block in `audit-overview.html` and runs:

```text
python3 -I tools/build_overview.py
python3 -I tools/check_overview.py
```

You can run both yourself at any time. Details: [overview-structure.md](overview-structure.md).

When the audit is finished, Claude stores a snapshot of the key numbers for the history with `python3 -I tools/history.py snapshot`. From the second snapshot on, the token card shows a timeline.

## Troubleshooting

| Problem | What to do |
|---|---|
| `python3: command not found` | Install Python (step 1). On Windows try `py -3` instead of `python3`. |
| What is `-I`? | It starts Python in isolated mode, so no stray files in the folder can be loaded by accident. Keep it. |
| Desktop-app plugins or claude.ai skills are not listed on Linux | Expected: on Linux only `~/.claude` is scanned, the desktop-app data is not. |
| Desktop-app data not found on Windows | The folder location is taken from the official documentation but untested. Tell Claude what you see; the tools skip missing folders with a note and continue. |
| The page shows English but you want German (or the other way round) | It follows your browser language. Use the DE \| EN toggle at the top right of the page. |
| The page looks unstyled or is missing a font | Run `python3 -I tools/build_overview.py`; it re-embeds `assets/style.css` and the fonts. A missing font file is reported as a warning. |
| `check_versions.py` says "unknown" for a plugin | Expected for plugins from external sources or without version information in the local marketplace copy; the reason is printed. The tool works offline and never fetches anything. |
| `check_overview.py` reports a warning about a missing file | A file listed in the Documentation section of the page is missing, for example after you deleted or renamed one. Restore it or update the table; with `--strict` such warnings become failures. |

Next: [review-guide.md](review-guide.md).
