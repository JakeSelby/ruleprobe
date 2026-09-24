# SPDX-License-Identifier: MIT
"""The registry: what it accepts, what it refuses, how a gate reads, and the two seams
third-party detectors arrive through."""
import contextlib
import importlib.util
import os
import sys
import unittest
from unittest import mock

from corpus import bash, say
from ruleprobe import (DEFAULT, Detector, Registry, contract_data, from_spec,
                       register_compiler, run)
from ruleprobe.registry import COMPILERS, fold_map


def never(events, ctx):
    return []


def always(events, ctx):
    return [(1, None)]


class DetectorTests(unittest.TestCase):
    def test_a_detector_with_no_gate_is_always_on(self):
        self.assertTrue(Detector("a/b", "a", "session", never).enabled(None))
        self.assertTrue(Detector("a/b", "a", "session", never).enabled({"commits": "off"}))

    def test_a_dimension_gate_needs_the_dimension_set_and_not_off(self):
        gated = Detector("a/b", "a", "session", never, gate=("commits", None))
        self.assertFalse(gated.enabled(None))
        self.assertFalse(gated.enabled({"commits": "off"}))
        self.assertTrue(gated.enabled({"commits": "conventional"}))

    def test_a_gate_may_name_the_variants_it_wants(self):
        gated = Detector("a/b", "a", "session", never, gate=("commits", ("attributed",)))
        self.assertFalse(gated.enabled({"commits": "conventional"}))
        self.assertTrue(gated.enabled({"commits": "attributed"}))

    def test_a_gate_may_be_a_callable(self):
        gated = Detector("a/b", "a", "session", never,
                         gate=lambda stances: stances.get("voice") == "terse")
        self.assertFalse(gated.enabled({"voice": "long"}))
        self.assertTrue(gated.enabled({"voice": "terse"}))

    def test_a_gated_detector_is_skipped_by_run(self):
        registry = Registry([Detector("a/gated", "a", "session", always,
                                      gate=("commits", None))])
        self.assertEqual(run([bash("ls")], registry=registry), {})
        self.assertIn("a/gated", run([bash("ls")], {"commits": "conventional"},
                                     registry=registry))


class RegistryTests(unittest.TestCase):
    def test_a_registered_detector_is_found_by_id(self):
        registry = Registry()
        detector = registry.add(Detector("a/b", "a", "session", never))
        self.assertIs(registry.get("a/b"), detector)
        self.assertIn("a/b", registry)
        self.assertEqual(len(registry), 1)

    def test_a_second_registration_replaces_in_place_rather_than_reordering(self):
        registry = Registry([Detector("a/b", "a", "session", never),
                             Detector("c/d", "c", "session", never)])
        registry.add(Detector("a/b", "a", "bash", always))
        self.assertEqual(registry.ids(), ["a/b", "c/d"])
        self.assertEqual(registry.get("a/b").event, "bash")

    def test_a_malformed_detector_is_refused_at_registration(self):
        registry = Registry()
        for bad in (Detector("", "a", "session", never),
                    Detector("a/b", "a/c", "session", never),
                    Detector("a/b", "a", "nonsense", never)):
            with self.assertRaises(ValueError):
                registry.add(bad)
        with self.assertRaises(TypeError):
            registry.add("not a detector")
        with self.assertRaises(TypeError):
            registry.add(Detector("a/b", "a", "session", "not callable"))

    def test_a_rename_is_recorded_and_not_applied_to_the_registry(self):
        registry = Registry([Detector("a/new", "a", "session", never)])
        registry.rename("a/old", "a/new")
        self.assertEqual(registry.renamed, {"a/old": "a/new"})
        self.assertNotIn("a/old", registry)

    def test_a_copy_carries_the_detectors_and_the_renames_and_is_independent(self):
        registry = Registry([Detector("a/b", "a", "session", never)], {"a/x": "a/b"})
        clone = registry.copy()
        clone.add(Detector("c/d", "c", "session", never))
        self.assertEqual(registry.ids(), ["a/b"])
        self.assertEqual(clone.renamed, {"a/x": "a/b"})

    def test_removing_a_detector_takes_it_out_of_both_views(self):
        registry = Registry([Detector("a/b", "a", "session", never)])
        registry.remove("a/b")
        self.assertEqual(registry.ids(), [])
        self.assertIsNone(registry.get("a/b"))

    def test_from_entry_points_starts_from_the_shipped_registry(self):
        # Nothing on this path advertises the group, so the result is the six and no more.
        registry = Registry.from_entry_points("ruleprobe.detectors.nothing-advertises-this")
        self.assertEqual(registry.ids(), DEFAULT.ids())
        self.assertIsNot(registry, DEFAULT)

    def test_from_entry_points_may_start_from_a_registry_of_your_own(self):
        base = Registry([Detector("a/b", "a", "session", never)])
        registry = Registry.from_entry_points("ruleprobe.detectors.nothing", base=base)
        self.assertEqual(registry.ids(), ["a/b"])


class DeclarativeSeamTests(unittest.TestCase):
    """Declarative detectors are a later story. What this one owes them is the seam."""

    def tearDown(self):
        COMPILERS.pop("test-shape", None)

    def test_a_spec_with_no_compiler_says_so_rather_than_failing_quietly(self):
        with self.assertRaises(NotImplementedError):
            from_spec({"kind": "regex", "pattern": "x"})

    def test_a_registered_compiler_turns_a_spec_into_a_working_detector(self):
        register_compiler("test-shape",
                          lambda spec: Detector(spec["id"], spec["rule"], "session", always))
        detector = from_spec({"kind": "test-shape", "id": "a/b", "rule": "a"})
        registry = Registry([detector])
        self.assertIn("a/b", run([say("anything")], registry=registry))


