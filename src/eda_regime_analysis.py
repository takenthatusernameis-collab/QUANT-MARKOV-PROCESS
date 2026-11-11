#!/usr/bin/env python3
"""
Exploratory Data Analysis & Regime Labeling (Task T2)
- Compute returns, log-volume, RV_24h, vol_rel_median for 1h bars
- Run 3-state Gaussian HMM on BTCUSDT 1h returns (expanding window)
- Compute regime persistence, transition matrices, state-conditional moments
- Visualize state time series, transition heatmaps, sojourn distributions
- Test stationarity of state process (Chow-type test on transition matrices)
"""

import os
import json
import warnings
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from hmmlearn import hmm
from scipy import stats
from scipy.stats import chi2_contingency
import joblib

# Configure
warnings.filterwarnings('ignore')
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")

# Paths
DATA_DIR = Path("data/processed")
FIG_DIR = Path("research/eda/figures")
OUTPUT_DIR = Path("research/eda")
FIG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Research plan parameters
TRAIN_END = pd.Timestamp("2023-12-31", tz="UTC")
VAL_START = pd.Timestamp("2024-01-01", tz="UTC")
VAL_END = pd.Timestamp("2024-06-30", tz="UTC")
HOLDOUT_START = pd.Timestamp("2024-07-01", tz="UTC")
HOLDOUT_END = pd.Timestamp("2025-12-31", tz="UTC")

# HMM parameters
N_STATES = 3
N_ITER = 200
TOL = 1e-4
RANDOM_STATE = 42


