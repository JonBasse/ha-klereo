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
class KlereoPoolDetails:
    """Parsed pool details for a single system."""

    probes: list[KlereoProbe] = field(default_factory=list)
    outs: list[KlereoOutput] = field(default_factory=list)
    regul_modes: dict[str, Any] = field(default_factory=dict)
    probe_index: dict[int, KlereoProbe] = field(default_factory=dict)
    output_index: dict[int, KlereoOutput] = field(default_factory=dict)

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
        return cls(
            probes=probes,
            outs=outs,
            regul_modes=dict(data.get("RegulModes", {})),
            probe_index={p.index: p for p in probes},
            output_index={o.index: o for o in outs},
        )


@dataclass
class KlereoSystemData:
    """Combined info + details for a single pool system."""

    info: KlereoSystemInfo
    details: KlereoPoolDetails
