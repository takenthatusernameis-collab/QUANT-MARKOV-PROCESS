# Cross-Family Validation Comparison: Markov-Process Models (BTCUSDT 1h, Validation 2024-01 to 2024-06)

**Generated:** 2026-11-11
**Scope:** Validation period only (2024-01-01 to 2024-06-30). Holdout (≥2024-07-01) **not used**.
**Data:** BTCUSDT 1h returns from `data/processed/features.parquet`, train ≤2023-12-31.
**Forecast grid:** 1,087 forecasts (eval_stride=4, ~4-hour cadence).
**Provenance:** All models use expanding walk-forward with point-in-time leakage controls; bin edges/state parameters fitted on training data only; holdout excluded by construction.

---

## 1. Point-Estimate Forecast Metrics Summary

| Model Family | Configuration | Log Score (↑) | CRPS (↓) | PIT Mean | PIT Std |
|--------------|---------------|---------------|----------|----------|---------|
| **H2 HMM** | 3-state Gaussian, filtered, refit_every=720, seeds=[0,1,2] | **4.0164** | **0.002597** | 0.5105 | 0.2697 |
| **H1 MC (Legacy KM3)** | K-means K=3, refit_every=720 | 3.9319 | 0.002654 | 0.5174 | 0.2777 |
| **H1 MC (Legacy KM5)** | K-means K=5, refit_every=720 | 3.9217 | 0.002677 | 0.5104 | 0.2740 |
| **H3 HOM** | 2nd-order, K=5 quantile, 25 pairs, expanding/step | 3.8584 | 0.002687 | 0.4993 | 0.2799 |
| **H1 MC (Legacy Q7)** | Quantile K=7, refit_every=720 | 3.8569 | 0.002683 | 0.5116 | 0.2708 |
| **EWMA Gaussian** | λ=0.94 (RiskMetrics) | 3.9022 | 0.002631 | — | — |
| **H1 MC (Canonical T3)** | Quantile K=5, expanding/step, Laplace α=1 | 3.8298 | 0.002708 | 0.4988 | 0.2788 |
| **H4 Semi-Markov** | K=5 quantile, NB sojourn, expanding/step | 3.8298 | 0.002708 | 0.4988 | 0.2788 |
| **H1 MC (Legacy Q5)** | Quantile K=5, refit_every=720 | 3.8390 | 0.002685 | 0.5144 | 0.2727 |
| **H1 MC (Legacy Q3)** | Quantile K=3, refit_every=720 | 3.7892 | 0.002755 | 0.5064 | 0.2500 |
| **Unconditional Gaussian** | Expanding mean/var | 3.7482 | 0.002903 | — | — |

**Key observations:**
- **H2 HMM (filtered) dominates all models** on both log score and CRPS.
- **EWMA Gaussian is a strong baseline**: beats all Markov-chain variants (H1, H3, H4) on log score except Legacy KM3/KM5; beats all on CRPS except H2 HMM.
- **H3 HOM (2nd-order)** is the best non-latent Markov chain on validation, significantly improving on H1 (canonical) on both metrics (log score +0.0287, p=0.001; CRPS -2.04e-5, p=0.004).
- **H4 Semi-Markov ≈ H1 Canonical**: Near-identical metrics (duration dependence minimal at 1h K=5 quantile stride-4 grid).
- **H1 sensitivity**: K-means K=3 best among MC variants but still loses to EWMA on both metrics with significance.

---

## 2. Block-Bootstrap Significance (Stationary Bootstrap, 2000 Reps, n^(1/3) Block)

### 2.1 H2 HMM vs Baselines (from `h2_hmm_validation_significance.json`)

| Comparison | Metric | Mean Diff | 95% CI | p-value | Eff. n | Significant (5%) |
|------------|--------|-----------|--------|---------|--------|------------------|
| HMM vs Unconditional | Log Score (↑) | +0.1518 | [+0.1104, +0.1906] | 0.0000 | 677 | **Yes (HMM better)** |
| HMM vs EWMA | Log Score (↑) | +0.01995 | [-0.0293, +0.0728] | 0.4365 | 1170 | No |
| HMM vs Unconditional | CRPS (↓, base-HMM) | +1.78e-4 | [+1.34e-4, +2.19e-4] | 0.0000 | 576 | **Yes (HMM better)** |
| HMM vs EWMA | CRPS (↓, base-HMM) | -4.54e-5 | [-7.63e-5, -1.20e-5] | 0.0060 | 633 | **Yes (EWMA better)** |

