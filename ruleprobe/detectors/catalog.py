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
            "id": "testing/no-test-run",
            "rule": "testing",
            "event": "session",
            "description": "A session that never ran a test command. A session that changed "
                           "nothing still counts, and a test run the shell parse cannot read "
                           "leaves the session uncounted.",
            "when": {
                "absent": {
                    "scope": "session",
                    "of": {
                        "any": [
                            {"command": {"name": ["pytest", "tox", "nox", "jest", "vitest",
                                                  "rspec"]}},
                            {"command": {"starts_with": ["python", "-m", "pytest"]}},
                            {"command": {"starts_with": ["python3", "-m", "pytest"]}},
                            {"command": {"starts_with": ["python", "-m", "unittest"]}},
                            {"command": {"starts_with": ["python3", "-m", "unittest"]}},
                            {"command": {"starts_with": ["uv", "run", "pytest"]}},
                            {"command": {"starts_with": ["npm", "test"]}},
                            {"command": {"starts_with": ["npm", "run", "test"]}},
                            {"command": {"starts_with": ["pnpm", "test"]}},
                            {"command": {"starts_with": ["yarn", "test"]}},
                            {"command": {"starts_with": ["cargo", "test"]}},
                            {"command": {"starts_with": ["go", "test"]}},
                            {"command": {"starts_with": ["make", "test"]}},
                        ],
                    },
                },
            },
            "examples": {
                "fire": [
                    {"events": [{"input": {"command": "git commit -m 'feat: add parser'"}}],
                     "note": "a commit and no test run"},
                    {"events": [{"input": {"command": "cat pytest.ini"}}],
                     "note": "reads the test configuration and runs nothing"},
                ],
                "skip": [
                    {"events": [{"input": {"command": "python3 -m pytest -q"}}],
                     "note": "the suite ran"},
                    {"events": [{"input": {"command": "cd app && npm test"}}],
                     "note": "the suite ran in a compound command"},
                    {"events": [{"input": {"command": "python3 -m unittest discover -s tests"}}],
                     "note": "the standard-library runner"},
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
                    {"command": {"regex": r"\bgit\s+push\b(?=[^;&|\n]*\s(?:-f|--force|"
                                          r"--force-with-lease(?:=\S*)?|\+(?:HEAD:)?"
                                          r"(?:main|master))(?![^\s;&|]))(?=[^;&|\n]*\s"
                                          r"\+?(?:HEAD:)?(?:main|master)(?![^\s;&|]))"}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "git push --force origin main"},
                    {"bash": "git push -f origin HEAD:master"},
                    {"bash": "git push origin +main", "note": "a forced refspec"},
                ],
                "skip": [
                    {"bash": "git push origin main", "note": "not forced"},
                    {"bash": "git push --force origin feature-parser",
                     "note": "forced, to another branch"},
                    {"bash": "git push -f origin feature && git push origin main",
                     "note": "the force and the default branch in two calls"},
                    {"bash": "echo 'git push -f origin main'", "note": "text, not a push"},
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
        "pattern": r"^(?:never|do\s+not|don't)\s+(?:read|cat|load|dump)\s+(?:a\s+|an\s+|the\s+|"
                   r"any\s+)?(?:whole|entire)\s+files?\b",
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
                           "`type(scope):`. A message from a heredoc, a file or the editor "
                           "is not read, and a merge or revert subject is passed over.",
            "when": {
                "all": [
                    {"git": {"subcommand": "commit"}},
                    {"command": {"regex": r"\bgit\s+(?:-[Cc]\s+\S+\s+)*commit\b(?:(?!\s-(?:a?m|"
                                          r"-message)(?:\s|=))[^\n;&|])*\s-(?:a?m|-message)"
                                          r"(?:\s+|=)[\"']?(?![\s\"']|\$\()(?!(?:Merge|Revert)"
                                          r"\s)(?![A-Za-z][\w-]*(?:\([^)\n]*\))?!?: \S)"}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "git commit -m \"fixed the parser\""},
                    {"bash": "git commit -am 'WIP'"},
                    {"bash": "git commit -m 'update readme' -m 'feat: body line'",
                     "note": "only the first message is the subject"},
                ],
                "skip": [
                    {"bash": "git commit -m \"fix(parser): handle empty input\"",
                     "note": "type and scope"},
                    {"bash": "git commit -m 'feat!: drop 3.8' -m 'a body'",
                     "note": "a breaking change, and a body that is not a subject"},
                    {"bash": "echo 'git commit -m wip'", "note": "text, not a commit"},
                    {"bash": "git commit --amend --no-edit", "note": "no message given"},
                ],
            },
        },
    },
    {
        "shape": "Never commit a secret-shaped file",
        "pattern": r"^(?:never|do\s+not|don't)\s+(?:commit|add|stage)\s+(?:a\s+|an\s+|any\s+)?"
                   r"(?:secrets?|credentials?|\.env|private\s+keys?)\b",
        "detector": {
            "id": "secrets/secret-file-add",
            "rule": "secrets",
            "event": "tool_use",
            "description": "A `git add` naming a secret-shaped path: `.env` and its variants "
                           "but the example ones, a private SSH key, a `.pem`, `.key`, `.p12` "
                           "or `.pfx`, or `credentials.json`. `git add -A` names none.",
            "when": {
                "all": [
                    {"git": {"subcommand": "add"}},
                    {"command": {"regex": r"\bgit\s+(?:-[Cc]\s+\S+\s+)*add\b[^\n;&|]*?\s[\"']?"
                                          r"(?:[^\s\"';&|]*/)?(?:\.env(?:\.(?!example|sample|"
                                          r"template|dist)[\w-]+)?|id_(?:rsa|dsa|ecdsa|ed25519)"
                                          r"|[\w.-]+\.(?:pem|key|p12|pfx)|credentials\.json)"
                                          r"[\"']?(?![^\s;&|])"}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "git add .env"},
                    {"bash": "git add src config/id_ed25519"},
                    {"bash": "git add deploy/server.key"},
                ],
                "skip": [
                    {"bash": "git add .env.example", "note": "the template, not the file"},
                    {"bash": "git add config/id_ed25519.pub", "note": "the public half"},
                    {"bash": "git add src/keys.py", "note": "a name, not a key"},
                    {"bash": "cat .env", "note": "read, not added"},
                ],
            },
        },
    },
)
