"""Tests for secure_ignore_loader.py"""
import json
import pathlib
import pytest

from secure_ignore_loader import SecureIgnoreLoader, load_ignore_lists


# ---------------------------------------------------------------------------
# load_mac_list
# ---------------------------------------------------------------------------

class TestLoadMacList:
    """Tests for SecureIgnoreLoader.load_mac_list"""

    def test_load_json_format(self, mac_list_json):
        result = SecureIgnoreLoader.load_mac_list(mac_list_json)
        assert result == ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]

    def test_load_python_format(self, mac_list_python):
        result = SecureIgnoreLoader.load_mac_list(mac_list_python)
        assert result == ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]

    def test_missing_file_returns_empty(self, tmp_path):
        result = SecureIgnoreLoader.load_mac_list(tmp_path / "nonexistent.json")
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("")
        result = SecureIgnoreLoader.load_mac_list(p)
        assert result == []

    def test_mixed_valid_invalid_macs(self, tmp_path):
        p = tmp_path / "mixed.json"
        p.write_text(json.dumps(["AA:BB:CC:DD:EE:FF", "not-a-mac", "11:22:33:44:55:66"]))
        result = SecureIgnoreLoader.load_mac_list(p)
        assert result == ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]

    def test_normalizes_to_uppercase(self, tmp_path):
        p = tmp_path / "lower.json"
        p.write_text(json.dumps(["aa:bb:cc:dd:ee:ff"]))
        result = SecureIgnoreLoader.load_mac_list(p)
        assert result == ["AA:BB:CC:DD:EE:FF"]

    def test_non_list_json_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"mac": "AA:BB:CC:DD:EE:FF"}))
        result = SecureIgnoreLoader.load_mac_list(p)
        assert result == []

    def test_non_string_entries_skipped(self, tmp_path):
        p = tmp_path / "nums.json"
        p.write_text(json.dumps(["AA:BB:CC:DD:EE:FF", 12345, None]))
        result = SecureIgnoreLoader.load_mac_list(p)
        assert result == ["AA:BB:CC:DD:EE:FF"]


# ---------------------------------------------------------------------------
# load_ssid_list
# ---------------------------------------------------------------------------

class TestLoadSsidList:
    """Tests for SecureIgnoreLoader.load_ssid_list"""

    def test_load_json_format(self, ssid_list_json):
        result = SecureIgnoreLoader.load_ssid_list(ssid_list_json)
        assert result == ["HomeNetwork", "CoffeeShop"]

    def test_load_python_format(self, tmp_path):
        p = tmp_path / "ssid_list.py"
        p.write_text("non_alert_ssid_list = ['HomeNetwork', 'CoffeeShop']")
        result = SecureIgnoreLoader.load_ssid_list(p)
        assert result == ["HomeNetwork", "CoffeeShop"]

    def test_missing_file_returns_empty(self, tmp_path):
        result = SecureIgnoreLoader.load_ssid_list(tmp_path / "nope.json")
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("")
        result = SecureIgnoreLoader.load_ssid_list(p)
        assert result == []

    def test_invalid_ssids_skipped(self, tmp_path):
        # SSIDs with dangerous chars are rejected by InputValidator
        p = tmp_path / "bad_ssid.json"
        p.write_text(json.dumps(["GoodSSID", "<script>alert(1)</script>", "AlsoGood"]))
        result = SecureIgnoreLoader.load_ssid_list(p)
        assert "GoodSSID" in result
        assert "AlsoGood" in result
        assert len(result) == 2

    def test_empty_ssid_string_skipped(self, tmp_path):
        p = tmp_path / "empty_ssid.json"
        p.write_text(json.dumps(["ValidSSID", ""]))
        result = SecureIgnoreLoader.load_ssid_list(p)
        assert result == ["ValidSSID"]


# ---------------------------------------------------------------------------
# _parse_python_list
# ---------------------------------------------------------------------------

