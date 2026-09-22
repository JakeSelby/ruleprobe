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
uvx ruleprobe report --by stance               # grouped by the configuration a session ran under
uvx ruleprobe report --root ./transcripts      # a directory of your own
uvx ruleprobe report --rules ./docs/rules      # bind detectors to rule files, and name the gaps
uvx ruleprobe detectors                        # what would run
```

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

rules: 2 measured, 1 dark, 1 unmeasured
  measured   house-style                 docs/rules/house-style.md
  dark       secrets                     docs/rules/secrets.md: a credential that never reaches a file leaves no shape in a transcript
  measured   verification                docs/rules/verification.md
  unmeasured working-style               docs/rules/working-style.md
```

Three lines of that report are the point. `house-style/sudo-install` is a rule of the
reader's own, firing. `secrets` is **dark** by choice: its front matter carries
`opt_out: <reason>`, because the rule is about a credential that never reaches a file and a
transcript only shows what did. `working-style` is **unmeasured**: it has neither a detector
nor an opt-out, and saying so is the only way an author sees the gap. Nothing fails; a
report is evidence, not a gate.

Point `--rules` at whatever directory your own rules live in, and drop the same entries into
`.ruleprobe/detectors.yaml` at the root of a repository, or into
`~/.config/ruleprobe/detectors.yaml` for the ones you want everywhere. Both are found
without a flag; `--no-config` skips them.

## Writing a detector

An entry is `id`, `rule`, `event`, `when`, and an optional `gate`. `event` is one of
`tool_use`, `assistant_text` and `session`, and it says what a hit is counted against. `when`
is a matcher: a mapping in which every key must hold, composed with `any`, `all` and `not`.

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

The matchers, in one list: `tool` (`name`, `glob`), `arg` (`field`, `regex`, `path_glob`,
`contains`, `equals`, `exists`), `command` (`name`, `starts_with`, `contains`, `none_of`,
`arg_count`, `sole_segment`, `redirect`, `unparsed`, `regex`), `git` (`subcommand`,
`args_any`, `args_none`, `token_prefix`), `env` (`name`, `command`), `text` (`source`,
`regex`, `contains`), `message` (`role`, `final`, `regex`, `contains`), `kind`, and the three
session matchers `order`, `absent` and `change`. `ruleprobe/detectors/common.yaml` uses all
but four of them, and `ruleprobe/matchers.py` documents each in one line.

Two rules about the format worth knowing before you hit them. Every key inside one `command`
block is read against the *same* pipeline segment, so two constraints on one command belong
in one block rather than in an `all` of two. And a session matcher may only be the whole of
a `session` detector's `when`, because a hit it produces is not a hit on an event in hand.

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

**A rule file is one rule.** Binding is per file, not per heading: a `CLAUDE.md` holding
twelve rules is one entry in the coverage block, not twelve. Splitting rules into files is
what makes the unmeasured list mean anything.

**Detector validity is unmeasured.** Every detector here was written by reading transcripts
and arguing about edge cases, not by scoring against a labelled corpus. Nobody has measured
its precision or its recall, so treat a count as a strong hint and not as a fact; a labelled
corpus is tracked as
[agent-harness#455](https://github.com/JakeSelby/agent-harness/issues/455). The detectors
deliberately under-count: a missed hit is a quieter report, a false hit is a wrong one.

**What a count is not.** A detector fires on a shape in a transcript, not on an intention.
`whole-file-cat` firing 89 times above does not prove the agent wasted context; it proves it
read 89 files whole, which is a fact worth having and an argument worth starting.

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

The public API is five names:

```python
iter_sessions(root=None, runtime="auto", since=None)   # -> Session(.id .repo .runtime .events)
run(events, stances=None, *, registry=DEFAULT, strict=False, errors=None)
Registry.add(Detector(id, rule, event, fn, gate=None))
Registry.from_entry_points("ruleprobe.detectors")
report(rows, by="rule", min_sessions=20, promote_share=0.30)
```

plus two for the declarative half:

```python
load_bundle(paths=None, rules_dir=None, cwd=None, config=True)  # -> Bundle(.detectors .rules .findings)
compile_detector(spec, path="<spec>", lines=None)               # -> Detector
```

## Development

```sh
git clone https://github.com/JakeSelby/ruleprobe && cd ruleprobe
python3 -m unittest discover -s tests
uv run --python 3.9 python -m unittest discover -s tests   # the floor the package claims
python3 -m compileall ruleprobe
python3 -m ruleprobe report --root tests/fixtures
python3 -m ruleprobe report --root docs --rules docs/rules
```

## Origins and neighbours

The engine was carved out of [agent-harness](https://github.com/JakeSelby/agent-harness),
where it grew as a hook that measured that project's own always-loaded rules; the detectors
that were about agent-harness's rules stayed there, and the rule-agnostic half is this
package. The nearest neighbour is [Burnd](https://github.com/garvitsurana271/burnd), which
also reads Claude Code transcripts locally, for token spend rather than for rule compliance.

MIT licensed.
