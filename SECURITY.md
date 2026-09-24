# Security policy

## What counts as a security issue here

ruleprobe reads transcripts that can contain anything an agent saw: file contents, commands,
credentials. It promises to send nothing and ask no model. `ruleprobe label` is the one
command that writes, and only under the corpus directory it is given; every other command
writes nothing to disk. Report privately if you find:

- Any path by which `ruleprobe report`, `explain` or `corpus` sends data over a network, runs a
  command from a transcript, or writes a file.
- Any path by which `ruleprobe label` writes outside the directory it is given, sends data over
  a network, or writes a secret shape its redaction should have removed.
- A crafted transcript or detector file that makes the parser execute code, read outside the
  paths it was given, or hang indefinitely.
- Report or `--json` output that prints a secret a detector matched in full, rather than only
  the fact that it matched.
- A credential, real transcript content or personal data anywhere in the tree or its history,
  including the shipped corpus.

## Supported versions

Only `main` and the latest release on PyPI receive fixes.

## How to report

Use GitHub's private vulnerability reporting for this repository (the **Security** tab, then
**Report a vulnerability**). Do not open a public issue for anything that could be exploited.
You will get an acknowledgement within a week and a fix or a decision within thirty days.

## Defences already in place

The package has no runtime dependency, so its supply chain is the standard library. Releases
are published from a tag by GitHub Actions through PyPI trusted publishing, with no stored
upload token. GitHub secret scanning with push protection is enabled on the repository, and
the corpus is synthetic by rule.
