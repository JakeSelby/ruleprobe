# SPDX-License-Identifier: MIT
"""The package envelope, enforced: no runtime dependency; no module importing AD-8's list of
`socket`, `urllib`, `http`, `subprocess` and model clients; and a `report` that writes and
sends nothing."""
import ast
import contextlib
import io
import json
import os
import re
import socket
import tempfile
import unittest
from unittest import mock

import ruleprobe
from ruleprobe.cli import main
from ruleprobe.readers import RUNTIMES, gemini, iter_sessions
from ruleprobe.report import explain, explain_row, explain_text, measure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.dirname(os.path.abspath(ruleprobe.__file__))
CORPUS_SESSIONS = os.path.join(PACKAGE, "corpus", "sessions")

FORBIDDEN_MODULES = ("socket", "urllib", "http", "subprocess")
MODEL_CLIENTS = ("anthropic", "openai", "cohere", "mistralai", "litellm", "ollama", "groq",
                 "google.generativeai", "google.genai", "vertexai", "transformers", "llama_cpp")
IMPORT_FUNCTIONS = ("__import__", "import_module")


# --- AC 1: the dependency list, read without tomllib (3.11 and newer) ------------------------


def strip_comments(text):
    """`text` with every `#` comment removed, leaving a `#` inside a quoted string alone."""
    out, quote = [], None
    lines = text.split("\n")
    for line in lines:
        kept = []
        for i, char in enumerate(line):
            if quote:
                if char == quote and not (quote == '"' and line[i - 1:i] == "\\"):
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == "#":
                break
            kept.append(char)
        out.append("".join(kept))
    return "\n".join(out)


def project_array(text, key):
    """The quoted entries of `key`'s array in the `[project]` table, or None when absent."""
    text = strip_comments(text)
    table = re.search(r"^\[project\][ \t]*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if table is None:
        return None
    found = re.search(r"^%s[ \t]*=[ \t]*\[(.*?)\]" % re.escape(key), table.group(1), re.M | re.S)
    if found is None:
        return None
    body = found.group(1)
    if re.sub(r"\"[^\"]*\"|'[^']*'|[\s,]", "", body):
        raise ValueError("unreadable %s array: %r" % (key, body))
    return [double or single for double, single in re.findall(r"\"([^\"]*)\"|'([^']*)'", body)]


def dependency_violations(text):
    """What in a `pyproject.toml` breaks `dependencies = []`; empty when nothing does."""
    found = []
    dependencies = project_array(text, "dependencies")
    if dependencies is None:
        found.append("no dependencies key")
    found.extend("dependency %s" % entry for entry in dependencies or [])
    if "dependencies" in (project_array(text, "dynamic") or []):
        found.append("dependencies is dynamic")
    return found


# --- AC 2: the import scan -------------------------------------------------------------------


def _forbidden(name):
    for banned in FORBIDDEN_MODULES + MODEL_CLIENTS:
        if name == banned or name.startswith(banned + "."):
            return banned
    return None


def _literal_name(call):
    for arg in call.args[:1] + [k.value for k in call.keywords if k.arg == "name"]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def forbidden_imports(source, filename="<source>"):
    """Every (line, module) in `source` that imports a forbidden module: by statement, or by an
    `__import__` / `import_module` call, under any alias, with a literal name."""
    tree = ast.parse(source, filename)
    loaders = set(IMPORT_FUNCTIONS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("importlib", "builtins"):
            loaders.update(a.asname or a.name for a in node.names if a.name in IMPORT_FUNCTIONS)
    found = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module] + [node.module + "." + a.name for a in node.names]
        elif isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if (isinstance(func, ast.Name) and called in loaders) or called in IMPORT_FUNCTIONS:
                names = [_literal_name(node) or ""]
        for name in names:
            if _forbidden(name):
                found.append((node.lineno, name))
                break
    return sorted(found)


def package_modules():
    for dirpath, dirnames, filenames in os.walk(PACKAGE):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)


