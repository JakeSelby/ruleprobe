# ruleprobe

Find out which of your agent rules actually fire.

You have written rules for your coding agent. A `CLAUDE.md`, an `AGENTS.md`, a house style
your team argued over. You do not know whether any of them changed what the agent did.
ruleprobe reads the transcripts your agent already wrote and counts the observable things
that happened in them.

## Sixty seconds

```sh
uvx ruleprobe report
```

That reads `~/.claude/projects/**/*.jsonl` (and `~/.codex/sessions/**/*.jsonl`, if Codex
wrote any), runs the detectors over them, and prints:

```
detector                                 hits  sessions    of   share  note
---------------------------------------------------------------------------
cache-hygiene/compact                       0         0   339       0%  unobserved
cache-hygiene/model-switch                 11        11   339       3%
secrets/secret-in-write                     3         2   339       1%
transcript-hygiene/unfiltered-find          0         0   339       0%  unobserved
transcript-hygiene/whole-file-cat          89        22   339       6%
verification/no-verify                      0         0   339       0%  unobserved
```

That is a real run, over one week of one person's transcripts. Two detectors have never
fired on this machine, which is itself the finding: `unfiltered-find` and `no-verify` are
guarding against something that is not happening, and the rules behind them are paying rent
in the context window for nothing.

`share` is the fraction of sessions the detector fired in at least once. `unobserved` means
it has never fired in the window. `promote?`, above a 30 percent share, means it is common
enough that either the rule is worth stating more loudly or the rule is wrong. Both notes
stay blank until there are twenty measured sessions, because a share over five sessions is
noise.

Nothing is sent anywhere, no model is asked anything, nothing is written to disk, and the
same transcript gives the same answer every time. Python 3.9 or newer, standard library
only.

Other groupings, and a window:

```sh
uvx ruleprobe report --by repo --since 30      # last 30 days, one line per repository
uvx ruleprobe report --by stance --stance commits=conventional   # grouped by configuration
uvx ruleprobe report --root ./transcripts      # a directory of your own
uvx ruleprobe report --rules ./docs/rules      # bind detectors to rule files, and name the gaps
uvx ruleprobe detectors                        # what would run
uvx ruleprobe corpus                           # how good each detector is, over the labelled corpus
uvx ruleprobe report --json                    # the same numbers as data, rows included
```

Each row and the `--json` result carry `schema_version`, and a row with a version this release
does not know is left out of every count and tallied in `unknown_schema`. The result also
carries `renamed`, the effective fold map of retired detector id to current id that its counts
were read through. It is complete, so a saved result folds a retired id by applying it as it
stands, never by merging it again with a later release's shipped map.
The result also carries `coverage`, on every run: `measured`, `dark` and `unmeasured` count
rules, not sessions as the top-level `measured` and `unmeasured` do, and `share` is the
measured share of them. With no rules read, the counts are zero and `share` is `null`.

A row names each detector that raised in `rules_errors`, and that session leaves the
detector's hit denominator only. A row also carries `compliance`, detector id to
`{"opportunities", "followed", "undecided"}`, for each enabled detector that defines
`opportunities`; an undecided opportunity counts in `undecided` alone. When that callable
raises, or returns something other than `(turn, tool_use_id, followed)` triples (recorded as
`MalformedOpportunities`), its `rules_errors` entry carries `"hook": "opportunities"`: the
detector loses its `compliance` entry, and its hit figures are untouched.

A transcript does not record the configuration it ran under, so `--stance dimension=variant`
is how you say what it was. It is repeatable, it is what `--by stance` groups on, and it is
what a detector's `gate:` block reads: a gated detector with no stance passed never fires,
and `ruleprobe detectors` names the stance each one is waiting for.

## Sixty seconds on a rule of your own

The six above are generic. Your rules are not, and measuring one takes no Python: write a
detector beside them as data. This is a real run over the example transcript and the example
rules in this repository, so it is reproducible from a clone:

```sh
cat docs/rules/house-style.md
```

