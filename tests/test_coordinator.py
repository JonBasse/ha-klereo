"""Tests for the Klereo coordinator."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from custom_components.klereo.api import KlereoApi, KlereoApiError
from custom_components.klereo.coordinator import KlereoCoordinator


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
        assert result["SYS1"]["info"]["idSystem"] == "SYS1"

    async def test_parses_list_format(self, coordinator, mock_api):
        """Should parse direct list format."""
        mock_api.get_systems.return_value = [
            {"idSystem": "SYS1"}
        ]
        mock_api.get_pool_details.return_value = {"response": [{}]}
        result = await coordinator._async_update_data()
        assert "SYS1" in result

    async def test_parses_list_systems_format(self, coordinator, mock_api):
        """Should parse {list_systems: [...]} format."""
        mock_api.get_systems.return_value = {
            "list_systems": [{"idSystem": "SYS1"}]
        }
        mock_api.get_pool_details.return_value = {"response": [{}]}
        result = await coordinator._async_update_data()
        assert "SYS1" in result

    async def test_builds_probe_index(self, coordinator, mock_api):
        """Should build _probe_index for O(1) lookup."""
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
        probe_idx = result["SYS1"]["details"]["_probe_index"]
        assert 0 in probe_idx
        assert 1 in probe_idx
        assert probe_idx[0]["filteredValue"] == 28.5

    async def test_builds_output_index(self, coordinator, mock_api):
        """Should build _output_index for O(1) lookup."""
        mock_api.get_systems.return_value = {
            "response": [{"idSystem": "SYS1"}]
        }
        mock_api.get_pool_details.return_value = {
            "response": [{"probes": [], "outs": [
                {"index": 0, "status": 1},
            ]}]
        }
        result = await coordinator._async_update_data()
        out_idx = result["SYS1"]["details"]["_output_index"]
        assert 0 in out_idx
        assert out_idx[0]["status"] == 1

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
