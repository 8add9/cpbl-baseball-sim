"""Generate reproducible PA-model candidate and first-checkpoint evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from baseball_sim.simulation.matchup import (
    BatterRatings,
    MatchupModel,
    PitcherRatings,
    matchup_probabilities,
)
from baseball_sim.simulation.outcomes import Outcome
from baseball_sim.simulation.sampling import analytic_line, simulate_plate_appearances

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "research"
REPORT = ROOT / "research" / "pa_matchup_model_report.md"
SEED = 20260811
PA = 100_000

SCENARIOS = {
    "Neutral": (BatterRatings(), PitcherRatings()),
    "Power50": (BatterRatings(power=50), PitcherRatings()),
    "Power80": (BatterRatings(power=80), PitcherRatings()),
    "Power95": (BatterRatings(power=95), PitcherRatings()),
    "Power100": (BatterRatings(power=100), PitcherRatings()),
    "Power105": (BatterRatings(power=105), PitcherRatings()),
    "Contact95": (BatterRatings(contact=95), PitcherRatings()),
    "Eye95": (BatterRatings(eye=95), PitcherRatings()),
    "Stuff95": (BatterRatings(), PitcherRatings(stuff=95)),
    "Control95": (BatterRatings(), PitcherRatings(control=95)),
    "HRSuppression95": (BatterRatings(), PitcherRatings(hr_suppression=95)),
    "Power100_vs_HRSuppression100": (
        BatterRatings(power=100),
        PitcherRatings(hr_suppression=100),
    ),
    "Contact100_vs_Stuff100": (BatterRatings(contact=100), PitcherRatings(stuff=100)),
}

COEFFICIENT_EVIDENCE = [
    ("Eye", "BB/C", 0.318166, 0.311330, 0.325003, 590503, 53650),
    ("Control", "BB/C", -0.332053, -0.340539, -0.323567, 550665, 48391),
    ("Control", "HBP/C", -0.183413, -0.205064, -0.161763, 509476, 7202),
    ("Contact", "SO/C", -0.319508, -0.325988, -0.313028, 645215, 108362),
    ("Stuff", "SO/C", 0.292498, 0.286566, 0.298429, 606464, 104190),
    ("Power", "HR/nonHR-contact", 0.411641, 0.402977, 0.420305, 536853, 11910),
    (
        "HRSuppression",
        "HR/nonHR-contact",
        -0.381629,
        -0.397185,
        -0.366073,
        502274,
        10749,
    ),
    ("Contact", "nonHR-hit/out", 0.093072, 0.087718, 0.098425, 524943, 160595),
    ("Power", "XBH/1B", 0.133431, 0.124837, 0.142025, 160595, 33036),
]


def _write_csv(path: Path, rows: list[dict[str, str | int | float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rows: list[dict[str, str | int | float]] = []
    for model in MatchupModel:
        for scenario, (batter, pitcher) in SCENARIOS.items():
            probabilities = matchup_probabilities(batter, pitcher, model)
            line = analytic_line(probabilities, PA)
            rows.append(
                {
                    "Model": model.value,
                    "Scenario": scenario,
                    "PA": PA,
                    "BBRate": line["BB"],
                    "HBPRate": line["HBP"],
                    "KRate": line["SO"],
                    "HRRate": line["HR"],
                    "AVG": line["AVG"],
                    "OBP": line["OBP"],
                    "SLG": line["SLG"],
                    "OPS": line["OPS"],
                }
            )
    comparison_path = OUTPUT / "pa_model_candidate_comparison.csv"
    _write_csv(comparison_path, rows)
    coefficient_rows = [
        {
            "Ability": ability,
            "Equation": equation,
            "Beta": beta,
            "CI95Low": low,
            "CI95High": high,
            "Exposure": exposure,
            "Events": events,
        }
        for ability, equation, beta, low, high, exposure, events in COEFFICIENT_EVIDENCE
    ]
    _write_csv(OUTPUT / "pa_model_coefficients.csv", coefficient_rows)

    neutral_prob = matchup_probabilities(BatterRatings(power=65), PitcherRatings())
    elite_prob = matchup_probabilities(BatterRatings(power=100), PitcherRatings())
    neutral_analytic = analytic_line(neutral_prob, PA)
    elite_analytic = analytic_line(elite_prob, PA)
    neutral_sim = simulate_plate_appearances(neutral_prob, PA, np.random.default_rng(SEED))
    elite_sim = simulate_plate_appearances(elite_prob, PA, np.random.default_rng(SEED))
    checkpoint = {
        "model": MatchupModel.HIERARCHICAL.value,
        "pa_per_scenario": PA,
        "seed": SEED,
        "power_65": {"analytic": neutral_analytic, "simulated": neutral_sim.as_dict()},
        "power_100": {"analytic": elite_analytic, "simulated": elite_sim.as_dict()},
        "delta": {
            "analytic_hr_rate": elite_analytic["HR"] - neutral_analytic["HR"],
            "analytic_slg": elite_analytic["SLG"] - neutral_analytic["SLG"],
            "simulated_hr": elite_sim.count(Outcome.HR) - neutral_sim.count(Outcome.HR),
            "simulated_slg": elite_sim.slg - neutral_sim.slg,
        },
    }
    checkpoint_path = OUTPUT / "power_65_vs_100_checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(checkpoint, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    neutral_rows = {row["Model"]: row for row in rows if row["Scenario"] == "Neutral"}
    power_rows = {row["Model"]: row for row in rows if row["Scenario"] == "Power100"}
    report_lines = [
        "# PA Matchup Model Research v0.1",
        "",
        "## Decision",
        "",
        "Accept the hierarchical model for the first playable numerical prototype. ",
        "The flat log-odds and naive multiplicative models remain explicit comparators.",
        "",
        "## Candidate comparison: Power 65 -> 100",
        "",
        "| Model | HR% 65 | HR% 100 | HR pp delta | SLG 65 | SLG 100 | "
        "SLG delta | BB pp leakage | K pp leakage |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MatchupModel:
        neutral = neutral_rows[model.value]
        power = power_rows[model.value]
        report_lines.append(
            f"| {model.value} | {100 * float(neutral['HRRate']):.3f} | "
            f"{100 * float(power['HRRate']):.3f} | "
            f"{100 * (float(power['HRRate']) - float(neutral['HRRate'])):.3f} | "
            f"{float(neutral['SLG']):.3f} | {float(power['SLG']):.3f} | "
            f"{float(power['SLG']) - float(neutral['SLG']):.3f} | "
            f"{100 * (float(power['BBRate']) - float(neutral['BBRate'])):.3f} | "
            f"{100 * (float(power['KRate']) - float(neutral['KRate'])):.3f} |"
        )
    report_lines.extend(
        [
            "",
            "Hierarchical wins the semantic gate because Power leaves the earlier BB, HBP and SO "
            "conditional stages exactly unchanged. Flat and naive renormalization change unrelated "
            "absolute outcomes.",
            "",
            "## Calibration evidence",
            "",
            "Grouped-binomial slopes use 2,940 completed batter seasons (PA>=50) and 2,061 "
            "completed eligible pitcher seasons. Intentional walks are excluded. Every reported "
            "95% interval excludes zero; the full coefficient table is written to "
            "`artifacts/research/pa_model_coefficients.csv`.",
            "",
            "## First hard checkpoint",
            "",
            f"- Fixed seed: `{SEED}`; PA per side: `{PA:,}`.",
            f"- Analytic HR-rate delta: `{checkpoint['delta']['analytic_hr_rate']:.6f}`.",
            f"- Analytic SLG delta: `{checkpoint['delta']['analytic_slg']:.6f}`.",
            f"- Simulated HR-count delta: `{checkpoint['delta']['simulated_hr']}`.",
            f"- Simulated SLG delta: `{checkpoint['delta']['simulated_slg']:.6f}`.",
            "- This is a 2021-2025 league-neutral counterfactual. Rating 65 is anchored to the "
            "chosen league environment by product convention; it is not a claim that historical "
            "Score-0 players exactly equal the PA-weighted league rate.",
            "",
            "The checkpoint passes when HR-rate increases by at least 0.5 percentage points and "
            "SLG by at least 0.050 analytically, with the fixed 100k sample confirming the "
            "direction and material size.",
            "",
            "## Limitations",
            "",
            "This is a season-card matchup approximation, not independently identified "
            "batter-vs-pitcher interaction research. SpeedProxy and Stamina intentionally do not "
            "affect one-PA quality. Intentional walks and game state are deferred. Coefficients "
            "remain versioned and must be replaced only through calibration evidence, never "
            "named-player exceptions.",
            "Power-to-HR slopes remain about 0.39-0.43 by decade, but the linear Score tail must "
            "still be compared with a monotone saturating alternative before balance freeze.",
        ]
    )
    REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(json.dumps(checkpoint["delta"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
