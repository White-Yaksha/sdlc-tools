"""Tests for the TagManager."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sdlc_tools.config import SdlcConfig
from sdlc_tools.tagger import TagManager


@pytest.fixture()
def mock_client() -> MagicMock:
    client = MagicMock()
    client.dry_run = False
    return client


@pytest.fixture()
def config(tmp_path: Path) -> SdlcConfig:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({
            "action": "closed",
            "pull_request": {
                "merged": True,
                "base": {"ref": "releases/2026.3"},
            },
        }),
        encoding="utf-8",
    )
    return SdlcConfig(
        release_prefix="releases",
        release_tag_name="v2026.3.0",
        github_event_path=str(event),
    )


class TestHandleEvent:
    def test_merged_pr_creates_tag(self, mock_client: MagicMock, config: SdlcConfig) -> None:
        mock_client.get_ref_sha.return_value = "abc123"
        mock_client.tag_exists.return_value = False
        mock_client.find_release_by_tag.return_value = None
        mock_client.create_tag.return_value = {"object": {"sha": "abc123"}}
        mock_client.create_release.return_value = {"id": 1}

        mgr = TagManager(mock_client, config)
        mgr.handle_event("owner", "repo")

        mock_client.create_tag.assert_called_once_with("owner", "repo", "v2026.3.0", "abc123")
        mock_client.create_release.assert_called_once()

    def test_existing_tag_deleted_first(self, mock_client: MagicMock, config: SdlcConfig) -> None:
        mock_client.get_ref_sha.return_value = "abc123"
        mock_client.tag_exists.return_value = True
        mock_client.find_release_by_tag.return_value = None
        mock_client.create_tag.return_value = {"object": {"sha": "abc123"}}
        mock_client.create_release.return_value = {"id": 1}

        mgr = TagManager(mock_client, config)
        mgr.handle_event("owner", "repo")

        mock_client.delete_tag.assert_called_once()
        mock_client.create_tag.assert_called_once()

    def test_existing_release_deleted_first(
        self, mock_client: MagicMock, config: SdlcConfig,
    ) -> None:
        mock_client.get_ref_sha.return_value = "abc123"
        mock_client.tag_exists.return_value = True
        mock_client.find_release_by_tag.return_value = 42
        mock_client.create_tag.return_value = {"object": {"sha": "abc123"}}
        mock_client.create_release.return_value = {"id": 99}

        mgr = TagManager(mock_client, config)
        mgr.handle_event("owner", "repo")

        mock_client.delete_release.assert_called_once_with("owner", "repo", 42)
        mock_client.delete_tag.assert_called_once()
        mock_client.create_tag.assert_called_once()
        mock_client.create_release.assert_called_once()

    def test_skip_if_not_closed(self, mock_client: MagicMock, tmp_path: Path) -> None:
        event = tmp_path / "event.json"
        payload = {
            "action": "opened",
            "pull_request": {"merged": False, "base": {"ref": "releases/2026.3"}},
        }
        event.write_text(json.dumps(payload), encoding="utf-8")
        cfg = SdlcConfig(release_tag_name="v1", github_event_path=str(event))
        mgr = TagManager(mock_client, cfg)
        mgr.handle_event("o", "r")
        mock_client.create_tag.assert_not_called()

    def test_skip_if_not_merged(self, mock_client: MagicMock, tmp_path: Path) -> None:
        event = tmp_path / "event.json"
        payload = {
            "action": "closed",
            "pull_request": {"merged": False, "base": {"ref": "releases/2026.3"}},
        }
        event.write_text(json.dumps(payload), encoding="utf-8")
        cfg = SdlcConfig(release_tag_name="v1", github_event_path=str(event))
        mgr = TagManager(mock_client, cfg)
        mgr.handle_event("o", "r")
        mock_client.create_tag.assert_not_called()

    def test_skip_if_wrong_prefix(self, mock_client: MagicMock, tmp_path: Path) -> None:
        event = tmp_path / "event.json"
        payload = {
            "action": "closed",
            "pull_request": {"merged": True, "base": {"ref": "main"}},
        }
        event.write_text(json.dumps(payload), encoding="utf-8")
        cfg = SdlcConfig(release_tag_name="v1", github_event_path=str(event))
        mgr = TagManager(mock_client, cfg)
        mgr.handle_event("o", "r")
        mock_client.create_tag.assert_not_called()

    def test_exit_if_no_tag_name(self, mock_client: MagicMock, tmp_path: Path) -> None:
        event = tmp_path / "event.json"
        payload = {
            "action": "closed",
            "pull_request": {"merged": True, "base": {"ref": "releases/2026.3"}},
        }
        event.write_text(json.dumps(payload), encoding="utf-8")
        cfg = SdlcConfig(release_tag_name="", github_event_path=str(event))
        mgr = TagManager(mock_client, cfg)
        with pytest.raises(SystemExit):
            mgr.handle_event("o", "r")