```markdown
---
rule: house-style
detector:
  id: house-style/sudo-install
  event: tool_use
  when:
    command: {starts_with: [sudo, pip]}
---

# House style

Install with `uv`, never with `sudo pip`.
```

```sh
ruleprobe report --root docs --rules docs/rules
```

```
detector                                 hits  sessions    of   share  note
---------------------------------------------------------------------------
cache-hygiene/compact                       0         0     1       0%
cache-hygiene/model-switch                  0         0     1       0%
house-style/sudo-install                    2         1     1     100%
secrets/secret-in-write                     0         0     1       0%
transcript-hygiene/unfiltered-find          0         0     1       0%
transcript-hygiene/whole-file-cat           0         0     1       0%
verification/no-test-run                    1         1     1     100%
verification/no-verify                      0         0     1       0%

rules: 2 measured, 1 dark, 1 unmeasured (50% measured)
  measured   house-style                    docs/rules/house-style.md
  dark       secrets                        docs/rules/secrets.md: a credential that never reaches a file leaves no shape in a transcript
  measured   verification                   docs/rules/verification.md
  unmeasured working-style.md#working-style docs/rules/working-style.md
```

Three lines of that report are the point. `house-style/sudo-install` is a rule of the
reader's own, firing. `secrets` is **dark** by choice: its front matter carries
`opt_out: <reason>`, because the rule is about a credential that never reaches a file and a
transcript only shows what did. `working-style` is **unmeasured**: it has neither a detector
nor an opt-out, so it is split at its headings and its one section is listed by its id,
`working-style.md#working-style`; saying so is the only way an author sees the gap. Nothing
fails; a report is evidence, not a gate.

Point `--rules` at whatever directory your own rules live in, and drop the same entries into
`.ruleprobe/detectors.yaml` at the root of a repository, or into
`~/.config/ruleprobe/detectors.yaml` for the ones you want everywhere. Both are found
without a flag; `--no-config` skips them.

## Writing a detector

An entry is `id`, `rule`, `event`, `when`, and an optional `gate`. `event` is one of
`tool_use`, `assistant_text` and `session`, and it says what a hit is counted against. `when`
is a matcher: a mapping in which every key must hold, composed with `any`, `all` and `not`.

An entry may also carry `schema_version`, the integer schema it was written under; this
release reads 1 and 2. An entry without one takes its detectors file's top-level `version`,
and a file without one is schema 1. Only a detectors file has a top-level `version`; a
`detector:` entry in rule-file front matter has no file-level default, so without its own key
it is schema 1. In a detectors file the file-level key is `version`: a top-level
`schema_version` is a finding, as a bad `version` is. An entry's own key wins over the file's.
A value this release does not know - newer than 2, below 1, or not an integer (`"2"`, `2.0`
and `true` included) - is a finding with its file and line, and only the entries that would be
read under it are skipped, so an entry written for a later schema is refused rather than
counted wrong.

```yaml
version: 2
detectors:
  - id: house-style/sudo-install
    when:
      command: {starts_with: [sudo, pip]}
  - id: house-style/old-entry
    schema_version: 1
    when:
      command: {name: npm}
```

**A tool use.** The shape is a command, a tool name, or an argument:

```yaml
- id: house-style/wide-grep
  rule: house-style
  event: tool_use
  when:
    command:
      name: grep
      none_of: [-n, --include, --exclude]
      arg_count: {max: 1}
```

**An assistant message.** One hit per message the pattern matches:

```yaml
- id: voice/hedged-verdict
  rule: voice
  event: assistant_text
  when:
    message:
      role: assistant
      final: true
      regex: "(?i)(should (now )?work|I think it works)"
```

**A whole session.** `absent` counts a session in which something never happened, which is
the only way to measure a rule that asks for something to be done; `order` counts one event
followed by another; `change` counts a field that differs from the event before it:

```yaml
- id: verification/no-test-run
  rule: verification
  event: session
  when:
    absent:
      of:
        command: {name: [pytest, tox, nox]}
      scope: session
```

