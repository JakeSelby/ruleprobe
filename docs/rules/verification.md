---
rule: verification
detector:
  id: verification/no-test-run
  event: session
  when:
    absent:
      of:
        command: {name: [pytest, tox, nox]}
      scope: session
---

# Verification

Run the tests before you say it works. A session that changed code and never ran a test is
the shape this measures.
