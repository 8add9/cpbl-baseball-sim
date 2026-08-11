from __future__ import annotations

from dataclasses import replace

import pytest

from baseball_sim.manager.cards import (
    AbilityRating,
    BatSide,
    CardCatalog,
    CardKind,
    PitcherRole,
    PlayerSeasonCard,
    ThrowSide,
)
from baseball_sim.manager.game_roster import LineupEntry, create_team_game_roster
from baseball_sim.manager.game_simulation import (
    create_manager_game,
    simulate_manager_game,
    simulate_manager_next_pa,
)
from baseball_sim.manager.roster import RosterSelection
from baseball_sim.ratings.mapping import rating_to_score, score_to_rating


def _ability(rating: float) -> AbilityRating:
    score = rating_to_score(rating)
    return AbilityRating(score, score_to_rating(score))


def _batter(identifier: str, position: str, rating: float = 60.0) -> PlayerSeasonCard:
    return PlayerSeasonCard(
        identifier,
        identifier,
        identifier,
        2025,
        "T",
        CardKind.BATTER,
        "b-v1",
        "map-v1",
        (position,),
        BatSide.RIGHT,
        ThrowSide.RIGHT,
        {
            name: _ability(rating)
            for name in ("Contact", "Power", "Eye", "SpeedProxy")
        },
    )


def _pitcher(
    identifier: str,
    role: PitcherRole,
    *,
    impact_rating: float = 60.0,
    stamina: float = 105.0,
) -> PlayerSeasonCard:
    return PlayerSeasonCard(
        identifier,
        identifier,
        identifier,
        2025,
        "T",
        CardKind.PITCHER,
        "p-v1",
        "map-v1",
        ("P",),
        BatSide.RIGHT,
        ThrowSide.RIGHT,
        {
            "Stuff": _ability(impact_rating),
            "Control": _ability(impact_rating),
            "HRSuppression": _ability(impact_rating),
            "Stamina": _ability(stamina),
        },
        pitcher_role=role,
    )


def _team(prefix: str):
    positions = ("C", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "LF", "CF", "RF")
    batters = [_batter(f"{prefix}-b{index}", position) for index, position in enumerate(positions)]
    starters = [
        _pitcher(f"{prefix}-sp{index}", PitcherRole.STARTER, stamina=35.0)
        for index in range(4)
    ]
    bullpen = [
        _pitcher(
            f"{prefix}-rp{index}",
            PitcherRole.RELIEVER if index < 3 else PitcherRole.SWINGMAN,
            impact_rating=62.0 + index,
        )
        for index in range(5)
    ]
    return batters, starters, bullpen


def _fixture(seed: int = 42):
    away = _team("a")
    home = _team("h")
    reserves = [
        *[_batter(f"reserve-b{index}", "DH", 100.0) for index in range(30)],
        *[
            _pitcher(
                f"reserve-p{index}",
                PitcherRole.RELIEVER,
                impact_rating=100.0,
            )
            for index in range(30)
        ],
    ]
    cards = [*away[0], *away[1], *away[2], *home[0], *home[1], *home[2], *reserves]
    catalog = CardCatalog("snapshot-v1", cards)

    def game_roster(team):
        batters, starters, bullpen = team
        selection = RosterSelection(
            tuple(card.card_id for card in batters),
            tuple(card.card_id for card in starters),
            tuple(card.card_id for card in bullpen),
        )
        indexes = (0, 2, 3, 4, 5, 6, 7, 8, 9)
        positions = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
        lineup = tuple(
            LineupEntry(batters[index].card_id, position)
            for index, position in zip(indexes, positions, strict=True)
        )
        return create_team_game_roster(catalog, selection, lineup, starters[0].card_id)

    return create_manager_game(game_roster(away), game_roster(home), seed=seed)


def test_next_pa_uses_raw_cards_and_synchronizes_lineup_and_pitcher_bf() -> None:
    session = _fixture()
    batter = session.game_state.batter
    pitcher = session.game_state.pitcher
    advanced = simulate_manager_next_pa(session)
    assert advanced.transitions[-1].batter == batter
    assert advanced.transitions[-1].pitcher == pitcher
    assert advanced.game_state.away_lineup_index == advanced.away_roster.current_batter_index == 1
    assert advanced.home_roster.active_pitcher_bf == 1
    assert advanced.away_roster.active_pitcher_bf == 0


def test_capacity_fallback_selects_highest_impact_then_card_id() -> None:
    session = _fixture()
    active = session.home_roster.active_pitcher_id
    counters = tuple(
        (card_id, session.home_roster.active_pitcher_capacity if card_id == active else value)
        for card_id, value in session.home_roster.pitcher_bf
    )
    home = replace(session.home_roster, pitcher_bf=counters)
    exhausted = replace(session, home_roster=home)
    advanced = simulate_manager_next_pa(exhausted)
    candidates = [
        home.catalog.get(card_id)
        for card_id in home.bullpen_card_ids
        if card_id not in home.used_pitcher_card_ids
    ]
    expected = sorted(candidates, key=lambda entry: (-entry.impact, entry.card.card_id))[0]
    assert advanced.home_roster.active_pitcher_id == expected.card.card_id
    assert advanced.transitions[-1].pitcher == expected.card.card_id
    assert advanced.substitution_events[-1].incoming_pitcher_id == expected.card.card_id


def test_exhausted_staff_uses_last_real_pitcher_emergency_extension() -> None:
    session = _fixture()
    active = session.home_roster.active_pitcher_id
    counters = tuple(
        (card_id, session.home_roster.active_pitcher_capacity if card_id == active else value)
        for card_id, value in session.home_roster.pitcher_bf
    )
    home = replace(
        session.home_roster,
        pitcher_bf=counters,
        used_pitcher_card_ids=(active, *session.home_roster.bullpen_card_ids),
    )
    advanced = simulate_manager_next_pa(replace(session, home_roster=home))
    assert advanced.home_roster.active_pitcher_id == active
    assert advanced.home_roster.emergency_extension
    assert advanced.substitution_events[-1].reason == "bullpen-exhausted-extension"


def test_full_simulation_equals_repeated_next_pa_and_is_seed_replayable() -> None:
    initial = _fixture(seed=777)
    full = simulate_manager_game(initial)
    stepped = initial
    while not stepped.game_state.finished:
        stepped = simulate_manager_next_pa(stepped)
    stepped_result = simulate_manager_game(stepped)
    assert stepped_result == full
    assert simulate_manager_game(_fixture(seed=777)) == full
    assert full.final_state.plate_appearances == len(full.transitions)


def test_pause_resume_session_matches_uninterrupted_game() -> None:
    initial = _fixture(seed=1234)
    uninterrupted = simulate_manager_game(initial)
    paused = initial
    for _ in range(25):
        paused = simulate_manager_next_pa(paused)
    resumed = simulate_manager_game(paused)
    assert resumed == uninterrupted
    assert paused.game_state.plate_appearances == 25


def test_opening_snapshot_mismatch_fails_closed() -> None:
    session = _fixture()
    other_catalog = CardCatalog(
        "other-snapshot",
        [entry.card for entry in session.home_roster.catalog.entries()],
    )
    home = replace(session.home_roster, catalog=other_catalog)
    with pytest.raises(ValueError, match="same rating snapshot"):
        create_manager_game(session.away_roster, home, seed=42)
