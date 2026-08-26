"""Tests for Klereo model parsing — notably which container carries the setpoints.

`RegulModes` was a guess (see #94): the commit that introduced it says so in its own
comment, and the string appears nowhere in the upstream Jeedom plugin, which reads every
setpoint from `params`. These tests pin the resolution rule down so it stops being an
assumption.
"""
from custom_components.klereo.const import SETTING_CONTAINERS
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


class TestExtraParamsContainer:
    """Tests for the THIRD container, reported from a real diagnostic JSON.

    On 2026-06-17 an external reporter read their own diagnostic export and named the
    counters as living "in the `params` and `ExtraParams` arrays" (GitHub #54). That is
    the first measurement of a real payload this repo has: it confirms `params` exists,
    and it names a container nobody had considered.
    """

    def test_reads_setpoint_from_extra_params(self):
        """Should find a setpoint that only exists under `ExtraParams`."""
        details = KlereoPoolDetails.from_dict({"ExtraParams": {"ConsigneEau": 28}})
        assert details.settings["ConsigneEau"] == 28

    def test_extra_params_stays_separate(self):
        """Should keep `ExtraParams` out of `regul_modes`, like `params`."""
        details = KlereoPoolDetails.from_dict({"ExtraParams": {"ConsigneEau": 28}})
        assert details.regul_modes == {}
        assert details.extra_params == {"ConsigneEau": 28}

    def test_precedence_is_regul_modes_then_params_then_extra(self):
        """Should resolve conflicts additively, most-established container first."""
        details = KlereoPoolDetails.from_dict(
            {
                "RegulModes": {"a": "regul"},
                "params": {"a": "params", "b": "params"},
                "ExtraParams": {"a": "extra", "b": "extra", "c": "extra"},
            }
        )
        assert details.settings == {"a": "regul", "b": "params", "c": "extra"}


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


class TestAlertParsing:
    """Tests for parsing the `alerts` array into typed entries."""

    def test_parses_the_measured_entry(self):
        """Should carry every field of the one payload anyone has measured (GitHub #57)."""
        details = KlereoPoolDetails.from_dict(
            {
                "alerts": [
                    {
                        "index": 0,
                        "code": 29,
                        "param": 0,
                        "updateTime": "2026-08-26 11:24:58",
                        "level": 2,
                    }
                ],
                "alertCount": 0,
            }
        )

        assert len(details.alerts) == 1
        alert = details.alerts[0]
        assert (alert.code, alert.param, alert.index, alert.level) == (29, 0, 0, 2)
        assert alert.updated == "2026-08-26 11:24:58"
        assert details.reported_alert_count == 0

    def test_keeps_the_timestamp_as_the_string_it_is(self):
        """Should NOT parse `updateTime` into a datetime.

        It is a string here and an integer epoch everywhere else in this API, and no
        timezone is stated anywhere. Parsing it would require inventing one, which
        silently shifts every timestamp by hours.
        """
        details = KlereoPoolDetails.from_dict(
            {"alerts": [{"code": 29, "updateTime": "2026-08-26 11:24:58"}]}
        )

        assert details.alerts[0].updated == "2026-08-26 11:24:58"

    def test_an_absent_key_parses_to_no_alerts(self):
        """Should read a healthy payload — the key is not sent when nothing is wrong."""
        details = KlereoPoolDetails.from_dict({"probes": [], "outs": []})

        assert details.alerts == []
        assert details.reported_alert_count is None

    def test_skips_an_entry_carrying_no_code(self):
        """Should drop a malformed entry rather than raise, as probes and outs do.

        Same rule as `probes`/`outs`, which skip entries with no `index`: one unusable
        element must not cost the whole refresh. `code` is the only field every branch of
        the rendering needs.
        """
        details = KlereoPoolDetails.from_dict(
            {"alerts": [{"param": 3}, {"code": 14, "param": 1}, "not-a-dict"]}
        )

        assert [a.code for a in details.alerts] == [14]
class TestContainerListMatchesPrecedence:
    """Pins `SETTING_CONTAINERS` to the merge order `settings` actually implements.

    🔴 The constant DESCRIBES a precedence that `settings` hard-codes as a dict merge, in
    another file. Nothing but this test stops the two from disagreeing — and a comment
    asserting the opposite of the code beside it is a defect this project has already
    shipped once, in a single edit, with no check able to see it.
    """

    def test_the_last_container_wins_as_the_constant_says(self):
        """Should resolve a key present in all three to the LAST entry of the tuple."""
        details = KlereoPoolDetails(
            extra_params={"Consigne": "extra"},
            params={"Consigne": "params"},
            regul_modes={"Consigne": "regul"},
        )
        by_name = {
            "ExtraParams": "extra",
            "params": "params",
            "RegulModes": "regul",
        }

        assert details.settings["Consigne"] == by_name[SETTING_CONTAINERS[-1]]

    def test_every_named_container_is_actually_read(self):
        """Absurdity control: a container named in the constant but never merged.

        Naming a fourth container would make the debug log promise a key set that
        `settings` then ignores — the instrument describing a code path that does not run.
        """
        for position, name in enumerate(SETTING_CONTAINERS):
            containers = {"extra_params": {}, "params": {}, "regul_modes": {}}
            field = {"ExtraParams": "extra_params", "params": "params", "RegulModes": "regul_modes"}
            assert name in field, f"{name} is named but has no field on KlereoPoolDetails"
            containers[field[name]] = {f"Key{position}": position}
            details = KlereoPoolDetails(**containers)
            assert details.settings == {f"Key{position}": position}
