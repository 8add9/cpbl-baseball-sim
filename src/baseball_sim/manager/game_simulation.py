"""Deterministic Manager rosters connected to the authoritative M3 PA engine."""

from __future__ import annotations

from dataclasses import dataclass

from baseball_sim.game.engine import Transition
from baseball_sim.game.simulation import simulate_next_pa
from baseball_sim.game.state import GameState, Team
from baseball_sim.simulation.matchup import BatterRatings, PitcherRatings

from .cards import CardKind
from .game_roster import (
    TeamGameRoster,
    begin_batting_pa,
    begin_fielding_pa,
    change_pitcher,
    complete_batting_pa,
    complete_fielding_pa,
    enable_emergency_extension,
)


@dataclass(frozen=True, slots=True)
class PitcherSubstitutionEvent:
    sequence: int
    team: Team
    outgoing_pitcher_id: str
    incoming_pitcher_id: str
    reason: str = "bf-capacity"


@dataclass(frozen=True, slots=True)
class ManagerGameSession:
    game_state: GameState
    away_roster: TeamGameRoster
    home_roster: TeamGameRoster
    transitions: tuple[Transition, ...] = ()
    substitution_events: tuple[PitcherSubstitutionEvent, ...] = ()

    def __post_init__(self) -> None:
        if self.game_state.away_lineup != tuple(
            entry.card_id for entry in self.away_roster.lineup
        ):
            raise ValueError("away M3 lineup is out of sync with Manager roster")
        if self.game_state.home_lineup != tuple(
            entry.card_id for entry in self.home_roster.lineup
        ):
            raise ValueError("home M3 lineup is out of sync with Manager roster")
        if self.game_state.away_pitcher != self.away_roster.active_pitcher_id:
            raise ValueError("away active pitcher is out of sync")
        if self.game_state.home_pitcher != self.home_roster.active_pitcher_id:
            raise ValueError("home active pitcher is out of sync")
        if self.game_state.away_lineup_index != self.away_roster.current_batter_index:
            raise ValueError("away batting-order index is out of sync")
        if self.game_state.home_lineup_index != self.home_roster.current_batter_index:
            raise ValueError("home batting-order index is out of sync")
        if (
            self.away_roster.pa_in_progress is not None
            or self.home_roster.pa_in_progress is not None
        ):
            raise ValueError("Manager sessions may persist only at PA boundaries")
        if len(self.transitions) != self.game_state.plate_appearances:
            raise ValueError("transition count must match M3 plate appearances")


@dataclass(frozen=True, slots=True, eq=False)
class ManagerGameResult:
    final_state: GameState
    away_roster: TeamGameRoster
    home_roster: TeamGameRoster
    transitions: tuple[Transition, ...]
    substitution_events: tuple[PitcherSubstitutionEvent, ...]

    def __post_init__(self) -> None:
        if not self.final_state.finished:
            raise ValueError("ManagerGameResult requires a finished M3 game")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ManagerGameResult):
            return NotImplemented
        return (
            self.final_state == other.final_state
            and _roster_signature(self.away_roster) == _roster_signature(other.away_roster)
            and _roster_signature(self.home_roster) == _roster_signature(other.home_roster)
            and self.transitions == other.transitions
            and self.substitution_events == other.substitution_events
        )


def _roster_signature(roster: TeamGameRoster) -> tuple[object, ...]:
    return (
        roster.catalog.snapshot_version,
        roster.lineup,
        roster.bench_card_ids,
        roster.rotation_card_ids,
        roster.bullpen_card_ids,
        roster.active_pitcher_id,
        roster.current_batter_index,
        roster.used_batter_card_ids,
        roster.removed_batter_card_ids,
        roster.used_pitcher_card_ids,
        roster.pitcher_bf,
        roster.pa_in_progress,
        roster.unavailable_pitcher_card_ids,
        roster.emergency_extension,
    )


def _validate_fresh_roster(roster: TeamGameRoster) -> None:
    if roster.current_batter_index != 0:
        raise ValueError("a new Manager game requires both batting orders at leadoff")
    if roster.pa_in_progress is not None:
        raise ValueError("a new Manager game must begin at a PA boundary")
    if roster.used_pitcher_card_ids != (roster.active_pitcher_id,):
        raise ValueError("a new Manager game cannot contain previously used pitchers")
    if any(value != 0 for _card_id, value in roster.pitcher_bf):
        raise ValueError("a new Manager game requires zero pitcher BF counters")
    batter_ids = tuple(entry.card_id for entry in roster.lineup) + roster.bench_card_ids
    pitcher_ids = roster.rotation_card_ids + roster.bullpen_card_ids
    for card_id in batter_ids + pitcher_ids:
        try:
            entry = roster.catalog.get(card_id)
        except KeyError as error:
            raise ValueError(f"new Manager game is missing card: {card_id}") from error
        if not entry.card.competitive or entry.cost is None:
            raise ValueError("a new Manager game contains a non-competitive card")
        expected = CardKind.BATTER if card_id in batter_ids else CardKind.PITCHER
        if entry.card.kind is not expected:
            raise ValueError("a new Manager game card has the wrong roster kind")


