"""Tests for the release-agreement check.

Publishing correctly requires three places to agree — `manifest.json`, a `CHANGELOG.md`
section and a `vX.Y.Z` tag — and until now nothing verified it. The gap is not theoretical:
**v1.5.2 is tagged and published with no CHANGELOG section at all**, and nothing signalled
the hole as it was being dug. Forgejo #101.
"""
import pytest

from scripts.check_release_agreement import (
    KNOWN_MISSING_CHANGELOG,
    changelog_versions,
    check_agreement,
    check_published,
    manifest_version,
)

CHANGELOG = """# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- something not released yet

## [1.8.1] — 2026-08-26

### Security

- a fix

## [1.8.0] — 2026-08-26
"""


class TestReadingTheThreePlaces:
    def test_the_manifest_version_is_read(self, tmp_path):
        (tmp_path / "manifest.json").write_text('{"domain": "klereo", "version": "1.8.1"}')
        assert manifest_version(tmp_path / "manifest.json") == "1.8.1"

    def test_changelog_sections_are_read(self):
        assert changelog_versions(CHANGELOG) == {"1.8.1", "1.8.0"}

    def test_the_unreleased_section_is_not_a_version(self):
        """🔴 `[Unreleased]` is this repository's convention between releases.

        A fix PR writes it and the `chore(release):` commit renames it. Reading it as a
        version would make the check pass on a release that never stamped its number —
        the exact hole it exists to catch.
        """
        assert "Unreleased" not in changelog_versions(CHANGELOG)


class TestTheManifestMustHaveASection:
    def test_it_agrees_today(self):
        """Positive control: the state this repository is actually in."""
        assert check_agreement("1.8.1", CHANGELOG, tags=["v1.8.1", "v1.8.0"]) == []

    def test_a_bumped_manifest_with_no_section_fails(self):
        """🔴 The negative control the ticket demands, and the whole point of the job."""
        problems = check_agreement("1.9.0", CHANGELOG, tags=["v1.8.1"])
        assert len(problems) == 1
        assert "1.9.0" in problems[0]
        assert "CHANGELOG" in problems[0]


class TestEveryTagMustHaveASection:
    """The stronger half: a release that SHIPPED without a section, which is what happened.

    Checking only the current manifest version would not have caught v1.5.2 — by the time
    anyone looked, the manifest had moved on.
    """

    def test_a_tag_with_no_section_fails(self):
        problems = check_agreement("1.8.1", CHANGELOG, tags=["v1.8.1", "v1.7.9"])
        assert any("1.7.9" in p for p in problems)

    def test_the_documented_hole_does_not_fail(self):
        """⚠️ v1.5.2's content is LOST, and inventing a section is forbidden.

        The hole is the fact. Recording it in an allowlist keeps it visible forever and
        keeps the check able to fail on a NEW one, which a permanently red job could not.
        """
        assert "1.5.2" in KNOWN_MISSING_CHANGELOG
        assert check_agreement("1.8.1", CHANGELOG, tags=["v1.8.1", "v1.5.2"]) == []

    def test_a_tag_that_is_not_a_version_is_ignored(self):
        assert check_agreement("1.8.1", CHANGELOG, tags=["v1.8.1", "nightly"]) == []

    def test_no_tags_at_all_is_a_failure_not_a_pass(self):
        """🔴 An empty tag list means the checkout was shallow, never "all tags agree".

        This is the failure mode that makes a green job worthless: with no tags fetched
        there is nothing to disagree, so the check would report success having verified
        nothing. It must fail loudly instead.
        """
        problems = check_agreement("1.8.1", CHANGELOG, tags=[])
        assert len(problems) == 1
        assert "no tags" in problems[0].lower()


class TestThePublishedSide:
    """What `git tag` locally cannot see: whether the tag reached GitHub at all.

    HACS installs from the GitHub *release*, so a tag that never leaves Forgejo ships to
    nobody, in silence, while everything local says it worked.
    """

    def test_everything_present_is_agreement(self):
        assert check_published("1.8.1", local_sha="abc", github_sha="abc",
                               github_releases={"v1.8.1"}) == []

    def test_a_tag_missing_from_github_fails(self):
        """🔴 The costliest case: it ships to nobody and nothing local says so."""
        problems = check_published("1.8.1", local_sha="abc", github_sha=None,
                                   github_releases=set())
        assert any("GitHub" in p and "tag" in p for p in problems)

    def test_a_tag_pointing_at_a_different_commit_fails(self):
        problems = check_published("1.8.1", local_sha="abc", github_sha="def",
                                   github_releases={"v1.8.1"})
        assert any("abc" in p and "def" in p for p in problems)

    def test_a_tag_with_no_github_release_fails(self):
        """A tag is not a release. HACS reads the release, so a bare tag installs nothing."""
        problems = check_published("1.8.1", local_sha="abc", github_sha="abc",
                                   github_releases=set())
        assert any("release" in p.lower() for p in problems)

    def test_an_unverifiable_github_answer_fails_closed(self):
        """🔴 Rate-limited is NOT "verified".

        Every repository's CI shares one egress IP here, so an anonymous 429 from
        api.github.com is a real event. Reading "I could not ask" as "it is fine" is the
        exact shape of failure this check exists to remove.
        """
        problems = check_published("1.8.1", local_sha="abc", github_sha=None,
                                   github_releases=None)
        assert len(problems) == 2
        assert any("could not" in p.lower() for p in problems)

    def test_a_missing_local_tag_fails(self):
        problems = check_published("1.8.1", local_sha=None, github_sha=None,
                                   github_releases=set())
        assert any("local" in p.lower() for p in problems)


class TestTheRepositoryItselfAgrees:
    """Run the real check against the working tree — the positive control that matters.

    If this ever fails, the repository is in the state #101 was filed about, and the
    message says which of the three places disagrees.
    """

    def test_the_current_checkout_is_in_agreement(self, repo_root):
        import subprocess
        version = manifest_version(repo_root / "custom_components" / "klereo" / "manifest.json")
        changelog = (repo_root / "CHANGELOG.md").read_text()
        tags = subprocess.run(["git", "-C", str(repo_root), "tag", "--list", "v*"],
                              capture_output=True, text=True).stdout.split()
        problems = check_agreement(version, changelog, tags)
        assert problems == [], "\n".join(problems)

    def test_this_control_can_actually_fail(self, repo_root):
        """🔴 The instrument check: the test above must be able to go red.

        A test that reads the real repository passes for as long as the repository is
        healthy, which is indistinguishable from a test that cannot fail. Bumping the
        version it checks is the arm that discriminates.
        """
        changelog = (repo_root / "CHANGELOG.md").read_text()
        tags = ["v1.8.1"]
        assert check_agreement("99.0.0", changelog, tags) != []


@pytest.fixture
def repo_root():
    import pathlib
    return pathlib.Path(__file__).resolve().parent.parent
