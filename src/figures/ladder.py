from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.physics.models import background_model, signal_model
from src.utils.config import load_yaml
from src.utils.paths import config_path, data_path
from src.utils.runlog import add_stage_stats

FIT_COLUMNS = (
    "resonance",
    "status",
    "gof_flag",
    "mass_fit",
    "mass_stat_unc",
    "signal_yield",
    "background_yield",
    "pdg_mass",
    "chi2",
    "ndf",
    "window",
    "n_bins",
    "selection_id",
    "fit_config_id",
    "signal_model",
    "background_model",
    "fit_parameters_json",
)


def fits_path_for_dataset(dataset_id: str, analysis: str = "resonance") -> Path:
    return data_path("results", f"analysis={analysis}", f"dataset={dataset_id}", "fits.parquet")


def gold_path_for_fits(fit_path: Path) -> Path:
    dataset_id = _partition_value(fit_path, "dataset")
    analysis = _partition_value(fit_path, "analysis") or "resonance"
    if dataset_id is None:
        raise ValueError(
            f"Cannot infer dataset= partition from fits path {fit_path}; provide gold_path explicitly"
        )
    return data_path("gold", f"analysis={analysis}", f"dataset={dataset_id}", "dimuon")


def generate_figures(
    fits_path: str | Path,
    *,
    run_id: str,
    canonical_dir: str | Path,
    results_dir: str | Path,
    gold_path: str | Path | None = None,
) -> dict[str, Any]:
    """Render figures and tables using only persisted fit and gold values."""
    fits_file = Path(fits_path).expanduser().resolve()
    if not fits_file.is_file():
        raise FileNotFoundError(f"Fits Parquet file not found: {fits_file}")
    fits = pd.read_parquet(fits_file)
    if fits.empty:
        raise ValueError(f"Fits Parquet file contains no fit rows: {fits_file}")
    missing = sorted(set(FIT_COLUMNS) - set(fits.columns))
    if missing:
        raise ValueError(
            f"Fits file {fits_file} lacks figure inputs {missing}; rerun the fit stage to persist models and parameters"
        )
    fit_rows = [_normalize_fit_row(row) for row in fits.to_dict(orient="records")]
    if any(not row["fit_parameters"] for row in fit_rows):
        raise ValueError(f"Fits file {fits_file} contains an empty fit parameter payload")

    gold_dir = (
        Path(gold_path).expanduser().resolve() if gold_path else gold_path_for_fits(fits_file)
    )
    gold_files = [gold_dir] if gold_dir.is_file() else sorted(gold_dir.glob("*.parquet"))
    if not gold_files:
        raise FileNotFoundError(f"No gold Parquet parts found under {gold_dir}")
    cfg = load_yaml(config_path("figures.yaml"))
    ladder_edges = np.geomspace(
        float(cfg["ladder"]["mass_min_gev"]),
        float(cfg["ladder"]["mass_max_gev"]),
        int(cfg["ladder"]["log_bins"]) + 1,
    )
    ladder_counts = np.zeros(len(ladder_edges) - 1, dtype=np.int64)
    panel_bins = {
        str(row["resonance"]): (
            np.histogram_bin_edges([], bins=int(row["n_bins"]), range=tuple(row["window"])),
            np.zeros(int(row["n_bins"]), dtype=np.int64),
        )
        for row in fit_rows
    }
    mass_row_count = 0
    for part in gold_files:
        values = pd.read_parquet(part, columns=["mass"])["mass"].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        mass_row_count += int(values.size)
        ladder_counts += np.histogram(values, bins=ladder_edges)[0]
        for row in fit_rows:
            panel_edges, panel_counts = panel_bins[str(row["resonance"])]
            in_window = values[(values >= panel_edges[0]) & (values <= panel_edges[-1])]
            panel_counts += np.histogram(in_window, bins=panel_edges)[0]
    if mass_row_count == 0:
        raise ValueError(f"Gold mass column contains no finite values under {gold_dir}")
    if int(ladder_counts.sum()) == 0:
        raise ValueError("Gold mass column has no entries in the configured ladder range")

    target = Path(canonical_dir)
    pointer = Path(results_dir)
    target.mkdir(parents=True, exist_ok=True)
    pointer.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, str]] = []
    dataset_id = _partition_value(fits_file, "dataset") or str(
        fit_rows[0].get("dataset_id", "unknown")
    )
    _style(cfg)

    ladder_files = _render_ladder(ladder_counts, ladder_edges, fit_rows, cfg, target, dataset_id)
    artifacts.extend(_copy_artifacts(ladder_files, target, pointer))
    for row in fit_rows:
        panel_edges, panel_counts = panel_bins[str(row["resonance"])]
        panel_files = _render_panel(panel_counts, panel_edges, row, cfg, target)
        artifacts.extend(_copy_artifacts(panel_files, target, pointer))

    markdown = _pdg_markdown(fit_rows)
    latex = _pdg_latex(fit_rows)
    _atomic_text(target / "pdg_table.md", markdown)
    _atomic_text(target / "pdg_table.tex", latex)
    _atomic_text(pointer / "pdg_table.md", markdown)
    _atomic_text(pointer / "pdg_table.tex", latex)
    artifacts.extend(_artifact_record(target / "pdg_table.md", pointer / "pdg_table.md"))
    artifacts.extend(_artifact_record(target / "pdg_table.tex", pointer / "pdg_table.tex"))

    inputs = {
        "fits": {"path": str(fits_file), "sha256": _sha256(fits_file)},
        "gold": _inventory(gold_dir),
    }
    canonical_manifest = {"run_id": run_id, "inputs": inputs, "files": artifacts}
    _atomic_text(
        target / "manifest.json", json.dumps(canonical_manifest, indent=2, sort_keys=True) + "\n"
    )
    pointer_manifest = {"run_id": run_id, "inputs": inputs, "files": artifacts}
    _atomic_text(
        pointer / "manifest.json", json.dumps(pointer_manifest, indent=2, sort_keys=True) + "\n"
    )
    add_stage_stats("figures", batches=1, rows_out=len(artifacts))
    return {
        "run_id": run_id,
        "canonical_dir": str(target),
        "results_dir": str(pointer),
        "manifest": canonical_manifest,
        "files": artifacts,
        "fits_path": str(fits_file),
        "gold_parts": len(gold_files),
        "gold_rows": mass_row_count,
        "fits_sha256": _sha256(fits_file),
        "gold_inventory": _inventory(gold_dir),
    }


