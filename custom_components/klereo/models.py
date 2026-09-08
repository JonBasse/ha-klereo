"""Typed data models for Klereo."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import REGULATION_REFERENCE_FIELDS


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
    """A Klereo controllable output.

    ⚠️ `off_delay` is the one field here added because a FEATURE reads it, and that is the
    distinction #145 turned on. #145 refused to widen this class to make payload fields
    *visible* — the raw diagnostics export already does that, and a field nothing reads is
    noise. `SetAutoOff` (#162) reads this one to build an entity, and the coordinator hands
    the platforms typed models rather than raw API dicts (`CLAUDE.md`), so it has to be
    carried here. The other unparsed keys of `outs[]` — six on the bench, eight on the
    payload that answered #141 — keep their refusal.

    🔴 **`realStatus` is the PHYSICAL state, `status` is the COMMANDED one — and this class
    still reads `status`, on purpose.** #141 asked which of the two makes law; @nopbop's
    diagnostics export of **2026-09-08** (GitHub #55), taken while his heat pump was
    heating, answers it from inside a single payload:

    - Three outputs are commanded on (`status: 1`) — 1, 3 and 4. Output 1 carries
      `totalTime: 51162044` and reads `realStatus: 1`. Outputs 3 and 4 carry `totalTime: 0`
      and read `realStatus: 0`. Every other output is `status: 0` and agrees trivially.
    - Those `totalTime` values ARE the pool counters, which makes the run times a second
      witness rather than a restatement: `params.PHMinus_TotalTime` equals
      `outs[2].totalTime` to the second (`127218`), `params.Filtration_TotalTime` matches
      `outs[1].totalTime` to within 351 — the stopped counter cannot drift, the running one
      does — and `params.Chauff_TotalTime` is `0`, like both divergent outputs.
    - Meanwhile `AqOnOff`, `AqPower` and `AqPACMode` all read `1`. The pump heats; the box
      has never counted one second on either relay typed for heat. So `realStatus: 0` is
      correct — neither relay ever closed — and `status: 1` is a command with nothing
      behind it.

    Where the two disagree, `realStatus` agrees with the run-time counter and `status` does
    not. That names the fields; it does NOT license swapping them, and `switch`/`select`
    keep reading `status`:

    - `data.get("realStatus", 0)` reads `0` on an installation that does not send the
      field, which is indistinguishable from a real "off". Switching would turn everyone's
      outputs off to fix one — a correction that makes false what was true. Two
      installations have been read and both carry the key; two are not all.
    - The upstream Jeedom plugin does not read it either. `realStatus` appears **zero**
      times in the whole plugin (clone of `MrWaloo/jeedom-klereo` at `10e35cf`, taken
      2026-09-08); it drives its own on/off from `$out['status']`
      (`klereo.class.php:626, 634, 637, 658`). Step 2 of #141's plan, and a negative
      result: not proof, but it moves the burden onto the swap.

    ⚠️ The consequence is stated rather than hidden: on an output whose relay does nothing,
    the switch shows the command and not the world. That is the same shape as GitHub #58,
    and it is now a known, measured limitation instead of an unexplained one. The field
    reaches a reporter through the raw diagnostics export (#145) and through nothing else.
    See #141 and `docs/klereo-api.md` § *Détail d'un bassin*.
    """

    index: int
    status: int = 0
    mode: int = 0
    type: int = 0
    off_delay: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KlereoOutput:
        """Parse an output dict from the API.

        🔴 `off_delay` defaults to `None`, NOT to `0`, unlike the four fields above it.
        An absent timer is unknown, and `0` is the single value nobody has measured — the
        upstream-declared floor is `1`. Defaulting to it would both invent a reading and
        pick a side in an open question (#162).
        """
        return cls(
            index=data["index"],
            status=data.get("status", 0),
            mode=data.get("mode", 0),
            type=data.get("type", 0),
            off_delay=data.get("offDelay"),
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


def _parse_regulation_probes(data: dict[str, Any]) -> dict[str, int]:
    """Return {regulation: probe index} for the reference fields this payload carries.

    An ABSENT field is left out rather than defaulted: `0` is a valid probe index, so a
    default would invent a reference on every installation that sends none.

    An integer written as a string is accepted, the way `_label_for_mode` accepts one —
    "16" addresses probe 16 unambiguously, and refusing it would drop a reference we can
    read. Anything else is dropped: a float index would have to be truncated, and a
    truncation is a guess about which probe was meant. `True` is rejected explicitly,
    since Python would otherwise read it as probe 1.

    `-1` is kept as-is. It is a real answer — "this regulation has no reference probe" —
    and dropping it here would make it indistinguishable from an absent field, which is
    exactly what the reader downstream has to tell apart.
    """
    probes = {}
    for api_key, name in REGULATION_REFERENCE_FIELDS.items():
        value = data.get(api_key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            probes[name] = value
        elif isinstance(value, str):
            try:
                probes[name] = int(value)
            except ValueError:
                continue
    return probes


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
    regulation_probes: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

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
    def from_dict(
        cls, data: dict[str, Any], raw: dict[str, Any] | None = None
    ) -> KlereoPoolDetails:
        """Parse pool details from the API.

        `data` is the merged view the parser reads — the `GetIndex` entry for this pool
        with the `GetPoolDetails` element laid over it. `raw` is that `GetPoolDetails`
        element VERBATIM, kept for the diagnostics export and read by nothing else.

        🔴 It is kept because the export is the only remote instrument this project has,
        and it was structurally blind to every field this class does not name: `outs[]`
        carried eleven keys on the bench and `KlereoOutput` parses four, so `realStatus` —
        the field that blocked #141 — could only be seen by calling the API with the
        owner's own credentials. No reporter can do that for us. See #145.

        ⚠️ "Eleven" was never a shape. @nopbop's export of 2026-09-08 carries THIRTEEN keys
        on eight of its ten outputs and eleven on the other two — the count varies inside a
        single payload, not merely between installations (#138's lesson, one level down).
        That is the argument for keeping the payload verbatim rather than for enumerating
        it: what is exported must not depend on a count anyone got right once.

        ✅ It paid for itself: #141 is answered out of a raw payload a reporter pasted, and
        the verdict — `realStatus` physical, `status` commanded, and why `switch`/`select`
        keep reading `status` anyway — is written on `KlereoOutput` above.

        ⚠️ Carrying it here is NOT a licence to widen `KlereoOutput`. A field nothing
        reads is noise; #138 refused exactly that. The raw payload answers the question
        *instead of* growing the model, which is the whole point of doing it in the
        export.

        The two halves of the wire are disjoint and both exported: `KlereoSystemInfo.raw`
        holds the `GetIndex` entry, this holds the `GetPoolDetails` element. Storing the
        merged view here would publish the `GetIndex` half twice.
        """
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
            regulation_probes=_parse_regulation_probes(data),
            raw=dict(raw) if isinstance(raw, dict) else {},
        )


@dataclass
class KlereoSystemData:
    """Combined info + details for a single pool system."""

    info: KlereoSystemInfo
    details: KlereoPoolDetails
