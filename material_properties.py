from dataclasses import dataclass
from math import isfinite


STATIC_PROPERTIES = {"E_MPa", "S_u_MPa", "S_y_MPa", "CTE_per_C"}
FATIGUE_PROPERTIES = {
    "K_dash",
    "n_dash",
    "sigma_f_dash",
    "b",
    "epsilon_f_dash",
    "c",
}


@dataclass(frozen=True)
class PropertyResult:
    value: float | None
    temperature_C: float | None
    units: str
    source: str
    basis: str
    condition: str
    status: str
    interpolated: bool
    lower_temperature: float | None
    upper_temperature: float | None
    warning: str


def get_property(rows, material, property_name, temperature_C, condition=None):
    """Resolve a material property at temperature from row dictionaries."""
    requested_temperature = _parse_float(temperature_C)
    if requested_temperature is None:
        return _result(
            property_name,
            status="UNAVAILABLE",
            warning="Requested temperature is not numeric or finite.",
        )

    material_rows = [row for row in rows if row.get("Material") == material]
    if not material_rows:
        return _result(
            property_name,
            temperature_C=requested_temperature,
            status="UNAVAILABLE",
            warning=f"No rows found for material '{material}'.",
        )

    property_rows = [row for row in material_rows if property_name in row]
    if not property_rows:
        return _result(
            property_name,
            temperature_C=requested_temperature,
            status="UNAVAILABLE",
            warning=f"Property '{property_name}' is not present for material '{material}'.",
        )

    if condition is None:
        conditions = {_condition(row) for row in property_rows}
        if len(conditions) > 1:
            return _result(
                property_name,
                temperature_C=requested_temperature,
                status="AMBIGUOUS_CONDITION",
                warning=(
                    f"Multiple material conditions are available for '{material}'. "
                    "Specify a material condition."
                ),
            )
        selected_condition = next(iter(conditions))
    else:
        selected_condition = condition
        property_rows = [
            row for row in property_rows if _condition(row) == selected_condition
        ]
        if not property_rows:
            return _result(
                property_name,
                temperature_C=requested_temperature,
                condition=selected_condition,
                status="UNAVAILABLE",
                warning=(
                    f"No rows found for material '{material}', condition "
                    f"'{selected_condition}', and property '{property_name}'."
                ),
            )

    points = []
    blank_at_requested_temperature = False
    invalid_value_seen = False
    for row in property_rows:
        row_temperature = _parse_float(row.get("Temperature_C"))
        if row_temperature is None:
            continue

        value = _parse_float(row.get(property_name))
        if value is None:
            if _same_temperature(row_temperature, requested_temperature):
                blank_at_requested_temperature = True
            elif row.get(property_name, "") not in (None, ""):
                invalid_value_seen = True
            continue

        points.append((row_temperature, value, row))

    if not points:
        warning = f"No finite values found for '{property_name}'."
        if blank_at_requested_temperature:
            warning = f"Property '{property_name}' is blank at the requested temperature."
        elif invalid_value_seen:
            warning = f"Property '{property_name}' contains nonnumeric values."
        return _result(
            property_name,
            temperature_C=requested_temperature,
            condition=selected_condition,
            status="UNAVAILABLE",
            warning=warning,
        )

    conflict = _find_conflicting_duplicate(points)
    if conflict is not None:
        duplicate_temperature = conflict
        return _result(
            property_name,
            temperature_C=requested_temperature,
            condition=selected_condition,
            status="DUPLICATE_CONFLICT",
            lower_temperature=duplicate_temperature,
            upper_temperature=duplicate_temperature,
            warning=(
                f"Conflicting duplicate values found at {duplicate_temperature:g} C "
                f"for '{property_name}'."
            ),
        )

    exact_points = [
        (row_temperature, value, row)
        for row_temperature, value, row in points
        if _same_temperature(row_temperature, requested_temperature)
    ]
    if exact_points:
        row_temperature, value, row = exact_points[0]
        return _result(
            property_name,
            value=value,
            temperature_C=row_temperature,
            condition=selected_condition,
            row=row,
            status="EXACT",
        )

    if blank_at_requested_temperature:
        return _result(
            property_name,
            temperature_C=requested_temperature,
            condition=selected_condition,
            status="UNAVAILABLE",
            warning=f"Property '{property_name}' is blank at the requested temperature.",
        )

    temperatures = sorted({row_temperature for row_temperature, _, _ in points})
    minimum_temperature = temperatures[0]
    maximum_temperature = temperatures[-1]
    if requested_temperature < minimum_temperature or requested_temperature > maximum_temperature:
        return _result(
            property_name,
            temperature_C=requested_temperature,
            condition=selected_condition,
            status="OUT_OF_RANGE",
            lower_temperature=minimum_temperature,
            upper_temperature=maximum_temperature,
            warning=(
                f"Requested temperature {requested_temperature:g} C is outside the "
                f"available range {minimum_temperature:g} C to {maximum_temperature:g} C."
            ),
        )

    lower = _nearest_lower(points, requested_temperature)
    upper = _nearest_upper(points, requested_temperature)
    if lower is None or upper is None:
        return _result(
            property_name,
            temperature_C=requested_temperature,
            condition=selected_condition,
            status="UNAVAILABLE",
            warning=f"Could not identify bounding temperatures for '{property_name}'.",
        )

    lower_temperature, lower_value, lower_row = lower
    upper_temperature, upper_value, upper_row = upper
    if _same_temperature(lower_temperature, upper_temperature):
        return _result(
            property_name,
            temperature_C=requested_temperature,
            condition=selected_condition,
            status="UNAVAILABLE",
            lower_temperature=lower_temperature,
            upper_temperature=upper_temperature,
            warning="Bounding temperatures are identical; interpolation is invalid.",
        )

    if not _interpolation_allowed(lower_row) or not _interpolation_allowed(upper_row):
        property_type = "fatigue" if property_name in FATIGUE_PROPERTIES else "static"
        return _result(
            property_name,
            temperature_C=requested_temperature,
            condition=selected_condition,
            row=lower_row,
            status="INTERPOLATION_NOT_ALLOWED",
            lower_temperature=lower_temperature,
            upper_temperature=upper_temperature,
            warning=(
                f"Interpolation is not allowed for this {property_type} property "
                "between the available temperatures."
            ),
        )

    interpolated_value = lower_value + (upper_value - lower_value) * (
        (requested_temperature - lower_temperature)
        / (upper_temperature - lower_temperature)
    )
    if not isfinite(interpolated_value):
        return _result(
            property_name,
            temperature_C=requested_temperature,
            condition=selected_condition,
            row=lower_row,
            status="UNAVAILABLE",
            lower_temperature=lower_temperature,
            upper_temperature=upper_temperature,
            warning=f"Interpolated value for '{property_name}' is not finite.",
        )

    return _result(
        property_name,
        value=interpolated_value,
        temperature_C=requested_temperature,
        condition=selected_condition,
        row=lower_row,
        status="INTERPOLATED",
        interpolated=True,
        lower_temperature=lower_temperature,
        upper_temperature=upper_temperature,
    )


