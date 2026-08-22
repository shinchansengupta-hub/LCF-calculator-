from dataclasses import dataclass

from material_properties import get_property


FULLY_TEMPERATURE_RESOLVED = "FULLY_TEMPERATURE_RESOLVED"
PARTIALLY_TEMPERATURE_INFORMED = "PARTIALLY_TEMPERATURE_INFORMED"
UNAVAILABLE = "UNAVAILABLE"

MATCH = "MATCH"
PARTIAL_MATCH = "PARTIAL_MATCH"
MISMATCH = "MISMATCH"
UNKNOWN = "UNKNOWN"

AVAILABLE_STATUSES = {"EXACT", "INTERPOLATED"}

REQUIRED_PROPERTIES = {
    ("HCF", "None"): {
        "static": [],
        "fatigue": ["sigma_f_dash", "b"],
    },
    ("HCF", "Goodman"): {
        "static": ["S_u_MPa"],
        "fatigue": ["sigma_f_dash", "b"],
    },
    ("LCF", "None"): {
        "static": ["E_MPa"],
        "fatigue": [
            "K_dash",
            "n_dash",
            "sigma_f_dash",
            "b",
            "epsilon_f_dash",
            "c",
        ],
    },
    ("LCF", "Morrow"): {
        "static": ["E_MPa"],
        "fatigue": [
            "K_dash",
            "n_dash",
            "sigma_f_dash",
            "b",
            "epsilon_f_dash",
            "c",
        ],
    },
}


@dataclass(frozen=True)
class ResolvedProperty:
    property_name: str
    property_group: str
    value: float | None
    status: str
    source: str
    condition: str
    basis: str
    interpolated: bool
    warning: str


@dataclass(frozen=True)
class TemperatureCapabilityResult:
    material: str
    temperature_C: float
    analysis_mode: str
    mean_stress_correction: str
    capability: str
    condition_compatibility: str
    required_properties: list[ResolvedProperty]
    resolved_properties: list[str]
    unresolved_properties: list[str]
    static_condition: str
    fatigue_condition: str
    summary: str
    warnings: list[str]


def assess_temperature_capability(
    material,
    temperature_C,
    analysis_mode,
    mean_stress_correction,
    static_rows,
    fatigue_rows,
    static_condition=None,
    fatigue_condition=None,
):
    """Assess whether a requested fatigue calculation is temperature-resolved."""
    mode = _normalize_mode(analysis_mode)
    correction = _normalize_correction(mean_stress_correction)
    key = (mode, correction)
    if key not in REQUIRED_PROPERTIES:
        return _invalid_request_result(
            material,
            temperature_C,
            mode,
            correction,
            f"Unsupported analysis mode / mean stress correction combination: {mode} / {correction}.",
        )

    required = REQUIRED_PROPERTIES[key]
    resolved = []
    warnings = []

    for property_name in required["static"]:
        resolved.append(
            _resolve_property(
                static_rows,
                material,
                property_name,
                temperature_C,
                static_condition,
                "static",
            )
        )

    for property_name in required["fatigue"]:
        resolved.append(
            _resolve_property(
                fatigue_rows,
                material,
                property_name,
                temperature_C,
                fatigue_condition,
                "fatigue",
            )
        )

    resolved_names = [
        item.property_name for item in resolved if item.status in AVAILABLE_STATUSES
    ]
    unresolved_names = [
        item.property_name for item in resolved if item.status not in AVAILABLE_STATUSES
    ]

    for item in resolved:
        if item.warning:
            warnings.append(f"{item.property_name}: {item.warning}")

    actual_static_condition = _first_condition(resolved, "static") or static_condition or ""
    actual_fatigue_condition = _first_condition(resolved, "fatigue") or fatigue_condition or ""
    condition_compatibility = _condition_compatibility(
        actual_static_condition,
        actual_fatigue_condition,
        needs_static=bool(required["static"]),
        needs_fatigue=bool(required["fatigue"]),
    )

    static_available = _all_group_available(resolved, "static")
    fatigue_available = _all_group_available(resolved, "fatigue")
    all_required_available = not unresolved_names

    if all_required_available and condition_compatibility in {MATCH, UNKNOWN}:
        capability = FULLY_TEMPERATURE_RESOLVED
    elif all_required_available and condition_compatibility in {PARTIAL_MATCH, MISMATCH}:
        capability = PARTIALLY_TEMPERATURE_INFORMED
        warnings.append(
            "All required properties were resolved, but static and fatigue conditions are not fully compatible."
        )
    elif _has_any_available_group(resolved, "static") and not fatigue_available:
        capability = PARTIALLY_TEMPERATURE_INFORMED
        warnings.append(
            "Some temperature-resolved static properties are available, but required fatigue constants are not fully resolved."
        )
    elif _has_any_available_group(resolved, "fatigue") and required["static"] and not static_available:
        capability = UNAVAILABLE
        warnings.append(
            "Required fatigue constants are available, but required static properties are unavailable."
        )
    else:
        capability = UNAVAILABLE

    summary = _build_summary(
        material,
        temperature_C,
        mode,
        correction,
        capability,
        condition_compatibility,
        resolved_names,
        unresolved_names,
    )

    return TemperatureCapabilityResult(
        material=material,
        temperature_C=float(temperature_C),
        analysis_mode=mode,
        mean_stress_correction=correction,
        capability=capability,
        condition_compatibility=condition_compatibility,
        required_properties=resolved,
        resolved_properties=resolved_names,
        unresolved_properties=unresolved_names,
        static_condition=actual_static_condition,
        fatigue_condition=actual_fatigue_condition,
        summary=summary,
        warnings=warnings,
    )


