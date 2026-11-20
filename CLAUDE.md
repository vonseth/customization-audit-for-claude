# CLAUDE.md - Customization Audit for Claude

Project memory for Claude in this copy of the project. Anyone reading this file can continue the work without the earlier chat.

Answer in the language the user writes in.

## What this project is

An unofficial tool (not affiliated with Anthropic) to audit and tidy Claude customizations: plugins, skills and MCP servers. The method is in `docs/review-guide.md`; the overview page is `audit-overview.html`, built from JSON data blocks by `tools/build_overview.py` and checked by `tools/check_overview.py` (structure: `docs/overview-structure.md`). All tools are read-only except the build script, `tools/sample_data.py` and `tools/import_data.py`.

`tools/import_data.py` moves audit data between pages: `python3 -I tools/import_data.py <file.json> [--replace]` imports a JSON file in the shape of `examples/sample-data.json`, `python3 -I tools/import_data.py --export <file.json>` writes the current page data out (backup, or moving to a newer download). Never put such a file with personal data into a public repository.

## FIRST RUN

If `audit-overview.html` holds no data (all data blocks empty) and no sample, ask the user **once**: "Do you want to see the sample overview first (fictional data, `python3 -I tools/sample_data.py load`), or start your first audit right away?"

- Sample first: run `python3 -I tools/sample_data.py load`, tell the user to open `audit-overview.html`, and explain what they see. When they are done, run `python3 -I tools/sample_data.py remove`.
- Remind the user to **remove the sample before the real audit** (`python3 -I tools/sample_data.py status` shows whether it is loaded).
- First audit: follow `docs/review-guide.md`.

## Working rules

1. **No change without explicit consent.** List first, explain, ask, then act.
2. **Explanations follow `docs/explanation-template.md`,** one package at a time, then wait for the answer.
3. **Sub-agents with the smallest fitting model** (small for mechanical work, mid-size for judgement), in parallel where independent; briefs in `docs/agent-briefs.md`. At the end an **independent quality gate** by a separate agent.
4. **After each decision** update the matching row in the data block of `audit-overview.html`, then run `python3 -I tools/build_overview.py` and `python3 -I tools/check_overview.py`. Update the "As of" date and the measured token values by hand.
5. **Log each change** as a line in the section "Changes made" of `reports/audit-report.md`.
6. **Back up before every change** to `~/.claude/backups/<reason>-<date>/`; check the result after every change.
7. **Measure, don't guess.** Count or measure numbers (tokens are about characters divided by 3.7); mark estimates as estimates.
8. **Keep the overview current.** Before an audit counts as finished, run `python3 -I tools/check_overview.py --strict --inventory reports/inventory.tsv` (create the file first with `python3 -I tools/inventory.py reports/inventory.tsv`) and fix everything it reports.
9. **Desktop-app plugins and claude.ai skills** are removed by the user in the app; local plugins by Claude with the `claude plugin` command. Never uninstall Claude Code with Homebrew `--zap`.
10. **Write decisions down immediately** in this file, the report or the overview, not only in the chat.

## Decisions (kept deliberately)

Only present these again if something changed (new version, new finding, different usage).

| Customization | Decision | Date |
|---|---|---|
| | | |

## Status and open items

Status: not started.

Open:
-