#: The recorders of the `traced_file_reads` blocks now open. An audit hook cannot be removed,
#: so one is installed on first use and records only while a block is open.
_RECORDERS = []
_AUDITED = ("open", "os.listdir", "os.scandir")
_HOOK = []


def _audit(event, args):
    if _RECORDERS and event in _AUDITED:
        for recorder in _RECORDERS:
            recorder.append((event, args[0] if args else None))


@contextlib.contextmanager
def traced_file_reads():
    """Record every file the block opens and every directory it lists, through the
    interpreter's audit events: the import system, `importlib.resources` and zipimport
    raise `open` as `open()` does."""
    if not _HOOK:
        sys.addaudithook(_audit)
        _HOOK.append(_audit)
    seen = []
    _RECORDERS.append(seen)
    try:
        yield seen
    finally:
        _RECORDERS.remove(seen)


class FoldMapTests(unittest.TestCase):
    """The one function every read folds renamed ids through."""

    def test_the_shipped_map_applies_with_no_map_of_your_own(self):
        with mock.patch.dict(contract_data.RENAMED, {"a/old": "a/one"}):
            self.assertEqual(Registry().fold_map(), {"a/old": "a/one"})
            self.assertEqual(Registry().renamed, {})

    def test_the_consumer_wins_a_clash_with_the_shipped_map(self):
        with mock.patch.dict(contract_data.RENAMED, {"a/old": "a/one"}):
            registry = Registry(renamed={"a/old": "a/two"})
            self.assertEqual(registry.fold_map(), {"a/old": "a/two"})

    def test_a_chain_resolves_to_its_end_across_both_maps(self):
        with mock.patch.dict(contract_data.RENAMED, {"a/x": "a/y"}):
            registry = Registry(renamed={"a/y": "a/z", "a/w": "a/x"})
            self.assertEqual(registry.fold_map(), {"a/w": "a/z", "a/x": "a/z", "a/y": "a/z"})

    def test_a_cycle_raises_when_the_registry_is_built(self):
        with self.assertRaises(ValueError):
            Registry(renamed={"a/x": "a/y", "a/y": "a/x"})
        with self.assertRaises(ValueError):
            Registry(renamed={"a/w": "a/x", "a/x": "a/y", "a/y": "a/x"})

    def test_a_cycle_through_the_shipped_map_raises_when_the_registry_is_built(self):
        with mock.patch.dict(contract_data.RENAMED, {"a/x": "a/y"}):
            with self.assertRaises(ValueError):
                Registry(renamed={"a/y": "a/x"})

    def test_a_rename_that_closes_a_cycle_raises_and_changes_nothing(self):
        registry = Registry([Detector("a/x", "a", "session", never)], {"a/x": "a/y"})
        with self.assertRaises(ValueError):
            registry.rename("a/y", "a/x")
        self.assertEqual(registry.renamed, {"a/x": "a/y"})
        self.assertIn("a/x", registry)

    def test_an_id_renamed_to_itself_is_no_rename_and_no_cycle(self):
        registry = Registry([Detector("a/x", "a", "session", never)])
        registry.rename("a/x", "a/x")
        self.assertEqual(registry.fold_map(), {})
        self.assertIn("a/x", registry)

    def test_the_consumer_may_undo_a_shipped_rename_and_the_map_shows_it(self):
        with mock.patch.dict(contract_data.RENAMED, {"a/old": "a/one", "a/gone": "a/old"}):
            self.assertEqual(Registry(renamed={"a/old": "a/old"}).fold_map(),
                             {"a/gone": "a/old", "a/old": "a/old"})

    def test_a_non_string_id_is_refused_by_name(self):
        for bad in ({1: "a/x"}, {"a/x": None}):
            with self.subTest(renamed=bad):
                with self.assertRaisesRegex(ValueError, "fold map ids are strings"):
                    Registry(renamed=bad)

    def test_a_cycle_names_each_edge_and_whose_it_is(self):
        with mock.patch.dict(contract_data.RENAMED, {"a/x": "a/y"}):
            with self.assertRaises(ValueError) as caught:
                Registry(renamed={"a/y": "a/x"})
        self.assertIn("a/x -> a/y (shipped)", str(caught.exception))
        self.assertIn("a/y -> a/x (consumer)", str(caught.exception))

    def test_the_default_registry_folds_the_shipped_map_and_holds_no_map_of_its_own(self):
        self.assertEqual(DEFAULT.renamed, {})
        self.assertEqual(DEFAULT.fold_map(), fold_map(contract_data.RENAMED))


class NoFileReadTests(unittest.TestCase):
    def test_building_copying_renaming_and_folding_a_registry_reads_no_file(self):
        with traced_file_reads() as seen:
            registry = Registry([Detector("a/one", "a", "session", never)], {"a/old": "a/one"})
            registry.copy().rename("a/older", "a/old")
            registry.fold_map()
            DEFAULT.copy().fold_map()
        self.assertEqual(seen, [])

    def test_nested_traces_each_see_a_read(self):
        with traced_file_reads() as outer:
            with traced_file_reads() as inner:
                os.listdir(os.path.dirname(__file__))
        self.assertEqual([name for name, _path in outer], ["os.listdir"])
        self.assertEqual(outer, inner)

    def test_the_trace_sees_a_read(self):
        with traced_file_reads() as seen:
            with open(__file__, encoding="utf-8") as handle:
                handle.readline()
            os.listdir(os.path.dirname(__file__))
            spec = importlib.util.spec_from_file_location("_traced_probe", __file__)
            spec.loader.get_data(__file__)
        self.assertEqual([name for name, _path in seen], ["open", "os.listdir", "open"])
        self.assertEqual(seen[-1][1], __file__)


if __name__ == "__main__":
    unittest.main()
