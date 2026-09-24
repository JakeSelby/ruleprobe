---
bmad_id: "RP-SP003"
type: "spike"
title: "spike(readers): choose the third runtime, Cursor or Gemini CLI"
lifecycle: "completed"
provenance: "authored"
github_issue: 54
github_issue_url: "https://github.com/JakeSelby/ruleprobe/issues/54"
parent_bmad_id: "RP-E007"
parent_github_issue: 26
updated: "2026-09-24"
---

# RP-SP003 — spike(readers): choose the third runtime, Cursor or Gemini CLI

<!-- bmad-sync:begin -->
- **GitHub issue:** [#54](https://github.com/JakeSelby/ruleprobe/issues/54)
- **Primary parent:** [RP-E007](https://github.com/JakeSelby/ruleprobe/issues/26)
- **State:** completed

The issue carries the summary, discussion and acceptance evidence; this file carries the design.

This work item was authored as part of the repository's committed BMad planning system.
<!-- bmad-sync:end -->

## Question

Which third runtime does ruleprobe read in 0.2: Cursor or Gemini CLI? This is PRD open question 1, and
it blocks FR-32, FR-33 and SM-6. The choice rests on which runtime's transcripts a detector can read.

## Experiment

For Gemini CLI, the runtime the maintainer chose, from public documentation and a synthetic session,
record:

- the transcript location and format;
- whether shell commands, file writes, tool-use ids and turns are recorded;
- the licence of any format documentation used.

Then, for the chosen runtime, list each file tool that maps exactly to a canonical name (`Write` with
`file_path` and `content`, `Edit` with `file_path` and `new_string`) and each that stays native
(AD-3). A native file tool matches no canonical detector and under-counts (AD-4); that gap is stated,
not closed by a lossy mapping.

## Exit criterion

- Gemini CLI has every field above recorded, or marked not recorded.
- If a field cannot be read reliably, the gap is reported to the maintainer.
- The chosen runtime's file tools are each listed as exact or native, so the part of FR-32 that holds
  is known before RP-S019.

## Result

Runtime chosen by the maintainer on 2026-09-23: Gemini CLI. Run 2026-09-23 from public sources only.

**Verdict:** shell commands, file writes, tool-use ids and tool results are recorded and readable
reliably. One shipped detector, `cache-hygiene/compact`, cannot be served on Gemini: compaction leaves
no record a reader can tell apart. Turns are derivable only on an unverified reading (open item 3).
`write_file` and `replace` map exactly to `Write` and `Edit`; `Bash` holds on macOS and Linux, pending
open item 2. Four calls go to the maintainer below.

**Sources read.** `google-gemini/gemini-cli` main at `8e70c862f9fceb8d1667656c92dde8c13460836d`
(2026-09-23) and release `v0.60.0` at `733edcb597ce690ac2e2fe3b3b3690b60a4c8f27` (2026-09-15);
`chatRecordingService.ts` and `chatRecordingTypes.ts` are byte-identical at both. Below, `…/` stands
for `https://github.com/google-gemini/gemini-cli/blob/8e70c862f9fceb8d1667656c92dde8c13460836d/`.

**Location and format.**

- Path: `~/.gemini/tmp/<project-slug>/chats/session-<YYYY-MM-DDTHH-MM>-<sessionId[:8]>.jsonl`; a
  subagent writes `…/chats/<parentSessionId>/<sessionId>.jsonl` with `kind: "subagent"`
  (`…/packages/core/src/services/chatRecordingService.ts` L479–519). The slug is the slugified
  project root basename, and each slug directory holds a `.project_root` file with the absolute
  root, which is where `Session.repo` comes from
  (`…/packages/core/src/config/projectRegistry.ts` L308–326, `…/packages/core/src/config/storage.ts`
  L195, L230). Under the macOS seatbelt sandbox the root is
  `~/.cache/.gemini/tmp` (storage.ts L90–100; on main, not checked at a release).
- Format: append-only JSONL with four record shapes, a metadata line, message records (`id`,
  `timestamp`, `type`, `content`, optional `toolCalls`, `thoughts`, `model`), `{"$set": …}` updates
  and `{"$rewindTo": id}` (`…/packages/core/src/services/chatRecordingTypes.ts`). A changed message is
  re-appended whole, so a reader keys by `id`, last line wins, first appearance fixes the order.
- On by default with no off switch (`…/docs/cli/session-management.md` L9); sessions older than 30
  days are deleted by default (same doc, L152–185). v0.38.0 and earlier write one `session-*.json`
  object rewritten whole; v0.39.0 and later write `.jsonl`, and a resumed legacy file leaves both.
- No version field and no public schema. The docs are stale against the code (they name a project
  hash where the code uses slugs), so Gemini's own tolerant loader, `loadConversationRecord`
  (chatRecordingService.ts L133–330), is the working spec.

**Fields.**

- Shell commands: recorded, as `run_shell_command` with `command`
  (`…/packages/core/src/tools/definitions/base-declarations.ts` L56–58).
- File writes: recorded, as `write_file` and `replace` in `gemini.toolCalls[]` (base-declarations.ts
  L61–69), with identical required keys in both model-family tool sets.
- Tool-use ids: recorded, as `toolCalls[].id`, stable within the file
  (`…/packages/core/src/core/turn.ts` L474–485). Calls are written only on completion, so one cut
  off by a crash is absent (`…/packages/core/src/core/geminiChat.ts` L1689–1715).
- Tool results: recorded, in `toolCalls[].result` as a `functionResponse` part.
- Turns: not recorded, derivable. A turn starts at each `type: "user"` record that is not all
  `functionResponse` parts, since tool responses are also written as `user` records
  (`…/packages/core/src/core/geminiChat.ts` L530–575). `final` is the last `gemini` record with
  non-thought text before the next prompt.
- Model changes: recorded, `model` on every `gemini` record.
- Context compaction: not reliably recorded. It writes `{"$set":{"messages":[…]}}`, the same shape as
  truncation, tool-output masking and rollback, with no marker (`…/packages/core/src/core/client.ts`
  L1222–1263). A reader ignores `$set.messages`, or it drops pre-compaction tool calls.
- Not recorded: platform or OS, cwd beyond `.project_root`, slash commands.

**File tools against AD-3.**

- `write_file` is exact, to `Write`: `file_path` and `content` mean the proposed whole file.
- `replace` is exact, to `Edit`: `file_path`, `old_string` and `new_string` carry over; `instruction`
  and `allow_multiple` stay native keys, and `allow_multiple` is not renamed to `replace_all`.
- `read_file`, `read_many_files`, `list_directory`, `glob`, `grep_search` (alias
  `search_file_content`) and `write_todos` stay native and under-count per AD-4.
- Caveats that touch no detector key: `file_path` may be relative (`…/packages/core/src/tools/edit.ts`
  L501), and the applied change can differ from the recorded args (edit.ts L81, L587). As with Claude
  Code, the args are the proposal, not the file on disk.
- Agent: `invoke_agent` is the name candidate for `Agent` (`…/packages/core/src/tools/tool-names.ts`
  L191), but its arguments were not checked. Unverified: native until they are (open item 4). A
  subagent's own session links through `toolCalls[].agentId`.
- Shell: `run_shell_command` maps to `Bash` with `command`, exact on macOS and Linux (`bash -c`),
  pending open item 2. On Windows `command` is PowerShell
  (`…/packages/core/src/tools/definitions/dynamic-declaration-helpers.ts` L59–79), see below.
  `dir_path` has no canonical twin and stays native.

**Reader rules the evidence supports.** Each is from the evidence, not tested.

- Ignore `$rewindTo`: the rewound calls still ran, so keep them.
- Skip `user` records whose parts are all `functionResponse`, and `info`, `error` and `warning`
  records, which are UI notices.
- Prefer the `.jsonl` when a legacy `.json` of the same session sits beside it.
- `final` is the last `gemini` record with non-empty, non-thought text before the next prompt or the
  end of the file.
- A cancelled or errored call is a `toolCalls[]` entry with `status` `cancelled` or `error`; an error
  result carries `error` in place of `output` in its `functionResponse`.
- A write the user edited holds the user's version in its args with `modified_by_user: true`, and the
  model's proposal in `ai_proposed_content` (`…/packages/core/src/tools/write-file.ts` L85–90).
- A relative `file_path` resolves against `.project_root`; a missing `.project_root` leaves the repo
  unknown. Both are inferred from the path and repo findings above.
- The model can change by router or fallback, not only by the user; `model` on each `gemini` record
  captures all three.

**Licence.** Apache License 2.0 (`…/LICENSE`); the docs used are Markdown in the same repository under
the same licence. Nothing was copied into ruleprobe.

**Against the Exit criterion.** Every Experiment field is recorded or marked not recorded; the three
gaps that cannot be read reliably are reported below, with the unverified agent tool; each file
tool is listed as exact or native.
Plan in RP-S019 for the legacy `.json` format, the 30-day retention and subagent sub-directories.

### Open for the maintainer

1. **Compaction cannot be told apart from other rewrites.** Options: emit no compaction event and state
   the gap in the README note AD-10 requires; or infer one from a `$set.messages` that shrinks the
   history, which would also fire on truncation and masking. Recommendation, not a decision: emit
   none; under-counting is the AD-4 side.
2. **Windows shell sessions run PowerShell, and the platform is not recorded.** Options: map every
   `run_shell_command` to `Bash` and rely on the AD-5 parse failing closed on PowerShell; infer Windows
   from drive-letter paths and keep those commands native; or keep the shell tool native everywhere.
   A PowerShell command can tokenize as Bash (for example `$env:X=1; git commit`), so the shell parse
   cannot be relied on to refuse it. Recommendation, not a decision: map to `Bash` on macOS and Linux
   paths, keep drive-letter sessions native, and state the gap in the README note.
3. **Non-prompt `user` records may inflate `turn` (unverified).** `GeminiChat.addHistory` and
   `setHistory` also write `user` records (geminiChat.ts L1205–1230); whether a CLI-injected one
   reaches the file is not established. Options: accept the rule above and measure; or also require a
   `displayContent` or plain-text part. Recommendation, not a decision: settle it with labelled real
   sessions in RP-S019 before tightening the rule.
4. **The agent tool is unclassified.** `invoke_agent` is the likely twin of `Agent`, but its
   arguments were not checked. Options: check them and map it exactly; or keep it native, so
   `Agent` detectors under-count on Gemini. Recommendation, not a decision: keep it native until
   its arguments are checked in RP-S019.

## Decision

Decided 2026-09-23 by the maintainer: the third runtime is Gemini CLI. The spike still runs, for
Gemini CLI only, to confirm its transcript location and format and to list its file tools as exact
or native. If it finds Gemini CLI cannot be read reliably, it reports back to the maintainer rather
than switching runtime. The result unblocks RP-S019.

## Dev notes

- Binds FR-32 (a third reader, Cursor or Gemini CLI), FR-33 (labelled third-runtime sessions at or
  above the floor), AD-3 (one tool vocabulary across runtimes), AD-10 (how a reader is added).
- No dependency. Files: this story file only. Tests: none.
- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.1]
- [Source: _bmad-output/planning-artifacts/prds/prd-ruleprobe-2026-09-23/prd.md#11. Open questions]
- [Source: _bmad-output/planning-artifacts/architecture-spines/architecture-ruleprobe-2026-09-23/ARCHITECTURE-SPINE.md#AD-3]

## Dev agent record

- **Research:** by a separate agent, from public sources only: the gemini-cli repository at the two
  commits above, its source and its docs. Nothing was installed or run, and no search was used.
- **Synthetic session:** one hand-authored 20-line session with a fictional project; a throwaway
  derivation over it gave one prompt, two assistant texts with only the last `final`, and three
  tool pairs named `Bash`, `Write` and `Edit`, all in turn 1. It covers a single turn only. It is
  not committed: corpus sessions belong to RP-T003.
- **File list:** this story file only.

## Review findings

`bmad-code-review`, four layers (blind hunter, edge-case hunter, verification gap, acceptance
auditor; the verification gap found none):

- **Patched, medium:** the verdict said every field a shipped detector reads is readable, but
  `cache-hygiene/compact` reads compaction; it now names that detector as not served on Gemini, and
  says turns rest on an unverified reading.
- **Patched, medium:** reader guidance in the evidence was missing (rewind records, duplicated tool
  results, UI records, a legacy `.json` beside its `.jsonl`, `final` on non-empty text, cancelled
  calls, user-modified writes, relative paths, router model switches); it is now listed as untested
  reader rules, and RP-S019 carries a note that it is blocked on the open items.
- **Patched, low:** the `Bash` mapping is qualified to macOS and Linux pending item 2, with the case
  of PowerShell that tokenizes as Bash; the agent tool is listed as unverified and native, and
  opened as item 4; a citation is corrected; the single-turn limit of the synthetic check is stated.
- **Rejected:** "done but not asked for" on the extra fields, the reader rules and the recommendations:
  the Experiment's purpose is to unblock RP-S019, and each extra is evidence that story needs.

## Change log

- 2026-09-23: written from the planning corpus before implementation.
- 2026-09-23: runtime chosen by the maintainer: Gemini CLI; the format check still runs.
- 2026-09-23: format check run; result recorded, three gaps opened for the maintainer.
- 2026-09-23: review fixes: `cache-hygiene/compact` named as unserved, `Bash` qualified, the agent
  tool listed and opened, reader rules added, a citation corrected.
