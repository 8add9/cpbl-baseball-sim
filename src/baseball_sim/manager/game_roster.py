"""Per-game lineup, bench, pitcher usage, and PA-boundary substitutions."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum

from .cards import CardCatalog, CardKind, PitcherRole, PlayerSeasonCard
from .roster import DEFAULT_ROSTER_RULES, RosterRules, RosterSelection, evaluate_roster

LINEUP_POSITIONS = frozenset({"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"})


class PlateAppearanceSide(StrEnum):
    BATTING = "batting"
    FIELDING = "fielding"


@dataclass(frozen=True, slots=True)
class LineupEntry:
    card_id: str
    position: str

    def __post_init__(self) -> None:
        if not self.card_id.strip():
            raise ValueError("lineup card_id cannot be blank")
        if self.position not in LINEUP_POSITIONS:
            raise ValueError("lineup position is invalid")


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def pitcher_bf_capacity(card: PlayerSeasonCard) -> int:
    if card.kind is not CardKind.PITCHER or card.pitcher_role is None:
        raise ValueError("BF capacity requires a pitcher card with a role")
    stamina = card.raw("Stamina")
    if card.pitcher_role is PitcherRole.STARTER:
        return min(32, max(18, _round_half_up(24.0 + 0.25 * (stamina - 65.0))))
    if card.pitcher_role is PitcherRole.SWINGMAN:
        return min(20, max(8, _round_half_up(12.0 + 0.20 * (stamina - 65.0))))
    return min(8, max(3, _round_half_up(5.0 + 0.10 * (stamina - 65.0))))


@dataclass(frozen=True, slots=True)
class TeamGameRoster:
    catalog: CardCatalog
    lineup: tuple[LineupEntry, ...]
    bench_card_ids: tuple[str, ...]
    rotation_card_ids: tuple[str, ...]
    bullpen_card_ids: tuple[str, ...]
    active_pitcher_id: str
    current_batter_index: int
    used_batter_card_ids: tuple[str, ...]
    removed_batter_card_ids: tuple[str, ...]
    used_pitcher_card_ids: tuple[str, ...]
    pitcher_bf: tuple[tuple[str, int], ...]
    pa_in_progress: PlateAppearanceSide | None = None
    unavailable_pitcher_card_ids: tuple[str, ...] = ()
    emergency_extension: bool = False

    def __post_init__(self) -> None:
        if len(self.lineup) != 9 or len(self.bench_card_ids) < 4:
            raise ValueError("a game roster requires lineup 9 and at least four bench cards")
        if len(self.rotation_card_ids) != 4 or len(self.bullpen_card_ids) != 5:
            raise ValueError("a game roster requires rotation 4 and bullpen 5")
        if {entry.position for entry in self.lineup} != LINEUP_POSITIONS:
            raise ValueError("lineup must assign every exact defensive position once")
        if len({entry.card_id for entry in self.lineup}) != 9:
            raise ValueError("lineup card IDs must be unique")
        if not 0 <= self.current_batter_index < 9:
            raise ValueError("current batter index is invalid")
        if self.active_pitcher_id not in self.used_pitcher_card_ids:
            raise ValueError("active pitcher must be recorded as used")
        if len(set(self.used_pitcher_card_ids)) != len(self.used_pitcher_card_ids):
            raise ValueError("used pitcher IDs must be unique")
        counters = dict(self.pitcher_bf)
        if len(counters) != len(self.pitcher_bf) or any(value < 0 for value in counters.values()):
            raise ValueError("pitcher BF counters are invalid")
        if set(counters) != set(self.rotation_card_ids + self.bullpen_card_ids):
            raise ValueError("pitcher BF counters must cover rotation and bullpen")
        unavailable = self.unavailable_pitcher_card_ids
        if len(set(unavailable)) != len(unavailable):
            raise ValueError("unavailable pitcher IDs must be unique")
        if not set(unavailable).issubset(self.bullpen_card_ids):
            raise ValueError("only bullpen cards may be unavailable for a game")
        if self.active_pitcher_id in unavailable:
            raise ValueError("the active pitcher cannot be unavailable")
        if self.emergency_extension and self.active_pitcher_bf < self.active_pitcher_capacity:
            raise ValueError("emergency extension requires a pitcher at BF capacity")

    @property
    def current_batter(self) -> LineupEntry:
        return self.lineup[self.current_batter_index]

    @property
    def active_pitcher_bf(self) -> int:
        return dict(self.pitcher_bf)[self.active_pitcher_id]

    @property
    def active_pitcher_capacity(self) -> int:
        return pitcher_bf_capacity(self.catalog.get(self.active_pitcher_id).card)

    @property
    def pitcher_change_required(self) -> bool:
        return (
            not self.emergency_extension
            and self.active_pitcher_bf >= self.active_pitcher_capacity
        )


def create_team_game_roster(
    catalog: CardCatalog,
    roster: RosterSelection,
    lineup: tuple[LineupEntry, ...],
    starting_pitcher_id: str,
    unavailable_pitcher_card_ids: tuple[str, ...] = (),
    rules: RosterRules = DEFAULT_ROSTER_RULES,
) -> TeamGameRoster:
    legality = evaluate_roster(catalog, roster, rules)
    if not legality.legal:
        raise ValueError(f"manager roster is illegal: {'; '.join(legality.violations)}")
    lineup_ids = tuple(entry.card_id for entry in lineup)
    if len(lineup_ids) != 9 or not set(lineup_ids).issubset(roster.batter_card_ids):
        raise ValueError("lineup must contain nine roster batter cards")
    for entry in lineup:
        card = catalog.get(entry.card_id).card
        if card.kind is not CardKind.BATTER:
            raise ValueError("lineup entries must be batter cards")
        if entry.position != "DH" and entry.position not in card.profile_positions:
            raise ValueError("lineup assignment must match exact ProfilePosition")
    bench = tuple(card_id for card_id in roster.batter_card_ids if card_id not in lineup_ids)
    if starting_pitcher_id not in roster.rotation_card_ids:
        raise ValueError("starting pitcher must be one of the four rotation cards")
    counters = tuple(
        (card_id, 0)
        for card_id in roster.rotation_card_ids + roster.bullpen_card_ids
    )
    return TeamGameRoster(
        catalog=catalog,
        lineup=lineup,
        bench_card_ids=bench,
        rotation_card_ids=roster.rotation_card_ids,
        bullpen_card_ids=roster.bullpen_card_ids,
        active_pitcher_id=starting_pitcher_id,
        current_batter_index=0,
        used_batter_card_ids=lineup_ids,
        removed_batter_card_ids=(),
        used_pitcher_card_ids=(starting_pitcher_id,),
        pitcher_bf=counters,
        unavailable_pitcher_card_ids=unavailable_pitcher_card_ids,
    )


def _require_boundary(state: TeamGameRoster) -> None:
    if state.pa_in_progress is not None:
        raise ValueError("substitutions are allowed only between plate appearances")


def pinch_hit(state: TeamGameRoster, bench_card_id: str) -> TeamGameRoster:
    _require_boundary(state)
    if bench_card_id not in state.bench_card_ids:
        raise ValueError("pinch hitter is not an unused available bench card")
    if bench_card_id in state.used_batter_card_ids:
        raise ValueError("a batter cannot re-enter after appearing")
    incoming = state.catalog.get(bench_card_id).card
    outgoing = state.current_batter
    if outgoing.position != "DH" and outgoing.position not in incoming.profile_positions:
        raise ValueError("pinch hitter cannot fill the outgoing exact position")
    lineup = list(state.lineup)
    lineup[state.current_batter_index] = LineupEntry(bench_card_id, outgoing.position)
    return replace(
        state,
        lineup=tuple(lineup),
        used_batter_card_ids=state.used_batter_card_ids + (bench_card_id,),
        removed_batter_card_ids=state.removed_batter_card_ids + (outgoing.card_id,),
    )


def change_pitcher(state: TeamGameRoster, pitcher_card_id: str) -> TeamGameRoster:
    _require_boundary(state)
    if pitcher_card_id not in state.bullpen_card_ids:
        raise ValueError("replacement pitcher must come from the bullpen")
    if pitcher_card_id in state.used_pitcher_card_ids:
        raise ValueError("a pitcher cannot re-enter the same game")
    if pitcher_card_id in state.unavailable_pitcher_card_ids:
        raise ValueError("pitcher is unavailable because of cross-game usage")
    return replace(
        state,
        active_pitcher_id=pitcher_card_id,
        used_pitcher_card_ids=state.used_pitcher_card_ids + (pitcher_card_id,),
        emergency_extension=False,
    )


def enable_emergency_extension(state: TeamGameRoster) -> TeamGameRoster:
    """Continue the last real pitcher only when no legal unused bullpen arm remains."""
    _require_boundary(state)
    if state.active_pitcher_bf < state.active_pitcher_capacity:
        raise ValueError("emergency extension requires a pitcher at BF capacity")
    remaining = set(state.bullpen_card_ids) - set(state.used_pitcher_card_ids)
    remaining -= set(state.unavailable_pitcher_card_ids)
    if remaining:
        raise ValueError("emergency extension is forbidden while a bullpen arm is available")
    return replace(state, emergency_extension=True)


def begin_batting_pa(state: TeamGameRoster) -> TeamGameRoster:
    _require_boundary(state)
    return replace(state, pa_in_progress=PlateAppearanceSide.BATTING)


def complete_batting_pa(state: TeamGameRoster) -> TeamGameRoster:
    if state.pa_in_progress is not PlateAppearanceSide.BATTING:
        raise ValueError("no batting plate appearance is in progress")
    return replace(
        state,
        current_batter_index=(state.current_batter_index + 1) % 9,
        pa_in_progress=None,
    )


def begin_fielding_pa(state: TeamGameRoster) -> TeamGameRoster:
    _require_boundary(state)
    if state.pitcher_change_required:
        raise ValueError("active pitcher reached BF capacity and must be replaced")
    return replace(state, pa_in_progress=PlateAppearanceSide.FIELDING)


def complete_fielding_pa(state: TeamGameRoster) -> TeamGameRoster:
    if state.pa_in_progress is not PlateAppearanceSide.FIELDING:
        raise ValueError("no fielding plate appearance is in progress")
    counters = dict(state.pitcher_bf)
    counters[state.active_pitcher_id] += 1
    ordered = tuple((card_id, counters[card_id]) for card_id, _value in state.pitcher_bf)
    return replace(state, pitcher_bf=ordered, pa_in_progress=None)
