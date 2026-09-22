# SPDX-License-Identifier: MIT
"""The registry: what it accepts, what it refuses, how a gate reads, and the two seams
third-party detectors arrive through."""
import unittest

from corpus import bash, say
from ruleprobe import DEFAULT, Detector, Registry, from_spec, register_compiler, run
from ruleprobe.registry import COMPILERS


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


if __name__ == "__main__":
    unittest.main()
