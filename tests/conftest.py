"""Shared test fixtures for Klereo integration tests."""
from unittest.mock import AsyncMock

import pytest

from custom_components.klereo.api import KlereoApi
from custom_components.klereo.const import DOMAIN

MOCK_SYSTEM_ID = "ABC123"
MOCK_USERNAME = "test@example.com"
MOCK_PASSWORD_HASH = "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"  # sha1("test")

MOCK_SYSTEMS_RESPONSE = {
    "response": [
        {
            "idSystem": MOCK_SYSTEM_ID,
            "poolNickname": "My Pool",
        }
    ]
}

MOCK_DETAILS_RESPONSE = {
    "response": [
        {
            "probes": [
                {"index": 0, "type": 5, "filteredValue": 28.5, "directValue": 28.4, "status": 0},
                {"index": 1, "type": 3, "filteredValue": 7.2, "directValue": 7.1, "status": 0},
            ],
            "outs": [
                {"index": 0, "status": 1, "mode": 0, "type": 0},
                {"index": 1, "status": 0, "mode": 1, "type": 0},
            ],
            "RegulModes": {
                "ConsigneEau": 28,
                "ModeFiltration": 1,
            },
        }
    ]
}


@pytest.fixture
def mock_api():
    """Create a mock KlereoApi."""
    api = AsyncMock(spec=KlereoApi)
    api.get_systems.return_value = MOCK_SYSTEMS_RESPONSE
    api.get_pool_details.return_value = MOCK_DETAILS_RESPONSE
    api.login.return_value = None
    api.set_output.return_value = {"response": "ok"}
    api.set_param.return_value = {"response": "ok"}
    return api
