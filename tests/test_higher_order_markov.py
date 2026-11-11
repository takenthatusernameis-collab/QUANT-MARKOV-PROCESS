import numpy as np
import pandas as pd

from src.higher_order_markov import (
    TRAIN_END,
    VAL_END,
    VAL_START,
    HOLDOUT_START,
    assign_states,
    estimate_transition_counts_order2,
    expanding_unconditional_params,
    fit_quantile_bins,
    load_btc_returns,
    run_higher_order_walkforward,
    state_conditional_params_order2,
    transition_probs_from_counts_order2,
)


def test_fit_quantile_bins_increasing_and_fixed_on_train():
    rng = np.random.default_rng(0)
    train = rng.normal(0, 0.01, 5000)
    edges = fit_quantile_bins(train, k=5)
    assert len(edges) == 4
    assert np.all(np.diff(edges) > 0)
    edges2 = fit_quantile_bins(train, k=5)
    assert np.allclose(edges, edges2)


def test_assign_states_range_and_deterministic():
    edges = np.array([-0.01, 0.0, 0.01])
    x = np.array([-0.02, -0.005, 0.005, 0.02])
    s = assign_states(x, edges)
    assert s.tolist() == [0, 1, 2, 3]
    assert np.array_equal(s, assign_states(x, edges))


def test_order2_transition_counts_shape_and_stochastic():
    states = np.array([0, 1, 1, 2, 2, 0, 1, 0])
    counts = estimate_transition_counts_order2(states, k=3)
    assert counts.shape == (3, 3, 3)
    # transitions (s_{u-1},s_u)->s_{u+1} for u=1..m-2 => m-2 transitions
    assert counts.sum() == len(states) - 2
    probs = transition_probs_from_counts_order2(counts, alpha=1.0)
    assert probs.shape == (3, 3, 3)
    for a in range(3):
        for b in range(3):
            assert np.allclose(probs[a, b, :].sum(), 1.0)
            assert np.all(probs[a, b, :] > 0)  # Laplace smoothing


def test_order2_state_conditional_shape_and_fallback():
    hist_r = np.array([0.01, 0.02, -0.01, 0.0, 0.03, 0.01, -0.02])
    hist_s = np.array([0, 0, 1, 2, 2, 0, 1])
    mu, var = state_conditional_params_order2(
        hist_r, hist_s, k=3, global_mu=0.001, global_var=0.0004, min_samples=2
    )
    assert mu.shape == (3, 3) and var.shape == (3, 3)
    assert np.all(var > 0)
    assert np.all(np.isfinite(mu))


def test_expanding_unconditional_no_future():
    h1 = np.array([0.1, -0.2, 0.05])
    h2 = np.array([0.1, -0.2, 0.05, 10.0])
    mu1, v1 = expanding_unconditional_params(h1)
    mu2, v2 = expanding_unconditional_params(h2)
    assert mu2 != mu1 and v2 > v1


def test_walkforward_validation_only_no_holdout_and_shapes():
    df = load_btc_returns()
    df = df[df["timestamp"] <= VAL_END].copy()
    out = run_higher_order_walkforward(df, k=5, eval_stride=24)
    payload = out["payload"]
    results = out["results"]
    assert payload["counts"]["validation_forecasts"] > 0
    assert payload["config"]["n_pairs"] == 25
    for r in results:
        assert r.timestamp >= VAL_START
        assert r.timestamp <= VAL_END
        assert r.timestamp < HOLDOUT_START
        assert r.next_state_probs.shape == (5,)
        assert np.allclose(r.next_state_probs.sum(), 1.0, atol=1e-8)
        assert np.all(r.next_state_probs >= 0)
        assert np.isfinite(r.hom_mu)
        assert r.hom_var > 0
    m = payload["metrics"]
    assert "log_score_higher_is_better" in m
    assert "crps_lower_is_better" in m
    assert "bootstrap" in payload
    assert "pit_higher_order_markov" in m