class TestParsePythonList:
    """Tests for SecureIgnoreLoader._parse_python_list"""

    def test_basic_single_quotes(self):
        content = "ignore_list = ['AA:BB:CC:DD:EE:FF', '11:22:33:44:55:66']"
        result = SecureIgnoreLoader._parse_python_list(content, "ignore_list")
        assert result == ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]

    def test_with_comments(self):
        content = (
            "# My MAC list\n"
            "ignore_list = ['AA:BB:CC:DD:EE:FF']  # home router\n"
        )
        result = SecureIgnoreLoader._parse_python_list(content, "ignore_list")
        assert result == ["AA:BB:CC:DD:EE:FF"]

    def test_missing_variable_raises(self):
        content = "other_var = ['foo']"
        with pytest.raises(ValueError, match="Could not find ignore_list"):
            SecureIgnoreLoader._parse_python_list(content, "ignore_list")

    def test_multiline_list(self):
        content = (
            "ignore_list = [\n"
            "    'AA:BB:CC:DD:EE:FF',\n"
            "    '11:22:33:44:55:66'\n"
            "]"
        )
        result = SecureIgnoreLoader._parse_python_list(content, "ignore_list")
        assert result == ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]


# ---------------------------------------------------------------------------
# save_mac_list / save_ssid_list
# ---------------------------------------------------------------------------

class TestSaveLists:
    """Tests for save_mac_list and save_ssid_list"""

    def test_save_mac_list_roundtrip(self, tmp_path):
        p = tmp_path / "macs.json"
        macs = ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]
        SecureIgnoreLoader.save_mac_list(macs, p)
        loaded = SecureIgnoreLoader.load_mac_list(p)
        assert loaded == macs

    def test_save_mac_list_normalizes_uppercase(self, tmp_path):
        p = tmp_path / "macs.json"
        SecureIgnoreLoader.save_mac_list(["aa:bb:cc:dd:ee:ff"], p)
        data = json.loads(p.read_text())
        assert data == ["AA:BB:CC:DD:EE:FF"]

    def test_save_mac_list_filters_invalid(self, tmp_path):
        p = tmp_path / "macs.json"
        SecureIgnoreLoader.save_mac_list(["AA:BB:CC:DD:EE:FF", "bad"], p)
        data = json.loads(p.read_text())
        assert data == ["AA:BB:CC:DD:EE:FF"]

    def test_save_ssid_list_roundtrip(self, tmp_path):
        p = tmp_path / "ssids.json"
        ssids = ["HomeNetwork", "CoffeeShop"]
        SecureIgnoreLoader.save_ssid_list(ssids, p)
        loaded = SecureIgnoreLoader.load_ssid_list(p)
        assert loaded == ssids

    def test_save_ssid_list_filters_invalid(self, tmp_path):
        p = tmp_path / "ssids.json"
        SecureIgnoreLoader.save_ssid_list(["Good", "<bad>"], p)
        data = json.loads(p.read_text())
        assert data == ["Good"]


# ---------------------------------------------------------------------------
# load_ignore_lists convenience function
# ---------------------------------------------------------------------------

class TestLoadIgnoreLists:
    """Tests for the load_ignore_lists() convenience function"""

    def test_loads_both_lists(self, tmp_path, monkeypatch):
        # Set up ignore_lists directory relative to cwd
        ignore_dir = tmp_path / "ignore_lists"
        ignore_dir.mkdir()
        mac_file = ignore_dir / "mac_list.json"
        ssid_file = ignore_dir / "ssid_list.json"
        mac_file.write_text(json.dumps(["AA:BB:CC:DD:EE:FF"]))
        ssid_file.write_text(json.dumps(["HomeNetwork"]))

        monkeypatch.chdir(tmp_path)

        config = {
            "paths": {
                "ignore_lists": {
                    "mac": "mac_list.json",
                    "ssid": "ssid_list.json",
                }
            }
        }
        mac_list, ssid_list = load_ignore_lists(config)
        assert mac_list == ["AA:BB:CC:DD:EE:FF"]
        assert ssid_list == ["HomeNetwork"]

    def test_missing_files_return_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = {
            "paths": {
                "ignore_lists": {
                    "mac": "no_such_mac.json",
                    "ssid": "no_such_ssid.json",
                }
            }
        }
        mac_list, ssid_list = load_ignore_lists(config)
        assert mac_list == []
        assert ssid_list == []
