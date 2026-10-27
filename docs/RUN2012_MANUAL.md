# Run 2012 production tutorial

This is the verified Windows/local runbook for
`run2012bc_doublemuparked` (CERN Open Data record 12341).

Run every command from the ColliderLake repository root:

```powershell
cd "C:\Ewok\Abomination\Theory of E\V-TRY\ColliderLake"
```

Use `uv run python -m src.cli ...`, not plain `python -m src.cli ...`, so the
locked Python 3.11 environment and dependencies are used.

## 1. Verify the raw file

The file must be here:

```text
data/raw/run2012bc_doublemuparked/Run2012BC_DoubleMuParked_Muons.root
```

Check its size and SHA-256:

```powershell
$root = "data/raw/run2012bc_doublemuparked/Run2012BC_DoubleMuParked_Muons.root"
Get-Item $root | Select-Object FullName,Length,LastWriteTime
Get-FileHash $root -Algorithm SHA256
```

The registered size is `2244449133` bytes. Compare the hash with the checksum
published by CERN. Do not process a truncated file.

## 2. Create or refresh the manifest

The original manual used an `acquire` subcommand, but this checkout exposes
acquisition as a pipeline stage. Run:

```powershell
uv run python -m src.cli run --dataset run2012bc_doublemuparked --stage acquire
Get-Content data/raw/run2012bc_doublemuparked/MANIFEST.json
```

Confirm that the manifest contains the expected filename, byte count, and the
same SHA-256 shown by `Get-FileHash`.

## 3. Inspect the ROOT structure

```powershell
uv run python -c "import uproot; f=uproot.open('data/raw/run2012bc_doublemuparked/Run2012BC_DoubleMuParked_Muons.root'); t=f['Events']; print('entries:', t.num_entries); print('branches:', sorted(t.keys()))"
```

The manual expects approximately `61540413` entries and the reduced muon
branches `nMuon`, `Muon_pt`, `Muon_eta`, `Muon_phi`, `Muon_mass`, and
`Muon_charge`. Treat the actual ROOT metadata as authoritative.

## 4. Run a three-batch rehearsal

```powershell
uv run python -m src.cli run --dataset run2012bc_doublemuparked --stage all --max-batches 3
```

This exercises bronze, silver, gold, and fitting with a small sample. The
current hotfix treats eta acceptance as silver cleaning and pair identity as a
gold `(event key, pair_idx)` key:

- bronze should accept finite muons with `|eta| > 2.4`;
- silver should report `muons_before`, `muons_after_eta`, and `eta_drop_fraction`;
- gold should retain multiple valid pairs from one event with distinct `pair_idx`;
- another failure: stop and inspect it before production.

Inspect the rehearsal results:

```powershell
Get-Content data/results/analysis=resonance/dataset=run2012bc_doublemuparked/fits.json
Get-Content data/results/dq_report.json | Select-Object -Last 20
```

Optional DuckDB check:

```powershell
uv run python -c "import duckdb; print(duckdb.sql(\"SELECT count(*) AS pairs, min(mass) AS min_mass, max(mass) AS max_mass FROM read_parquet('data/gold/analysis=resonance/dataset=run2012bc_doublemuparked/dimuon/*.parquet')\"))"
```

## 5. Clear only generated layers before production

Keep `data/raw`. Remove only the rehearsal outputs:

```powershell
Remove-Item -Recurse -Force data/bronze,data/silver,data/gold,data/results
```

If PowerShell reports that a path does not exist, continue; the raw directory
and its manifest must remain.

## 6. Run the full dataset

```powershell
uv run python -m src.cli run --dataset run2012bc_doublemuparked --stage all *> run_full.log
Get-Content run_full.log -Wait
```

The command can run for hours. Keep the machine plugged in and leave roughly
10 GB free. In another PowerShell window, monitor the generated files:

```powershell
Get-ChildItem data/bronze,data/silver,data/gold -Recurse -Filter *.parquet |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 10 FullName,Length,LastWriteTime
```

If a stage fails, record the last stage in `run_full.log`. After diagnosing the
cause, rerun that stage explicitly, for example:

```powershell
uv run python -m src.cli run --dataset run2012bc_doublemuparked --stage silver
```

## 7. Audit the final result

```powershell
Get-Content data/results/analysis=resonance/dataset=run2012bc_doublemuparked/fits.json
Get-Content run_full.log | Select-Object -Last 40
Get-Content data/results/dq_report.json
```

The fit JSON should contain valid rows for the resonance windows that have
events. Compare fitted masses and uncertainties with the PDG references in
`src/physics/pdg.py`; do not judge success from a peak position alone. Check
fit status, uncertainty, yield, chi-square/ndf, and `delta_pdg_sigma`.

## What was corrected from the supplied manual

- `src.cli acquire` was replaced with the supported `run --stage acquire`
  command.
- `sha256sum` was replaced with PowerShell `Get-FileHash`.
- All commands use the repository's locked `uv` environment.
- The gold Parquet query uses the current `.../dimuon/*.parquet` layout.
- The documented fit output path is the current dataset-scoped `fits.json`.

The current implementation keeps the structural bronze checks, applies eta
acceptance per muon in silver, and checks gold uniqueness using `pair_idx`.
Preserve any other DQ failure and log rather than disabling a gate silently.
