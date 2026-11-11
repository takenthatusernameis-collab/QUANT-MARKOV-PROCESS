import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.validation_period_perturbation import (
    gaussian_crps,
    gaussian_logpdf,
    split_period,
    stationary_bootstrap_indices,
    bootstrap_mean,
    score_frame,
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
    idx = stationary_bootstrap_indices(20, block_length=4.0, n_bootstrap=5, rng=rng)
    assert idx.shape == (5, 20)
    assert idx.min() >= 0 and idx.max() < 20


def test_bootstrap_mean_ci_contains_point_estimate_reasonably():
    rng_vals = np.random.default_rng(1).normal(loc=0.5, scale=0.1, size=200)
    res = bootstrap_mean(rng_vals, n_bootstrap=500, seed=7)
    assert res.n_obs == 200
    assert res.ci_lower <= res.mean <= res.ci_upper


def test_split_period_and_score_frame_on_saved_hmm_grid():
    df = pd.read_csv("research/forecasts/h2_validation_forecasts.csv")
    parts = split_period(df)
    assert len(parts["Q1_2024"]) + len(parts["Q2_2024"]) == len(df)
    assert len(parts["Q1_2024"]) == 546
    assert len(parts["Q2_2024"]) == 541
    q1_scores = score_frame(parts["Q1_2024"], "hmm")
    assert set(["model_log_score", "model_crps", "d_log_model_minus_ewma"]).issubset(q1_scores.columns)
    assert np.isfinite(q1_scores["model_log_score"]).all()


def test_artifacts_generated_and_holdout_not_used():
    out_json = Path("research/forecasts/period_perturbation_q1q2.json")
    out_md = Path("research/forecasts/period_perturbation_q1q2.md")
    assert out_json.exists() and out_md.exists()
    data = json.loads(out_json.read_text())
    assert data["holdout_used"] is False
    assert data["scope"] == "validation_only"
    assert len(data["models"]) == 2
    # ensure dates stay in validation window
    for m in data["models"]:
        for p in m["periods"].values():
            assert p["time_start"].startswith("2024-0")
            assert p["time_end"].startswith("2024-0")
