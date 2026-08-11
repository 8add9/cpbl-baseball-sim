"""Immutable player-season card artifact and competitive catalog contracts."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from baseball_sim.ratings.mapping import score_to_rating
from baseball_sim.simulation.matchup import BatterRatings, PitcherRatings, matchup_probabilities
from baseball_sim.simulation.outcomes import Outcome

TIER_POLICY_VERSION = "tier-impact-v0.1+baseline2021-25"
NEUTRAL_RATING = 65.0


class CardKind(StrEnum):
    BATTER = "batter"
    PITCHER = "pitcher"


class PitcherRole(StrEnum):
    STARTER = "SP"
    RELIEVER = "RP"
    SWINGMAN = "Swingman"


class BatSide(StrEnum):
    RIGHT = "R"
    LEFT = "L"
    SWITCH = "S"


class ThrowSide(StrEnum):
    RIGHT = "R"
    LEFT = "L"


class Tier(StrEnum):
    N = "N"
    R = "R"
    SR = "SR"
    SSR = "SSR"


TIER_COST: Mapping[Tier, int] = MappingProxyType(
    {Tier.N: 1, Tier.R: 3, Tier.SR: 6, Tier.SSR: 10}
)


@dataclass(frozen=True, slots=True)
class AbilityRating:
    score: float
    rating_raw: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.score) or not math.isfinite(self.rating_raw):
            raise ValueError("ability Score and RatingRaw must be finite")
        if not math.isclose(
            score_to_rating(self.score), self.rating_raw, rel_tol=0.0, abs_tol=1e-9
        ):
            raise ValueError("RatingRaw does not match the versioned Score mapping")


@dataclass(frozen=True, slots=True)
class PlayerSeasonCard:
    card_id: str
    player_id: str
    player_name: str
    season_year: int
    team: str
    kind: CardKind
    model_version: str
    mapping_version: str
    profile_positions: tuple[str, ...]
    bats: BatSide
    throws: ThrowSide
    abilities: Mapping[str, AbilityRating]
    incomplete_season: bool = False
    pitcher_role: PitcherRole | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("card_id", self.card_id),
            ("player_id", self.player_id),
            ("player_name", self.player_name),
            ("team", self.team),
            ("model_version", self.model_version),
            ("mapping_version", self.mapping_version),
        ):
            if not value.strip():
                raise ValueError(f"{name} cannot be blank")
        if not 1990 <= self.season_year <= 2026:
            raise ValueError("card season must be between 1990 and 2026")
        if self.incomplete_season != (self.season_year == 2026):
            raise ValueError("only 2026 cards may be incomplete, and every 2026 card must be")
        positions = tuple(
            dict.fromkeys(position.strip().upper() for position in self.profile_positions)
        )
        allowed_positions = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "P"}
        if not positions or any(not position for position in positions):
            raise ValueError("ProfilePosition requires at least one non-blank position")
        if any(position not in allowed_positions for position in positions):
            raise ValueError("ProfilePosition contains an unsupported position")
        object.__setattr__(self, "profile_positions", positions)
        abilities = dict(self.abilities)
        expected = (
            {"Contact", "Power", "Eye", "SpeedProxy"}
            if self.kind is CardKind.BATTER
            else {"Stuff", "Control", "HRSuppression", "Stamina"}
        )
        if set(abilities) != expected:
            raise ValueError(f"{self.kind.value} card ability contract is incomplete")
        object.__setattr__(self, "abilities", MappingProxyType(abilities))
        if self.kind is CardKind.PITCHER and self.pitcher_role is None:
            raise ValueError("pitcher cards require a role")
        if self.kind is CardKind.BATTER and self.pitcher_role is not None:
            raise ValueError("batter cards cannot have a pitcher role")

    @property
    def competitive(self) -> bool:
        return self.season_year <= 2025 and not self.incomplete_season

    def raw(self, ability: str) -> float:
        return self.abilities[ability].rating_raw

    @property
    def eligible_positions(self) -> frozenset[str]:
        """Derive game families without mutating the exact profile artifact value."""
        positions = set(self.profile_positions)
        if positions & {"LF", "CF", "RF"}:
            positions.add("OF")
        if self.kind is CardKind.BATTER and "P" in positions:
            positions.add("DH")
        return frozenset(positions)


def _simplified_ops(batter: BatterRatings, pitcher: PitcherRatings) -> float:
    probabilities = matchup_probabilities(batter, pitcher)
    on_base = sum(
        probabilities[outcome]
        for outcome in (
            Outcome.BB,
            Outcome.HBP,
            Outcome.SINGLE,
            Outcome.DOUBLE,
            Outcome.TRIPLE,
            Outcome.HR,
        )
    )
    at_bat_probability = 1.0 - probabilities[Outcome.BB] - probabilities[Outcome.HBP]
    total_bases = (
        probabilities[Outcome.SINGLE]
        + 2.0 * probabilities[Outcome.DOUBLE]
        + 3.0 * probabilities[Outcome.TRIPLE]
        + 4.0 * probabilities[Outcome.HR]
    )
    return on_base + total_bases / at_bat_probability


def impact(card: PlayerSeasonCard) -> float:
    """Return the researched analytic impact, never a Display or Overall rating."""
    if card.kind is CardKind.BATTER:
        batter = BatterRatings(card.raw("Contact"), card.raw("Power"), card.raw("Eye"))
        return _simplified_ops(batter, PitcherRatings())
    pitcher = PitcherRatings(
        card.raw("Stuff"), card.raw("Control"), card.raw("HRSuppression")
    )
    return -_simplified_ops(BatterRatings(), pitcher)


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    card: PlayerSeasonCard
    impact: float
    percentile: float | None
    tier: Tier | None
    cost: int | None
    policy_version: str = TIER_POLICY_VERSION


def _tier(percentile: float) -> Tier:
    if percentile < 0.40:
        return Tier.N
    if percentile < 0.75:
        return Tier.R
    if percentile < 0.95:
        return Tier.SR
    return Tier.SSR


class CardCatalog:
    """Snapshot-bound cards with completed-pool percentile economics."""

    def __init__(self, snapshot_version: str, cards: Iterable[PlayerSeasonCard]) -> None:
        if not snapshot_version.strip():
            raise ValueError("snapshot_version cannot be blank")
        materialized = tuple(cards)
        if not materialized:
            raise ValueError("card catalog cannot be empty")
        by_id = {card.card_id: card for card in materialized}
        if len(by_id) != len(materialized):
            raise ValueError("card_id must be unique within a snapshot")
        identities = {(card.player_id, card.season_year, card.kind) for card in materialized}
        if len(identities) != len(materialized):
            raise ValueError("player-season-kind must be unique within a snapshot")
        self.snapshot_version = snapshot_version
        self.fingerprint = snapshot_version.rsplit(":", 1)[-1]
        self._entries = self._build_entries(materialized)

    @staticmethod
    def _build_entries(cards: tuple[PlayerSeasonCard, ...]) -> Mapping[str, CatalogEntry]:
        entries: dict[str, CatalogEntry] = {}
        impacts = {card.card_id: impact(card) for card in cards}
        for kind in CardKind:
            pool = [card for card in cards if card.kind is kind and card.competitive]
            pool_values = [impacts[card.card_id] for card in pool]
            for card in (item for item in cards if item.kind is kind):
                value = impacts[card.card_id]
                if not card.competitive:
                    entries[card.card_id] = CatalogEntry(card, value, None, None, None)
                    continue
                below = sum(candidate < value for candidate in pool_values)
                equal = sum(candidate == value for candidate in pool_values)
                percentile = (
                    0.5
                    if len(pool_values) == 1
                    else (below + (equal - 1) / 2) / (len(pool_values) - 1)
                )
                tier = _tier(percentile)
                entries[card.card_id] = CatalogEntry(
                    card, value, percentile, tier, TIER_COST[tier]
                )
        return MappingProxyType(entries)

    def get(self, card_id: str) -> CatalogEntry:
        try:
            return self._entries[card_id]
        except KeyError as error:
            raise KeyError(f"unknown card_id: {card_id}") from error

    def entries(self, *, competitive_only: bool = False) -> tuple[CatalogEntry, ...]:
        values = tuple(self._entries.values())
        if competitive_only:
            return tuple(entry for entry in values if entry.card.competitive)
        return values
