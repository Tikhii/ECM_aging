# 0003. R5 four-step protocol (scan → confirm → edit → verify) with strict no-auto-git clause

Date: 2026-04-21
Status: accepted

## Context

Two structural incidents shaped R5:

1. **FIT-3 §-missing event (2026-04-21)**: A structural change to PARAMETERS.json removed a fit-step section, but several derived MD documents continued to reference the removed FIT-3 by name. The mismatch only surfaced during an unrelated audit. Root cause: no protocol required cross-document scanning before structural edits.

2. **2026-04-23 v0.2.2 P0 incident**: A `conda env export` was run without first activating the target environment, dumping the `base` environment into `environment.yml`. A separate `conda env export --no-builds > environment-frozen.yml` similarly captured the wrong env. Two simultaneous bad states caused a downstream agent (Claude Code) to misjudge "environment.yml is a pre-existing legacy error" — judgment based on the corrupted working tree rather than HEAD. Recovery required `git restore environment.yml` and re-export from the correctly-activated env. The agent's report had been used as ground truth for a commit plan; only `git status` revealed the working-tree contradiction.

R5 emerged from incident 1; the verify-stage git clause was widened after incident 2.

## Decision

**R5 protocol** governs structural edits to `PARAMETERS.json` or any `docs/*.md` (adding/removing sections, parameters, FIT steps, EXP experiments). Four mandatory steps:

1. **Scan** (pre-edit): grep the docs/ directory for affected keywords (parameter name in snake_case + LaTeX; FIT-N + its EXP-* inputs; EXP-N + its parameter outputs). List each match with file path and line number.
2. **Confirm**: present scan results to the user — files needing change vs files merely mentioning. Wait for user confirmation of edit scope.
3. **Edit**: edit fact layer first (PARAMETERS.json), then narrative (MD), then code. Order follows R1.
4. **Verify**: re-grep the same keywords; run `pytest tests/ -v`; emit `git diff --stat`. **Forbidden: auto `git add` / `git commit` / `git tag`.** Staging is a semantic choice (the human approves), commit is the final-record decision, tag is the release-readiness signal — all three require explicit human authorization.

The git clause was widened in v0.2.2 from the initial "no auto commit" to "no auto add / commit / tag" after incident 2 demonstrated that auto-staging during an audit could obscure working-tree state mismatches.

**Proposed-but-unimplemented enhancement** (recorded for future reference, not currently in R5 text): the v0.5.1 patch (ADR see CHANGELOG 2026-04-26) identified that R5's scan stage should explicitly enumerate "semantic radiation targets" — when modifying `fit_steps::FIT-X::requires_experiments`, scan must include all derived fields (`experiments::EXP-old::outputs`, `parameters::*::experiment`, `minimal_viable_experiments::*`) that reference the changed structure. This proposal awaits a future docs/CLAUDE.md governance patch.

## Alternatives

- **Edit-first, verify-after** (no scan) — rejected. The FIT-3 incident demonstrated this approach's failure mode: derived references stay broken until accidental discovery.
- **Allow auto-staging in verify stage** — rejected after the v0.2.2 incident. Staging conflates the agent's edit boundary with the human's commit boundary; under simultaneous-bad-state conditions, conflation prevents the human from observing the contradictory working tree.
- **Enforce by CI hook rather than protocol** — partially complementary, not a replacement. CI runs after the agent has already produced changes; pre-edit scanning has no CI analog.

## Consequences

Positive:
- Cross-document consistency becomes a procedural requirement rather than a vigilance task.
- The verify-stage git clause forced a clean separation: agents propose edits, humans authorize git transitions. This separation has prevented at least two subsequent near-misses (recorded in `docs/legacy/MIGRATION_NOTES.md` §十一 and follow-on chapters).
- Provides a clear rubric for what counts as a "structural" change (adding/removing sections vs editing values within an existing structure).

Negative:
- Adds a confirmation round-trip on every structural edit, which is friction. The friction is intentional (it forces explicit scope agreement) but slows iteration.
- Scanning relies on grep keyword choice; subtle dependencies (e.g., a fit step referenced by FIT-N notation in one place and §SOP-N notation in another) can escape scan if keywords are not chosen carefully. The "semantic radiation" enhancement proposed above attempts to address this systematically.

## References

- `docs/CLAUDE.md` R5 rule text (canonical)
- `docs/CLAUDE.md` 版本纪要 entries 2026-04-21 (R5 birth) and 2026-04-23 (R5 git-clause widening)
- `docs/legacy/MIGRATION_NOTES.md` §十一 (P0 incident detail and meta lessons)
- `docs/legacy/MIGRATION_NOTES.md` §十九.2 (semantic-radiation R5 enhancement proposal, not yet institutionalized)
