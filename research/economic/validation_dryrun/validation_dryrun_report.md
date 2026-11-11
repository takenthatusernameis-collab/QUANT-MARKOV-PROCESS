# Validation-Only Economic Simulation Dry-Run Report

**Generated:** 2026-11-11T03:33:45.389788+00:00
**Protocol:** research/specifications/holdout_evaluation_protocol.md
**Scope:** Validation period 2024-01-01 to 2024-06-30 (BTCUSDT 1h)
**Status:** DRY-RUN ONLY — No holdout evaluation performed

## Configuration

- Theta sensitivity (bps): [0.0, 2.0, 5.0]
- Notional fraction: 0.1
- Max gross exposure: 1.0
- Base cost round-trip: 8.0 bps per side = 16.0 bps round-trip
- Stress cost round-trip: 32.0 bps round-trip

## Results Summary

### C1_hmm

| Theta (bps) | Cost | Net Sharpe | Net CAGR | Max DD | Hit Rate | Trade Count | Turnover (ann.) | Excess vs No-Trade | Excess vs BuyHold |
|-------------|------|------------|----------|--------|----------|-------------|-----------------|-------------------|-------------------|
| 0.0 | base | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -2.208 |
| 0.0 | stress | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -2.195 |
| 2.0 | base | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -2.208 |
| 2.0 | stress | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -2.195 |
| 5.0 | base | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -2.208 |
| 5.0 | stress | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -2.195 |

### C2_hom

| Theta (bps) | Cost | Net Sharpe | Net CAGR | Max DD | Hit Rate | Trade Count | Turnover (ann.) | Excess vs No-Trade | Excess vs BuyHold |
|-------------|------|------------|----------|--------|----------|-------------|-----------------|-------------------|-------------------|
| 0.0 | base | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -1.695 |
| 0.0 | stress | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -1.683 |
| 2.0 | base | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -1.695 |
| 2.0 | stress | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -1.683 |
| 5.0 | base | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -1.695 |
| 5.0 | stress | 0.000 | 0.0000 | 0.0000 | 0.000 | 0 | 0.0 | 0.000 | -1.683 |

## Baseline Comparison (Theta=0, Base Costs)

| Baseline | Net Sharpe | Net CAGR | Max DD | Trade Count |
|----------|------------|----------|--------|-------------|
| B3_notrade | 0.000 | 0.0000 | 0.0000 | 0 |
| B4_buyhold | 2.208 | 0.1114 | -0.0143 | 1 |
| B5_momentum | 10.757 | 0.6256 | -0.0040 | 127 |

## Gate Criteria Assessment (Validation Dry-Run)

| Criterion | Threshold | C1 (HMM) | C2 (HOM) | Pass? |
|-----------|-----------|----------|----------|-------|
| Net Sharpe > 0.5 | 0.5 | 0.000 ✗ | 0.000 ✗ |  |
| Max DD < 20% | -0.2 | 0.000 ✓ | 0.000 ✓ | C1 C2 |
| Positive expectancy (per bar) | 0.0 | 0.000 ✗ | 0.000 ✗ |  |
| Trade count > 100 | 100 | 0.000 ✗ | 0.000 ✗ |  |
| Turnover < 500% | 5.0 | 0.000 ✓ | 0.000 ✓ | C1 C2 |

---
*This is a validation-only dry-run. No holdout evaluation has been performed.*
*Results do not constitute evidence for or against any candidate.*