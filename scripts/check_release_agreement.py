#!/usr/bin/env python3
"""Verify that a release's three places agree.

Publishing this integration correctly requires three things to say the same number:

1. `version` in `custom_components/klereo/manifest.json`
2. a `## [X.Y.Z]` section in `CHANGELOG.md`
3. a `vX.Y.Z` tag — which must reach **GitHub**, since HACS installs from the GitHub
   release and a tag that never leaves Forgejo ships to nobody.

Nothing verified this, and the gap is not theoretical: **v1.5.2 is tagged and published
with no CHANGELOG section**, and nothing signalled the hole as it was being dug (#101).

Two modes, and the split is measured rather than chosen:

- default — checks 1 and 2, plus every tag against the changelog. No network, so it runs
  as a CI job on every push.
- `--published X.Y.Z` — additionally asks GitHub whether the tag and the release exist.
  This is NOT a CI job. 🔴 The ticket proposed triggering it on `release: [published]`;
  measured 2026-08-26, **this repository has zero Forgejo releases** — only tags — so that
  trigger would never fire, and a check that cannot fire is worse than none. A `push: tags`
  trigger races the mirror and the human, who creates the GitHub release afterwards. So
  this half is a step of the ritual, run by hand, and `CLAUDE.md` points at it.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_SECTION = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)
_TAG = re.compile(r"^v(\d+\.\d+\.\d+)$")

# ⚠️ v1.5.2 shipped with no CHANGELOG section and its content is LOST. Writing a plausible
# section would turn a visible hole into a false certainty — the hole is the fact. It is
# recorded here instead: that keeps it visible forever AND keeps this check able to fail on
# a NEW one, which a permanently red job could not.
KNOWN_MISSING_CHANGELOG = frozenset({"1.5.2"})


def manifest_version(path: Path) -> str:
    """Return the version `manifest.json` advertises to HACS."""
    return json.loads(path.read_text())["version"]


def changelog_versions(text: str) -> set[str]:
    """Return every version that has a `## [X.Y.Z]` section.

    `## [Unreleased]` is deliberately not one. It is this repository's convention between
    releases — a fix PR writes it and the `chore(release):` commit renames it — and reading
    it as a version would make this check pass on a release that never stamped its number.
    """
    return set(_SECTION.findall(text))


def check_agreement(version: str, changelog: str, tags: list[str]) -> list[str]:
    """Return every disagreement between the manifest, the changelog and the tags."""
    documented = changelog_versions(changelog)
    problems = []

    if not tags:
        # 🔴 Never a pass. With no tags fetched there is nothing to disagree, so the check
        # would report success having verified nothing — a green job worth less than none.
        return ["no tags found: was the checkout shallow? (needs fetch-depth: 0)"]

    if version not in documented:
        problems.append(
            f"manifest.json is at {version}, but CHANGELOG.md has no `## [{version}]` section"
        )

    for tag in tags:
        match = _TAG.match(tag)
        if match is None:
            continue
        released = match.group(1)
        if released in KNOWN_MISSING_CHANGELOG or released in documented:
            continue
        problems.append(
            f"tag {tag} is published but CHANGELOG.md has no `## [{released}]` section"
        )
    return problems


def check_published(
    version: str,
    local_sha: str | None,
    github_sha: str | None,
    github_releases: set[str] | None,
) -> list[str]:
    """Return every reason this version is not actually published.

    `github_releases=None` means the question could not be asked — a rate limit, a network
    failure. It fails CLOSED: every repository's CI shares one egress IP here, so an
    anonymous 429 from api.github.com is a real event, and reading "I could not ask" as
    "it is fine" is the exact shape of failure this check exists to remove.
    """
    tag = f"v{version}"
    problems = []

    if local_sha is None:
        problems.append(f"no local tag {tag}")
    if github_sha is None:
        problems.append(f"tag {tag} is not on GitHub, or GitHub could not be asked")
    elif local_sha is not None and github_sha != local_sha:
        problems.append(f"tag {tag} points at {local_sha} locally and {github_sha} on GitHub")

    if github_releases is None:
        problems.append("could not ask GitHub for releases: treating that as NOT verified")
    elif tag not in github_releases:
        problems.append(
            f"no GitHub release for {tag} — HACS installs from the release, not the tag"
        )
    return problems


def _run(*args: str) -> str | None:
    """Return a command's stdout, or None when it fails — never an empty string."""
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def main(argv: list[str] | None = None) -> int:
    """Run the check and report every disagreement, not just the first."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published", metavar="X.Y.Z",
                        help="also ask GitHub whether this version's tag and release exist")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)

    version = manifest_version(args.root / "custom_components" / "klereo" / "manifest.json")
    changelog = (args.root / "CHANGELOG.md").read_text()
    tags = (_run("git", "-C", str(args.root), "tag", "--list", "v*") or "").split()

    problems = check_agreement(version, changelog, tags)

    if args.published:
        local = _run("git", "-C", str(args.root), "rev-list", "-n", "1", f"v{args.published}")
        # 🔴 `commits/<ref>`, NOT `git/ref/tags/<tag>`. Every tag here is ANNOTATED, so that
        # route returns the TAG OBJECT's sha while `git rev-list` returns the COMMIT's —
        # two different things that compare unequal on a release that is perfectly fine.
        # Measured on v1.8.1, which is correctly published and which the first version of
        # this check reported as broken. The unit tests could not see it: both sides were
        # fixtures, and a fixture agrees with whatever the code asks it for.
        remote = _run("gh", "api", f"repos/JonBasse/ha-klereo/commits/v{args.published}",
                      "--jq", ".sha")
        listing = _run("gh", "release", "list", "--repo", "JonBasse/ha-klereo",
                       "--limit", "50", "--json", "tagName", "--jq", ".[].tagName")
        releases = set(listing.split()) if listing is not None else None
        problems += check_published(args.published, local, remote, releases)

    if problems:
        print(f"🔴 release agreement broken ({len(problems)}):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    scope = f"{version} + {len(tags)} tags"
    print(f"✅ release agreement holds ({scope})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
