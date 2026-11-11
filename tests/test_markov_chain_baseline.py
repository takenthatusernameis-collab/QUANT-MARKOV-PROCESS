import numpy as np
import pandas as pd
import pytest

from src.markov_chain_baseline import (
    TRAIN_END,
    VAL_END,
    VAL_START,
    discretize_returns,
    estimate_transition_matrix,
    expanding_unconditional_params,
    forecast_next_state_probs,
    load_btc_returns,
    run_markov_chain_walkforward,
)


def test_discretize_quantile_ordering():
    rng = np.random.default_rng(0)
    x = np.concatenate([
        rng.normal(-0.01, 0.02, 400),
        rng.normal(0.0, 0.005, 400),
        rng.normal(0.01, 0.01, 400),
    ])
    labels, means, vars_ = discretize_returns(x, n_states=3, method="quantile")
    assert labels.shape == (len(x),)
    assert means.shape == (3,)
    assert vars_.shape == (3,)
    assert means[0] <= means[1] <= means[2]
    assert np.all(vars_ > 0)
    assert np.all(labels >= 0) and np.all(labels < 3)


def test_discretize_kmeans_ordering():
    rng = np.random.default_rng(1)
    x = np.concatenate([
        rng.normal(-0.01, 0.02, 400),
        rng.normal(0.0, 0.005, 400),
        rng.normal(0.01, 0.01, 400),
    ])
    labels, means, vars_ = discretize_returns(x, n_states=3, method="kmeans")
    assert labels.shape == (len(x),)
    assert means.shape == (3,)
    assert vars_.shape == (3,)
    assert means[0] <= means[1] <= means[2]
    assert np.all(vars_ > 0)
    assert np.all(labels >= 0) and np.all(labels < 3)


def test_discretize_kmeans_deterministic():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 0.01, 600)
    labels1, means1, vars1 = discretize_returns(x, n_states=3, method="kmeans", random_state=42)
    labels2, means2, vars2 = discretize_returns(x, n_states=3, method="kmeans", random_state=42)
    assert np.array_equal(labels1, labels2)
    assert np.allclose(means1, means2)
    assert np.allclose(vars1, vars2)


def test_transition_matrix_shape_and_stochastic():
    labels = np.array([0, 1, 2, 0, 1, 1, 2, 2, 0], dtype=int)
    transmat = estimate_transition_matrix(labels, n_states=3)
    assert transmat.shape == (3, 3)
    assert np.allclose(transmat.sum(axis=1), 1.0, atol=1e-8)
    assert np.all(transmat >= 0)
    # Check specific transitions
    # 0 -> 1 occurs once, 0 -> 2 occurs once (from 0,1,2,0... last 0 has no next)
    # With pseudocounts, row 0 should have mass on 1 and 2
    assert transmat[0, 1] > 0
    assert transmat[0, 2] > 0


def test_forecast_next_state_probs():
    transmat = np.array([
        [0.8, 0.1, 0.1],
        [0.2, 0.7, 0.1],
        [0.1, 0.2, 0.7],
    ])
    probs = forecast_next_state_probs(0, transmat)
    assert probs.shape == (3,)
    assert np.allclose(probs.sum(), 1.0, atol=1e-8)
    assert np.allclose(probs, transmat[0])


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
    out = run_markov_chain_walkforward(df, n_states=3, discretization="quantile", refit_every=2200, eval_stride=24)
    payload = out["payload"]
    results = out["results"]
    assert payload["counts"]["validation_forecasts"] > 0
    for r in results:
        assert r.timestamp >= VAL_START
        assert r.timestamp <= VAL_END
        assert r.timestamp < pd.Timestamp("2024-07-01 00:00:00", tz="UTC")
    for rec in payload["refits"]:
        assert rec["refit_timestamp"] <= str(VAL_END)
        assert rec["train_size"] >= (df["timestamp"] <= TRAIN_END).sum()
    m = payload["metrics"]
    assert "log_score_higher_is_better" in m
    assert "crps_lower_is_better" in m
    assert m["n_obs"] == payload["counts"]["validation_forecasts"]


def test_walkforward_kmeans_config():
    df = load_btc_returns()
    df = df[df["timestamp"] <= VAL_END].copy()
    out = run_markov_chain_walkforward(df, n_states=5, discretization="kmeans", refit_every=2200, eval_stride=24)
    payload = out["payload"]
    assert payload["counts"]["validation_forecasts"] > 0
    assert payload["config"]["n_states"] == 5
    assert payload["config"]["discretization"] == "kmeans"


def test_walkforward_different_n_states():
    df = load_btc_returns()
    df = df[df["timestamp"] <= VAL_END].copy()
    for k in [3, 5, 7]:
        out = run_markov_chain_walkforward(df, n_states=k, discretization="quantile", refit_every=2200, eval_stride=24)
        payload = out["payload"]
        assert payload["counts"]["validation_forecasts"] > 0
        assert payload["config"]["n_states"] == k
        # Check state probabilities dimension
        for r in out["results"]:
            assert len(r.mc_state_probs_next) == k
            assert len(r.mc_state_means) == k
            assert len(r.mc_state_vars) == k


if __name__ == "__main__":
    pytest.main([__file__, "-v"])