Over a Bash command the shell parse skipped - empty or missing, longer than 16,384
characters, or one that does not tokenize or parse - the segment keys of `command`, `git` and
`env`, and a `text` read of `source: heredocs`, are undecided rather than false, so `not` and
`absent` do not count it. Any one such command in a session leaves the session-scope `absent`
above undecided, and so no hit, whether or not that command was the test run.
`command: {unparsed: true}` on its own matches those commands; combined with a segment key it
can never fire.

The matchers, in one list: `tool` (`name`, `glob`), `arg` (`field`, `regex`, `path_glob`,
`contains`, `equals`, `exists`), `command` (`name`, `starts_with`, `contains`, `none_of`,
`arg_count`, `sole_segment`, `redirect`, `unparsed`, `regex`), `git` (`subcommand`,
`args_any`, `args_none`, `token_prefix`), `env` (`name`, `command`), `text` (`source`,
`regex`, `contains`), `message` (`role`, `final`, `regex`, `contains`), `kind`, and the three
session matchers `order`, `absent` and `change`. `ruleprobe/matchers.py` documents each in
one line. The shipped six in `ruleprobe/detectors/common.yaml` use ten of them - `tool`,
`arg`, `command`, `git`, `env`, `text`, `kind`, `change`, `any` and `all` - because that is
what those six observables need; `message`, `order`, `absent` and `not` are exercised by the
examples on this page and in `tests/`, not by a shipped detector.

Three rules about the format worth knowing before you hit them. Every key inside one
`command` block is read against the *same* pipeline segment, so two constraints on one
command belong in one block rather than in an `all` of two. A session matcher may only be
the whole of a `session` detector's `when`, because a hit it produces is not a hit on an
event in hand. And a list is always alternatives: `regex`, `contains` and `path_glob` hold
when any one of their patterns does. `contains` is a substring, so `contains: no-verify`
finds the token `--no-verify`; `path_glob` is a path, so `*` stops at a `/`, `**` crosses
one, and `src/*.py` matches the absolute path a transcript actually carries.

**The format is a YAML subset, and JSON is the same thing.** YAML is not in the standard
library and this package takes no dependencies, so `ruleprobe/declarative.py` implements the
subset a detector needs - block and flow mappings and sequences, scalars, quoted strings,
comments - and refuses everything else by name and line: anchors, aliases, tags, block
scalars, directives, and more than one document in a file. A file named `.json` is read by
the standard library's JSON parser into exactly the same objects, so a generator can write
JSON and a person can write YAML.

**A malformed entry is a finding, not a crash.** It is printed with its file, its line and
its reason, that entry is skipped, and every other detector in the file still runs.

## What it actually covers

Be clear-eyed about the scope, because the name promises more than version 0.1 delivers.

**Six detectors ship with the package**, and they are the generic ones: reading a whole
file into the context window, an unfiltered `find`, a commit or push that walks past the
repository's hooks, a secret-shaped string written to a file, a context compaction, and a
model change mid-session. They are in the package because they mean the same thing in every
repository, and none of them needs to know what your rules say.

**Your own rules take a detector you write**, as data in the declarative format above or,
when the shape is past what a matcher can say, as Python:

```python
from ruleprobe import DEFAULT, Detector, iter_sessions, measure, report

def sudo_install(events, ctx):
    return [(p.turn, p.id) for p in ctx.bash
            if any(seg[:2] == ["sudo", "pip"] for pipe in p.pipelines for seg in pipe)]

DEFAULT.add(Detector("house-style/sudo-install", "house-style", "bash", sudo_install))
print(report([measure(s) for s in iter_sessions(since=30)]))
```

