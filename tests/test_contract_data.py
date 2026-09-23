# SPDX-License-Identifier: MIT
"""The shipped contract data: literals only, and a shipped id is never silently lost.

`ruleprobe/contract_data.py` must load the same way from a zip as from a directory, so it
may hold nothing the import system would have to run: no import, no call, no function. And
every id any release shipped must still be either registered in `DEFAULT` or a key of the
fold map, or a ledger written under that release loses the history stored under it.
"""
import ast
import inspect
import unittest

from ruleprobe import DEFAULT, contract_data
from ruleprobe.registry import fold_map


def non_literal(source):
    """The line numbers of every top-level statement in `source` that is not a docstring or
    a plain `NAME = <literal>` assignment."""
    bad = []
    for index, node in enumerate(ast.parse(source).body):
        if (index == 0 and isinstance(node, ast.Expr)
                and isinstance(getattr(node, "value", None), ast.Constant)
                and isinstance(node.value.value, str)):
            continue
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            try:
                ast.literal_eval(node.value)
                continue
            except ValueError:
                pass
        bad.append(node.lineno)
    return bad


def unaccounted(shipped_ids, registry, renamed):
    """The shipped ids that are neither registered in `registry` nor folded by `renamed`."""
    folds = fold_map(renamed)
    return [did for did in shipped_ids if did not in registry and did not in folds]


class LiteralTests(unittest.TestCase):
    def setUp(self):
        with open(inspect.getsourcefile(contract_data), encoding="utf-8") as handle:
            self.source = handle.read()

    def test_the_module_holds_only_literals(self):
        self.assertEqual(non_literal(self.source), [])

    def test_the_check_catches_an_import_a_call_and_a_function(self):
        for snippet in ("import os\n", "X = open('ids.txt').read()\n",
                        "def f():\n    return {}\n", "X = dict(a=1)\n", "X: dict = {}\n"):
            with self.subTest(snippet=snippet):
                self.assertEqual(non_literal(snippet), [1])

    def test_the_check_passes_a_docstring_and_literal_assignments(self):
        self.assertEqual(non_literal('"""doc"""\nA = {}\nB = ("x/y",)\n'), [])

    def test_the_values_are_a_string_map_and_a_string_sequence(self):
        self.assertIsInstance(contract_data.RENAMED, dict)
        for old, new in contract_data.RENAMED.items():
            self.assertIsInstance(old, str)
            self.assertIsInstance(new, str)
        self.assertTrue(contract_data.SHIPPED_IDS)
        for did in contract_data.SHIPPED_IDS:
            self.assertIsInstance(did, str)
        self.assertEqual(len(set(contract_data.SHIPPED_IDS)), len(contract_data.SHIPPED_IDS))


class ShippedIdTests(unittest.TestCase):
    def test_every_shipped_id_is_registered_or_folded(self):
        self.assertEqual(unaccounted(contract_data.SHIPPED_IDS, DEFAULT,
                                     contract_data.RENAMED), [])

    def test_the_check_fails_an_id_that_is_neither(self):
        shipped = contract_data.SHIPPED_IDS + ("never/registered-anywhere",)
        self.assertEqual(unaccounted(shipped, DEFAULT, contract_data.RENAMED),
                         ["never/registered-anywhere"])

    def test_the_check_passes_an_id_the_fold_map_carries(self):
        shipped = ("old/gone",)
        self.assertEqual(unaccounted(shipped, DEFAULT, {"old/gone": DEFAULT.ids()[0]}), [])

    def test_every_default_detector_is_on_the_shipped_list(self):
        self.assertEqual([did for did in DEFAULT.ids()
                          if did not in contract_data.SHIPPED_IDS], [])

    def test_every_shipped_rename_lands_on_a_registered_detector(self):
        self.assertEqual([new for new in fold_map(contract_data.RENAMED).values()
                          if new not in DEFAULT], [])


if __name__ == "__main__":
    unittest.main()
