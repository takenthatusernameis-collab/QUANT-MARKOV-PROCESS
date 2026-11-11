import numpy as np
import pandas as pd

from src.markov_chain_baseline import (
    TRAIN_END,
    VAL_END,
    VAL_START,
    HOLDOUT_START,
    assign_states,
    estimate_transition_counts,
    expanding_unconditional_params,
    fit_quantile_bins,
    load_btc_returns,
    run_markov_chain_walkforward,
    state_conditional_params,
    transition_probs_from_counts,
)


def test_fit_quantile_bins_increasing_and_fixed_on_train():
    rng = np.random.default_rng(0)
    train = rng.normal(0, 0.01, 5000)
    edges = fit_quantile_bins(train, k=5)
    assert len(edges) == 4
    assert np.all(np.diff(edges) > 0)
    # applying to other data does not change edges
    edges2 = fit_quantile_bins(train, k=5)
    assert np.allclose(edges, edges2)


def test_assign_states_range_and_deterministic():
    edges = np.array([-0.01, 0.0, 0.01])
    x = np.array([-0.02, -0.005, 0.005, 0.02])
    s = assign_states(x, edges)
    assert s.tolist() == [0, 1, 2, 3]
    s2 = assign_states(x, edges)
    assert np.array_equal(s, s2)


def test_transition_counts_and_probs_row_stochastic():
    states = np.array([0, 1, 1, 2, 2, 0, 1])
    counts = estimate_transition_counts(states, k=3)
    assert counts.shape == (3, 3)
    assert counts.sum() == len(states) - 1
    probs = transition_probs_from_counts(counts, alpha=1.0)
    assert probs.shape == (3, 3)
    assert np.allclose(probs.sum(axis=1), 1.0)
    assert np.all(probs > 0)  # Laplace smoothing


def test_state_conditional_params_fallback():
    hist_r = np.array([0.01, 0.02, -0.01, 0.0, 0.03])
    hist_s = np.array([0, 0, 1, 2, 2])
    mu, var = state_conditional_params(hist_r, hist_s, k=4, global_mu=0.001, global_var=0.0004, min_samples=2)
    assert mu.shape == (4,) and var.shape == (4,)
    # state 3 unseen -> global fallback
    assert np.isclose(mu[3], 0.001)
    assert var[3] >= 1e-10
    assert np.all(var > 0)


def test_expanding_unconditional_no_future():
    h1 = np.array([0.1, -0.2, 0.05])
    h2 = np.array([0.1, -0.2, 0.05, 10.0])
    mu1, v1 = expanding_unconditional_params(h1)
    mu2, v2 = expanding_unconditional_params(h2)
    assert mu2 != mu1 and v2 > v1


def test_walkforward_validation_only_no_holdout_and_shapes():
    df = load_btc_returns()
    # restrict to data up to validation end for speed and to ensure no holdout access by inputs
    df = df[df["timestamp"] <= VAL_END].copy()
    out = run_markov_chain_walkforward(df, k=5, eval_stride=24)
    payload = out["payload"]
    results = out["results"]
    assert payload["counts"]["validation_forecasts"] > 0
    for r in results:
        assert r.timestamp >= VAL_START
        assert r.timestamp <= VAL_END
        assert r.timestamp < HOLDOUT_START
        assert r.next_state_probs.shape == (5,)
        assert np.allclose(r.next_state_probs.sum(), 1.0, atol=1e-8)
        assert np.all(r.next_state_probs >= 0)
        assert np.isfinite(r.mc_mu)
        assert r.mc_var > 0
    m = payload["metrics"]
    assert "log_score_higher_is_better" in m
    assert "crps_lower_is_better" in m
    assert "bootstrap" in payload
