# SPDX-License-Identifier: MIT
"""The data the versioned contract ships: the fold map and every detector id ever shipped.

Both are Python literals and nothing else, never a file read beside this module, so they load
through the import system the same way from a directory, a wheel or a zip on `sys.path`, and
building a `Registry` reads no file. `tests/test_contract_data.py` holds the module to that.

A release that renames a shipped detector adds `old_id: new_id` to `RENAMED` in the same
change, and a release that ships a new detector, in `DEFAULT` or in the catalog
(`ruleprobe/detectors/catalog.py`), adds its id to `SHIPPED_IDS`. An id is never
removed from either: a ledger written under any earlier release still holds it.
"""

#: `{retired_id: successor_id}` for every shipped detector that has been renamed. Read through
#: `ruleprobe.registry.fold_map`, which merges a consumer's own `Registry(renamed=)` over it.
RENAMED = {}

#: Every detector id any release has shipped in `DEFAULT` or the catalog, in the order it
#: first shipped.
SHIPPED_IDS = (
    "transcript-hygiene/whole-file-cat",
    "transcript-hygiene/unfiltered-find",
    "verification/no-verify",
    "secrets/secret-in-write",
    "cache-hygiene/compact",
    "cache-hygiene/model-switch",
    "testing/no-test-run",
    "git-safety/force-push-default",
    "package-manager/pip-install",
    "commits/non-conventional-subject",
    "secrets/secret-file-add",
)
