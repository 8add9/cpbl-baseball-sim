"""Pure Manager v0.1 team naming, lineup and rotation customization."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .cards import CardCatalog
from .game_roster import LineupEntry, create_team_game_roster
from .league import ManagerTeamConfig
from .roster import DEFAULT_ROSTER_RULES, RosterRules, RosterSelection

TEAM_CUSTOMIZATION_VERSION = "manager-team-customization-v0.1"
UNLIMITED_TEAM_NAME = "8add9"
AI_CPBL_TEAM_NAMES = (
    "中信兄弟",
    "統一7-ELEVEn獅",
    "樂天桃猿",
    "味全龍",
    "富邦悍將",
    "台鋼雄鷹",
)


@dataclass(frozen=True, slots=True)
class TeamRosterLimits:
    cost_limit: int | None
    ssr_limit: int | None

    @property
    def unlimited(self) -> bool:
        return self.cost_limit is None and self.ssr_limit is None


@dataclass(frozen=True, slots=True)
class RotationPlan:
    """Four scheduled slots; owned SP may intentionally repeat in v0.1."""

    starter_card_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.starter_card_ids) != 4:
            raise ValueError("rotation plan requires exactly four slots")
        if any(not card_id.strip() for card_id in self.starter_card_ids):
            raise ValueError("rotation plan CardIDs cannot be blank")


def roster_limits_for_name(
    display_name: str,
    *,
    base_cost_limit: int = 70,
    base_ssr_limit: int = 2,
    cost_bonus: int = 0,
    ssr_bonus: int = 0,
) -> TeamRosterLimits:
    """The exact team name `8add9` opts into unlimited roster caps."""
    if display_name == UNLIMITED_TEAM_NAME:
        return TeamRosterLimits(None, None)
    values = (base_cost_limit, base_ssr_limit, cost_bonus, ssr_bonus)
    if any(value < 0 for value in values):
        raise ValueError("roster limits and bonuses cannot be negative")
    return TeamRosterLimits(base_cost_limit + cost_bonus, base_ssr_limit + ssr_bonus)


def rename_team(config: ManagerTeamConfig, display_name: str) -> ManagerTeamConfig:
    name = display_name.strip()
    if not name or len(name) > 40:
        raise ValueError("team display name must contain 1 to 40 characters")
    return replace(config, name=name)


def set_starting_lineup(
    catalog: CardCatalog,
    selection: RosterSelection,
    lineup: tuple[LineupEntry, ...],
    rules: RosterRules = DEFAULT_ROSTER_RULES,
) -> tuple[LineupEntry, ...]:
    """Validate any nine roster batters in any batting order at exact positions."""
    create_team_game_roster(
        catalog,
        selection,
        lineup,
        selection.rotation_card_ids[0],
        rules=rules,
    )
    return lineup


def set_rotation_plan(
    selection: RosterSelection, starter_card_ids: tuple[str, ...]
) -> RotationPlan:
    plan = RotationPlan(starter_card_ids)
    if not set(plan.starter_card_ids).issubset(selection.rotation_card_ids):
        raise ValueError("rotation plan may reference only the four owned SP cards")
    return plan
