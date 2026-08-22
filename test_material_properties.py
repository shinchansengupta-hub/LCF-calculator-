from material_properties import get_property


def base_rows():
    return [
        {
            "Material": "Test Alloy",
            "material_condition": "Condition A",
            "Temperature_C": "20",
            "E_MPa": "100000",
            "E_MPa_units": "MPa",
            "property_source": "Synthetic Source",
            "property_basis": "Synthetic Basis",
            "interpolation_allowed": "Yes",
            "property_notes": "Synthetic row.",
        },
        {
            "Material": "Test Alloy",
            "material_condition": "Condition A",
            "Temperature_C": "120",
            "E_MPa": "90000",
            "E_MPa_units": "MPa",
            "property_source": "Synthetic Source",
            "property_basis": "Synthetic Basis",
            "interpolation_allowed": "Yes",
            "property_notes": "Synthetic row.",
        },
        {
            "Material": "Test Alloy",
            "material_condition": "Condition A",
            "Temperature_C": "20",
            "sigma_f_dash": "950",
            "sigma_f_dash_units": "MPa",
            "property_source": "Synthetic Fatigue",
            "property_basis": "Synthetic Fatigue Basis",
            "interpolation_allowed": "No",
        },
        {
            "Material": "Test Alloy",
            "material_condition": "Condition A",
            "Temperature_C": "120",
            "sigma_f_dash": "850",
            "sigma_f_dash_units": "MPa",
            "property_source": "Synthetic Fatigue",
            "property_basis": "Synthetic Fatigue Basis",
            "interpolation_allowed": "No",
        },
        {
            "Material": "Test Alloy",
            "material_condition": "Condition A",
            "Temperature_C": "20",
            "b": "-0.09",
            "property_source": "Synthetic Fatigue",
            "property_basis": "Synthetic Fatigue Basis",
            "interpolation_allowed": "Yes",
        },
        {
            "Material": "Test Alloy",
            "material_condition": "Condition A",
            "Temperature_C": "120",
            "b": "-0.10",
            "property_source": "Synthetic Fatigue",
            "property_basis": "Synthetic Fatigue Basis",
            "interpolation_allowed": "Yes",
        },
    ]


def assert_close(actual, expected, tolerance=1e-12):
    assert abs(actual - expected) <= tolerance, (actual, expected)


def test_exact_lookup():
    result = get_property(base_rows(), "Test Alloy", "E_MPa", 20)
    assert result.status == "EXACT"
    assert result.value == 100000
    assert result.interpolated is False


def test_linear_interpolation():
    result = get_property(base_rows(), "Test Alloy", "E_MPa", 70)
    assert result.status == "INTERPOLATED"
    assert_close(result.value, 95000)
    assert result.interpolated is True
    assert result.lower_temperature == 20
    assert result.upper_temperature == 120


def test_below_range_rejection():
    result = get_property(base_rows(), "Test Alloy", "E_MPa", 0)
    assert result.status == "OUT_OF_RANGE"
    assert "20 C to 120 C" in result.warning


def test_above_range_rejection():
    result = get_property(base_rows(), "Test Alloy", "E_MPa", 200)
    assert result.status == "OUT_OF_RANGE"
    assert "20 C to 120 C" in result.warning


def test_missing_property():
    result = get_property(base_rows(), "Test Alloy", "S_u_MPa", 20)
    assert result.status == "UNAVAILABLE"
    assert "not present" in result.warning


def test_ambiguous_condition():
    rows = base_rows() + [
        {
            "Material": "Test Alloy",
            "material_condition": "Condition B",
            "Temperature_C": "20",
            "E_MPa": "99000",
        }
    ]
    result = get_property(rows, "Test Alloy", "E_MPa", 20)
    assert result.status == "AMBIGUOUS_CONDITION"


def test_static_property_interpolation():
    result = get_property(base_rows(), "Test Alloy", "E_MPa", 100)
    assert result.status == "INTERPOLATED"
    assert_close(result.value, 92000)


def test_fatigue_interpolation_blocked():
    result = get_property(base_rows(), "Test Alloy", "sigma_f_dash", 70)
    assert result.status == "INTERPOLATION_NOT_ALLOWED"
    assert result.value is None


def test_fatigue_interpolation_explicitly_allowed():
    result = get_property(base_rows(), "Test Alloy", "b", 70)
    assert result.status == "INTERPOLATED"
    assert_close(result.value, -0.095)


def test_blank_property_value():
    rows = [
        {
            "Material": "Blank Alloy",
            "material_condition": "Condition A",
            "Temperature_C": "20",
            "E_MPa": "",
        }
    ]
    result = get_property(rows, "Blank Alloy", "E_MPa", 20)
    assert result.status == "UNAVAILABLE"
    assert "blank" in result.warning


def test_conflicting_duplicate_point():
    rows = base_rows() + [
        {
            "Material": "Test Alloy",
            "material_condition": "Condition A",
            "Temperature_C": "20",
            "E_MPa": "101000",
        }
    ]
    result = get_property(rows, "Test Alloy", "E_MPa", 20)
    assert result.status == "DUPLICATE_CONFLICT"
    assert "Conflicting duplicate" in result.warning


def test_traceability_metadata_returned():
    result = get_property(base_rows(), "Test Alloy", "E_MPa", 20)
    assert result.units == "MPa"
    assert result.source == "Synthetic Source"
    assert result.basis == "Synthetic Basis"
    assert result.condition == "Condition A"


def run_tests():
    tests = [
        test_exact_lookup,
        test_linear_interpolation,
        test_below_range_rejection,
        test_above_range_rejection,
        test_missing_property,
        test_ambiguous_condition,
        test_static_property_interpolation,
        test_fatigue_interpolation_blocked,
        test_fatigue_interpolation_explicitly_allowed,
        test_blank_property_value,
        test_conflicting_duplicate_point,
        test_traceability_metadata_returned,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    run_tests()
