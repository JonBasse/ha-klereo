"""Tests for confirming a queued write without blocking on it.

`SetOut` / `SetParam` only queue; the verdict is read back separately. Klereo documents TWO
routes for that read — `WaitCommand`, which **waits for the end of execution**, and
`CommandStatus`, which **returns immediately** (`docs/klereo-api.md`). We took the blocking
one. @nopbop measured the real latency at **1 to 2 seconds** from `SetOut` to `status: 9`
(GitHub #58, 2026-08-28), which leaves the blocking route nothing to buy.

🔴 The trap this file exists to hold shut: swapping the route WITHOUT adding a poll turns
every write into "unconfirmed". A single non-blocking call lands on *in flight* almost every
time, `_async_confirm_command` returns False, and nothing is logged above debug — silently,
and looking exactly like a success to the user. Forgejo #140.
"""
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.klereo.api import CMD_POLL_ATTEMPTS, KlereoApi
from custom_components.klereo.coordinator import KlereoCoordinator


@pytest.fixture
def mock_api():
    api = AsyncMock(spec=KlereoApi)
    api.set_output.return_value = {"status": "ok", "response": {"cmdID": 77}}
    api.set_param.return_value = {"status": "ok", "response": {"cmdID": 77}}
    return api


@pytest.fixture
def coordinator(mock_api, monkeypatch):
    """A coordinator whose polling sleep is a no-op, so tests cost no wall-clock."""
    monkeypatch.setattr("custom_components.klereo.coordinator.asyncio.sleep", AsyncMock())

    coord = KlereoCoordinator.__new__(KlereoCoordinator)
    coord.api = mock_api
    coord.hass = MagicMock()
    coord.logger = MagicMock()
    coord.name = "klereo"
    coord.update_interval = None
    coord._listeners = {}
    coord.data = {}
    coord.last_update_success = True
    coord.async_request_refresh = AsyncMock()
    return coord


def _statuses(*codes):
    """Successive `CommandStatus` payloads, one per poll."""
    return [{"status": "ok", "response": code} for code in codes]


class TestPollingReplacesBlocking:
    async def test_a_command_still_in_flight_is_polled_until_it_succeeds(
        self, coordinator, mock_api
    ):
        mock_api.command_status.side_effect = _statuses(0, 1, 9)

        await coordinator.async_set_output("SYS1", 2, 0, 1)

        assert mock_api.command_status.await_count == 3

    async def test_a_command_that_succeeds_at_once_is_not_polled_again(
        self, coordinator, mock_api
    ):
        """Positive control: the loop must not poll for its own sake."""
        mock_api.command_status.side_effect = _statuses(9)

        await coordinator.async_set_output("SYS1", 2, 0, 1)

        assert mock_api.command_status.await_count == 1

    async def test_polling_stops_at_the_ceiling_and_never_claims_success(
        self, coordinator, mock_api
    ):
        """A command that never lands is UNCONFIRMED — the ceiling is not a verdict."""
        mock_api.command_status.side_effect = _statuses(*([1] * (CMD_POLL_ATTEMPTS + 5)))

        confirmed = await coordinator._async_confirm_command(
            {"status": "ok", "response": {"cmdID": 77}}, "Setting output 2"
        )

        assert confirmed is False
        assert mock_api.command_status.await_count == CMD_POLL_ATTEMPTS

    async def test_a_rejection_is_raised_at_once_and_not_polled_away(
        self, coordinator, mock_api
    ):
        """🔴 The half a badly written loop swallows.

        Status 13 is a verdict, not a delay. If the loop keeps asking, a refused command
        turns into an exhausted ceiling — a rejection downgraded to "unconfirmed", which is
        exactly the failure #95 exists to prevent.
        """
        mock_api.command_status.side_effect = _statuses(13, 13, 13)

        with pytest.raises(HomeAssistantError, match="insufficient rights"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

        assert mock_api.command_status.await_count == 1


class TestAWriteIsLegibleInTheLog:
    """A successful write logged nothing at all, so its silence meant two opposite things.

    "Home Assistant never sent anything" and "sent, accepted, confirmed" produced the same
    trace — none. @StephanH27 hit exactly that on GitHub #55 and had nowhere to look.
    """

    async def test_the_emission_is_logged_before_the_answer_is_known(
        self, coordinator, mock_api, caplog
    ):
        mock_api.command_status.side_effect = _statuses(9)

        with caplog.at_level(logging.DEBUG, logger="custom_components.klereo.coordinator"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

        assert any("Setting output 2" in r.message and "sending" in r.message.lower()
                   for r in caplog.records)

    async def test_a_confirmed_write_is_logged_with_its_command_id(
        self, coordinator, mock_api, caplog
    ):
        mock_api.command_status.side_effect = _statuses(9)

        with caplog.at_level(logging.DEBUG, logger="custom_components.klereo.coordinator"):
            await coordinator.async_set_output("SYS1", 2, 0, 1)

        assert any("77" in r.getMessage() and "confirmed" in r.getMessage().lower()
                   for r in caplog.records)

    async def test_an_exhausted_ceiling_is_louder_than_debug(
        self, coordinator, mock_api, caplog
    ):
        """Giving up is not routine: it must be visible without turning debug on."""
        mock_api.command_status.side_effect = _statuses(*([1] * (CMD_POLL_ATTEMPTS + 5)))

        with caplog.at_level(logging.DEBUG, logger="custom_components.klereo.coordinator"):
            await coordinator._async_confirm_command(
                {"status": "ok", "response": {"cmdID": 77}}, "Setting output 2"
            )

        assert any(r.levelno >= logging.WARNING for r in caplog.records)