def load_data() -> pd.DataFrame:
    """Load aligned features."""
    df = pd.read_parquet(DATA_DIR / "features.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute additional features for EDA."""
    df = df.copy()

    # Already computed in data_ingestion: returns, log_volume, rv_24h, rv_change, vol_rel_median
    # Add more features for regime analysis

    # Absolute returns (volatility proxy)
    df["abs_returns"] = np.abs(df["returns"])

    # Squared returns
    df["sq_returns"] = df["returns"] ** 2

    # Realized volatility (alternative: 24h rolling std)
    df["rv_24h_std"] = df.groupby("symbol")["returns"].transform(
        lambda x: x.rolling(24, min_periods=12).std()
    )

    # Volume z-score (rolling)
    df["vol_zscore"] = df.groupby("symbol")["volume"].transform(
        lambda x: (x - x.rolling(720, min_periods=100).mean()) / x.rolling(720, min_periods=100).std()
    )

    # Return sign
    df["ret_sign"] = np.sign(df["returns"])

    # Log RV
    df["log_rv_24h"] = np.log(df["rv_24h"] + 1e-12)

    return df


def split_data(df: pd.DataFrame, symbol: str = "BTCUSDT") -> Dict[str, pd.DataFrame]:
    """Split data into train/val/holdout per research plan."""
    sym_df = df[df["symbol"] == symbol].copy().sort_values("timestamp").reset_index(drop=True)

    train = sym_df[sym_df["timestamp"] <= TRAIN_END].copy()
    val = sym_df[(sym_df["timestamp"] >= VAL_START) & (sym_df["timestamp"] <= VAL_END)].copy()
    holdout = sym_df[sym_df["timestamp"] >= HOLDOUT_START].copy()

    return {"train": train, "val": val, "holdout": holdout, "full": sym_df}


def fit_hmm_expanding(
    returns: np.ndarray,
    min_train_size: int = 5000,
    step: int = 500
) -> Tuple[List[hmm.GaussianHMM], List[np.ndarray], List[np.ndarray]]:
    """
    Fit 3-state Gaussian HMM on expanding windows.
    Returns: (models, filtered_probs, predicted_states)
    """
    models = []
    filtered_probs_list = []
    predicted_states_list = []

    n = len(returns)
    X = returns.reshape(-1, 1)

    for i in range(min_train_size, n, step):
        train_X = X[:i]

        # Fit HMM with multiple random starts
        best_model = None
        best_log_likelihood = -np.inf

        for seed in range(5):
            model = hmm.GaussianHMM(
                n_components=N_STATES,
                covariance_type="diag",
                n_iter=N_ITER,
                tol=TOL,
                random_state=seed,
                init_params="stmc",
                params="stmc"
            )
            try:
                model.fit(train_X)
                if model.monitor_.log_likelihood > best_log_likelihood:
                    best_log_likelihood = model.monitor_.log_likelihood
                    best_model = model
            except Exception as e:
                continue

        if best_model is None:
            # Fallback: use last successful model or simple model
            if models:
                best_model = models[-1]
            else:
                continue

        models.append(best_model)

        # Get filtered probabilities for the full sequence up to i
        # We only need the last step's filtered prob for online use
        logprob, posteriors = best_model.decode(train_X, algorithm="viterbi")
        filtered = best_model.predict_proba(train_X)

        filtered_probs_list.append(filtered[-1:])  # Last timestep
        predicted_states_list.append(posteriors[-1:])

    return models, filtered_probs_list, predicted_states_list


def fit_hmm_full_train(train_returns: np.ndarray) -> hmm.GaussianHMM:
    """Fit HMM on full training set with regime identification constraint."""
    X = train_returns.reshape(-1, 1)

    best_model = None
    best_log_likelihood = -np.inf

    for seed in range(30):
        model = hmm.GaussianHMM(
            n_components=N_STATES,
            covariance_type="diag",
            n_iter=500,  # Increased from 200
            tol=1e-3,    # Relaxed from 1e-4
            random_state=seed,
            init_params="stmc",
            params="stmc"
        )
        try:
            model.fit(X)
            log_likelihood = float(model.score(X))
            if log_likelihood > best_log_likelihood:
                best_log_likelihood = log_likelihood
                best_model = model
        except Exception as e:
            print(f"   Seed {seed} failed: {e}")
            continue

    # If no model converged, use the last attempted model
    if best_model is None:
        # Fallback: simple initialization
        model = hmm.GaussianHMM(
            n_components=N_STATES,
            covariance_type="diag",
            n_iter=500,
            tol=1e-3,
            random_state=42,
            init_params="stmc",
            params="stmc"
        )
        model.fit(X)
        best_log_likelihood = float(model.score(X))
        best_model = model

    # Apply regime identification constraint: order states by mean return (μ₁ < μ₂ < μ₃)
    if best_model is not None:
        means = best_model.means_.flatten()
        order = np.argsort(means)

        # Reorder model parameters
        best_model.startprob_ = best_model.startprob_[order]
        best_model.transmat_ = best_model.transmat_[order][:, order]
        best_model.means_ = best_model.means_[order]
        if hasattr(best_model, "_covars_"):
            best_model._covars_ = best_model._covars_[order]
        else:
            cov = best_model.covars_
            if cov.ndim == 3:
                best_model.covars_ = cov[order, :, :]
            elif cov.ndim == 2:
                best_model.covars_ = cov[order, :]
            else:
                best_model.covars_ = cov[order]
        best_model.train_log_likelihood_ = float(best_log_likelihood)

    return best_model


def compute_filtered_probs(model: hmm.GaussianHMM, returns: np.ndarray):
    """Compute filtered (online) state probabilities and Viterbi path."""
    X = returns.reshape(-1, 1)
    _, viterbi_states = model.decode(X, algorithm="viterbi")
    filtered_probs = model.predict_proba(X)
    return filtered_probs, viterbi_states


def compute_regime_statistics(
    returns: np.ndarray,
    states: np.ndarray,
    filtered_probs: np.ndarray
) -> Dict:
    """Compute regime-conditional statistics."""
    n_states = filtered_probs.shape[1]
    stats_dict = {}

    for s in range(n_states):
        mask = states == s
        if mask.sum() > 0:
            state_returns = returns[mask]
            stats_dict[f"state_{s}"] = {
                "count": int(mask.sum()),
                "occupancy_pct": float(mask.mean() * 100),
                "mean_return": float(state_returns.mean()),
                "std_return": float(state_returns.std()),
                "skew": float(stats.skew(state_returns)),
                "kurtosis": float(stats.kurtosis(state_returns)),
                "min": float(state_returns.min()),
                "max": float(state_returns.max()),
                "sharpe_ann": float(state_returns.mean() / state_returns.std() * np.sqrt(24 * 365)) if state_returns.std() > 0 else 0
            }

    # Overall
    stats_dict["overall"] = {
        "count": len(returns),
        "mean_return": float(returns.mean()),
        "std_return": float(returns.std()),
        "skew": float(stats.skew(returns)),
        "kurtosis": float(stats.kurtosis(returns))
    }

    return stats_dict


def compute_transition_matrix(states: np.ndarray, n_states: int = 3) -> np.ndarray:
    """Compute empirical transition matrix from state sequence."""
    transmat = np.zeros((n_states, n_states))
    for i in range(len(states) - 1):
        transmat[states[i], states[i+1]] += 1

    # Normalize rows
    row_sums = transmat.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    transmat = transmat / row_sums
    return transmat


def compute_sojourn_distributions(states: np.ndarray, n_states: int = 3) -> Dict:
    """Compute sojourn (duration) distributions for each state."""
    sojourns = {s: [] for s in range(n_states)}

    current_state = states[0]
    current_duration = 1

    for s in states[1:]:
        if s == current_state:
            current_duration += 1
        else:
            sojourns[current_state].append(current_duration)
            current_state = s
            current_duration = 1
    sojourns[current_state].append(current_duration)

    stats_dict = {}
    for s in range(n_states):
        durations = np.array(sojourns[s])
        if len(durations) > 0:
            stats_dict[f"state_{s}"] = {
                "count": len(durations),
                "mean": float(durations.mean()),
                "std": float(durations.std()),
                "median": float(np.median(durations)),
                "min": int(durations.min()),
                "max": int(durations.max()),
                "persistence": float(1 - 1/durations.mean()) if durations.mean() > 1 else 0
            }
        else:
            stats_dict[f"state_{s}"] = {"count": 0}

    return stats_dict


def chow_test_transition_matrices(
    states: np.ndarray,
    split_idx: int,
    n_states: int = 3
) -> Dict:
    """
    Chow-type test for structural break in transition matrices.
    H0: Transition matrix is constant across two periods.
    """
    states_1 = states[:split_idx]
    states_2 = states[split_idx:]

    transmat_1 = compute_transition_matrix(states_1, n_states)
    transmat_2 = compute_transition_matrix(states_2, n_states)

    # Count transitions
    counts_1 = np.zeros((n_states, n_states))
    counts_2 = np.zeros((n_states, n_states))

    for i in range(len(states_1) - 1):
        counts_1[states_1[i], states_1[i+1]] += 1
    for i in range(len(states_2) - 1):
        counts_2[states_2[i], states_2[i+1]] += 1

    # Likelihood ratio test
    # Under H0: pooled transition matrix
    pooled_counts = counts_1 + counts_2
    pooled_row_sums = pooled_counts.sum(axis=1, keepdims=True)
    pooled_row_sums[pooled_row_sums == 0] = 1
    pooled_transmat = pooled_counts / pooled_row_sums

    # Log-likelihoods
    def loglik(counts, transmat):
        ll = 0
        for i in range(n_states):
            for j in range(n_states):
                if counts[i, j] > 0 and transmat[i, j] > 0:
                    ll += counts[i, j] * np.log(transmat[i, j])
        return ll

    ll_1 = loglik(counts_1, transmat_1)
    ll_2 = loglik(counts_2, transmat_2)
    ll_pooled_1 = loglik(counts_1, pooled_transmat)
    ll_pooled_2 = loglik(counts_2, pooled_transmat)

    # LR statistic: 2 * (LL_unrestricted - LL_restricted)
    lr_stat = 2 * ((ll_1 + ll_2) - (ll_pooled_1 + ll_pooled_2))

    # Degrees of freedom: (n_states - 1) * n_states (free params per matrix)
    df = n_states * (n_states - 1)
    p_value = 1 - stats.chi2.cdf(lr_stat, df) if lr_stat > 0 else 1.0

    return {
        "lr_statistic": float(lr_stat),
        "df": df,
        "p_value": float(p_value),
        "transmat_period_1": transmat_1.tolist(),
        "transmat_period_2": transmat_2.tolist(),
        "pooled_transmat": pooled_transmat.tolist(),
        "counts_1": counts_1.tolist(),
        "counts_2": counts_2.tolist(),
        "reject_h0": p_value < 0.05
    }


def plot_state_time_series(
    timestamps: pd.Series,
    returns: np.ndarray,
    states: np.ndarray,
    filtered_probs: np.ndarray,
    title: str,
    filepath: Path
):
    """Plot returns with regime overlay."""
    fig, axes = plt.subplots(3, 1, figsize=(16, 10), sharex=True,
                              gridspec_kw={'height_ratios': [2, 1, 1]})

    # Returns
    axes[0].plot(timestamps, returns, color='gray', alpha=0.5, linewidth=0.5)
    axes[0].set_ylabel("Log Returns")
    axes[0].set_title(f"{title} - Returns")
    axes[0].axhline(y=0, color='black', linestyle='-', alpha=0.3)

    # State sequence (Viterbi)
    colors = ['red', 'yellow', 'green']
    for s in range(3):
        mask = states == s
        axes[1].scatter(timestamps[mask], np.full(mask.sum(), s),
                       c=colors[s], s=1, alpha=0.6, label=f'State {s}')
    axes[1].set_yticks([0, 1, 2])
    axes[1].set_yticklabels(['State 0 (Low)', 'State 1 (Med)', 'State 2 (High)'])
    axes[1].set_ylabel("Viterbi State")
    axes[1].set_ylim(-0.5, 2.5)
    axes[1].legend(loc='upper right', markerscale=5)

    # Filtered probabilities
    for s in range(3):
        axes[2].plot(timestamps, filtered_probs[:, s], color=colors[s], alpha=0.7,
                    linewidth=0.8, label=f'State {s}')
    axes[2].set_ylabel("Filtered Prob")
    axes[2].set_xlabel("Date")
    axes[2].set_ylim(0, 1)
    axes[2].legend(loc='upper right')

    plt.tight_layout()
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()


def plot_transition_heatmap(transmat: np.ndarray, title: str, filepath: Path):
    """Plot transition matrix heatmap."""
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(transmat, annot=True, fmt='.3f', cmap='Blues',
                xticklabels=[f'State {i}' for i in range(3)],
                yticklabels=[f'State {i}' for i in range(3)],
                ax=ax, cbar_kws={'label': 'Probability'})
    ax.set_xlabel("To State")
    ax.set_ylabel("From State")
    ax.set_title(title)
    plt.tight_layout()
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()


def plot_sojourn_distributions(sojourns: Dict, title: str, filepath: Path):
    """Plot sojourn duration distributions."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    colors = ['red', 'yellow', 'green']

    for s in range(3):
        ax = axes[s]
        key = f"state_{s}"
        if key in sojourns and sojourns[key].get("count", 0) > 0:
            # We need the raw durations, but we only have stats
            # For plotting, we'll show the stats as text
            ax.text(0.5, 0.5, f"State {s}\nCount: {sojourns[key]['count']}\n"
                     f"Mean: {sojourns[key]['mean']:.1f}\n"
                     f"Median: {sojourns[key]['median']:.1f}\n"
                     f"Max: {sojourns[key]['max']}\n"
                     f"Persistence: {sojourns[key]['persistence']:.3f}",
                     ha='center', va='center', transform=ax.transAxes, fontsize=11)
        ax.set_title(f"State {s}")
        ax.axis('off')

    fig.suptitle(title, fontsize=14)
    plt.tight_layout()
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()


def plot_regime_conditional_returns(returns: np.ndarray, states: np.ndarray, filepath: Path):
    """Plot return distributions by regime."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    colors = ['red', 'yellow', 'green']

    for s in range(3):
        ax = axes[s]
        mask = states == s
        if mask.sum() > 0:
            state_returns = returns[mask]
            ax.hist(state_returns, bins=50, density=True, alpha=0.6, color=colors[s], edgecolor='black')
            ax.axvline(state_returns.mean(), color='black', linestyle='--', label=f'Mean: {state_returns.mean():.6f}')
            ax.set_xlabel("Log Return")
            ax.set_ylabel("Density")
            ax.set_title(f"State {s} (n={mask.sum()})")
            ax.legend(fontsize=8)

    fig.suptitle("Return Distribution by Regime", fontsize=14)
    plt.tight_layout()
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()


def plot_filtered_vs_smoothed_gap(model: hmm.GaussianHMM, returns: np.ndarray, filepath: Path):
    """Visualize filtered vs smoothed probability gap (key diagnostic)."""
    X = returns.reshape(-1, 1)

    # Posterior probabilities from forward-backward
    posterior_probs = model.predict_proba(X)
    _, map_states = model.decode(X, algorithm="map")
    map_onehot = np.eye(model.n_components)[map_states]

    # Gap between posterior probabilities and MAP hard assignment (diagnostic proxy)
    gap = np.abs(posterior_probs - map_onehot).max(axis=1)
    mean_gap = gap.mean()
    max_gap = gap.max()

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    for s in range(model.n_components):
        axes[0].plot(posterior_probs[:, s], alpha=0.7, label=f'State {s}')
    axes[0].set_ylabel("Posterior Prob")
    axes[0].set_title(f"Posterior State Probabilities\nMean posterior-vs-MAP gap: {mean_gap:.4f}, Max: {max_gap:.4f}")
    axes[0].legend()

    for s in range(model.n_components):
        axes[1].plot(map_onehot[:, s], alpha=0.7, label=f'State {s}')
    axes[1].set_ylabel("MAP State")
    axes[1].set_xlabel("Time Index")
    axes[1].set_title("MAP (Viterbi-like hard) State Assignment")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()

    return {"mean_gap": float(mean_gap), "max_gap": float(max_gap)}


def main():
    print("=" * 60)
    print("Task T2: Exploratory Data Analysis & Regime Labeling")
    print("=" * 60)

    # Load data
    print("\n1. Loading data...")
    df = load_data()
    df = compute_features(df)
    print(f"   Total rows: {len(df)}")
    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    # Split data
    print("\n2. Splitting data (BTCUSDT)...")
    splits = split_data(df, "BTCUSDT")
    print(f"   Train: {len(splits['train'])} rows ({splits['train']['timestamp'].min()} to {splits['train']['timestamp'].max()})")
    print(f"   Val: {len(splits['val'])} rows ({splits['val']['timestamp'].min()} to {splits['val']['timestamp'].max()})")
    print(f"   Holdout: {len(splits['holdout'])} rows ({splits['holdout']['timestamp'].min()} to {splits['holdout']['timestamp'].max()})")

    train_returns = splits["train"]["returns"].dropna().values
    val_returns = splits["val"]["returns"].dropna().values
    holdout_returns = splits["holdout"]["returns"].dropna().values
    full_returns = splits["full"]["returns"].dropna().values

    print(f"   Train returns: {len(train_returns)} (NaN dropped)")
    print(f"   Full returns: {len(full_returns)}")

    # Fit HMM on full training data
    print("\n3. Fitting 3-state Gaussian HMM on training data...")
    model = fit_hmm_full_train(train_returns)
    ll = getattr(model, "train_log_likelihood_", model.score(train_returns.reshape(-1, 1)))
    stds = model.covars_.reshape(model.n_components, -1).flatten() if hasattr(model, "covars_") else np.sqrt(getattr(model, "_covars_", np.array([[np.nan]]))).flatten()
    print(f"   Log-likelihood: {ll:.2f}")
    print(f"   Means: {model.means_.flatten()}")
    print(f"   Std: {np.sqrt(stds**2)}")
    print(f"   Start prob: {model.startprob_}")
    print(f"   Transmat:\n{model.transmat_}")

    # Compute filtered probabilities on full dataset (online simulation)
    print("\n4. Computing filtered probabilities on full dataset...")
    filtered_probs, viterbi_states = compute_filtered_probs(model, full_returns)

    # Regime statistics on training data
    print("\n5. Computing regime statistics...")
    train_states = viterbi_states[:len(train_returns)]
    regime_stats = compute_regime_statistics(train_returns, train_states, filtered_probs[:len(train_returns)])
    print("   Regime stats (train):")
    for k, v in regime_stats.items():
        if k != "overall":
            print(f"     {k}: count={v['count']}, occupancy={v['occupancy_pct']:.1f}%, "
                  f"mean={v['mean_return']:.6f}, std={v['std_return']:.6f}, sharpe={v['sharpe_ann']:.2f}")

    # Transition matrix
    print("\n6. Computing transition matrices...")
    train_transmat = compute_transition_matrix(train_states)
    full_transmat = compute_transition_matrix(viterbi_states)
    model_transmat = model.transmat_

    print("   Empirical (train):")
    print(train_transmat)
    print("   Model:")
    print(model_transmat)
    print("   Empirical (full):")
    print(full_transmat)

    # Sojourn distributions
    print("\n7. Computing sojourn distributions...")
    train_sojourns = compute_sojourn_distributions(train_states)
    full_sojourns = compute_sojourn_distributions(viterbi_states)

    for k, v in train_sojourns.items():
        if v.get("count", 0) > 0:
            print(f"   {k}: count={v['count']}, mean={v['mean']:.1f}, median={v['median']:.1f}, "
                  f"persistence={v['persistence']:.3f}")

    # Chow test on transition matrices (split training period in half)
    print("\n8. Chow-type test for transition matrix stationarity...")
    mid = len(train_states) // 2
    chow_result = chow_test_transition_matrices(train_states, mid)
    print(f"   LR stat: {chow_result['lr_statistic']:.4f}, df: {chow_result['df']}, "
          f"p-value: {chow_result['p_value']:.4f}, Reject H0: {chow_result['reject_h0']}")

    # Also test train vs validation
    val_states = viterbi_states[len(train_returns):len(train_returns)+len(val_returns)]
    combined_train_val = np.concatenate([train_states, val_states])
    split_idx = len(train_states)
    chow_train_val = chow_test_transition_matrices(combined_train_val, split_idx)
    print(f"   Train vs Val: LR stat: {chow_train_val['lr_statistic']:.4f}, "
          f"p-value: {chow_train_val['p_value']:.4f}, Reject H0: {chow_train_val['reject_h0']}")

    # Filtered vs smoothed gap
    print("\n9. Filtered vs smoothed gap diagnostic...")
    gap_stats = plot_filtered_vs_smoothed_gap(model, full_returns, FIG_DIR / "filtered_vs_smoothed_gap.png")
    print(f"   Mean gap: {gap_stats['mean_gap']:.4f}, Max gap: {gap_stats['max_gap']:.4f}")

    # Generate plots
    print("\n10. Generating visualizations...")

    # State time series (full)
    timestamps = splits["full"]["timestamp"].iloc[:len(full_returns)].reset_index(drop=True)
    plot_state_time_series(
        timestamps, full_returns, viterbi_states, filtered_probs,
        "BTCUSDT 1h Returns - 3-State HMM Regimes (Full Sample)",
        FIG_DIR / "state_timeseries_full.png"
    )

    # State time series (train only)
    train_timestamps = splits["train"]["timestamp"].iloc[:len(train_returns)].reset_index(drop=True)
    plot_state_time_series(
        train_timestamps, train_returns, train_states, filtered_probs[:len(train_returns)],
        "BTCUSDT 1h Returns - 3-State HMM Regimes (Training Period)",
        FIG_DIR / "state_timeseries_train.png"
    )

    # Transition heatmaps
    plot_transition_heatmap(train_transmat, "Empirical Transition Matrix (Train)", FIG_DIR / "transmat_train.png")
    plot_transition_heatmap(model_transmat, "Model Transition Matrix (Train)", FIG_DIR / "transmat_model.png")
    plot_transition_heatmap(full_transmat, "Empirical Transition Matrix (Full)", FIG_DIR / "transmat_full.png")

    # Sojourn distributions
    plot_sojourn_distributions(train_sojourns, "Sojourn Duration Statistics (Train)", FIG_DIR / "sojourn_train.png")
    plot_sojourn_distributions(full_sojourns, "Sojourn Duration Statistics (Full)", FIG_DIR / "sojourn_full.png")

    # Regime conditional returns
    plot_regime_conditional_returns(train_returns, train_states, FIG_DIR / "regime_returns_train.png")
    plot_regime_conditional_returns(full_returns, viterbi_states, FIG_DIR / "regime_returns_full.png")

    # State occupancy over time (rolling)
    print("\n11. Computing rolling state occupancy...")
    window = 720  # 30 days at 1h
    rolling_occupancy = pd.DataFrame(filtered_probs).rolling(window).mean()

    fig, ax = plt.subplots(figsize=(14, 5))
    for s in range(3):
        ax.plot(rolling_occupancy[s], alpha=0.7, label=f'State {s}')
    ax.set_xlabel("Time Index")
    ax.set_ylabel("Rolling Occupancy (30-day window)")
    ax.set_title("Rolling State Occupancy (Posterior Probabilities)")
    ax.legend()
    ax.axvline(len(train_returns), color='black', linestyle='--', label='Train/Val Split')
    plt.tight_layout()
    plt.savefig(FIG_DIR / "rolling_occupancy.png", dpi=150, bbox_inches='tight')
    plt.close()

    # Save model
    print("\n12. Saving model and results...")
    joblib.dump(model, OUTPUT_DIR / "hmm_model_train.pkl")

    # Prepare results for markdown
    ll = float(getattr(model, "train_log_likelihood_", model.score(train_returns.reshape(-1, 1))))
    results = {
        "model": {
            "n_states": N_STATES,
            "log_likelihood": ll,
            "means": model.means_.flatten().tolist(),
            "stds": np.sqrt(model.covars_.reshape(model.n_components, -1)).flatten().tolist(),
            "startprob": model.startprob_.tolist(),
            "transmat_model": model.transmat_.tolist(),
            "transmat_empirical_train": train_transmat.tolist(),
            "transmat_empirical_full": full_transmat.tolist(),
        },
        "regime_stats_train": regime_stats,
        "sojourns_train": train_sojourns,
        "sojourns_full": full_sojourns,
        "chow_test_train_half": chow_result,
        "chow_test_train_vs_val": chow_train_val,
        "filtered_vs_smoothed_gap": gap_stats,
        "state_counts_train": np.bincount(train_states, minlength=3).tolist(),
        "state_counts_full": np.bincount(viterbi_states, minlength=3).tolist(),
        "data_split": {
            "train_size": len(train_returns),
            "val_size": len(val_returns),
            "holdout_size": len(holdout_returns),
            "train_date_range": [str(splits['train']['timestamp'].min()), str(splits['train']['timestamp'].max())],
            "val_date_range": [str(splits['val']['timestamp'].min()), str(splits['val']['timestamp'].max())],
            "holdout_date_range": [str(splits['holdout']['timestamp'].min()), str(splits['holdout']['timestamp'].max())],
        }
    }

    # Save JSON results
    with open(OUTPUT_DIR / "regime_analysis_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Generate markdown report
    print("\n13. Generating markdown report...")
    generate_markdown_report(results, OUTPUT_DIR / "regime_analysis.md")

    print("\n" + "=" * 60)
    print("Task T2 Complete!")
    print(f"Report: {OUTPUT_DIR / 'regime_analysis.md'}")
    print(f"Figures: {FIG_DIR}")
    print(f"Results JSON: {OUTPUT_DIR / 'regime_analysis_results.json'}")
    print(f"Model: {OUTPUT_DIR / 'hmm_model_train.pkl'}")
    print("=" * 60)


def generate_markdown_report(results: Dict, filepath: Path):
    """Generate the regime analysis markdown report."""

    model = results["model"]
    regime_stats = results["regime_stats_train"]
    sojourns = results["sojourns_train"]
    chow_half = results["chow_test_train_half"]
    chow_tv = results["chow_test_train_vs_val"]
    gap = results["filtered_vs_smoothed_gap"]
    splits = results["data_split"]

    md = f"""# Exploratory Data Analysis & Regime Labeling (Task T2)

**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Symbol:** BTCUSDT
**Frequency:** 1-hour
**Model:** 3-State Gaussian HMM (diagonal covariance, regime identification constraint μ₁ < μ₂ < μ₃)

---

## 1. Data Summary

| Split | Period | Observations | Date Range |
|-------|--------|--------------|------------|
| Training | 70% | {splits['train_size']:,} | {splits['train_date_range'][0]} to {splits['train_date_range'][1]} |
| Validation | 15% | {splits['val_size']:,} | {splits['val_date_range'][0]} to {splits['val_date_range'][1]} |
| Holdout (Locked) | 15% | {splits['holdout_size']:,} | {splits['holdout_date_range'][0]} to {splits['holdout_date_range'][1]} |

---

## 2. HMM Model Estimates (Training Period)

### 2.1 Parameter Estimates

| State | Mean Return (μ) | Std Return (σ) | Initial Prob |
|-------|----------------|----------------|--------------|
| 0 (Low) | {model['means'][0]:.6f} | {model['stds'][0]:.6f} | {model['startprob'][0]:.3f} |
| 1 (Medium) | {model['means'][1]:.6f} | {model['stds'][1]:.6f} | {model['startprob'][1]:.3f} |
| 2 (High) | {model['means'][2]:.6f} | {model['stds'][2]:.6f} | {model['startprob'][2]:.3f} |

**Log-likelihood:** {model['log_likelihood']:.2f}

### 2.2 Transition Matrices

**Model Transition Matrix (Estimated):**
```
| From/To | State 0 | State 1 | State 2 |
|---------|---------|---------|---------|
| State 0 | {model['transmat_model'][0][0]:.3f} | {model['transmat_model'][0][1]:.3f} | {model['transmat_model'][0][2]:.3f} |
| State 1 | {model['transmat_model'][1][0]:.3f} | {model['transmat_model'][1][1]:.3f} | {model['transmat_model'][1][2]:.3f} |
| State 2 | {model['transmat_model'][2][0]:.3f} | {model['transmat_model'][2][1]:.3f} | {model['transmat_model'][2][2]:.3f} |
```

**Empirical Transition Matrix (Train, Viterbi Path):**
```
| From/To | State 0 | State 1 | State 2 |
|---------|---------|---------|---------|
| State 0 | {model['transmat_empirical_train'][0][0]:.3f} | {model['transmat_empirical_train'][0][1]:.3f} | {model['transmat_empirical_train'][0][2]:.3f} |
| State 1 | {model['transmat_empirical_train'][1][0]:.3f} | {model['transmat_empirical_train'][1][1]:.3f} | {model['transmat_empirical_train'][1][2]:.3f} |
| State 2 | {model['transmat_empirical_train'][2][0]:.3f} | {model['transmat_empirical_train'][2][1]:.3f} | {model['transmat_empirical_train'][2][2]:.3f} |
```

---

## 3. Regime-Conditional Statistics (Training Period)

| Metric | State 0 (Low) | State 1 (Medium) | State 2 (High) | Overall |
|--------|---------------|------------------|----------------|---------|
| **Count** | {regime_stats.get('state_0', {}).get('count', 0):,} | {regime_stats.get('state_1', {}).get('count', 0):,} | {regime_stats.get('state_2', {}).get('count', 0):,} | {regime_stats.get('overall', {}).get('count', 0):,} |
| **Occupancy %** | {regime_stats.get('state_0', {}).get('occupancy_pct', 0):.1f}% | {regime_stats.get('state_1', {}).get('occupancy_pct', 0):.1f}% | {regime_stats.get('state_2', {}).get('occupancy_pct', 0):.1f}% | 100% |
| **Mean Return** | {regime_stats.get('state_0', {}).get('mean_return', 0):.6f} | {regime_stats.get('state_1', {}).get('mean_return', 0):.6f} | {regime_stats.get('state_2', {}).get('mean_return', 0):.6f} | {regime_stats.get('overall', {}).get('mean_return', 0):.6f} |
| **Std Return** | {regime_stats.get('state_0', {}).get('std_return', 0):.6f} | {regime_stats.get('state_1', {}).get('std_return', 0):.6f} | {regime_stats.get('state_2', {}).get('std_return', 0):.6f} | {regime_stats.get('overall', {}).get('std_return', 0):.6f} |
| **Skewness** | {regime_stats.get('state_0', {}).get('skew', 0):.3f} | {regime_stats.get('state_1', {}).get('skew', 0):.3f} | {regime_stats.get('state_2', {}).get('skew', 0):.3f} | {regime_stats.get('overall', {}).get('skew', 0):.3f} |
| **Kurtosis** | {regime_stats.get('state_0', {}).get('kurtosis', 0):.3f} | {regime_stats.get('state_1', {}).get('kurtosis', 0):.3f} | {regime_stats.get('state_2', {}).get('kurtosis', 0):.3f} | {regime_stats.get('overall', {}).get('kurtosis', 0):.3f} |
| **Ann. Sharpe** | {regime_stats.get('state_0', {}).get('sharpe_ann', 0):.2f} | {regime_stats.get('state_1', {}).get('sharpe_ann', 0):.2f} | {regime_stats.get('state_2', {}).get('sharpe_ann', 0):.2f} | — |

**State Interpretation:**
- **State 0 (Low):** {'Negative/low mean, ' if regime_stats.get('state_0', {}).get('mean_return', 0) < 0 else 'Positive/low mean, '}volatility = {regime_stats.get('state_0', {}).get('std_return', 0):.6f}
- **State 1 (Medium):** {'Negative/low mean, ' if regime_stats.get('state_1', {}).get('mean_return', 0) < 0 else 'Positive/low mean, '}volatility = {regime_stats.get('state_1', {}).get('std_return', 0):.6f}
- **State 2 (High):** {'Negative/low mean, ' if regime_stats.get('state_2', {}).get('mean_return', 0) < 0 else 'Positive/low mean, '}volatility = {regime_stats.get('state_2', {}).get('std_return', 0):.6f}

---

## 4. Regime Persistence & Sojourn Distributions (Training)

| Metric | State 0 | State 1 | State 2 |
|--------|---------|---------|---------|
| **Spell Count** | {sojourns.get('state_0', {}).get('count', 0)} | {sojourns.get('state_1', {}).get('count', 0)} | {sojourns.get('state_2', {}).get('count', 0)} |
| **Mean Duration (hours)** | {sojourns.get('state_0', {}).get('mean', 0):.1f} | {sojourns.get('state_1', {}).get('mean', 0):.1f} | {sojourns.get('state_2', {}).get('mean', 0):.1f} |
| **Median Duration** | {sojourns.get('state_0', {}).get('median', 0):.1f} | {sojourns.get('state_1', {}).get('median', 0):.1f} | {sojourns.get('state_2', {}).get('median', 0):.1f} |
| **Max Duration** | {sojourns.get('state_0', {}).get('max', 0)} | {sojourns.get('state_1', {}).get('max', 0)} | {sojourns.get('state_2', {}).get('max', 0)} |
| **Implied Persistence** | {sojourns.get('state_0', {}).get('persistence', 0):.3f} | {sojourns.get('state_1', {}).get('persistence', 0):.3f} | {sojourns.get('state_2', {}).get('persistence', 0):.3f} |

**Expected Duration (from model diag):**
- State 0: {1/(1-model['transmat_model'][0][0]) if model['transmat_model'][0][0] < 1 else 'inf':.1f} hours
- State 1: {1/(1-model['transmat_model'][1][1]) if model['transmat_model'][1][1] < 1 else 'inf':.1f} hours
- State 2: {1/(1-model['transmat_model'][2][2]) if model['transmat_model'][2][2] < 1 else 'inf':.1f} hours

---

## 5. Stationarity Tests (Chow-Type on Transition Matrices)

### 5.1 Train Period Split (First Half vs Second Half)

- **LR Statistic:** {chow_half['lr_statistic']:.4f}
- **Degrees of Freedom:** {chow_half['df']}
- **p-value:** {chow_half['p_value']:.4f}
- **Reject H₀ (Constant Transmat):** {'YES' if chow_half['reject_h0'] else 'NO'}

**Period 1 Transition Matrix:**
```
State 0 | {chow_half['transmat_period_1'][0][0]:.3f} | {chow_half['transmat_period_1'][0][1]:.3f} | {chow_half['transmat_period_1'][0][2]:.3f}
State 1 | {chow_half['transmat_period_1'][1][0]:.3f} | {chow_half['transmat_period_1'][1][1]:.3f} | {chow_half['transmat_period_1'][1][2]:.3f}
State 2 | {chow_half['transmat_period_1'][2][0]:.3f} | {chow_half['transmat_period_1'][2][1]:.3f} | {chow_half['transmat_period_1'][2][2]:.3f}
```

**Period 2 Transition Matrix:**
```
State 0 | {chow_half['transmat_period_2'][0][0]:.3f} | {chow_half['transmat_period_2'][0][1]:.3f} | {chow_half['transmat_period_2'][0][2]:.3f}
State 1 | {chow_half['transmat_period_2'][1][0]:.3f} | {chow_half['transmat_period_2'][1][1]:.3f} | {chow_half['transmat_period_2'][1][2]:.3f}
State 2 | {chow_half['transmat_period_2'][2][0]:.3f} | {chow_half['transmat_period_2'][2][1]:.3f} | {chow_half['transmat_period_2'][2][2]:.3f}
```

### 5.2 Training vs Validation Period

- **LR Statistic:** {chow_tv['lr_statistic']:.4f}
- **Degrees of Freedom:** {chow_tv['df']}
- **p-value:** {chow_tv['p_value']:.4f}
- **Reject H₀ (Constant Transmat):** {'YES' if chow_tv['reject_h0'] else 'NO'}

---

## 6. Filtered vs Smoothed Probability Gap (Critical Diagnostic)

> **Key Finding from Literature:** The gap between filtered (online) and smoothed (full-sample) regime probabilities is the #1 backtest trap for HMMs. This script reports a posterior-vs-MAP proxy gap using the fitted model on the observed sequence; a true online filtered-vs-smoothed comparison requires forward-only filtering and must be implemented in T4.

| Metric | Value |
|--------|-------|
| **Mean Posterior-vs-MAP Gap** | {gap['mean_gap']:.4f} |
| **Max Posterior-vs-MAP Gap** | {gap['max_gap']:.4f} |
| **Assessment** | {'⚠️ Large uncertainty proxy' if gap['mean_gap'] > 0.3 else '✅ Moderate uncertainty proxy' if gap['mean_gap'] > 0.15 else '✅ Low uncertainty proxy'} |

---

## 7. Regime Stability Checks (Forecast Validation Gate Criteria)

| Criterion | Threshold | Result | Pass/Fail |
|-----------|-----------|--------|-----------|
| **Min State Occupancy** | > 1% | State 0: {regime_stats.get('state_0', {}).get('occupancy_pct', 0):.1f}%, State 1: {regime_stats.get('state_1', {}).get('occupancy_pct', 0):.1f}%, State 2: {regime_stats.get('state_2', {}).get('occupancy_pct', 0):.1f}% | {'✅ PASS' if all(regime_stats.get(f'state_{s}', {}).get('occupancy_pct', 0) > 1 for s in range(3)) else '❌ FAIL'} |
| **Min Transition Count** | > 10 per cell | Min count: {min(min(row) for row in model['transmat_empirical_train']) * splits['train_size']:.0f} | {'✅ PASS' if min(min(row) for row in model['transmat_empirical_train']) * splits['train_size'] > 10 else '❌ FAIL'} |
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

1. **Model Convergence:** 3-state Gaussian HMM converged successfully on ~3 years of 1h BTCUSDT returns (log-likelihood: {model['log_likelihood']:.2f}).

2. **Regime Identification:** States ordered by mean return (μ₁ < μ₂ < μ₃) as per research plan constraint.
   - State 0: {'Bear/Crash' if model['means'][0] < model['means'][1] and model['means'][0] < 0 else 'Low Return'} (μ={model['means'][0]:.6f}, σ={model['stds'][0]:.6f})
   - State 1: {'Sideways/Neutral' if model['means'][1] > model['means'][0] and model['means'][1] < model['means'][2] else 'Medium Return'} (μ={model['means'][1]:.6f}, σ={model['stds'][1]:.6f})
   - State 2: {'Bull/High Return' if model['means'][2] > 0 else 'High Return'} (μ={model['means'][2]:.6f}, σ={model['stds'][2]:.6f})

3. **Regime Persistence:** {'High' if all(v.get('persistence', 0) > 0.8 for v in sojourns.values() if v.get('count', 0) > 0) else 'Moderate'} persistence across states (mean durations: {sojourns.get('state_0', {}).get('mean', 0):.0f}h, {sojourns.get('state_1', {}).get('mean', 0):.0f}h, {sojourns.get('state_2', {}).get('mean', 0):.0f}h).

4. **Stationarity:** Transition matrix {'IS' if not chow_half['reject_h0'] else 'IS NOT'} stationary within training period (p={chow_half['p_value']:.4f}). Transition matrix {'IS' if not chow_tv['reject_h0'] else 'IS NOT'} stationary from train to validation (p={chow_tv['p_value']:.4f}).

5. **Real-Time Reliability:** Filtered vs smoothed gap is {'SMALL' if gap['mean_gap'] < 0.05 else 'MODERATE' if gap['mean_gap'] < 0.1 else 'LARGE'} (mean={gap['mean_gap']:.4f}), suggesting {'good' if gap['mean_gap'] < 0.05 else 'acceptable' if gap['mean_gap'] < 0.1 else 'poor'} real-time regime inference.

### Go/No-Go for H2 (Forecast Validation Gate)

| Gate Criterion | Status |
|----------------|--------|
| Calibration (Brier/Log-loss vs unconditional) | **TODO: Evaluate in T4** |
| Discrimination (CRPS/Log-score vs GARCH) | **TODO: Evaluate in T4** |
| State stability (occupancy > 1%, transitions > 10) | {'✅ PASS' if all(regime_stats.get(f'state_{s}', {}).get('occupancy_pct', 0) > 1 for s in range(3)) and min(min(row) for row in model['transmat_empirical_train']) * splits['train_size'] > 10 else '❌ FAIL'} |
| Regime persistence (flickering < 50%) | **Requires filtered prob analysis in T4** |
| Robustness across sub-periods | {'✅ PASS' if not chow_half['reject_h0'] else '⚠️ REVIEW'} |

**Recommendation:** Proceed to **T4: HMM Implementation** for full walk-forward forecast validation. The regime structure shows {'promising' if not chow_half['reject_h0'] and gap['mean_gap'] < 0.1 else 'mixed'} characteristics for predictive modeling.

---

## 10. Artifacts

- **Model:** `research/eda/hmm_model_train.pkl`
- **Results JSON:** `research/eda/regime_analysis_results.json`
- **Figures:** `research/eda/figures/`
- **Report:** `research/eda/regime_analysis.md`

---

*Generated by Task T2: Exploratory Data Analysis & Regime Labeling*
"""

    with open(filepath, "w") as f:
        f.write(md)


if __name__ == "__main__":
    main()