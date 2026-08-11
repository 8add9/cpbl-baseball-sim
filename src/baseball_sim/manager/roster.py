"""Manager Mode v0.1 roster constraints and legality reporting."""

from __future__ import annotations

from dataclasses import dataclass

from .cards import CardCatalog, CardKind, CatalogEntry, PitcherRole, Tier


@dataclass(frozen=True, slots=True)
class RosterRules:
    roster_size: int = 22
    batter_count: int = 13
    rotation_count: int = 4
    bullpen_count: int = 5
    budget: int = 70
    max_ssr: int = 2
    max_sr: int = 5
    minimum_relief_pitchers: int = 3

    def __post_init__(self) -> None:
        if self.roster_size != self.batter_count + self.rotation_count + self.bullpen_count:
            raise ValueError("roster group counts must sum to roster_size")
        if min(
            self.roster_size,
            self.batter_count,
            self.rotation_count,
            self.bullpen_count,
            self.budget,
            self.minimum_relief_pitchers,
        ) <= 0:
            raise ValueError("roster counts and budget must be positive")
        if self.max_ssr < 0 or self.max_sr < 0:
            raise ValueError("tier caps cannot be negative")
        if self.minimum_relief_pitchers > self.bullpen_count:
            raise ValueError("minimum RP cannot exceed bullpen size")


DEFAULT_ROSTER_RULES = RosterRules()


@dataclass(frozen=True, slots=True)
class RosterSelection:
    batter_card_ids: tuple[str, ...]
    rotation_card_ids: tuple[str, ...]
    bullpen_card_ids: tuple[str, ...]

    @property
    def all_card_ids(self) -> tuple[str, ...]:
        return self.batter_card_ids + self.rotation_card_ids + self.bullpen_card_ids


@dataclass(frozen=True, slots=True)
class RosterLegality:
    legal: bool
    total_cost: int
    sr_count: int
    ssr_count: int
    violations: tuple[str, ...]


_POSITION_SLOTS = ("C", "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF", "OF")


def _can_fill_position_slots(entries: tuple[CatalogEntry, ...]) -> bool:
    candidates = [set(entry.card.eligible_positions) for entry in entries]

    def eligible(slot: str, positions: set[str]) -> bool:
        if slot == "OF":
            return "OF" in positions
        return slot in positions

    slots = sorted(
        _POSITION_SLOTS, key=lambda slot: sum(eligible(slot, item) for item in candidates)
    )

    def assign(index: int, used: frozenset[int]) -> bool:
        if index == len(slots):
            return True
        slot = slots[index]
        return any(
            player not in used
            and eligible(slot, positions)
            and assign(index + 1, used | {player})
            for player, positions in enumerate(candidates)
        )

    return assign(0, frozenset())


def evaluate_roster(
    catalog: CardCatalog,
    selection: RosterSelection,
    rules: RosterRules = DEFAULT_ROSTER_RULES,
) -> RosterLegality:
    violations: list[str] = []
    if len(selection.batter_card_ids) != rules.batter_count:
        violations.append(f"roster requires exactly {rules.batter_count} batters")
    if len(selection.rotation_card_ids) != rules.rotation_count:
        violations.append(f"rotation requires exactly {rules.rotation_count} starters")
    if len(selection.bullpen_card_ids) != rules.bullpen_count:
        violations.append(f"bullpen requires exactly {rules.bullpen_count} pitchers")
    if len(selection.all_card_ids) != rules.roster_size:
        violations.append(f"roster requires exactly {rules.roster_size} cards")
    if len(set(selection.all_card_ids)) != len(selection.all_card_ids):
        violations.append("a card may appear only once")

    groups: list[tuple[str, tuple[str, ...], CardKind]] = [
        ("batter", selection.batter_card_ids, CardKind.BATTER),
        ("rotation", selection.rotation_card_ids, CardKind.PITCHER),
        ("bullpen", selection.bullpen_card_ids, CardKind.PITCHER),
    ]
    entries: list[CatalogEntry] = []
    batter_entries: list[CatalogEntry] = []
    rotation_entries: list[CatalogEntry] = []
    bullpen_entries: list[CatalogEntry] = []
    destinations = {
        "batter": batter_entries,
        "rotation": rotation_entries,
        "bullpen": bullpen_entries,
    }
    for label, identifiers, expected_kind in groups:
        for card_id in identifiers:
            try:
                entry = catalog.get(card_id)
            except KeyError:
                violations.append(f"unknown card in {label}: {card_id}")
                continue
            entries.append(entry)
            destinations[label].append(entry)
            if entry.card.kind is not expected_kind:
                violations.append(f"{card_id} has the wrong card kind for {label}")
            if not entry.card.competitive:
                violations.append(f"{card_id} is not eligible for competitive rosters")

    player_ids = [entry.card.player_id for entry in entries]
    if len(set(player_ids)) != len(player_ids):
        violations.append("only one season card per PlayerID is allowed")
    if any(entry.card.pitcher_role is not PitcherRole.STARTER for entry in rotation_entries):
        violations.append("rotation cards must all have SP role")
    allowed_bullpen = {PitcherRole.RELIEVER, PitcherRole.SWINGMAN}
    if any(entry.card.pitcher_role not in allowed_bullpen for entry in bullpen_entries):
        violations.append("bullpen cards must have RP or Swingman role")
    relief_count = sum(
        entry.card.pitcher_role is PitcherRole.RELIEVER for entry in bullpen_entries
    )
    if len(bullpen_entries) == rules.bullpen_count and relief_count < rules.minimum_relief_pitchers:
        violations.append(f"bullpen requires at least {rules.minimum_relief_pitchers} RP cards")
    if len(batter_entries) == rules.batter_count and not _can_fill_position_slots(
        tuple(batter_entries)
    ):
        violations.append("batters cannot fill 2C, 1B/2B/3B/SS, and four OF slots distinctly")

    competitive_entries = [entry for entry in entries if entry.cost is not None]
    total_cost = sum(entry.cost or 0 for entry in competitive_entries)
    sr_count = sum(entry.tier is Tier.SR for entry in competitive_entries)
    ssr_count = sum(entry.tier is Tier.SSR for entry in competitive_entries)
    if total_cost > rules.budget:
        violations.append(f"roster cost {total_cost} exceeds budget {rules.budget}")
    if ssr_count > rules.max_ssr:
        violations.append(f"SSR count {ssr_count} exceeds cap {rules.max_ssr}")
    if sr_count > rules.max_sr:
        violations.append(f"SR count {sr_count} exceeds cap {rules.max_sr}")
    return RosterLegality(not violations, total_cost, sr_count, ssr_count, tuple(violations))
