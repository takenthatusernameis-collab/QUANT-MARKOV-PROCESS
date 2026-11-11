import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import holdout_runner as hr


def _write_protocol(path: Path, text: str = "frozen protocol") -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _write_template(path: Path) -> Path:
    tmpl = {
        "protocol": {"document": "research/specifications/holdout_evaluation_protocol.md"},
        "data_provenance": {"features_parquet": "data/processed/features.parquet", "raw_manifest": "data/raw/manifest.json"},
        "execution": {"git_sha": None, "command": None, "executed_utc": None, "holdout_evaluated": False, "operator_notes": "template"},
    }
    path.write_text(json.dumps(tmpl), encoding="utf-8")
    return path


def test_compute_protocol_hash_matches_sha256(tmp_path):
    p = _write_protocol(tmp_path / "protocol.md", "abc\n")
    expected = hashlib.sha256(b"abc\n").hexdigest()
    assert hr.compute_protocol_hash(p) == expected


def test_refusal_without_execute_flag(tmp_path):
    p = _write_protocol(tmp_path / "protocol.md")
    with pytest.raises(hr.HoldoutAuthorizationError, match="--execute-holdout not provided"):
        hr.verify_execution_authorized(False, None, protocol_path=p)


def test_refusal_without_protocol_hash(tmp_path):
    p = _write_protocol(tmp_path / "protocol.md")
    with pytest.raises(hr.HoldoutAuthorizationError, match="--protocol-hash is required"):
        hr.verify_execution_authorized(True, None, protocol_path=p)


def test_refusal_with_wrong_protocol_hash(tmp_path):
    p = _write_protocol(tmp_path / "protocol.md", "content")
    with pytest.raises(hr.HoldoutAuthorizationError, match="hash does not match"):
        hr.verify_execution_authorized(True, "deadbeef", protocol_path=p)


def test_authorization_succeeds_with_matching_hash(tmp_path):
    p = _write_protocol(tmp_path / "protocol.md", "content")
    expected = hr.compute_protocol_hash(p)
    assert hr.verify_execution_authorized(True, expected, protocol_path=p) == expected


def test_main_refuses_by_default(tmp_path, capsys):
    p = _write_protocol(tmp_path / "protocol.md", "content")
    t = _write_template(tmp_path / "tmpl.json")
    rc = hr.main(["--protocol-path", str(p), "--manifest-template", str(t)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "refused" in err.lower()
    assert "--execute-holdout" in err


def test_no_lookahead_enforcement_rejects_history_ge_target():
    target = pd.Timestamp("2024-07-01 04:00:00+00:00")
    with pytest.raises(hr.HoldoutIntegrityError, match="lookahead/leakage"):
        hr.validate_no_lookahead(target, target)
    with pytest.raises(hr.HoldoutIntegrityError, match="lookahead/leakage"):
        hr.validate_no_lookahead(target, target + pd.Timedelta(hours=1))


def test_no_lookahead_enforcement_rejects_target_outside_holdout():
    outside = pd.Timestamp("2024-06-30 23:00:00+00:00")
    hist = outside - pd.Timedelta(hours=1)
    with pytest.raises(hr.HoldoutIntegrityError, match="outside holdout window"):
        hr.validate_no_lookahead(outside, hist)


def test_no_lookahead_accepts_valid_holdout_target():
    target = pd.Timestamp("2024-07-01 04:00:00+00:00")
    hist = pd.Timestamp("2024-07-01 03:00:00+00:00")
    hr.validate_no_lookahead(target, hist)  # should not raise


def test_manifest_population_sets_execution_fields(tmp_path):
    p = _write_protocol(tmp_path / "protocol.md", "content")
    tpath = _write_template(tmp_path / "tmpl.json")
    template = json.loads(tpath.read_text())
    protocol_hash = hr.compute_protocol_hash(p)
    manifest = hr.build_execution_manifest(
        template=template,
        protocol_hash=protocol_hash,
        command="holdout_runner.py --execute-holdout ...",
        executed_utc="2026-11-11T00:00:00+00:00",
        git_sha="abc123",
        features_sha256="featsha",
        raw_manifest_sha256="rawsha",
        holdout_evaluated=True,
        operator_notes="test",
    )
    assert manifest["protocol"]["protocol_sha256"] == protocol_hash
    assert manifest["execution"]["holdout_evaluated"] is True
    assert manifest["execution"]["git_sha"] == "abc123"
    assert manifest["execution"]["command"].startswith("holdout_runner.py")
    assert manifest["execution"]["executed_utc"] == "2026-11-11T00:00:00+00:00"
    assert manifest["data_provenance"]["features_sha256"] == "featsha"
    assert manifest["data_provenance"]["raw_manifest_sha256"] == "rawsha"
    # template must remain unmodified on disk
    original = json.loads(tpath.read_text())
    assert original["execution"]["holdout_evaluated"] is False


def test_validate_holdout_window_filters_correctly():
    ts = pd.date_range("2024-06-30 22:00:00", periods=6, freq="1h", tz="UTC")
    df = pd.DataFrame({"timestamp": ts, "symbol": "BTCUSDT", "close": np.linspace(100, 105, len(ts))})
    out = hr.validate_holdout_window(df)
    assert out["timestamp"].min() >= hr.HOLDOUT_START
    assert out["timestamp"].max() <= hr.HOLDOUT_END
    assert len(out) == 4  # 2024-07-01 00:00,01:00,02:00,03:00 in this range
    assert (pd.to_datetime(out["timestamp"], utc=True) < hr.HOLDOUT_START).sum() == 0


def test_print_protocol_hash_exits_zero(tmp_path, capsys):
    p = _write_protocol(tmp_path / "protocol.md", "content")
    rc = hr.main(["--protocol-path", str(p), "--print-protocol-hash"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == hr.compute_protocol_hash(p)