def run_figures_recorded(
    fits_path: str | Path,
    *,
    gold_path: str | Path | None = None,
    hodoscope_root: str | Path | None = None,
) -> dict[str, Any]:
    from src.hodoscope.registry import run as hodo_run
    from src.utils.paths import data_root

    fits_file = Path(fits_path).expanduser().resolve()
    if not fits_file.is_file():
        raise FileNotFoundError(f"Fits Parquet file not found: {fits_file}")
    inferred_gold = (
        Path(gold_path).expanduser().resolve() if gold_path else gold_path_for_fits(fits_file)
    )
    context = {
        "fits_path": str(fits_file),
        "fits_sha256": _sha256(fits_file),
        "gold_path": str(inferred_gold),
        "gold_inventory": _inventory(inferred_gold),
    }
    record = hodo_run(
        "colliderlake:figures",
        context_providers=[lambda: context],
        env_prefixes=("HODO", "COLLIDERLAKE_"),
        root=hodoscope_root or data_root() / "results",
    )
    output: dict[str, Any]
    with record:
        stage = record.stage("figures")
        with stage:
            output = generate_figures(
                fits_file,
                run_id=record.run_id,
                canonical_dir=record.run_dir / "figures",
                results_dir=data_path("results", "figures", record.run_id),
                gold_path=inferred_gold,
            )
            stage.rows_out = len(output["files"])
            stage.metric("files", output["files"])
            stage.metric("gold_rows", output["gold_rows"])
            stage.metric("fit_rows", len(pd.read_parquet(fits_file)))
            stage.metric("fits_sha256", output["fits_sha256"])
            stage.metric("gold_inventory", output["gold_inventory"])
            for item in output["files"]:
                if item["location"] == "canonical":
                    record.artifact(record.run_dir / "figures" / item["name"])
            record.artifact(record.run_dir / "figures" / "manifest.json")
            record.external(output["results_dir"], run_id=record.run_id)
    return output


