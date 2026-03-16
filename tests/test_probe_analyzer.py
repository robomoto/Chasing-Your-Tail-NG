"""Tests for probe_analyzer.py module."""
import pathlib
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# The module-level `secure_config_loader('config.json')` in probe_analyzer.py
# runs at import time and tries to read config.json from disk.  We intercept it
# by patching the function inside the secure_credentials module *before* the
# import occurs.

_FAKE_CONFIG = {
    "paths": {"log_dir": "/tmp/cyt_fake_logs"},
    "search": {
        "lat_min": 31.3,
        "lat_max": 37.0,
        "lon_min": -114.8,
        "lon_max": -109.0,
    },
}
_FAKE_CRED_MANAGER = MagicMock()
_FAKE_CRED_MANAGER.get_wigle_token.return_value = None


@pytest.fixture(autouse=True)
def _patch_module_level_config(monkeypatch):
    """Ensure the module-level `config` and `credential_manager` are safe."""
    # If probe_analyzer is already imported, patch its globals directly.
    if "probe_analyzer" in sys.modules:
        monkeypatch.setattr("probe_analyzer.config", _FAKE_CONFIG)
        monkeypatch.setattr("probe_analyzer.credential_manager", _FAKE_CRED_MANAGER)


# Perform the guarded import.  The patch on secure_credentials.secure_config_loader
# prevents real file I/O during the module-level call.
with patch(
    "secure_credentials.secure_config_loader",
    return_value=(_FAKE_CONFIG, _FAKE_CRED_MANAGER),
):
    from probe_analyzer import ProbeAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_log(directory: pathlib.Path, filename: str, content: str) -> pathlib.Path:
    """Write *content* to *directory/filename* and return the path."""
    p = directory / filename
    p.write_text(content)
    return p


LOG_BASIC = (
    "Current Time: 2025-07-23 14:30:00\n"
    "Found a probe!: HomeNetwork\n"
    "Current Time: 2025-07-23 14:31:00\n"
    "Found a probe!: CoffeeShop\n"
)

LOG_MULTI_SAME_SSID = (
    "Current Time: 2025-07-23 14:30:00\n"
    "Found a probe!: HomeNetwork\n"
    "Current Time: 2025-07-23 14:35:00\n"
    "Found a probe!: HomeNetwork\n"
    "Current Time: 2025-07-23 14:40:00\n"
    "Found a probe!: HomeNetwork\n"
)

LOG_NO_PROBES = (
    "Current Time: 2025-07-23 14:30:00\n"
    "No probes detected this cycle.\n"
)

LOG_NO_TIMESTAMP = "Found a probe!: OrphanSSID\n"

LOG_HEADER_ONLY = "Current Time: 2025-07-23 14:30:00\n"


# ---------------------------------------------------------------------------
# TestParseLogFile
# ---------------------------------------------------------------------------

class TestParseLogFile:
    """Unit tests for ProbeAnalyzer.parse_log_file."""

    def test_basic_extraction(self, tmp_path):
        """Two distinct probes each preceded by a timestamp."""
        log = _write_log(tmp_path, "cyt_log_072325_143000", LOG_BASIC)
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True)
        analyzer.parse_log_file(log)

        assert "HomeNetwork" in analyzer.probes
        assert "CoffeeShop" in analyzer.probes
        assert analyzer.probes["HomeNetwork"] == ["2025-07-23 14:30:00"]
        assert analyzer.probes["CoffeeShop"] == ["2025-07-23 14:31:00"]

    def test_multiple_same_ssid(self, tmp_path):
        """The same SSID seen at three different timestamps."""
        log = _write_log(tmp_path, "cyt_log_072325_143000", LOG_MULTI_SAME_SSID)
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True)
        analyzer.parse_log_file(log)

        assert len(analyzer.probes["HomeNetwork"]) == 3
        assert analyzer.probes["HomeNetwork"][0] == "2025-07-23 14:30:00"
        assert analyzer.probes["HomeNetwork"][-1] == "2025-07-23 14:40:00"

    def test_no_probes(self, tmp_path):
        """Log with timestamps but no probe lines yields empty dict."""
        log = _write_log(tmp_path, "cyt_log_072325_143000", LOG_NO_PROBES)
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True)
        analyzer.parse_log_file(log)

        assert analyzer.probes == {}

    def test_no_timestamp_falls_back_to_filename(self, tmp_path):
        """When no timestamp precedes the probe, the filename is parsed.

        Note: The source splits on '_' using the FULL path string, so the
        indices [2:4] depend on how many underscores are in the tmp_path.
        We just verify the SSID was captured (the timestamp may be garbled
        due to the path-splitting approach in the source code).
        """
        log = _write_log(tmp_path, "cyt_log_072325_143000", LOG_NO_TIMESTAMP)
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True)
        analyzer.parse_log_file(log)

        assert "OrphanSSID" in analyzer.probes
        assert len(analyzer.probes["OrphanSSID"]) == 1

    def test_header_only_no_probes(self, tmp_path):
        """A log that contains only a timestamp header (no probe lines)."""
        log = _write_log(tmp_path, "cyt_log_072325_143000", LOG_HEADER_ONLY)
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True)
        analyzer.parse_log_file(log)

        assert analyzer.probes == {}


