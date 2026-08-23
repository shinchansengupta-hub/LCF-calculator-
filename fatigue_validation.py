"""Validation helpers for fatigue-life comparison and future model calibration.

This module intentionally does not compute fatigue life. It provides reusable
data structures and error metrics for comparing predicted life against
experimental fatigue data on a logarithmic basis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class ExperimentalFatigueSample:
    """Template for an experimental fatigue record."""

    dataset_id: str = ""
    material: str = ""
    material_condition: str = ""
    temperature_C: Optional[float] = None
    analysis_mode: str = ""
    sigma_max_MPa: Optional[float] = None
    sigma_min_MPa: Optional[float] = None
    strain_amplitude: Optional[float] = None
    experimental_life_cycles: Optional[float] = None
    runout: bool = False
    test_standard: str = ""
    environment: str = ""
    frequency_Hz: Optional[float] = None
    strain_rate: Optional[float] = None
    source: str = ""
    notes: str = ""


@dataclass(frozen=True)
class FatigueValidationSample:
    """Predicted-versus-experimental pair used for validation metrics."""

    predicted_life_cycles: float
    experimental_life_cycles: float
    runout: bool = False
    dataset_id: str = ""
    material: str = ""
    material_condition: str = ""
    temperature_C: Optional[float] = None
    analysis_mode: str = ""
    source: str = ""
    notes: str = ""


@dataclass(frozen=True)
class ComparisonModelResult:
    model_name: str
    analysis_mode: str
    predicted_life_cycles: Optional[float]
    reversals: Optional[float]
    availability: str
    temperature_capability: str
    property_basis: str
    condition_compatibility: str
    legacy_fallback_used: bool
    estimated_parameter_used: bool
    warnings: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    status: str = "UNAVAILABLE"
    reason: str = ""


@dataclass(frozen=True)
class ComparisonSummary:
    material: str
    temperature_C: float
    analysis_mode: str
    sigma_max_MPa: float
    sigma_min_MPa: float
    sigma_a_MPa: float
    sigma_m_MPa: float
    model_results: List[ComparisonModelResult] = field(default_factory=list)
    lowest_predicted_life_model: Optional[str] = None
    lowest_predicted_life_cycles: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationMetrics:
    sample_count: int
    skipped_runouts: int
    mean_log_error: Optional[float]
    mean_absolute_log_error: Optional[float]
    rmse_log10: Optional[float]
    percentage_within_factor_2: Optional[float]
    percentage_within_factor_3: Optional[float]


def _validate_positive_pair(predicted_life_cycles, experimental_life_cycles):
    if predicted_life_cycles is None or experimental_life_cycles is None:
        raise ValueError("Predicted and experimental life cycles must be provided.")
    if not math.isfinite(predicted_life_cycles) or not math.isfinite(experimental_life_cycles):
        raise ValueError("Predicted and experimental life cycles must be finite.")
    if predicted_life_cycles <= 0 or experimental_life_cycles <= 0:
        raise ValueError("Predicted and experimental life cycles must be positive.")


def life_ratio(predicted_life_cycles, experimental_life_cycles):
    _validate_positive_pair(predicted_life_cycles, experimental_life_cycles)
    return predicted_life_cycles / experimental_life_cycles


def log_error(predicted_life_cycles, experimental_life_cycles):
    _validate_positive_pair(predicted_life_cycles, experimental_life_cycles)
    return math.log10(predicted_life_cycles) - math.log10(experimental_life_cycles)


def factor_error(predicted_life_cycles, experimental_life_cycles):
    ratio = life_ratio(predicted_life_cycles, experimental_life_cycles)
    return max(ratio, 1.0 / ratio)


def summarize_validation(samples: Sequence[FatigueValidationSample], include_runouts: bool = False):
    """Summarize validation metrics on a logarithmic basis.

    Runouts are excluded by default so they are not treated as ordinary
    failures at the censoring cycle count.
    """

    log_errors = []
    factor_errors = []
    skipped_runouts = 0

    for sample in samples:
        if sample.runout and not include_runouts:
            skipped_runouts += 1
            continue
        try:
            le = log_error(sample.predicted_life_cycles, sample.experimental_life_cycles)
            fe = factor_error(sample.predicted_life_cycles, sample.experimental_life_cycles)
        except ValueError:
            continue
        log_errors.append(le)
        factor_errors.append(fe)

    if not log_errors:
        return ValidationMetrics(
            sample_count=0,
            skipped_runouts=skipped_runouts,
            mean_log_error=None,
            mean_absolute_log_error=None,
            rmse_log10=None,
            percentage_within_factor_2=None,
            percentage_within_factor_3=None,
        )

    count = len(log_errors)
    mean_log_error_value = sum(log_errors) / count
    mean_absolute_log_error_value = sum(abs(value) for value in log_errors) / count
    rmse_log10_value = math.sqrt(sum(value * value for value in log_errors) / count)
    within_factor_2 = sum(1 for value in factor_errors if value <= 2.0) / count * 100.0
    within_factor_3 = sum(1 for value in factor_errors if value <= 3.0) / count * 100.0

    return ValidationMetrics(
        sample_count=count,
        skipped_runouts=skipped_runouts,
        mean_log_error=mean_log_error_value,
        mean_absolute_log_error=mean_absolute_log_error_value,
        rmse_log10=rmse_log10_value,
        percentage_within_factor_2=within_factor_2,
        percentage_within_factor_3=within_factor_3,
    )


def fit_walker_gamma(*args, **kwargs):
    """Reserved for future Walker calibration.

    Walker gamma fitting requires suitable multi-R experimental data and is not
    implemented in this phase.
    """

    raise NotImplementedError(
        "Walker gamma calibration requires suitable multi-R experimental data and is not implemented yet."
    )
