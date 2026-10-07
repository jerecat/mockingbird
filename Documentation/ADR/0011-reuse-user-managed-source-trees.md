# ADR 0011: Reuse user-managed source trees

Status: accepted, 2026-10-07

## Context

Users edit sources after prepare, including during long runs. Repeating prepare
must neither discard these edits nor reject a working tree because it is dirty.
Mockingbird does not implement version control or track editing history.

## Decision

- If no checkout exists, Git/SVN providers acquire the requested URL/revision.
  A non-empty directory without the expected checkout metadata is left untouched
  and reported as an error; it cannot safely be treated as a checkout.
- If a checkout exists, reuse it as-is. Git does not fetch, checkout, reset,
  clean or change remotes. SVN does not switch or update. No dirty gate is added.
- Evidence records `materialization: created` or `reused`, plus the actual local
  revision observed at prepare time in `resolved_revision`. The requested URL
  and revision remain configuration intent, not a claim that reused content
  matches them. Provider metadata records the local origin/working-copy URL.
- To change revisions, users operate Git/SVN themselves or choose a new
  workspace. A changed URL/revision in YAML does not modify an existing checkout.
- No editing diffs, content hashes, dirty flags, or per-Job source monitoring are
  collected. Source edits do not block run. Run copies prepare-time evidence;
  it does not claim to have captured the source contents used by each Job.

## Consequences

Repeated prepare is non-destructive to existing Git/SVN working trees and needs
no remote connection to reuse them. Existing local branches, index changes,
untracked files and ignored build outputs are preserved.

Revision evidence identifies a baseline, not a content snapshot. In particular,
SVN records the working-copy root revision; mixed revisions and local edits are
not represented as a reproducible tree. Users who need reproducibility manage
commits, revisions and source stability through their version control workflow.

The incomplete-prepare marker from ADR 0010 still guards failed preparation.
Context and plan remain frozen metadata/contracts, while source trees remain
user-managed and mutable. The rule applies to built-in Git/SVN providers; custom
SourceProviders must document their own materialisation semantics.
