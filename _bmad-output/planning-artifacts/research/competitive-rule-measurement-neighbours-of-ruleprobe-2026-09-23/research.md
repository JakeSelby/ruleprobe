---
title: 'competitive research: rule-measurement neighbours of ruleprobe'
type: 'competitive'
topic: 'rule-measurement neighbours of ruleprobe'
decision: 'How ruleprobe positions against the projects that now measure rule compliance from coding-agent transcripts, and what its 0.2 must contain to hold a defensible position.'
source: 'process: one imported web-field report (imports/web-field-2026-09-23.md, produced 2026-09-23 by a web-research subagent, 19 searches and about 9 fetches), spot-checked with 8 page fetches and 3 searches on 2026-09-23'
status: complete
preset: 'standard'
validation: 'normal'
secondary_dimension: 'academic-lit'
claims_verified: 7
claims_unverified: 21
claims_total: 28
created: '2026-09-23'
updated: '2026-09-23'
---

# competitive research: rule-measurement neighbours of ruleprobe

**Decision this research serves:** how ruleprobe positions against the projects that now measure rule compliance from coding-agent transcripts, and what its 0.2 must contain to hold a defensible position.

## Executive summary

**Verdict: ruleprobe cannot claim to be the first tool that measures rule compliance from transcripts; its defensible position is cross-runtime, deterministic, evidence-quoting measurement, and its 0.2 must ship a Codex rollout reader to own the one lane nobody was found in.**

1. **The niche is populated, but only on Claude Code.** claude-md-doctor (MIT, standard-library Python, local) backtests each CLAUDE.md or AGENTS.md rule against Claude Code transcripts by replaying model-authored matchers deterministically [1]. RuleReceipt does the same job in TypeScript with deterministic checks and an opt-in LLM grader, under a source-available licence that bars competing commercial offerings [2]. Neither reads anything but Claude Code transcripts [1][2].
2. **No one was found measuring rule compliance from Codex rollouts.** This is absence of evidence from one import and one targeted search, so it is thin [9]. The nearest first-party move is OpenAI's Codex Code Review applying AGENTS.md rules to pull-request diffs, which judges the output, not the session [31].
3. **The literature backs deterministic-first measurement.** Two independent preprints recommend deterministic verification with any LLM judge demoted to advisor [26][27], and the largest controlled study found file structure has no detectable effect while compliance falls with each additional function the agent writes [22].

**Biggest caveat:** absorption risk is real but unshipped. Langfuse and LangSmith already ingest both Claude Code and Codex transcripts [17][19], and Anthropic's /insights already reads local transcripts to suggest rules [15]. None of them was found scoring existing rules, but that is an absence claim that ages in three months.

## Offer and feature teardown

- **claude-md-doctor** reads CLAUDE.md or AGENTS.md plus Claude Code session transcripts and reports a per-rule backtest of followed, ignored and never-used rules [1]. Its backtest script replays model-authored regex matchers deterministically over sessions, and matcher results are sample-verified before they count [1]. Its README names no transcript format other than Claude Code [1]. Confidence high.
- **RuleReceipt** reads Claude Code transcripts with the rule file, checks git commands and file operations deterministically, and reports judgment rules as UNCLEAR unless the opt-in `--llm` flag grades them with the user's own key [2]. Its plain check makes no network calls [2]. Confidence high. Its author also parsed 559 public CLAUDE.md files and titled the finding as most of their content not being rules [3] (low, title only).
- **Prospective LLM-scored testers.** Marketplace Claude Code skills generate test scenarios from CLAUDE.md and score them with an LLM, which is test generation rather than transcript replay [4] (low, search snippet).
- **Static rule tooling does not measure behaviour.** agnix lints CLAUDE.md, AGENTS.md, SKILL.md and other agents' formats with 456 claimed rules and does not read transcripts [11] (high). ctxlint lints context files statically and its session mode only looks for loops and repeated commands [10] (medium, unverified). rulesync converts rule files across agents [12] (medium, unverified).
- **Transcript analyzers measure spend, not rules.** ccusage reads Claude Code, Codex and many other agents' logs for tokens and cost [6], and analyzers and browsers such as cc-analyzer, Agent Sessions and codex-usage-analyzer report tools, tokens or history with no rule-compliance output [7][8][9] (medium, unverified).

## Pricing and packaging

- No neighbour was found charging. claude-md-doctor is MIT and local with no dependencies claimed [1]; agnix is MIT OR Apache-2.0 [11]; RuleReceipt is source-available, not open source, and bars competing commercial offerings [2]. Confidence high for all three.
- Packaging therefore differentiates only against RuleReceipt; against claude-md-doctor, licence and install footprint are parity.

