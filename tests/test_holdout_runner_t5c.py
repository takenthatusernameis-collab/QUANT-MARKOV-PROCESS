import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import holdout_runner as hr


def _synthetic_features_df():
    # train (<=2023-12-31) + holdout timestamps; small but sufficient for fixtures
    train_ts = pd.date_range("2023-12-01 00:00:00", periods=600, freq="1h", tz="UTC")
    holdout_ts = pd.date_range("2024-07-01 00:00:00", periods=40, freq="1h", tz="UTC")
    ts = train_ts.append(holdout_ts)
    # simple random-walk prices
    rng = np.random.default_rng(123)
    rets = rng.normal(0, 0.001, size=len(ts))
    close = 30000.0 * np.exp(np.cumsum(rets))
    df = pd.DataFrame({
        "timestamp": ts,
        "symbol": "BTCUSDT",
        "close": close,
        "funding_rate": np.where(np.arange(len(ts)) % 8 == 0, 0.0001, np.nan),
    })
    return df


def test_bootstrap_paired_differences_deterministic_and_significant():
    rng = np.random.default_rng(0)
    diffs = rng.normal(0.05, 0.01, size=200)  # clearly positive mean
    res = hr.bootstrap_paired_differences(diffs, n_bootstrap=500, block_length=5.0, rng_seed=7)
    assert res["n"] == 200
    assert res["mean_difference"] > 0
    assert res["ci_lower"] > 0
    assert res["p_value_two_sided"] <= 0.05
    assert res["effective_sample_size"] > 0
    # deterministic given seed
    res2 = hr.bootstrap_paired_differences(diffs, n_bootstrap=500, block_length=5.0, rng_seed=7)
    assert res["ci_lower"] == res2["ci_lower"]
    assert res["ci_upper"] == res2["ci_upper"]


def test_bootstrap_paired_differences_insignificant_near_zero():
    rng = np.random.default_rng(1)
    diffs = rng.normal(0.0, 0.02, size=200)
    res = hr.bootstrap_paired_differences(diffs, n_bootstrap=500, block_length=5.0, rng_seed=9)
    assert res["n"] == 200
    assert res["ci_lower"] <= 0 <= res["ci_upper"]
    assert res["p_value_two_sided"] > 0.05


def test_compute_forecast_significance_outputs_structure():
    rows = []
    rng = np.random.default_rng(2)
    for i in range(60):
        rows.append({
            "y_true": float(rng.normal(0, 0.001)),
            "m_log": float(-1.0 + rng.normal(0.01, 0.001)),
            "unc_log": float(-1.0),
            "ewma_log": float(-1.0),
            "m_crps": float(0.001 - rng.normal(0.0001, 0.00001)),
            "unc_crps": float(0.001),
            "ewma_crps": float(0.001),
            "m_mu": 0.0,
            "m_var": 1e-6,
        })
    # adapt keys to prefix 'm'
    sig = hr.compute_forecast_significance(rows, "m", n_bootstrap=200)
    assert sig["n"] == 60
    assert "pit" in sig and "mean" in sig["pit"]
    comps = sig["comparisons"]
    for k in ["log_score_model_minus_unconditional", "log_score_model_minus_ewma",
              "crps_unconditional_minus_model", "crps_ewma_minus_model"]:
        assert k in comps
        assert "mean_difference" in comps[k]
        assert "ci_lower" in comps[k] and "ci_upper" in comps[k]
        assert "p_value_two_sided" in comps[k]
        assert "effective_sample_size" in comps[k]


def test_manifest_includes_artifacts_field(tmp_path):
    p = tmp_path / "protocol.md"
    p.write_text("content", encoding="utf-8")
    tpath = tmp_path / "tmpl.json"
    tpath.write_text(json.dumps({"protocol": {}, "data_provenance": {}, "execution": {"holdout_evaluated": False}}), encoding="utf-8")
    template = json.loads(tpath.read_text())
    protocol_hash = hr.compute_protocol_hash(p)
    manifest = hr.build_execution_manifest(
        template=template,
        protocol_hash=protocol_hash,
        command="cmd",
        executed_utc="2026-11-11T00:00:00Z",
        git_sha="abc",
        features_sha256="f",
        raw_manifest_sha256="r",
        holdout_evaluated=True,
        artifacts={"a": "b"},
    )
    assert manifest["execution"]["artifacts"] == {"a": "b"}
    assert manifest["execution"]["holdout_evaluated"] is True


def test_evaluate_economic_holdout_writes_artifacts(tmp_path):
    df = _synthetic_features_df()
    # small synthetic forecast rows within holdout
    holdout_ts = pd.date_range("2024-07-01 00:00:00", periods=20, freq="4h", tz="UTC")
    rng = np.random.default_rng(3)
    y = rng.normal(0, 0.001, size=len(holdout_ts))
    rows = []
    for t, yt in zip(holdout_ts, y):
        rows.append({
            "timestamp": str(t), "y_true": float(yt),
            "hmm_mu": float(rng.normal(0, 0.0005)), "hmm_var": 1e-6,
            "unc_mu": 0.0, "unc_var": 1e-6, "ewma_mu": 0.0, "ewma_var": 1e-6,
        })
    forecast_rows_by_model = {"C1": rows, "C2": []}
    out = hr.evaluate_economic_holdout(forecast_rows_by_model, df, output_dir=tmp_path, theta_values=(0.0, 2.0))
    assert "C1" in out["models"]
    assert "theta_0.0bps" in out["models"]["C1"]
    assert "base" in out["models"]["C1"]["theta_0.0bps"]
    assert (tmp_path / "holdout_economic_results.json").exists()
    assert (tmp_path / "holdout_economic_report.md").exists()
    # trade/returns artifacts for base/stress and both thetas
    for theta in (0.0, 2.0):
        for cost in ("base", "stress"):
            assert (tmp_path / f"C1_theta{theta}bps_{cost}_trades.csv").exists()
            assert (tmp_path / f"C1_theta{theta}bps_{cost}_returns.csv").exists()


def test_execute_holdout_still_refused_without_authorization(tmp_path, monkeypatch, capsys):
    # ensure main/verify path not bypassed by new wiring
    p = tmp_path / "protocol.md"; p.write_text("content", encoding="utf-8")
    t = tmp_path / "tmpl.json"; t.write_text(json.dumps({"protocol":{},"data_provenance":{},"execution":{}}), encoding="utf-8")
    rc = hr.main(["--protocol-path", str(p), "--manifest-template", str(t)])
    assert rc == 2
    assert "refused" in capsys.readouterr().err.lower()


def test_main_requires_hash_with_execute(tmp_path, capsys):
    p = tmp_path / "protocol.md"; p.write_text("content", encoding="utf-8")
    t = tmp_path / "tmpl.json"; t.write_text(json.dumps({"protocol":{},"data_provenance":{},"execution":{}}), encoding="utf-8")
    rc = hr.main(["--execute-holdout", "--protocol-path", str(p), "--manifest-template", str(t)])
    assert rc == 2
    assert "protocol-hash" in capsys.readouterr().err.lower() or "hash" in capsys.readouterr().err.lower()
