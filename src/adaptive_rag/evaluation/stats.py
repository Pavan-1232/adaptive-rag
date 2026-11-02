"""Bootstrap confidence intervals. Seeded, so a report can be reproduced exactly."""

import numpy as np

DEFAULT_RESAMPLES = 10_000
DEFAULT_SEED = 13


def mean_ci(
    values: list[float],
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float, float]:
    """Return (mean, low, high) with a 95% percentile interval."""
    if not values:
        return (float("nan"),) * 3
    data = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    samples = rng.choice(data, size=(resamples, len(data)), replace=True).mean(axis=1)
    low, high = np.percentile(samples, [2.5, 97.5])
    return float(data.mean()), float(low), float(high)


def paired_difference_ci(
    first: list[float],
    second: list[float],
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float, float]:
    """Return (mean difference, low, high) for first minus second, on the same questions."""
    if len(first) != len(second):
        raise ValueError("paired values must have the same length")
    differences = [a - b for a, b in zip(first, second, strict=True)]
    return mean_ci(differences, resamples, seed)


def is_tie(difference_ci: tuple[float, float, float]) -> bool:
    """An interval that includes zero means the data can't separate the two systems."""
    _, low, high = difference_ci
    return low <= 0 <= high