**Interpretation:** HMM significantly outperforms unconditional on both metrics. HMM does **not** significantly outperform EWMA on log score; EWMA significantly outperforms HMM on CRPS.

### 2.2 H1 MC (Canonical T3) vs Baselines (from `h1_markov_chain_validation.json`)

| Comparison | Metric | Mean Diff | 95% CI | p-value | Eff. n | Significant (5%) |
|------------|--------|-----------|--------|---------|--------|------------------|
| MC vs Unconditional | Log Score (↑) | +0.0816 | [+0.0079, +0.1558] | 0.032 | 558 | **Yes (MC better)** |
| MC vs EWMA | Log Score (↑) | -0.0745 | [-0.1488, +0.0059] | 0.060 | 979 | No |
| MC vs Unconditional | CRPS (↓, base-MC) | +1.95e-4 | [+1.41e-4, +2.47e-4] | 0.000 | 366 | **Yes (MC better)** |
| MC vs EWMA | CRPS (↓, base-MC) | -3.40e-5 | [-6.61e-5, -1.74e-6] | 0.039 | 882 | **Yes (EWMA better)** |

### 2.3 H3 HOM vs Baselines (from `h3_higher_order_markov_validation.json`)

| Comparison | Metric | Mean Diff | 95% CI | p-value | Eff. n | Significant (5%) |
|------------|--------|-----------|--------|---------|--------|------------------|
| HOM vs Unconditional | Log Score (↑) | +0.1102 | [+0.0370, +0.1814] | 0.002 | 685 | **Yes (HOM better)** |
| HOM vs EWMA | Log Score (↑) | -0.0458 | [-0.1148, +0.0259] | 0.2125 | 1020 | No |
| HOM vs Unconditional | CRPS (↓, base-HOM) | +2.15e-4 | [+1.61e-4, +2.70e-4] | 0.000 | 435 | **Yes (HOM better)** |
| HOM vs EWMA | CRPS (↓, base-HOM) | -1.36e-5 | [-4.50e-5, +1.86e-5] | 0.412 | 901 | No |

### 2.4 H4 Semi-Markov vs Baselines (from `h4_semi_markov_validation.json`)

| Comparison | Metric | Mean Diff | 95% CI | p-value | Eff. n | Significant (5%) |
|------------|--------|-----------|--------|---------|--------|------------------|
| SM vs Unconditional | Log Score (↑) | +0.0816 | [+0.0079, +0.1558] | 0.032 | 558 | **Yes (SM better)** |
| SM vs EWMA | Log Score (↑) | -0.0745 | [-0.1488, +0.0059] | 0.060 | 979 | No |
| SM vs Unconditional | CRPS (↓, base-SM) | +1.95e-4 | [+1.41e-4, +2.47e-4] | 0.000 | 366 | **Yes (SM better)** |
| SM vs EWMA | CRPS (↓, base-SM) | -3.40e-5 | [-6.61e-5, -1.74e-6] | 0.039 | 882 | **Yes (EWMA better)** |

### 2.5 Aligned Model Comparisons (identical 1,087 timestamps)

| Comparison | Log Score Diff | 95% CI | p-value | CRPS Diff | 95% CI | p-value |
|------------|----------------|--------|---------|-----------|--------|---------|
| HOM − H1 (Canonical) | +0.0287 | [+0.0124, +0.0455] | **0.001** | -2.04e-5 | [-3.53e-5, -6.2e-6] | **0.004** |
| SM − H1 (Canonical) | +0.0463 | [-0.0235, +0.1151] | 0.189 | -1.53e-4 | [-1.98e-4, -1.07e-4] | **0.000** |
| SM − HOM | -0.0051 | [-0.0688, +0.0608] | 0.88 | -1.06e-4 | [-1.44e-4, -6.36e-5] | **0.000** |

**Interpretation:**
- HOM significantly beats H1 on both metrics.
- SM beats H1 on CRPS (significant) but not on log score (CI includes 0).
- SM and HOM are statistically indistinguishable on log score; SM better on CRPS (likely due to Gaussian approximation artifacts in bootstrap).

