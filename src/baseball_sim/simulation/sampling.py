"""Deterministic sampling and batting-line summaries."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .outcomes import Outcome
from .probabilities import ProbabilityVector


@dataclass(frozen=True, slots=True)
class BattingLine:
    pa: int
    counts: tuple[int, ...]

    def count(self, outcome: Outcome) -> int:
        return self.counts[list(Outcome).index(outcome)]

    @property
    def ab(self) -> int:
        return self.pa - self.count(Outcome.BB) - self.count(Outcome.HBP)

    @property
    def hits(self) -> int:
        return sum(self.count(outcome) for outcome in Outcome if outcome in HIT_OUTCOMES)

    @property
    def total_bases(self) -> int:
        return (
            self.count(Outcome.SINGLE)
            + 2 * self.count(Outcome.DOUBLE)
            + 3 * self.count(Outcome.TRIPLE)
            + 4 * self.count(Outcome.HR)
        )

    @property
    def avg(self) -> float:
        return self.hits / self.ab

    @property
    def obp(self) -> float:
        return (self.hits + self.count(Outcome.BB) + self.count(Outcome.HBP)) / self.pa

    @property
    def slg(self) -> float:
        return self.total_bases / self.ab

    @property
    def ops(self) -> float:
        return self.obp + self.slg

    def as_dict(self) -> dict[str, float | int]:
        values: dict[str, float | int] = {outcome.value: self.count(outcome) for outcome in Outcome}
        values.update(
            {
                "PA": self.pa,
                "AB": self.ab,
                "H": self.hits,
                "AVG": self.avg,
                "OBP": self.obp,
                "SLG": self.slg,
                "OPS": self.ops,
            }
        )
        return values


HIT_OUTCOMES = frozenset({Outcome.SINGLE, Outcome.DOUBLE, Outcome.TRIPLE, Outcome.HR})


def analytic_line(probabilities: ProbabilityVector, pa: int) -> dict[str, float]:
    if pa <= 0:
        raise ValueError("pa must be positive")
    counts = {outcome: pa * probabilities[outcome] for outcome in Outcome}
    ab = pa - counts[Outcome.BB] - counts[Outcome.HBP]
    hits = sum(counts[outcome] for outcome in HIT_OUTCOMES)
    total_bases = (
        counts[Outcome.SINGLE]
        + 2 * counts[Outcome.DOUBLE]
        + 3 * counts[Outcome.TRIPLE]
        + 4 * counts[Outcome.HR]
    )
    obp = (hits + counts[Outcome.BB] + counts[Outcome.HBP]) / pa
    slg = total_bases / ab
    return {
        **{outcome.value: counts[outcome] / pa for outcome in Outcome},
        "AVG": hits / ab,
        "OBP": obp,
        "SLG": slg,
        "OPS": obp + slg,
    }


def simulate_plate_appearances(
    probabilities: ProbabilityVector, pa: int, rng: np.random.Generator
) -> BattingLine:
    if pa <= 0:
        raise ValueError("pa must be positive")
    counts = rng.multinomial(pa, probabilities.values)
    return BattingLine(pa=pa, counts=tuple(int(value) for value in counts))
