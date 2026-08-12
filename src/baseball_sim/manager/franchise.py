"""Versioned, cumulative Manager season transition and reward ledger."""

from __future__ import annotations

from dataclasses import dataclass

MANAGER_REWARD_VERSION = "manager-standings-reward-v0.1"
MANAGER_FRANCHISE_VERSION = "manager-franchise-v0.1"
TEAM_COUNT = 6


@dataclass(frozen=True, slots=True)
class SeasonPlacement:
    season_year: int
    ordered_team_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 1990 <= self.season_year <= 9999:
            raise ValueError("Manager season year is invalid")
        if (
            len(self.ordered_team_ids) != TEAM_COUNT
            or len(set(self.ordered_team_ids)) != TEAM_COUNT
        ):
            raise ValueError("season placement requires six unique teams")
        if any(not team_id.strip() for team_id in self.ordered_team_ids):
            raise ValueError("placement team IDs cannot be blank")

    @property
    def champion(self) -> str:
        return self.ordered_team_ids[0]

    @property
    def last_place(self) -> str:
        return self.ordered_team_ids[-1]


@dataclass(frozen=True, slots=True)
class RewardGrant:
    season_year: int
    team_id: str
    ssr_cap_bonus: int
    cost_budget_bonus: int
    reason: str
    version: str = MANAGER_REWARD_VERSION

    def __post_init__(self) -> None:
        policy = {(1, 5): "champion", (2, 10): "consecutive-last-place"}
        if not self.team_id.strip() or not 1990 <= self.season_year <= 9999:
            raise ValueError("reward grant identity is invalid")
        if self.version != MANAGER_REWARD_VERSION:
            raise ValueError("unsupported standings reward version")
        if policy.get((self.ssr_cap_bonus, self.cost_budget_bonus)) != self.reason:
            raise ValueError("reward grant does not match the v0.1 policy")


@dataclass(frozen=True, slots=True)
class TeamEntitlement:
    team_id: str
    ssr_cap_bonus: int = 0
    cost_budget_bonus: int = 0

    def __post_init__(self) -> None:
        if not self.team_id.strip() or self.ssr_cap_bonus < 0 or self.cost_budget_bonus < 0:
            raise ValueError("team entitlement cannot be blank or negative")


@dataclass(frozen=True, slots=True)
class ManagerFranchise:
    active_season_year: int
    team_ids: tuple[str, ...]
    history: tuple[SeasonPlacement, ...] = ()
    reward_grants: tuple[RewardGrant, ...] = ()
    entitlements: tuple[TeamEntitlement, ...] = ()
    version: str = MANAGER_FRANCHISE_VERSION

    def __post_init__(self) -> None:
        if self.version != MANAGER_FRANCHISE_VERSION:
            raise ValueError("unsupported Manager franchise version")
        if len(self.team_ids) != TEAM_COUNT or len(set(self.team_ids)) != TEAM_COUNT:
            raise ValueError("Manager franchise requires six unique teams")
        years = tuple(item.season_year for item in self.history)
        if years != tuple(range(self.active_season_year - len(years), self.active_season_year)):
            raise ValueError("franchise history must be consecutive")
        if any(set(item.ordered_team_ids) != set(self.team_ids) for item in self.history):
            raise ValueError("season history teams must match the franchise")
        if any(grant.team_id not in self.team_ids for grant in self.reward_grants):
            raise ValueError("reward grant team must belong to the franchise")
        if tuple(item.team_id for item in self.entitlements) != tuple(sorted(self.team_ids)):
            raise ValueError("entitlements must cover teams in deterministic order")
        expected = {team_id: [0, 0] for team_id in self.team_ids}
        for grant in self.reward_grants:
            expected[grant.team_id][0] += grant.ssr_cap_bonus
            expected[grant.team_id][1] += grant.cost_budget_bonus
        if any(
            (item.ssr_cap_bonus, item.cost_budget_bonus) != tuple(expected[item.team_id])
            for item in self.entitlements
        ):
            raise ValueError("entitlements must equal the cumulative reward ledger")


def create_franchise(team_ids: tuple[str, ...], season_year: int) -> ManagerFranchise:
    teams = tuple(sorted(team_ids))
    return ManagerFranchise(
        season_year,
        teams,
        entitlements=tuple(TeamEntitlement(team_id) for team_id in teams),
    )


def standings_reward_grants(
    placement: SeasonPlacement, previous: SeasonPlacement | None
) -> tuple[RewardGrant, ...]:
    grants = [RewardGrant(placement.season_year, placement.champion, 1, 5, "champion")]
    if previous is not None and previous.last_place == placement.last_place:
        grants.append(
            RewardGrant(
                placement.season_year,
                placement.last_place,
                2,
                10,
                "consecutive-last-place",
            )
        )
    return tuple(sorted(grants, key=lambda item: (item.team_id, item.reason)))


def advance_to_next_season(
    franchise: ManagerFranchise, final_order: tuple[str, ...]
) -> ManagerFranchise:
    placement = SeasonPlacement(franchise.active_season_year, final_order)
    if set(placement.ordered_team_ids) != set(franchise.team_ids):
        raise ValueError("final standings teams must match the franchise")
    previous = franchise.history[-1] if franchise.history else None
    grants = franchise.reward_grants + standings_reward_grants(placement, previous)
    totals = {team_id: [0, 0] for team_id in franchise.team_ids}
    for grant in grants:
        totals[grant.team_id][0] += grant.ssr_cap_bonus
        totals[grant.team_id][1] += grant.cost_budget_bonus
    entitlements = tuple(
        TeamEntitlement(team_id, totals[team_id][0], totals[team_id][1])
        for team_id in sorted(franchise.team_ids)
    )
    return ManagerFranchise(
        franchise.active_season_year + 1,
        franchise.team_ids,
        franchise.history + (placement,),
        grants,
        entitlements,
    )
