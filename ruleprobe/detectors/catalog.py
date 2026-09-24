# SPDX-License-Identifier: MIT
"""The shipped catalog: declarative detectors for common rule shapes, bound by what a rule says.

A rule file section that no front matter binds is matched against every entry here, and binds
the one entry whose `pattern` matches its text, so a stranger's rule is measured without a
detector written. `ruleprobe.rules` owns that binding and compiles each entry's `detector`
with `compile_detector`; how a rule's text is read, and why none or several matches leave it
unmeasured, is its docstring.

Each entry is a mapping of three keys:

- `shape` - the rule shape, in words, for a person reading the catalog.
- `pattern` - one regular expression, anchored with `^`, matched case-insensitively at the
  start of each sentence of a rule's text.
- `detector` - a declarative detector entry, as a detector file holds one, carrying an
  `examples:` block with a deliberate near-miss beside each positive. `ruleprobe corpus`
  scores those examples, and the floor applies to them as to any detector.

The catalog detector keeps its own slash-free `rule`; a bound section keeps its own id, path
and all, on the rule entry that lists this detector's id, so a rule file in a subdirectory
binds as one at the root does. Two entries restate a shipped detector,
`verification/no-verify` and `transcript-hygiene/whole-file-cat`, under the shipped id: a
section binds the shipped detector and the report carries one line for it, not two.

This module holds literals and nothing else - no import, no call, no function - so it loads
through the import system the same way from a directory, a wheel or a zip on `sys.path`, and
reads no file beside itself; `tests/test_catalog.py` holds it to that. An id added here joins
`SHIPPED_IDS` in `ruleprobe/contract_data.py` in the same change.
"""

