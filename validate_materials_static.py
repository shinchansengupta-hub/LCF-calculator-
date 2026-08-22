import csv

from material_properties import get_property


DATA_FILE = "materials_static.csv"


CASES = [
    {
        "material": "Aluminum 2024-T3",
        "condition": "2024-T3",
        "exact": ("S_u_MPa", 24),
        "interpolation": ("S_u_MPa", 124.5),
        "e_check": ("E_MPa", 24, "EXACT"),
        "sy_check": ("S_y_MPa", 124.5, "INTERPOLATED"),
        "cte_check": ("mean_CTE_per_C", 200, "INTERPOLATED"),
        "range": ("S_u_MPa", 23, 372),
    },
    {
        "material": "Inconel 718",
        "condition": "HAYNES 718 plate, mill annealed + 1325F/8h furnace cool to 1150F/8h air cool",
        "exact": ("S_u_MPa", 21),
        "interpolation": ("S_u_MPa", 482.5),
        "e_check": ("E_MPa", 150, "INTERPOLATED"),
        "sy_check": ("S_y_MPa", 482.5, "INTERPOLATED"),
        "cte_check": ("mean_CTE_per_C", 150, "INTERPOLATED"),
        "range": ("S_u_MPa", 20, 983),
    },
    {
        "material": "Ti-6Al-4V",
        "condition": "TIMETAL 6-4 / ASTM Grade 5 sheet/plate annealed per ASTM B265",
        "exact": ("S_u_MPa", 21),
        "interpolation": None,
        "e_check": ("E_MPa", 21, "EXACT"),
        "sy_check": ("S_y_MPa", 21, "EXACT"),
        "cte_check": None,
        "range": ("S_u_MPa", 20, 22),
    },
    {
        "material": "Ti-6Al-4V",
        "condition": "Ti-6Al-4V, MaterialHub resonant test dataset",
        "exact": ("E_MPa", 24),
        "interpolation": ("E_MPa", 150),
        "e_check": ("E_MPa", 150, "INTERPOLATED"),
        "sy_check": None,
        "cte_check": ("mean_CTE_per_C", 150, "INTERPOLATED"),
        "range": ("E_MPa", 23, 401),
    },
    {
        "material": "Nickel 625",
        "condition": "HAYNES 625 hot-rolled plate, 1925F mill-annealed",
        "exact": ("S_u_MPa", 21),
        "interpolation": ("S_u_MPa", 482.5),
        "e_check": ("E_MPa", 150, "INTERPOLATED"),
        "sy_check": ("S_y_MPa", 482.5, "INTERPOLATED"),
        "cte_check": ("mean_CTE_per_C", 150, "INTERPOLATED"),
        "range": ("S_u_MPa", 20, 1094),
    },
    {
        "material": "316 Stainless Steel",
        "condition": "ATI 316 / UNS S31600, annealed elevated-properties dataset",
        "exact": ("S_u_MPa", 20),
        "interpolation": ("S_u_MPa", 150),
        "e_check": None,
        "sy_check": ("S_y_MPa", 150, "INTERPOLATED"),
        "cte_check": None,
        "range": ("S_u_MPa", 19, 872),
    },
    {
        "material": "316 Stainless Steel",
        "condition": "Generic 316 SS, PPPL thermal and structural property table",
        "exact": ("E_MPa", 26.85),
        "interpolation": ("E_MPa", 176.85),
        "e_check": ("E_MPa", 176.85, "INTERPOLATED"),
        "sy_check": None,
        "cte_check": ("mean_CTE_per_C", 176.85, "INTERPOLATED"),
        "range": ("E_MPa", 25, 627),
    },
    {
        "material": "Alloy Steel 4340",
        "condition": "AISI 4340, normalized, 25 mm round",
        "exact": ("S_u_MPa", 25),
        "interpolation": ("mean_CTE_per_C", 400),
        "e_check": ("E_MPa", 25, "EXACT"),
        "sy_check": ("S_y_MPa", 25, "EXACT"),
        "cte_check": ("mean_CTE_per_C", 400, "INTERPOLATED"),
        "range": ("mean_CTE_per_C", 200, 600),
    },
    {
        "material": "Aluminum 7075-T6",
        "condition": "7075-T6",
        "exact": ("S_u_MPa", 24),
        "interpolation": ("mean_CTE_per_C", 200),
        "e_check": ("E_MPa", 24, "EXACT"),
        "sy_check": ("S_y_MPa", 24, "EXACT"),
        "cte_check": ("mean_CTE_per_C", 200, "INTERPOLATED"),
        "range": ("mean_CTE_per_C", 50, 350),
    },
    {
        "material": "Haynes 230",
        "condition": "HAYNES 230 plate, solution annealed",
        "exact": ("S_u_MPa", 21),
        "interpolation": ("S_u_MPa", 593.5),
        "e_check": ("E_MPa", 150, "INTERPOLATED"),
        "sy_check": ("S_y_MPa", 593.5, "INTERPOLATED"),
        "cte_check": ("mean_CTE_per_C", 150, "INTERPOLATED"),
        "range": ("S_u_MPa", 20, 1094),
    },
    {
        "material": "Rene 41",
        "condition": "HAYNES R-41, age hardened 1400F/16h/air cool",
        "exact": ("S_u_MPa", 21),
        "interpolation": ("S_u_MPa", 315.5),
        "e_check": None,
        "sy_check": ("S_y_MPa", 315.5, "INTERPOLATED"),
        "cte_check": ("mean_CTE_per_C", 538, "EXACT"),
        "range": ("S_u_MPa", 20, 983),
    },
]


