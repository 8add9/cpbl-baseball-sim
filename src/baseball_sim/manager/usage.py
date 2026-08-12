"""Immutable cross-game pitcher availability for Manager Mode."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .cards import CardCatalog, CardKind, PitcherRole

ROTATION_SIZE = 4
BULLPEN_SIZE = 5
MAX_CONSECUTIVE_RELIEF_GAMES = 2


@dataclass(frozen=True, slots=True)
class PitcherUsageEvent:
    """The pitchers used in one completed team game, in entry order."""

    game_number: int
    starting_pitcher_id: str
    used_pitcher_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.game_number <= 0:
            raise ValueError("game_number must be positive")
        if not self.starting_pitcher_id.strip():
            raise ValueError("starting_pitcher_id cannot be blank")
        if not self.used_pitcher_ids:
            raise ValueError("used_pitcher_ids cannot be empty")
        if self.used_pitcher_ids[0] != self.starting_pitcher_id:
            raise ValueError("the starting pitcher must be first in usage order")
        if len(set(self.used_pitcher_ids)) != len(self.used_pitcher_ids):
            raise ValueError("a pitcher cannot appear twice in one game")


@dataclass(frozen=True, slots=True)
class PitcherAvailability:
    """Replayable availability after a known number of completed team games."""

    catalog: CardCatalog
    rotation_card_ids: tuple[str, ...]
    bullpen_card_ids: tuple[str, ...]
    team_games_played: int
    next_rotation_index: int
    last_start_games: tuple[tuple[str, int | None], ...]
    relief_streaks: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if len(self.rotation_card_ids) != ROTATION_SIZE:
            raise ValueError(f"pitcher usage requires exactly {ROTATION_SIZE} SP cards")
        if len(self.bullpen_card_ids) != BULLPEN_SIZE:
            raise ValueError(f"pitcher usage requires exactly {BULLPEN_SIZE} bullpen cards")
        all_ids = self.rotation_card_ids + self.bullpen_card_ids
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("rotation and bullpen card IDs must be unique")
        if self.team_games_played < 0:
            raise ValueError("team_games_played cannot be negative")
        if not 0 <= self.next_rotation_index < ROTATION_SIZE:
            raise ValueError("next_rotation_index is invalid")

        for card_id in self.rotation_card_ids:
            try:
                card = self.catalog.get(card_id).card
            except KeyError as error:
                raise ValueError(f"unknown rotation card: {card_id}") from error
            if card.kind is not CardKind.PITCHER or card.pitcher_role is not PitcherRole.STARTER:
                raise ValueError("rotation cards must all have SP role")
        for card_id in self.bullpen_card_ids:
            try:
                card = self.catalog.get(card_id).card
            except KeyError as error:
                raise ValueError(f"unknown bullpen card: {card_id}") from error
            if card.kind is not CardKind.PITCHER or card.pitcher_role not in {
                PitcherRole.RELIEVER,
                PitcherRole.SWINGMAN,
            }:
                raise ValueError("bullpen cards must have RP or Swingman role")

        starts = dict(self.last_start_games)
        if len(starts) != len(self.last_start_games) or set(starts) != set(
            self.rotation_card_ids
        ):
            raise ValueError("last-start tracking must cover the four rotation cards")
        if any(
            game is not None and (game <= 0 or game > self.team_games_played)
            for game in starts.values()
        ):
            raise ValueError("last-start game numbers are invalid")

        streaks = dict(self.relief_streaks)
        if len(streaks) != len(self.relief_streaks) or set(streaks) != set(
            self.bullpen_card_ids
        ):
            raise ValueError("relief-streak tracking must cover all bullpen cards")
        if any(not 0 <= streak <= MAX_CONSECUTIVE_RELIEF_GAMES for streak in streaks.values()):
            raise ValueError("relief streak is outside the supported range")

    @property
    def next_game_number(self) -> int:
        return self.team_games_played + 1


def create_pitcher_availability(
    catalog: CardCatalog,
    rotation_card_ids: tuple[str, ...],
    bullpen_card_ids: tuple[str, ...],
) -> PitcherAvailability:
    return PitcherAvailability(
        catalog=catalog,
        rotation_card_ids=rotation_card_ids,
        bullpen_card_ids=bullpen_card_ids,
        team_games_played=0,
        next_rotation_index=0,
        last_start_games=tuple((card_id, None) for card_id in rotation_card_ids),
        relief_streaks=tuple((card_id, 0) for card_id in bullpen_card_ids),
    )


def eligible_starters(state: PitcherAvailability) -> tuple[str, ...]:
    """Return all four SP in configured cyclic order; v0.1 has no SP rest rule."""

    candidates = list(state.rotation_card_ids)
    rotation_index = {
        card_id: index for index, card_id in enumerate(state.rotation_card_ids)
    }

    def key(card_id: str) -> tuple[int, str]:
        distance = (rotation_index[card_id] - state.next_rotation_index) % ROTATION_SIZE
        return distance, card_id

    return tuple(sorted(candidates, key=key))


def select_next_starter(
    state: PitcherAvailability, preferred_card_id: str | None = None
) -> str:
    if preferred_card_id is not None:
        if preferred_card_id not in state.rotation_card_ids:
            raise ValueError("preferred starter must come from the four-card SP rotation")
        return preferred_card_id
    candidates = eligible_starters(state)
    return candidates[0]


def available_bullpen(state: PitcherAvailability) -> tuple[str, ...]:
    streaks = dict(state.relief_streaks)
    return tuple(
        sorted(
            card_id
            for card_id in state.bullpen_card_ids
            if streaks[card_id] < MAX_CONSECUTIVE_RELIEF_GAMES
        )
    )


def apply_pitcher_usage(
    state: PitcherAvailability, event: PitcherUsageEvent
) -> PitcherAvailability:
    """Settle one game or reject the entire transition without partial state."""

    if event.game_number != state.next_game_number:
        raise ValueError("pitcher usage events must be applied in team-game order")
    if event.starting_pitcher_id not in state.rotation_card_ids:
        raise ValueError("starting pitcher must come from the four-card SP rotation")
    relievers = event.used_pitcher_ids[1:]
    unknown = set(relievers) - set(state.bullpen_card_ids)
    if unknown:
        raise ValueError("every non-starter must be an RP or Swingman from the bullpen")
    available = set(available_bullpen(state))
    unavailable = set(relievers) - available
    if unavailable:
        raise ValueError("a reliever cannot pitch a third consecutive team game")

    starts = dict(state.last_start_games)
    starts[event.starting_pitcher_id] = event.game_number
    streaks = dict(state.relief_streaks)
    used_relievers = set(relievers)
    for card_id in state.bullpen_card_ids:
        streaks[card_id] = streaks[card_id] + 1 if card_id in used_relievers else 0
    rotation_index = state.rotation_card_ids.index(event.starting_pitcher_id)
    return replace(
        state,
        team_games_played=event.game_number,
        next_rotation_index=(rotation_index + 1) % ROTATION_SIZE,
        last_start_games=tuple(
            (card_id, starts[card_id]) for card_id in state.rotation_card_ids
        ),
        relief_streaks=tuple(
            (card_id, streaks[card_id]) for card_id in state.bullpen_card_ids
        ),
    )


def replay_pitcher_usage(
    initial: PitcherAvailability, events: tuple[PitcherUsageEvent, ...]
) -> PitcherAvailability:
    state = initial
    for event in events:
        state = apply_pitcher_usage(state, event)
    return state