def create_manager_game(
    away_roster: TeamGameRoster,
    home_roster: TeamGameRoster,
    *,
    seed: int,
) -> ManagerGameSession:
    _validate_fresh_roster(away_roster)
    _validate_fresh_roster(home_roster)
    if away_roster.catalog.snapshot_version != home_roster.catalog.snapshot_version:
        raise ValueError("both teams must pin the same rating snapshot")
    state = GameState(
        away_lineup=tuple(entry.card_id for entry in away_roster.lineup),
        home_lineup=tuple(entry.card_id for entry in home_roster.lineup),
        away_pitcher=away_roster.active_pitcher_id,
        home_pitcher=home_roster.active_pitcher_id,
        seed=seed,
        rating_snapshot_version=away_roster.catalog.snapshot_version,
    )
    return ManagerGameSession(state, away_roster, home_roster)


def _fallback_pitcher(roster: TeamGameRoster) -> str:
    candidates = [
        roster.catalog.get(card_id)
        for card_id in roster.bullpen_card_ids
        if card_id not in roster.used_pitcher_card_ids
        and card_id not in roster.unavailable_pitcher_card_ids
    ]
    if not candidates:
        raise RuntimeError("no unused bullpen pitcher remains at the required PA boundary")
    candidates.sort(key=lambda entry: (-entry.impact, entry.card.card_id))
    return candidates[0].card.card_id


def _ensure_pitcher(
    roster: TeamGameRoster,
    game_state: GameState,
    team: Team,
) -> tuple[TeamGameRoster, GameState, PitcherSubstitutionEvent | None]:
    if not roster.pitcher_change_required:
        return roster, game_state, None
    outgoing = roster.active_pitcher_id
    try:
        incoming = _fallback_pitcher(roster)
    except RuntimeError:
        roster = enable_emergency_extension(roster)
        event = PitcherSubstitutionEvent(
            sequence=game_state.plate_appearances + 1,
            team=team,
            outgoing_pitcher_id=outgoing,
            incoming_pitcher_id=outgoing,
            reason="bullpen-exhausted-extension",
        )
        return roster, game_state, event
    roster = change_pitcher(roster, incoming)
    game_state = game_state.with_pitcher(team, incoming)
    event = PitcherSubstitutionEvent(
        sequence=game_state.plate_appearances + 1,
        team=team,
        outgoing_pitcher_id=outgoing,
        incoming_pitcher_id=incoming,
    )
    return roster, game_state, event


def _batter(card_id: str, roster: TeamGameRoster) -> BatterRatings:
    card = roster.catalog.get(card_id).card
    if card.kind is not CardKind.BATTER:
        raise ValueError("M3 batting lineup references a non-batter card")
    return BatterRatings(card.raw("Contact"), card.raw("Power"), card.raw("Eye"))


def _pitcher(card_id: str, roster: TeamGameRoster) -> PitcherRatings:
    card = roster.catalog.get(card_id).card
    if card.kind is not CardKind.PITCHER:
        raise ValueError("M3 active pitcher references a non-pitcher card")
    return PitcherRatings(
        card.raw("Stuff"), card.raw("Control"), card.raw("HRSuppression")
    )


def simulate_manager_next_pa(session: ManagerGameSession) -> ManagerGameSession:
    if session.game_state.finished:
        raise ValueError("cannot simulate a PA in a finished Manager game")
    state = session.game_state
    away = session.away_roster
    home = session.home_roster
    batting = away if state.batting_team is Team.AWAY else home
    fielding_team = state.fielding_team
    fielding = home if fielding_team is Team.HOME else away
    fielding, state, substitution = _ensure_pitcher(fielding, state, fielding_team)
    if fielding_team is Team.HOME:
        home = fielding
    else:
        away = fielding

    batting_started = begin_batting_pa(batting)
    fielding_started = begin_fielding_pa(fielding)
    transition = simulate_next_pa(
        state,
        {state.batter: _batter(state.batter, batting)},
        {state.pitcher: _pitcher(state.pitcher, fielding)},
    )
    batting = complete_batting_pa(batting_started)
    fielding = complete_fielding_pa(fielding_started)
    if state.batting_team is Team.AWAY:
        away, home = batting, fielding
    else:
        home, away = batting, fielding
    events = session.substitution_events + (() if substitution is None else (substitution,))
    return ManagerGameSession(
        transition.state,
        away,
        home,
        session.transitions + (transition,),
        events,
    )


def simulate_manager_game(
    session: ManagerGameSession, *, max_plate_appearances: int = 1_000
) -> ManagerGameResult:
    if max_plate_appearances <= 0:
        raise ValueError("max_plate_appearances must be positive")
    current = session
    added = 0
    while not current.game_state.finished and added < max_plate_appearances:
        current = simulate_manager_next_pa(current)
        added += 1
    if not current.game_state.finished:
        raise RuntimeError("Manager game exceeded the plate-appearance safety limit")
    return ManagerGameResult(
        current.game_state,
        current.away_roster,
        current.home_roster,
        current.transitions,
        current.substitution_events,
    )
