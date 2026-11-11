# Exploratory Data Analysis & Regime Labeling (Task T2)

**Date:** 2026-11-11 01:19:25 UTC
**Symbol:** BTCUSDT
**Frequency:** 1-hour
**Model:** 3-State Gaussian HMM (diagonal covariance, regime identification constraint μ₁ < μ₂ < μ₃)

---

## 1. Data Summary

| Split | Period | Observations | Date Range |
|-------|--------|--------------|------------|
| Training | 70% | 26,256 | 2021-01-01 00:00:00+00:00 to 2023-12-31 00:00:00+00:00 |
| Validation | 15% | 4,345 | 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 |
| Holdout (Locked) | 15% | 13,176 | 2024-07-01 00:00:00+00:00 to 2025-12-31 23:00:00+00:00 |

---

## 2. HMM Model Estimates (Training Period)

### 2.1 Parameter Estimates

| State | Mean Return (μ) | Std Return (σ) | Initial Prob |
|-------|----------------|----------------|--------------|
| 0 (Low) | -0.000502 | 0.018283 | 1.000 |
| 1 (Medium) | 0.000003 | 0.002629 | 0.000 |
| 2 (High) | 0.000135 | 0.006583 | 0.000 |

**Log-likelihood:** 100885.83

### 2.2 Transition Matrices

**Model Transition Matrix (Estimated):**
```
| From/To | State 0 | State 1 | State 2 |
|---------|---------|---------|---------|
| State 0 | 0.711 | 0.000 | 0.289 |
| State 1 | 0.007 | 0.933 | 0.060 |
| State 2 | 0.052 | 0.075 | 0.873 |
```

**Empirical Transition Matrix (Train, Viterbi Path):**
```
| From/To | State 0 | State 1 | State 2 |
|---------|---------|---------|---------|
| State 0 | 0.805 | 0.000 | 0.195 |
| State 1 | 0.004 | 0.967 | 0.029 |
| State 2 | 0.022 | 0.037 | 0.942 |
```

---

## 3. Regime-Conditional Statistics (Training Period)

| Metric | State 0 (Low) | State 1 (Medium) | State 2 (High) | Overall |
|--------|---------------|------------------|----------------|---------|
| **Count** | 1,603 | 12,931 | 11,722 | 26,256 |
| **Occupancy %** | 6.1% | 49.2% | 44.6% | 100% |
| **Mean Return** | -0.000858 | -0.000015 | 0.000166 | 0.000014 |
| **Std Return** | 0.021087 | 0.002494 | 0.006747 | 0.007113 |
| **Skewness** | 0.013 | -0.100 | -0.030 | -0.165 |
| **Kurtosis** | 0.960 | 0.905 | 0.262 | 16.919 |
| **Ann. Sharpe** | -3.81 | -0.55 | 2.30 | — |

**State Interpretation:**
- **State 0 (Low):** Negative/low mean, volatility = 0.021087
- **State 1 (Medium):** Negative/low mean, volatility = 0.002494
- **State 2 (High):** Positive/low mean, volatility = 0.006747

---

## 4. Regime Persistence & Sojourn Distributions (Training)

| Metric | State 0 | State 1 | State 2 |
|--------|---------|---------|---------|
| **Spell Count** | 312 | 429 | 685 |
| **Mean Duration (hours)** | 5.1 | 30.1 | 17.1 |
| **Median Duration** | 2.0 | 17.0 | 10.0 |
| **Max Duration** | 77 | 548 | 141 |
| **Implied Persistence** | 0.805 | 0.967 | 0.942 |

**Expected Duration (from model diag):**
- State 0: 3.5 hours
- State 1: 14.9 hours
- State 2: 7.9 hours

---

## 5. Stationarity Tests (Chow-Type on Transition Matrices)

### 5.1 Train Period Split (First Half vs Second Half)

- **LR Statistic:** 307.2498
- **Degrees of Freedom:** 6
- **p-value:** 0.0000
- **Reject H₀ (Constant Transmat):** YES

**Period 1 Transition Matrix:**
```
State 0 | 0.839 | 0.000 | 0.161
State 1 | 0.007 | 0.945 | 0.048
State 2 | 0.023 | 0.021 | 0.956
```

**Period 2 Transition Matrix:**
```
State 0 | 0.596 | 0.000 | 0.404
State 1 | 0.003 | 0.974 | 0.022
State 2 | 0.018 | 0.078 | 0.905
```

### 5.2 Training vs Validation Period