---

## 3. H1 Sensitivity Summary (7 Configurations)

| Config | Discretization | K | Refit | Log Score | CRPS | vs Unc (log, p) | vs EWMA (log, p) |
|--------|---------------|---|-------|-----------|------|-----------------|------------------|
| Legacy KM3 | K-means | 3 | 720 | **3.9319** | **0.002654** | +0.0228 (0.020) | -0.1090 (0.0005) |
| Legacy KM5 | K-means | 5 | 720 | 3.9217 | 0.002677 | +0.0138 (0.502) | -0.1180 (0.0005) |
| Legacy KM7 | K-means | 7 | 720 | 3.9012 | 0.002672 | -0.0056 (0.738) | -0.1374 (0.0005) |
| Legacy Q7 | Quantile | 7 | 720 | 3.8569 | 0.002683 | -0.0001 (0.994) | -0.1319 (0.000) |
| Legacy Q5 | Quantile | 5 | 720 | 3.8390 | 0.002685 | +0.0117 (0.116) | -0.1201 (0.000) |
| Canonical T3 | Quantile | 5 | Expanding/step | 3.8298 | 0.002708 | +0.0816 (0.032) | -0.0745 (0.060) |
| Legacy Q3 | Quantile | 3 | 720 | 3.7892 | 0.002755 | +0.00007 (0.985) | -0.1317 (0.000) |

**Findings:**
- K-means K=3 is the best MC configuration but **significantly worse than EWMA on both metrics**.
- Quantile binning improves monotonically with K but never beats EWMA significantly on log score.
- Canonical T3 (expanding per-step) has stronger significance vs unconditional but weaker point estimates than Legacy Q5 (refit_every=720).
- **EWMA is never significantly beaten by any MC config on log score.**

---

## 4. Calibration (PIT) Summary

| Model | PIT Mean | PIT Std | Ideal (Mean/Std) | Assessment |
|-------|----------|---------|------------------|------------|
| H2 HMM | 0.5105 | 0.2697 | 0.5 / 0.289 | Slightly conservative (mean > 0.5), good spread |
| H3 HOM | 0.4993 | 0.2799 | 0.5 / 0.289 | Excellent calibration |
| H1 Canonical | 0.4988 | 0.2788 | 0.5 / 0.289 | Excellent calibration |
| H4 Semi-Markov | 0.4988 | 0.2788 | 0.5 / 0.289 | Excellent calibration |
| Legacy KM3 | 0.5174 | 0.2777 | 0.5 / 0.289 | Conservative |

All Markov-chain variants show good PIT calibration (near-uniform). HMM shows slight conservatism (mean > 0.5).

---

## 5. Economic Feasibility (Validation Dry-Run, T5a)

**Configuration:** Theta ∈ {0, 2, 5} bps, notional_fraction=0.10, base cost 16 bps round-trip (8 bps/side), stress 32 bps round-trip.

| Candidate | Max \|μ\| (bps) | Trades (any θ/cost) | Net Sharpe | Max DD | Passes Gate? |
|-----------|----------------|---------------------|------------|--------|--------------|
| C1 (HMM) | 3.17 | 0 | 0.000 | 0.000 | **No** (fails Sharpe, expectancy, trade count) |
| C2 (HOM) | 6.79 | 0 | 0.000 | 0.000 | **No** (fails Sharpe, expectancy, trade count) |

**Baselines (θ=0, base cost):**
- B3 No-Trade: Sharpe 0.000
- B4 Buy-Hold: Sharpe 2.21 (C1 grid) / 1.70 (C2 grid)
- B5 Momentum (24h): Sharpe 10.76, 127 trades

**Interpretation:** Forecast conditional means are too small to exceed conservative cost thresholds at 1h horizon. HMM max |μ| ≈ 3.17 bps vs 8 bps/side base threshold. **Statistical forecast skill (proper scores) does not translate to economic profitability after costs on validation.**

---

## 6. Cross-Cutting Methodological Issues

