"""Tests for the Klereo coordinator."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.klereo.api import KlereoApi
from custom_components.klereo.coordinator import KlereoCoordinator
from custom_components.klereo.models import KlereoSystemData


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.loop = None
    return hass


@pytest.fixture
def mock_api():
    """Create a mock API."""
    api = AsyncMock(spec=KlereoApi)
    api.login.return_value = None
    return api


@pytest.fixture
def coordinator(mock_hass, mock_api):
    """Create a coordinator with mock dependencies."""
    coord = KlereoCoordinator.__new__(KlereoCoordinator)
    coord.api = mock_api
    coord.hass = mock_hass
    coord.logger = MagicMock()
    coord.name = "klereo"
    coord.update_interval = None
    coord._listeners = {}
    coord.data = {}
    coord.last_update_success = True
    return coord


class TestAsyncUpdateData:
    """Tests for _async_update_data."""

    async def test_parses_response_format(self, coordinator, mock_api):
        """Should parse {response: [...]} format."""
        mock_api.get_systems.return_value = {
            "response": [{"idSystem": "SYS1", "poolNickname": "Pool"}]
        }
        mock_api.get_pool_details.return_value = {
            "response": [{"probes": [{"index": 0, "type": 5}], "outs": []}]
        }
        result = await coordinator._async_update_data()
        assert "SYS1" in result
        assert isinstance(result["SYS1"], KlereoSystemData)
        assert result["SYS1"].info.id_system == "SYS1"

    async def test_parses_list_format(self, coordinator, mock_api):
        """Should parse direct list format."""
        mock_api.get_systems.return_value = [
            {"idSystem": "SYS1"}
        ]
        mock_api.get_pool_details.return_value = {"response": [{}]}
        result = await coordinator._async_update_data()
        assert "SYS1" in result
        assert isinstance(result["SYS1"], KlereoSystemData)

    async def test_parses_list_systems_format(self, coordinator, mock_api):
        """Should parse {list_systems: [...]} format."""
        mock_api.get_systems.return_value = {
            "list_systems": [{"idSystem": "SYS1"}]
        }
        mock_api.get_pool_details.return_value = {"response": [{}]}
        result = await coordinator._async_update_data()
        assert "SYS1" in result

    async def test_builds_probe_index(self, coordinator, mock_api):
        """Should build probe_index for O(1) lookup."""
        mock_api.get_systems.return_value = {
            "response": [{"idSystem": "SYS1"}]
        }
        mock_api.get_pool_details.return_value = {
            "response": [{"probes": [
                {"index": 0, "type": 5, "filteredValue": 28.5},
                {"index": 1, "type": 3, "filteredValue": 7.2},
            ], "outs": []}]
        }
        result = await coordinator._async_update_data()
        probe_idx = result["SYS1"].details.probe_index
        assert 0 in probe_idx
        assert 1 in probe_idx
        assert probe_idx[0].filtered_value == 28.5

    async def test_builds_output_index(self, coordinator, mock_api):
        """Should build output_index for O(1) lookup."""
        mock_api.get_systems.return_value = {
            "response": [{"idSystem": "SYS1"}]
        }
        mock_api.get_pool_details.return_value = {
            "response": [{"probes": [], "outs": [
                {"index": 0, "status": 1},
            ]}]
        }
        result = await coordinator._async_update_data()
        out_idx = result["SYS1"].details.output_index
        assert 0 in out_idx
        assert out_idx[0].status == 1

    async def test_skips_system_without_id(self, coordinator, mock_api):
        """Should skip systems without idSystem."""
        mock_api.get_systems.return_value = {
            "response": [{"poolNickname": "No ID"}]
        }
        result = await coordinator._async_update_data()
        assert len(result) == 0

    async def test_partial_failure_continues(self, coordinator, mock_api):
        """Should continue when one system's details fail."""
        mock_api.get_systems.return_value = {
            "response": [
                {"idSystem": "SYS1"},
                {"idSystem": "SYS2"},
            ]
        }
        mock_api.get_pool_details.side_effect = [
            Exception("API error"),
            {"response": [{"probes": [], "outs": []}]},
        ]
        result = await coordinator._async_update_data()
        assert "SYS1" in result  # still present, just without merged details
        assert "SYS2" in result