`measure`, `DEFAULT`, `Detector` imported from the root, and `Parsed`'s `.turn`, `.id` and
`.pipelines` are importable but not declared (see [the public API](#the-public-api)). A tool
pinning a version has declared alternatives for some: `Detector` from `ruleprobe.registry`,
`hit(p.event)` for `(p.turn, p.id)`, and `pipelines(p.command)` for `p.pipelines`. No declared
function yet produces a row, so `measure` has none.

The two are the same engine: `ruleprobe/detectors/common.yaml` is the shipped six written as
data, and a test asserts it produces hit-for-hit what the Python in
`ruleprobe/detectors/common.py` produces over the corpus. Python remains the escape hatch,
and the seam a third compiler plugs into is still `register_compiler` and `from_spec`.

**What a matcher cannot say.** It reads one event, or one of the three session shapes, and
nothing else. There is no arithmetic, no counting ("more than three reads in a turn"), no
reading a tool's *result*, no comparing one argument with another, and no state carried
across turns beyond `order`, `absent` and `change`. The `command` matcher inherits every
known miss of the shell parse in `ruleprobe/shell.py` - a command inside a substitution is
invisible, and so is a variable's value. A rule whose shape needs any of that is a Python
detector, and the report will not pretend otherwise.

**Unbound rule files split into one rule per section.** A file whose front matter gives
`detector:` or `opt_out:` a value is one rule, named by its `rule:` key or its file name; a key
with no value binds nothing and is a finding. Any other file is split at its ATX (`#`)
headings, so a `CLAUDE.md` of twelve sections is twelve entries in the coverage block, each
with the id `<path>#<heading-slug>` under `--rules`, and a repeated heading takes `-2`. A
section holding only a code block, an HTML comment, a table, a blockquote, an image or a link
reference is not a rule. A file with no heading, or with no section that is a rule, stays one
unmeasured rule, named by its `rule:` key or else its file name. Known misses: text above the
first heading of a headed file is no rule, a setext heading (text underlined with `===` or
`---`) does not split, and list items are never split.

**Detector validity is measured, and the measurement is small.** Every detector is scored
against a hand-labelled corpus that ships with the package - see
[How good are the detectors?](#how-good-are-the-detectors) below - but that corpus is
synthetic and it is six sessions, so it catches a detector that is wrong about a shape it
was shown and says nothing about a shape nobody thought of. The detectors deliberately
under-count: a missed hit is a quieter report, a false hit is a wrong one.

**What a count is not.** A detector fires on a shape in a transcript, not on an intention.
`whole-file-cat` firing 89 times above does not prove the agent wasted context; it proves it
read 89 files whole, which is a fact worth having and an argument worth starting.

## Why did that fire?

A count you are surprised by is one you want to check. `ruleprobe explain` reruns the
detectors over the same transcripts and prints every hit `report` counts, with the event
behind it:

```sh
uvx ruleprobe explain                                   # every hit
uvx ruleprobe explain --detector verification/no-verify # one detector's
uvx ruleprobe explain --session claude-code:sess-1 --key 1:toolu_2
```

```
session   claude-code:sess-1
key       1:toolu_2
detector  verification/no-verify
turn      1
tool use  toolu_2 (Bash)
command   git commit --no-verify -m 'fix: the thing'
```

A hit's address is its session, `<runtime>:<session id>`, plus its key, `<turn>:<tool use id>`,
or `<turn>:-` for a hit that names no tool use - a compaction, a model switch - and so has no
single event to show, only its turn. A key is unique only within its session, so both are
printed. What is shown is the Bash command, or any other tool's whole input as JSON, because a
hit does not record which field of the event matched. `--session` takes the address or the bare
session id; `--session`, `--detector` and `--key` each narrow the output, and one that matches
nothing prints nothing and exits 0; `--detector` takes a renamed id too. It takes `report`'s
`--root`, `--runtime`, `--since`, `--stance` and `--plugins`, and `--rules`, `--detectors` and
`--no-config`, so a gated or plugin detector `report` counts is listed as well; what a detector
file skipped goes to stderr.

Every line it prints, to either stream, passes through `redact` first. It redacts AWS access
key ids, Bearer tokens, private keys (header to footer), Slack, GitHub, OpenAI and Anthropic
style tokens, a URL's password, and the value after a key name - `aws_secret_access_key`,
`client_secret`, and `password`, `passwd`, `pwd`, `token`, `api_key`, `apikey`, `secret` or
`access_key` followed by `:` or `=` - through the end of its line, its continuations, and the
indented lines below when the value starts there. Any other credential can still print, so
read explain's output before you share it. A control character or a Unicode format
character is printed as its `\xNN` or `\uNNNN` escape, so a transcript cannot drive your
terminal or reorder a line, and one event's text is cut at 4,000 characters with a note of
how many were cut. Like `report`, it writes nothing and
sends nothing, and running it changes no report number. A stored row keeps counts only, not
the events behind them, so it cannot be explained after the fact; an undeclared helper in
`ruleprobe.report` says so for a row and names the rerun over its session that would.

## How good are the detectors?

A hit rate is a rate of the detector until somebody says what the detector *should* have
found. So a labelled corpus ships inside the package, at `ruleprobe/corpus/`: six synthetic
sessions in both transcript shapes, every interesting event labelled by hand with the
detectors that ought to fire on it, and a deliberate near-miss beside each one - a `cat` of
a line range, a `find` narrowed by `-name`, a `git push` after the gate ran, a heredoc with
`rm -rf` in its body as text rather than as a command.

```sh
ruleprobe corpus
```

```
detector                                pos  neg   tp   fp   fn   prec  recall     f1  note
-------------------------------------------------------------------------------------------
cache-hygiene/compact                     5    6    5    0    0   1.00    1.00   1.00
cache-hygiene/model-switch                5   10    5    0    0   1.00    1.00   1.00
secrets/secret-in-write                   6    6    6    0    0   1.00    1.00   1.00
transcript-hygiene/unfiltered-find        5    8    5    0    0   1.00    1.00   1.00
transcript-hygiene/whole-file-cat         5    6    5    0    0   1.00    1.00   1.00
verification/no-verify                    6    6    6    0    0   1.00    1.00   1.00
-------------------------------------------------------------------------------------------
total                                    32   42   32    0    0   1.00    1.00   1.00  floor 0.90
```

`pos` and `neg` are what the labels asked for; `tp`, `fp` and `fn` are what happened.
`ruleprobe corpus --floor 0.9` exits non-zero when a scored detector falls under the floor,
and CI in this repository runs exactly that. It is a gate on the repository, not on a run:
nothing in `ruleprobe report` reads the floor, and no report of yours will ever fail because
a detector scored badly. `--json` prints the same numbers as data.

`ruleprobe report --validity` puts each detector's `p=` and `r=` beside its row. It is off
by default because the report is meant to be read in a minute and an eight-column table is
not, and because the same two numbers apply to every run - they belong to the detector, not
to your transcripts.

**Read the number for what it is.** The corpus is synthetic and hand-labelled: no real
transcript content, no home paths, no personal names. A 1.00 says the detector is right
about the shapes somebody thought to write down, which is a weaker claim than it looks - the
false positives a detector meets in the wild are the ones nobody anticipated. It is a floor
under an obvious mistake and a place to put the next surprising transcript, not a measured
field accuracy. Growing it is the cheapest contribution this repository takes: add a session
under `ruleprobe/corpus/sessions/`, label it in `ruleprobe/corpus/labels.yaml`, and the
table above moves.

**A detector of your own scores itself.** Rather than a corpus, a declarative detector may
carry an `examples:` block of minimal cases, and `ruleprobe corpus --rules ./docs/rules`
scores those:

```yaml
- id: house-style/sudo-install
  rule: house-style
  event: tool_use
  when:
    command: {starts_with: [sudo, pip]}
  examples:
    fire:
      - bash: sudo pip install ruff
    skip:
      - bash: uv pip install ruff
        note: the tool the rule asks for
```

`fire` is a list of cases the detector should fire on and `skip` a list it should not. A
case is `bash: <command>`, or `event: <one event>`, or `events: [...]` for a `session`
detector, with an optional `note`. Nothing runs them at report time. A detector with no
examples and no corpus label prints `no examples` rather than a number, and the floor steps
over it: an unmeasured detector is a gap to see, not a failure to fix.

## How it is put together

- `ruleprobe/events.py` - the event schema every reader emits: `assistant_text`, `tool_use`,
  `tool_result`, `user_prompt`, `compact`.
- `ruleprobe/readers/` - one module per runtime, turning a transcript into that schema.
  Claude Code and Codex today; a reader is `ROOT`, `transcripts()` and `read()`.
- `ruleprobe/shell.py` - the Bash decomposition every shell detector shares. Compounds,
  pipelines, heredocs, substitutions and continuations, parsed once per command.
- `ruleprobe/registry.py` - `Detector`, `Registry`, `run()`. Third-party detectors arrive
  through the `ruleprobe.detectors` entry point group or through `Registry.add`.
- `ruleprobe/declarative.py` - the YAML subset and the front-matter split, with a line
  number on every refusal.
- `ruleprobe/matchers.py` - one entry compiled into the same `Detector` a Python one builds.
- `ruleprobe/rules.py` - where detector files live, and which rule files nothing measures.
- `ruleprobe/report.py` - rows in, text out. A row is a small dict, so a report can be taken
  over rows you stored months ago rather than over transcripts you still have.

## The public API

The declared API is these names, at these import paths. `tests/test_contract.py` imports and
exercises every one, so removing a name or changing a call shape below fails the suite, and a
name joins the list only with its test. Every other name in `ruleprobe.__all__` is importable
but not declared, so it may change in any release.

- `ruleprobe`: `Registry`, `analyse`, `compile_detector`, `counts`, `is_undecided`,
  `iter_sessions`, `load_bundle`, `report`, `report_data`, `run`, `validity`
- `ruleprobe.declarative`: `load`
- `ruleprobe.detectors.common`: `DETECTORS`, `SECRET_PATTERNS`
- `ruleprobe.events`: `hit`, `input_of`, `text_of`
- `ruleprobe.registry`: `Detector`, `Registry`
- `ruleprobe.shell`: `Context`, `MARKER_RE`, `MAX_COMMAND`, `Parsed`, `SUB_PLACEHOLDER`,
  `git_calls`, `has_redirect`, `normalise`, `operands`, `pipelines`, `strip_heredocs`
- `ruleprobe.validity`: `CorpusError`, `DEFAULT_FLOOR`, `Score`, `below_floor`, `score_corpus`,
  `scores_as_dict`, `validity_table`

Measuring and reporting:

```python
iter_sessions(root=None, runtime="auto", since=None, errors=None)  # -> Session(.id .repo .events)
run(events, stances=None, *, registry=DEFAULT, strict=False, errors=None)
Registry([Detector, ...]); Registry.add(Detector(id, rule, event, fn, gate=None))
Registry.from_entry_points("ruleprobe.detectors")
report(rows, by="rule", min_sessions=20, promote_share=0.30)
report_data(rows, by="rule", ...)                       # the same numbers as a dict; --json prints it
validity(registry=DEFAULT, directory=None)              # -> {detector_id: Score(.precision .recall)}
load_bundle(paths=None, rules_dir=None, cwd=None, config=True)  # -> Bundle(.detectors .rules .findings)
compile_detector(spec, path="<spec>", lines=None)               # -> Detector
```

Writing a detector in Python:

```python
Detector(id, rule, event, fn, gate)       # positional; a subclass may add __slots__ = ()
fn(events, ctx)                           # -> [(turn, tool_use_id), ...]
Detector(..., opportunities=count)        # keyword only; count(events, ctx) ->
                                          # [(turn, tool_use_id, followed), ...], followed
                                          # True, False or None when undecided
ctx.events, ctx.bash, ctx.finals          # a Context: every event, each Bash call as a
                                          # Parsed(.event .command .heredocs), final messages
hit(event); hit(event, tool_use_id=False) # -> (turn, tool_use_id or None)
git_calls(parsed, ("commit",))            # yields (segment, subcommand, args)
MARKER_RE.match(token).group(1)           # an index into parsed.heredocs
input_of(event); text_of(value); normalise(command)
```

A `gate` is `None` or a `(dimension, variants_or_None)` pair. A detector reads the event
fields `kind`, `turn`, `id`, `name`, `input`, `text`, `final`, `tool_use_id` and `tool_name`,
each on the kinds `ruleprobe/events.py` documents it for.

Scoring against the corpus:

```python
score_corpus(registry=DEFAULT, directory=None)  # -> {detector_id: Score}; raises CorpusError
Score(detector_id)                              # .detector .scored .precision .recall .add(other)
below_floor(scores, floor); scores_as_dict(scores, floor); validity_table(scores, floor)
declarative.load(path)                          # -> (document, lines)
```

A predicate from `compile_matcher` returns true, false, or a falsy undecided value when it
could not read its input. A Python caller who negates one itself reads undecided as false and
can over-count: compose through the declarative `not`, `any` and `all`, or test the result
with `is_undecided(value)` before negating it. `compile_matcher` itself is not declared: it
needs arguments the package does not declare, so it is not yet a declared way to build a
predicate, and `is_undecided` is declared ahead of it.

Four promises are not names:

- `SECRET_PATTERNS` stays a plain module-level assignment of a literal list in
  `ruleprobe/detectors/common.py`, so it can be read by syntax tree without importing.
- The wheel is pure Python and named `ruleprobe-<version>-py3-none-any.whl`.
- The package imports and runs from that wheel placed on `sys.path` as a zip, uninstalled.
- The wheel carries the corpus at `ruleprobe/corpus/`, beside `ruleprobe.__file__`. A caller
  importing from a zip unpacks it, or points `RULEPROBE_CORPUS` at a copy.

## Versioning

0.2.0 versions the contract: the declared API above, the row schema (`schema_version` on each
row and on the `report_data` result) and the detector-entry schema (`schema_version` on an entry,
`version` on a detectors file). [CHANGELOG.md](CHANGELOG.md) lists every part of that break and
its migration.

- **Within a minor series, nothing declared breaks.** No declared name, call shape, row schema
  or entry schema changes incompatibly between 0.2.0 and any 0.2.x. A patch may add; it may not
  remove or reshape. A detector renamed in a patch ships its fold entry, so rows stored under
  the old id still count under the new one, and a test fails when a shipped id is neither
  registered nor folded. The release preflight refuses a patch release whose contract test no
  longer declares a name its series' `.0` tag declared.
- **A later 0.x minor may break the declared surface, with notice.** Its changelog section opens
  with a **Breaking** heading naming the migration, and the contract test changes in the same
  release. A tool pinning a minor should treat each minor bump as a possible break: read that
  heading and re-run its own contract tests before bumping.
- **From 1.0, a break is a major.**

## Development

```sh
git clone https://github.com/JakeSelby/ruleprobe && cd ruleprobe
python3 -m unittest discover -s tests
uv run --python 3.9 python -m unittest discover -s tests   # the floor the package claims
python3 -m compileall ruleprobe
python3 -m ruleprobe report --root tests/fixtures
python3 -m ruleprobe report --root docs --rules docs/rules
python3 -m ruleprobe corpus --floor 0.9                    # the corpus gate CI runs
```

## Contributing and releases

Issues, false positives and labelled corpus sessions are welcome; [CONTRIBUTING.md](CONTRIBUTING.md)
says how a change lands, and [docs/releasing.md](docs/releasing.md) how a version ships. Questions go
to [Discussions](https://github.com/JakeSelby/ruleprobe/discussions).

## Origins and neighbours

The engine was carved out of [agent-harness](https://github.com/JakeSelby/agent-harness),
where it grew as a hook that measured that project's own always-loaded rules; the detectors
that were about agent-harness's rules stayed there, and the rule-agnostic half is this
package. The nearest neighbour is [Burnd](https://github.com/garvitsurana271/burnd), which
also reads Claude Code transcripts locally, for token spend rather than for rule compliance.

MIT licensed.