ENTRIES = (
    {
        "shape": "Run the tests before finishing",
        "pattern": r"^(?:always\s+)?run\s+(?:the\s+|all\s+(?:the\s+)?|your\s+)?(?:unit\s+)?"
                   r"tests?\b.*\bbefore\b",
        "detector": {
            "id": "testing/test-after-change",
            "rule": "testing",
            "event": "session",
            "description": "A file change followed, later in the session, by a test run. Each "
                           "Write or Edit opens an opportunity, and a hit is one followed, so "
                           "the report's opportunities and followed count say how often a "
                           "change was tested. A runner is read at a command's start, by the "
                           "basename of its first word or through a common wrapper, on the "
                           "command's first line only.",
            "when": {
                "order": {
                    "first": {"tool": {"name": ["Write", "Edit", "MultiEdit"]}},
                    "then": {"command": {"regex": r"^(?:(?:[^'\"\\\n;&|(]|\\.|'[^'\n]*'|\"(?:[^\"\\\n]|\\.)*\")*[;&|(]+\s*)*\s*"
                                          r"(?:[A-Za-z_]\w*=\S*\s+)*"
                                          r"(?:(?:uv|poetry|pipenv|hatch|pdm)\s+run\s+|npx\s+|"
                                          r"bundle\s+exec\s+)?(?:(?:\S*/)?(?:pytest|py\.test|tox|"
                                          r"nox|jest|vitest|mocha|rspec|phpunit|ctest)"
                                          r"(?![^\s;&|)])|(?:\S*/)?python[\d.]*\s+-m\s+(?:pytest|"
                                          r"unittest)\b|(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test\b|"
                                          r"(?:go|cargo)\s+test\b|(?:\S*/)?(?:mvn|mvnw|gradle|"
                                          r"gradlew)\s+(?:-\S+\s+)*test\b|make\s+(?:-\S+\s+)*"
                                          r"(?:test|check)\b)"}},
                    "within": 100000,
                },
            },
            "examples": {
                "fire": [
                    {"events": [{"name": "Edit", "input": {"file_path": "src/app.py"}},
                                {"input": {"command": "python3 -m pytest -q"}}],
                     "note": "a change, then the suite"},
                    {"events": [{"name": "Write", "input": {"file_path": "src/app.py"}},
                                {"input": {"command": "uv run pytest"}}],
                     "note": "through a wrapper"},
                    {"events": [{"name": "Edit", "input": {"file_path": "src/app.py"}},
                                {"input": {"command": ".venv/bin/pytest tests"}}],
                     "note": "the runner by its basename"},
                    {"events": [{"name": "Edit", "input": {"file_path": "web/app.ts"}},
                                {"input": {"command": "cd web && pnpm run test"}}],
                     "note": "in a compound command"},
                ],
                "skip": [
                    {"events": [{"name": "Edit", "input": {"file_path": "src/app.py"}},
                                {"input": {"command": "cat pytest.ini"}}],
                     "note": "reads the test configuration and runs nothing"},
                    {"events": [{"input": {"command": "python3 -m pytest -q"}},
                                {"name": "Edit", "input": {"file_path": "src/app.py"}}],
                     "note": "the suite ran before the change, not after"},
                    {"events": [{"name": "Edit", "input": {"file_path": "src/app.py"}},
                                {"input": {"command": "pip install pytest"}}],
                     "note": "installs the runner and runs nothing"},
                    {"events": [{"name": "Edit", "input": {"file_path": "src/app.py"}},
                                {"input": {"command": "echo 'run pytest later'"}}],
                     "note": "the runner as text"},
                ],
            },
        },
    },
    {
        "shape": "Never skip pre-commit hooks with --no-verify",
        "pattern": r"^(?:never|do\s+not|don't)\s+(?:(?:skip|bypass)\s+(?:the\s+)?"
                   r"(?:pre-commit\s+|commit\s+|git\s+)?hooks?\b|(?:use|pass)\s+--no-verify\b)",
        "detector": {
            "id": "verification/no-verify",
            "rule": "verification",
            "event": "tool_use",
            "description": "The shipped detector, written as data: a commit or push past the "
                           "hooks by flag, hooksPath override or pre-commit's SKIP.",
            "when": {
                "any": [
                    {"git": {"subcommand": ["commit", "push"], "args_any": ["--no-verify"]}},
                    {"git": {"subcommand": ["commit"], "args_any": ["-n"]}},
                    {"git": {"subcommand": ["commit", "push"],
                             "token_prefix": "core.hooksPath="}},
                    {"env": {"name": ["SKIP", "PRE_COMMIT_ALLOW_NO_CONFIG"],
                             "command": ["git", "pre-commit"]}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "git commit --no-verify -m 'fix: typo'"},
                    {"bash": "git commit -n -m 'fix: typo'", "note": "the short flag"},
                    {"bash": "SKIP=ruff git commit -m 'fix: typo'"},
                ],
                "skip": [
                    {"bash": "git commit -m 'fix: typo'", "note": "the hooks ran"},
                    {"bash": "git log -n 5", "note": "-n on another subcommand"},
                    {"bash": "grep -rn -- --no-verify docs",
                     "note": "the flag as text, not passed to git"},
                ],
            },
        },
    },
    {
        "shape": "Never force-push the default branch",
        "pattern": r"^(?:never|do\s+not|don't)\s+force[- ]?push\b.*\b(?:main|master|"
                   r"default\s+branch)\b",
        "detector": {
            "id": "git-safety/force-push-default",
            "rule": "git-safety",
            "event": "tool_use",
            "description": "A force push naming main or master in the same git call. A bare "
                           "`git push -f` from the default branch names none, and is missed.",
            "when": {
                "all": [
                    {"git": {"subcommand": "push",
                             "args_any": ["main", "master", "HEAD:main", "HEAD:master",
                                          "+main", "+master", "+HEAD:main", "+HEAD:master"]}},
                    {"command": {"regex": r"^(?:(?:[^'\"\\\n;&|(]|\\.|'[^'\n]*'|\"(?:[^\"\\\n]|\\.)*\")*[;&|(]+\s*)*\s*"
                                          r"(?:[A-Za-z_]\w*=\S*\s+)*"
                                          r"git\s+(?:(?:-C|-c)\s+\S+\s+|--[\w-]+(?:=\S+)?\s+)*push\b(?=[^;&|\n]*\s(?:-(?!-)[A-Za-z]*f[A-Za-z]*|"
                                          r"--force|--force-with-lease(?:=\S*)?|\+(?:HEAD:)?"
                                          r"(?:refs/heads/)?(?:main|master))(?![^\s;&|]))"
                                          r"(?=[^;&|\n]*\s\+?(?:HEAD:)?(?:refs/heads/)?"
                                          r"(?:main|master)(?![^\s;&|]))"}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "git push --force origin main"},
                    {"bash": "git push -f origin HEAD:master"},
                    {"bash": "git push origin +main", "note": "a forced refspec"},
                    {"bash": "git -C app push -fu origin main",
                     "note": "a global option and a short-flag cluster"},
                ],
                "skip": [
                    {"bash": "git push origin main", "note": "not forced"},
                    {"bash": "git push --force origin feature-parser",
                     "note": "forced, to another branch"},
                    {"bash": "git push -f origin feature && git push origin main",
                     "note": "the force and the default branch in two calls"},
                    {"bash": "echo 'git push -f origin main'", "note": "text, not a push"},
                    {"bash": "git push origin main; echo \"git push -f origin main\"",
                     "note": "the force only in another segment's text"},
                ],
            },
        },
    },
    {
        "shape": "Use the named package manager, not another: uv, not pip",
        "pattern": r"^(?:always\s+)?(?:use|install\s+(?:\w+\s+)?with)\s+uv\b.*"
                   r"\b(?:not|never|instead\s+of|rather\s+than)\b.*\bpip\b",
        "detector": {
            "id": "package-manager/pip-install",
            "rule": "package-manager",
            "event": "tool_use",
            "description": "An install through pip rather than uv.",
            "when": {
                "any": [
                    {"command": {"starts_with": ["pip", "install"]}},
                    {"command": {"starts_with": ["pip3", "install"]}},
                    {"command": {"starts_with": ["python", "-m", "pip", "install"]}},
                    {"command": {"starts_with": ["python3", "-m", "pip", "install"]}},
                    {"command": {"starts_with": ["sudo", "pip", "install"]}},
                    {"command": {"starts_with": ["sudo", "pip3", "install"]}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "pip install ruff"},
                    {"bash": "python3 -m pip install -r requirements.txt"},
                    {"bash": "sudo pip install ruff"},
                ],
                "skip": [
                    {"bash": "uv pip install ruff", "note": "pip's interface, through uv"},
                    {"bash": "pip --version", "note": "pip, installing nothing"},
                    {"bash": "pipx install ruff", "note": "another tool"},
                ],
            },
        },
    },
    {
        "shape": "Do not read a whole file into context",
        "pattern": r"^(?:never|do\s+not|don't)\s+(?:cat\s+(?:a\s+|an\s+|the\s+|any\s+)?(?:whole|"
                   r"entire)\s+files?\b|(?:read|load|dump)\s+(?:a\s+|an\s+|the\s+|any\s+)?"
                   r"(?:whole|entire)\s+files?\s+into\s+(?:the\s+|your\s+)?context\b)",
        "detector": {
            "id": "transcript-hygiene/whole-file-cat",
            "rule": "transcript-hygiene",
            "event": "tool_use",
            "description": "The shipped detector, written as data: a lone `cat` of one path.",
            "when": {
                "command": {"starts_with": "cat", "sole_segment": True, "redirect": False,
                            "arg_count": 1},
            },
            "examples": {
                "fire": [
                    {"bash": "cat README.md"},
                    {"bash": "cat src/app/main.py"},
                ],
                "skip": [
                    {"bash": "cat README.md | head -40", "note": "piped to a filter"},
                    {"bash": "cat a.md b.md", "note": "two operands"},
                    {"bash": "cat README.md > copy.md", "note": "redirected"},
                ],
            },
        },
    },
    {
        "shape": "Conventional Commit subjects",
        "pattern": r"^(?:(?:always\s+)?(?:use|write|follow)\s+(?:the\s+)?conventional\s+"
                   r"commits?\b|(?:every\s+)?commit\s+(?:messages?|subjects?)\s+(?:must\s+|"
                   r"should\s+)?(?:follow|use)\s+(?:the\s+)?conventional\s+commits?\b)",
        "detector": {
            "id": "commits/non-conventional-subject",
            "rule": "commits",
            "event": "tool_use",
            "description": "A `git commit -m` whose first message does not open `type:` or "
                           "`type(scope):`. A message from a variable, a substitution, a "
                           "heredoc, a file or the editor is not read, and a merge or revert "
                           "subject is passed over.",
            "when": {
                "all": [
                    {"git": {"subcommand": "commit"}},
                    {"command": {"regex": r"^(?:(?:[^'\"\\\n;&|(]|\\.|'[^'\n]*'|\"(?:[^\"\\\n]|\\.)*\")*[;&|(]+\s*)*\s*"
                                          r"(?:[A-Za-z_]\w*=\S*\s+)*"
                                          r"git\s+(?:(?:-C|-c)\s+\S+\s+|--[\w-]+(?:=\S+)?\s+)*commit\b(?:(?!\s-(?:a?m|-message))[^\n;&|])*"
                                          r"\s-(?:a?m|-message)(?:\s+|=)?[\"']?(?![\s\"'$`])"
                                          r"(?!(?:Merge|Revert)\s)"
                                          r"(?![A-Za-z][\w-]*(?:\([^)\n]*\))?!?: \S)"}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "git commit -m \"fixed the parser\""},
                    {"bash": "git commit -am 'WIP'"},
                    {"bash": "git commit -m 'update readme' -m 'feat: body line'",
                     "note": "only the first message is the subject"},
                    {"bash": "git commit -m\"tidy up\"", "note": "the attached form"},
                ],
                "skip": [
                    {"bash": "git commit -m \"fix(parser): handle empty input\"",
                     "note": "type and scope"},
                    {"bash": "git commit -m 'feat!: drop 3.8' -m 'a body'",
                     "note": "a breaking change, and a body that is not a subject"},
                    {"bash": "echo 'git commit -m wip'", "note": "text, not a commit"},
                    {"bash": "git commit --amend --no-edit", "note": "no message given"},
                    {"bash": "git commit -m \"$MSG\"", "note": "a subject nobody can read"},
                    {"bash": "git commit -m 'feat: x' && echo \"git commit -m wip\"",
                     "note": "the bad subject only in another segment's text"},
                ],
            },
        },
    },
    {
        "shape": "Never commit a secret-shaped file",
        "pattern": r"^(?:never|do\s+not|don't)\s+(?:commit|stage|git\s+add)\s+(?:a\s+|an\s+|any\s+)?"
                   r"(?:secrets?|credentials?|\.env|private\s+keys?)\b",
        "detector": {
            "id": "secrets/secret-file-add",
            "rule": "secrets",
            "event": "tool_use",
            "description": "A `git add` naming a secret-shaped path: `.env`, `.env.local` or "
                           "`.env.production`, a private SSH key, a `.key`, a `.pem` named for "
                           "a key, a `.p12` or `.pfx`, or `credentials.json`. `git add -A` "
                           "names none, and only the command's first line is read.",
            "when": {
                "all": [
                    {"git": {"subcommand": "add"}},
                    {"command": {"regex": r"^(?:(?:[^'\"\\\n;&|(]|\\.|'[^'\n]*'|\"(?:[^\"\\\n]|\\.)*\")*[;&|(]+\s*)*\s*"
                                          r"(?:[A-Za-z_]\w*=\S*\s+)*"
                                          r"git\s+(?:(?:-C|-c)\s+\S+\s+|--[\w-]+(?:=\S+)?\s+)*add\b[^\n;&|]*?\s[\"']?(?:[^\s\"';&|]*/)?"
                                          r"(?:\.env(?:\.(?:local|production|prod))?|id_(?:rsa|"
                                          r"dsa|ecdsa|ed25519)|[\w.-]+\.key|privkey\.pem|"
                                          r"[\w.-]*key[\w.-]*\.pem|[\w.-]+\.(?:p12|pfx)|"
                                          r"credentials\.json)[\"']?(?![^\s;&|])"}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "git add .env"},
                    {"bash": "git add src config/id_ed25519"},
                    {"bash": "git add deploy/server.key"},
                    {"bash": "git add certs/privkey.pem"},
                ],
                "skip": [
                    {"bash": "git add .env.example", "note": "the template, not the file"},
                    {"bash": "git add config/id_ed25519.pub", "note": "the public half"},
                    {"bash": "git add src/keys.py", "note": "a name, not a key"},
                    {"bash": "cat .env", "note": "read, not added"},
                    {"bash": "git add .env.test", "note": "a test environment"},
                    {"bash": "git add certs/ca.pem", "note": "a certificate"},
                    {"bash": "git add src; echo \"git add .env\"",
                     "note": "the path only in another segment's text"},
                ],
            },
        },
    },
)