def load_rows():
    with open(DATA_FILE, newline="", encoding="utf-8-sig") as csvfile:
        rows = list(csv.DictReader(csvfile))
    for index, row in enumerate(rows, start=2):
        if row.get(None):
            raise AssertionError(f"CSV row {index} has extra fields: {row[None]}")
        missing = [key for key, value in row.items() if value is None]
        if missing:
            raise AssertionError(f"CSV row {index} has missing fields: {missing}")
    return rows


def require_status(result, expected_status, label):
    if result.status != expected_status:
        raise AssertionError(
            f"{label}: expected {expected_status}, got {result.status}: {result.warning}"
        )
    if expected_status in {"EXACT", "INTERPOLATED"}:
        if result.value is None:
            raise AssertionError(f"{label}: expected a finite value")
        if not result.source or not result.basis:
            raise AssertionError(f"{label}: missing traceability metadata")


def run_check(rows, case, key, label):
    check = case.get(key)
    if check is None:
        return "not available"
    property_name, temperature, expected_status = check
    result = get_property(
        rows,
        case["material"],
        property_name,
        temperature,
        condition=case["condition"],
    )
    require_status(result, expected_status, label)
    return f"{property_name}@{temperature:g}C={result.status}"


def main():
    rows = load_rows()
    print(f"Loaded {len(rows)} static property rows")
    for case in CASES:
        material = case["material"]
        condition = case["condition"]

        exact_property, exact_temperature = case["exact"]
        exact = get_property(
            rows, material, exact_property, exact_temperature, condition=condition
        )
        require_status(exact, "EXACT", f"{material} exact")

        interpolation_summary = "not available"
        if case["interpolation"] is not None:
            interp_property, interp_temperature = case["interpolation"]
            interp = get_property(
                rows, material, interp_property, interp_temperature, condition=condition
            )
            require_status(interp, "INTERPOLATED", f"{material} interpolation")
            interpolation_summary = f"{interp_property}@{interp_temperature:g}C"

        e_summary = run_check(rows, case, "e_check", f"{material} E check")
        sy_summary = run_check(rows, case, "sy_check", f"{material} S_y check")
        cte_summary = run_check(rows, case, "cte_check", f"{material} CTE check")

        range_property, below_temperature, above_temperature = case["range"]
        below = get_property(
            rows, material, range_property, below_temperature, condition=condition
        )
        above = get_property(
            rows, material, range_property, above_temperature, condition=condition
        )
        require_status(below, "OUT_OF_RANGE", f"{material} below range")
        require_status(above, "OUT_OF_RANGE", f"{material} above range")

        print(
            "PASS "
            f"{material} | condition={condition} | exact={exact_property}@{exact_temperature:g}C "
            f"| interpolation={interpolation_summary} | E={e_summary} "
            f"| S_y={sy_summary} | CTE={cte_summary} | out_of_range=OK"
        )

    print(f"{len(CASES)} material-condition validation cases passed")


if __name__ == "__main__":
    main()
