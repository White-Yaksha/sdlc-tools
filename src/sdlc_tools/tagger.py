"""Release tag management — idempotent create/update of lightweight tags."""

from __future__ import annotations

import json
import sys
from typing import Any

from sdlc_tools.client import GitHubClient
from sdlc_tools.config import SdlcConfig
from sdlc_tools.log import get_logger

log = get_logger("tagger")


class TagManager:
    """Manages release tag lifecycle via the GitHub API."""

    def __init__(self, client: GitHubClient, config: SdlcConfig) -> None:
        self.client = client
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_tag(self, owner: str, repo: str, branch: str, tag_name: str) -> None:
        """Create or re-create a tag and release pointing to the branch HEAD.

        Idempotent: deletes an existing release and tag before re-creating.
        """
        sha = self.client.get_ref_sha(owner, repo, f"heads/{branch}")
        log.info("Branch '%s' HEAD SHA: %s", branch, sha)

        # Delete existing release first (must happen before tag deletion).
        release_id = self.client.find_release_by_tag(owner, repo, tag_name)
        if release_id:
            log.info("Release for '%s' exists (ID: %d). Deleting.", tag_name, release_id)
            self.client.delete_release(owner, repo, release_id)

        # Delete existing tag.
        if self.client.tag_exists(owner, repo, tag_name):
            log.info("Tag '%s' exists. Deleting before re-creation.", tag_name)
            self.client.delete_tag(owner, repo, tag_name)

        # Create tag.
        result = self.client.create_tag(owner, repo, tag_name, sha)
        if result:
            log.info("Created tag '%s' → %s", tag_name, result["object"]["sha"])
        elif self.client.dry_run:
            log.info("[DRY-RUN] Would create tag '%s' → %s", tag_name, sha)

        # Create release.
        release = self.client.create_release(
            owner, repo, tag_name, name=tag_name,
        )
        if release:
            log.info(
                "Created release '%s' (ID: %d).",
                tag_name, release.get("id", 0),
            )
        elif self.client.dry_run:
            log.info("[DRY-RUN] Would create release '%s'.", tag_name)

    def handle_event(self, owner: str, repo: str) -> None:
        """Handle a GitHub Actions ``pull_request`` event.

        Reads the event payload from ``config.github_event_path`` and
        creates/updates a release tag if the PR was merged into a branch
        matching ``config.release_prefix``.
        """
        payload = self._read_event_payload()

        action = payload.get("action", "")
        pull_request = payload.get("pull_request", {})
        merged = pull_request.get("merged", False)
        base_ref = pull_request.get("base", {}).get("ref", "")

        log.info("PR event: action=%s, merged=%s, base=%s", action, merged, base_ref)

        if action != "closed":
            log.info("PR action is not 'closed'. Skipping.")
            return

        if not merged:
            log.info("PR was not merged. Skipping tag creation.")
            return

        if not base_ref.startswith(self.config.release_prefix):
            log.info(
                "Base branch '%s' does not match prefix '%s'. Skipping.",
                base_ref,
                self.config.release_prefix,
            )
            return

        tag_name = self.config.release_tag_name
        if not tag_name:
            log.error("release_tag_name is not set. Cannot create tag.")
            sys.exit(1)

        self.ensure_tag(owner, repo, base_ref, tag_name)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _read_event_payload(self) -> dict[str, Any]:
        """Read and parse the GitHub event JSON file."""
        path = self.config.github_event_path
        if not path:
            log.error("github_event_path is not set.")
            sys.exit(1)
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.error("Failed to read event payload from '%s': %s", path, exc)
            sys.exit(1)
