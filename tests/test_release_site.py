"""tools/release_site.py: the checks before a release of the web page; nothing is made or deployed."""
import pytest

import release_site


@pytest.mark.parametrize("tag, ok", [("v1.0.0", True), ("v1.2.3-rc.1", True), ("1.0.0", False), ("v1.0", False), ("latest", False)])
def test_tag_is_a_version(tag, ok):
    if ok:
        release_site.check_tag(tag)
    else:
        with pytest.raises(SystemExit, match="not a version tag"):
            release_site.check_tag(tag)


def test_a_checkout_with_changes_is_refused(monkeypatch):
    monkeypatch.setattr(release_site, "git", lambda *a: " M web/index.html" if a[0] == "status" else "")
    with pytest.raises(SystemExit, match="commit or put away"):
        release_site.check_checkout()


def test_a_commit_that_is_not_pushed_is_refused(monkeypatch):
    monkeypatch.setattr(release_site, "git", lambda *a: "" if a[0] in ("status", "branch") else "abc123")
    with pytest.raises(SystemExit, match="push this commit"):
        release_site.check_checkout()


def test_a_clean_pushed_checkout_passes(monkeypatch):
    monkeypatch.setattr(release_site, "git", lambda *a: "" if a[0] == "status" else "origin/main" if a[0] == "branch" else "abc123")
    release_site.check_checkout()


def test_the_release_runs_the_web_tests_and_prints_the_deploy_command_only():
    assert all(t.startswith("test_") for t in release_site.TESTS) and "test_web_build.py" in release_site.TESTS
    assert release_site.DEPLOY == "npx wrangler deploy -c deploy/stompmod/wrangler.jsonc"
