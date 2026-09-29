# SPDX-License-Identifier: MIT
"""The shipped catalog: declarative detectors for common rule shapes, bound by what a rule says.

A rule file section that no front matter binds is matched against every entry here, sentence
by sentence, and each sentence binds the one entry whose `pattern` matches it, so a stranger's
rule is measured without a detector written. `ruleprobe.rules` owns that binding and compiles
each entry's `detector` with `compile_detector`; how a rule's text is read, and why none or
several matches leave a sentence unbound, is its docstring.

Each entry is a mapping of three keys:

- `shape` - the rule shape, in words, for a person reading the catalog.
- `pattern` - one regular expression, anchored with `^`, matched case-insensitively at the
  start of each sentence of a rule's text. It never crosses a clause break (`;`, `,`, `:`,
  a run of hyphens between spaces such as ` - ` or ` -- `, an en or em dash): where it
  needs words between two it spans a run of characters that stops at one, never `.*`, and
  the one comma it may cross is the one opening its own contrast, as in "use uv, not pip".
- `detector` - a declarative detector entry, as a detector file holds one, carrying an
  `examples:` block with a deliberate near-miss beside each positive. `ruleprobe corpus`
  scores those examples, and the floor applies to them as to any detector.

`NEGATED_EXCEPTIONS` below the entries is the closed list of phrases that deny an exception
("admit no exception"), which never unbind a rule.

A detector reads a Bash command through the shared parse only - `command`, `git` and `env`
keys, per segment and per argument - and never through a regular expression over the whole
command, so no entry splits a command itself and none backtracks on a long one; a shape the
parse cannot see is a stated under-count in the entry's `description`.

The catalog detector keeps its own slash-free `rule`; a bound section keeps its own id, path
and all, on the rule entry that lists this detector's id, so a rule file in a subdirectory
binds as one at the root does. Six entries restate a shipped detector under the shipped id,
one for each in `DEFAULT`: a section binds the shipped detector and the report carries one
line for it, not two. Where a rule in a shape could carry a narrowing the pattern cannot
read ("never compact more than once", "never run a bare find from the home directory"), the
pattern must reach the end of the sentence, so the narrowed rule, or one with a second clause,
binds nothing. Those patterns also name only scopes as wide as the detector's: a session or the
context, never a task or a database, and files in general, never a commit, a repository, a
config file or the code.

This module holds literals and nothing else - no import, no call, no function - so it loads
through the import system the same way from a directory, a wheel or a zip on `sys.path`, and
reads no file beside itself; `tests/test_catalog.py` holds it to that. An id added here joins
`SHIPPED_IDS` in `ruleprobe/contract_data.py` in the same change.
"""

