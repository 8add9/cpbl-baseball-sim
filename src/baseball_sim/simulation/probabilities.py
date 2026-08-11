"""Probability value objects and the audited neutral league baseline."""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

from .outcomes import Outcome

PROBABILITY_TOLERANCE = 1e-12


@dataclass(frozen=True, slots=True)
class ProbabilityVector:
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.values) != len(Outcome):
            raise ValueError(f"expected {len(Outcome)} probabilities")
        if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in self.values):
            raise ValueError("probabilities must be finite and within [0, 1]")
        if not math.isclose(sum(self.values), 1.0, rel_tol=0.0, abs_tol=PROBABILITY_TOLERANCE):
            raise ValueError("probabilities must sum to one")

    @classmethod
    def from_mapping(cls, values: Mapping[Outcome, float]) -> ProbabilityVector:
        return cls(tuple(float(values[outcome]) for outcome in Outcome))

    @classmethod
    def normalized(cls, weights: Iterable[float]) -> ProbabilityVector:
        raw = tuple(float(value) for value in weights)
        if len(raw) != len(Outcome):
            raise ValueError(f"expected {len(Outcome)} weights")
        if not all(math.isfinite(value) and value >= 0.0 for value in raw):
            raise ValueError("weights must be finite and non-negative")
        total = sum(raw)
        if total <= 0.0:
            raise ValueError("at least one weight must be positive")
        return cls(tuple(value / total for value in raw))

    def __getitem__(self, outcome: Outcome) -> float:
        return self.values[list(Outcome).index(outcome)]

    def __iter__(self) -> Iterator[float]:
        return iter(self.values)

    def as_dict(self) -> dict[str, float]:
        return {outcome.value: self[outcome] for outcome in Outcome}


# Audited from completed CPBL seasons 2021-2025, excluding intentional walks.
# Twelve unclassified PA (0.0097%) are conservatively absorbed into OUT.
DEFAULT_BASELINE_2021_2025 = ProbabilityVector.from_mapping(
    {
        Outcome.BB: 0.075000,
        Outcome.HBP: 0.013106,
        Outcome.SO: 0.171333,
        Outcome.OUT: 0.508316,
        Outcome.SINGLE: 0.176035,
        Outcome.DOUBLE: 0.038540,
        Outcome.TRIPLE: 0.004296,
        Outcome.HR: 0.013374,
    }
)
