"""Shared GitHub API client with dry-run support."""

from __future__ import annotations

from typing import Any

import requests

from sdlc_tools.log import get_logger

log = get_logger("client")

_API_BASE = "https://api.github.com"
_TIMEOUT = 30


class GitHubClient:
    """Thin wrapper around the GitHub REST API.

    Supports dry-run mode: read operations execute normally, write
    operations (POST / PATCH / DELETE) are logged but skipped.
    """

    def __init__(self, token: str = "", *, dry_run: bool = False) -> None:
        self.token = token or self._resolve_token()
        self.dry_run = dry_run
        if not self.token:
            raise ValueError(
                "No GitHub token found. Set GITHUB_TOKEN env var"
                " or run 'sdlc-tools setup'."
            )

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_token() -> str:
        """Resolve token from ``GITHUB_TOKEN`` environment variable."""
        import os

        return os.environ.get("GITHUB_TOKEN", "")

    @staticmethod
    def validate_token(token: str) -> dict:
        """Validate a GitHub token by calling ``GET /user``.

        Returns:
            Dict with ``login``, ``name``, and ``scopes`` keys.

        Raises:
            ValueError: If the token is invalid or the API call fails.
        """
        resp = requests.get(
            f"{_API_BASE}/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code == 401:
            raise ValueError("Invalid GitHub token — authentication failed.")
        if resp.status_code == 403:
            raise ValueError("GitHub token lacks required permissions.")
        resp.raise_for_status()
        data = resp.json()
        scopes = resp.headers.get("X-OAuth-Scopes", "")
        return {
            "login": data.get("login", ""),
            "name": data.get("name", ""),
            "scopes": scopes,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

    # ------------------------------------------------------------------
    # Low-level HTTP
    # ------------------------------------------------------------------

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        resp = requests.get(url, headers=self._headers(), timeout=_TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, url: str, json: dict, **kwargs: Any) -> requests.Response | None:
        if self.dry_run:
            log.info("[DRY-RUN] POST %s — %s", url, json)
            return None
        resp = requests.post(
            url, headers=self._headers(), json=json, timeout=_TIMEOUT, **kwargs,
        )
        resp.raise_for_status()
        return resp

    def _patch(self, url: str, json: dict, **kwargs: Any) -> requests.Response | None:
        if self.dry_run:
            log.info("[DRY-RUN] PATCH %s — %s", url, json)
            return None
        resp = requests.patch(
            url, headers=self._headers(), json=json, timeout=_TIMEOUT, **kwargs,
        )
        resp.raise_for_status()
        return resp

    def _delete(self, url: str, **kwargs: Any) -> requests.Response | None:
        if self.dry_run:
            log.info("[DRY-RUN] DELETE %s", url)
            return None
        resp = requests.delete(url, headers=self._headers(), timeout=_TIMEOUT, **kwargs)
        if resp.status_code == 404:
            return resp
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Git refs / tags
    # ------------------------------------------------------------------

    def get_ref_sha(self, owner: str, repo: str, ref: str) -> str:
        """Fetch the SHA a ref (branch/tag) points to."""
        encoded = ref.replace("/", "%2F")
        url = f"{_API_BASE}/repos/{owner}/{repo}/git/ref/{encoded}"
        return self._get(url).json()["object"]["sha"]

    def tag_exists(self, owner: str, repo: str, tag_name: str) -> bool:
        """Return True if the tag ref exists."""
        encoded = tag_name.replace("/", "%2F")
        url = f"{_API_BASE}/repos/{owner}/{repo}/git/ref/tags/{encoded}"
        try:
            requests.get(url, headers=self._headers(), timeout=_TIMEOUT).raise_for_status()
            return True
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return False
            raise

    def create_tag(self, owner: str, repo: str, tag_name: str, sha: str) -> dict | None:
        """Create a lightweight tag ref."""
        url = f"{_API_BASE}/repos/{owner}/{repo}/git/refs"
        body = {"ref": f"refs/tags/{tag_name}", "sha": sha}
        resp = self._post(url, json=body)
        return resp.json() if resp else None

    def delete_tag(self, owner: str, repo: str, tag_name: str) -> None:
        """Delete a tag ref. Handles 404 gracefully."""
        encoded = tag_name.replace("/", "%2F")
        url = f"{_API_BASE}/repos/{owner}/{repo}/git/refs/tags/{encoded}"
        resp = self._delete(url)
        if resp and resp.status_code == 404:
            log.info("Tag '%s' was already deleted or does not exist.", tag_name)
        else:
            log.info("Deleted tag '%s'.", tag_name)

    # ------------------------------------------------------------------
    # Pull Requests
    # ------------------------------------------------------------------

    def find_pr(self, owner: str, repo: str, branch: str) -> int | None:
        """Find the open PR number for the given head branch."""
        url = f"{_API_BASE}/repos/{owner}/{repo}/pulls"
        params = {"head": f"{owner}:{branch}", "state": "open"}
        resp = requests.get(
            url, headers=self._headers(), params=params, timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            log.warning("Failed to fetch PRs: %s", resp.status_code)
            return None
        prs = resp.json()
        return prs[0]["number"] if prs else None

    def create_pr(
        self,
        owner: str,
        repo: str,
        *,
        head: str,
        base: str,
        title: str,
        body: str = "",
        draft: bool = True,
    ) -> int | None:
        """Create a pull request via REST API. Returns the PR number or None."""
        url = f"{_API_BASE}/repos/{owner}/{repo}/pulls"
        payload = {
            "head": head,
            "base": base,
            "title": title,
            "body": body,
            "draft": draft,
        }
        resp = self._post(url, json=payload)
        if resp is None:
            return None
        if resp.status_code in (201, 200):
            pr_number = resp.json().get("number")
            log.info("Created draft PR #%s.", pr_number)
            return pr_number
        log.error("Failed to create PR: %s %s", resp.status_code, resp.text[:200])
        return None

    # ------------------------------------------------------------------
    # PR Comments
    # ------------------------------------------------------------------

    def find_comment_by_marker(
        self, owner: str, repo: str, pr_number: int, marker: str,
    ) -> int | None:
        """Search PR comments for a marker string. Return comment ID or None."""
        url = f"{_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        page = 1
        while True:
            resp = requests.get(
                url,
                headers=self._headers(),
                params={"per_page": 100, "page": page},
                timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                return None
            comments = resp.json()
            if not comments:
                return None
            for comment in comments:
                if marker in comment.get("body", ""):
                    return comment["id"]
            page += 1

    def create_comment(
        self, owner: str, repo: str, pr_number: int, body: str,
    ) -> None:
        """Create a new PR comment."""
        url = f"{_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        resp = self._post(url, json={"body": body})
        if resp and resp.status_code != 201:
            log.error("Failed to create comment: %s", resp.status_code)
        else:
            log.info("Created comment on PR #%d.", pr_number)

    def update_comment(
        self, owner: str, repo: str, comment_id: int, body: str,
    ) -> None:
        """Update an existing PR comment."""
        url = f"{_API_BASE}/repos/{owner}/{repo}/issues/comments/{comment_id}"
        resp = self._patch(url, json={"body": body})
        if resp and resp.status_code != 200:
            log.error("Failed to update comment: %s", resp.status_code)
        else:
            log.info("Updated comment (ID: %d).", comment_id)
