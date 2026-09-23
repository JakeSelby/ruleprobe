# SPDX-License-Identifier: MIT
"""The package envelope, enforced: no runtime dependency, no network or subprocess import, and
a `report` that writes and sends nothing."""
import ast
import builtins
import contextlib
import io
import os
import re
import socket
import unittest
from unittest import mock

import ruleprobe
from ruleprobe.cli import main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.dirname(os.path.abspath(ruleprobe.__file__))
CORPUS_SESSIONS = os.path.join(PACKAGE, "corpus", "sessions")

FORBIDDEN_MODULES = ("socket", "urllib", "http", "subprocess")
MODEL_CLIENTS = ("anthropic", "openai", "cohere", "mistralai", "litellm", "ollama", "groq",
                 "google.generativeai", "google.genai", "vertexai", "transformers", "llama_cpp")


def project_dependencies(text):
    """The `dependencies` list of the `[project]` table, as its quoted entries, or None when the
    key is absent. A reader for this one key, since `tomllib` is 3.11 and newer."""
    table = re.search(r"^\[project\][ \t]*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if table is None:
        return None
    key = re.search(r"^dependencies[ \t]*=[ \t]*\[(.*?)\]", table.group(1), re.M | re.S)
    if key is None:
        return None
    body = "\n".join(line.split("#", 1)[0] for line in key.group(1).split("\n"))
    entries = re.findall(r"\"([^\"]*)\"|'([^']*)'", body)
    leftover = re.sub(r"\"[^\"]*\"|'[^']*'|[\s,]", "", body)
    if leftover:
        raise ValueError("unreadable dependencies list: %r" % key.group(1))
    return [double or single for double, single in entries]


def _forbidden(name):
    for banned in FORBIDDEN_MODULES + MODEL_CLIENTS:
        if name == banned or name.startswith(banned + "."):
            return banned
    return None


def forbidden_imports(source, filename="<source>"):
    """Every (line, module) in `source` that imports a forbidden module, by statement or by an
    `__import__` / `import_module` call with a literal name."""
    found = []
    for node in ast.walk(ast.parse(source, filename)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module] + [node.module + "." + a.name for a in node.names]
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            called = getattr(func, "id", None) or getattr(func, "attr", None)
            first = node.args[0]
            if called in ("__import__", "import_module") and isinstance(first, ast.Constant) \
                    and isinstance(first.value, str):
                names = [first.value]
        for name in names:
            banned = _forbidden(name)
            if banned:
                found.append((node.lineno, name))
                break
    return found


def package_modules():
    for dirpath, dirnames, filenames in os.walk(PACKAGE):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)


_WRITE_MODE = re.compile(r"[wax+]")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


@contextlib.contextmanager
def no_network_no_writes():
    """Make socket creation and every write-mode open raise, and record each attempt, so an
    attempt the code under test swallows is still seen."""
    attempts = []
    real_open, real_os_open = builtins.open, os.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if _WRITE_MODE.search(mode):
            attempts.append(("open", file, mode))
            raise PermissionError("write-mode open during report: %r %r" % (file, mode))
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & _WRITE_FLAGS:
            attempts.append(("os.open", path, flags))
            raise PermissionError("write-mode os.open during report: %r" % (path,))
        return real_os_open(path, flags, *args, **kwargs)

    def refuse_socket(*args, **kwargs):
        attempts.append(("socket", args))
        raise OSError("socket creation during report")

    with mock.patch("builtins.open", guarded_open), mock.patch("io.open", guarded_open), \
            mock.patch("os.open", guarded_os_open), \
            mock.patch("socket.socket", refuse_socket), \
            mock.patch("socket.create_connection", refuse_socket), \
            mock.patch("socket.socketpair", refuse_socket):
        yield attempts


class DependencyTests(unittest.TestCase):
    def test_pyproject_declares_no_runtime_dependency(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertEqual(project_dependencies(text), [])
        dynamic = re.search(r"^dynamic[ \t]*=[ \t]*\[(.*?)\]", text, re.M | re.S)
        self.assertNotIn("dependencies", dynamic.group(1) if dynamic else "")
        try:
            import tomllib
        except ImportError:
            return
        self.assertEqual(tomllib.loads(text)["project"]["dependencies"], [])

    def test_the_reader_sees_a_dependency_when_there_is_one(self):
        text = ('[project]\nname = "x"\ndependencies = [\n    "requests>=2",  # http\n'
                "    'pyyaml',\n]\n\n[tool.x]\ndependencies = []\n")
        self.assertEqual(project_dependencies(text), ["requests>=2", "pyyaml"])

    def test_the_reader_reads_only_the_project_table(self):
        text = '[tool.x]\ndependencies = ["a"]\n\n[project]\ndependencies = []\n'
        self.assertEqual(project_dependencies(text), [])
        self.assertIsNone(project_dependencies('[tool.x]\ndependencies = ["a"]\n'))


class ImportTests(unittest.TestCase):
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

    def test_the_scan_passes_a_near_miss(self):
        source = ("import shlex\nfrom .http import thing\nimport httpx_like as h\n"
                  "import socketserver_notes\nfrom . import subprocess\n"
                  "print('import socket')\n")
        self.assertEqual(forbidden_imports(source), [])


class ReportWritesAndSendsNothingTests(unittest.TestCase):
    def test_report_over_the_corpus_runs_with_no_socket_and_no_write(self):
        out = io.StringIO()
        with no_network_no_writes() as attempts:
            code = main(["report", "--root", CORPUS_SESSIONS, "--no-config"], out=out)
        self.assertEqual(attempts, [])
        self.assertEqual(code, 0)
        lines = out.getvalue().split("\n")
        self.assertIn("detector", lines[0])
        self.assertIn("hits", lines[0])
        self.assertTrue(lines[1].startswith("---"))
        self.assertIn("transcript-hygiene/whole-file-cat", out.getvalue())

    def test_the_guard_refuses_a_write_and_a_socket(self):
        scratch = os.path.join(CORPUS_SESSIONS, "never-written.txt")
        with no_network_no_writes() as attempts:
            with self.assertRaises(PermissionError):
                open(scratch, "w")
            with self.assertRaises(PermissionError):
                io.open(scratch, "ab")
            with self.assertRaises(PermissionError):
                os.open(scratch, os.O_WRONLY | os.O_CREAT)
            with self.assertRaises(OSError):
                socket.socket()
            with self.assertRaises(OSError):
                socket.create_connection(("127.0.0.1", 9))
            with open(os.path.join(ROOT, "pyproject.toml"), "rb") as handle:
                self.assertTrue(handle.read(1))
        self.assertEqual([kind for kind, *_ in attempts],
                         ["open", "open", "os.open", "socket", "socket"])
        self.assertFalse(os.path.exists(scratch))


if __name__ == "__main__":
    unittest.main()
