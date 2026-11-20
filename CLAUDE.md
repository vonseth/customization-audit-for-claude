# CLAUDE.md - Customization Audit for Claude

Project memory for Claude in this copy of the project. Anyone reading this file can continue the work without the earlier chat.

Answer in the language the user writes in.

## What this project is

An unofficial tool (not affiliated with Anthropic) to audit and tidy Claude customizations: plugins, skills and MCP servers. The method is in `docs/review-guide.md`; the overview page is `audit-overview.html`, built from JSON data blocks by `tools/build_overview.py` and checked by `tools/check_overview.py` (structure: `docs/overview-structure.md`). All tools are read-only except the build script, `tools/sample_data.py`, `tools/import_data.py`, `tools/history.py` and `tools/mcp_cost.py --write` (these write only the overview page) and `tools/backup.py` (writes to `~/.claude/backups/`, and on a confirmed restore to the original paths).

`tools/import_data.py` moves audit data between pages: `python3 -I tools/import_data.py <file.json> [--replace]` imports a JSON file in the shape of `examples/sample-data.json`, `python3 -I tools/import_data.py --export <file.json>` writes the current page data out (backup, or moving to a newer download). Never put such a file with personal data into a public repository.

## FIRST RUN

If `audit-overview.html` holds no data (all data blocks empty) and no sample, ask the user **once**: "Do you want to see the sample overview first (fictional data, `python3 -I tools/sample_data.py load`), or start your first audit right away?"

- Sample first: run `python3 -I tools/sample_data.py load`, tell the user to open `audit-overview.html`, and explain what they see. When they are done, run `python3 -I tools/sample_data.py remove`.
- Remind the user to **remove the sample before the real audit** (`python3 -I tools/sample_data.py status` shows whether it is loaded).
- First audit: follow `docs/review-guide.md`.

## Tools

All in `tools/`, started as `python3 -I tools/<name>.py`; the first lines of each file explain the options.

| Tool | Use |
|---|---|
| `inventory.py` | Inventory of everything installed (`reports/inventory.tsv`) |
| `check_desktop_plugin.py` | Is a desktop plugin or claude.ai skill still installed? |
| `count_usage.py`, `count_mcp_usage.py` | Usage counts from the transcripts (names and numbers only) |
| `diff_inventory.py` | What changed since the last audit; run first in every audit |
| `check_versions.py` | Offline version check of local plugins; agent L only for the rest and for "unknown" |
| `mcp_cost.py` | MCP context cost from the user's pasted `/context` output |
| `history.py` | `snapshot` after an audit, `list` |
| `backup.py` | `create` before a change, `list`, `show`, `restore` |
| `build_overview.py`, `check_overview.py` | Build and verify the page |
| `sample_data.py`, `import_data.py` | Sample data; import and export of audit data |
| `selftest.py` | Self-test of all tools (`paths.py` is internal) |

## Working rules

1. **No change without explicit consent.** List first, explain, ask, then act.
2. **Explanations follow `docs/explanation-template.md`,** one package at a time, then wait for the answer.
3. **Sub-agents with the smallest fitting model** (small for mechanical work, mid-size for judgement), in parallel where independent; briefs in `docs/agent-briefs.md`. At the end an **independent quality gate** by a separate agent.
4. **After each decision** update the matching row in the data block of `audit-overview.html`, then run `python3 -I tools/build_overview.py` and `python3 -I tools/check_overview.py`. Update the "As of" date and the measured token values by hand.
5. **Log each change** as a line in the section "Changes made" of `reports/audit-report.md`.
6. **Back up before every change:** run `python3 -I tools/backup.py create <reason> <paths>` first (goes to `~/.claude/backups/<reason>-<date>/` with a manifest); check the result after every change. `backup.py restore` asks the user for a confirmation: never pass `--yes` and never answer that question yourself. Old backup folders without a manifest are restored by hand.
7. **Measure, don't guess.** Count or measure numbers (tokens are about characters divided by 3.7); mark estimates as estimates.
8. **Keep the overview current.** Before an audit counts as finished, run `python3 -I tools/check_overview.py --strict --inventory reports/inventory.tsv` (create the file first with `python3 -I tools/inventory.py reports/inventory.tsv`) and fix everything it reports.
9. **Desktop-app plugins and claude.ai skills** are removed by the user in the app; local plugins by Claude with the `claude plugin` command. Never uninstall Claude Code with Homebrew `--zap`.
10. **Start an audit with `python3 -I tools/diff_inventory.py`** (changes since the last audit). Check local plugin versions with `python3 -I tools/check_versions.py` (offline); give the version agent only desktop plugins, claude.ai skills and the plugins reported as "unknown".
11. **MCP cost only from the user's pasted `/context` output.** Never run `/context` yourself. Ask the user to run it in a new Claude Code session, expand "MCP tools" and paste the text or a file, then run `python3 -I tools/mcp_cost.py <file> --write` (file before `--write`). Permanent = loaded MCP tools + server instructions; deferred only on demand; per-server totals cannot be split.
12. **After an audit** (numbers final, check passed) run `python3 -I tools/history.py snapshot`.
13. **Write decisions down immediately** in this file, the report or the overview, not only in the chat.

## Decisions (kept deliberately)

Only present these again if something changed (new version, new finding, different usage).

| Customization | Decision | Date |
|---|---|---|
| | | |

## Status and open items

Status: not started.

Open:
-
