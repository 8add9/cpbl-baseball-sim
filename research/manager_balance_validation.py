"""Paired Monte Carlo validation for Manager Mode roster strategies.

Each trial is a common-random-number pair: the same seed is used once with the
left team away and once with it home.  Confidence intervals therefore use the
pair score (0, 0.5, or 1) as the independent observation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from baseball_sim.manager.cards import CardCatalog
from baseball_sim.manager.game_roster import LineupEntry, create_team_game_roster
from baseball_sim.manager.game_simulation import create_manager_game, simulate_manager_game
from baseball_sim.manager.loader import load_card_catalog
from baseball_sim.manager.optimizer import RosterStrategy, build_optimized_roster
from baseball_sim.manager.roster import RosterRules, RosterSelection, evaluate_roster

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "generated" / "ratings"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "research"
DEFAULT_REPORT = ROOT / "research" / "manager_balance_report.md"
DEFAULT_GAMES = 20_000
BALANCE_LOW = 0.45
BALANCE_HIGH = 0.55
MAX_NONSTAR_DEFICIT_WINS_PER_120 = 8.0
MAX_MUTUAL_GAP_WINS_PER_120 = 6.0


@dataclass(frozen=True, slots=True)
class TeamSpec:
    label: str
    strategy: str
    selection: RosterSelection
    lineup: tuple[LineupEntry, ...]
    total_cost: int
    sr_count: int
    ssr_count: int
    rule: str


@dataclass(frozen=True, slots=True)
class Comparison:
    name: str
    left: str
    right: str


@dataclass(frozen=True, slots=True)
class ChunkTask:
    comparison: Comparison
    first_pair: int
    pair_count: int
    base_seed: int


@dataclass(frozen=True, slots=True)
class ChunkResult:
    comparison: str
    pairs: int
    left_wins: int
    left_home_wins: int
    left_away_wins: int
    left_runs: int
    right_runs: int
    pair_score_sum: float
    pair_score_squared_sum: float


COMPARISONS = (
    Comparison("balanced_vs_reference", "balanced", "reference"),
    Comparison("offense_vs_reference", "offense", "reference"),
    Comparison("pitching_vs_reference", "pitching", "reference"),
    Comparison("balanced_vs_offense", "balanced", "offense"),
    Comparison("balanced_vs_pitching", "balanced", "pitching"),
    Comparison("offense_vs_pitching", "offense", "pitching"),
)

_WORKER_CATALOG: CardCatalog | None = None
_WORKER_SPECS: dict[str, TeamSpec] = {}


def validate_run_arguments(games: int, workers: int) -> None:
    if games < 2 or games % 2:
        raise ValueError("games must be an even integer of at least 2")
    if workers < 1:
        raise ValueError("workers must be at least 1")


def _stable_seed(base_seed: int, comparison: str, pair_index: int) -> int:
    payload = f"manager-balance-v1|{base_seed}|{comparison}|{pair_index}".encode()
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


def build_team_specs(catalog: CardCatalog) -> dict[str, TeamSpec]:
    """Build four deterministic, mutually card-disjoint benchmark rosters."""
    specs: dict[str, TeamSpec] = {}
    used: set[str] = set()
    plans = (
        ("reference", RosterStrategy.BALANCED, RosterRules(), "standard-legal"),
        ("balanced", RosterStrategy.BALANCED, RosterRules(max_ssr=0, max_sr=3), "0SSR-3SR"),
        ("offense", RosterStrategy.OFFENSE, RosterRules(max_ssr=0, max_sr=3), "0SSR-3SR"),
        ("pitching", RosterStrategy.PITCHING, RosterRules(max_ssr=0, max_sr=3), "0SSR-3SR"),
    )
    for label, strategy, rules, rule_label in plans:
        optimized = build_optimized_roster(
            catalog,
            strategy,
            rules,
            excluded_card_ids=used,
        )
        legality = evaluate_roster(catalog, optimized.selection, rules)
        if not legality.legal:
            raise RuntimeError(f"optimizer returned illegal {label} roster")
        if used.intersection(optimized.selection.all_card_ids):
            raise RuntimeError("benchmark rosters must be card-disjoint")
        used.update(optimized.selection.all_card_ids)
        specs[label] = TeamSpec(
            label=label,
            strategy=strategy.value,
            selection=optimized.selection,
            lineup=optimized.lineup,
            total_cost=legality.total_cost,
            sr_count=legality.sr_count,
            ssr_count=legality.ssr_count,
            rule=rule_label,
        )
    return specs


def _fresh_roster(catalog: CardCatalog, spec: TeamSpec, pair_index: int):
    starter = spec.selection.rotation_card_ids[pair_index % 4]
    return create_team_game_roster(catalog, spec.selection, spec.lineup, starter)


def _play_game(
    catalog: CardCatalog,
    left: TeamSpec,
    right: TeamSpec,
    *,
    pair_index: int,
    left_is_home: bool,
    seed: int,
) -> tuple[bool, int, int]:
    left_roster = _fresh_roster(catalog, left, pair_index)
    right_roster = _fresh_roster(catalog, right, pair_index)
    away, home = (
        (right_roster, left_roster) if left_is_home else (left_roster, right_roster)
    )
    final = simulate_manager_game(create_manager_game(away, home, seed=seed)).final_state
    if final.away_score == final.home_score:
        raise RuntimeError("finished baseball game cannot be tied")
    left_runs, right_runs = (
        (final.home_score, final.away_score)
        if left_is_home
        else (final.away_score, final.home_score)
    )
    return left_runs > right_runs, left_runs, right_runs


def _run_chunk(catalog: CardCatalog, specs: dict[str, TeamSpec], task: ChunkTask) -> ChunkResult:
    left = specs[task.comparison.left]
    right = specs[task.comparison.right]
    wins = home_wins = away_wins = left_runs = right_runs = 0
    pair_sum = pair_squared_sum = 0.0
    for pair_index in range(task.first_pair, task.first_pair + task.pair_count):
        seed = _stable_seed(task.base_seed, task.comparison.name, pair_index)
        pair_wins = 0
        away_win, runs_for, runs_against = _play_game(
            catalog,
            left,
            right,
            pair_index=pair_index,
            left_is_home=False,
            seed=seed,
        )
        pair_wins += int(away_win)
        away_wins += int(away_win)
        left_runs += runs_for
        right_runs += runs_against
        home_win, runs_for, runs_against = _play_game(
            catalog,
            left,
            right,
            pair_index=pair_index,
            left_is_home=True,
            seed=seed,
        )
        pair_wins += int(home_win)
        home_wins += int(home_win)
        left_runs += runs_for
        right_runs += runs_against
        wins += pair_wins
        score = pair_wins / 2.0
        pair_sum += score
        pair_squared_sum += score * score
    return ChunkResult(
        task.comparison.name,
        task.pair_count,
        wins,
        home_wins,
        away_wins,
        left_runs,
        right_runs,
        pair_sum,
        pair_squared_sum,
    )


def _initialize_worker(artifact_root: str, specs: dict[str, TeamSpec]) -> None:
    global _WORKER_CATALOG, _WORKER_SPECS
    _WORKER_CATALOG = load_card_catalog(Path(artifact_root))
    _WORKER_SPECS = specs


def _worker_chunk(task: ChunkTask) -> ChunkResult:
    if _WORKER_CATALOG is None:
        raise RuntimeError("balance worker was not initialized")
    return _run_chunk(_WORKER_CATALOG, _WORKER_SPECS, task)


def _tasks(
    comparisons: tuple[Comparison, ...], games: int, workers: int, seed: int
) -> list[ChunkTask]:
    pair_count = games // 2
    chunks = min(pair_count, workers)
    tasks: list[ChunkTask] = []
    for comparison in comparisons:
        start = 0
        for chunk in range(chunks):
            size = pair_count // chunks + int(chunk < pair_count % chunks)
            tasks.append(ChunkTask(comparison, start, size, seed))
            start += size
    return tasks


def _paired_ci(pair_count: int, pair_sum: float, pair_squared_sum: float) -> tuple[float, float]:
    mean = pair_sum / pair_count
    if pair_count < 2:
        return 0.0, 1.0
    variance = max(0.0, (pair_squared_sum - pair_sum * pair_sum / pair_count) / (pair_count - 1))
    margin = 1.96 * math.sqrt(variance / pair_count)
    return max(0.0, mean - margin), min(1.0, mean + margin)


def summarize_results(
    comparisons: tuple[Comparison, ...],
    chunks: list[ChunkResult],
    games: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for comparison in comparisons:
        selected = [row for row in chunks if row.comparison == comparison.name]
        pairs = sum(row.pairs for row in selected)
        wins = sum(row.left_wins for row in selected)
        pair_sum = sum(row.pair_score_sum for row in selected)
        pair_sq = sum(row.pair_score_squared_sum for row in selected)
        rate = wins / games
        ci_low, ci_high = _paired_ci(pairs, pair_sum, pair_sq)
        if comparison.right == "reference":
            deficit = max(0.0, (0.5 - rate) * 120.0)
            metric_pass = (
                ci_low >= BALANCE_LOW
                and deficit <= MAX_NONSTAR_DEFICIT_WINS_PER_120
            )
            gate_rule = "nonstar-ci-lower>=45%; deficit<=8 wins/120"
        else:
            deficit = abs(rate - 0.5) * 120.0
            metric_pass = (
                BALANCE_LOW <= rate <= BALANCE_HIGH
                or deficit <= MAX_MUTUAL_GAP_WINS_PER_120
            )
            gate_rule = "mutual 45-55%; gap<=6 wins/120"
        sample_pass = games >= DEFAULT_GAMES
        rows.append(
            {
                "comparison": comparison.name,
                "left_team": comparison.left,
                "right_team": comparison.right,
                "games": games,
                "pairs": pairs,
                "left_wins": wins,
                "right_wins": games - wins,
                "left_win_rate": rate,
                "ci95_low": ci_low,
                "ci95_high": ci_high,
                "left_wins_per_120": rate * 120.0,
                "right_wins_per_120": (1.0 - rate) * 120.0,
                "wins_gap_or_deficit_per_120": deficit,
                "left_home_win_rate": sum(row.left_home_wins for row in selected) / pairs,
                "left_away_win_rate": sum(row.left_away_wins for row in selected) / pairs,
                "left_runs_per_game": sum(row.left_runs for row in selected) / games,
                "right_runs_per_game": sum(row.right_runs for row in selected) / games,
                "metric_gate_pass": metric_pass,
                "gate_rule": gate_rule,
                "sample_gate_pass": sample_pass,
                "release_gate_pass": metric_pass and sample_pass,
            }
        )
    return rows


def simulate_comparisons(
    catalog: CardCatalog,
    specs: dict[str, TeamSpec],
    *,
    artifact_root: Path,
    games: int,
    workers: int,
    seed: int,
    comparisons: tuple[Comparison, ...] = COMPARISONS,
) -> list[dict[str, Any]]:
    validate_run_arguments(games, workers)
    tasks = _tasks(comparisons, games, workers, seed)
    if workers == 1:
        chunks = [_run_chunk(catalog, specs, task) for task in tasks]
    else:
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=context,
            initializer=_initialize_worker,
            initargs=(str(artifact_root), specs),
        ) as pool:
            chunks = list(pool.map(_worker_chunk, tasks))
    return summarize_results(comparisons, chunks, games)


def _roster_record(spec: TeamSpec) -> dict[str, Any]:
    return {
        "label": spec.label,
        "strategy": spec.strategy,
        "rule": spec.rule,
        "total_cost": spec.total_cost,
        "sr_count": spec.sr_count,
        "ssr_count": spec.ssr_count,
        "card_ids": list(spec.selection.all_card_ids),
    }


def _write_outputs(
    output_dir: Path,
    report_path: Path,
    *,
    catalog: CardCatalog,
    specs: dict[str, TeamSpec],
    rows: list[dict[str, Any]],
    games: int,
    workers: int,
    seed: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "manager_balance_validation.csv"
    json_path = output_dir / "manager_balance_validation.json"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "schema_version": "manager-balance-validation-v1",
        "rating_snapshot": catalog.snapshot_version,
        "config": {
            "games_per_comparison": games,
            "paired_trials_per_comparison": games // 2,
            "workers": workers,
            "seed": seed,
            "release_minimum_games": DEFAULT_GAMES,
            "balance_band": [BALANCE_LOW, BALANCE_HIGH],
            "ci_method": "normal-95%-over-pair-scores",
        },
        "rosters": [_roster_record(specs[label]) for label in specs],
        "comparisons": rows,
        "overall_release_gate_pass": all(row["release_gate_pass"] for row in rows),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Manager Mode paired balance validation",
        "",
        f"Snapshot: `{catalog.snapshot_version}`. Seed: `{seed}`. Workers: `{workers}`.",
        f"Each comparison used **{games:,} games / {games // 2:,} paired seeds**.",
        "",
        "A pair reuses one random seed with home/away reversed. The 95% CI treats the pair score "
        "(0, 0.5, 1) as one independent observation. The release gate requires at least 20,000 "
        "games per comparison. A non-star roster must have a paired-CI lower bound of at "
        "least 45% and trail the legal reference by no more than eight expected wins per "
        "120. Mutual non-star matchups must remain within 45%-55% or six wins per 120.",
        "",
        "## Rosters",
        "",
        "| Team | Strategy | Rule | Cost | SR | SSR |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for spec in specs.values():
        lines.append(
            f"| {spec.label} | {spec.strategy} | {spec.rule} | {spec.total_cost} | "
            f"{spec.sr_count} | {spec.ssr_count} |"
        )
    lines.extend(
        [
            "",
            "The four fixtures are deterministic and mutually card-disjoint. The reference is a "
            "standard legal balanced optimizer roster; the other three use 0 SSR / at most 3 SR.",
            "",
            "## Results",
            "",
            "| Comparison | Win rate | 95% paired CI | Wins/120 | R/G | Opp R/G | Gate |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        status = "PASS" if row["release_gate_pass"] else "FAIL"
        lines.append(
            f"| {row['comparison']} | {row['left_win_rate']:.3%} | "
            f"{row['ci95_low']:.3%}–{row['ci95_high']:.3%} | "
            f"{row['left_wins_per_120']:.2f} | {row['left_runs_per_game']:.3f} | "
            f"{row['right_runs_per_game']:.3f} | {status} |"
        )
    overall = all(row["release_gate_pass"] for row in rows)
    lines.extend(
        [
            "",
            "## Decision",
            "",
            ("**Release balance gate passed.**" if overall else "**Release balance gate failed.**"),
            "Failures are reported as measured; this research harness does not alter card costs, "
            "optimizer weights, or game-engine coefficients.",
            "",
            "## Interpretation limits",
            "",
            "This isolates roster construction and single-game simulation. Every game starts "
            "with a fresh bullpen, so season fatigue/availability, injuries, and human lineup "
            "management are "
            "outside this gate. Starting pitchers rotate evenly across paired trials.",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_validation(
    *,
    artifact_root: Path,
    output_dir: Path,
    report_path: Path,
    games: int,
    workers: int,
    seed: int,
) -> list[dict[str, Any]]:
    validate_run_arguments(games, workers)
    catalog = load_card_catalog(artifact_root)
    specs = build_team_specs(catalog)
    rows = simulate_comparisons(
        catalog,
        specs,
        artifact_root=artifact_root,
        games=games,
        workers=workers,
        seed=seed,
    )
    _write_outputs(
        output_dir,
        report_path,
        catalog=catalog,
        specs=specs,
        rows=rows,
        games=games,
        workers=workers,
        seed=seed,
    )
    return rows


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--games", type=int, default=DEFAULT_GAMES)
    parser.add_argument("--workers", type=int, default=max(1, multiprocessing.cpu_count() - 1))
    parser.add_argument("--seed", type=int, default=20260812)
    return parser


def main() -> int:
    args = _parser().parse_args()
    rows = run_validation(
        artifact_root=args.artifact_root,
        output_dir=args.output_dir,
        report_path=args.report,
        games=args.games,
        workers=args.workers,
        seed=args.seed,
    )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
