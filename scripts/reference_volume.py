# SPDX-License-Identifier: MIT
"""Write a synthetic reference volume of Claude Code transcripts, for timing `ruleprobe report`.

    python3 scripts/reference_volume.py OUT [--sessions 500] [--megabytes 200] [--seed 50]
                                            [--anchor YYYY-MM-DD] [--subagent-share 0.15]
                                            [--recent-share 0.85] [--short-outputs]

The volume is `OUT/<project>/<session>.jsonl`, with a share of the transcripts written as
subagent files, `OUT/<project>/<parent session>/subagents/agent-<id>.jsonl`, the layout newer
Claude Code writes. `--sessions` counts every transcript file, parents and subagents alike,
because the reader reads each as one session. Lines are Claude Code's native JSONL shape, so the
real reader reads them: mostly Bash calls, then reads, edits, writes and searches, a few long
tool outputs, repeated lines for one streamed response, and the odd compaction boundary.
`--short-outputs` drops the long outputs, so the same bytes hold several times as many lines: the
dense variant, for timing how the report scales with lines rather than bytes.

Every word is generated. No transcript content, home path or personal name enters the volume.

On one Python version the output is a function of the arguments alone: the same seed, anchor and
options write the same bytes. `random` promises a stable stream only for `random()` itself, so
another version may write another volume of the same shape. `--anchor` is the day the newest
session ends, and no timestamp runs past it; it defaults to today so that `--since 30` keeps about
`--recent-share` of the sessions. Pass it explicitly to reproduce a volume.

Repository tooling, never imported by the package; standard library only.
"""
import argparse
import datetime
import json
import os
import random
import sys
import uuid

WORDS = (
    "alpha beta gamma delta config module handler request response cache index parser reader "
    "writer report session detector matcher window budget branch commit review fixture table "
    "record schema migration service client worker queue event stream buffer token filter "
    "value field source target result error warning check option default layout render"
).split()
PROJECTS = ("demo-api", "demo-web", "demo-cli", "demo-data", "demo-infra", "demo-docs",
            "demo-mobile", "demo-sdk")
FILES = ("src/app.py", "src/models.py", "src/routes.py", "src/util.py", "tests/test_app.py",
         "tests/test_models.py", "README.md", "config/settings.yaml", "pyproject.toml",
         "web/index.ts", "web/components/Table.tsx", "docs/guide.md", "Makefile")
COMMANDS = (
    "git status", "git diff --stat", "git log --oneline -5", "ls -la {dir}",
    "python3 -m pytest -q", "python3 -m unittest discover -s tests", "npm test",
    "npm run build", "grep -rn {word} src", "cat {file}", "head -n 40 {file}",
    "sed -n 1,80p {file}", "git add {file}", "git commit -m 'fix({word}): tidy the {word2}'",
    "git commit -m 'update {word}'", "git push origin HEAD", "git push --force origin main",
    "pip install {word}", "uv add {word}", "uv run pytest", "make lint", "ruff check .",
    "git commit --no-verify -m 'wip'", "rm -rf build", "git checkout -b feat/{word}",
    "gh pr create --fill", "find . -name '*.py' | head", "wc -l {file}",
)
TOOLS = (("Bash", 55), ("Read", 18), ("Edit", 10), ("Write", 5), ("Grep", 7), ("Glob", 5))
MODELS = ("model-large", "model-medium", "model-small")


