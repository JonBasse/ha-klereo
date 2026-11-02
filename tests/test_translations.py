"""`translations/fr.json` must answer exactly the keys of `translations/en.json` (#216).

A key missing from a translation falls back in silence, and a key that only the translation
carries is dead text: neither raises, so the form simply stops being French, one field at a
time. The comparison is on the full key paths, values ignored.
"""
import json
from pathlib import Path

TRANSLATIONS = Path(__file__).resolve().parent.parent / "custom_components/klereo/translations"


def _key_paths(node, prefix=()):
    """Every leaf of a translation file, as its full path of keys."""
    if not isinstance(node, dict):
        return {prefix}
    return {path for key, value in node.items() for path in _key_paths(value, (*prefix, key))}


def _keys(name):
    return _key_paths(json.loads((TRANSLATIONS / name).read_text(encoding="utf-8")))


def test_french_covers_exactly_the_english_keys():
    english, french = _keys("en.json"), _keys("fr.json")

    assert english - french == set(), "missing from fr.json"
    assert french - english == set(), "absent from en.json"


def test_the_comparison_reads_nested_keys():
    """Positive control: a key buried in the tree is seen, so an empty diff means something."""
    assert ("config", "error", "no_pools") in _keys("en.json")
    assert ("options", "step", "init", "data", "power_Filtration") in _keys("en.json")
