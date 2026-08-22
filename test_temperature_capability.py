import csv
from pathlib import Path

from temperature_capability import (
    FULLY_TEMPERATURE_RESOLVED,
    MATCH,
    MISMATCH,
    PARTIAL_MATCH,
    PARTIALLY_TEMPERATURE_INFORMED,
    UNAVAILABLE,
    UNKNOWN,
    assess_temperature_capability,
)


def main():
    test_fully_resolved_synthetic_hcf()
    test_fully_resolved_synthetic_goodman()
    test_fully_resolved_synthetic_lcf()
    test_missing_fatigue_constants()
    test_missing_su_for_goodman()
    test_out_of_range_property()
    test_fatigue_interpolation_disabled()
    test_condition_match()
    test_condition_partial_match()
    test_condition_mismatch()
    test_condition_unknown()
    test_real_nickel_625_mismatch()
    test_real_316_316h_not_full_match()
    test_real_inconel_718_partial()
    test_real_material_without_fatigue_data()
    print("temperature_capability tests PASSED")


def test_fully_resolved_synthetic_hcf():
    result = assess_temperature_capability(
        "Synthetic A",
        25,
        "HCF",
        "None",
        [],
        [fatigue_row("Synthetic A", "Condition A", 25)],
    )
    assert result.capability == FULLY_TEMPERATURE_RESOLVED
    assert result.condition_compatibility == UNKNOWN
    assert set(result.resolved_properties) == {"sigma_f_dash", "b"}


def test_fully_resolved_synthetic_goodman():
    result = assess_temperature_capability(
        "Synthetic A",
        25,
        "HCF",
        "Goodman",
        [static_row("Synthetic A", "Condition A", 25)],
        [fatigue_row("Synthetic A", "Condition A", 25)],
    )
    assert result.capability == FULLY_TEMPERATURE_RESOLVED
    assert result.condition_compatibility == MATCH
    assert set(result.resolved_properties) == {"S_u_MPa", "sigma_f_dash", "b"}


def test_fully_resolved_synthetic_lcf():
    result = assess_temperature_capability(
        "Synthetic A",
        25,
        "LCF",
        "Morrow",
        [static_row("Synthetic A", "Condition A", 25)],
        [fatigue_row("Synthetic A", "Condition A", 25)],
    )
    assert result.capability == FULLY_TEMPERATURE_RESOLVED
    assert result.condition_compatibility == MATCH
    assert set(result.resolved_properties) == {
        "E_MPa",
        "K_dash",
        "n_dash",
        "sigma_f_dash",
        "b",
        "epsilon_f_dash",
        "c",
    }


def test_missing_fatigue_constants():
    result = assess_temperature_capability(
        "Synthetic A",
        25,
        "LCF",
        "None",
        [static_row("Synthetic A", "Condition A", 25)],
        [],
    )
    assert result.capability == PARTIALLY_TEMPERATURE_INFORMED
    assert "K_dash" in result.unresolved_properties


def test_missing_su_for_goodman():
    row = static_row("Synthetic A", "Condition A", 25)
    row["S_u_MPa"] = ""
    result = assess_temperature_capability(
        "Synthetic A",
        25,
        "HCF",
        "Goodman",
        [row],
        [fatigue_row("Synthetic A", "Condition A", 25)],
    )
    assert result.capability == UNAVAILABLE
    assert "S_u_MPa" in result.unresolved_properties


def test_out_of_range_property():
    result = assess_temperature_capability(
        "Synthetic A",
        100,
        "HCF",
        "None",
        [],
        [fatigue_row("Synthetic A", "Condition A", 25)],
    )
    assert result.capability == UNAVAILABLE
    assert "sigma_f_dash" in result.unresolved_properties


def test_fatigue_interpolation_disabled():
    rows = [
        fatigue_row("Synthetic A", "Condition A", 25),
        fatigue_row("Synthetic A", "Condition A", 100),
    ]
    result = assess_temperature_capability(
        "Synthetic A",
        50,
        "HCF",
        "None",
        [],
        rows,
    )
    assert result.capability == UNAVAILABLE
    assert any(item.status == "INTERPOLATION_NOT_ALLOWED" for item in result.required_properties)


def test_condition_match():
    result = assess_temperature_capability(
        "Synthetic A",
        25,
        "LCF",
        "None",
        [static_row("Synthetic A", "Same Condition", 25)],
        [fatigue_row("Synthetic A", "Same Condition", 25)],
    )
    assert result.condition_compatibility == MATCH
    assert result.capability == FULLY_TEMPERATURE_RESOLVED


