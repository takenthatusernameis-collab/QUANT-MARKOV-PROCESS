"""
Protocol-enforcing holdout evaluation runner (T5b stub).

Loads frozen protocol/manifest, enforces leakage/integrity controls, and
REFUSES execution by default. Holdout evaluation runs only with explicit
`--execute-holdout` and a matching protocol SHA256 hash.

Holdout period (frozen): 2024-07-01 00:00:00+00:00 .. 2025-12-31 23:00:00+00:00
Candidates: C1 filtered 3-state Gaussian HMM, C2 higher-order Markov (order 2, K=5)

This module must not modify AGENTS.md, MARKOV_RESEARCH_PROMPT.md, or .github/workflows/*.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = REPO_ROOT / "research" / "specifications" / "holdout_evaluation_protocol.md"
MANIFEST_TEMPLATE_PATH = REPO_ROOT / "research" / "specifications" / "holdout_evaluation_manifest_template.json"
DATA_PATH = REPO_ROOT / "data" / "processed" / "features.parquet"
RAW_MANIFEST_PATH = REPO_ROOT / "data" / "raw" / "manifest.json"
HOLDOUT_START = pd.Timestamp("2024-07-01 00:00:00", tz="UTC")
HOLDOUT_END = pd.Timestamp("2025-12-31 23:00:00+00:00", tz="UTC")
TRAIN_END = pd.Timestamp("2023-12-31 23:59:59", tz="UTC")  # bins/edges fit on training only (<=2023-12-31 per artifacts/protocol)
FORECAST_OUT_DIR = REPO_ROOT / "research" / "forecasts" / "holdout"
ECON_OUT_DIR = REPO_ROOT / "research" / "economic" / "holdout"

# Frozen C1 config (T4/H2)
C1_SEEDS: Tuple[int, ...] = (0, 1, 2)
C1_REFIT_EVERY = 720
C1_EVAL_STRIDE = 4
C1_N_STATES = 3
# Frozen C2 config (H3)
C2_ORDER = 2
C2_K = 5
C2_LAPLACE_ALPHA = 1.0
C2_MIN_PAIR_SAMPLES = 20
C2_EVAL_STRIDE = 4


class HoldoutAuthorizationError(RuntimeError):
    """Raised when holdout execution is not explicitly authorized."""


class HoldoutIntegrityError(ValueError):
    """Raised when a leakage/integrity control is violated."""


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_protocol_hash(protocol_path: Path = PROTOCOL_PATH) -> str:
    if not protocol_path.exists():
        raise FileNotFoundError(f"protocol not found: {protocol_path}")
    return compute_file_sha256(protocol_path)


def load_protocol_text(protocol_path: Path = PROTOCOL_PATH) -> str:
    return protocol_path.read_text(encoding="utf-8")


def load_manifest_template(path: Path = MANIFEST_TEMPLATE_PATH) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_git_sha(repo_root: Path = REPO_ROOT) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), stderr=subprocess.DEVNULL, text=True
        )
        return out.strip()
    except Exception:
        return None


def verify_execution_authorized(
    execute_holdout: bool,
    provided_hash: Optional[str],
    protocol_path: Path = PROTOCOL_PATH,
) -> str:
    """Return protocol hash if explicitly authorized; otherwise raise."""
    expected = compute_protocol_hash(protocol_path)
    if not execute_holdout:
        raise HoldoutAuthorizationError(
            "Holdout execution refused: --execute-holdout not provided. "
            "This runner enforces a locked holdout and will not run by default."
        )
    if not provided_hash:
        raise HoldoutAuthorizationError(
            "Holdout execution refused: --protocol-hash is required with --execute-holdout."
        )
    if provided_hash.strip().lower() != expected.lower():
        raise HoldoutAuthorizationError(
            "Holdout execution refused: provided protocol hash does not match frozen protocol. "
            f"expected={expected} provided={provided_hash.strip().lower()}"
        )
    return expected


def validate_no_lookahead(
    target_timestamp: pd.Timestamp,
    history_end_timestamp: pd.Timestamp,
    holdout_start: pd.Timestamp = HOLDOUT_START,
    holdout_end: pd.Timestamp = HOLDOUT_END,
) -> None:
    """Enforce point-in-time constraints for a single forecast target."""
    if target_timestamp < holdout_start or target_timestamp > holdout_end:
        raise HoldoutIntegrityError(
            f"target {target_timestamp} outside holdout window [{holdout_start}, {holdout_end}]"
        )
    if history_end_timestamp >= target_timestamp:
        raise HoldoutIntegrityError(
            f"lookahead/leakage: history_end {history_end_timestamp} must be < target {target_timestamp}"
        )


def validate_holdout_window(df: pd.DataFrame, holdout_start: pd.Timestamp = HOLDOUT_START, holdout_end: pd.Timestamp = HOLDOUT_END) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], utc=True)
    mask = (ts >= holdout_start) & (ts <= holdout_end)
    holdout_df = df.loc[mask].copy()
    if holdout_df.empty:
        raise HoldoutIntegrityError("no rows found in frozen holdout window")
    return holdout_df


def build_execution_manifest(
    template: Dict,
    protocol_hash: str,
    command: str,
    executed_utc: str,
    git_sha: Optional[str],
    features_sha256: Optional[str],
    raw_manifest_sha256: Optional[str],
    holdout_evaluated: bool,
    operator_notes: str = "",
) -> Dict:
    manifest = json.loads(json.dumps(template))  # deep copy
    manifest.setdefault("protocol", {})
    manifest["protocol"]["protocol_sha256"] = protocol_hash
    manifest.setdefault("data_provenance", {})
    manifest["data_provenance"]["features_sha256"] = features_sha256
    manifest["data_provenance"]["raw_manifest_sha256"] = raw_manifest_sha256
    manifest.setdefault("execution", {})
    manifest["execution"]["git_sha"] = git_sha
    manifest["execution"]["command"] = command
    manifest["execution"]["executed_utc"] = executed_utc
    manifest["execution"]["holdout_evaluated"] = bool(holdout_evaluated)
    manifest["execution"]["operator_notes"] = operator_notes
    return manifest


def _load_btc_returns(df: pd.DataFrame) -> pd.DataFrame:
    btc = df[df["symbol"] == "BTCUSDT"].copy()
    btc["timestamp"] = pd.to_datetime(btc["timestamp"], utc=True)
    btc = btc.sort_values("timestamp").reset_index(drop=True)
    btc = btc.dropna(subset=["close"]).copy()
    btc["returns"] = btc["close"].pct_change()
    btc = btc.dropna(subset=["returns"]).reset_index(drop=True)
    return btc


def _collect_holdout_targets(ts: pd.Series, eval_stride: int) -> List[int]:
    idx = np.where((ts >= HOLDOUT_START) & (ts <= HOLDOUT_END))[0]
    idx = idx[:: max(1, int(eval_stride))]
    # need at least one prior observation
    return [int(i) for i in idx if i >= 1]


def run_c1_holdout_hmm(df: pd.DataFrame) -> Dict:
    """Run frozen C1 (filtered 3-state Gaussian HMM) on locked holdout. Point-in-time only."""
    # Lazy imports to keep refusal path lightweight
    from src.hmm_walkforward import (
        expanding_unconditional_params,
        ewma_forecast_params,
        filtered_state_probs,
        fit_ordered_hmm,
        forecast_next_from_filtered,
        gaussian_logpdf,
        gaussian_crps,
        mixture_logpdf,
        mixture_crps_grid,
    )

    btc = _load_btc_returns(df)
    ts = btc["timestamp"]
    returns = btc["returns"].to_numpy(dtype=float)
    target_indices = _collect_holdout_targets(ts, C1_EVAL_STRIDE)
    rows = []
    refits = []
    current_model = None
    last_refit_i = None

    for i in target_indices:
        target_ts = pd.Timestamp(ts.iloc[i])
        validate_no_lookahead(target_ts, pd.Timestamp(ts.iloc[i - 1]))
        # fit/predict using history up to i-1 only (expanding)
        history_end = i - 1
        need_refit = current_model is None or (history_end - (last_refit_i or 0)) >= C1_REFIT_EVERY
        if need_refit:
            train_slice = returns[: history_end + 1]
            if len(train_slice) < 500:
                continue
            current_model = fit_ordered_hmm(train_slice, seeds=C1_SEEDS)
            last_refit_i = history_end
            refits.append({
                "refit_at_index": int(history_end),
                "refit_timestamp": str(ts.iloc[history_end]),
                "train_size": int(history_end + 1),
                "log_likelihood": float(getattr(current_model, "train_log_likelihood_", np.nan)),
            })
        assert current_model is not None
        hist = returns[: history_end + 1]
        filt = filtered_state_probs(current_model, hist)[-1]
        next_probs, mix_means, mix_vars = forecast_next_from_filtered(current_model, filt)
        hmm_mu = float(np.sum(next_probs * mix_means))
        hmm_var = float(np.sum(next_probs * (mix_vars + mix_means ** 2)) - hmm_mu ** 2)
        hmm_var = max(hmm_var, 1e-12)
        unc_mu, unc_var = expanding_unconditional_params(hist)
        ewma_mu, ewma_var = ewma_forecast_params(hist, lam=0.94)
        y_true = float(returns[i])
        rows.append({
            "timestamp": str(target_ts),
            "y_true": y_true,
            "p_s0": float(next_probs[0]), "p_s1": float(next_probs[1]), "p_s2": float(next_probs[2]),
            "hmm_mu": hmm_mu, "hmm_var": hmm_var,
            "unc_mu": unc_mu, "unc_var": unc_var,
            "ewma_mu": ewma_mu, "ewma_var": ewma_var,
            "hmm_log": float(mixture_logpdf(y_true, next_probs, mix_means, mix_vars)),
            "unc_log": float(gaussian_logpdf(np.array([y_true]), np.array([unc_mu]), np.array([unc_var]))[0]),
            "ewma_log": float(gaussian_logpdf(np.array([y_true]), np.array([ewma_mu]), np.array([ewma_var]))[0]),
            "hmm_crps": float(mixture_crps_grid(y_true, next_probs, mix_means, mix_vars)),
            "unc_crps": float(gaussian_crps(y_true, unc_mu, math.sqrt(unc_var))),
            "ewma_crps": float(gaussian_crps(y_true, ewma_mu, math.sqrt(ewma_var))),
        })
    return {"model": "C1_hmm", "rows": rows, "refits": refits, "n": len(rows)}


def run_c2_holdout_hom(df: pd.DataFrame) -> Dict:
    """Run frozen C2 (higher-order Markov order 2, K=5) on locked holdout. Point-in-time only."""
    from src.higher_order_markov import (
        expanding_unconditional_params,
        ewma_forecast_params,
        fit_quantile_bins,
        assign_states,
        estimate_transition_counts_order2,
        transition_probs_from_counts_order2,
        state_conditional_params_order2,
        gaussian_logpdf,
        gaussian_crps,
        mixture_logpdf,
        mixture_crps_grid,
    )

    btc = _load_btc_returns(df)
    ts = btc["timestamp"]
    returns = btc["returns"].to_numpy(dtype=float)
    train_mask = ts <= TRAIN_END
    train_returns = returns[train_mask.to_numpy()]
    if len(train_returns) < 500:
        raise HoldoutIntegrityError("insufficient training data for C2 bin fitting")
    edges = fit_quantile_bins(train_returns, C2_K)  # train-fitted only
    all_states = assign_states(returns, edges)
    target_indices = _collect_holdout_targets(ts, C2_EVAL_STRIDE)
    target_indices = [i for i in target_indices if i >= 2]
    rows = []
    for i in target_indices:
        target_ts = pd.Timestamp(ts.iloc[i])
        validate_no_lookahead(target_ts, pd.Timestamp(ts.iloc[i - 1]))
        history_returns = returns[:i]
        history_states = all_states[:i]
        if len(history_returns) < 100:
            continue
        s_prev = int(history_states[i - 2])
        s_curr = int(history_states[i - 1])
        counts = estimate_transition_counts_order2(history_states, C2_K)
        trans = transition_probs_from_counts_order2(counts, alpha=C2_LAPLACE_ALPHA)
        next_probs = np.clip(trans[s_prev, s_curr].copy(), 1e-16, 1.0)
        next_probs = next_probs / next_probs.sum()
        unc_mu, unc_var = expanding_unconditional_params(history_returns)
        ewma_mu, ewma_var = ewma_forecast_params(history_returns)
        pair_means, pair_vars = state_conditional_params_order2(history_returns, history_states, C2_K, unc_mu, unc_var)
        state_means = pair_means[s_curr].copy()
        state_vars = pair_vars[s_curr].copy()
        hom_mu = float(np.sum(next_probs * state_means))
        hom_var = float(max(np.sum(next_probs * (state_vars + state_means ** 2)) - hom_mu ** 2, 1e-10))
        y_true = float(returns[i])
        rows.append({
            "timestamp": str(target_ts), "y_true": y_true,
            "s_prev": s_prev, "s_curr": s_curr,
            **{f"p_s{k}": float(next_probs[k]) for k in range(C2_K)},
            "hom_mu": hom_mu, "hom_var": hom_var,
            "unc_mu": unc_mu, "unc_var": unc_var,
            "ewma_mu": ewma_mu, "ewma_var": ewma_var,
            "hom_log": float(mixture_logpdf(y_true, next_probs, state_means, state_vars)),
            "unc_log": float(gaussian_logpdf(np.array([y_true]), np.array([unc_mu]), np.array([unc_var]))[0]),
            "ewma_log": float(gaussian_logpdf(np.array([y_true]), np.array([ewma_mu]), np.array([ewma_var]))[0]),
            "hom_crps": float(mixture_crps_grid(y_true, next_probs, state_means, state_vars)),
            "unc_crps": float(gaussian_crps(y_true, unc_mu, math.sqrt(unc_var))),
            "ewma_crps": float(gaussian_crps(y_true, ewma_mu, math.sqrt(ewma_var))),
        })
    return {"model": "C2_hom_order2_k5", "rows": rows, "n": len(rows), "bin_edges": edges.tolist()}


def _summary_metrics(rows: List[Dict], prefix: str) -> Dict:
    if not rows:
        return {"n_obs": 0}
    log_m = np.array([r[f"{prefix}_log"] for r in rows], dtype=float)
    unc_log = np.array([r["unc_log"] for r in rows], dtype=float)
    ewma_log = np.array([r["ewma_log"] for r in rows], dtype=float)
    crps_m = np.array([r[f"{prefix}_crps"] for r in rows], dtype=float)
    unc_crps = np.array([r["unc_crps"] for r in rows], dtype=float)
    ewma_crps = np.array([r["ewma_crps"] for r in rows], dtype=float)
    def s(a):
        return {"mean": float(np.mean(a)), "median": float(np.median(a)), "std": float(np.std(a))}
    return {
        "n_obs": len(rows),
        "log_score_higher_is_better": {prefix: s(log_m), "unconditional_gaussian": s(unc_log), "ewma_gaussian": s(ewma_log)},
        "crps_lower_is_better": {prefix: s(crps_m), "unconditional_gaussian": s(unc_crps), "ewma_gaussian": s(ewma_crps)},
    }


def execute_holdout(protocol_hash: str, command: str, protocol_path: Path = PROTOCOL_PATH,
                    manifest_template_path: Path = MANIFEST_TEMPLATE_PATH,
                    data_path: Path = DATA_PATH) -> Dict:
    """Execute authorized holdout evaluation for C1/C2 and write artifacts/manifest."""
    template = load_manifest_template(manifest_template_path)
    if not data_path.exists():
        raise FileNotFoundError(f"features data not found: {data_path}")
    df = pd.read_parquet(data_path)
    validate_holdout_window(df)

    FORECAST_OUT_DIR.mkdir(parents=True, exist_ok=True)
    ECON_OUT_DIR.mkdir(parents=True, exist_ok=True)

    c1 = run_c1_holdout_hmm(df)
    c2 = run_c2_holdout_hom(df)

    # Save forecast artifacts
    c1_df = pd.DataFrame(c1["rows"])
    c2_df = pd.DataFrame(c2["rows"])
    c1_csv = FORECAST_OUT_DIR / "c1_hmm_holdout_forecasts.csv"
    c2_csv = FORECAST_OUT_DIR / "c2_hom_holdout_forecasts.csv"
    c1_df.to_csv(c1_csv, index=False)
    c2_df.to_csv(c2_csv, index=False)

    c1_metrics = _summary_metrics(c1["rows"], "hmm")
    c2_metrics = _summary_metrics(c2["rows"], "hom")
    metrics_payload = {
        "executed_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": protocol_hash,
        "holdout_start": str(HOLDOUT_START),
        "holdout_end": str(HOLDOUT_END),
        "c1": {"metrics": c1_metrics, "refits": len(c1.get("refits", [])), "artifact": str(c1_csv)},
        "c2": {"metrics": c2_metrics, "artifact": str(c2_csv)},
        "notes": "Forecast metrics only; economic simulation/bootstrap extensions can be layered per protocol in follow-up authorized runs.",
    }
    metrics_path = FORECAST_OUT_DIR / "holdout_forecast_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)

    executed_utc = datetime.now(timezone.utc).isoformat()
    git_sha = get_git_sha()
    features_sha = compute_file_sha256(data_path) if data_path.exists() else None
    raw_sha = compute_file_sha256(RAW_MANIFEST_PATH) if RAW_MANIFEST_PATH.exists() else None
    manifest = build_execution_manifest(
        template=template,
        protocol_hash=protocol_hash,
        command=command,
        executed_utc=executed_utc,
        git_sha=git_sha,
        features_sha256=features_sha,
        raw_manifest_sha256=raw_sha,
        holdout_evaluated=True,
        operator_notes="Authorized holdout execution completed by holdout_runner.",
    )
    manifest_path = FORECAST_OUT_DIR / "holdout_execution_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Minimal report
    report_lines = [
        "# Holdout Forecast Evaluation (Authorized Run)",
        "",
        f"- Executed UTC: {executed_utc}",
        f"- Protocol SHA256: {protocol_hash}",
        f"- Git SHA: {git_sha}",
        f"- Holdout: {HOLDOUT_START} to {HOLDOUT_END}",
        f"- C1 forecasts: {c1['n']} -> {c1_csv}",
        f"- C2 forecasts: {c2['n']} -> {c2_csv}",
        f"- Metrics: {metrics_path}",
        f"- Manifest: {manifest_path}",
        "",
        "All forecasts generated with point-in-time expanding history, filtered inference for C1, and train-fitted bins for C2.",
    ]
    (FORECAST_OUT_DIR / "holdout_forecast_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {"manifest": manifest, "metrics": metrics_payload, "artifacts": {
        "c1_csv": str(c1_csv), "c2_csv": str(c2_csv), "metrics_json": str(metrics_path), "manifest_json": str(manifest_path)
    }}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Protocol-enforcing holdout evaluation runner (refuses by default)")
    p.add_argument("--execute-holdout", action="store_true", help="Explicitly authorize holdout execution (required)")
    p.add_argument("--protocol-hash", type=str, default=None, help="SHA256 of frozen protocol file (required with --execute-holdout)")
    p.add_argument("--protocol-path", type=Path, default=PROTOCOL_PATH, help="Path to frozen protocol markdown")
    p.add_argument("--manifest-template", type=Path, default=MANIFEST_TEMPLATE_PATH, help="Path to manifest template JSON")
    p.add_argument("--data-path", type=Path, default=DATA_PATH, help="Path to processed features parquet")
    p.add_argument("--print-protocol-hash", action="store_true", help="Print expected protocol hash and exit")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.print_protocol_hash:
        print(compute_protocol_hash(args.protocol_path))
        return 0
    try:
        protocol_hash = verify_execution_authorized(
            execute_holdout=args.execute_holdout,
            provided_hash=args.protocol_hash,
            protocol_path=args.protocol_path,
        )
    except (HoldoutAuthorizationError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        return 2

    command = " ".join([Path(sys.argv[0]).name] + (list(argv) if argv is not None else sys.argv[1:]))
    result = execute_holdout(
        protocol_hash=protocol_hash,
        command=command,
        protocol_path=args.protocol_path,
        manifest_template_path=args.manifest_template,
        data_path=args.data_path,
    )
    print(json.dumps({"status": "executed", "protocol_sha256": protocol_hash, "artifacts": result["artifacts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