def _resolve_property(rows, material, property_name, temperature_C, condition, group):
    result = get_property(rows, material, property_name, temperature_C, condition)
    return ResolvedProperty(
        property_name=property_name,
        property_group=group,
        value=result.value,
        status=result.status,
        source=result.source,
        condition=result.condition,
        basis=result.basis,
        interpolated=result.interpolated,
        warning=result.warning,
    )


def _condition_compatibility(static_condition, fatigue_condition, needs_static, needs_fatigue):
    if not needs_static or not needs_fatigue:
        return UNKNOWN
    if not static_condition or not fatigue_condition:
        return UNKNOWN

    static_norm = _normalize_condition(static_condition)
    fatigue_norm = _normalize_condition(fatigue_condition)
    if static_norm == fatigue_norm:
        return MATCH

    static_tokens = set(static_norm.split())
    fatigue_tokens = set(fatigue_norm.split())
    if _has_strong_condition_mismatch(static_tokens, fatigue_tokens):
        return MISMATCH

    shared = static_tokens & fatigue_tokens
    if not shared:
        return UNKNOWN

    alloy_tokens = {
        token
        for token in shared
        if token.isdigit()
        or token in {"alloy", "inconel", "haynes", "nickel", "aluminum", "steel", "stainless"}
    }
    if alloy_tokens:
        return PARTIAL_MATCH

    return UNKNOWN


def _has_strong_condition_mismatch(static_tokens, fatigue_tokens):
    static_text = " ".join(sorted(static_tokens))
    fatigue_text = " ".join(sorted(fatigue_tokens))

    if ("weld" in fatigue_text or "welded" in fatigue_text or "welding" in fatigue_text) and not (
        "weld" in static_text or "welded" in static_text or "welding" in static_text
    ):
        return True

    if ("316h" in fatigue_text and "316h" not in static_text) or (
        "316h" in static_text and "316h" not in fatigue_text
    ):
        return True

    heat_treatment_tokens = {
        "annealed",
        "mill",
        "solution",
        "aged",
        "age",
        "hardened",
        "normalized",
        "treated",
    }
    static_heat = static_tokens & heat_treatment_tokens
    fatigue_heat = fatigue_tokens & heat_treatment_tokens
    if static_heat and fatigue_heat and static_heat != fatigue_heat:
        return True

    return False


def _normalize_condition(condition):
    characters = []
    for character in condition.lower():
        if character.isalnum():
            characters.append(character)
        else:
            characters.append(" ")
    return " ".join("".join(characters).split())


def _normalize_mode(analysis_mode):
    value = str(analysis_mode).strip()
    if value in {"LCF", "Strain-Life / LCF"}:
        return "LCF"
    if value in {"HCF", "Stress-Life / HCF"}:
        return "HCF"
    return value


def _normalize_correction(mean_stress_correction):
    value = str(mean_stress_correction).strip()
    return value or "None"


def _all_group_available(resolved, group):
    group_items = [item for item in resolved if item.property_group == group]
    return bool(group_items) and all(item.status in AVAILABLE_STATUSES for item in group_items)


def _has_any_available_group(resolved, group):
    return any(
        item.property_group == group and item.status in AVAILABLE_STATUSES
        for item in resolved
    )


def _first_condition(resolved, group):
    for item in resolved:
        if item.property_group == group and item.condition:
            return item.condition
    return ""


def _build_summary(
    material,
    temperature_C,
    analysis_mode,
    correction,
    capability,
    condition_compatibility,
    resolved_names,
    unresolved_names,
):
    if capability == FULLY_TEMPERATURE_RESOLVED:
        return (
            f"All required {analysis_mode} / {correction} properties are available "
            f"and condition-compatible for {material} at {float(temperature_C):g} C."
        )

    if capability == PARTIALLY_TEMPERATURE_INFORMED:
        unresolved_text = ", ".join(unresolved_names) if unresolved_names else "none"
        return (
            f"{material} at {float(temperature_C):g} C is partially temperature-informed. "
            f"Condition compatibility: {condition_compatibility}. "
            f"Resolved: {', '.join(resolved_names) or 'none'}. "
            f"Unresolved: {unresolved_text}."
        )

    unresolved_text = ", ".join(unresolved_names) if unresolved_names else "requested properties"
    return (
        f"{analysis_mode} / {correction} temperature capability is unavailable for "
        f"{material} at {float(temperature_C):g} C. Unresolved: {unresolved_text}."
    )


def _invalid_request_result(material, temperature_C, analysis_mode, correction, warning):
    return TemperatureCapabilityResult(
        material=material,
        temperature_C=float(temperature_C),
        analysis_mode=analysis_mode,
        mean_stress_correction=correction,
        capability=UNAVAILABLE,
        condition_compatibility=UNKNOWN,
        required_properties=[],
        resolved_properties=[],
        unresolved_properties=[],
        static_condition="",
        fatigue_condition="",
        summary=warning,
        warnings=[warning],
    )
