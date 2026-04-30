# 0013. Fig. 6c sum(DMs) ≠ cap_loss handling — T4 redesign as cap_loss self-consistency

Date: 2026-04-28
Status: accepted

## Context

The original v0.5.2 IC-analysis task package §4.1 included acceptance test T4: `sum(DMs) ≈ cap_loss within 10%`. The reasoning was a physical-intuition guess that degradation modes (LLI + LAM_PE + LAM_NE) should approximately conserve to measured capacity loss.

When subphase 4 implemented T4, three test cases produced ratios `sum(DMs)/cap_loss` of 1.66, 2.29, and 2.97 — 2× to 3× excess, far outside any plausible 10% tolerance. The test was either wrong or the forward model was wrong.

User-side check against Mmeka 2025 paper §"Cycle degradation" at 143 EFC yielded the resolution:

```
sum(DMs) = LAM_PE 0.08 + LAM_NE 0.04 + LLI 0.13 = 0.25 Ah
measured cap_loss = 0.11 Ah → ratio 2.27
```

Paper text explicitly warns:

> "the sum of the degradation modes (0.25 Ah) exceeds the measured capacity loss at the full-cell level (Fig. 6a) ... highlighting the nonlinear relationship between various degradation modes and overall capacity loss."

The implementation matched paper-measured ratios. The forward model was correct; the task-package T4 was a physical-intuition error.

## Decision

**T4 is redesigned as cap_loss self-consistency**, not sum conservation:

- Invert the IC analysis to recover `(LLI, LAM_PE, LAM_NE)`.
- Run the same forward model on those recovered values to produce `cap_loss_hat`.
- Compare `cap_loss_hat` to `cap_loss_truth` (also obtained from the same forward model on the ground-truth degradation tuple).
- Pass criterion: relative error < 10%.

The self-consistency criterion catches "DMs internal-allocation errors" (the inversion finding the wrong split between LLI and LAM modes) more precisely than a sum-equality test would, and does not overlap semantically with T2 (single-point parameter accuracy) or T3 (covariance structure).

**The Fig. 6c phenomenon itself** ("sum(DMs) ≠ cap_loss is a real nonlinear-coupling effect") is captured at multiple layers:

- Test docstring in `tests/test_ic_analysis.py` cites the paper finding so future readers don't reattempt the sum-conservation test.
- A `critical_review_findings::N3` entry in `PARAMETERS.json` documents the nonlinearity as a known scope-of-validity property. (The N3 entry was deferred at v0.5.2 — the IC-analysis task package was scoped to not modify `critical_review_findings` — and was added in the v0.5.3 docs patch on 2026-04-29; see CHANGELOG.)
- `docs/CRITICAL_REVIEW.md §二` mirrors the N3 entry in narrative form.

## Alternatives

- **Keep T4 as sum equality with a relaxed 300% tolerance** — rejected. Hides the nonlinearity rather than testing self-consistency, and a 300% tolerance is so loose it would catch almost any error.
- **Drop T4 entirely** — rejected. The IC-analysis recovery path needs *some* end-to-end consistency check; sum conservation was the wrong one but not the only candidate.
- **Test against Fig. 6c data points directly** — rejected as too specific. The paper's exact (EFC, sum, cap_loss) trio is one data point; the self-consistency test is general across all RPTs, including those with no published reference.

## Consequences

Positive:
- T4 now genuinely tests inversion correctness rather than encoding a physical-intuition assumption.
- Future IC-analysis runs have a sharper failure signal: a self-consistency violation indicates the inversion's internal allocation is wrong, not that physics is misunderstood.
- Documenting the Fig. 6c phenomenon at three layers (test, PARAMETERS.json::N3, CRITICAL_REVIEW.md §二) makes it discoverable from any direction — code, data layer, narrative.

Negative:
- The redesigned T4 does not catch a hypothetical bug where the forward model's nonlinearity itself is wrong (since it's used on both sides of the comparison). Such a bug would need an independent test against paper measurements directly.
- Future readers may rediscover the sum-conservation intuition and need the test docstring + N3 entry to redirect them. Defense-in-depth is the price of the layered documentation.

## References

- `tests/test_ic_analysis.py` T4 (cap_loss self-consistency form)
- `docs/PARAMETERS.json::critical_review_findings::N3` (added in v0.5.3 docs patch, 2026-04-29)
- `docs/CRITICAL_REVIEW.md §二` N3 entry
- `docs/legacy/MIGRATION_NOTES.md` §20.6 (T4 blocking + paper Fig. 6c resolution)
- `docs/legacy/MIGRATION_NOTES.md` §20.7.2 (deferred N3 critical_review_findings upgrade rationale)
- Mmeka, Dubarry, Bessler 2025, J. Electrochem. Soc. 172:080538, Fig. 6a/6c, §"Cycle degradation"
- Tag: `release/v0.5.2-ic-analysis`, `docs/v0.5.3-ic-methodology-review`
