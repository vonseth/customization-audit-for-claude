# Explanation template

Every explanation of a skill, plugin or MCP server follows this structure, in this order and with these headings. That way all explanations look alike and can be compared. Sections marked "optional" are left out only if there is nothing to say; all others are always there.

Language: the language you use with Claude, plain, short sentences. Numbers are always backed up (measured, counted, read from a file); otherwise they are marked as an estimate.

## Structure

```markdown
## <Name> (<where: desktop app / local Claude Code plugin / own skill>; <display name in the app, if different>)

**First of all:** <optional: only for a necessary clarification, for example "This is not the same as ...",
"This is not ballast but ...", "Not harmful, but a risk">

**What it is**
<Origin: provider, source (official directory, your own marketplace, third party), who installed it.
Purpose in one or two sentences. Who it is built for.>

**The <N> skills** or **Parts**
| Skill / command | Function |
|---|---|
| ... | ... |
<Group by area if there are many. Name external data sources (connectors) and their sign-in state here.>

**How it works** <optional: only for hooks, network access, executed code, uploads>

**What this means**
1. **Context cost:** ~<tokens> per session <(measured or estimated)>, put in perspective (small / medium / large).
2. **Fit and usage:** <Does it fit what you do? Calls according to the usage count.>
3. **Overlaps:** <which other installed plugins, skills, connectors or built-in commands it overlaps with, always by name>
4. **Misfire risk:** <which everyday phrasings could trigger it unintentionally, and what then happens>
5. **Security / third party:** <optional: only if there is a finding>

**What speaks for it**
<Concrete benefit for something you do, or explicitly: "None.">

**Assessment:** <One summary sentence.> Recommendation: **Remove** / **Keep** / **Disable** /
**Borderline** (then the deciding question, with both answers). <Whether it is risk-free and reversible.
How it is removed: in the Claude app (Customize, then Plugins), or by command through Claude.>

Is the explanation clear, or do you have questions?
```

## Rules for the sections

- **The heading "What this means" stays the same** even if the result is "not ballast". In that case the point goes under "First of all" and in the assessment, not under a different heading. (In earlier versions of the method this heading read "why it is ballast"; it was neutralized because many items are not ballast.)
- **The heading "What speaks for it" is always present.**
- **"Harmful" is used only for proven harmful effect.** Otherwise say "risk" with a level (Critical / High / Medium / Low / Harmless) and evidence (file:line).
- **Keep plugin and connector apart.** A connector in your claude.ai account is independent of a plugin with the same name; removing one does not touch the other. Say so explicitly when both exist.
- **Separate proven from assumed.** Anything not checked is named as not checked.
- **One recommendation, not several.** For a borderline case, name the one question it hangs on.
- **Wait after the explanation.** No change before you have decided.

## Answers after the decision

| You say | Claude's response |
|---|---|
| "Keep it." | One sentence of confirmation; entry in the report and in the overview as "kept deliberately". |
| "Remove it." (local plugin) | Remove with `claude plugin uninstall ...`, check, short result, update report and overview. |
| "I removed it. Please check." (desktop plugin or claude.ai skill) | Check the plugin list of the desktop app and the plugin folder (`tools/check_desktop_plugin.py`). If you ask for short feedback only, Claude answers with exactly "Yes, it was removed." or "No, it was not removed." and no reasoning. |
| A question | Answer it, then ask again whether everything is clear. |

## Candidates ("not installed yet")

For something you are only considering, end the explanation with two answers, the one that fits the recommendation first: **Don't install** and **Install**.

| You say | Claude's response |
|---|---|
| "Don't install." | Ask: "Should the entry be removed from the list?" with the answers **Yes** and **No**. |
| ... "No" | The entry stays in the candidates data block; mark it as discussed and note the decision with the date. |
| ... "Yes" | The entry stays in the data block, marked as discussed, with the reason for the removal. It then appears in the archive "Removed" under "Candidates, never installed". Record the decision in `CLAUDE.md` and in the report. |
| "Install." | First the review of [review-guide.md](review-guide.md) (security, overlaps). Connectors you connect yourself in your account. After installing, move the entry from the candidates block to the matching block. |
