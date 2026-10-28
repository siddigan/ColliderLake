# M1 resonance ladder result ledger

Evidence snapshot: 2026-10-28. Result files: `fits_core_window.json` and `fits_full_window.json` at repository root. Their common selection ID is `4d93aea9`; core fit ID is `4c5247e8`; full-window fit ID is `2c27a652`. Fit values below are copied from those JSON files. Relative shifts are calculated as `(mass_fit - pdg_mass) / pdg_mass * 100`.

## 1. Fit results

| Resonance | Mass ± stat. unc. (GeV) | PDG (GeV) | Relative shift | Signal yield | χ²/ndf | gof_flag | status | Window (GeV) | selection_id | fit_config_id | Source |
|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|
| J/ψ | 3.0936947635945184 ± 0.000026829486270196767 | 3.0969 | -0.103498% | 3592064.6446233336 | 25581.982374694497/93 | poor | valid | [2.8, 3.4] | 4d93aea9 | 4c5247e8 | `fits_core_window.json` |
| ψ(2S) | 3.6810456012805277 ± 0.00021540225840044336 | 3.6861 | -0.137120% | 153992.0607380972 | 334.8897084604709/95 | ok | valid | [3.4, 3.95] | 4d93aea9 | 4c5247e8 | `fits_core_window.json` |
| Υ(1S) | 9.44680231087616 ± 0.0003537581626547187 | 9.4603 | -0.142677% | 493073.05941462726 | 982.5692279119083/91 | poor | valid | [8.5, 11.5] | 4d93aea9 | 4c5247e8 | `fits_core_window.json` |
| Z, core | 90.8619189594322 ± 0.001916936987804263 | 91.1876 | -0.357155% | 4085844.038696047 | 2813.519779595544/95 | poor | valid | [86, 96] | 4d93aea9 | 4c5247e8 | `fits_core_window.json` |
| Z, full | 90.7207575824507 ± 0.0013623489234788622 | 91.1876 | -0.511958% | 5101067.469697696 | 94860.22803327402/95 | poor | valid | [70, 110] | 4d93aea9 | 2c27a652 | `fits_full_window.json` |

Widths and background yields are present in each cited JSON file and are omitted from this headline table.

## 2. Dataset and provenance

- Dataset: `run2012bc_doublemuparked`; 61,540,413 events (`data/results/dq_report.json`, silver `events_after`).
- Portal record 12341; DOIs `10.7483/OPENDATA.CMS.YLIC.86ZZ`, `10.7483/OPENDATA.CMS.M5AD.Y3V3` (`configs/datasets.yaml`, `data/raw/run2012bc_doublemuparked/MANIFEST.json`).
- ROOT file SHA-256: `f8a9d40dba9ee7131a4110f93b4e14a29f99255cbff777018848477f2f61b00b` (`data/raw/run2012bc_doublemuparked/MANIFEST.json`). Dataset certification is `prefiltered`; the dataset config note describes the reduced 2012 sample as prefiltered to validated runs. (`configs/datasets.yaml`; `docs/COLLIDERLAKE_DEV_SKILL.md`).
- Silver certified fraction: 1.0; eta drop fraction: 0.008019932380431782 (`data/results/dq_report.json`).
- Observed selected-muon maximum: UNRESOLVED — `data/results/dq_report.json` contains only configured `max_muons_per_event: 128`, not the observed maximum or `events_above_half_max` metric.
- Gold pair rows: 83,057,658; pairs/event max 612; p99 10.0; p99.9 24.0; distinct event keys 42,812,309. Both duplicate full-key and duplicate canonical-pair counts are 0 (`docs/audits/CL2.0.7_PRE_GOLD_FIT_AUDIT.md`, §A).

## 3. Performance baseline

| Stage | Duration / rate | Evidence |
|---|---|---|
| Bronze | 14m28s; 79,404 ev/s | UNRESOLVED — `run_full.log` records 14m28s but does not contain 79,404 ev/s; that rate is stated only in the task brief. |
| Silver | 3m06s | `run_full.log` |
| Gold | 14m41s; 179 batches; 83,057,658 rows | `run_gold.log` DONE banner; this local log is untracked. |
| Fit | UNRESOLVED — `data/results/run_summary.txt` reports 4.6s and fit ID `2c27a652`; `run_fit.log` reports 5.2s and fit ID `4c5247e8`. These identify different fit configurations. |
| Total gold pairs | 83,057,658 | `docs/audits/CL2.0.7_PRE_GOLD_FIT_AUDIT.md`, §A. |

CL2.0.6 baseline — all CL2.0.7+ speedups are measured against this row.

The supplied smoke reference is 1,324,707 pairs / 1,034,022 events. The full-run audit gives 83,057,658 pair rows / 42,812,309 pair-bearing events: ratios calculated directly from these counts are 62.69x pairs and 41.40x pair-bearing events. The supplied 59.5x dataset-statistics ratio compares 61,540,413 full events with the smoke event count; these are different populations/denominators. Sources: `docs/audits/CL2.0.7_PRE_GOLD_FIT_AUDIT.md`, §D, and this ledger's cited files.