# ---------------------------------------------------------------------------
# TestParseAllLogs
# ---------------------------------------------------------------------------

class TestParseAllLogs:
    """Tests for ProbeAnalyzer.parse_all_logs (date filtering, glob)."""

    def test_filters_old_files(self, tmp_path):
        """Files older than days_back are skipped."""
        # Recent file: use today's date in MMDDYY format
        today = datetime.now()
        recent_name = f"cyt_log_{today.strftime('%m%d%y')}_120000"
        _write_log(tmp_path, recent_name, LOG_BASIC)

        # Old file: 60 days ago
        old_date = today - timedelta(days=60)
        old_name = f"cyt_log_{old_date.strftime('%m%d%y')}_120000"
        _write_log(tmp_path, old_name, LOG_MULTI_SAME_SSID)

        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True, days_back=14)
        analyzer.parse_all_logs()

        # Only the recent file's probes should be present.
        assert "HomeNetwork" in analyzer.probes
        assert "CoffeeShop" in analyzer.probes
        # HomeNetwork should have 1 entry (from recent), not 3 extra from old.
        assert len(analyzer.probes["HomeNetwork"]) == 1

    def test_includes_unparseable_filenames(self, tmp_path):
        """Files whose date part raises ValueError are included (safe fallback).

        The source checks len(date_str)==6 before parsing, so we need a 6-char
        date_str that triggers ValueError in int() or datetime().
        'ab0025' -> int('ab') raises ValueError -> except clause includes file.
        """
        _write_log(tmp_path, "cyt_log_ab0025_120000", LOG_BASIC)
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True, days_back=14)
        analyzer.parse_all_logs()

        assert "HomeNetwork" in analyzer.probes

    def test_empty_log_dir(self, tmp_path):
        """No log files at all -- parse_all_logs should not raise."""
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True, days_back=14)
        analyzer.parse_all_logs()

        assert analyzer.probes == {}


# ---------------------------------------------------------------------------
# TestAnalyzeProbes
# ---------------------------------------------------------------------------

class TestAnalyzeProbes:
    """Tests for ProbeAnalyzer.analyze_probes aggregation."""

    def test_aggregation(self, tmp_path):
        """Results include count, first_seen, last_seen for each SSID."""
        log = _write_log(tmp_path, "cyt_log_072325_143000", LOG_MULTI_SAME_SSID)
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True)
        analyzer.parse_log_file(log)
        results = analyzer.analyze_probes()

        assert len(results) == 1
        entry = results[0]
        assert entry["ssid"] == "HomeNetwork"
        assert entry["count"] == 3
        assert entry["first_seen"] == "2025-07-23 14:30:00"
        assert entry["last_seen"] == "2025-07-23 14:40:00"
        # local_only=True means wigle_data should be None
        assert entry["wigle_data"] is None

    def test_empty_probes(self, tmp_path):
        """analyze_probes returns empty list when no probes collected."""
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=True)
        results = analyzer.analyze_probes()
        assert results == []


# ---------------------------------------------------------------------------
# TestQueryWigle
# ---------------------------------------------------------------------------

class TestQueryWigle:
    """Tests for ProbeAnalyzer.query_wigle -- always mocked, never real API."""

    def test_no_api_key_returns_error(self, tmp_path):
        """Without an API key, query_wigle returns an error dict."""
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=False)
        # Ensure no key
        analyzer.wigle_api_key = None
        result = analyzer.query_wigle("TestSSID")

        assert result == {"error": "WiGLE API key not configured"}

    @patch("probe_analyzer.requests.get")
    def test_successful_query(self, mock_get, tmp_path):
        """A mocked successful WiGLE response is returned as JSON."""
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "success": True,
            "results": [{"trilat": 33.45, "trilong": -112.07}],
        }
        mock_get.return_value = fake_response

        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=False)
        analyzer.wigle_api_key = "fake_encoded_key"
        result = analyzer.query_wigle("CoffeeShop")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["headers"]["Authorization"] == "Basic fake_encoded_key"
        assert result["success"] is True
        assert len(result["results"]) == 1

    @patch("probe_analyzer.requests.get", side_effect=ConnectionError("network down"))
    def test_network_error_returns_error_dict(self, mock_get, tmp_path):
        """Network failures are caught and returned as an error dict."""
        analyzer = ProbeAnalyzer(log_dir=tmp_path, local_only=False)
        analyzer.wigle_api_key = "fake_encoded_key"
        result = analyzer.query_wigle("TestSSID")

        assert "error" in result
        assert "network down" in result["error"]
