"""Typed data models for Klereo."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KlereoProbe:
    """A Klereo probe sensor reading."""

    index: int
    type: int | None = None
    status: int | None = None
    value: float | None = None
    filtered_value: float | None = None
    direct_value: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KlereoProbe:
        """Parse a probe dict from the API."""
        return cls(
            index=data["index"],
            type=data.get("type"),
            status=data.get("status"),
            value=data.get("value"),
            filtered_value=data.get("filteredValue"),
            direct_value=data.get("directValue"),
        )


@dataclass
class KlereoOutput:
    """A Klereo controllable output."""

    index: int
    status: int = 0
    mode: int = 0
    type: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KlereoOutput:
        """Parse an output dict from the API."""
        return cls(
            index=data["index"],
            status=data.get("status", 0),
            mode=data.get("mode", 0),
            type=data.get("type", 0),
        )


@dataclass
class KlereoSystemInfo:
    """Metadata for a Klereo pool system."""

    id_system: str
    pool_nickname: str = "Klereo Pool"
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KlereoSystemInfo:
        """Parse a system info dict from the API."""
        return cls(
            id_system=data.get("idSystem", ""),
            pool_nickname=data.get("poolNickname", "Klereo Pool"),
            raw=data,
        )


@dataclass
class KlereoAlert:
    """One entry of the `alerts` array Klereo returns beside the pool payload.

    Measured once (GitHub #57, @sbdomo, 2026-08-26):

        {"index": 0, "code": 29, "param": 0,
         "updateTime": "2026-08-26 11:24:58", "level": 2}

    ⚠️ `updated` is a STRING, `"YYYY-MM-DD HH:MM:SS"` — the only such field in the whole
    payload, where `Now`, `lastPing`, `startTime` and every probe `*Time` are integers. It
    is kept verbatim rather than parsed: no timezone is stated anywhere, and inventing one
    would silently shift every timestamp.

    ⚠️ `level` appears in NO source — not the upstream plugin, not `docs/klereo-api.md`,
    not the issue. It is carried through unnamed because its meaning is unknown; do not
    map it to a severity.
    """

    code: int
    param: Any = None
    index: int | None = None
    level: int | None = None
    updated: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KlereoAlert:
        """Parse one alert entry from the API."""
        return cls(
            code=data["code"],
            param=data.get("param"),
            index=data.get("index"),
            level=data.get("level"),
            updated=data.get("updateTime"),
        )


@dataclass
class KlereoPoolDetails:
    """Parsed pool details for a single system."""

    probes: list[KlereoProbe] = field(default_factory=list)
    outs: list[KlereoOutput] = field(default_factory=list)
    regul_modes: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    extra_params: dict[str, Any] = field(default_factory=dict)
    alerts: list[KlereoAlert] = field(default_factory=list)
    reported_alert_count: int | None = None
    access: int | None = None
    probe_index: dict[int, KlereoProbe] = field(default_factory=dict)
    output_index: dict[int, KlereoOutput] = field(default_factory=dict)

    @property
    def settings(self) -> dict[str, Any]:
        """Return setpoints and regulation parameters from either container.

        Three containers are known to carry these, and none of them is redundant:

        - `RegulModes` — guessed from one user's GetIndex log, and the only one read
          before #94. The introducing commit declares the guess in its own comment.
        - `params` — what the upstream Jeedom plugin reads, at 40+ sites.
        - `ExtraParams` — named alongside `params` by an external reporter reading their
          own diagnostic export (GitHub #54, 2026-06-17), the first real payload anyone
          has measured here.

        Precedence runs most-established first, so the read can only ever *add* a value,
        never alter one an existing install already displays.
        """
        return {**self.extra_params, **self.params, **self.regul_modes}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KlereoPoolDetails:
        """Parse pool details from the API."""
        probes = [
            KlereoProbe.from_dict(p)
            for p in data.get("probes", [])
            if p.get("index") is not None
        ]
        outs = [
            KlereoOutput.from_dict(o)
            for o in data.get("outs", [])
            if o.get("index") is not None
        ]
        # 🔴 The `alerts` key is ABSENT when there is nothing to report — not present and
        # empty (GitHub #57, 2026-08-26). So an empty list here means "none active", and
        # it is indistinguishable in the payload from "we failed to read them". That is
        # why the entity built on this is created unconditionally rather than on the key.
        alerts = [
            KlereoAlert.from_dict(a)
            for a in data.get("alerts", [])
            if isinstance(a, dict) and a.get("code") is not None
        ]
        return cls(
            probes=probes,
            outs=outs,
            alerts=alerts,
            # Kept beside `alerts`, never used as the count: the one measured payload
            # carries `alertCount: 0` next to one active alert. Upstream ignores the field
            # too (`klereo.class.php` l.511).
            reported_alert_count=data.get("alertCount"),
            regul_modes=dict(data.get("RegulModes", {})),
            params=dict(data.get("params", {})),
            extra_params=dict(data.get("ExtraParams", {})),
            access=data.get("access"),
            probe_index={p.index: p for p in probes},
            output_index={o.index: o for o in outs},
        )


@dataclass
class KlereoSystemData:
    """Combined info + details for a single pool system."""

    info: KlereoSystemInfo
    details: KlereoPoolDetails
