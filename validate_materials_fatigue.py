import csv
import math
from collections import defaultdict
from pathlib import Path

from material_properties import get_property


CSV_PATH = Path("materials_fatigue.csv")

EXPECTED_COLUMNS = [
    "Material",
    "material_condition",
    "product_form",
    "Temperature_C",
    "fatigue_dataset_id",
    "K_dash",
    "K_dash_units",
    "n_dash",
    "sigma_f_dash",
    "sigma_f_dash_units",
    "b",
    "epsilon_f_dash",
    "c",
    "load_ratio_R",
    "strain_ratio_R",
    "strain_rate",
    "frequency_Hz",
    "hold_time_s",
    "environment",
    "test_standard",
    "supports_LCF",
    "supports_HCF",
    "supports_Ramberg_Osgood",
    "property_source",
    "property_basis",
    "interpolation_allowed",
    "property_notes",
]

FATIGUE_CONSTANTS = [
    "K_dash",
    "n_dash",
    "sigma_f_dash",
    "b",
    "epsilon_f_dash",
    "c",
]

OPTIONAL_NUMERIC_COLUMNS = [
    "load_ratio_R",
    "strain_ratio_R",
    "strain_rate",
    "frequency_Hz",
    "hold_time_s",
]


def main():
    rows = load_rows()
    errors = []

    errors.extend(validate_csv_shape(rows))
    errors.extend(validate_numeric_fields(rows))
    errors.extend(validate_resolver_behavior(rows))

    if errors:
        print("materials_fatigue.csv validation FAILED")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("materials_fatigue.csv validation PASSED")
    print(f"Rows validated: {len(rows)}")
    print("Exact lookups: PASSED")
    print("Fatigue interpolation disabled checks: PASSED")
    print("Out-of-range checks: PASSED")
    print("Missing-property checks: PASSED")
    print("Condition ambiguity checks: PASSED")
    print("Duplicate-conflict checks: PASSED")
    print("Traceability checks: PASSED")


def load_rows():
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise SystemExit(
                "materials_fatigue.csv header mismatch.\n"
                f"Expected: {EXPECTED_COLUMNS}\n"
                f"Actual:   {reader.fieldnames}"
            )
        return list(reader)


def validate_csv_shape(rows):
    errors = []
    if not rows:
        errors.append("No fatigue rows were found.")
        return errors

    required_text_columns = [
        "Material",
        "material_condition",
        "Temperature_C",
        "fatigue_dataset_id",
        "property_source",
        "property_basis",
        "interpolation_allowed",
    ]

    for index, row in enumerate(rows, start=2):
        if None in row:
            errors.append(f"Row {index} has extra CSV fields: {row[None]}")

        for column in EXPECTED_COLUMNS:
            if column not in row:
                errors.append(f"Row {index} is missing column '{column}'.")

        for column in required_text_columns:
            if not (row.get(column) or "").strip():
                errors.append(f"Row {index} has blank required field '{column}'.")

        interpolation_allowed = (row.get("interpolation_allowed") or "").strip()
        if interpolation_allowed not in {"Yes", "No"}:
            errors.append(
                f"Row {index} has invalid interpolation_allowed value "
                f"'{interpolation_allowed}'. Use Yes or No."
            )

    return errors


def validate_numeric_fields(rows):
    errors = []
    for index, row in enumerate(rows, start=2):
        if parse_float(row.get("Temperature_C")) is None:
            errors.append(f"Row {index} has nonnumeric Temperature_C.")

        for column in FATIGUE_CONSTANTS:
            if parse_float(row.get(column)) is None:
                errors.append(f"Row {index} has nonnumeric or blank {column}.")

        for column in OPTIONAL_NUMERIC_COLUMNS:
            value = row.get(column)
            if value not in (None, "") and parse_float(value) is None:
                errors.append(f"Row {index} has nonnumeric optional {column}.")

    return errors


