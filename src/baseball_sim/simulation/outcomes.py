"""Stable plate-appearance outcome ordering."""

from __future__ import annotations

from enum import StrEnum


class Outcome(StrEnum):
    BB = "BB"
    HBP = "HBP"
    SO = "SO"
    OUT = "OUT"
    SINGLE = "1B"
    DOUBLE = "2B"
    TRIPLE = "3B"
    HR = "HR"
