"""Tests for S3/MinIO helper functions."""

from __future__ import annotations

import pytest
from s3fs.core import S3FileSystem

from core.config import settings
from core.helpers.s3 import S3_STORAGE_OPTIONS, get_s3_fs


class TestGetS3Fs:
    """Test the S3FileSystem factory."""

    @pytest.mark.helper
    def test_get_s3_fs_creates_instance(self) -> None:
        """get_s3_fs() must return an S3FileSystem instance."""
        fs: S3FileSystem = get_s3_fs()
        assert fs is not None
        # S3FileSystem has a 'ls' method
        assert hasattr(fs, "ls")

    @pytest.mark.helper
    def test_uses_settings_credentials(self) -> None:
        """The S3FileSystem must use credentials from settings."""
        fs: S3FileSystem = get_s3_fs()
        assert fs.key == settings.minio.root_user
        assert fs.secret == settings.minio.root_password

    @pytest.mark.helper
    def test_uses_custom_endpoint(self) -> None:
        """The S3FileSystem must use the configured MinIO endpoint."""
        fs: S3FileSystem = get_s3_fs()
        # S3FileSystem stores endpoint in storage_options
        assert settings.minio.endpoint in str(object=fs.endpoint_url)


class TestS3StorageOptions:
    """Test the S3_STORAGE_OPTIONS constant."""

    @pytest.mark.helper
    def test_storage_options_contain_credentials(self) -> None:
        """S3_STORAGE_OPTIONS must include aws keys and endpoint."""
        assert S3_STORAGE_OPTIONS["aws_access_key_id"] == settings.minio.root_user
        assert S3_STORAGE_OPTIONS["aws_secret_access_key"] == settings.minio.root_password
        assert S3_STORAGE_OPTIONS["aws_endpoint_url"] == settings.minio.endpoint

    @pytest.mark.helper
    def test_allows_http(self) -> None:
        """S3_STORAGE_OPTIONS must allow HTTP (for local MinIO)."""
        assert S3_STORAGE_OPTIONS.get("aws_allow_http") == "true"

    @pytest.mark.helper
    def test_default_region(self) -> None:
        """S3_STORAGE_OPTIONS must default to us-east-1."""
        assert S3_STORAGE_OPTIONS.get("aws_region") == "us-east-1"