def _normalize_fit_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    try:
        params = json.loads(str(row["fit_parameters_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid fit_parameters_json for {row.get('resonance')}: {exc}") from exc
    if not isinstance(params, dict):
        raise TypeError(f"fit_parameters_json for {row.get('resonance')} must be an object")
    normalized["fit_parameters"] = {str(key): float(value) for key, value in params.items()}
    normalized["window"] = [float(value) for value in row["window"]]
    return normalized


def _render_ladder(
    counts: np.ndarray,
    edges: np.ndarray,
    fit_rows: list[dict[str, Any]],
    cfg: dict[str, Any],
    output_dir: Path,
    dataset_id: str,
) -> list[Path]:
    settings = cfg["ladder"]
    centers = np.sqrt(edges[:-1] * edges[1:])
    fig, ax = plt.subplots(figsize=(9.2, 6.2), constrained_layout=False)
    fig.subplots_adjust(left=0.09, right=0.985, top=0.98, bottom=0.18)
    ax.step(centers, counts, where="mid", color="black", linewidth=0.85)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(edges[0], edges[-1])
    ax.set_xlabel(r"Dimuon invariant mass $m_{\mu\mu}$ [GeV]")
    ax.set_ylabel("Gold dimuon pairs / log-mass bin")
    ymax = float(np.max(counts))
    for index, row in enumerate(fit_rows):
        mass = float(row["mass_fit"])
        ax.axvline(mass, color="0.35", linestyle=(0, (2, 2)), linewidth=0.75)
        y = ymax * (0.56 if index % 2 == 0 else 0.30)
        ax.annotate(
            f"{_display_resonance(row['resonance'])}  {mass:.5g} GeV",
            (mass, y),
            xytext=(4, 2),
            textcoords="offset points",
            fontsize=7,
            rotation=90,
            va="bottom",
            color="0.15",
        )
    trigger_x = float(settings["trigger_artifact_mass_gev"])
    ax.axvline(trigger_x, color="0.5", linestyle=(0, (1, 2)), linewidth=0.8)
    ax.annotate(
        str(settings["trigger_artifact_label"]),
        (trigger_x, ymax * 0.08),
        xytext=(4, 4),
        textcoords="offset points",
        fontsize=7,
        rotation=90,
        va="bottom",
        color="0.25",
    )
    fig.text(
        0.01,
        0.005,
        f"CMS Open Data · {dataset_id} · values from gold and persisted fit artifacts",
        fontsize=7,
        color="0.25",
    )
    if any(str(row["resonance"]) == "upsilon" for row in fit_rows):
        fig.text(
            0.01,
            0.022,
            "\u03a5(1S): 2S/3S constrained at PDG splittings in a shared fit",
            fontsize=6.5,
            color="0.25",
        )
    return _save_figure(fig, output_dir / "dimuon_ladder")


def _render_panel(
    counts: np.ndarray,
    edges: np.ndarray,
    row: dict[str, Any],
    cfg: dict[str, Any],
    output_dir: Path,
) -> list[Path]:
    window = tuple(row["window"])
    centers = 0.5 * (edges[:-1] + edges[1:])
    signal_spec = signal_model(str(row["signal_model"]), str(row["resonance"]), window)
    background_spec = background_model(str(row["background_model"]), window)
    params = row["fit_parameters"]
    signal_shape = {key: params[key] for key in signal_spec.parameter_defaults}
    background_shape = {key: params[key] for key in background_spec.parameter_defaults}
    signal, background = _model_components(
        centers,
        window,
        float(row["signal_yield"]),
        float(row["background_yield"]),
        signal_spec,
        background_spec,
        signal_shape,
        background_shape,
    )
    total = signal + background
    sigma = np.sqrt(np.maximum(total, np.finfo(float).tiny))
    pulls = (counts - total) / sigma

    fig, (ax, pull_ax) = plt.subplots(
        2,
        1,
        figsize=(7.3, 6.2),
        sharex=True,
        gridspec_kw={"height_ratios": [3.2, 1.0]},
        constrained_layout=True,
    )
    ax.errorbar(
        centers, counts, yerr=np.sqrt(counts), fmt="o", ms=2.4, color="black", label="Gold data"
    )
    ax.plot(centers, total, color="0.1", linewidth=1.2, label="Total model")
    ax.plot(centers, background, color="0.35", linestyle="--", linewidth=1.0, label="Background")
    ax.set_ylabel("Pairs / bin")
    ax.legend(frameon=False, fontsize=8)
    ax.set_title(_display_resonance(row["resonance"]))
    chi2_ndf = _chi2_ndf(row)
    delta = float(row["mass_fit"]) - float(row["pdg_mass"])
    annotation = (
        f"mass = {float(row['mass_fit']):.7g} ± {float(row['mass_stat_unc']):.3g} GeV\n"
        f"PDG = {float(row['pdg_mass']):.7g} GeV; Δ = {delta:+.3g} GeV\n"
        f"χ²/ndf = {chi2_ndf:.4g}; gof = {row['gof_flag']}; status = {row['status']}\n"
        f"selection_id = {row['selection_id']}\nfit_config_id = {row['fit_config_id']}"
    )
    if str(row["resonance"]) == "upsilon":
        annotation += "\nΥ(1S): 2S/3S constrained at PDG splittings in a shared fit"
    ax.text(
        0.02,
        0.97,
        annotation,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=7,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "0.75", "alpha": 0.9},
    )
    pull_ax.axhline(0.0, color="0.2", linewidth=0.8)
    reference_pull = float(cfg["panels"]["pull_reference_sigma"])
    pull_ax.axhline(reference_pull, color="0.55", linestyle="--", linewidth=0.65)
    pull_ax.axhline(-reference_pull, color="0.55", linestyle="--", linewidth=0.65)
    pull_ax.bar(
        centers, pulls, width=np.diff(edges), color="0.45", edgecolor="black", linewidth=0.15
    )
    pull_ax.set_ylabel("Pull")
    pull_ax.set_xlabel(r"Dimuon invariant mass $m_{\mu\mu}$ [GeV]")
    return _save_figure(fig, output_dir / f"{row['resonance']}_fit")


def _model_components(
    centers: np.ndarray,
    window: tuple[float, float],
    signal_yield: float,
    background_yield: float,
    signal_spec,
    background_spec,
    signal_shape: dict[str, float],
    background_shape: dict[str, float],
) -> tuple[np.ndarray, np.ndarray]:
    signal = signal_yield * signal_spec.pdf(centers, signal_shape, window)
    background = background_yield * background_spec.pdf(centers, background_shape, window)
    return signal, background


def _save_figure(fig, stem: Path) -> list[Path]:
    dpi = int(load_yaml(config_path("figures.yaml"))["style"]["figure_dpi"])
    outputs = []
    for suffix, fmt, options in ((".pdf", "pdf", {}), (".png", "png", {"dpi": dpi})):
        destination = stem.with_suffix(suffix)
        temp = destination.with_name(f".{destination.stem}.{os.getpid()}.tmp{suffix}")
        try:
            fig.savefig(temp, format=fmt, **options)
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)
        outputs.append(destination)
    plt.close(fig)
    return outputs