class TestCommandResultIsChecked:
    """Tests that a rejected Klereo command stops looking like a successful one.

    `SetOut` / `SetParam` queue and return immediately, so an HTTP 200 says only that the
    command was *accepted for execution*. Status 13 (insufficient rights) is the costly
    one: upstream bars outputs 2, 3, 8 and 15 below access 20, so a non-professional
    account commanding its pH corrector gets a silent success today (#95).
    """

    @pytest.fixture(autouse=True)
    def _no_refresh(self, coordinator):
        coordinator.async_request_refresh = AsyncMock()

    async def test_raises_on_insufficient_rights(self, coordinator, mock_api):
        """Should raise, naming the status, when the command is refused."""
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {"status": "ok", "response": 13}

        with pytest.raises(HomeAssistantError, match="insufficient rights"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

        mock_api.command_status.assert_awaited_once_with(77)

    async def test_raises_on_bad_parameters(self, coordinator, mock_api):
        """Should raise on status 11 too — the check is not specific to one code."""
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {"status": "ok", "response": 11}

        with pytest.raises(HomeAssistantError, match="bad parameters"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

    async def test_does_not_raise_on_success(self, coordinator, mock_api):
        """Should stay silent on status 9 and still refresh.

        This is the positive control: without it, an exception reaching the caller would
        not prove the right field is read — only that something raised.
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {"status": "ok", "response": 9}

        await coordinator.async_set_output("SYS1", 2, 0, 1)

        coordinator.async_request_refresh.assert_awaited_once()

    async def test_does_not_raise_while_still_in_flight(self, coordinator, mock_api):
        """Should not raise on 0 (pending) or 1 (running) — those are not failures."""
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        for in_flight in (0, 1):
            mock_api.command_status.return_value = {"status": "ok", "response": in_flight}
            await coordinator.async_set_output("SYS1", 2, 0, 1)

    async def test_does_not_raise_when_no_command_id_is_returned(self, coordinator, mock_api):
        """Should behave exactly as before when no cmdID can be found.

        The response shape is not measured — an expired JWT answers
        `{"status": "error", "detail": ...}` with no `response` key at all. Raising on a
        shape we guessed would break every write on a guess, which is the defect #94
        records. Never worse than today is the rule here.
        """
        mock_api.set_output.return_value = {"status": "error", "detail": "expired"}

        await coordinator.async_set_output("SYS1", 2, 0, 1)

        mock_api.command_status.assert_not_awaited()
        coordinator.async_request_refresh.assert_awaited_once()

    async def test_accepts_a_bare_command_id(self, coordinator, mock_api):
        """Should read a cmdID returned as a bare scalar, not only wrapped in a dict."""
        mock_api.set_output.return_value = {"status": "ok", "response": 77}
        mock_api.command_status.return_value = {"status": "ok", "response": 9}

        await coordinator.async_set_output("SYS1", 2, 0, 1)

        mock_api.command_status.assert_awaited_once_with(77)

    async def test_set_param_is_checked_too(self, coordinator, mock_api):
        """Should check SetParam the same way — both writes queue."""
        mock_api.set_param.return_value = {"status": "ok", "response": {"cmdID": 88}}
        mock_api.command_status.return_value = {"status": "ok", "response": 15}

        with pytest.raises(HomeAssistantError, match="execution timeout"):
            await coordinator.async_set_param("SYS1", "ConsigneEau", 28)

    async def test_does_not_refresh_after_a_rejected_command(self, coordinator, mock_api):
        """Should not refresh when the command failed — upstream refreshes only on 9."""
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {"status": "ok", "response": 10}

        with pytest.raises(HomeAssistantError):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

        coordinator.async_request_refresh.assert_not_awaited()

    async def test_unknown_status_still_raises(self, coordinator, mock_api):
        """Should raise on a status code absent from the label table, naming the number."""
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {"status": "ok", "response": 99}

        with pytest.raises(HomeAssistantError, match="99"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

class TestDocumentedListShape:
    """Tests the response shape Klereo's own API documentation describes (#106).

    `#95` was written without documentation and said so: `_command_id`'s comment declared
    *"The response shape is NOT measured"*. The documentation arrived on 2026-08-24
    (`docs/klereo-api.md`) and describes `response` as a **JSON ARRAY** whose elements
    carry `cmdID`, `status`, `startTime`, `updateTime` and `detail` — never a bare integer.

    The tests in `TestCommandResultIsChecked` above all mock the integer form, so they were
    green while agreeing with the code's own assumption rather than with the API. They are
    kept: which of the two shapes is live is still unmeasured, and reading both is the only
    remedy that cannot regress either way.
    """

    @pytest.fixture(autouse=True)
    def _no_refresh(self, coordinator):
        coordinator.async_request_refresh = AsyncMock()

    async def test_reads_the_command_id_from_a_list_response(self, coordinator, mock_api):
        """Should find cmdID inside `response[0]`, the shape SetOut is documented to return."""
        mock_api.set_output.return_value = {
            "status": "ok",
            "response": [{"cmdID": 77, "poolID": 1}],
        }
        mock_api.command_status.return_value = {"status": "ok", "response": 9}

        await coordinator.async_set_output("SYS1", 2, 0, 1)

        mock_api.command_status.assert_awaited_once_with(77)

    async def test_raises_on_insufficient_rights_in_a_list_response(self, coordinator, mock_api):
        """Should read `status` from inside the element, not from `response` itself."""
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {
            "status": "ok",
            "response": [{"cmdID": 77, "status": 13, "detail": ""}],
        }

        with pytest.raises(HomeAssistantError, match="insufficient rights"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

    async def test_does_not_raise_on_success_in_a_list_response(self, coordinator, mock_api, caplog):
        """Positive control: status 9 inside the element is READ, not merely tolerated.

        ⚠️ Asserting only "did not raise, and refreshed" does NOT discriminate here: an
        unparsed response also fails to raise and also refreshes. The two outcomes are
        byte-identical to the caller. The discriminator is the absence of the "unreadable
        command status" warning — that is what separates "understood as success" from
        "not understood at all".
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {
            "status": "ok",
            "response": [{"cmdID": 77, "status": 9, "startTime": 1, "updateTime": 2}],
        }

        await coordinator.async_set_output("SYS1", 2, 0, 1)

        assert "unreadable command status" not in caplog.text
        coordinator.async_request_refresh.assert_awaited_once()

    async def test_picks_the_element_matching_our_command_id(self, coordinator, mock_api):
        """Should match on cmdID rather than blindly taking the first element.

        The documentation says each element represents a command, so a response carrying
        more than one is well-formed. Taking `[0]` would read another command's verdict —
        a plausible, wrong answer, which is the failure this whole issue is about.
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {
            "status": "ok",
            "response": [
                {"cmdID": 41, "status": 9},
                {"cmdID": 77, "status": 13},
            ],
        }

        with pytest.raises(HomeAssistantError, match="insufficient rights"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

    async def test_reports_klereos_detail_string_when_present(self, coordinator, mock_api):
        """Should surface `detail`, the free-text field Klereo documents alongside status."""
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {
            "status": "ok",
            "response": [{"cmdID": 77, "status": 10, "detail": "pump unreachable"}],
        }

        with pytest.raises(HomeAssistantError, match="pump unreachable"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

    async def test_does_not_raise_while_in_flight_in_a_list_response(self, coordinator, mock_api, caplog):
        """Should treat 0 and 1 inside the element as not-yet-a-verdict, as for the integer form.

        Same discrimination problem as the success case: silence alone proves nothing, so
        the assertion is that the status was parsed rather than skipped.
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        for in_flight in (0, 1):
            mock_api.command_status.return_value = {
                "status": "ok",
                "response": [{"cmdID": 77, "status": in_flight}],
            }
            await coordinator.async_set_output("SYS1", 2, 0, 1)

        assert "unreadable command status" not in caplog.text

    async def test_an_empty_list_is_not_a_verdict(self, coordinator, mock_api):
        """Should not raise on `response: []` — absence of a verdict is not a rejection.

        Absurdity control: an empty list is indistinguishable from "not answered yet", and
        turning it into a failure would invent rejections nobody reported.
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {"status": "ok", "response": []}

        await coordinator.async_set_output("SYS1", 2, 0, 1)


class TestMeasuredObjectShape:
    """Tests for the shape `WaitCommand` was MEASURED to return: a bare object.

    #106 read two shapes — the bare integer #95 shipped, and the JSON array
    `docs/klereo-api.md` documents — on the stated ground that reading both could not
    regress whichever turned out to be real. Neither is. The first real payload anyone
    has measured (GitHub #55, @StephanH27, 2026-08-26) carries `response` as a single
    object, four times out of four.

    ⚠️ Every test above this class passes on the broken code, because each one builds its
    own fixture out of the two *assumed* shapes. A test whose fixture is the assumption it
    should be controlling discriminates nothing — which is why this class quotes the
    reported payload verbatim rather than paraphrasing it.
    """

    @pytest.fixture(autouse=True)
    def _no_refresh(self, coordinator):
        coordinator.async_request_refresh = AsyncMock()

    async def test_reads_the_status_from_the_reported_payload_verbatim(
        self, coordinator, mock_api, caplog
    ):
        """Should understand the exact response @StephanH27 reported, status 9 included.

        Positive control, and the whole point of the issue: silence alone does not
        discriminate here, since an unparsed response is also silent and also refreshes.
        The absence of the "unreadable command status" warning is what separates
        "understood as success" from "not understood at all".
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 4351826}}
        mock_api.command_status.return_value = {
            "status": "ok",
            "response": {
                "cmdID": 4351826,
                "status": 9,
                "startTime": 1787652057,
                "updateTime": 1787652059,
                "detail": "Ok",
            },
        }

        await coordinator.async_set_output("SYS1", 4, 3, 2)

        assert "unreadable command status" not in caplog.text
        coordinator.async_request_refresh.assert_awaited_once()

    async def test_raises_on_insufficient_rights_in_an_object_response(self, coordinator, mock_api):
        """Should raise on status 13 in the object form.

        This is the defect's actual cost: with the object unparsed, a rejection for
        insufficient rights reads exactly like a success, on every install, since #95.
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {
            "status": "ok",
            "response": {"cmdID": 77, "status": 13, "detail": ""},
        }

        with pytest.raises(HomeAssistantError, match="insufficient rights"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

    async def test_reports_klereos_detail_string_from_an_object_response(self, coordinator, mock_api):
        """Should surface `detail` from the object form, as it does from the list form."""
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {
            "status": "ok",
            "response": {"cmdID": 77, "status": 10, "detail": "pump unreachable"},
        }

        with pytest.raises(HomeAssistantError, match="pump unreachable"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

    async def test_does_not_raise_while_in_flight_in_an_object_response(
        self, coordinator, mock_api, caplog
    ):
        """Should treat 0 and 1 in the object form as not-yet-a-verdict.

        The measured payload reaches status 9 in 1 to 2 seconds (four samples, GitHub
        #55), so a caller polling early genuinely sees these — they are not hypothetical.
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        for in_flight in (0, 1):
            caplog.clear()
            mock_api.command_status.return_value = {
                "status": "ok",
                "response": {"cmdID": 77, "status": in_flight},
            }
            await coordinator.async_set_output("SYS1", 2, 0, 1)
            assert "unreadable command status" not in caplog.text

    async def test_does_not_read_another_commands_verdict(self, coordinator, mock_api, caplog):
        """Should refuse an object whose `cmdID` is not ours rather than report its status.

        Negative control. The list branch matches on `cmdID` for exactly this reason; an
        object naming a different command is the same hazard, and answering "rejected"
        from another command's verdict is worse than answering nothing.
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {
            "status": "ok",
            "response": {"cmdID": 41, "status": 13},
        }

        await coordinator.async_set_output("SYS1", 2, 0, 1)

        assert "unreadable command status" in caplog.text

    async def test_reads_an_object_that_carries_no_command_id(self, coordinator, mock_api, caplog):
        """Should still read `status` when the object names no command at all.

        Absurdity control on the matching rule above: `cmdID` is used to REJECT a verdict
        proven to belong elsewhere, not to require a field whose presence is unmeasured on
        every install. Only a *mismatching* id disqualifies an object.
        """
        mock_api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
        mock_api.command_status.return_value = {"status": "ok", "response": {"status": 13}}

        with pytest.raises(HomeAssistantError, match="insufficient rights"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)


class TestPayloadShapeLogging:
    """Tests for the debug trace that records which containers the API actually sends.

    `RegulModes` vs `params` (#94) could not be settled from the code because nothing ever
    recorded what a real payload looks like. This trace is the instrument that stops the
    next reporter's container from being a guess.
    """

    async def test_logs_detail_payload_top_level_keys(self, coordinator, mock_api, caplog):
        """Should log the top-level keys of each system's detail payload at debug level."""
        mock_api.get_systems.return_value = {"response": [{"idSystem": "SYS1"}]}
        mock_api.get_pool_details.return_value = {
            "response": [{"probes": [], "outs": [], "params": {"ConsigneEau": 28}, "access": 10}]
        }
        with caplog.at_level("DEBUG", logger="custom_components.klereo.coordinator"):
            await coordinator._async_update_data()

        assert "params" in caplog.text
        assert "access" in caplog.text

    async def test_logs_the_keys_inside_each_setting_container(self, coordinator, mock_api, caplog):
        """Should log what each container CARRIES, not only that it is present.

        The top-level line above answered less than it looked like it did: its first real
        reading (GitHub #57, 2026-08-26) showed all three containers present at once,
        which retired the question it was built for and left the blocking one — where
        `ConsigneEau` and the consumption counters live — untouched. An instrument one
        level too shallow reads as an answer.
        """
        mock_api.get_systems.return_value = {"response": [{"idSystem": "SYS1"}]}
        mock_api.get_pool_details.return_value = {
            "response": [
                {
                    "RegulModes": {"HeaterMode": 0},
                    "params": {"ConsigneEau": 28, "EauMin": 15},
                    "ExtraParams": {"PHMinus_TodayTime": 42},
                }
            ]
        }
        with caplog.at_level("DEBUG", logger="custom_components.klereo.coordinator"):
            await coordinator._async_update_data()

        assert "ConsigneEau" in caplog.text
        assert "EauMin" in caplog.text
        assert "PHMinus_TodayTime" in caplog.text
        assert "HeaterMode" in caplog.text

    async def test_does_not_log_a_container_the_payload_omits(self, coordinator, mock_api, caplog):
        """Negative control: an absent container must not be reported as an empty one.

        "Not sent" and "sent empty" are different facts about the API, and this log line
        exists precisely to tell them apart. Rendering both as `[]` would make the
        instrument assert something the payload never said.
        """
        mock_api.get_systems.return_value = {"response": [{"idSystem": "SYS1"}]}
        mock_api.get_pool_details.return_value = {"response": [{"params": {"EauMin": 15}}]}
        with caplog.at_level("DEBUG", logger="custom_components.klereo.coordinator"):
            await coordinator._async_update_data()

        assert "params carries keys" in caplog.text
        assert "ExtraParams carries keys" not in caplog.text
        assert "RegulModes carries keys" not in caplog.text
