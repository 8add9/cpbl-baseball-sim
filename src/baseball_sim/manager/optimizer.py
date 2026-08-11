"""Deterministic budget-roster construction for Manager balance fixtures."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from .cards import CardCatalog, CardKind, CatalogEntry, PitcherRole, Tier
from .game_roster import LineupEntry
from .roster import RosterRules, RosterSelection, evaluate_roster


class RosterStrategy(StrEnum):
    BALANCED = "balanced"
    OFFENSE = "offense"
    PITCHING = "pitching"


_BATTER_BUDGET_CAP = {
    RosterStrategy.BALANCED: 42,
    RosterStrategy.OFFENSE: 52,
    RosterStrategy.PITCHING: 30,
}


@dataclass(frozen=True, slots=True)
class OptimizedRoster:
    strategy: RosterStrategy
    selection: RosterSelection
    lineup: tuple[LineupEntry, ...]
    total_cost: int
    utility: float


@dataclass(frozen=True, slots=True)
class _Slot:
    label: str
    kind: CardKind
    position: str | None = None
    role: PitcherRole | None = None


@dataclass(frozen=True, slots=True)
class _SearchState:
    entries: tuple[CatalogEntry, ...]
    player_ids: frozenset[str]
    cost: int
    sr_count: int
    ssr_count: int
    utility: float


_SLOTS = (
    _Slot("C", CardKind.BATTER, position="C"),
    _Slot("1B", CardKind.BATTER, position="1B"),
    _Slot("2B", CardKind.BATTER, position="2B"),
    _Slot("3B", CardKind.BATTER, position="3B"),
    _Slot("SS", CardKind.BATTER, position="SS"),
    _Slot("LF", CardKind.BATTER, position="LF"),
    _Slot("CF", CardKind.BATTER, position="CF"),
    _Slot("RF", CardKind.BATTER, position="RF"),
    _Slot("DH", CardKind.BATTER, position="DH"),
    _Slot("bench-C", CardKind.BATTER, position="C"),
    _Slot("bench-OF", CardKind.BATTER, position="OF"),
    _Slot("bench-flex-1", CardKind.BATTER),
    _Slot("bench-flex-2", CardKind.BATTER),
    *(_Slot(f"SP-{index}", CardKind.PITCHER, role=PitcherRole.STARTER) for index in range(4)),
    *(_Slot(f"RP-{index}", CardKind.PITCHER, role=PitcherRole.RELIEVER) for index in range(3)),
    *(
        _Slot(f"Swing-{index}", CardKind.PITCHER, role=PitcherRole.SWINGMAN)
        for index in range(2)
    ),
)


def _eligible(entry: CatalogEntry, slot: _Slot) -> bool:
    card = entry.card
    if card.kind is not slot.kind or entry.cost is None or entry.percentile is None:
        return False
    if slot.kind is CardKind.BATTER:
        if slot.position is None or slot.position == "DH":
            return True
        return slot.position in card.eligible_positions
    if slot.role is not None:
        return card.pitcher_role is slot.role
    return card.pitcher_role in {PitcherRole.RELIEVER, PitcherRole.SWINGMAN}


def _weight(strategy: RosterStrategy, kind: CardKind) -> float:
    if strategy is RosterStrategy.OFFENSE:
        return 1.35 if kind is CardKind.BATTER else 0.65
    if strategy is RosterStrategy.PITCHING:
        return 0.65 if kind is CardKind.BATTER else 1.35
    return 1.0


def _candidate_pool(
    catalog: CardCatalog,
    slot: _Slot,
    strategy: RosterStrategy,
    excluded_card_ids: frozenset[str],
) -> tuple[CatalogEntry, ...]:
    eligible = [
        entry
        for entry in catalog.entries(competitive_only=True)
        if entry.card.card_id not in excluded_card_ids and _eligible(entry, slot)
    ]
    selected: list[CatalogEntry] = []
    for tier in Tier:
        tier_entries = [entry for entry in eligible if entry.tier is tier]
        tier_entries.sort(
            key=lambda entry: (
                -_weight(strategy, slot.kind) * (entry.percentile or 0.0),
                entry.card.card_id,
            )
        )
        selected.extend(tier_entries[:16])
    return tuple(selected)


def _cost_diverse_beam(
    expanded: list[_SearchState], beam_width: int
) -> tuple[_SearchState, ...]:
    """Keep strong paths at every reachable cost instead of spending early by accident."""
    expanded.sort(
        key=lambda state: (
            -state.utility,
            state.cost,
            tuple(entry.card.card_id for entry in state.entries),
        )
    )
    by_cost: dict[int, list[_SearchState]] = {}
    for state in expanded:
        by_cost.setdefault(state.cost, []).append(state)
    selected: list[_SearchState] = []
    depth = 0
    costs = sorted(by_cost)
    while len(selected) < beam_width:
        added = False
        for cost in costs:
            bucket = by_cost[cost]
            if depth < len(bucket):
                selected.append(bucket[depth])
                added = True
                if len(selected) == beam_width:
                    break
        if not added:
            break
        depth += 1
    return tuple(selected)


def build_optimized_roster(
    catalog: CardCatalog,
    strategy: RosterStrategy = RosterStrategy.BALANCED,
    rules: RosterRules | None = None,
    *,
    beam_width: int = 250,
    excluded_card_ids: Collection[str] | None = None,
) -> OptimizedRoster:
    """Build a deterministic legal roster; intended for AI and balance fixtures."""
    if beam_width <= 0:
        raise ValueError("beam_width must be positive")
    rules = rules or RosterRules()
    excluded = frozenset(excluded_card_ids or ())
    if rules.roster_size != len(_SLOTS) or rules.batter_count != 13:
        raise ValueError("optimizer supports the frozen 22-card Manager v0.1 roster")
    states: tuple[_SearchState, ...] = (
        _SearchState((), frozenset(), 0, 0, 0, 0.0),
    )
    for slot_index, slot in enumerate(_SLOTS):
        candidates = _candidate_pool(catalog, slot, strategy, excluded)
        if not candidates:
            raise ValueError(f"catalog has no competitive candidate for {slot.label}")
        remaining = len(_SLOTS) - slot_index - 1
        expanded: list[_SearchState] = []
        for state in states:
            for entry in candidates:
                card = entry.card
                if card.player_id in state.player_ids:
                    continue
                cost = state.cost + (entry.cost or 0)
                if (
                    slot.kind is CardKind.BATTER
                    and cost > _BATTER_BUDGET_CAP[strategy]
                ):
                    continue
                sr_count = state.sr_count + int(entry.tier is Tier.SR)
                ssr_count = state.ssr_count + int(entry.tier is Tier.SSR)
                if (
                    cost + remaining > rules.budget
                    or sr_count > rules.max_sr
                    or ssr_count > rules.max_ssr
                ):
                    continue
                expanded.append(
                    _SearchState(
                        state.entries + (entry,),
                        state.player_ids | {card.player_id},
                        cost,
                        sr_count,
                        ssr_count,
                        state.utility
                        + _weight(strategy, slot.kind) * (entry.percentile or 0.0),
                    )
                )
        if not expanded:
            raise ValueError(f"no legal roster path remains at slot {slot.label}")
        states = _cost_diverse_beam(expanded, beam_width)

    ranked_states = sorted(
        states,
        key=lambda state: (
            -state.utility,
            state.cost,
            tuple(entry.card.card_id for entry in state.entries),
        ),
    )
    for state in ranked_states:
        batter_ids = tuple(entry.card.card_id for entry in state.entries[:13])
        rotation_ids = tuple(entry.card.card_id for entry in state.entries[13:17])
        bullpen_ids = tuple(entry.card.card_id for entry in state.entries[17:])
        selection = RosterSelection(batter_ids, rotation_ids, bullpen_ids)
        legality = evaluate_roster(catalog, selection, rules)
        if legality.legal:
            lineup = tuple(
                LineupEntry(entry.card.card_id, slot.position or "DH")
                for entry, slot in zip(state.entries[:9], _SLOTS[:9], strict=True)
            )
            return OptimizedRoster(
                strategy, selection, lineup, legality.total_cost, state.utility
            )
    raise ValueError("optimizer could not construct a legal roster")
