# Mockingbird project rules

- Before planning verification, reviewing coverage, or validating consequential
  changes, read and apply `.skills/design-verification/SKILL.md`. Derive cases
  from requirements and invariants, and report failures and unverified gaps.

- Before changing runtime code, tests, examples, dependencies, or test tooling,
  read and apply `.skills/verify-python-compatibility/SKILL.md`. Verification in
  both the normal and shared-Python workaround environments is a completion
  condition. Report any environment that could not be verified explicitly.
- For CLI, lifecycle, tutorial, error, progress, or status changes, also read and
  apply `.skills/review-cli-ux/SKILL.md`.
- Keep repository documentation and skills in English.
- Commit skill/project-rule changes separately from product and documentation
  changes. Do not assume every agent discovers `.skills/` automatically; use
  the explicit references above.

