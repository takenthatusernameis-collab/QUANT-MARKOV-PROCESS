import numpy as np
import pandas as pd

from src.hmm_walkforward import (
    TRAIN_END,
    VAL_END,
    VAL_START,
    expanding_unconditional_params,
    filtered_state_probs,
    fit_ordered_hmm,
    forecast_next_from_filtered,
    load_btc_returns,
    reorder_hmm_by_mean,
    run_walkforward,
)


def test_fit_ordered_hmm_means_sorted():
    rng = np.random.default_rng(0)
    x = np.concatenate([
        rng.normal(-0.01, 0.02, 400),
        rng.normal(0.0, 0.005, 400),
        rng.normal(0.01, 0.01, 400),
    ])
    model = fit_ordered_hmm(x, seeds=(0, 1))
    means = model.means_.reshape(-1)
    assert means.shape[0] == 3
    assert means[0] <= means[1] <= means[2]


def test_filtered_probs_shape_and_simplex():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.01, 600)
    model = fit_ordered_hmm(x, seeds=(0, 1))
    probs = filtered_state_probs(model, x)
    assert probs.shape == (len(x), 3)
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-6)
    assert np.all(probs >= 0)


def test_forecast_next_uses_transition_and_sums_to_one():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 0.01, 600)
    model = fit_ordered_hmm(x, seeds=(0, 1))
    filt_t = filtered_state_probs(model, x)[-1]
    next_probs, means, vars_ = forecast_next_from_filtered(model, filt_t)
    assert next_probs.shape == (3,)
    assert np.allclose(next_probs.sum(), 1.0, atol=1e-8)
    assert means.shape == (3,)
    assert vars_.shape == (3,)
    assert np.all(vars_ > 0)
    manual = filt_t @ model.transmat_
    manual = manual / manual.sum()
    assert np.allclose(next_probs, manual, atol=1e-8)


def test_expanding_unconditional_params_no_future():
    hist1 = np.array([0.1, -0.2, 0.05])
    hist2 = np.array([0.1, -0.2, 0.05, 10.0])
    mu1, var1 = expanding_unconditional_params(hist1)
    mu2, var2 = expanding_unconditional_params(hist2)
    assert mu2 != mu1
    assert var2 > var1


def test_walkforward_validation_only_and_no_holdout_leakage():
    df = load_btc_returns()
    df = df[df["timestamp"] <= VAL_END].copy()
    out = run_walkforward(df, refit_every=2200, seeds=(0,), eval_stride=24)
    payload = out["payload"]
    results = out["results"]
    assert payload["counts"]["validation_forecasts"] > 0
    # all forecast targets must be in validation window and before holdout
    for r in results:
        assert r.timestamp >= VAL_START
        assert r.timestamp <= VAL_END
        assert r.timestamp < pd.Timestamp("2024-07-01 00:00:00", tz="UTC")
    # refits must be trained on data up to a point <= val end and after initial train
    for rec in payload["refits"]:
        assert rec["refit_timestamp"] <= str(VAL_END)
        assert rec["train_size"] >= (df["timestamp"] <= TRAIN_END).sum()
    # metrics present
    m = payload["metrics"]
    assert "log_score_higher_is_better" in m
    assert "crps_lower_is_better" in m
    assert m["n_obs"] == payload["counts"]["validation_forecasts"]
