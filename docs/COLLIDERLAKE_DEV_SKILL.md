---
name: colliderlake-dev
description: Operating manual for building ColliderLake 2.0 — a laptop-scale CMS Open Data lakehouse (uproot/awkward → Parquet medallion layers → DuckDB, orchestrated by Airflow, fitted with iminuit). Use this skill for ANY work in the ColliderLake repo — writing pipeline code, selection configs, fitting/statistics, DAGs, tests, CI, or docs — even for small edits. It encodes the physics correctness rules, naming conventions, and definition-of-done that generic coding knowledge will get wrong.
---

# ColliderLake 2.0 — Agent Operating Manual

You are building a physics research platform whose output will be published on
arXiv. Correctness rules here are non-negotiable: a subtle physics bug produces
plausible-looking wrong results that survive until a reviewer finds them.

## Read first, always
1. `docs/ARCHITECTURE_2.0.md` — the authoritative design (layers, schemas,
   configs, trade-offs). Do not contradict it; if a task seems to require
   deviating, STOP and ask the user instead of improvising.
2. This file — conventions and physics rules.
3. The existing 1.0 code — extend and refactor incrementally; never rewrite
   wholesale. Preserve the Windows JDK/winutils handling.

## Prime directives
- **Configuration over code.** Dataset URLs, cuts, trigger paths, fit windows,
  and model choices live in `configs/*.yaml`. If you hardcode a cut, a GeV
  value, or a file path in Python, you have made an error. The only physics
  constants allowed in code are in `src/physics/pdg.py`.
- **Trigger flags are silver data; trigger cuts are gold decisions.** Never
  filter on any HLT path in bronze or silver. This rule exists because 1.0
  filtered HLT_IsoMu24 at silver and silently destroyed all quarkonium physics.
- **Airflow-free core.** All pipeline logic lives in plain functions under
  `src/`, callable from the CLI (`colliderlake run --stage ...`). DAG tasks in
  `dags/` are thin wrappers. `src/` must never import Airflow.
- **No hand-typed physics numbers in outputs.** Every number in a figure,
  table, or the paper is generated from `results/fits.parquet` or
  `src/physics/pdg.py`. If a docstring or README needs a mass value, reference
  PDG constants programmatically or mark it clearly as illustrative.
- **Scope guard.** Nothing beyond the `gold.dimuon` contract (anomaly
  detection, GNNs, DIAMOND layers) gets implemented before the RESONANCE
  preprint is done. If asked, build only the stable gold contract.

## Environment
- Python **3.11** (pinned — PySpark compatibility; do not "upgrade").
- Core deps: `uproot`, `awkward`, `pyarrow`, `pyspark`, `duckdb`, `iminuit`,
  `numpy`, `hist`, `matplotlib`, `pyyaml`, `typer` (CLI), `pytest`.
- Env managed by `uv` with a lockfile. Canonical execution = Docker Compose;
  local Windows dev path retained for iteration.
- Data paths: `data/{raw,bronze,silver,gold,results}` — Hive-partitioned by
  `dataset=<id>`, gold adds `analysis=<name>`. Never write outside `data/`
  staging conventions: write to `<path>.staging` then atomic rename.

## Naming (locked decisions — do not bikeshed)
- DuckDB catalog: **`colliderlake.db`** with schemas `bronze`, `silver`,
  `gold`, `results`. (1.0's `muon_db` is legacy; migrate, don't extend.)
- Datasets: `run2012bc_doublemuparked` (record 12341), `run2016h_singlemuon`
  (record 30563).
- Selection configs produce a `selection_id` = first 8 hex chars of the SHA-256
  of the resolved YAML. Stamp it on every gold row.
- DAGs: `resonance_2012`, `resonance_2016`, `resonance_paper`.

## Physics correctness rules

### Invariant mass (the single most important calculation)
Use the full 4-vector sum with the muon mass, in **float64**:

```
E_i  = sqrt(pt_i^2 * cosh(eta_i)^2 + m_mu^2)
px_i = pt_i * cos(phi_i);  py_i = pt_i * sin(phi_i);  pz_i = pt_i * sinh(eta_i)
m^2  = (E1+E2)^2 - (px1+px2)^2 - (py1+py2)^2 - (pz1+pz2)^2
mass = sqrt(max(m^2, 0))
```

`m_mu = 0.1056583755` GeV. The massless approximation
`m^2 = 2 pt1 pt2 (cosh(eta1-eta2) - cos(phi1-phi2))` is acceptable ONLY as a
cross-check in tests, never in the pipeline (it biases the J/psi region).

### PDG reference values (source of truth: `src/physics/pdg.py`)
| Particle | Mass (GeV) |
|---|---|
| mu        | 0.1056583755 |
| J/psi     | 3.0969 |
| psi(2S)   | 3.6861 |
| Upsilon(1S) | 9.4603 |
| Upsilon(2S) | 10.0233 |
| Upsilon(3S) | 10.3552 |
| Z         | 91.1876 |

### Selection rules
- Pairing: all opposite-charge muon pairs per event; flag the leading
  (highest sum-pT) pair. Same-charge pairs are kept ONLY behind an explicit
  `same_charge_control: true` config flag (background studies).
