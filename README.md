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
uvx ruleprobe detectors                        # what would run
```

## What it actually covers

Be clear-eyed about the scope, because the name promises more than version 0.1 delivers.

**Today the report covers six detectors**, and they are the generic ones: reading a whole
file into the context window, an unfiltered `find`, a commit or push that walks past the
repository's hooks, a secret-shaped string written to a file, a context compaction, and a
model change mid-session. They are in the package because they mean the same thing in every
repository, and none of them needs to know what your rules say.

**Your own rules are not covered yet.** A detector for a line in your `CLAUDE.md` is a
detector somebody has to write. Today that means Python:

```python
from ruleprobe import DEFAULT, Detector, iter_sessions, measure, report

def sudo_install(events, ctx):
    return [(p.turn, p.id) for p in ctx.bash
            if any(seg[:2] == ["sudo", "pip"] for pipe in p.pipelines for seg in pipe)]

DEFAULT.add(Detector("house-style/sudo-install", "house-style", "bash", sudo_install))
print(report([measure(s) for s in iter_sessions(since=30)]))
```

A detector written as data instead - a pattern, a tool name and a rule id in a config file -
is the declarative format, tracked as
[agent-harness#452](https://github.com/JakeSelby/agent-harness/issues/452). The seam it
plugs into is already in `ruleprobe/registry.py` (`register_compiler`, `from_spec`), and it
is the thing that will make this useful to somebody who does not want to write Python.

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

## Development

```sh
git clone https://github.com/JakeSelby/ruleprobe && cd ruleprobe
python3 -m unittest discover -s tests
python3 -m compileall ruleprobe
python3 -m ruleprobe report --root tests/fixtures
```

## Origins and neighbours

The engine was carved out of [agent-harness](https://github.com/JakeSelby/agent-harness),
where it grew as a hook that measured that project's own always-loaded rules; the detectors
that were about agent-harness's rules stayed there, and the rule-agnostic half is this
package. The nearest neighbour is [Burnd](https://github.com/garvitsurana271/burnd), which
also reads Claude Code transcripts locally, for token spend rather than for rule compliance.

MIT licensed.
