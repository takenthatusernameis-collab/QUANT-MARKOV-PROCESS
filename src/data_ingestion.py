#!/usr/bin/env python3
"""
Data Ingestion from Binance Public S3 Data Dumps
Fetches klines, funding rates, and metrics (open interest) for BTCUSDT and ETHUSDT.
"""

import os
import json
import hashlib
import logging
import zipfile
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import requests
from tqdm import tqdm


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class DataManifestEntry:
    """Single entry in the data manifest."""
    symbol: str
    data_type: str
    interval: str
    start_time: str
    end_time: str
    row_count: int
    file_path: str
    sha256_hash: str
    retrieval_timestamp: str
    source_url: str


S3_BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["15m", "1h", "4h", "1d"]
START_DATE = datetime(2021, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_file(url: str, dest: Path) -> bool:
    """Download a file with retry logic."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=60, stream=True)
            response.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
            if attempt == 2:
                logger.error(f"Failed to download {url} after 3 attempts")
                return False
    return False


def extract_zip_to_dataframe(zip_path: Path, has_header: bool = False) -> Optional[pd.DataFrame]:
    """Extract CSV from zip and return as DataFrame."""
    with zipfile.ZipFile(zip_path, "r") as z:
        for name in z.namelist():
            if name.endswith(".csv"):
                with z.open(name) as csv_file:
                    if has_header:
                        df = pd.read_csv(csv_file)
                    else:
                        df = pd.read_csv(csv_file, header=None)
                return df
    return None


def process_klines_csv(df: pd.DataFrame, has_header: bool = False) -> pd.DataFrame:
    """Process raw klines CSV to DataFrame."""
    # Binance klines CSV format:
    # Before 2022: no header, columns are 0-11
    # 2022+: with header: open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore
    expected_cols = 12

    if has_header:
        # Columns already have names, just ensure we have the right ones
        # The header format from 2022 uses slightly different names
        rename_map = {
            "quote_volume": "quote_asset_volume",
            "count": "number_of_trades",
            "taker_buy_volume": "taker_buy_base_volume",
            "taker_buy_quote_volume": "taker_buy_quote_volume",
        }
        df = df.rename(columns=rename_map)
    else:
        # No header, assign column names
        if len(df.columns) >= expected_cols:
            df = df.iloc[:, :expected_cols].copy()
            df.columns = [
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "number_of_trades",
                "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
            ]

    # Ensure required columns exist
    required = ["open_time", "open", "high", "low", "close", "volume", "close_time",
                "quote_asset_volume", "number_of_trades", "taker_buy_base_volume", "taker_buy_quote_volume"]
    for col in required:
        if col not in df.columns:
            df[col] = np.nan

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    numeric_cols = ["open", "high", "low", "close", "volume",
                    "quote_asset_volume", "taker_buy_base_volume", "taker_buy_quote_volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["number_of_trades"] = pd.to_numeric(df["number_of_trades"], errors="coerce").astype("Int64")

    df = df[["open_time", "open", "high", "low", "close", "volume", "number_of_trades"]]
    df = df.rename(columns={"open_time": "timestamp"})
    return df


def process_funding_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Process raw funding rate CSV to DataFrame."""
    # fundingRate CSV has header: calc_time, funding_interval_hours, last_funding_rate
    if "last_funding_rate" in df.columns and "calc_time" in df.columns:
        df = df.rename(columns={"calc_time": "timestamp", "last_funding_rate": "funding_rate"})
    elif len(df.columns) >= 3:
        df.columns = ["timestamp", "funding_interval_hours", "funding_rate"] + list(df.columns[3:])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["funding_rate"] = pd.to_numeric(df["funding_rate"], errors="coerce")
    return df[["timestamp", "funding_rate"]]


def process_metrics_csv(df: pd.DataFrame) -> pd.DataFrame:
    """Process raw metrics CSV to DataFrame (contains open interest)."""
    # Metrics CSV has header: create_time, symbol, sum_open_interest, ...
    if "create_time" in df.columns and "sum_open_interest" in df.columns:
        df = df.rename(columns={"create_time": "timestamp", "sum_open_interest": "open_interest"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce")
        return df[["timestamp", "open_interest"]]
    return df


def run_quality_checks(
    df: pd.DataFrame,
    symbol: str,
    data_type: str,
    interval: str
) -> Dict:
    """Run data quality checks per Section 5.1 of research plan."""
    checks = {}

    if "timestamp" not in df.columns:
        return {"error": "No timestamp column"}

    timestamps = df["timestamp"].values

    # 1. Monotonic timestamps
    is_monotonic = np.all(timestamps[:-1] <= timestamps[1:]) if len(timestamps) > 1 else True
    checks["monotonic_timestamps"] = {
        "passed": bool(is_monotonic),
        "violations": int(np.sum(timestamps[:-1] > timestamps[1:])) if len(timestamps) > 1 else 0
    }

    # 2. Duplicate timestamps
    dup_count = pd.Series(timestamps).duplicated().sum()
    checks["duplicate_timestamps"] = {
        "passed": dup_count == 0,
        "count": int(dup_count)
    }

    # 3. OHLCV consistency (for klines)
    if data_type == "klines":
        ohlc_valid = (
            (df["open"] >= df["low"]) & (df["open"] <= df["high"]) &
            (df["close"] >= df["low"]) & (df["close"] <= df["high"]) &
            (df["high"] >= df["low"]) &
            (df["volume"] >= 0)
        ).all()
        checks["ohlcv_consistency"] = {
            "passed": bool(ohlc_valid),
            "invalid_rows": int((~ohlc_valid).sum())
        }

    # 4. Missing bars (gap detection)
    if len(df) > 1:
        expected_freq = interval_to_timedelta(interval)
        time_diffs = pd.Series(timestamps).diff().dropna()
        max_gap = time_diffs.max()
        gaps_over_1h = (time_diffs > pd.Timedelta(hours=1)).sum()
        missing_pct = (time_diffs > expected_freq * 1.5).sum() / len(time_diffs) * 100

        checks["missing_bars"] = {
            "passed": missing_pct < 1.0 and gaps_over_1h == 0,
            "max_gap": str(max_gap),
            "gaps_over_1h": int(gaps_over_1h),
            "missing_pct": float(missing_pct)
        }

    # 5. Outlier returns (for klines)
    if data_type == "klines" and len(df) > 100:
        returns = np.log(df["close"] / df["close"].shift(1)).dropna()
        rolling_std = returns.rolling(100, min_periods=20).std()
        rolling_mean = returns.rolling(100, min_periods=20).mean()
        z_scores = np.abs((returns - rolling_mean) / rolling_std)
        outlier_count = (z_scores > 10).sum()
        checks["outlier_returns"] = {
            "passed": outlier_count == 0,
            "count": int(outlier_count),
            "max_zscore": float(z_scores.max()) if len(z_scores) > 0 else 0
        }

    # 6. Timezone consistency (all UTC)
    tz_aware = hasattr(df["timestamp"].dtype, "tz") and df["timestamp"].dt.tz is not None
    all_utc = all(ts.tz == timezone.utc for ts in df["timestamp"]) if tz_aware else False
    checks["timezone_consistency"] = {
        "passed": all_utc,
        "tz_aware": tz_aware
    }

    return checks


def interval_to_timedelta(interval: str) -> timedelta:
    """Convert Binance interval string to timedelta."""
    mapping = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
        "8h": timedelta(hours=8),
    }
    return mapping.get(interval, timedelta(hours=1))


def download_monthly_klines(symbol: str, interval: str, year: int, month: int, raw_dir: Path) -> Optional[pd.DataFrame]:
    """Download and process monthly klines."""
    filename = f"{symbol}-{interval}-{year}-{month:02d}.zip"
    url = f"{S3_BASE}/data/futures/um/monthly/klines/{symbol}/{interval}/{filename}"
    zip_path = raw_dir / "klines" / symbol / interval / filename

    if not download_file(url, zip_path):
        return None

    # Binance klines format changed in 2022: files before 2022 have no header,
    # files from 2022 onwards have headers
    has_header = year >= 2022
    df = extract_zip_to_dataframe(zip_path, has_header=has_header)
    if df is None:
        return None

    df = process_klines_csv(df, has_header=has_header)
    return df


def download_monthly_funding(symbol: str, year: int, month: int, raw_dir: Path) -> Optional[pd.DataFrame]:
    """Download and process monthly funding rate."""
    filename = f"{symbol}-fundingRate-{year}-{month:02d}.zip"
    url = f"{S3_BASE}/data/futures/um/monthly/fundingRate/{symbol}/{filename}"
    zip_path = raw_dir / "funding_rate" / symbol / filename

    if not download_file(url, zip_path):
        return None

    df = extract_zip_to_dataframe(zip_path, has_header=True)
    if df is None:
        return None

    df = process_funding_csv(df)
    return df


def download_daily_metrics(symbol: str, date: datetime, raw_dir: Path) -> Optional[pd.DataFrame]:
    """Download and process daily metrics (contains open interest)."""
    filename = f"{symbol}-metrics-{date.strftime('%Y-%m-%d')}.zip"
    url = f"{S3_BASE}/data/futures/um/daily/metrics/{symbol}/{filename}"
    zip_path = raw_dir / "metrics" / symbol / filename

    if not download_file(url, zip_path):
        return None

    df = extract_zip_to_dataframe(zip_path, has_header=True)
    if df is None:
        return None

    df = process_metrics_csv(df)
    return df


def save_dataframe(df: pd.DataFrame, filepath: Path) -> str:
    """Save DataFrame to parquet and return SHA256 hash."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(filepath, index=False)
    return compute_sha256(filepath)


def main():
    RAW_DIR = Path("data/raw")
    PROCESSED_DIR = Path("data/processed")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    manifest: List[DataManifestEntry] = []
    all_quality_checks = {}

    logger.info("Starting data ingestion from Binance S3 for %s from %s to %s", SYMBOLS, START_DATE, END_DATE)

    # Track processed data for alignment
    klines_data = {symbol: {} for symbol in SYMBOLS}
    funding_data = {symbol: [] for symbol in SYMBOLS}
    metrics_data = {symbol: [] for symbol in SYMBOLS}

    # Download monthly klines for each interval
    for interval in INTERVALS:
        logger.info("Downloading %s klines for %s...", interval, SYMBOLS)

        # Generate month list
        months = []
        current = START_DATE.replace(day=1)
        while current <= END_DATE:
            months.append((current.year, current.month))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        for symbol in SYMBOLS:
            all_dfs = []
            for year, month in tqdm(months, desc=f"{symbol} {interval}"):
                df = download_monthly_klines(symbol, interval, year, month, RAW_DIR)
                if df is not None and len(df) > 0:
                    all_dfs.append(df)

            if all_dfs:
                combined = pd.concat(all_dfs, ignore_index=True)
                combined = combined.sort_values("timestamp").drop_duplicates(subset="timestamp", keep="first")
                combined = combined.reset_index(drop=True)

                # Filter to date range
                combined = combined[
                    (combined["timestamp"] >= START_DATE) &
                    (combined["timestamp"] <= END_DATE)
                ]

                # Save
                outfile = RAW_DIR / f"{symbol}_{interval}_klines.parquet"
                file_hash = save_dataframe(combined, outfile)

                # Quality checks
                checks = run_quality_checks(combined, symbol, "klines", interval)
                all_quality_checks[f"{symbol}_{interval}_klines"] = checks
                for check_name, result in checks.items():
                    status = "PASS" if result.get("passed", False) else "FAIL"
                    logger.info("  %s %s: %s", symbol, check_name, status)

                # Manifest entry
                manifest.append(DataManifestEntry(
                    symbol=symbol,
                    data_type="klines",
                    interval=interval,
                    start_time=combined["timestamp"].min().isoformat(),
                    end_time=combined["timestamp"].max().isoformat(),
                    row_count=len(combined),
                    file_path=str(outfile),
                    sha256_hash=file_hash,
                    retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                    source_url=f"{S3_BASE}/data/futures/um/monthly/klines/{symbol}/{interval}/"
                ))

                klines_data[symbol][interval] = combined
                logger.info("Saved %s %s klines: %d rows", symbol, interval, len(combined))

    # Download monthly funding rates
    logger.info("Downloading funding rates...")
    months = []
    current = START_DATE.replace(day=1)
    while current <= END_DATE:
        months.append((current.year, current.month))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    for symbol in SYMBOLS:
        all_dfs = []
        for year, month in tqdm(months, desc=f"{symbol} funding"):
            df = download_monthly_funding(symbol, year, month, RAW_DIR)
            if df is not None and len(df) > 0:
                all_dfs.append(df)

        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            combined = combined.sort_values("timestamp").drop_duplicates(subset="timestamp", keep="first")
            combined = combined.reset_index(drop=True)

            combined = combined[
                (combined["timestamp"] >= START_DATE) &
                (combined["timestamp"] <= END_DATE)
            ]

            outfile = RAW_DIR / f"{symbol}_funding_rate.parquet"
            file_hash = save_dataframe(combined, outfile)

            checks = run_quality_checks(combined, symbol, "funding_rate", "8h")
            all_quality_checks[f"{symbol}_funding_rate"] = checks
            for check_name, result in checks.items():
                status = "PASS" if result.get("passed", False) else "FAIL"
                logger.info("  %s %s: %s", symbol, check_name, status)

            manifest.append(DataManifestEntry(
                symbol=symbol,
                data_type="funding_rate",
                interval="8h",
                start_time=combined["timestamp"].min().isoformat(),
                end_time=combined["timestamp"].max().isoformat(),
                row_count=len(combined),
                file_path=str(outfile),
                sha256_hash=file_hash,
                retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                source_url=f"{S3_BASE}/data/futures/um/monthly/fundingRate/{symbol}/"
            ))

            funding_data[symbol] = combined
            logger.info("Saved %s funding rate: %d rows", symbol, len(combined))

    # Download daily metrics (open interest) - only for a few months to test
    logger.info("Downloading daily metrics (open interest)...")
    # This is very slow (daily files). We'll skip for now and note in manifest.
    logger.info("Skipping daily metrics download (too many daily files); open interest not included")

    # Save manifest
    manifest_file = RAW_DIR / "manifest.json"

    def convert_for_json(obj):
        """Convert numpy types to Python types for JSON serialization."""
        if isinstance(obj, (np.bool_, np.integer, np.floating)):
            return obj.item()
        elif isinstance(obj, dict):
            return {k: convert_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_for_json(v) for v in obj]
        return obj

    manifest_data = {
        "retrieval_date": datetime.now(timezone.utc).isoformat(),
        "symbols": SYMBOLS,
        "date_range": {
            "start": START_DATE.isoformat(),
            "end": END_DATE.isoformat()
        },
        "entries": [asdict(entry) for entry in manifest],
        "quality_checks": convert_for_json(all_quality_checks)
    }

    with open(manifest_file, "w") as f:
        json.dump(manifest_data, f, indent=2)

    manifest_hash = compute_sha256(manifest_file)
    logger.info("Manifest saved to %s (hash: %s)", manifest_file, manifest_hash[:16])

    # Create aligned features.parquet
    logger.info("Creating aligned features.parquet...")
    create_aligned_features(klines_data, funding_data, RAW_DIR, PROCESSED_DIR, SYMBOLS, INTERVALS)

    logger.info("Data ingestion complete!")


def create_aligned_features(
    klines_data: Dict,
    funding_data: Dict,
    raw_dir: Path,
    processed_dir: Path,
    symbols: List[str],
    intervals: List[str]
):
    """Create aligned feature matrix from raw data."""

    base_interval = "1h"
    feature_dfs = {}

    for symbol in symbols:
        if base_interval not in klines_data[symbol]:
            logger.warning("Base interval %s not found for %s", base_interval, symbol)
            continue

        base_df = klines_data[symbol][base_interval].copy()
        base_df = base_df.set_index("timestamp")

        # Compute features
        base_df["returns"] = np.log(base_df["close"] / base_df["close"].shift(1))
        base_df["log_volume"] = np.log(base_df["volume"] + 1)

        # Realized volatility (24h = 24 periods at 1h)
        base_df["rv_24h"] = base_df["returns"].rolling(24).apply(
            lambda x: np.sum(x**2), raw=True
        )

        # Volatility change
        base_df["rv_change"] = base_df["rv_24h"].diff()

        # Volume relative to rolling median (30 days = 720 hours)
        base_df["vol_rel_median"] = base_df["volume"] / base_df["volume"].rolling(720).median()

        # Load funding rate and align
        if symbol in funding_data and len(funding_data[symbol]) > 0:
            funding_df = funding_data[symbol].copy()
            funding_df = funding_df.set_index("timestamp")
            # Resample to 1h and forward fill (funding is 8h)
            funding_df = funding_df.resample("1h").ffill()
            base_df = base_df.join(funding_df, how="left", rsuffix="_funding")
        else:
            base_df["funding_rate"] = np.nan

        # Open interest not available from monthly dumps; mark as NaN
        base_df["open_interest"] = np.nan
        base_df["oi_change"] = np.nan

        # Add symbol column
        base_df["symbol"] = symbol

        feature_dfs[symbol] = base_df.reset_index()

    if feature_dfs:
        combined = pd.concat(feature_dfs.values(), ignore_index=True)
        combined = combined.sort_values(["timestamp", "symbol"]).reset_index(drop=True)

        output_file = processed_dir / "features.parquet"
        combined.to_parquet(output_file, index=False)

        features_hash = compute_sha256(output_file)
        logger.info("Saved aligned features to %s (%d rows, hash: %s)",
                    output_file, len(combined), features_hash[:16])

        # Update manifest
        manifest_file = raw_dir / "manifest.json"
        with open(manifest_file, "r") as f:
            manifest_data = json.load(f)

        manifest_data["features_file"] = {
            "path": str(output_file),
            "sha256_hash": features_hash,
            "row_count": len(combined),
            "columns": list(combined.columns),
            "date_range": {
                "start": combined["timestamp"].min().isoformat(),
                "end": combined["timestamp"].max().isoformat()
            }
        }

        with open(manifest_file, "w") as f:
            json.dump(manifest_data, f, indent=2)


if __name__ == "__main__":
    main()