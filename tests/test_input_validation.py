"""Comprehensive tests for input_validation.py module."""
import json
import pytest
from pathlib import Path

from input_validation import InputValidator, SecureInputHandler


# ---------------------------------------------------------------------------
# InputValidator.validate_mac_address
# ---------------------------------------------------------------------------
class TestValidateMacAddress:
    """Tests for MAC address validation."""

    @pytest.mark.parametrize("mac", [
        "AA:BB:CC:DD:EE:FF",
        "aa:bb:cc:dd:ee:ff",
        "00:11:22:33:44:55",
        "AA-BB-CC-DD-EE-FF",
        "aA:bB:cC:dD:eE:fF",
    ])
    def test_valid_mac_addresses(self, mac):
        assert InputValidator.validate_mac_address(mac) is True

    @pytest.mark.parametrize("mac", [
        "",
        "not-a-mac",
        "GG:HH:II:JJ:KK:LL",
        "AA:BB:CC:DD:EE",         # too short
        "AA:BB:CC:DD:EE:FF:00",   # too long
        "AABBCCDDEEFF",            # no separators
        "AA:BB:CC:DD:EE:FF ",     # trailing space
    ])
    def test_invalid_mac_addresses(self, mac):
        assert InputValidator.validate_mac_address(mac) is False

    def test_non_string_input(self):
        assert InputValidator.validate_mac_address(None) is False
        assert InputValidator.validate_mac_address(12345) is False
        assert InputValidator.validate_mac_address([]) is False

    def test_oversized_input(self):
        assert InputValidator.validate_mac_address("A" * 100) is False


# ---------------------------------------------------------------------------
# InputValidator.validate_ssid
# ---------------------------------------------------------------------------
class TestValidateSSID:
    """Tests for SSID validation."""

    @pytest.mark.parametrize("ssid", [
        "HomeNetwork",
        "CoffeeShop",
        "a",                      # min length
        "A" * 32,                 # max length
        "My WiFi 123",
        "test_network-5G",
    ])
    def test_valid_ssids(self, ssid):
        assert InputValidator.validate_ssid(ssid) is True

    def test_empty_ssid(self):
        assert InputValidator.validate_ssid("") is False

    def test_too_long_ssid(self):
        assert InputValidator.validate_ssid("A" * 33) is False

    def test_non_string_input(self):
        assert InputValidator.validate_ssid(None) is False
        assert InputValidator.validate_ssid(123) is False

    def test_null_byte(self):
        assert InputValidator.validate_ssid("test\x00ssid") is False

    def test_control_characters(self):
        assert InputValidator.validate_ssid("test\x01ssid") is False

    def test_del_character_rejected(self):
        assert InputValidator.validate_ssid("\x7f") is False

    @pytest.mark.parametrize("char", InputValidator.DANGEROUS_CHARS)
    def test_each_dangerous_character_rejected(self, char):
        assert InputValidator.validate_ssid(f"test{char}ssid") is False


# ---------------------------------------------------------------------------
# InputValidator.validate_file_path
# ---------------------------------------------------------------------------
class TestValidateFilePath:
    """Tests for file path validation."""

    @pytest.mark.parametrize("path", [
        "/tmp/test.log",
        "/home/user/data/file.txt",
        "relative/path/file.txt",
        "/var/log/kismet/capture.kismet",
    ])
    def test_valid_paths(self, path):
        assert InputValidator.validate_file_path(path) is True

    def test_path_traversal_dotdot(self):
        assert InputValidator.validate_file_path("/tmp/../etc/passwd") is False

    def test_path_traversal_tilde(self):
        assert InputValidator.validate_file_path("~/secret") is False

    @pytest.mark.parametrize("char", ['<', '>', '|', '&', ';', '`'])
    def test_dangerous_characters_in_path(self, char):
        assert InputValidator.validate_file_path(f"/tmp/test{char}file") is False

    def test_oversized_path(self):
        assert InputValidator.validate_file_path("/" + "a" * 4096) is False

    def test_non_string_input(self):
        assert InputValidator.validate_file_path(None) is False
        assert InputValidator.validate_file_path(123) is False

    def test_empty_path(self):
        # Empty string is technically valid by the method (no traversal, no dangerous chars)
        assert InputValidator.validate_file_path("") is True


# ---------------------------------------------------------------------------
# InputValidator.validate_filename
# ---------------------------------------------------------------------------
class TestValidateFilename:
    """Tests for filename validation."""

    @pytest.mark.parametrize("filename", [
        "test.txt",
        "data_file-01.csv",
        "capture.kismet",
    ])
    def test_valid_filenames(self, filename):
        assert InputValidator.validate_filename(filename) is True

    @pytest.mark.parametrize("filename", [
        "",
        ".",
        "..",
        ".hidden",
    ])
    def test_rejected_dot_patterns(self, filename):
        assert InputValidator.validate_filename(filename) is False

    def test_too_long_filename(self):
        assert InputValidator.validate_filename("a" * 256) is False

    def test_boundary_length_255(self):
        assert InputValidator.validate_filename("a" * 255) is True

    def test_non_string_input(self):
        assert InputValidator.validate_filename(None) is False

    def test_filename_with_spaces(self):
        # Spaces are not in the FILENAME_PATTERN
        assert InputValidator.validate_filename("my file.txt") is False

    def test_filename_with_slash(self):
        assert InputValidator.validate_filename("dir/file.txt") is False