ENTRIES = (
    {
        "shape": "Run the tests before finishing",
        "pattern": r"^(?:always\s+)?run\s+(?:the\s+|all\s+(?:the\s+)?|your\s+)?(?:unit\s+)?"
                   r"tests?\b(?:(?!\s-+\s)[^;,:–—])*?\bbefore\b",
        "detector": {
            "id": "testing/test-after-change",
            "rule": "testing",
            "event": "session",
            "description": "Compliance, not violations: unlike every other catalog row, a hit "
                           "is a rule followed. Each Write, Edit, MultiEdit or Codex "
                           "`apply_patch`, as a tool or run as a command, opens an "
                           "opportunity, and a hit is one a later test run followed, so "
                           "the detector's opportunities, and how many were followed, say "
                           "how often a change was tested. A test run is a pipeline segment whose program, by "
                           "basename and past any `NAME=value`, is a known runner, or a build "
                           "tool whose first operand is its test target (`go test`, "
                           "`mvn -q test`, `make -C dir test`), past the value of a "
                           "`--cwd`, `-C`, `--prefix`, `--dir`, `-f` or `--file` flag, or a "
                           "common wrapper around one. Missed: a runner behind `env` or "
                           "`sudo`, a wrapper not listed, a build tool given another target "
                           "before its test one (`mvn clean test`, `gradle clean test`, "
                           "`make clean test`), and one whose other option takes a value "
                           "before the target (`mvn -pl core test`).",
            "when": {
                "order": {
                    "first": {"any": [
                        {"tool": {"name": ["Write", "Edit", "MultiEdit", "apply_patch"]}},
                        {"command": {"program": r"apply_patch"}},
                    ]},
                    "then": {
                        "any": [
                            {"command": {"program": r"pytest|py\.test|tox|nox|jest|vitest|"
                                                    r"mocha|rspec|phpunit|ctest"}},
                            {"command": {"program": r"python[0-9.]*",
                                         "first_operand": r"pytest|unittest"}},
                            {"command": {"program": r"npm|pnpm|yarn|bun",
                                         "first_operand": r"test"}},
                            {"command": {"program": r"go|cargo", "first_operand": r"test"}},
                            {"command": {"program": r"g?make", "first_operand": r"test|check"}},
                            {"command": {"program": r"mvnw?|gradlew?",
                                         "first_operand": r"test"}},
                            {"command": {"starts_with": ["npm", "t"]}},
                            {"command": {"starts_with": ["npm", "run", "test"]}},
                            {"command": {"starts_with": ["pnpm", "run", "test"]}},
                            {"command": {"starts_with": ["yarn", "run", "test"]}},
                            {"command": {"starts_with": ["bun", "run", "test"]}},
                            {"command": {"starts_with": ["uv", "run", "pytest"]}},
                            {"command": {"starts_with": ["uv", "run", "tox"]}},
                            {"command": {"starts_with": ["uv", "run", "python", "-m",
                                                         "pytest"]}},
                            {"command": {"starts_with": ["uv", "run", "python", "-m",
                                                         "unittest"]}},
                            {"command": {"starts_with": ["poetry", "run", "pytest"]}},
                            {"command": {"starts_with": ["pipenv", "run", "pytest"]}},
                            {"command": {"starts_with": ["pdm", "run", "pytest"]}},
                            {"command": {"starts_with": ["hatch", "test"]}},
                            {"command": {"starts_with": ["npx", "jest"]}},
                            {"command": {"starts_with": ["npx", "vitest"]}},
                            {"command": {"starts_with": ["npx", "mocha"]}},
                            {"command": {"starts_with": ["bundle", "exec", "rspec"]}},
                        ],
                    },
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
                     "note": "the runner in a virtual environment"},
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
                                {"input": {"command": "echo 'run pytest later; pytest'"}}],
                     "note": "the runner as text, a separator inside the quote"},
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
                           "hooks by flag, a hooksPath of nothing or pre-commit's SKIP.",
            "when": {
                "any": [
                    {"git": {"subcommand": ["commit", "push"], "args_any": ["--no-verify"]}},
                    {"git": {"subcommand": ["commit"], "args_any": ["-n"]}},
                    {"git": {"subcommand": ["commit", "push"],
                             "config_regex": r"^(?i:core\.hookspath)=(?:/dev/null)?$"}},
                    {"env": {"name": ["SKIP", "PRE_COMMIT_ALLOW_NO_CONFIG"],
                             "command": ["git", "pre-commit"]}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "git commit --no-verify -m 'fix: typo'"},
                    {"bash": "git commit -n -m 'fix: typo'", "note": "the short flag"},
                    {"bash": "SKIP=ruff git commit -m 'fix: typo'"},
                    {"bash": "git -c core.hooksPath=/dev/null commit -m 'fix: typo'",
                     "note": "the hooks path pointed at nothing"},
                ],
                "skip": [
                    {"bash": "git commit -m 'fix: typo'", "note": "the hooks ran"},
                    {"bash": "git log -n 5", "note": "-n on another subcommand"},
                    {"bash": "grep -rn -- --no-verify docs",
                     "note": "the flag as text, not passed to git"},
                    {"bash": "git -c core.hooksPath=.githooks commit -m 'fix: typo'",
                     "note": "the repository's own hooks turned on, not off"},
                ],
            },
        },
    },
    {
        "shape": "Never force-push the default branch",
        "pattern": r"^(?:never|do\s+not|don't)\s+force[- ]?push\b"
                   r"(?:(?!\s-+\s)[^;,:–—])*?\b(?:main|master|default\s+branch)\b",
        "detector": {
            "id": "git-safety/force-push-default",
            "rule": "git-safety",
            "event": "tool_use",
            "description": "A force push naming main or master in the same git call: a "
                           "`+` refspec, or `-f`, a short-flag cluster opening with it, or a "
                           "`--force` flag beside the branch as `main`, `HEAD:main`, "
                           "`main:main` or `refs/heads/main` in either place. A bare "
                           "`git push -f` from the default branch names none, and is missed; "
                           "so are `feature:main`, a cluster such as `-uf`, and a branch "
                           "given through a variable. "
                           "`--force-if-includes` alone forces nothing and is no hit.",
            "when": {
                "any": [
                    {"git": {"subcommand": "push",
                             "args_any": ["+main", "+master", "+HEAD:main", "+HEAD:master",
                                          "+refs/heads/main", "+refs/heads/master",
                                          "+HEAD:refs/heads/main", "+HEAD:refs/heads/master",
                                          "+main:main", "+master:master",
                                          "+main:refs/heads/main",
                                          "+master:refs/heads/master"]}},
                    {"git": {"subcommand": "push",
                             "args_any": ["main", "master", "HEAD:main", "HEAD:master",
                                          "refs/heads/main", "refs/heads/master",
                                          "HEAD:refs/heads/main", "HEAD:refs/heads/master",
                                          "main:main", "master:master",
                                          "main:refs/heads/main", "master:refs/heads/master"],
                             "token_prefix": ["-f", "--force-with-lease"]}},
                    {"git": {"subcommand": "push",
                             "args_any": ["main", "master", "HEAD:main", "HEAD:master",
                                          "refs/heads/main", "refs/heads/master",
                                          "HEAD:refs/heads/main", "HEAD:refs/heads/master",
                                          "main:main", "master:master",
                                          "main:refs/heads/main", "master:refs/heads/master"],
                             "arg_regex": "^--force$"}},
                ],
            },
            "examples": {
                "fire": [
                    {"bash": "git push --force origin main"},
                    {"bash": "git push -f origin HEAD:master"},
                    {"bash": "git push origin +main", "note": "a forced refspec"},
                    {"bash": "git -C app push -fu origin main",
                     "note": "a global option and a short-flag cluster"},
                    {"bash": "git push --force-with-lease origin HEAD:refs/heads/main",
                     "note": "a full ref"},
                    {"bash": "git push origin +refs/heads/master", "note": "a forced full ref"},
                    {"bash": "git push --force --force-if-includes origin main",
                     "note": "forced, beside a safety flag that needs a lease"},
                ],
                "skip": [
                    {"bash": "git push origin main", "note": "not forced"},
                    {"bash": "git push --force origin feature-parser",
                     "note": "forced, to another branch"},
                    {"bash": "git push --force-if-includes origin main",
                     "note": "a safety flag that forces nothing on its own"},
                    {"bash": "git push -f origin feature:main-backup",
                     "note": "forced, to a branch whose name opens with main"},
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
        "pattern": r"^(?:always\s+)?(?:use|install\s+(?:\w+\s+)?with)\s+uv\b"
                   r"(?:(?!\s-+\s)[^;,:–—])*?(?:,\s*)?\b(?:not|never|instead\s+of|"
                   r"rather\s+than)\s+(?:with\s+)?(?:sudo\s+)?pip\b",
        "detector": {
            "id": "package-manager/pip-install",
            "rule": "package-manager",
            "event": "tool_use",
            "description": "An install through pip rather than uv: `pip install` by any "
                           "path or version suffix (`.venv/bin/pip3.12 -q install`), "
                           "`python -m pip install` and `python3 -m pip install`, or `sudo "
                           "pip install` and `sudo pip3 install`. Missed: `-m pip` through a "
                           "python by path, with a version (`python3.12 -m pip install`) or "
                           "with a flag before `-m`, a pip with a version behind `sudo` "
                           "(`sudo pip3.12 install`), and pip behind `env` or another "
                           "wrapper.",
            "when": {
                "any": [
                    {"command": {"program": r"pip[0-9.]*", "first_operand": r"install"}},
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
                    {"bash": ".venv/bin/pip3.12 -q install ruff",
                     "note": "by path, version and a leading flag"},
                ],
                "skip": [
                    {"bash": "uv pip install ruff", "note": "pip's interface, through uv"},
                    {"bash": "pip --version", "note": "pip, installing nothing"},
                    {"bash": "pipx install ruff", "note": "another tool"},
                    {"bash": "pip uninstall ruff", "note": "the opposite of an install"},
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
            "description": "A `git commit` whose first message, read from the parsed "
                           "arguments (`-m`, `--message`, `-am`, `-sm`, `-amtext`), does not "
                           "open `type:` or `type(scope):`. A message from a variable, a "
                           "substitution, a heredoc, a file or the editor is not read, and "
                           "nor is one holding a `$` at all, a single-quoted literal one "
                           "included, since the parse keeps no quoting. Merge and Revert "
                           "subjects and git's own `fixup! `, `squash! ` and `amend! ` are "
                           "passed over, and any word before the colon reads as a type, so "
                           "`WIP: stuff` passes. Each is an under-count.",
            "when": {
                "git": {"subcommand": "commit",
                        "message_regex": r"^(?=\S)(?!(?:Merge|Revert)\s|(?:fixup|squash|amend)! )"
                                         r"(?![A-Za-z][\w-]*(?:\([^)\n]*\))?!?: \S)"},
            },
            "examples": {
                "fire": [
                    {"bash": "git commit -m \"fixed the parser\""},
                    {"bash": "git commit -am 'WIP'"},
                    {"bash": "git commit -m 'update readme' -m 'feat: body line'",
                     "note": "only the first message is the subject"},
                    {"bash": "git commit -m\"tidy up\"", "note": "the attached form"},
                    {"bash": "git commit -sm 'fixed it'", "note": "a sign-off cluster"},
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
                    {"bash": "git commit --author=\"A -m B\" -m 'feat: x'",
                     "note": "a -m inside another option's quoted value"},
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
            "description": "A `git add` naming a secret-shaped path: `.env`, `.env.local`, "
                           "`.env.prod` or `.env.production`, a private SSH key, a `.key`, a "
                           "`.pem` named for a key and not a public one, a `.p12` or `.pfx`, "
                           "or `credentials.json`. `git add -A` names none, and is missed. A "
                           "rule such as \"Never commit secrets\" is measured only by these "
                           "adds, never by a secret written inline into a file or a command.",
            "when": {
                "git": {"subcommand": "add",
                        "arg_regex": r"^(?:[^/]*/)*(?:\.env(?:\.(?:local|production|prod))?|"
                                     r"id_(?:rsa|dsa|ecdsa|ed25519)|[\w.-]+\.key|"
                                     r"(?![\w.-]*pub)(?=[\w.-]*key)[\w.-]*\.pem|"
                                     r"[\w.-]+\.(?:p12|pfx)|credentials\.json)\Z"},
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
                    {"bash": "git add certs/public-key.pem", "note": "a public key"},
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
    {
        "shape": "Never compact the context",
        "pattern": r"^(?:(?:never|do\s+not|don't|avoid)\s+(?:trigger(?:ing)?\s+)?(?:(?:context|"
                   r"conversation)\s+compaction|auto-?compact(?:ion|ing)?|compaction\s+of\s+(?:the\s+|"
                   r"your\s+)?(?:context|conversation|session)|compact(?:ing)?\s+(?:(?:the\s+|your\s+)?"
                   r"(?:context|conversation|session)(?:\s+window)?|mid-?(?:session|conversation)|"
                   r"(?:in\s+the\s+middle\s+of|partway\s+through)\s+(?:a|the)\s+(?:session|"
                   r"conversation)))|(?:start|open)\s+a\s+(?:fresh|new)\s+(?:session|conversation)\s+"
                   r"(?:rather\s+than|instead\s+of)\s+compacting)(?=[.!?]*$)",
        "detector": {
            "id": "cache-hygiene/compact",
            "rule": "cache-hygiene",
            "event": "session",
            "description": "The shipped detector, written as data: one hit per context "
                           "compaction, typed or automatic, since the transcript marks both "
                           "the same way, so a rule against the typed `/compact` alone, or "
                           "one scoped to a task, is not this shape and binds nothing; nor is "
                           "\"never compact more than once\", nor compaction with no word "
                           "saying it is the context's, which a database does too.",
            "when": {"kind": "compact"},
            "examples": {
                "fire": [
                    {"events": [{"kind": "compact"}], "note": "one compaction"},
                    {"events": [{"kind": "assistant_text", "text": "Done."},
                                {"kind": "compact"},
                                {"kind": "assistant_text", "text": "Resuming."}],
                     "note": "a compaction mid-session"},
                ],
                "skip": [
                    {"events": [{"kind": "assistant_text", "text": "Run /compact now?"}],
                     "note": "the command named, not run"},
                    {"bash": "echo /compact", "note": "the command as text"},
                    {"events": [{"kind": "user_prompt", "text": "/clear"}],
                     "note": "a fresh start, not a compaction"},
                ],
            },
        },
    },
    {
        "shape": "Never switch models mid-session",
        "pattern": r"^(?:(?:never|do\s+not|don't|avoid)\s+(?:switch(?:ing)?|chang(?:e|ing)|"
                   r"swap(?:ping)?)\s+(?:the\s+|your\s+)?models?\s+(?:mid-?(?:session|conversation|"
                   r"chat)|(?:in\s+the\s+middle\s+of|partway\s+through|during)\s+(?:a|the)\s+"
                   r"(?:session|conversation|chat))|(?:always\s+)?(?:stay|stick)\s+(?:on|with)\s+"
                   r"(?:one|a\s+single|the\s+same)\s+model\s+(?:for|throughout)\s+(?:the\s+"
                   r"(?:whole\s+|entire\s+)?|a\s+|each\s+)?(?:session|conversation|chat))"
                   r"(?=[.!?]*$)",
        "detector": {
            "id": "cache-hygiene/model-switch",
            "rule": "cache-hygiene",
            "event": "session",
            "description": "The shipped detector, written as data: one hit per change of the "
                           "assistant's model within a session. A bracketed model name is a "
                           "turn the runtime generated, and is stepped over. A rule naming a "
                           "purpose (\"never switch models to save money\") is not this shape "
                           "and binds nothing.",
            "when": {
                "change": {"kind": "assistant_text", "field": "model",
                           "ignore_prefix": "<", "ignore_empty": True},
            },
            "examples": {
                "fire": [
                    {"events": [{"kind": "assistant_text", "text": "a", "model": "model-a"},
                                {"kind": "assistant_text", "text": "b", "model": "model-b"}],
                     "note": "one change"},
                    {"events": [{"kind": "assistant_text", "text": "a", "model": "model-a"},
                                {"kind": "assistant_text", "text": "b", "model": "<synthetic>"},
                                {"kind": "assistant_text", "text": "c", "model": "model-b"}],
                     "note": "a change across a runtime-generated turn"},
                ],
                "skip": [
                    {"events": [{"kind": "assistant_text", "text": "a", "model": "model-a"},
                                {"kind": "assistant_text", "text": "b", "model": "model-a"}],
                     "note": "the same model throughout"},
                    {"events": [{"kind": "assistant_text", "text": "a", "model": "model-a"},
                                {"kind": "assistant_text", "text": "b", "model": "<synthetic>"},
                                {"kind": "assistant_text", "text": "c", "model": "model-a"}],
                     "note": "a runtime-generated turn between two of one model"},
                    {"events": [{"kind": "assistant_text", "text": "a", "model": "model-a"},
                                {"kind": "assistant_text", "text": "b"}],
                     "note": "a turn with no model named"},
                ],
            },
        },
    },
    {
        "shape": "Never write a secret into a file",
        "pattern": r"^(?:never|do\s+not|don't)\s+(?:write|hard-?code|paste|put|embed|inline)\s+"
                   r"(?:a\s+|an\s+|any\s+)?(?:secrets?|credentials?|(?:api|access)\s+keys?|"
                   r"(?:api|access|auth)\s+tokens?|tokens?|private\s+keys?)\s+(?:in|into|to)\s+"
                   r"(?:a\s+|any\s+)?files?(?=[.!?]*$)",
        "detector": {
            "id": "secrets/secret-in-write",
            "rule": "secrets",
            "event": "tool_use",
            "description": "The shipped detector, written as data: a secret-shaped string - an "
                           "access key id, a bearer token, a client secret assignment, a "
                           "private key block, a chat or code-host token, an `sk-` key - in "
                           "the text a Write or Edit writes, or in a Bash heredoc body. A key "
                           "given on the command line outside a heredoc is missed, and so is "
                           "a password, which has no shape.",
            "when": {
                "any": [
                    {"all": [
                        {"tool": {"name": ["Write", "Edit"]}},
                        {"arg": {"field": ["content", "new_string"],
                                 "regex": ["AKIA[0-9A-Z]{16}",
                                           r"(?i)aws_secret[_]access_key",
                                           r"Bearer [A-Za-z0-9._-]{20,}",
                                           r"(?i)client_secret\s*[:=]",
                                           "-----BEGIN [A-Z ]*PRIVATE KEY-----",
                                           "xox[bp]-",
                                           "ghp_[A-Za-z0-9]{20,}",
                                           "sk-[A-Za-z0-9]{20,}"]}},
                    ]},
                    {"all": [
                        {"tool": {"name": "Bash"}},
                        {"text": {"source": "payload",
                                  "regex": ["AKIA[0-9A-Z]{16}",
                                            r"(?i)aws_secret[_]access_key",
                                            r"Bearer [A-Za-z0-9._-]{20,}",
                                            r"(?i)client_secret\s*[:=]",
                                            "-----BEGIN [A-Z ]*PRIVATE KEY-----",
                                            "xox[bp]-",
                                            "ghp_[A-Za-z0-9]{20,}",
                                            "sk-[A-Za-z0-9]{20,}"]}},
                    ]},
                ],
            },
            # Each secret-shaped literal below is split in two, so a repository that greps
            # its tracked files for secret shapes does not trip over this module.
            "examples": {
                "fire": [
                    {"event": {"name": "Write",
                               "input": {"file_path": "config/app.env",
                                         "content": "KEY_ID=AKIA" "QQQQQQQQQQQQQQQQ\n"}},
                     "note": "an access key id written to a file"},
                    {"event": {"name": "Edit",
                               "input": {"file_path": "src/auth.py", "old_string": "x",
                                         "new_string": "client_" "secret = 'abc123'"}},
                     "note": "a client secret assigned in an edit"},
                    {"bash": "cat > token.txt <<'EOF'\nghp_" "abcdefghijklmnopqrstuvwx\nEOF",
                     "note": "a code-host token in a heredoc body"},
                ],
                "skip": [
                    {"event": {"name": "Write",
                               "input": {"file_path": "config/app.env",
                                         "content": "KEY_ID=${KEY_ID}\n"}},
                     "note": "a placeholder, not a value"},
                    {"event": {"name": "Edit",
                               "input": {"file_path": "src/auth.py", "old_string": "x",
                                         "new_string": "headers['Authorization'] = "
                                                       "'Bearer ' + token"}},
                     "note": "a token read from a variable"},
                    {"bash": "grep -rn client_" "secret src",
                     "note": "the key name searched for, nothing written"},
                    {"bash": "cat > notes.txt <<'EOF'\nrotate the keys on Friday\nEOF",
                     "note": "a heredoc with no secret in it"},
                ],
            },
        },
    },
    {
        "shape": "Filter every find",
        "pattern": r"^(?:(?:always\s+)?(?:filter|narrow)\s+(?:every\s+|each\s+|any\s+|all\s+|"
                   r"your\s+)?find(?![\w-])(?:\s+(?:commands?|calls?|searches))?(?:\s+(?:by|with)\s+"
                   r"(?:(?:a|an|its|the)\s+)?(?:name|type|depth|size|pattern)s?(?:\s+(?:or|and)\s+"
                   r"(?:(?:a|an|its|the)\s+)?(?:name|type|depth|size|pattern)s?)*)?|(?:never|"
                   r"do\s+not|don't)\s+(?:run\s+)?(?:a\s+|an\s+)?(?:unfiltered|bare|unbounded)\s+"
                   r"find(?![\w-])(?:\s+(?:commands?|calls?|searches))?)(?=[.!?]*$)",
        "detector": {
            "id": "transcript-hygiene/unfiltered-find",
            "rule": "transcript-hygiene",
            "event": "tool_use",
            "description": "The shipped detector, written as data: a lone `find` with no "
                           "narrowing predicate, no redirect and nothing piped from it. A "
                           "`find` piped to `head` is filtered by its consumer and is no hit.",
            "when": {
                "command": {"starts_with": "find", "sole_segment": True, "redirect": False,
                            "none_of": ["-name", "-iname", "-path", "-ipath", "-regex",
                                        "-iregex", "-type", "-maxdepth", "-mindepth",
                                        "-mmin", "-mtime", "-newer", "-newermt", "-size",
                                        "-perm", "-user", "-group", "-empty", "-prune",
                                        "-exec", "-execdir", "-delete", "-print0"]},
            },
            "examples": {
                "fire": [
                    {"bash": "find ."},
                    {"bash": "find src -follow", "note": "an option that narrows nothing"},
                ],
                "skip": [
                    {"bash": "find . -name '*.py'", "note": "narrowed by name"},
                    {"bash": "find . -maxdepth 2", "note": "narrowed by depth"},
                    {"bash": "find . | head -50", "note": "piped to a filter"},
                    {"bash": "find . > files.txt", "note": "redirected to a file"},
                ],
            },
        },
    },
)

#: Negated exception markers: phrases that deny an exception rather than grant one, so a rule
#: stating one ("Never force-push to main. No exceptions.") still binds. A closed list, read
#: case-insensitively, each phrase also in the plural, with any whitespace between its words,
#: and only where the clause ends after the phrase: "without exception approval" and "with no
#: exception ticket open" name a thing and deny nothing. `ruleprobe.rules` removes them from a
#: sentence before it looks for an exception or a condition word. A marker not listed here, or
#: not ending its clause, unbinds, which under-counts.
NEGATED_EXCEPTIONS = (
    "admit no exception",
    "allow no exception",
    "make no exception",
    "with no exception",
    "without any exception",
    "without exception",
    "no exception",
)