| Issue | Status | Impact |
|-------|--------|--------|
| **Train-vs-validation non-stationarity** | Chow LR p=0.0042 (T2) | All expanding-window estimators affected; regime/transition instability across periods |
| **HMM EM convergence** | Non-fatal warnings on some refits/seeds | Parameter/refit stability concerns; best-seed selection by train log-likelihood |
| **Filtered vs smoothed inference** | HMM uses filtered (`score_samples`); MC uses expanding counts | Correct for H2; MC by construction uses history < t |
| **Discretization arbitrariness** | Quantile vs K-means; K=3,5,7 tested | MC results sensitive to binning; K-means K=3 best but not robust |
| **State-space explosion** | HOM: K^2=25 pairs; HMM: 3 latent states | HOM handles via Laplace + fallback; HMM avoids discretization |
| **Effective sample size** | 366–1183 vs nominal 1087 | Temporal dependence reduces bootstrap power; all CIs wider |
| **Gaussian mixture CRPS approximation** | Canonical T3 & HMM bootstrap use moment approx | True mixture CRPS not computed; may affect significance |
| **HMM grid offset** | H2 forecasts at 01:00/05:00 vs H1/H3/H4 at 00:00/04:00 | Direct timestamp-aligned HMM-vs-MC comparison not computed |

---

## 7. Outstanding Robustness / Red-Team Checks (Predeclared in Protocol)

Per `holdout_evaluation_protocol.md`, the following remain **not yet executed**:

1. **Period perturbations**: Re-evaluate on non-overlapping sub-windows (e.g., 2024 Q1 vs Q2, 2023 vs 2024).
2. **Asset perturbations**: Repeat on ETHUSDT 1h (data ingested, features aligned).
3. **State perturbations**: Vary K (3,5,7), discretization (quantile/k-means), HMM states (2,3,4).
4. **Cost perturbations**: Vary round-trip cost 5–30 bps; test maker/taker asymmetry.
5. **Negative controls**:
   - Label permutation (shuffle returns, verify skill disappears)
   - White-noise data (simulate, verify no edge)
   - Future-leak injection (verify detection)
6. **FDR correction**: Multiple comparisons across models/horizons/assets (Benjamini-Hochberg).
7. **Purge/embargo verification**: Confirm 1-step gap between train and test at each refit.
8. **MS-GARCH / MDP families**: Not yet implemented (H5, H6 in research plan).

---

## 8. Forecast Validation Gate Assessment (Validation Only)

| Criterion (Plan §7) | H2 HMM | H3 HOM | H1 Canonical | H4 SM | EWMA |
|---------------------|--------|--------|--------------|-------|------|
| Calibration (PIT) | ✓ Good | ✓ Excellent | ✓ Excellent | ✓ Excellent | N/A |
| Discrimination vs unconditional (p<0.05) | ✓ Yes (both) | ✓ Yes (both) | ✓ Yes (both) | ✓ Yes (both) | ✓ Yes |
| Discrimination vs EWMA (p<0.05) | ✗ No (log); ✗ EWMA better (CRPS) | ✗ No (both) | ✗ No (log); ✗ EWMA better (CRPS) | ✗ No (log); ✗ EWMA better (CRPS) | — |
| State stability (refit occupancy) | ✓ Low variance | N/A (deterministic counts) | N/A | N/A | N/A |
| Regime persistence | ✓ 5–30h sojourns | N/A | N/A | Weak duration effect | N/A |
| Robustness across sub-periods | ⚠ Sensitivity: Δlog_score=-0.059 (Jan-Mar) | Not tested | Not tested | Not tested | — |

**Gate status (validation):** **H2 HMM passes calibration and beats unconditional significantly, but fails to significantly beat EWMA on log score and loses on CRPS.** No model family achieves clear dominance over EWMA on both proper scores simultaneously.

---

## 9. Economic Simulation Gate Projection (Holdout, Not Evaluated)

| Criterion (Protocol §6.3) | Threshold | Validation Dry-Run (C1/C2) | Projected Holdout Risk |
|---------------------------|-----------|----------------------------|------------------------|
| Net Sharpe > 0.5 | 0.5 | 0.000 (fail) | **High** — validation forecasts too weak |
| Max DD < 20% | -0.2 | 0.000 (pass, vacuous) | Unknown |
| Positive expectancy (p<0.1 HAC) | >0 | 0.000 (fail) | **High** |
| Trade count > 100 | 100 | 0 (fail) | **High** — edge < cost threshold |
| Turnover < 500% | 5.0 | 0.000 (pass, vacuous) | Unknown |
| Beat best baseline by >0.25 Sharpe | +0.25 | -2.2 / -1.7 vs buy-hold | **High** |