## 4. Measured results and interpretation

The core-window Z mass is 90.8619189594322 GeV and the full-window Z mass is 90.7207575824507 GeV. Their measured two-window difference is 141.16137698150055 MeV, calculated from `fits_core_window.json` and `fits_full_window.json`.

The J/ψ, ψ(2S), and Υ(1S) relative shifts calculated from the fit files are -0.103498%, -0.137120%, and -0.142677%. FSR and momentum-scale effects are interpretations consistent with the pattern; the fits do not experimentally separate or quantify those effects. Decomposition is not established without simulation.

J/ψ statistical uncertainty in `fits_core_window.json` is 0.000026829486270196767 GeV (0.026829486270196767 MeV). A claim that this has reached a systematic floor is UNRESOLVED — no quantified systematic-uncertainty artifact is present in the cited result set. The fit files flag gof as `poor` for J/ψ, Υ(1S), and both Z fits; `status` is `valid` in each row. The interpretation that high-statistics chi-square reflects expected model mis-shape is UNRESOLVED — no model-mis-shape study artifact is cited here.

The prior degenerate Z fit is recorded in `docs/audits/CL2.0.7_PRE_GOLD_FIT_AUDIT.md`, §D: mass 90.89219983 GeV, width 0.0033341692 GeV, χ²/ndf 122647/95 (~1291), status `valid`. The current fit-status tiers are documented in `docs/audits/CL2.0.7_PRE_GOLD_FIT_AUDIT.md`, Part 2 implementation: `failed`, `invalid_at_limit`, `invalid_covariance`, `valid`.

Smoke-era fit values and the claimed four-significant-figure mass reproduction are UNRESOLVED — no smoke-era fit JSON/Parquet artifact is present in the repository result set identified by `docs/audits/CL2.0.7_PRE_GOLD_FIT_AUDIT.md`, §D. Availability of Rochester corrections upstream is UNRESOLVED — no artifact in this repository establishes their availability or absence.

## 5. Full-scale campaign log

| Attempt | Date | Failed stage and observed cause | Fix commit / evidence |
|---|---|---|---|
| 1 | 2026-10-28 (commit date; run date UNRESOLVED ? `run_full.log` has no calendar date) | Bronze/DQ failed with pandas `ArrayMemoryError` allocating 13.0 MiB after 210,862,869 rows (`git show a4acc2f:run_full.log`). | `0c20fd3824068620775c4595c27e5902d1c5cfe2`, titled `CL2.0.6C HOTFIX - DQ Streaming`; the requested brief labels this mapping CL2.0.6d, which conflicts with the commit title, so that version label is UNRESOLVED. |
| 2 | 2026-10-28 (commit date; run date UNRESOLVED ? `run_full.log` has no calendar date) | Bronze/DQ failed with DuckDB OOM at 953.5/953.6 MiB (`git show de0eb545:run_full.log`). | `3dddfe98f8e0a09417bedbf8812200d2593e04c3`, titled `CL2.0.6de HOTFIX DuckDB Spillage`; this is consistent with the requested CL2.0.6e fix family. |
| 3 | 2026-10-28 (commit date; run date UNRESOLVED ? `run_full.log` has no calendar date) | Gold failed on the multiplicity assertion (`git show 4a359aba:run_full.log`). | `18ba3a63e6fbe6b891a0aa923db826303a709703`, titled `CL2.0.6f HOTFIX -MUON-MULTIPLICITY TRIPWIRE MISCALIBRATED`. |
| 4 | UNRESOLVED ? no committed failing run log with a calendar date was found. | Z-fit degeneracy is documented in `docs/audits/CL2.0.7_PRE_GOLD_FIT_AUDIT.md`, ?D; the full-scale failure log is absent. | `3ea5691f7636f10b1571074121983f4632890268` is titled `CL2.0.7 - GOLD/FIT AUDIT`, but mapping this commit as the fix for a specific failed full run is UNRESOLVED without that run's committed log. |

The task brief says each failure produced a permanent regression test. Test-to-campaign mapping is UNRESOLVED ? no per-campaign mapping artifact was found.

## 6. Reproduction record

- Audit SQL and explicit gold/silver Parquet paths: `docs/audits/CL2.0.7_PRE_GOLD_FIT_AUDIT.md`, §§A–B.
- Dataset configuration: `configs/datasets.yaml`; source manifest: `data/raw/run2012bc_doublemuparked/MANIFEST.json`.
- Fit JSON artifacts: repository-root `fits_core_window.json` and `fits_full_window.json`; selected fit configuration: `configs/fits/resonance_ladder.yaml`.
- Documented CLI command: `python -m src.cli run --dataset run2012bc_doublemuparked --stage all` (`README.md`). Exact `clam` acquisition/staging command and exact two-window fit command are UNRESOLVED — no command record for them is present in the cited artifacts.
- Repository HEAD at document preparation: `8b69610b1bc80d0742bb1ae1b218e438caee5b1d` (`git rev-parse HEAD`). The fit sidecars do not record a producing commit hash; exact result-producing commit is UNRESOLVED — no artifact ties these JSON files to a source commit.