def test_condition_partial_match():
    result = assess_temperature_capability(
        "Synthetic A",
        25,
        "LCF",
        "None",
        [static_row("Synthetic A", "Alloy X annealed plate", 25)],
        [fatigue_row("Synthetic A", "Alloy X annealed bar", 25)],
    )
    assert result.condition_compatibility == PARTIAL_MATCH
    assert result.capability == PARTIALLY_TEMPERATURE_INFORMED


def test_condition_mismatch():
    result = assess_temperature_capability(
        "Synthetic A",
        25,
        "LCF",
        "None",
        [static_row("Synthetic A", "Alloy X base plate", 25)],
        [fatigue_row("Synthetic A", "Alloy X welded joint", 25)],
    )
    assert result.condition_compatibility == MISMATCH
    assert result.capability == PARTIALLY_TEMPERATURE_INFORMED


def test_condition_unknown():
    result = assess_temperature_capability(
        "Synthetic A",
        25,
        "LCF",
        "None",
        [static_row("Synthetic A", "Condition Alpha", 25)],
        [fatigue_row("Synthetic A", "Condition Beta", 25)],
    )
    assert result.condition_compatibility == UNKNOWN
    assert result.capability == FULLY_TEMPERATURE_RESOLVED


def test_real_nickel_625_mismatch():
    static_rows = load_csv("materials_static.csv")
    fatigue_rows = load_csv("materials_fatigue.csv")
    result = assess_temperature_capability(
        "Nickel 625",
        760,
        "HCF",
        "Goodman",
        static_rows,
        fatigue_rows,
        static_condition="HAYNES 625 hot-rolled plate, 1925F mill-annealed",
        fatigue_condition="Inconel 625 nickel-base superalloy welding joint",
    )
    assert result.condition_compatibility == MISMATCH
    assert result.capability == PARTIALLY_TEMPERATURE_INFORMED


def test_real_316_316h_not_full_match():
    static_rows = load_csv("materials_static.csv")
    fatigue_rows = load_csv("materials_fatigue.csv")
    result = assess_temperature_capability(
        "316 Stainless Steel",
        600,
        "LCF",
        "None",
        static_rows,
        fatigue_rows,
        static_condition="Generic 316 SS, PPPL thermal and structural property table",
        fatigue_condition="316H stainless steel low-cycle fatigue dataset at 600-800 C",
    )
    assert result.condition_compatibility == MISMATCH
    assert result.capability == PARTIALLY_TEMPERATURE_INFORMED


def test_real_inconel_718_partial():
    static_rows = load_csv("materials_static.csv")
    fatigue_rows = load_csv("materials_fatigue.csv")
    result = assess_temperature_capability(
        "Inconel 718",
        537.85,
        "HCF",
        "Goodman",
        static_rows,
        fatigue_rows,
        static_condition="HAYNES 718 plate, mill annealed + 1325F/8h furnace cool to 1150F/8h air cool",
        fatigue_condition="Inconel 718 unified creep-fatigue coefficient dataset at 811 K",
    )
    assert result.condition_compatibility == PARTIAL_MATCH
    assert result.capability == PARTIALLY_TEMPERATURE_INFORMED


def test_real_material_without_fatigue_data():
    static_rows = load_csv("materials_static.csv")
    fatigue_rows = load_csv("materials_fatigue.csv")
    result = assess_temperature_capability(
        "Aluminum 2024-T3",
        100,
        "HCF",
        "Goodman",
        static_rows,
        fatigue_rows,
        static_condition="2024-T3",
    )
    assert result.capability == PARTIALLY_TEMPERATURE_INFORMED
    assert "sigma_f_dash" in result.unresolved_properties


def static_row(material, condition, temperature):
    return {
        "Material": material,
        "material_condition": condition,
        "Temperature_C": str(temperature),
        "E_MPa": "200000",
        "E_MPa_units": "MPa",
        "S_u_MPa": "900",
        "S_u_MPa_units": "MPa",
        "property_source": "Synthetic static source",
        "property_basis": "Synthetic test data",
        "interpolation_allowed": "Yes",
    }


def fatigue_row(material, condition, temperature):
    return {
        "Material": material,
        "material_condition": condition,
        "Temperature_C": str(temperature),
        "K_dash": "1000",
        "K_dash_units": "MPa",
        "n_dash": "0.12",
        "sigma_f_dash": "1200",
        "sigma_f_dash_units": "MPa",
        "b": "-0.09",
        "epsilon_f_dash": "0.08",
        "c": "-0.55",
        "property_source": "Synthetic fatigue source",
        "property_basis": "Synthetic test data",
        "interpolation_allowed": "No",
    }


def load_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    main()
