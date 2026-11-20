# Review guide

How an audit works, so you can repeat it every few months in the same scope and the same form. To start one, tell Claude: "Run the audit following docs/review-guide.md."

## Purpose

1. **Security:** Is any installed skill, plugin or MCP server harmful or risky (hooks, network access, executed third-party code, data leaving your computer, prompt injection)?
2. **Usefulness:** Which customizations give you no benefit for what you actually do?
3. **Ballast:** How much permanent context does each one occupy in every session (token cost), and where do they overlap?
4. **Usage:** What do you actually call, and how often?
5. **Currency:** Are there newer versions? If yes, check what changed and point it out. Updating happens only after your approval.
6. **Result:** A complete list with a recommendation per item, then a one-by-one discussion, then changes only with your consent.

## Principles (binding)

- **Read-only first.** Everything in the review phases only reads.
- **Nothing changes without your explicit consent.** First the complete list, then the one-by-one discussion, then the change.
- **Back up before every change** to `~/.claude/backups/<reason>-<date>/`, and check the result after every change.
- **Measure, don't guess.** Count or measure numbers. Permanent context in tokens is roughly the number of characters divided by 3.7. Anything that is not measured is marked as an estimate.
- **Smallest fitting model for sub-agents:** a small model for mechanical work (counting, pattern search, collecting), a mid-size model for judgement (security, overlaps, wording). Run independent agents in parallel.
- **Independent quality gate** at the end: a separate agent checks the report against the raw data.
- **One explanation per item**, in the fixed structure of [explanation-template.md](explanation-template.md), and wait for your answer.
- **Document continuously:** every decision goes into the project files right away (data block, report, `CLAUDE.md`).

## Where customizations live

| Source | Where | Removed by |
|---|---|---|
| Local Claude Code plugins | `~/.claude/plugins/installed_plugins.json`, cache in `~/.claude/plugins/cache/`, enabled state in `~/.claude/settings.json` (`enabledPlugins`) | Claude, with the `claude plugin` command |
| Your own skills and agents | `~/.claude/skills/`, `~/.claude/agents/` | Claude (after a backup) |
| Desktop-app plugins | Desktop-app data folder, in `local-agent-mode-sessions/<user>/<organization>/rpm/manifest.json` and `plugin_*` folders | **You**, in the Claude app (Customize, then Plugins) |
| claude.ai skills | Desktop-app data folder, in `local-agent-mode-sessions/skills-plugin/...` | **You**, in the Claude app (Customize, then Skills) |
| MCP servers | Plugin `.mcp.json` files, `~/.claude.json` (`mcpServers`), `claude_desktop_config.json`, desktop extensions; claude.ai connectors live in your account, not on disk | Depends on the kind (see pitfalls) |
| Built-in plugins of Claude Code | Listed in `~/.claude.json` under `pluginUsage` with the id `@builtin` | Part of the app, not yours; list them, do not count them |

The desktop-app data folder:

