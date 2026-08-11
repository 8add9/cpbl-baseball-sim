"""Command-line entry points for numerical simulation checkpoints."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

import numpy as np

from .simulation.matchup import (
    BatterRatings,
    MatchupModel,
    PitcherRatings,
    matchup_probabilities,
)
from .simulation.sampling import analytic_line, simulate_plate_appearances


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="baseball-sim")
    subparsers = parser.add_subparsers(dest="command", required=True)
    matchup = subparsers.add_parser("matchup", help="simulate independent plate appearances")
    matchup.add_argument("--contact", type=float, default=65.0)
    matchup.add_argument("--power", type=float, default=65.0)
    matchup.add_argument("--eye", type=float, default=65.0)
    matchup.add_argument("--stuff", type=float, default=65.0)
    matchup.add_argument("--control", type=float, default=65.0)
    matchup.add_argument("--hr-suppression", type=float, default=65.0)
    matchup.add_argument("--pa", type=int, default=100_000)
    matchup.add_argument("--seed", type=int, default=20260811)
    matchup.add_argument(
        "--model", choices=[value.value for value in MatchupModel], default="hierarchical"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "matchup":
        raise AssertionError("argparse accepted an unknown command")
    batter = BatterRatings(args.contact, args.power, args.eye)
    pitcher = PitcherRatings(args.stuff, args.control, args.hr_suppression)
    probabilities = matchup_probabilities(batter, pitcher, MatchupModel(args.model))
    sampled = simulate_plate_appearances(probabilities, args.pa, np.random.default_rng(args.seed))
    payload = {
        "model": args.model,
        "seed": args.seed,
        "ratings": {
            "batter": {"contact": args.contact, "power": args.power, "eye": args.eye},
            "pitcher": {
                "stuff": args.stuff,
                "control": args.control,
                "hr_suppression": args.hr_suppression,
            },
        },
        "probabilities": probabilities.as_dict(),
        "analytic": analytic_line(probabilities, args.pa),
        "simulated": sampled.as_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0