def validate_resolver_behavior(rows):
    errors = []

    for row in rows:
        material = row["Material"]
        condition = row["material_condition"]
        temperature = float(row["Temperature_C"])

        for property_name in FATIGUE_CONSTANTS:
            result = get_property(rows, material, property_name, temperature, condition)
            if result.status != "EXACT":
                errors.append(
                    f"{material} {condition} {temperature:g} C {property_name} "
                    f"expected EXACT, got {result.status}."
                )
                continue

            expected_value = float(row[property_name])
            if not close(result.value, expected_value):
                errors.append(
                    f"{material} {condition} {temperature:g} C {property_name} "
                    f"value mismatch: expected {expected_value}, got {result.value}."
                )

            if not result.source or not result.basis or not result.condition:
                errors.append(
                    f"{material} {condition} {temperature:g} C {property_name} "
                    "did not return traceability metadata."
                )

    grouped_rows = defaultdict(list)
    for row in rows:
        key = (row["Material"], row["material_condition"], row["fatigue_dataset_id"])
        grouped_rows[key].append(row)

    for (material, condition, dataset_id), group in grouped_rows.items():
        temperatures = sorted(float(row["Temperature_C"]) for row in group)
        low = temperatures[0]
        high = temperatures[-1]

        below = get_property(rows, material, "sigma_f_dash", low - 1.0, condition)
        if below.status != "OUT_OF_RANGE":
            errors.append(
                f"{material} {dataset_id} below-range check expected OUT_OF_RANGE, "
                f"got {below.status}."
            )

        above = get_property(rows, material, "sigma_f_dash", high + 1.0, condition)
        if above.status != "OUT_OF_RANGE":
            errors.append(
                f"{material} {dataset_id} above-range check expected OUT_OF_RANGE, "
                f"got {above.status}."
            )

        if len(temperatures) >= 2:
            midpoint = (temperatures[0] + temperatures[1]) / 2.0
            midpoint_result = get_property(
                rows,
                material,
                "sigma_f_dash",
                midpoint,
                condition,
            )
            if midpoint_result.status != "INTERPOLATION_NOT_ALLOWED":
                errors.append(
                    f"{material} {dataset_id} midpoint check expected "
                    f"INTERPOLATION_NOT_ALLOWED, got {midpoint_result.status}."
                )

    errors.extend(validate_synthetic_missing_property(rows))
    errors.extend(validate_synthetic_ambiguity(rows))
    errors.extend(validate_synthetic_duplicate_conflict(rows))

    return errors


def validate_synthetic_missing_property(rows):
    synthetic = dict(rows[0])
    synthetic["Material"] = "Synthetic Missing Fatigue Property"
    synthetic["epsilon_f_dash"] = ""
    synthetic["Temperature_C"] = "100"
    result = get_property(
        rows + [synthetic],
        synthetic["Material"],
        "epsilon_f_dash",
        100,
        synthetic["material_condition"],
    )
    if result.status != "UNAVAILABLE":
        return [
            "Synthetic blank-property check expected UNAVAILABLE, "
            f"got {result.status}."
        ]
    return []


def validate_synthetic_ambiguity(rows):
    first = dict(rows[0])
    second = dict(rows[0])
    first["Material"] = "Synthetic Ambiguous Fatigue Material"
    second["Material"] = "Synthetic Ambiguous Fatigue Material"
    first["material_condition"] = "Condition A"
    second["material_condition"] = "Condition B"
    result = get_property(
        rows + [first, second],
        "Synthetic Ambiguous Fatigue Material",
        "sigma_f_dash",
        first["Temperature_C"],
    )
    if result.status != "AMBIGUOUS_CONDITION":
        return [
            "Synthetic condition-ambiguity check expected AMBIGUOUS_CONDITION, "
            f"got {result.status}."
        ]
    return []


def validate_synthetic_duplicate_conflict(rows):
    first = dict(rows[0])
    second = dict(rows[0])
    first["Material"] = "Synthetic Duplicate Conflict Fatigue Material"
    second["Material"] = "Synthetic Duplicate Conflict Fatigue Material"
    second["sigma_f_dash"] = str(float(first["sigma_f_dash"]) + 1.0)
    result = get_property(
        rows + [first, second],
        "Synthetic Duplicate Conflict Fatigue Material",
        "sigma_f_dash",
        first["Temperature_C"],
        first["material_condition"],
    )
    if result.status != "DUPLICATE_CONFLICT":
        return [
            "Synthetic duplicate-conflict check expected DUPLICATE_CONFLICT, "
            f"got {result.status}."
        ]
    return []


def parse_float(value):
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def close(first, second):
    return abs(first - second) <= max(1e-12, 1e-9 * max(abs(first), abs(second), 1.0))


if __name__ == "__main__":
    main()
