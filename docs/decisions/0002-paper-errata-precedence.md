# 0002. paper_errata field precedence over paper text

Date: 2026-04-20
Status: accepted

## Context

The Mmeka 2025 paper (J. Electrochem. Soc. 172:080538) contains at least two confirmed errors in its parameter tables and prose:

1. **`k_SEI_cal` typo in Table Ib**: printed as `4.2 × 10⁻²² A²·s`, but the MATLAB source code on Zenodo uses `0.0419625 ≈ 4.2 × 10⁻² A²·s`. Dimensional analysis of Eq. 36, MATLAB code verification, and forward simulation reproducing Fig. 4c all confirm the code value is correct. The typo is consistent with `10⁻²` being typeset such that the `²` was duplicated into `⁻²²`.
2. **`k_SEI,cyc` mislabeled in §10 prose** as a calendar parameter, contradicting the paper's own Tables (which are correct).

Without an authoritative mechanism to override paper text, downstream users who consult the paper directly would inherit broken parameters. A user pulling `4.2 × 10⁻²² A²·s` would compute SEI growth rates 20 orders of magnitude too small.

## Decision

`docs/PARAMETERS.json` carries a `paper_errata` field on each parameter entry. The field's contents take precedence over any quotation from the paper text. Code, narrative MD, and any other consumer must consult PARAMETERS.json's `paper_errata` field before using a paper-cited value.

`docs/CRITICAL_REVIEW.md §一` (paper errata) is the human-readable companion: it documents each erratum's discovery method (dimensional analysis, code cross-check, forward simulation) so future maintainers can extend the registry with confidence.

Code-side enforcement: the affected dataclasses (e.g., `SEIParameters.k_cal`) carry docstring notes pointing to the erratum. The fact-layer-first rule (ADR-0001) means new errata land in PARAMETERS.json before any narrative or code change.

## Alternatives

- **Annotate the paper PDF** — rejected. Annotations don't propagate to programmatic consumers and aren't reviewable in git.
- **Hard-code corrected values without flagging** — rejected. Future maintainers would have no signal that the code value disagrees with the paper. Silent divergence is the original problem.
- **Maintain a separate `errata.md`** — rejected as an alternative; CRITICAL_REVIEW.md absorbs this role and ties errata to the broader scope-of-validity cards.

## Consequences

Positive:
- A reviewer who spots a future paper-vs-code discrepancy has a defined channel: open an erratum entry, write up the dimensional/empirical justification, propagate.
- Tooling can validate that all `paper_errata` entries are referenced from at least one `critical_review_findings` row, catching dangling errata.

Negative:
- Adds reviewer burden: each erratum must include a justification (dimensional analysis, code cross-check, or forward simulation).
- Possible confusion when paper authors publish an errata document themselves; the registry must distinguish "we found this" from "authors confirmed this".

## References

- `docs/PARAMETERS.json` parameter entries with `paper_errata` field (e.g., `k_SEI_cal`)
- `docs/CRITICAL_REVIEW.md §一` paper errata section
- `libquiv_aging/aging_kinetics.py::SEIParameters.k_cal` docstring
- Mmeka, Dubarry, Bessler 2025, J. Electrochem. Soc. 172:080538, Table Ib + §10
- Zenodo MATLAB source: 10.5281/zenodo.15833031
