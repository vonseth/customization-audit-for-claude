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

Keep the folder: your overview page, reports and decisions will live in it.

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

## 5. Open the overview page

Open `audit-overview.html` in your browser (double-click the file). The key figures are at the top; click an entry in the list to see its details and the recommendation. The page shows English or German depending on your browser language; the DE | EN toggle in the top bar switches it.

## 6. Run your first real audit

Tell Claude:

```text
Run the audit following docs/review-guide.md.
```

## 7. What happens next

- Claude takes an inventory of what is installed and runs read-only checks (security, usage, overlaps, new versions), often with several helper agents in parallel.
- It consolidates the findings in a report (`reports/audit-report.md`) and fills the overview page.
- Then it goes through the customizations **one at a time**, in a fixed structure (see [explanation-template.md](explanation-template.md)), and waits for your decision after each one.
- **Nothing is changed without your OK.** Before any change Claude makes a backup in `~/.claude/backups/<reason>-<date>/`.
- Some things you do yourself in the Claude app (removing desktop-app plugins and claude.ai skills); Claude tells you where to click and then checks that it worked.
- Changes take effect from the next session.

## 8. Update the overview afterwards

After each decision Claude updates the matching data block in `audit-overview.html` and runs:

```text
python3 -I tools/build_overview.py
python3 -I tools/check_overview.py
```

You can run both yourself at any time. Details: [overview-structure.md](overview-structure.md).

## Troubleshooting

| Problem | What to do |
|---|---|
| `python3: command not found` | Install Python (step 1). On Windows try `py -3` instead of `python3`. |
| What is `-I`? | It starts Python in isolated mode, so no stray files in the folder can be loaded by accident. Keep it. |
| Desktop-app plugins or claude.ai skills are not listed on Linux | Expected: on Linux only `~/.claude` is scanned, the desktop-app data is not. |
| Desktop-app data not found on Windows | The folder location is taken from the official documentation but untested. Tell Claude what you see; the tools skip missing folders with a note and continue. |
| The page shows English but you want German (or the other way round) | It follows your browser language. Use the DE \| EN toggle at the top right of the page. |
| The page looks unstyled or is missing a font | Run `python3 -I tools/build_overview.py`; it re-embeds `assets/style.css` and the fonts. A missing font file is reported as a warning. |
| `check_overview.py` reports a warning about a missing file | Files such as `reports/audit-report.md` appear during your first audit. With `--strict` such warnings become failures. |

Next: [review-guide.md](review-guide.md).
