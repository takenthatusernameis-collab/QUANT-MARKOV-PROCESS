import json
import hashlib
from pathlib import Path

import pandas as pd
import pytest


RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")


def file_hash(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_manifest_exists():
    manifest_path = RAW_DIR / "manifest.json"
    assert manifest_path.exists(), "manifest.json not found"


def test_manifest_structure():
    manifest_path = RAW_DIR / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    assert "retrieval_date" in manifest
    assert "symbols" in manifest
    assert set(manifest["symbols"]) == {"BTCUSDT", "ETHUSDT"}
    assert "date_range" in manifest
    assert "entries" in manifest
    assert "quality_checks" in manifest
    assert len(manifest["entries"]) > 0


def test_manifest_file_hashes():
    manifest_path = RAW_DIR / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    for entry in manifest["entries"]:
        filepath = Path(entry["file_path"])
        assert filepath.exists(), f"File not found: {filepath}"
        actual_hash = file_hash(filepath)
        assert actual_hash == entry["sha256_hash"], f"Hash mismatch for {filepath}"


def test_raw_parquet_files_exist():
    expected_files = [
        "BTCUSDT_15m_klines.parquet",
        "BTCUSDT_1h_klines.parquet",
        "BTCUSDT_4h_klines.parquet",
        "BTCUSDT_1d_klines.parquet",
        "BTCUSDT_funding_rate.parquet",
        "ETHUSDT_15m_klines.parquet",
        "ETHUSDT_1h_klines.parquet",
        "ETHUSDT_4h_klines.parquet",
        "ETHUSDT_1d_klines.parquet",
        "ETHUSDT_funding_rate.parquet",
    ]
    for fname in expected_files:
        assert (RAW_DIR / fname).exists(), f"Missing: {fname}"


def test_klines_row_counts():
    df_15m_btc = pd.read_parquet(RAW_DIR / "BTCUSDT_15m_klines.parquet")
    df_15m_eth = pd.read_parquet(RAW_DIR / "ETHUSDT_15m_klines.parquet")
    df_1h_btc = pd.read_parquet(RAW_DIR / "BTCUSDT_1h_klines.parquet")
    df_1h_eth = pd.read_parquet(RAW_DIR / "ETHUSDT_1h_klines.parquet")
    df_4h_btc = pd.read_parquet(RAW_DIR / "BTCUSDT_4h_klines.parquet")
    df_4h_eth = pd.read_parquet(RAW_DIR / "ETHUSDT_4h_klines.parquet")
    df_1d_btc = pd.read_parquet(RAW_DIR / "BTCUSDT_1d_klines.parquet")
    df_1d_eth = pd.read_parquet(RAW_DIR / "ETHUSDT_1d_klines.parquet")

    assert len(df_15m_btc) == 175296, f"BTCUSDT 15m: expected 175296, got {len(df_15m_btc)}"
    assert len(df_15m_eth) == 175296, f"ETHUSDT 15m: expected 175296, got {len(df_15m_eth)}"
    assert len(df_1h_btc) == 43824, f"BTCUSDT 1h: expected 43824, got {len(df_1h_btc)}"
    assert len(df_1h_eth) == 43824, f"ETHUSDT 1h: expected 43824, got {len(df_1h_eth)}"
    assert len(df_4h_btc) == 10956, f"BTCUSDT 4h: expected 10956, got {len(df_4h_btc)}"
    assert len(df_4h_eth) == 10956, f"ETHUSDT 4h: expected 10956, got {len(df_4h_eth)}"
    assert len(df_1d_btc) == 1826, f"BTCUSDT 1d: expected 1826, got {len(df_1d_btc)}"
    assert len(df_1d_eth) == 1826, f"ETHUSDT 1d: expected 1826, got {len(df_1d_eth)}"


def test_funding_rate_row_counts():
    df_funding_btc = pd.read_parquet(RAW_DIR / "BTCUSDT_funding_rate.parquet")
    df_funding_eth = pd.read_parquet(RAW_DIR / "ETHUSDT_funding_rate.parquet")

    assert len(df_funding_btc) == 5478, f"BTCUSDT funding: expected 5478, got {len(df_funding_btc)}"
    assert len(df_funding_eth) == 5478, f"ETHUSDT funding: expected 5478, got {len(df_funding_eth)}"


def test_date_ranges():
    df_1h_btc = pd.read_parquet(RAW_DIR / "BTCUSDT_1h_klines.parquet")
    df_1h_eth = pd.read_parquet(RAW_DIR / "ETHUSDT_1h_klines.parquet")

    for df in [df_1h_btc, df_1h_eth]:
        assert df["timestamp"].min() >= pd.Timestamp("2021-01-01", tz="UTC")
        assert df["timestamp"].max() <= pd.Timestamp("2025-12-31 23:59:59", tz="UTC")


def test_quality_checks_recorded():
    manifest_path = RAW_DIR / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    assert len(manifest["quality_checks"]) > 0
    for dataset_key, checks in manifest["quality_checks"].items():
        for check_name, check_data in checks.items():
            assert "passed" in check_data, f"{dataset_key}.{check_name} missing 'passed'"
            assert check_data["passed"] in (True, False), f"{dataset_key}.{check_name} invalid 'passed' value"


def test_features_parquet_exists():
    features_path = PROCESSED_DIR / "features.parquet"
    assert features_path.exists(), "features.parquet not found"


def test_features_row_count():
    df = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    assert len(df) == 87648, f"Expected 87648 rows, got {len(df)}"


def test_features_columns():
    df = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    expected_cols = {
        "timestamp", "symbol",
        "open", "high", "low", "close", "volume",
        "funding_rate"
    }
    assert expected_cols.issubset(set(df.columns)), f"Missing columns: {expected_cols - set(df.columns)}"


def test_features_no_duplicate_timestamps_per_symbol():
    df = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        sym_df = df[df["symbol"] == symbol]
        dupes = sym_df["timestamp"].duplicated().sum()
        assert dupes == 0, f"{symbol}: {dupes} duplicate timestamps in features"


def test_features_monotonic_timestamps_per_symbol():
    df = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        sym_df = df[df["symbol"] == symbol].sort_values("timestamp")
        diffs = sym_df["timestamp"].diff().dropna()
        assert (diffs >= pd.Timedelta(0)).all(), f"{symbol}: non-monotonic timestamps"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])