# --- AC 3: the guard -------------------------------------------------------------------------


_WRITE_MODE = re.compile(r"[wax+]")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_REFUSED_OS = ("mkdir", "makedirs", "rename", "replace", "remove", "unlink", "rmdir")
_REFUSED_SOCKET = ("socket", "create_connection", "socketpair", "getaddrinfo", "gethostbyname")


@contextlib.contextmanager
def no_network_no_writes():
    """Make socket creation, name lookup, every write-mode open and every filesystem change
    raise, and record each attempt, so an attempt the code under test swallows is still seen."""
    attempts = []
    real_open, real_os_open, real_file_io = io.open, os.open, io.FileIO

    def guarded_open(file, mode="r", *args, **kwargs):
        if _WRITE_MODE.search(mode):
            attempts.append("open")
            raise PermissionError("write-mode open: %r %r" % (file, mode))
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & _WRITE_FLAGS:
            attempts.append("os.open")
            raise PermissionError("write-mode os.open: %r" % (path,))
        return real_os_open(path, flags, *args, **kwargs)

    class GuardedFileIO(real_file_io):
        def __init__(self, file, mode="r", *args, **kwargs):
            if _WRITE_MODE.search(mode):
                attempts.append("io.FileIO")
                raise PermissionError("write-mode FileIO: %r %r" % (file, mode))
            real_file_io.__init__(self, file, mode, *args, **kwargs)

    def refuse(label, error):
        def refused(*args, **kwargs):
            attempts.append(label)
            raise error("%s refused: %r" % (label, args))
        return refused

    patches = [mock.patch("builtins.open", guarded_open), mock.patch("io.open", guarded_open),
               mock.patch("os.open", guarded_os_open), mock.patch("io.FileIO", GuardedFileIO)]
    patches += [mock.patch("os." + name, refuse("os." + name, PermissionError))
                for name in _REFUSED_OS]
    patches += [mock.patch("socket." + name, refuse("socket." + name, OSError))
                for name in _REFUSED_SOCKET]
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        yield attempts


def corpus_transcripts():
    # Every session file the readers walk to: each `.jsonl`, at any depth and through a
    # linked directory, and a legacy Gemini `session-*.json` its `.jsonl` does not replace.
    walked = os.walk(CORPUS_SESSIONS, followlinks=True)
    found = set(os.path.join(d, n) for d, _s, files in walked for n in files
                if n.endswith(".jsonl"))
    found.update(p for p in gemini.transcripts(CORPUS_SESSIONS) if p.endswith(".json"))
    return len(found)


