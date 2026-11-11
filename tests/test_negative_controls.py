import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.negative_controls import (
    bootstrap_mean,
    gaussian_crps,
    gaussian_logpdf,
    load_model_grid,
    stationary_bootstrap_indices,
    target_shuffled_scores,
    white_noise_scores,
)


def test_gaussian_scoring_finite_and_ordered():
    ls = gaussian_logpdf(np.array([0.0, 1.0]), np.array([0.0, 0.0]), np.array([1.0, 1.0]))
    assert ls.shape == (2,)
    assert np.all(np.isfinite(ls))
    assert ls[0] > ls[1]
    c0 = gaussian_crps(0.0, 0.0, 1.0)
    c1 = gaussian_crps(2.0, 0.0, 1.0)
    assert c0 >= 0.0 and c1 >= c0


def test_stationary_bootstrap_indices_shape_and_range():
    rng = np.random.default_rng(0)
    idx = stationary_bootstrap_indices(20, block_length=4.0, n_draws=5, rng=rng)
    assert idx.shape == (5, 20)
    assert idx.min() >= 0 and idx.max() < 20


def test_bootstrap_mean_ci_contains_point_estimate():
    vals = np.random.default_rng(1).normal(loc=0.5, scale=0.1, size=200)
    res = bootstrap_mean(vals, n_bootstrap=500, seed=7)
    assert res.n_obs == 200
    assert res.ci_lower <= res.mean <= res.ci_upper


def test_white_noise_scores_shapes():
    y = np.random.default_rng(3).normal(0.0, 0.02, size=100)
    log_score, crps, params = white_noise_scores(y)
    assert log_score.shape == (100,)
    assert crps.shape == (100,)
    assert np.all(np.isfinite(log_score)) and np.all(np.isfinite(crps))
    assert params["mu"] == 0.0 and params["var"] > 0


def test_target_shuffled_scores_shape_and_finite():
    mu = np.random.default_rng(4).normal(0.0, 1e-4, size=50)
    var = np.full(50, 1e-4)
    y = np.random.default_rng(5).normal(0.0, 0.02, size=50)
    sh_log, sh_crps = target_shuffled_scores(mu, var, y, n_shuffle=20, seed=0)
    assert sh_log.shape == (50,)
    assert sh_crps.shape == (50,)
    assert np.all(np.isfinite(sh_log)) and np.all(np.isfinite(sh_crps))


def test_load_model_grid_on_saved_hmm_grid():
    df = load_model_grid(Path("research/forecasts/h2_validation_forecasts.csv"), "hmm")
    assert len(df) == 1087
    assert set(["model_log_score", "model_crps", "unc_log_score", "ewma_log_score"]).issubset(df.columns)
    assert np.isfinite(df["model_log_score"]).all()
    ts = pd.to_datetime(df["timestamp"], utc=True)
    assert ts.min() >= pd.Timestamp("2024-01-01", tz="UTC")
    assert ts.max() < pd.Timestamp("2024-07-01", tz="UTC")


def test_artifacts_generated_and_holdout_not_used():
    out_json = Path("research/forecasts/negative_controls.json")
    out_md = Path("research/forecasts/negative_controls.md")
    assert out_json.exists() and out_md.exists()
    data = json.loads(out_json.read_text())
    assert data["holdout_used"] is False
    assert data["scope"] == "validation_only"
    assert len(data["models"]) == 2
    for m in data["models"]:
        assert m["holdout_used"] is False
        assert m["n_forecasts"] == 1087
        pd_ = m["paired_differences"]
        for key in [
            "real_minus_white_noise_log",
            "real_minus_shuffled_log",
            "shuffled_minus_white_noise_log",
        ]:
            r = pd_[key]
            assert "mean" in r and "ci_lower" in r and "ci_upper" in r and "p_value_two_sided" in r
