"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from sdlc_tools.config import SdlcConfig


@pytest.fixture()
def default_config() -> SdlcConfig:
    """Return a default SdlcConfig for testing."""
    return SdlcConfig(
        github_token="test-token-123",
        github_repository="test-owner/test-repo",
        dry_run=True,
    )
