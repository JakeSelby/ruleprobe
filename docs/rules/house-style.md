---
rule: house-style
detector:
  id: house-style/sudo-install
  event: tool_use
  when:
    command: {starts_with: [sudo, pip]}
---

# House style

Install with `uv`, never with `sudo pip`: a system Python that a project has written into
is a machine nobody can reproduce.