def _style(cfg: dict[str, Any]) -> None:
    plt.rcParams.update(
        {
            "font.family": str(cfg["style"]["serif_family"]),
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _pdg_markdown(rows: list[dict[str, Any]]) -> str:
    headers = [
        "Resonance",
        "Window [GeV]",
        "Mass \u00b1 stat. unc. [GeV]",
        "PDG [GeV]",
        "Shift [%]",
        "Signal yield",
        "chi2/ndf",
        "GOF",
        "Status",
        "selection_id",
        "fit_config_id",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_table_values(row)) + " |")
    text = "\n".join(lines) + "\n"
    if any(str(row["resonance"]) == "upsilon" for row in rows):
        text += "\nΥ(1S): 2S/3S constrained at PDG splittings in a shared fit.\n"
    return text


def _pdg_latex(rows: list[dict[str, Any]]) -> str:
    headers = [
        "Resonance",
        "Window [GeV]",
        r"Mass $\pm$ stat. unc. [GeV]",
        "PDG [GeV]",
        "Shift [\\%]",
        "Signal yield",
        r"$\chi^2$/ndf",
        "GOF",
        "Status",
        r"selection\_id",
        r"fit\_config\_id",
    ]
    alignment = "l" + "c" * (len(headers) - 1)
    lines = [
        r"\documentclass{article}",
        r"\usepackage{booktabs}",
        r"\begin{document}",
        rf"\begin{{tabular}}{{{alignment}}}",
        r"\toprule",
        " & ".join(headers) + " " + "\\" * 2,
        r"\midrule",
    ]
    for row in rows:
        values = [
            value.replace("_", r"\_").replace("\u00b1", r"$\pm$") for value in _table_values(row)
        ]
        if values[0] == "Υ(1S)":
            values[0] = r"$\Upsilon(1S)$"
        lines.append(" & ".join(values) + " " + "\\" * 2)
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    if any(str(row["resonance"]) == "upsilon" for row in rows):
        lines.append(r"\par\smallskip\noindent\footnotesize $\Upsilon(1S)$: 2S/3S constrained at PDG splittings in a shared fit.")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def _table_values(row: dict[str, Any]) -> list[str]:
    low, high = row["window"]
    mass = float(row["mass_fit"])
    pdg = float(row["pdg_mass"])
    shift_percent = 100.0 * (mass - pdg) / pdg
    return [
        _display_resonance(row["resonance"]),
        f"[{float(low)!r}, {float(high)!r}]",
        _rounded_mass_and_uncertainty(mass, float(row["mass_stat_unc"])),
        repr(pdg),
        repr(shift_percent),
        repr(float(row["signal_yield"])),
        repr(_chi2_ndf(row)),
        str(row["gof_flag"]),
        str(row["status"]),
        str(row["selection_id"]),
        str(row["fit_config_id"]),
    ]


def _display_resonance(resonance: Any) -> str:
    return "Υ(1S)" if str(resonance) == "upsilon" else str(resonance)


def _rounded_mass_and_uncertainty(mass: float, uncertainty: float) -> str:
    """Round the uncertainty to two significant figures and mass to its place."""
    if not (uncertainty > 0 and np.isfinite(uncertainty)):
        raise ValueError("statistical uncertainty must be finite and positive for table display")
    unc = Decimal(str(uncertainty))
    mass_value = Decimal(str(mass))
    quantum = Decimal(1).scaleb(unc.adjusted() - 1)
    rounded_unc = unc.quantize(quantum, rounding=ROUND_HALF_UP)
    rounded_mass = mass_value.quantize(quantum, rounding=ROUND_HALF_UP)
    decimals = max(0, -quantum.as_tuple().exponent)
    return f"{rounded_mass:.{decimals}f} ± {rounded_unc:.{decimals}f}"


def _chi2_ndf(row: dict[str, Any]) -> float:
    ndf = int(row["ndf"])
    return float(row["chi2"]) / ndf if ndf > 0 else float("nan")


def _copy_artifacts(files: list[Path], canonical: Path, pointer: Path) -> list[dict[str, str]]:
    result = []
    for source in files:
        destination = pointer / source.name
        _atomic_copy(source, destination)
        result.extend(_artifact_record(source, destination))
    return result


def _artifact_record(canonical: Path, pointer: Path) -> list[dict[str, str]]:
    digest = _sha256(canonical)
    return [
        {"name": canonical.name, "sha256": digest, "location": "canonical"},
        {"name": pointer.name, "sha256": _sha256(pointer), "location": "results/figures"},
    ]


def _inventory(path: Path) -> list[dict[str, Any]]:
    files = [path] if path.is_file() else sorted(path.glob("*.parquet"))
    return [{"path": str(item), "sha256": _sha256(item)} for item in files]


def _partition_value(path: Path, prefix: str) -> str | None:
    for part in path.parts:
        if part.startswith(prefix + "="):
            return part.split("=", 1)[1]
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _atomic_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
