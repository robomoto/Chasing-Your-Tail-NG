"""Tests for secure_credentials.py."""
import json
import os
import stat

import pytest

from secure_credentials import (
    SecureCredentialManager,
    get_environment_credentials,
    secure_config_loader,
)


# ---------------------------------------------------------------------------
# SecureCredentialManager.__init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_creates_credentials_directory(self, tmp_path):
        cred_dir = tmp_path / "creds"
        SecureCredentialManager(credentials_dir=str(cred_dir))
        assert cred_dir.is_dir()

    def test_directory_permissions_0700(self, tmp_path):
        cred_dir = tmp_path / "creds"
        SecureCredentialManager(credentials_dir=str(cred_dir))
        mode = cred_dir.stat().st_mode & 0o777
        assert mode == 0o700

    def test_existing_directory_is_reused(self, tmp_path):
        cred_dir = tmp_path / "creds"
        cred_dir.mkdir(mode=0o700)
        mgr = SecureCredentialManager(credentials_dir=str(cred_dir))
        assert mgr.credentials_dir == cred_dir


# ---------------------------------------------------------------------------
# _generate_key_from_password
# ---------------------------------------------------------------------------

class TestGenerateKey:
    def test_deterministic_same_password_and_salt(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        salt = b"fixed_salt_value"
        key1 = mgr._generate_key_from_password(b"mypassword", salt)
        key2 = mgr._generate_key_from_password(b"mypassword", salt)
        assert key1 == key2

    def test_different_salt_produces_different_key(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        key1 = mgr._generate_key_from_password(b"mypassword", b"salt_one_16byte!")
        key2 = mgr._generate_key_from_password(b"mypassword", b"salt_two_16byte!")
        assert key1 != key2


# ---------------------------------------------------------------------------
# store_credential / get_credential round-trip
# ---------------------------------------------------------------------------

class TestStoreAndGet:
    def test_round_trip(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        mgr.store_credential("wigle", "token", "secret_value_42")
        assert mgr.get_credential("wigle", "token") == "secret_value_42"

    def test_multiple_services(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        mgr.store_credential("wigle", "token", "wigle_tok")
        mgr.store_credential("other", "api_key", "other_key")
        assert mgr.get_credential("wigle", "token") == "wigle_tok"
        assert mgr.get_credential("other", "api_key") == "other_key"

    def test_overwrite_credential(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        mgr.store_credential("svc", "key", "old_value")
        mgr.store_credential("svc", "key", "new_value")
        assert mgr.get_credential("svc", "key") == "new_value"


# ---------------------------------------------------------------------------
# store_credential input validation
# ---------------------------------------------------------------------------

class TestStoreValidation:
    def test_empty_service_raises(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        with pytest.raises(ValueError, match="empty"):
            mgr.store_credential("", "token", "value")

    def test_empty_value_raises(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        with pytest.raises(ValueError, match="empty"):
            mgr.store_credential("svc", "key", "   ")

    def test_non_string_raises(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        with pytest.raises(ValueError, match="strings"):
            mgr.store_credential("svc", "key", 12345)

    def test_too_long_value_raises(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        with pytest.raises(ValueError, match="too long"):
            mgr.store_credential("svc", "key", "x" * 10001)


# ---------------------------------------------------------------------------
# get_credential edge cases
# ---------------------------------------------------------------------------

class TestGetEdgeCases:
    def test_missing_credential_returns_none(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        mgr.store_credential("svc", "key", "val")
        assert mgr.get_credential("svc", "nonexistent") is None

    def test_no_credentials_file_returns_none(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        assert mgr.get_credential("svc", "key") is None


# ---------------------------------------------------------------------------
# migrate_from_config
# ---------------------------------------------------------------------------

class TestMigrateFromConfig:
    def test_migrates_wigle_token(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        config = {
            "api_keys": {
                "wigle": {"encoded_token": "my_wigle_token_abc123"}
            }
        }
        mgr.migrate_from_config(config)
        assert mgr.get_credential("wigle", "encoded_token") == "my_wigle_token_abc123"

    def test_no_wigle_key_does_not_error(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        config = {"api_keys": {"other_service": {}}}
        mgr.migrate_from_config(config)  # should not raise
        assert mgr.get_credential("wigle", "encoded_token") is None


# ---------------------------------------------------------------------------
# File permissions on credential files
# ---------------------------------------------------------------------------

class TestFilePermissions:
    def test_credentials_file_is_0600(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        mgr.store_credential("svc", "key", "val")
        mode = mgr.credentials_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_key_file_is_0600(self, tmp_path):
        mgr = SecureCredentialManager(credentials_dir=str(tmp_path / "creds"))
        mgr.store_credential("svc", "key", "val")
        mode = mgr.key_file.stat().st_mode & 0o777
        assert mode == 0o600


# ---------------------------------------------------------------------------
# secure_config_loader
# ---------------------------------------------------------------------------

class TestSecureConfigLoader:
    def test_loads_config_and_returns_tuple(self, tmp_path, monkeypatch):
        config_data = {
            "paths": {"base_dir": "."},
            "timing": {"check_interval": 60},
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        # Point the credential manager at a temp directory
        monkeypatch.chdir(tmp_path)
        result = secure_config_loader(config_path=str(config_file))
        assert isinstance(result, tuple)
        assert len(result) == 2
        config, cred_mgr = result
        assert isinstance(config, dict)
        assert isinstance(cred_mgr, SecureCredentialManager)
        assert config["paths"]["base_dir"] == "."

    def test_config_without_api_keys(self, tmp_path, monkeypatch):
        config_data = {"paths": {"base_dir": "."}}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        monkeypatch.chdir(tmp_path)
        config, cred_mgr = secure_config_loader(config_path=str(config_file))
        assert "api_keys" not in config


# ---------------------------------------------------------------------------
# get_environment_credentials
# ---------------------------------------------------------------------------

class TestGetEnvironmentCredentials:
    def test_returns_dict_with_expected_keys(self, monkeypatch):
        monkeypatch.delenv("WIGLE_API_TOKEN", raising=False)
        monkeypatch.delenv("CYT_DB_PASSWORD", raising=False)
        result = get_environment_credentials()
        assert "wigle_token" in result
        assert "db_password" in result

    def test_reads_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("WIGLE_API_TOKEN", "tok_abc")
        monkeypatch.setenv("CYT_DB_PASSWORD", "pass_xyz")
        result = get_environment_credentials()
        assert result["wigle_token"] == "tok_abc"
        assert result["db_password"] == "pass_xyz"

    def test_missing_env_vars_return_none(self, monkeypatch):
        monkeypatch.delenv("WIGLE_API_TOKEN", raising=False)
        monkeypatch.delenv("CYT_DB_PASSWORD", raising=False)
        result = get_environment_credentials()
        assert result["wigle_token"] is None
        assert result["db_password"] is None