# ---------------------------------------------------------------------------
# InputValidator.sanitize_string
# ---------------------------------------------------------------------------
class TestSanitizeString:
    """Tests for string sanitization."""

    def test_clean_string_unchanged(self):
        assert InputValidator.sanitize_string("hello world") == "hello world"

    def test_truncation_at_max_length(self):
        result = InputValidator.sanitize_string("a" * 1500, max_length=1000)
        assert len(result) == 1000

    def test_custom_max_length(self):
        result = InputValidator.sanitize_string("abcdefgh", max_length=5)
        assert result == "abcde"

    def test_non_string_returns_empty(self):
        assert InputValidator.sanitize_string(None) == ""
        assert InputValidator.sanitize_string(123) == ""

    def test_removes_null_bytes(self):
        assert "\x00" not in InputValidator.sanitize_string("test\x00value")

    def test_removes_control_characters(self):
        result = InputValidator.sanitize_string("test\x01\x02value")
        assert result == "testvalue"

    def test_preserves_tab_newline(self):
        result = InputValidator.sanitize_string("line1\nline2\ttab")
        assert "line1\nline2\ttab" == result

    @pytest.mark.parametrize("char", InputValidator.DANGEROUS_CHARS)
    def test_removes_each_dangerous_character(self, char):
        result = InputValidator.sanitize_string(f"before{char}after")
        assert char not in result

    def test_strips_sql_keywords(self):
        result = InputValidator.sanitize_string("SELECT * FROM users")
        assert "SELECT" not in result

    def test_sql_keyword_stripping_false_positive(self):
        """sanitize_string strips 'DROP' from 'DROPLET' because it uses
        substring matching rather than whole-word matching."""
        result = InputValidator.sanitize_string("DROPLET")
        assert result == "DROPLET"

    def test_empty_string(self):
        assert InputValidator.sanitize_string("") == ""

    def test_whitespace_stripped(self):
        assert InputValidator.sanitize_string("  hello  ") == "hello"


# ---------------------------------------------------------------------------
# InputValidator.validate_config_structure
# ---------------------------------------------------------------------------
class TestValidateConfigStructure:
    """Tests for config structure validation."""

    def test_valid_config(self, sample_config):
        assert InputValidator.validate_config_structure(sample_config) is True

    def test_missing_paths_key(self):
        assert InputValidator.validate_config_structure({"timing": {}}) is False

    def test_missing_timing_key(self):
        config = {
            "paths": {"log_dir": "/tmp", "kismet_logs": "/tmp", "ignore_lists": "/tmp"},
        }
        assert InputValidator.validate_config_structure(config) is False

    def test_non_dict_input(self):
        assert InputValidator.validate_config_structure("string") is False
        assert InputValidator.validate_config_structure([]) is False

    def test_paths_not_a_dict(self):
        assert InputValidator.validate_config_structure({"paths": "bad", "timing": {}}) is False

    def test_missing_required_path_keys(self):
        config = {"paths": {"log_dir": "/tmp"}, "timing": {}}
        assert InputValidator.validate_config_structure(config) is False

    def test_invalid_path_value(self):
        config = {
            "paths": {
                "log_dir": "/tmp/../etc",
                "kismet_logs": "/tmp",
                "ignore_lists": "/tmp",
            },
            "timing": {},
        }
        assert InputValidator.validate_config_structure(config) is False

    def test_timing_not_a_dict(self):
        config = {
            "paths": {"log_dir": "/tmp", "kismet_logs": "/tmp", "ignore_lists": "/tmp"},
            "timing": "bad",
        }
        assert InputValidator.validate_config_structure(config) is False

    def test_negative_timing_value(self):
        config = {
            "paths": {"log_dir": "/tmp", "kismet_logs": "/tmp", "ignore_lists": "/tmp"},
            "timing": {"check_interval": -1},
        }
        assert InputValidator.validate_config_structure(config) is False

    def test_zero_timing_value(self):
        config = {
            "paths": {"log_dir": "/tmp", "kismet_logs": "/tmp", "ignore_lists": "/tmp"},
            "timing": {"check_interval": 0},
        }
        assert InputValidator.validate_config_structure(config) is False