| System | Folder |
|---|---|
| macOS | `~/Library/Application Support/Claude` (tested) |
| Windows | `%APPDATA%\Claude`, or for the installer downloaded from Anthropic `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude` (untested; locations from <https://code.claude.com/docs/en/hipaa-setup#code-tab-data>) |
| Linux | Not scanned (no official source found) |

`~/.claude/` has the same layout on all systems. If you use several organizations or accounts in the desktop app, plugins and claude.ai skills are separate per organization.

## Phases

### Phase 1: Inventory (Claude, a few minutes)

```text
python3 -I tools/inventory.py reports/inventory.tsv
```

Lists every source with the number of skills, description characters (about the permanent context), hooks and MCP servers. Tokens per session are the description characters divided by 3.7 (an approximation). Also check: broken symlinks under `~/.claude/skills/`, `settings.json` and `settings.local.json` (permissions, hooks), marketplaces in `known_marketplaces.json`.

For MCP servers and connectors, read the sources in the table above. claude.ai connectors are not on disk: their tools and instructions are visible only to the running session, so Claude writes them down from the session. The app tool `session_connectors_status` (if available) gives the binding state of all MCP servers of the session.

### Phase 2: Read-only sub-agents in parallel

| Agent | Model | Task | Result file |
|---|---|---|---|
| **A Security (third party)** | mid | Every third-party and own package, file by file: hooks, network, data access, `eval`/base64, destructive commands, prompt injection, aggressive triggers. Risk level per package with file:line, "proven" vs "assumption" | `reports/A_security.md` |
| **B Pattern scan (official plugins)** | small | Tabulate hooks and MCP servers of all plugins, grep scripts for network, exec and secret patterns, list outdated cache versions | `reports/B_pattern_scan.md` |
| **C Usage** | small | `tools/count_usage.py` (and `tools/count_mcp_usage.py`) over all transcripts: skill calls, slash commands, agent types, MCP servers. Names and numbers only, no contents | `reports/C_usage.md` |
| **D Redundancy and usefulness** | mid | Description length per plugin (ballast), overlaps, fit to your work, recommendation Keep / Disable / Remove | `reports/D_redundancy.md` |
| **L Versions** | small | Installed vs newest version per customization (see below) | `reports/L_versions_<date>.md` |

Ready-to-use briefs are in [agent-briefs.md](agent-briefs.md). Where you also have MCP servers or newly installed desktop plugins, run the same kind of agents for them (inventory: small model; security and usefulness: mid model).

**Version check (agent L, runs in parallel).** Where versions come from:

| Kind | Installed | Newest |
|---|---|---|
| Local plugins | `installed_plugins.json` (version, `gitCommitSha`) | `plugin.json` or last commit of the source repository, read with `gh api`; **not** `plugin marketplace update` (that changes your setup) |
| Desktop-app plugins | `version` in `rpm/manifest.json` or the plugin's `plugin.json` | Managed by the app; compare with the last audit report. For third-party plugins with a GitHub source also check their newest version |
| claude.ai skills | No version number; SHA-256 of each `SKILL.md` | Managed by Anthropic; a changed hash since the last audit means a new version |
| Own skills (`~/.claude/skills/`) | Commit recorded in an origin note you keep next to the skill | Last commit of the source repository |
| MCP servers | Own servers: installed version; extensions: `manifest.json` | Own servers: newest version in the package index (read only); claude.ai connectors run at the provider and have no version |

If a newer version exists, a mid-size agent reviews only the changes (changelog, commit comparison) like agent A: new hooks, network access, scripts, permissions, changed triggers, license change. The result goes into the same partial report. The version state is the baseline for the next audit.

### Phase 3: Consolidation (Claude)

One running report, `reports/audit-report.md` (no date in the file name). Each audit adds a section "Review of <date>" with this outline:

0. Summary (table of key figures)
1. Where the customizations live
2. Security assessment
3. Usefulness and redundancy (3a keep, 3b optional, 3c disable, 3d remove, 3e tidy up, 3f broken)
4. Suggested order, and 4a changes made
5. Method and limits
6. MCP servers and connectors
7. New desktop plugins (if any)
8. New versions (table: customization, installed, new, what changes, check result, recommendation "update" / "wait" / "do not update")

Claude checks samples itself before claiming anything (does the path exist, is the binary missing).

### Phase 4: Independent quality gate (mid model, read-only)

A separate agent checks the report against the inventory, the partial reports and the original files: completeness (every active package has a recommendation), factual accuracy (at least ten samples), contradictions (especially a recommendation against the usage data), risk of the recommendations (would a removal break something in use?), over- or understatement of security levels, spelling. Verdict: passed / passed with corrections / failed, with numbered corrections. All corrections are worked in and noted in the report.

### Phase 5: One-by-one discussion

One package at a time using [explanation-template.md](explanation-template.md). Order: security findings first, then new versions (what changes, check result, recommendation), then the biggest context items, then the rest. Wait for your decision after each explanation. Customizations you deliberately kept are listed in `CLAUDE.md` and are shown again only if something changed (new version, new finding, different usage).

### Phase 6: Changes (only after approval)

- **Remove or disable a local plugin:** `claude plugin uninstall <name>@<marketplace>` or `claude plugin disable <name>@<marketplace>`; then check `installed_plugins.json` and `enabledPlugins`.
- **Desktop-app plugin or claude.ai skill:** you remove it in the app (Customize, then Plugins or Skills). Claude then checks with `python3 -I tools/check_desktop_plugin.py "<name>"`, which answers "Yes, it was removed." or "No, it was not removed."
- **Own files:** back up to `~/.claude/backups/<reason>-<date>/` first, then remove.
- **Update (only after your approval per item):** local plugin `claude plugin update <name>@<marketplace>`; desktop plugins and claude.ai skills are updated by the app; own skills are re-copied from the new commit with your own adjustments reapplied. Back up first, check the version afterwards.
- **Effect:** changes apply from the **next session**. Test plugins in a new session.

### Phase 7: Documentation

After every change:

1. Update the matching data block in `audit-overview.html` (see [overview-structure.md](overview-structure.md)).
2. Run `python3 -I tools/build_overview.py`, then `python3 -I tools/check_overview.py`.
3. Add a line to the section "Changes made" in `reports/audit-report.md`.
4. Update the decisions and status in `CLAUDE.md`.

Before you call an audit finished, run `python3 -I tools/check_overview.py --strict --inventory reports/inventory.tsv` (inventory written with `python3 -I tools/inventory.py reports/inventory.tsv`). If the inventory lists installed items that the page does not show yet, this check fails on purpose until every one of them is recorded. It reports outdated content (missing files, references to removed items, deviating values, too-long fields); update everything it reports. Texts maintained by hand (open items, group notes, documentation table, glossary) should then be read against the actual state by a mid-size agent.

## Pitfalls worth knowing

- **Never uninstall Claude Code with Homebrew's `--zap`:** it deletes `~/.claude.json` (account, connectors).
- **Plugin is not connector.** A claude.ai connector is independent of a plugin with the same name; removing one does not touch the other. "Disconnect" in the connector list is not "uninstall" of a plugin.
- **Display names differ** from plugin names in the app. Match by looking at the manifest, not only at the label.
- Plugin skills and agents carry the plugin's prefix (`<plugin>:<skill>`).
- A skill with `disable-model-invocation: true` does not appear in the model's skill list, but its agents do.
- Claude Code stores session data per folder path under `~/.claude/projects/`; moving or renaming a folder means a new session folder.
- Clicking through the app can install a plugin by accident; check the plugin list after a removal.
- `tools/inventory.py` counts hooks by text search; hits in reference texts are false alarms.
- Some folders (for example `~/Downloads` on macOS) are protected from Claude by the system; do not plan to process exports there.
- Pasted test prompts after a slash command should be plain running text (no backticks or lists); the app may reject them otherwise.
