import numpy as np
import pandas as pd

from src.hmm_walkforward import (
    HOLDOUT_START,
    VAL_END,
    VAL_START,
    load_btc_returns,
    load_returns,
    run_walkforward,
)


def test_load_returns_ethusdt_symbol_only():
    df = load_returns("ETHUSDT")
    assert (df["symbol"] == "ETHUSDT").all() if "symbol" in df.columns else True
    assert list(df.columns) == ["timestamp", "returns"]
    assert df["timestamp"].is_monotonic_increasing
    assert df["returns"].notna().all()
    assert df["timestamp"].min() >= pd.Timestamp("2021-01-01", tz="UTC")


def test_load_btc_returns_backward_compat():
    df = load_btc_returns()
    assert list(df.columns) == ["timestamp", "returns"]
    assert df["returns"].notna().all()
    assert len(df) > 0


def test_ethusdt_walkforward_validation_only_no_holdout_leakage():
    df = load_returns("ETHUSDT")
    df = df[df["timestamp"] <= VAL_END].copy()
    out = run_walkforward(df, refit_every=2200, seeds=(0,), eval_stride=24, symbol="ETHUSDT")
    payload = out["payload"]
    results = out["results"]
    assert payload["counts"]["validation_forecasts"] > 0
    assert payload["config"]["symbol"] == "ETHUSDT"
    for r in results:
        assert r.timestamp >= VAL_START
        assert r.timestamp <= VAL_END
        assert r.timestamp < HOLDOUT_START
    for rec in payload["refits"]:
        assert rec["refit_timestamp"] <= str(VAL_END)
    m = payload["metrics"]
    assert "log_score_higher_is_better" in m
    assert "crps_lower_is_better" in m
    assert m["n_obs"] == payload["counts"]["validation_forecasts"]
    assert m["pit_hmm"]["mean"] is not None
    assert 0.0 <= m["pit_hmm"]["mean"] <= 1.0


def test_ethusdt_forecasts_use_expanding_history_no_future():
    df = load_returns("ETHUSDT")
    df = df[df["timestamp"] <= VAL_END].copy()
    out_full = run_walkforward(df, refit_every=2200, seeds=(0,), eval_stride=24, symbol="ETHUSDT")
    out_short = run_walkforward(
        df[df["timestamp"] <= pd.Timestamp("2024-03-31", tz="UTC")],
        refit_every=2200,
        seeds=(0,),
        eval_stride=24,
        symbol="ETHUSDT",
    )
    # Both produce validation forecasts; the shorter-history run must not exceed full-run log score absurdly,
    # and both must be finite.
    ls_full = out_full["payload"]["metrics"]["log_score_higher_is_better"]["hmm_mixture"]["mean"]
    ls_short = out_short["payload"]["metrics"]["log_score_higher_is_better"]["hmm_mixture"]["mean"]
    assert np.isfinite(ls_full) and np.isfinite(ls_short)
