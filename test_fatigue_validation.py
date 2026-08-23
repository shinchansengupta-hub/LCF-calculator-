import math

from fatigue_validation import (
    FatigueValidationSample,
    factor_error,
    fit_walker_gamma,
    life_ratio,
    log_error,
    summarize_validation,
)


def main():
    test_basic_pair_metrics()
    test_aggregate_metrics()
    test_runout_handling()
    test_gamma_fit_stub()
    print("test_fatigue_validation.py PASSED")


def test_basic_pair_metrics():
    assert math.isclose(life_ratio(1000.0, 500.0), 2.0)
    assert math.isclose(log_error(1000.0, 500.0), math.log10(2.0))
    assert math.isclose(factor_error(1000.0, 500.0), 2.0)


def test_aggregate_metrics():
    samples = [
        FatigueValidationSample(100.0, 200.0),
        FatigueValidationSample(200.0, 100.0),
        FatigueValidationSample(1000.0, 1000.0),
    ]
    metrics = summarize_validation(samples)
    assert metrics.sample_count == 3
    assert metrics.skipped_runouts == 0
    assert metrics.mean_log_error is not None
    assert metrics.mean_absolute_log_error is not None
    assert metrics.rmse_log10 is not None
    assert metrics.percentage_within_factor_2 == 100.0
    assert metrics.percentage_within_factor_3 == 100.0


def test_runout_handling():
    samples = [
        FatigueValidationSample(100.0, 200.0),
        FatigueValidationSample(100.0, 10_000.0, runout=True),
    ]
    metrics = summarize_validation(samples)
    assert metrics.sample_count == 1
    assert metrics.skipped_runouts == 1


def test_gamma_fit_stub():
    try:
        fit_walker_gamma([])
    except NotImplementedError:
        return
    raise AssertionError("Walker gamma fitting stub should raise NotImplementedError.")


if __name__ == "__main__":
    main()