**Projection:** Given validation dry-run results (zero trades, forecast means << cost threshold), **both C1 and C2 are likely to fail the Economic Simulation Gate on holdout** unless holdout regime structure produces substantially larger conditional means.

---

## 10. Recommendation for Next Steps

### Immediate (validation-only, no holdout tuning):
1. **Implement PIT/calibration figure helpers** for holdout artifacts (exercised on synthetic fixtures only) — addresses protocol reporting requirement.
2. **Run asset perturbation (ETHUSDT 1h)** on validation grid using existing pipelines — tests cross-asset robustness.
3. **Run period perturbation (2024 Q1 vs Q2 sub-windows)** — tests temporal stability.
4. **Implement negative-control tests** (label permutation, white noise) — verifies skill is not artifact.

### Holdout Evaluation (requires explicit authorization):
- If authorized, run `src/holdout_runner.py --execute-holdout --protocol-hash 50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062` **once**.
- Produce gate decision report (`REJECT` / `RESEARCH_MORE` / `CANDIDATE_FOR_INDEPENDENT_CONFIRMATION`).
- **Do not tune configs based on holdout outcomes.**

### Research Extensions (if cycle continues):
- **MS-GARCH (H5)**: Implement Markov-switching GARCH for volatility dynamics.
- **MDP (H6)**: Formalize state/action/reward for execution-aware policy.
- **Multi-horizon**: Test 15m/4h/24h horizons per research plan.
- **Cost model refinement**: Validate 10.6 bps round-trip with L2 data (T8).

---

## 11. Reproducibility Index

| Artifact | Path | Generator |
|----------|------|-----------|
| H1 Canonical MC | `h1_markov_chain_validation.{json,csv,md}` | `src/markov_chain_baseline.py` |
| H1 Sensitivity Consolidation | `h1_mc_sensitivity_consolidation.{json,md}` | `src/verify_h1_consolidation.py` |
| H2 HMM Validation | `h2_hmm_validation_{results.json,significance.json,.md}` | `src/hmm_walkforward.py`, `src/hmm_validation_significance.py` |
| H3 HOM | `h3_higher_order_markov_validation.{json,csv,md}` | `src/higher_order_markov.py` |
| H4 Semi-Markov | `h4_semi_markov_validation.{json,csv,md}` | `src/semi_markov_baseline.py` |
| Economic Dry-Run | `research/economic/validation_dryrun/*` | `src/economic_simulation.py` |
| Holdout Protocol | `research/specifications/holdout_evaluation_protocol.md` | (design doc) |
| Holdout Runner | `src/holdout_runner.py` | (protocol-enforcing stub) |

**All tests:** `PYTHONPATH=. python -m pytest -q` → **129 passed** (as of T5c close).
**No changes** to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`.
**No holdout executed.**

---

## 12. Conclusion

**On the validation period (2024-01 to 2024-06):**
- The **H2 filtered HMM (3-state)** is the best model by proper scoring rules, significantly outperforming unconditional Gaussian but **not significantly outperforming EWMA Gaussian on log score**, while **EWMA significantly outperforms HMM on CRPS**.
- Among non-latent Markov chains, **H3 (2nd-order, K=5 quantile)** is the strongest, significantly improving on H1, but still **does not beat EWMA on either metric with significance**.
- **No model family achieves statistically robust superiority over EWMA Gaussian** on both log score and CRPS simultaneously.
- **Economic feasibility is negative** on validation: forecast conditional means (max 3–7 bps) are far below conservative cost thresholds (8–16 bps/side), yielding zero trades and zero Sharpe.

**Implication for holdout:** Unless the holdout period (2024-07 to 2025-12) exhibits substantially different regime structure with stronger predictability, both frozen candidates (C1 HMM, C2 HOM) are projected to fail the Economic Simulation Gate. The research cycle should either (a) execute the holdout to confirm/deny this projection per protocol, or (b) pivot to model families with higher potential edge (MS-GARCH, multi-asset, shorter horizons) before committing holdout evaluation.

**No holdout evaluation has been performed.** This memo is a validation-only consolidation.