- 2012 ladder selection is LOOSE: `pt_min: 3.0`, `|eta| < 2.4`, no HLT
  requirement, no isolation cut. Tight cuts here silently destroy the physics
  — if a review suggests "tightening for quality," refuse and cite this rule.
- 2016 Z selection: `pt_min: 20`, tight ID, `iso < 0.15`, `HLT_IsoMu24`,
  golden JSON certification (portal record 14220) applied at silver.
- Sanity bounds enforced by DQ gates: `pt > 0`, `|eta| <= 2.4`, `iso >= 0`,
  `mass > 2*m_mu`.

### Known gotchas (do not "fix" these as bugs)
- **~30 GeV structure in the 2012 spectrum is a trigger turn-on artifact,
  not a resonance.** Exclude from fit windows; never fit or report it as a peak.
- **Upsilon 1S/2S/3S partially merge at NanoAOD resolution.** Fit with a
  triple-Gaussian whose mass SPLITTINGS are fixed to PDG differences; float a
  common offset and shared width scale. Report 1S; 2S/3S are constrained.
- **NanoAOD has reduced numerical precision upstream.** Do not chase
  sub-MeV discrepancies; statistical uncertainty only (no detector
  systematics) — this is a documented limitation, not a defect.
- 2012 reduced dataset is pre-filtered to validated runs — mark
  `certified=true` with provenance note; do NOT try to apply a 2016 golden
  JSON to it.

## Fitting module rules (`src/physics/fitting.py`, `models.py`)
- iminuit **binned extended maximum-likelihood** fits per resonance window,
  driven entirely by `configs/fits/*.yaml`.
- Model registry (string → callable): signals `gaussian`, `double_gaussian`,
  `triple_gaussian`, `crystal_ball`, `breit_wigner_conv_gaussian`;
  backgrounds `exponential`, `chebyshev1`, `chebyshev2`.
- Every fit must report: fitted mass ± stat uncertainty, width, signal yield,
  chi2/ndf, convergence status (`Minuit.fmin.is_valid`), and
  `delta_pdg_sigma = (m_fit - m_PDG) / sigma_fit`.
- A fit that fails to converge raises — never silently returns last values.
- Persist to `results/fits.parquet` + JSON sidecar. Figures read from these
  files only.

## Data quality gates (every layer boundary)
Implement in `src/dq/`; called by both CLI and DAGs; failure = hard stop.
- Structural: nonzero rows, no nulls in key columns
  `(dataset_id, run, luminosityBlock, event)`, no duplicate event keys within
  a dataset, row count within ±5% of the previous successful run (skip on
  first run).
- Physics: the sanity bounds above.
- Certification: certified fraction within the expected band (config value).
- Emit `results/dq_report.json` (append per-run entries).

## Testing & verification (definition of done)
A stage is done only when:
1. **Unit tests pass**, including pinned physics values: a hand-constructed
   muon pair with known kinematics must yield the expected invariant mass to
   1e-6 GeV; selection YAML round-trips to the same `selection_id`.
2. **Sample-file integration test passes**: the committed/downloaded ~50 MB
   sample (first N events of the 2012 file) runs acquire→fit; the J/psi fit
   must converge with `|m_fit - 3.0969| < 0.05` GeV.
3. **Smoke-test expectations** on full data (manual/CI-nightly):
   J/psi peak visible at 3.10 ± 0.05, Upsilon(1S) at 9.46 ± 0.10,
   Z at 91.2 ± 1.0 GeV. If a peak is missing, the FIRST suspects are
   (a) trigger filtering leaked into silver, (b) pt_min too high,
   (c) same-charge pairs included, (d) massless-approximation used.
4. `ruff` + `mypy` clean; no Airflow imports under `src/` (enforce with a test).
5. DQ gates green and `dq_report.json` updated.

Never mark work complete on "code runs without error" — physics output must
match expectations above.

## Publication hygiene (bake in from the start)
- Every dataset citation carries its portal record number and DOI (from
  `configs/datasets.yaml`).
- The verbatim CMS disclaimer must appear in README and paper: "Neither the
  experiment(s) (CMS) nor CERN endorse any works, scientific or otherwise,
  produced using these data."
- `reana.yaml` mirrors the CLI stages; keep it in sync when stages change.
- README top section reserves a slot for the ladder plot + one-command run:
  `docker compose up pipeline`.

## Task sequencing (when the user says "continue" without specifics)
Phase 0: pdg.py + fitting/models + tests → 2012 acquire/bronze → config-driven
selection engine → golden JSON transform (2016). Phase 1: DAGs. Phase 2: CI +
sample file + reana.yaml. Phase 3: full-stats runs + figures. Consult
`docs/ARCHITECTURE_2.0.md` §5 for component specs before each.

## When uncertain
Physics ambiguity (cut values, fit models, windows, interpretation of a
spectrum feature) → ask the user; do not guess. Engineering ambiguity within
the architecture doc's constraints → decide, note the decision in the PR/commit
message, move on.
