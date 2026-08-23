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