# ---------------------------------------------------------------------------
# InputValidator.validate_ignore_list
# ---------------------------------------------------------------------------
class TestValidateIgnoreList:
    """Tests for ignore list validation."""

    def test_valid_mac_list(self):
        macs = ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]
        result = InputValidator.validate_ignore_list(macs, "mac")
        assert result == macs

    def test_filters_invalid_macs(self):
        macs = ["AA:BB:CC:DD:EE:FF", "not-a-mac"]
        result = InputValidator.validate_ignore_list(macs, "mac")
        assert result == ["AA:BB:CC:DD:EE:FF"]

    def test_valid_ssid_list(self):
        ssids = ["HomeNetwork", "CoffeeShop"]
        result = InputValidator.validate_ignore_list(ssids, "ssid")
        assert result == ssids

    def test_non_list_input(self):
        assert InputValidator.validate_ignore_list("not a list", "mac") == []
        assert InputValidator.validate_ignore_list(None, "ssid") == []

    def test_empty_list(self):
        assert InputValidator.validate_ignore_list([], "mac") == []


# ---------------------------------------------------------------------------
# InputValidator.validate_json_input
# ---------------------------------------------------------------------------
class TestValidateJsonInput:
    """Tests for JSON input validation."""

    def test_valid_json_dict(self):
        data = '{"key": "value"}'
        result = InputValidator.validate_json_input(data)
        assert result == {"key": "value"}

    def test_valid_json_list(self):
        data = '["a", "b"]'
        result = InputValidator.validate_json_input(data)
        assert result == ["a", "b"]

    def test_invalid_json(self):
        assert InputValidator.validate_json_input("{bad json}") is None

    def test_oversized_json(self):
        big = '{"key": "' + "x" * (1024 * 1024 + 1) + '"}'
        assert InputValidator.validate_json_input(big) is None

    def test_non_string_input(self):
        assert InputValidator.validate_json_input(123) is None

    def test_key_too_long(self):
        data = json.dumps({"a" * 101: "value"})
        assert InputValidator.validate_json_input(data) is None

    def test_value_string_too_long(self):
        data = json.dumps({"key": "x" * 10001})
        assert InputValidator.validate_json_input(data) is None

    def test_custom_max_size(self):
        data = '{"key": "value"}'
        assert InputValidator.validate_json_input(data, max_size=5) is None

    def test_nested_dict_allowed(self):
        data = json.dumps({"outer": {"inner": "val"}})
        result = InputValidator.validate_json_input(data)
        assert result is not None


# ---------------------------------------------------------------------------
# InputValidator.validate_database_path
# ---------------------------------------------------------------------------
class TestValidateDatabasePath:
    """Tests for database path validation."""

    def test_existing_file(self, tmp_path):
        db = tmp_path / "test.kismet"
        db.write_text("")
        assert InputValidator.validate_database_path(str(db)) is True

    def test_nonexistent_file(self, tmp_path):
        assert InputValidator.validate_database_path(str(tmp_path / "nope.db")) is False

    def test_glob_with_existing_base_dir(self, tmp_path):
        assert InputValidator.validate_database_path(str(tmp_path) + "/*.kismet") is True

    def test_glob_with_nonexistent_base_dir(self):
        assert InputValidator.validate_database_path("/nonexistent/dir/*.kismet") is False

    def test_path_traversal_rejected(self):
        assert InputValidator.validate_database_path("/tmp/../etc/passwd") is False


# ---------------------------------------------------------------------------
# SecureInputHandler.safe_load_config
# ---------------------------------------------------------------------------
class TestSafeLoadConfig:
    """Tests for safe config loading."""

    def test_loads_valid_config(self, tmp_path, sample_config):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(sample_config))
        handler = SecureInputHandler()
        result = handler.safe_load_config(str(config_file))
        assert result is not None
        assert "paths" in result

    def test_rejects_nonexistent_file(self):
        handler = SecureInputHandler()
        assert handler.safe_load_config("/tmp/no_such_config.json") is None

    def test_rejects_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        handler = SecureInputHandler()
        assert handler.safe_load_config(str(bad)) is None

    def test_rejects_path_traversal(self, tmp_path):
        handler = SecureInputHandler()
        assert handler.safe_load_config("/tmp/../etc/passwd") is None


# ---------------------------------------------------------------------------
# SecureInputHandler.safe_load_ignore_list
# ---------------------------------------------------------------------------
class TestSafeLoadIgnoreList:
    """Tests for safe ignore list loading."""

    def test_loads_mac_json(self, mac_list_json):
        handler = SecureInputHandler()
        result = handler.safe_load_ignore_list(mac_list_json, "mac")
        assert len(result) == 2

    def test_loads_ssid_json(self, ssid_list_json):
        handler = SecureInputHandler()
        result = handler.safe_load_ignore_list(ssid_list_json, "ssid")
        assert result == ["HomeNetwork", "CoffeeShop"]

    def test_nonexistent_file_returns_empty(self, tmp_path):
        handler = SecureInputHandler()
        result = handler.safe_load_ignore_list(tmp_path / "nope.json", "mac")
        assert result == []

    def test_legacy_format_returns_empty(self, mac_list_python):
        handler = SecureInputHandler()
        result = handler.safe_load_ignore_list(mac_list_python, "mac")
        assert result == []