def _result(
    property_name,
    value=None,
    temperature_C=None,
    units="",
    source="",
    basis="",
    condition="",
    row=None,
    status="UNAVAILABLE",
    interpolated=False,
    lower_temperature=None,
    upper_temperature=None,
    warning="",
):
    if row is not None:
        units = row.get(f"{property_name}_units", row.get("units", units)) or ""
        source = row.get("property_source", source) or ""
        basis = row.get("property_basis", basis) or ""
        condition = _condition(row) if not condition else condition

    return PropertyResult(
        value=value,
        temperature_C=temperature_C,
        units=units,
        source=source,
        basis=basis,
        condition=condition,
        status=status,
        interpolated=interpolated,
        lower_temperature=lower_temperature,
        upper_temperature=upper_temperature,
        warning=warning,
    )


def _condition(row):
    return (row.get("material_condition") or "").strip()


def _parse_float(value):
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(parsed):
        return None
    return parsed


def _same_temperature(first, second):
    return abs(first - second) <= 1e-9


def _interpolation_allowed(row):
    value = (row.get("interpolation_allowed") or "").strip().lower()
    return value in {"yes", "y", "true", "1"}


def _find_conflicting_duplicate(points):
    values_by_temperature = {}
    for temperature, value, _ in points:
        existing = values_by_temperature.setdefault(temperature, value)
        if abs(existing - value) > max(1e-12, 1e-9 * max(abs(existing), abs(value), 1.0)):
            return temperature
    return None


def _nearest_lower(points, requested_temperature):
    candidates = [
        point for point in points if point[0] < requested_temperature
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda point: point[0])


def _nearest_upper(points, requested_temperature):
    candidates = [
        point for point in points if point[0] > requested_temperature
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda point: point[0])