class DependencyTests(unittest.TestCase):
    def test_pyproject_declares_no_runtime_dependency(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertEqual(dependency_violations(text), [])
        try:
            import tomllib
        except ImportError:
            return
        self.assertEqual(tomllib.loads(text)["project"]["dependencies"], [])

    def test_a_dependency_is_seen_and_other_tables_are_not_read(self):
        text = ('[project]\nname = "x"\ndependencies = [\n    "requests>=2",\n'
                "    'pyyaml',\n]\n\n[tool.x]\ndependencies = []\n")
        self.assertEqual(dependency_violations(text),
                         ["dependency requests>=2", "dependency pyyaml"])
        text = '[tool.x]\ndependencies = ["a"]\n\n[project]\ndependencies = []\n'
        self.assertEqual(dependency_violations(text), [])
        self.assertEqual(dependency_violations('[tool.x]\ndependencies = ["a"]\n'),
                         ["no dependencies key"])

    def test_a_bracket_in_a_comment_does_not_end_the_list(self):
        text = '[project]\ndependencies = [  # see [docs]\n    "requests",\n]\n'
        self.assertEqual(dependency_violations(text), ["dependency requests"])
        text = '[project]\ndependencies = ["a#b"]  # a [comment]\n'
        self.assertEqual(project_array(text, "dependencies"), ["a#b"])

    def test_an_unreadable_list_is_refused_not_read_as_empty(self):
        with self.assertRaises(ValueError):
            project_array("[project]\ndependencies = [requests]\n", "dependencies")
        self.assertEqual(project_array('[project]\ndependencies = [ "a", ]\n', "dependencies"),
                         ["a"])

    def test_dynamic_dependencies_are_refused(self):
        text = '[project]\ndependencies = []\ndynamic = ["version", "dependencies"]\n'
        self.assertEqual(dependency_violations(text), ["dependencies is dynamic"])
        text = ('[project]\ndependencies = []\ndynamic = ["optional-dependencies"]\n'
                '[tool.x]\ndynamic = ["dependencies"]\n')
        self.assertEqual(dependency_violations(text), [])


class ImportTests(unittest.TestCase):
    def test_the_scanned_package_is_the_source_tree(self):
        self.assertEqual(PACKAGE, os.path.join(ROOT, "ruleprobe"))

    def test_no_module_imports_the_network_a_subprocess_or_a_model_client(self):
        modules = list(package_modules())
        self.assertIn(os.path.join(PACKAGE, "cli.py"), modules)
        found = []
        for path in modules:
            with open(path, encoding="utf-8") as handle:
                for line, name in forbidden_imports(handle.read(), path):
                    found.append("%s:%d %s" % (os.path.relpath(path, ROOT), line, name))
        self.assertEqual(found, [])

    def test_the_scan_catches_every_import_form(self):
        source = ("import os, subprocess\nfrom http import client\nimport urllib.request\n"
                  "from socket import socket\nimport openai\nfrom google.genai import types\n"
                  "import importlib\nimportlib.import_module('anthropic')\n"
                  "__import__('http.client')\n")
        self.assertEqual([line for line, _ in forbidden_imports(source)],
                         [1, 2, 3, 4, 5, 6, 8, 9])

    def test_the_scan_catches_a_keyword_name(self):
        source = "from importlib import import_module\nimport_module(name='socket')\n"
        self.assertEqual(forbidden_imports(source), [(2, "socket")])
        self.assertEqual(forbidden_imports("import_module(name='json')\n"), [])

    def test_the_scan_catches_an_aliased_loader(self):
        source = "from importlib import import_module as load\nload('socket')\n"
        self.assertEqual(forbidden_imports(source), [(2, "socket")])
        self.assertEqual(forbidden_imports("load('socket')\n"), [])

    def test_the_scan_passes_a_near_miss(self):
        source = ("import shlex\nfrom .http import thing\nimport httpx_like as h\n"
                  "import socketserver_notes\nfrom . import subprocess\n"
                  "print('import socket')\n")
        self.assertEqual(forbidden_imports(source), [])


class ReportWritesAndSendsNothingTests(unittest.TestCase):
    def temporary_directory(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        return scratch.name

    def run_guarded(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with no_network_no_writes() as attempts, contextlib.redirect_stderr(err):
            code = main(list(argv), out=out)
        self.assertEqual(attempts, [])
        return code, out.getvalue(), err.getvalue()

    def test_report_over_the_corpus_runs_with_no_socket_and_no_write(self):
        code, text, err = self.run_guarded("report", "--root", CORPUS_SESSIONS, "--no-config")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        lines = text.split("\n")
        self.assertIn("detector", lines[0])
        self.assertIn("hits", lines[0])
        self.assertTrue(lines[1].startswith("---"))
        self.assertIn("transcript-hygiene/whole-file-cat", text)

    def test_report_with_config_discovery_json_and_validity_writes_nothing(self):
        home = self.temporary_directory()
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(home)
        environ = {"HOME": home, "XDG_CONFIG_HOME": home}
        with mock.patch.dict(os.environ, environ):
            os.environ.pop("RULEPROBE_CORPUS", None)
            code, text, err = self.run_guarded("report", "--root", CORPUS_SESSIONS, "--json",
                                               "--validity")
        self.assertEqual(code, 0)
        self.assertNotIn("produced no session", err)
        data = json.loads(text)
        self.assertEqual(data["read_errors"], [])
        self.assertEqual(data["measured"], corpus_transcripts())

    def test_the_guard_refuses_each_write_and_socket_and_allows_a_read(self):
        scratch = self.temporary_directory()
        existing = os.path.join(scratch, "existing.txt")
        with open(existing, "w") as handle:
            handle.write("x")
        target = os.path.join(scratch, "never-written")
        refusals = [
            ("open", lambda: open(target, "w")),
            ("open", lambda: io.open(target, "ab")),
            ("io.FileIO", lambda: io.FileIO(target, "w")),
            ("os.open", lambda: os.open(target, os.O_WRONLY | os.O_CREAT)),
            ("os.mkdir", lambda: os.mkdir(target)),
            ("os.makedirs", lambda: os.makedirs(os.path.join(target, "deep"))),
            ("os.rename", lambda: os.rename(existing, target)),
            ("os.replace", lambda: os.replace(existing, target)),
            ("os.remove", lambda: os.remove(existing)),
            ("os.unlink", lambda: os.unlink(existing)),
            ("os.rmdir", lambda: os.rmdir(scratch)),
            ("socket.socket", lambda: socket.socket()),
            ("socket.create_connection", lambda: socket.create_connection(("127.0.0.1", 9))),
            ("socket.socketpair", lambda: socket.socketpair()),
            ("socket.getaddrinfo", lambda: socket.getaddrinfo("example.invalid", 80)),
            ("socket.gethostbyname", lambda: socket.gethostbyname("example.invalid")),
        ]
        with no_network_no_writes() as attempts:
            for label, attempt in refusals:
                with self.subTest(label=label), self.assertRaises(OSError):
                    attempt()
            with open(existing, "rb") as handle:
                self.assertEqual(handle.read(), b"x")
            with io.open(existing, "r") as handle:
                self.assertEqual(handle.read(), "x")
            with io.FileIO(existing, "r") as handle:
                self.assertEqual(handle.read(), b"x")
            descriptor = os.open(existing, os.O_RDONLY)
            os.close(descriptor)
        self.assertEqual(attempts, [label for label, _ in refusals])
        self.assertEqual(sorted(os.listdir(scratch)), ["existing.txt"])


class ExplainWritesAndSendsNothingTests(unittest.TestCase):
    """`explain` holds the same envelope as `report`: the transcripts are read, the detectors
    rerun in memory, and each hit printed."""

    temporary_directory = ReportWritesAndSendsNothingTests.temporary_directory
    run_guarded = ReportWritesAndSendsNothingTests.run_guarded

    def test_explain_over_the_corpus_runs_with_no_socket_and_no_write(self):
        code, text, err = self.run_guarded("explain", "--root", CORPUS_SESSIONS, "--no-config")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertTrue(text.startswith("session   "))
        self.assertIn("detector  transcript-hygiene/whole-file-cat", text)

    def test_explain_with_config_discovery_and_filters_writes_nothing(self):
        home = self.temporary_directory()
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(home)
        with mock.patch.dict(os.environ, {"HOME": home, "XDG_CONFIG_HOME": home}):
            code, text, err = self.run_guarded("explain", "--root", CORPUS_SESSIONS,
                                               "--detector", "no/such-detector")
        self.assertEqual((code, text), (0, ""))
        self.assertNotIn("produced no session", err)
        self.assertEqual(os.listdir(home), [])

    def test_the_library_explain_and_explain_row_write_and_send_nothing(self):
        with no_network_no_writes() as attempts:
            sessions = iter_sessions(root=CORPUS_SESSIONS)
            items = [explain_text(item) for item in explain(sessions)]
            rows = [measure(s) for s in iter_sessions(root=CORPUS_SESSIONS)]
            notes = [explain_row(row, RUNTIMES) for row in rows]
        self.assertEqual(attempts, [])
        self.assertTrue(items)
        self.assertEqual(len(notes), corpus_transcripts())
        self.assertTrue(all("counts only" in note for note in notes))


if __name__ == "__main__":
    unittest.main()
