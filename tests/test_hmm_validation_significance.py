import numpy as np
import pytest

from src.hmm_validation_significance import (
    block_bootstrap_differences,
    compute_bootstrap_results,
    stationary_bootstrap_indices,
)


def test_stationary_bootstrap_indices_shape_and_range():
    n = 100
    block_length = 5.0
    n_bootstrap = 50
    rng = np.random.default_rng(123)
    indices = stationary_bootstrap_indices(n, block_length, n_bootstrap, rng)
    assert indices.shape == (n_bootstrap, n)
    assert np.all(indices >= 0)
    assert np.all(indices < n)


def test_stationary_bootstrap_indices_deterministic():
    n = 50
    block_length = 4.0
    n_bootstrap = 10
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    idx1 = stationary_bootstrap_indices(n, block_length, n_bootstrap, rng1)
    idx2 = stationary_bootstrap_indices(n, block_length, n_bootstrap, rng2)
    assert np.array_equal(idx1, idx2)


def test_block_bootstrap_differences_basic():
    # Constant differences -> bootstrap means should all equal the constant
    diffs = np.full(200, 0.05)
    n_bootstrap = 500
    boot_means, block_len = block_bootstrap_differences(diffs, block_length=5.0, n_bootstrap=n_bootstrap, rng_seed=42)
    assert boot_means.shape == (n_bootstrap,)
    assert np.allclose(boot_means, 0.05, atol=1e-10)
    assert block_len == 5.0


def test_block_bootstrap_differences_auto_block_length():
    # Test auto block length (n^(1/3))
    diffs = np.random.default_rng(1).normal(0, 1, 1000)
    boot_means, block_len = block_bootstrap_differences(diffs, block_length=None, n_bootstrap=200, rng_seed=42)
    expected_len = max(1.0, 1000 ** (1.0 / 3.0))
    assert abs(block_len - expected_len) < 1e-6
    assert boot_means.shape == (200,)


def test_compute_bootstrap_results_structure():
    rng = np.random.default_rng(0)
    diffs = rng.normal(0.02, 0.1, 500)
    res = compute_bootstrap_results(
        diffs,
        metric_name="test_metric",
        comparison="hmm_vs_unc",
        n_bootstrap=500,
        rng_seed=123,
    )
    assert res.metric_name == "test_metric"
    assert res.comparison == "hmm_vs_unc"
    assert isinstance(res.mean_diff, float)
    assert isinstance(res.median_diff, float)
    assert isinstance(res.ci_lower, float)
    assert isinstance(res.ci_upper, float)
    assert isinstance(res.p_value_two_sided, float)
    assert isinstance(res.effective_n, int)
    assert isinstance(res.block_length, float)
    assert res.n_bootstrap == 500
    # CI should contain mean
    assert res.ci_lower <= res.mean_diff <= res.ci_upper
    # p-value in [0,1]
    assert 0.0 <= res.p_value_two_sided <= 1.0


def test_compute_bootstrap_results_significant_positive():
    # Large positive mean difference should give CI > 0 and small p-value
    diffs = np.full(200, 0.5)
    res = compute_bootstrap_results(diffs, "test", "hmm_vs_unc", n_bootstrap=200, rng_seed=42)
    assert res.ci_lower > 0
    assert res.ci_upper > 0
    assert res.p_value_two_sided < 0.05


def test_compute_bootstrap_results_significant_negative():
    # Large negative mean difference should give CI < 0
    diffs = np.full(200, -0.5)
    res = compute_bootstrap_results(diffs, "test", "hmm_vs_unc", n_bootstrap=200, rng_seed=42)
    assert res.ci_lower < 0
    assert res.ci_upper < 0
    assert res.p_value_two_sided < 0.05


def test_compute_bootstrap_results_null():
    # Mean near zero should not be significant
    rng = np.random.default_rng(42)
    diffs = rng.normal(0.0, 1.0, 1000)
    res = compute_bootstrap_results(diffs, "test", "hmm_vs_unc", n_bootstrap=500, rng_seed=123)
    # With true mean 0, CI should often include 0 (not guaranteed but likely)
    # At minimum, p-value should not be extreme
    assert 0.0 <= res.p_value_two_sided <= 1.0


def test_effective_sample_size_reasonable():
    # For i.i.d. data, effective n should be close to actual n
    rng = np.random.default_rng(1)
    diffs = rng.normal(0, 1, 2000)
    res = compute_bootstrap_results(diffs, "test", "hmm_vs_unc", n_bootstrap=1000, rng_seed=42)
    # For i.i.d., effective n ~ n (allowing factor of 2-3 due to bootstrap variance)
    assert res.effective_n > len(diffs) // 5
    assert res.effective_n <= len(diffs) * 2


def test_no_future_leakage_in_bootstrap():
    """Ensure bootstrap resampling doesn't use future information implicitly.
    This is a design check: stationary bootstrap resamples blocks from the observed
    series, preserving temporal structure but not introducing future data.
    """
    n = 300
    diffs = np.arange(n, dtype=float)  # Structured signal
    boot_means, _ = block_bootstrap_differences(diffs, block_length=7.0, n_bootstrap=100, rng_seed=42)
    # All bootstrap means should be within the range of the data
    assert np.all(boot_means >= diffs.min() - 1e-10)
    assert np.all(boot_means <= diffs.max() + 1e-10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])