## Positioning and messaging

- claude-md-doctor frames itself against /insights and rule-writing helpers: those answer what you should write, it answers whether what you already wrote is doing anything [1] (medium; a competitor's framing of a first party).
- A secondary post claims CLAUDE.md rules reach about 0% compliance for anything the agent would not do anyway [5] (low, unverified). This is the market story every neighbour sells into.

## Trajectory

- Thin. claude-md-doctor showed 38 stars and RuleReceipt 2 stars with about 240 commits on 2026-09-23 [1][2] (medium, single observation). agnix, a static linter, showed 421 stars [11]. No funding, hiring or release-cadence signal was gathered. The niche is occupied but not won.

## Absorption risk from platforms

- Anthropic's OpenTelemetry export carries usage metrics and activity events and no instruction-adherence signal [13] (high, primary docs). Its analytics report sessions, lines, commits and accept rates with no compliance measure [14] (medium, unverified).
- /insights reads the last 30 days of local transcripts and produces a report with friction analysis and suggested CLAUDE.md additions [15][16] (medium; secondary blogs only, as the Anthropic commands page fetched this run had no /insights entry). No source shows it scoring existing rules [15] (low, absence).
- Langfuse's Claude Code integration reads transcript JSONL on every Stop hook and points to Codex, Copilot and Cursor coverage, with no rule evaluator shipped [17] (high). The import reports a Langfuse page saying loaded CLAUDE.md and skills context is not readable by its hooks [18]; the page fetched this run did not carry that sentence, so it stays unverified.
- LangSmith traces Claude Code, Codex, Cursor and others with no instruction-compliance metric found [19], and generic eval vendors were found offering custom scorers but no packaged instruction-adherence evaluator [20] (low, absence from vendor comparison pages).

## Academic literature (secondary dimension)

- **Deterministic first, judge as advisor.** A preprint on LLM adherence auditing found judges agreeing on verdicts while their cited reasoning was unstable, and recommends code for deterministically verifiable logic and LLM judges only for semantics [26] (high, abstract read). A September 2026 preprint independently argues the judge should be an advisor behind a deterministic layer it cannot override [27] (high). These are two labs agreeing, which meets the pack's two-source bar.
- **What moves compliance.** A factorial preprint over 1,650 Claude Code sessions and 16,050 function-level observations found no detectable effect of file size, placement, design or conflicts after correction, and about 5.6% lower compliance odds per additional function generated (OR 0.944) [22] (high, abstract read). The import calls its scoring deterministic; the abstract does not say, so that detail is unverified [22].
- **Compliance is low and must be measured from behaviour.** Preprints report agents opening contribution-policy files in 3.5% of runs [21], 0% process-instruction compliance under default framing across 2,031 sessions [25], a gap between task solving and checklist compliance [23], and low strict pass rates on handbook-following tasks [24] (medium, unverified, one lab each).
- **Outcome studies are a different question.** Context files did not improve task success and raised cost in one preprint [28], with counterpoints reporting gains [29]; neither measures rule adherence (medium, unverified). MAC-Bench applies the same deterministic-oracle pattern to non-coding trajectories [30], and a ZORO preprint on active rules for coding was seen by title only [32].

## Cross-dimension insights

- **Licence and capability point the same way.** The closest capability match is also the most permissive [1], so ruleprobe's differentiation cannot be licence or locality; it has to be a capability claude-md-doctor lacks.
- **The platforms have the data but not the rules.** Langfuse and LangSmith hold both Claude Code and Codex transcripts [17][19] but ship no rule evaluator, and if the Langfuse loaded-context claim holds [18], they also lack the rule text a verdict needs. A local tool that reads the rule file and the transcript together has a structural edge until that changes; this rests partly on an unverified claim.
- **The literature and the neighbours converge.** Both neighbours already use deterministic checks with optional model help [1][2], which is what the literature recommends [26][27]. Deterministic-first is table stakes, not a differentiator.

## Recommendations

1. **Bound the novelty claim** (PRD, differentiation). Do not claim first or only transcript-based rule measurement; claude-md-doctor and RuleReceipt disprove it [1][2] (high). Claim cross-runtime measurement over Claude Code and Codex, stated as "no other tool found as of 2026-09-23" because the Codex gap rests on absence of evidence [9] (low).
2. **Ship a Codex rollout reader in 0.2** (architecture, constraint). It is the one lane no neighbour was found in [1][2][9], and platforms already ingest Codex, so the window is time-bound [17][19] (medium, partly absence-based).
3. **Keep verdicts deterministic and quote the evidence; make any model judgment advisory and separable** (architecture, constraint). Two independent preprints support this [26][27] and both neighbours already do it [1][2], so this is parity required to be credible, not the pitch (high).
4. **Report compliance against in-session position, not file structure** (PRD, differentiation). The strongest controlled result says structure has no detectable effect and position does [22] (high for the finding; the study is a single preprint).
5. **List claude-md-doctor, RuleReceipt, /insights and Codex Code Review as the named alternatives** (product brief, alternatives), with /insights and Codex Code Review as the first-party absorption paths [15][31] (medium and low respectively).

**Project note, added after synthesis.** The research firewall kept the ruleprobe code out of this run, so recommendation 2 was written without knowing that ruleprobe 0.1.0 already reads Codex rollouts beside Claude Code transcripts (`ruleprobe/readers/codex.py`, released 2026-09-22). The recommendation is therefore already met. What it implies for 0.2 is to lead with the two-runtime reading in the claim, and to add a third reader so the lead does not rest on one runtime the platforms already ingest [17][19].

## Open questions

1. Does claude-md-doctor or RuleReceipt plan Codex support? Read their issue trackers and changelogs.
2. Does /insights score existing rules? Find Anthropic's own page for the command.
3. Does Langfuse state that loaded context is unreadable by its hooks? Fetch its coding-agent tracing guide [18].
4. What do users of either neighbour praise or complain about? No customer voice was gathered; a user-voice pass would answer it.
5. Did the factorial study [22] score compliance deterministically? Read the full paper's method section.
6. Does Codex Code Review ever read session behaviour, or only diffs [31]? Fetch the OpenAI post.
7. Is there any Codex-rollout rule-compliance tool the searches missed? A targeted Run on the Codex ecosystem would close or confirm the gap.

## Source appendix

| n | Claim or finding it supports | Publisher | Pub date | Accessed | Confidence |
| --- | --- | --- | --- | --- | --- |
| 1 | claude-md-doctor capability, licence, stars, positioning | [agent-clinic (GitHub)](https://github.com/agent-clinic/claude-md-doctor) | live page | 2026-09-23 | high |
| 2 | RuleReceipt capability, licence, stars | [rulereceipt (GitHub)](https://github.com/rulereceipt/rulereceipt) | live page | 2026-09-23 | high |
| 3 | 559 public CLAUDE.md files parsed | [dev.to (RuleReceipt author)](https://dev.to/rulereceipt/i-parsed-559-public-claudemd-files-most-of-whats-in-them-isnt-rules-3flo) | n/v | 2026-09-23 | low |
| 4 | LLM-scored prospective compliance skills | [MCP Market](https://mcpmarket.com/tools/skills/agent-md-compliance-tester) | n/v | 2026-09-23 | low |
| 5 | About 0% compliance claim | [dev.to (independent author)](https://dev.to/james-coombs/your-claudemd-rules-achieve-0-compliance-heres-the-data-kk3) | n/v | 2026-09-23 | low |
| 6 | ccusage reads many agents for cost only | [ccusage (GitHub)](https://github.com/ccusage/ccusage) | n/v | 2026-09-23 | medium |
| 7 | Analyzers report spend and tools, not rules | [yorch (GitHub)](https://github.com/yorch/cc-analyzer) | n/v | 2026-09-23 | medium |
| 8 | Cross-agent session browser, no rules | [jazzyalex (GitHub)](https://github.com/jazzyalex/agent-sessions) | n/v | 2026-09-23 | medium |
| 9 | Codex analyzer without compliance; Codex gap | [daguix (GitHub)](https://github.com/daguix/codex-usage-analyzer) | n/v | 2026-09-23 | low |
| 10 | ctxlint static only | [YawLabs (GitHub)](https://github.com/YawLabs/ctxlint) | n/v | 2026-09-23 | medium |
| 11 | agnix static linter, no transcripts | [agent-sh (GitHub)](https://github.com/agent-sh/agnix) | live page | 2026-09-23 | high |
| 12 | rulesync converts rules only | [dyoshikawa (GitHub)](https://github.com/dyoshikawa/rulesync) | n/v | 2026-09-23 | medium |
| 13 | OTel export has no adherence signal | [Anthropic](https://code.claude.com/docs/en/monitoring-usage) | live page | 2026-09-23 | high |
| 14 | Analytics have no compliance measure | [Anthropic](https://code.claude.com/docs/en/analytics) | n/v | 2026-09-23 | medium |
| 15 | /insights suggests rules; no scoring found | [Nate Meyvis (blog)](https://www.natemeyvis.com/claude-codes-insights/) | n/v | 2026-09-23 | medium |
| 16 | /insights corroboration | [Vincent Qiao (blog)](https://blog.vincentqiao.com/en/posts/claude-code-insights/) | n/v | 2026-09-23 | medium |
| 17 | Langfuse reads transcripts, no rule evaluator | [Langfuse](https://langfuse.com/integrations/developer-tools/claude-code) | live page | 2026-09-23 | high |
| 18 | Langfuse loaded-context claim | [Langfuse](https://langfuse.com/resources/engineering/coding-agent-tracing) | n/v | 2026-09-23 | low |
| 19 | LangSmith traces agents, no compliance metric | [LangChain](https://docs.langchain.com/langsmith/trace-claude-code) | n/v | 2026-09-23 | medium |
| 20 | No packaged adherence evaluator in eval vendors | [Braintrust](https://www.braintrust.dev/articles/agent-observability-complete-guide-2026) | n/v | 2026-09-23 | low |
| 21 | Contribution-rule compliance, hybrid method | [arXiv 2607.26819 (preprint)](https://arxiv.org/abs/2607.26819) | 2026-07-29 | 2026-09-23 | medium |
| 22 | File structure no effect; per-function decline | [arXiv 2605.10039 (preprint)](https://arxiv.org/abs/2605.10039) | 2026-05-11 | 2026-09-23 | high |
| 23 | OctoBench checklist compliance gap | [arXiv 2601.10343 (preprint)](https://arxiv.org/abs/2601.10343) | 2026-01-15 | 2026-09-23 | medium |
| 24 | HANDBOOK.md handbook-following tasks | [arXiv 2607.25398 (preprint)](https://arxiv.org/abs/2607.25398) | 2026-07 | 2026-09-23 | medium |
| 25 | Compliance Gap, measure from behaviour | [arXiv 2605.01771 (preprint)](https://arxiv.org/abs/2605.01771) | 2026-05-03 | 2026-09-23 | medium |
| 26 | Deterministic code for verifiable logic | [arXiv 2601.11783 (preprint)](https://arxiv.org/abs/2601.11783) | 2026-01-16 | 2026-09-23 | high |
| 27 | Judge as advisor behind deterministic layer | [arXiv 2609.02246 (preprint)](https://arxiv.org/abs/2609.02246) | 2026-09-02 | 2026-09-23 | high |
| 28 | Context files and task success | [arXiv 2602.11988 (preprint)](https://arxiv.org/abs/2602.11988) | 2026-02 | 2026-09-23 | medium |
| 29 | Counterpoint on context files | [arXiv 2607.27250 (preprint)](https://arxiv.org/html/2607.27250) | 2026-07 | 2026-09-23 | medium |
| 30 | Deterministic rules over trajectories, non-coding | [arXiv 2606.07805 (preprint)](https://arxiv.org/html/2606.07805v1) | 2026-06 | 2026-09-23 | medium |
| 31 | Codex Code Review applies AGENTS.md rules to diffs | [OpenAI](https://developers.openai.com/blog/custom-code-review-rules-for-codex) | n/v | 2026-09-23 | low |
| 32 | ZORO active rules, title only | [arXiv 2604.15625 (preprint)](https://arxiv.org/pdf/2604.15625) | 2026-04 | 2026-09-23 | low |

## Staleness map

Computed with `recon_kit.py staleness` on 2026-09-23 using the competitive pack's bars (features, packaging, positioning and absence claims 3 months; traction 6 months; sentiment 12 months) and the academic pack's ML bar (6 months). Undated and live pages take the access date.

- **Already stale:** OctoBench [23] (re-check 2026-07-15), the Evaluating AGENTS.md preprint [28] (2026-08-01) and the Stability Trap preprint [26] (2026-07-16). Check whether each has been superseded.
- **2026-10-01:** ZORO [32].
- **2026-11-03 to 2026-11-11:** the Compliance Gap [25] and the factorial study [22].
- **2026-12-01:** MAC-Bench [30].
- **2026-12-23:** every capability, licence, positioning and absence claim, including the Codex gap [9], /insights [15], Langfuse [17][18], OTel [13] and both neighbours' features [1][2]. This is the date that matters most for the decision.
- **2027-01-29 to 2027-03-23:** the contribution-rules preprint [21], the judge-as-advisor preprint [27] and both neighbours' star counts [1][2].
- **2027-09-23:** the 0% compliance blog [5].

Earliest re-check: 2026-07-15, already past.
