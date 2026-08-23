"""Tests for Klereo model parsing — notably which container carries the setpoints.

`RegulModes` was a guess (see #94): the commit that introduced it says so in its own
comment, and the string appears nowhere in the upstream Jeedom plugin, which reads every
setpoint from `params`. These tests pin the resolution rule down so it stops being an
assumption.
"""
from custom_components.klereo.models import KlereoPoolDetails


class TestSettingsContainer:
    """Tests for how `params` and `RegulModes` resolve into one settings view."""

    def test_reads_setpoint_from_params_container(self):
        """Should find a setpoint that only exists under `params`."""
        details = KlereoPoolDetails.from_dict({"params": {"ConsigneEau": 28}})
        assert details.settings["ConsigneEau"] == 28

    def test_keeps_regul_modes_when_params_absent(self):
        """Should keep reading `RegulModes` — the new container only ever adds."""
        details = KlereoPoolDetails.from_dict({"RegulModes": {"ConsigneEau": 26}})
        assert details.settings["ConsigneEau"] == 26

    def test_regul_modes_wins_over_params_on_conflict(self):
        """Should prefer `RegulModes` where both carry a key.

        Neither container is measured, so the rule is chosen to be additive-only: a user
        already seeing a value keeps seeing that value, and `params` fills the gaps.
        """
        details = KlereoPoolDetails.from_dict(
            {"RegulModes": {"ConsigneEau": 26}, "params": {"ConsigneEau": 28}}
        )
        assert details.settings["ConsigneEau"] == 26

    def test_merges_disjoint_keys_from_both_containers(self):
        """Should expose keys from either container."""
        details = KlereoPoolDetails.from_dict(
            {"RegulModes": {"ModeFiltration": 1}, "params": {"ConsigneEau": 28}}
        )
        assert details.settings == {"ModeFiltration": 1, "ConsigneEau": 28}

    def test_params_stays_separate_from_regul_modes(self):
        """Should not fold `params` into `regul_modes`.

        `sensor.py` creates one entity per `regul_modes` key, so folding dozens of `params`
        keys in there would create dozens of entities in every install.
        """
        details = KlereoPoolDetails.from_dict({"params": {"ConsigneEau": 28}})
        assert details.regul_modes == {}
        assert details.params == {"ConsigneEau": 28}


class TestAccessLevel:
    """Tests for the `access` level that upstream gates every setpoint on."""

    def test_parses_access_level(self):
        """Should expose the payload's access level."""
        details = KlereoPoolDetails.from_dict({"access": 16})
        assert details.access == 16

    def test_access_absent_is_none(self):
        """Should report None rather than 0 when the payload carries no access level.

        0 would read as "no rights at all" and gate every setpoint off for a payload that
        simply does not carry the field.
        """
        details = KlereoPoolDetails.from_dict({})
        assert details.access is None