- **LR Statistic:** 18.9749
- **Degrees of Freedom:** 6
- **p-value:** 0.0042
- **Reject H₀ (Constant Transmat):** YES

---

## 6. Filtered vs Smoothed Probability Gap (Critical Diagnostic)

> **Key Finding from Literature:** The gap between filtered (online) and smoothed (full-sample) regime probabilities is the #1 backtest trap for HMMs. This script reports a posterior-vs-MAP proxy gap using the fitted model on the observed sequence; a true online filtered-vs-smoothed comparison requires forward-only filtering and must be implemented in T4.

| Metric | Value |
|--------|-------|
| **Mean Posterior-vs-MAP Gap** | 0.1493 |
| **Max Posterior-vs-MAP Gap** | 0.6012 |
| **Assessment** | ✅ Low uncertainty proxy |

---

## 7. Regime Stability Checks (Forecast Validation Gate Criteria)

| Criterion | Threshold | Result | Pass/Fail |
|-----------|-----------|--------|-----------|
| **Min State Occupancy** | > 1% | State 0: 6.1%, State 1: 49.2%, State 2: 44.6% | ✅ PASS |
| **Min Transition Count** | > 10 per cell | Min count: 0 | ❌ FAIL |
| **Regime Flickering** | < 50% switches | N/A (not computed in this script) | **TODO** |

---

## 8. Visualizations

| Figure | Description | Path |
|--------|-------------|------|
| State Time Series (Full) | Returns with Viterbi states and filtered probabilities | `figures/state_timeseries_full.png` |
| State Time Series (Train) | Training period detail | `figures/state_timeseries_train.png` |
| Transition Heatmap (Train) | Empirical transition matrix | `figures/transmat_train.png` |
| Transition Heatmap (Model) | Estimated model transition matrix | `figures/transmat_model.png` |
| Transition Heatmap (Full) | Full sample empirical matrix | `figures/transmat_full.png` |
| Sojourn Distributions (Train) | Duration statistics by state | `figures/sojourn_train.png` |
| Sojourn Distributions (Full) | Full sample duration statistics | `figures/sojourn_full.png` |
| Regime Returns (Train) | Return distributions by state | `figures/regime_returns_train.png` |
| Regime Returns (Full) | Full sample return distributions | `figures/regime_returns_full.png` |
| Filtered vs Smoothed Gap | Critical diagnostic for real-time use | `figures/filtered_vs_smoothed_gap.png` |
| Rolling Occupancy | 30-day rolling state occupancy | `figures/rolling_occupancy.png` |

---

## 9. Conclusions & Implications for H2

### Summary of Findings

1. **Model Convergence:** 3-state Gaussian HMM converged successfully on ~3 years of 1h BTCUSDT returns (log-likelihood: 100885.83).

2. **Regime Identification:** States ordered by mean return (μ₁ < μ₂ < μ₃) as per research plan constraint.
   - State 0: Bear/Crash (μ=-0.000502, σ=0.018283)
   - State 1: Sideways/Neutral (μ=0.000003, σ=0.002629)
   - State 2: Bull/High Return (μ=0.000135, σ=0.006583)

3. **Regime Persistence:** High persistence across states (mean durations: 5h, 30h, 17h).

4. **Stationarity:** Transition matrix IS NOT stationary within training period (p=0.0000). Transition matrix IS NOT stationary from train to validation (p=0.0042).

5. **Real-Time Reliability:** Filtered vs smoothed gap is LARGE (mean=0.1493), suggesting poor real-time regime inference.

### Go/No-Go for H2 (Forecast Validation Gate)

| Gate Criterion | Status |
|----------------|--------|
| Calibration (Brier/Log-loss vs unconditional) | **TODO: Evaluate in T4** |
| Discrimination (CRPS/Log-score vs GARCH) | **TODO: Evaluate in T4** |
| State stability (occupancy > 1%, transitions > 10) | ❌ FAIL |
| Regime persistence (flickering < 50%) | **Requires filtered prob analysis in T4** |
| Robustness across sub-periods | ⚠️ REVIEW |

**Recommendation:** Proceed to **T4: HMM Implementation** for full walk-forward forecast validation. The regime structure shows mixed characteristics for predictive modeling.

---

## 10. Artifacts

- **Model:** `research/eda/hmm_model_train.pkl`
- **Results JSON:** `research/eda/regime_analysis_results.json`
- **Figures:** `research/eda/figures/`
- **Report:** `research/eda/regime_analysis.md`

---

*Generated by Task T2: Exploratory Data Analysis & Regime Labeling*