class _Gen(object):
    """One volume's random stream and the sentences it builds."""

    def __init__(self, seed, short_outputs=False):
        self.rng = random.Random(seed)
        self.short_outputs = short_outputs

    def words(self, count):
        return " ".join(self.rng.choice(WORDS) for _ in range(count))

    def sentence(self):
        text = self.words(self.rng.randint(5, 16))
        return text[0].upper() + text[1:] + "."

    def paragraph(self, lines):
        return "\n".join(self.sentence() for _ in range(lines))

    def ident(self, prefix):
        return prefix + uuid.UUID(int=self.rng.getrandbits(128), version=4).hex[:24]

    def command(self):
        template = self.rng.choice(COMMANDS)
        return template.format(dir=self.rng.choice(("src", "tests", "web", ".")),
                               file=self.rng.choice(FILES), word=self.rng.choice(WORDS),
                               word2=self.rng.choice(WORDS))

    def tool(self):
        roll = self.rng.randrange(sum(weight for _, weight in TOOLS))
        for name, weight in TOOLS:
            if roll < weight:
                break
            roll -= weight
        path = "/work/project/" + self.rng.choice(FILES)
        if name == "Bash":
            return name, {"command": self.command(), "description": self.words(4)}
        if name == "Read":
            return name, {"file_path": path}
        if name == "Edit":
            return name, {"file_path": path, "old_string": self.words(8),
                          "new_string": self.words(9)}
        if name == "Write":
            return name, {"file_path": path, "content": self.paragraph(self.rng.randint(5, 60))}
        if name == "Grep":
            return name, {"pattern": self.rng.choice(WORDS), "path": "src"}
        return name, {"pattern": "**/*.py"}

    def output(self, room):
        """A tool result's text: mostly short, a few long logs, and with `short_outputs` only
        short ones. A line is at most about 128 bytes once written as JSON, so the text stays
        within `room` bytes, bar the one line every output has."""
        roll = self.rng.random()
        if self.short_outputs:
            lines = self.rng.randint(1, 20)
        elif roll < 0.04:
            lines = self.rng.randint(800, 4000)
        elif roll < 0.25:
            lines = self.rng.randint(40, 300)
        else:
            lines = self.rng.randint(1, 20)
        lines = max(1, min(lines, room // 128))
        return "\n".join("%4d  %s" % (n, self.words(self.rng.randint(3, 12)))
                         for n in range(1, lines + 1))


def _stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (moment.microsecond // 1000)


def _session_lines(gen, budget, session_id, cwd, start, cap, agent_id=""):
    """Lines of one transcript, until about `budget` bytes are written, none stamped after
    `cap`."""
    clock = [start]
    model = gen.rng.choice(MODELS)
    base = {"sessionId": session_id, "cwd": cwd, "gitBranch": "main", "version": "2.0.0"}
    if agent_id:
        base.update(isSidechain=True, agentId=agent_id)
    else:
        base["isSidechain"] = False
    parent = [None]
    written = 0
    lines = []

    def emit(kind, message=None, **extra):
        clock[0] = min(cap, clock[0] + datetime.timedelta(
            milliseconds=gen.rng.randint(200, 40000)))
        entry = {"parentUuid": parent[0], "type": kind}
        entry.update(base)
        entry["uuid"] = str(uuid.UUID(int=gen.rng.getrandbits(128), version=4))
        entry["timestamp"] = _stamp(clock[0])
        if message is not None:
            entry["message"] = message
        entry.update(extra)
        parent[0] = entry["uuid"]
        line = json.dumps(entry, separators=(",", ":")) + "\n"
        lines.append(line)
        return len(line.encode("utf-8"))

    def say(mid, text):
        return {"id": mid, "type": "message", "role": "assistant", "model": model,
                "content": [{"type": "text", "text": text}]}

    while True:
        written += emit("user", {"role": "user", "content": gen.paragraph(gen.rng.randint(1, 4))})
        for _step in range(gen.rng.randint(1, 8)):
            mid = gen.ident("msg_")
            if gen.rng.random() < 0.5:
                text = gen.paragraph(gen.rng.randint(1, 3))
                if gen.rng.random() < 0.3:
                    # A streamed response repeats its id, the early line carrying a partial.
                    written += emit("assistant", say(mid, text[:len(text) // 2]))
                written += emit("assistant", say(mid, text))
            name, tool_input = gen.tool()
            use_id = gen.ident("toolu_")
            written += emit("assistant", {
                "id": mid, "type": "message", "role": "assistant", "model": model,
                "content": [{"type": "tool_use", "id": use_id, "name": name,
                             "input": tool_input}]})
            written += emit("user", {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": use_id,
                 "content": [{"type": "text", "text": gen.output(budget - written)}]}]})
        written += emit("assistant", say(gen.ident("msg_"), gen.paragraph(gen.rng.randint(1, 5))))
        if not agent_id and gen.rng.random() < 0.02:
            written += emit("system", subtype="compact_boundary", content="Conversation compacted")
        if written >= budget:
            return lines


def _split(sessions, subagent_share):
    """`(parents, subagents)`, raising ValueError when no parent session would be left."""
    if not 0 <= subagent_share < 1:
        raise ValueError("--subagent-share must be at least 0 and below 1")
    subagents = int(round(sessions * subagent_share))
    if sessions - subagents < 1:
        raise ValueError("--sessions and --subagent-share leave no parent session")
    return sessions - subagents, subagents


def generate(out, sessions=500, megabytes=200.0, seed=50, anchor=None, subagent_share=0.15,
             recent_share=0.85, short_outputs=False):
    """Write the volume under `out` and return `(files, bytes)` written."""
    anchor = anchor or datetime.date.today()
    parents, _subagents = _split(sessions, subagent_share)
    gen = _Gen(seed, short_outputs)
    weights = [gen.rng.lognormvariate(0, 0.9) for _ in range(sessions)]
    scale = megabytes * 1024 * 1024 / sum(weights)
    budgets = [max(2000, int(w * scale)) for w in weights]
    end = datetime.datetime(anchor.year, anchor.month, anchor.day, 18, 0, 0)
    cap = datetime.datetime(anchor.year, anchor.month, anchor.day, 23, 59, 59, 999000)
    records = []
    for index in range(parents):
        if gen.rng.random() < recent_share:
            days = gen.rng.randint(0, 28)
        else:
            days = gen.rng.randint(32, 120)
        start = end - datetime.timedelta(days=days, hours=gen.rng.randint(1, 9),
                                         minutes=gen.rng.randint(0, 59))
        project = PROJECTS[index % len(PROJECTS)]
        session_id = str(uuid.UUID(int=gen.rng.getrandbits(128), version=4))
        records.append((project, session_id, start))
    total = 0
    files = 0
    for index in range(sessions):
        if index < parents:
            project, session_id, start = records[index]
            path = os.path.join(out, "-work-" + project, session_id + ".jsonl")
            agent_id = ""
        else:
            project, session_id, start = records[gen.rng.randrange(parents)]
            agent_id = gen.ident("a")[:17]
            path = os.path.join(out, "-work-" + project, session_id, "subagents",
                                "agent-%s.jsonl" % agent_id)
            start += datetime.timedelta(minutes=gen.rng.randint(1, 30))
        lines = _session_lines(gen, budgets[index], session_id, "/work/" + project, start,
                               cap, agent_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.writelines(lines)
        total += sum(len(line.encode("utf-8")) for line in lines)
        files += 1
    return files, total


def _day(value):
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD, got %r" % value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", help="directory to write; created, and must be empty")
    parser.add_argument("--sessions", type=int, default=500)
    parser.add_argument("--megabytes", type=float, default=200.0)
    parser.add_argument("--seed", type=int, default=50)
    parser.add_argument("--anchor", type=_day, default=None,
                        help="day the newest session ends (default: today)")
    parser.add_argument("--subagent-share", type=float, default=0.15)
    parser.add_argument("--recent-share", type=float, default=0.85)
    parser.add_argument("--short-outputs", action="store_true",
                        help="short tool outputs only: the dense variant")
    args = parser.parse_args(argv)
    if os.path.exists(args.out) and not os.path.isdir(args.out):
        parser.error("%s exists and is not a directory" % args.out)
    if os.path.isdir(args.out) and os.listdir(args.out):
        parser.error("%s is not empty" % args.out)
    if args.sessions < 1 or args.megabytes <= 0:
        parser.error("--sessions and --megabytes must be positive")
    try:
        _split(args.sessions, args.subagent_share)
    except ValueError as exc:
        parser.error(str(exc))
    files, total = generate(args.out, args.sessions, args.megabytes, args.seed, args.anchor,
                            args.subagent_share, args.recent_share, args.short_outputs)
    print("reference volume: %d transcript(s), %.1f MB at %s"
          % (files, total / 1024.0 / 1024.0, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
