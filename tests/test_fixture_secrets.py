"""🔴 No test fixture may carry a REAL value under a key the export redacts.

The failure this guards against has already happened. Commit `08cf765` — titled *"redact
what the repository PROMISES to redact in diagnostics"*, the fix for #122 — committed the
Bioul box `pin`, the customer reference `compta` and the account `username` **in clear**
into `test_diagnostics.py`, including into the fixture of the very class that asserts the
username is redacted. They sat in a public repository for eight days and were served by
`raw.githubusercontent.com`.

⚠️ **`gitleaks` runs on the full history in CI and stayed green throughout**, because it is
right: a Klereo pin and a short alphanumeric customer reference have no recognisable
shape. Searching for
a leak by the SHAPE of a secret returns a false negative for every credential whose form is
not distinctive. This file searches by **position** instead — any value sitting under a
redacted key — which is a property the payload cannot hide.

The check is deliberately *inverted*: rather than trying to recognise a real secret, it
requires every such value to be on an explicit list of synthetic ones. Pasting a real
payload into a fixture then fails until somebody adds that value here by hand, which is a
visible and deliberate act rather than an oversight.
"""
import ast
from pathlib import Path

import pytest

from custom_components.klereo.diagnostics import TO_REDACT

# Every value allowed to sit under a redacted key anywhere in `tests/`.
#
# Adding to this list is how you say "this one is invented". Keep them structurally
# realistic — same delimiters, same lengths — so the fixtures still exercise real shapes,
# and visibly fake, so a reader can tell at a glance which they are looking at.
SYNTHETIC = {
    # payload identifiers
    "0000-0000000-0000",          # pin — same dash structure as a real one
    "1111-2222222-3333",          # pin whose last field IS `proID`, for the #147 substring test
    "XX00000",                    # compta — same 2-letter + 5-digit shape
    "POD00012345",                # podSerial
    99999999,                     # idAddress
    "1 Example Street, Anytown",  # Address
    "owner@example.invalid",      # emailNotify — .invalid is reserved by RFC 2606
    "X",                          # a one-character pin, for a shape test
    # credentials
    "ExampleUser", "test@example.com",
    "secret", "secret_hash", "hash", "password",
    "my-token", "new-token", "alt-token", "tok", "tok123", "user",
    # prose used by the README-agreement tests, not payload values
    "session token", "account username",
    # the sentinel of the envelope tests
    "sentinel-klereo-account-name",
}

TESTS = Path(__file__).resolve().parent


def _values_under_redacted_keys():
    """Every (file, line, key, value) literal keyed by something in `TO_REDACT`."""
    found = []
    for path in sorted(TESTS.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in TO_REDACT
                    and isinstance(value, ast.Constant)
                ):
                    found.append((path.name, key.lineno, key.value, value.value))
    return found


class TestNoRealSecretInAFixture:
    def test_the_scan_finds_something_to_judge(self):
        """🔴 Positive control, and it carries the whole file.

        An AST walk that matched nothing — a renamed key, a moved fixture, a parse that
        silently returned no `Dict` nodes — would make every assertion below pass
        vacuously. "Nothing found" and "nothing wrong" are the same green otherwise.
        """
        found = _values_under_redacted_keys()

        assert len(found) >= 20, f"scan degenerate: only {len(found)} values found"
        assert {k for _, _, k, _ in found} >= {"pin", "compta", "username", "password"}

    @pytest.mark.parametrize(
        "location", _values_under_redacted_keys(), ids=lambda f: f"{f[0]}:{f[1]}:{f[2]}"
    )
    def test_every_value_under_a_redacted_key_is_synthetic(self, location):
        """One case per literal: a batch that loses one still passes on the others."""
        filename, lineno, key, value = location

        assert value in SYNTHETIC, (
            f"{filename}:{lineno} — {key!r} carries {value!r}, which is not on the "
            f"synthetic list. If it is invented, add it to SYNTHETIC in this file. "
            f"If it came from a real installation, it must not be committed: this "
            f"repository is public, and the export redacts this key precisely because "
            f"its value is sensitive."
        )

    def test_the_guard_rejects_a_value_that_is_not_listed(self):
        """🔴 Negative control: prove the assertion can actually fail.

        Without it, `SYNTHETIC` growing to cover everything by accident would be
        indistinguishable from a guard that works.
        """
        # Shaped exactly like the values this file exists to keep out, and invented
        # here — naming the real ones would re-commit them, which is the whole defect.
        assert "1234-5678901-2345" not in SYNTHETIC   # a pin's dash structure
        assert "ZZ99999" not in SYNTHETIC             # a compta's letter+digit shape
        assert len(SYNTHETIC) < 40, "the list has grown into an allow-everything"
