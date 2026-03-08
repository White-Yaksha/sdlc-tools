"""Tests for the GitHub API client."""

from __future__ import annotations

import pytest
import responses

from sdlc_tools.client import GitHubClient

API = "https://api.github.com"


@pytest.fixture()
def client() -> GitHubClient:
    return GitHubClient(token="test-token")


@pytest.fixture()
def dry_client() -> GitHubClient:
    return GitHubClient(token="test-token", dry_run=True)


class TestAuth:
    def test_explicit_token(self) -> None:
        c = GitHubClient(token="abc123")
        assert c.token == "abc123"

    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(ValueError, match="No GitHub token"):
            GitHubClient()


class TestTagOperations:
    @responses.activate
    def test_tag_exists_true(self, client: GitHubClient) -> None:
        responses.add(responses.GET, f"{API}/repos/o/r/git/ref/tags/v1.0", status=200)
        assert client.tag_exists("o", "r", "v1.0") is True

    @responses.activate
    def test_tag_exists_false(self, client: GitHubClient) -> None:
        responses.add(responses.GET, f"{API}/repos/o/r/git/ref/tags/v1.0", status=404)
        assert client.tag_exists("o", "r", "v1.0") is False

    @responses.activate
    def test_create_tag(self, client: GitHubClient) -> None:
        responses.add(
            responses.POST,
            f"{API}/repos/o/r/git/refs",
            json={"object": {"sha": "abc123"}},
            status=201,
        )
        result = client.create_tag("o", "r", "v1.0", "abc123")
        assert result is not None
        assert result["object"]["sha"] == "abc123"

    @responses.activate
    def test_delete_tag(self, client: GitHubClient) -> None:
        responses.add(responses.DELETE, f"{API}/repos/o/r/git/refs/tags/v1.0", status=204)
        client.delete_tag("o", "r", "v1.0")  # should not raise

    @responses.activate
    def test_delete_tag_404(self, client: GitHubClient) -> None:
        responses.add(responses.DELETE, f"{API}/repos/o/r/git/refs/tags/v1.0", status=404)
        client.delete_tag("o", "r", "v1.0")  # 404 is handled gracefully


class TestDryRun:
    def test_create_tag_dry_run(self, dry_client: GitHubClient) -> None:
        result = dry_client.create_tag("o", "r", "v1.0", "abc")
        assert result is None  # no HTTP call made

    def test_delete_tag_dry_run(self, dry_client: GitHubClient) -> None:
        dry_client.delete_tag("o", "r", "v1.0")  # no HTTP call made


class TestPullRequests:
    @responses.activate
    def test_find_pr(self, client: GitHubClient) -> None:
        responses.add(
            responses.GET,
            f"{API}/repos/o/r/pulls",
            json=[{"number": 42}],
            status=200,
        )
        assert client.find_pr("o", "r", "feature/x") == 42

    @responses.activate
    def test_find_pr_none(self, client: GitHubClient) -> None:
        responses.add(
            responses.GET, f"{API}/repos/o/r/pulls", json=[], status=200,
        )
        assert client.find_pr("o", "r", "feature/x") is None


class TestComments:
    @responses.activate
    def test_find_comment_by_marker(self, client: GitHubClient) -> None:
        responses.add(
            responses.GET,
            f"{API}/repos/o/r/issues/1/comments",
            json=[{"id": 99, "body": "<!-- AI-SDLC-REPORT --> content"}],
            status=200,
        )
        assert client.find_comment_by_marker("o", "r", 1, "<!-- AI-SDLC-REPORT -->") == 99

    @responses.activate
    def test_find_comment_by_marker_not_found(self, client: GitHubClient) -> None:
        responses.add(
            responses.GET,
            f"{API}/repos/o/r/issues/1/comments",
            json=[],
            status=200,
        )
        assert client.find_comment_by_marker("o", "r", 1, "<!-- AI-SDLC-REPORT -->") is None


class TestCreatePR:
    @responses.activate
    def test_create_pr_success(self, client: GitHubClient) -> None:
        responses.add(
            responses.POST,
            f"{API}/repos/o/r/pulls",
            json={"number": 10, "html_url": "https://github.com/o/r/pull/10"},
            status=201,
        )
        pr_num = client.create_pr("o", "r", head="feat", base="main", title="My PR")
        assert pr_num == 10
        body = responses.calls[0].request.body
        assert b'"draft": true' in body

    @responses.activate
    def test_create_pr_non_draft(self, client: GitHubClient) -> None:
        responses.add(
            responses.POST,
            f"{API}/repos/o/r/pulls",
            json={"number": 11},
            status=201,
        )
        pr_num = client.create_pr(
            "o", "r", head="feat", base="main", title="PR", draft=False,
        )
        assert pr_num == 11
        body = responses.calls[0].request.body
        assert b'"draft": false' in body

    def test_create_pr_dry_run(self, dry_client: GitHubClient) -> None:
        result = dry_client.create_pr(
            "o", "r", head="feat", base="main", title="PR",
        )
        assert result is None

    @responses.activate
    def test_create_pr_failure(self, client: GitHubClient) -> None:
        responses.add(
            responses.POST,
            f"{API}/repos/o/r/pulls",
            json={
                "message": "Validation Failed",
                "errors": [{"message": "No commits between main and feat"}],
            },
            status=422,
        )
        import requests as req

        with pytest.raises(req.HTTPError, match="No commits between main and feat"):
            client.create_pr("o", "r", head="feat", base="main", title="PR")
