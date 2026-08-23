import math

from LCF_Life_Calculator import (
    LCF_LOCAL_CORRECTION_NEUBER,
    LCF_NEUBER_BASIS_KT_Q,
    LCF_NEUBER_BASIS_ORIGINAL_KT,
    STRESS_SOURCE_LINEAR_FEA,
    STRESS_SOURCE_NOMINAL,
)


CASES = [
    ("A", 800.0, 0.0, 400.0, 400.0, "0"),
    ("B", 800.0, 100.0, 350.0, 450.0, "0.125"),
    ("C", 0.0, -800.0, 400.0, -400.0, "undefined because sigma_max is zero"),
    ("D", -100.0, -800.0, 350.0, -450.0, "8"),
    ("E", -300.0, -800.0, 250.0, -550.0, "2.6666667"),
    ("F", 800.0, -800.0, 800.0, 0.0, "-1"),
]


def configure_lcf_linear_neuber(window, sigma_max, sigma_min, *, material="Aluminum 2024-T3", temperature="24"):
    window.analysis_mode_box.setCurrentText("Strain-Life / LCF")
    window.stress_source_box.setCurrentText(STRESS_SOURCE_LINEAR_FEA)
    window.material_box.setCurrentText(material)
    window.analysis_temperature_input.setText(str(temperature))
    window.legacy_fallback_box.setChecked(False)
    window.mean_stress_box.setCurrentText("None")
    window.local_correction_box.setCurrentText(LCF_LOCAL_CORRECTION_NEUBER)
    window.update_mean_stress_options("Strain-Life / LCF")
    window.update_stress_source_ui()
    window.update_lcf_local_correction_ui()
    window.refresh_correction_availability()
    window.sigma_max_input.setText(str(sigma_max))
    window.sigma_min_input.setText(str(sigma_min))


def configure_lcf_nominal_neuber(window, sigma_max, sigma_min, *, basis=LCF_NEUBER_BASIS_ORIGINAL_KT, k_t=None, q=None):
    window.analysis_mode_box.setCurrentText("Strain-Life / LCF")
    window.stress_source_box.setCurrentText(STRESS_SOURCE_NOMINAL)
    window.material_box.setCurrentText("Aluminum 2024-T3")
    window.analysis_temperature_input.setText("24")
    window.legacy_fallback_box.setChecked(True)
    window.mean_stress_box.setCurrentText("None")
    window.local_correction_box.setCurrentText(LCF_LOCAL_CORRECTION_NEUBER)
    window.lcf_neuber_basis_box.setCurrentText(basis)
    if k_t is not None:
        window.lcf_kt_input.setText(str(k_t))
    if q is not None:
        window.lcf_q_input.setText(str(q))
    window.update_mean_stress_options("Strain-Life / LCF")
    window.update_stress_source_ui()
    window.update_lcf_local_correction_ui()
    window.refresh_correction_availability()
    window.sigma_max_input.setText(str(sigma_max))
    window.sigma_min_input.setText(str(sigma_min))


def parse_value(text, label):
    for line in text.splitlines():
        if line.startswith(f"{label}:"):
            raw = line.split(":", 1)[1].strip().replace(",", "")
            if raw == "-" or not raw:
                return None
            try:
                return float(raw)
            except ValueError:
                return raw
    raise AssertionError(f"Missing line: {label}")


def test_inconel_718_partial_match_neuber_case(window):
    configure_lcf_linear_neuber(window, 800.0, 0.0, material="Inconel 718", temperature="537.85")
    window.calculate_life()
    text = window.result_text.toPlainText()

    assert "TEMPERATURE DATA UNAVAILABLE" not in text
    assert "Condition Compatibility: PARTIAL_MATCH" in text
    assert "Calculation Status: READY_WITH_CONDITION_WARNING" in text
    assert "Elastic pseudo-reference stress amplitude (MPa): 400" in text
    assert "Local Neuber stress amplitude" in text
    assert "Local total strain amplitude" in text
    assert "Estimated Life (cycles)" in text
    assert "Reversals to Failure (2Nf)" in text
    assert window.tabs.currentIndex() == 1


def test_invalid_sigma_order_is_rejected(window):
    configure_lcf_linear_neuber(window, -800.0, 0.0)
    window.calculate_life()
    text = window.result_text.toPlainText()

    assert "Calculation Status: BLOCKED - Invalid Input" in text
    assert "greater than or equal to minimum stress" in text


def test_signed_stress_cycle_matrix(window):
    for case_id, sigma_max, sigma_min, sigma_a, sigma_m, r_text in CASES:
        configure_lcf_linear_neuber(window, sigma_max, sigma_min)
        lines = window.build_input_interpretation_lines()
        joined = "\n".join(lines)
        assert f"Stress Amplitude, sigma_a (MPa): {sigma_a:,.6g}" in joined
        assert f"Mean Stress, sigma_m (MPa): {sigma_m:,.6g}" in joined
        if case_id == "C":
            assert "Stress Ratio, R: undefined because sigma_max is zero" in joined
        else:
            r_line = next(line for line in lines if line.startswith("Stress Ratio, R:"))
            r_value = float(r_line.split(":", 1)[1].strip())
            expected_r = sigma_min / sigma_max
            assert math.isclose(r_value, expected_r, rel_tol=1e-5, abs_tol=1e-5)


def test_scalar_neuber_amplitude_equivalence(window):
    configure_lcf_linear_neuber(window, 800.0, 0.0)
    a_state = window.resolve_lcf_neuber_state(800.0, 0.0)
    c_state = window.resolve_lcf_neuber_state(0.0, -800.0)
    a_result = window.solve_neuber_local_response(
        a_state["sigma_elastic_ref"],
        window.materials["Aluminum 2024-T3"]["E"],
        window.materials["Aluminum 2024-T3"]["K_dash"],
        window.materials["Aluminum 2024-T3"]["n_dash"],
    )
    c_result = window.solve_neuber_local_response(
        c_state["sigma_elastic_ref"],
        window.materials["Aluminum 2024-T3"]["E"],
        window.materials["Aluminum 2024-T3"]["K_dash"],
        window.materials["Aluminum 2024-T3"]["n_dash"],
    )

    assert math.isclose(a_state["sigma_elastic_ref"], c_state["sigma_elastic_ref"], rel_tol=0, abs_tol=1e-12)
    assert math.isclose(a_result["sigma_a_local"], c_result["sigma_a_local"], rel_tol=0, abs_tol=1e-12)
    assert math.isclose(a_result["epsilon_a_local"], c_result["epsilon_a_local"], rel_tol=0, abs_tol=1e-12)

    configure_lcf_linear_neuber(window, 800.0, 100.0)
    b_state = window.resolve_lcf_neuber_state(800.0, 100.0)
    d_state = window.resolve_lcf_neuber_state(-100.0, -800.0)
    b_result = window.solve_neuber_local_response(
        b_state["sigma_elastic_ref"],
        window.materials["Aluminum 2024-T3"]["E"],
        window.materials["Aluminum 2024-T3"]["K_dash"],
        window.materials["Aluminum 2024-T3"]["n_dash"],
    )
    d_result = window.solve_neuber_local_response(
        d_state["sigma_elastic_ref"],
        window.materials["Aluminum 2024-T3"]["E"],
        window.materials["Aluminum 2024-T3"]["K_dash"],
        window.materials["Aluminum 2024-T3"]["n_dash"],
    )

    assert math.isclose(b_state["sigma_elastic_ref"], d_state["sigma_elastic_ref"], rel_tol=0, abs_tol=1e-12)
    assert math.isclose(b_result["sigma_a_local"], d_result["sigma_a_local"], rel_tol=0, abs_tol=1e-12)
    assert math.isclose(b_result["epsilon_a_local"], d_result["epsilon_a_local"], rel_tol=0, abs_tol=1e-12)


def test_neuber_product_and_kn_equals_one_regression(window):
    configure_lcf_linear_neuber(window, 800.0, 0.0)
    state = window.resolve_lcf_neuber_state(800.0, 0.0)
    result = window.solve_neuber_local_response(
        state["sigma_elastic_ref"],
        window.materials["Aluminum 2024-T3"]["E"],
        window.materials["Aluminum 2024-T3"]["K_dash"],
        window.materials["Aluminum 2024-T3"]["n_dash"],
    )
    rhs = (state["sigma_elastic_ref"] ** 2) / window.materials["Aluminum 2024-T3"]["E"]
    lhs = result["sigma_a_local"] * result["epsilon_a_local"]
    assert math.isclose(lhs, rhs, rel_tol=1e-8, abs_tol=1e-10)

    configure_lcf_nominal_neuber(window, 800.0, 0.0, basis=LCF_NEUBER_BASIS_ORIGINAL_KT, k_t=1.0)
    k1_state = window.resolve_lcf_neuber_state(800.0, 0.0)
    k1_result = window.solve_neuber_local_response(
        k1_state["sigma_elastic_ref"],
        window.materials["Aluminum 2024-T3"]["E"],
        window.materials["Aluminum 2024-T3"]["K_dash"],
        window.materials["Aluminum 2024-T3"]["n_dash"],
    )
    assert math.isclose(k1_state["sigma_elastic_ref"], 400.0, rel_tol=0, abs_tol=1e-12)
    assert not math.isclose(k1_result["sigma_a_local"], k1_state["sigma_elastic_ref"], rel_tol=0, abs_tol=1e-12)
    assert math.isclose(
        k1_result["sigma_a_local"] * k1_result["epsilon_a_local"],
        (k1_state["sigma_elastic_ref"] ** 2) / window.materials["Aluminum 2024-T3"]["E"],
        rel_tol=1e-8,
        abs_tol=1e-10,
    )


def test_nominal_kt_reference_amplitudes(window):
    expectations = [
        (800.0, 0.0, 800.0),
        (800.0, 100.0, 700.0),
        (0.0, -800.0, 800.0),
        (-100.0, -800.0, 700.0),
        (-300.0, -800.0, 500.0),
        (800.0, -800.0, 1600.0),
    ]
    for sigma_max, sigma_min, expected in expectations:
        configure_lcf_nominal_neuber(window, sigma_max, sigma_min, k_t=2.0)
        state = window.resolve_lcf_neuber_state(sigma_max, sigma_min)
        assert math.isclose(state["sigma_elastic_ref"], expected, rel_tol=0, abs_tol=1e-12)


def test_nominal_kt_trend(window):
    lives = []
    totals = []
    for k_t in (1.5, 2.0, 2.5):
        configure_lcf_nominal_neuber(window, 800.0, 0.0, k_t=k_t)
        state = window.resolve_lcf_neuber_state(800.0, 0.0)
        result = window.solve_neuber_local_response(
            state["sigma_elastic_ref"],
            window.materials["Aluminum 2024-T3"]["E"],
            window.materials["Aluminum 2024-T3"]["K_dash"],
            window.materials["Aluminum 2024-T3"]["n_dash"],
        )
        life = window.solve_life(
            result["epsilon_a_local"],
            window.materials["Aluminum 2024-T3"]["E"],
            window.materials["Aluminum 2024-T3"]["sigma_f_dash"],
            window.materials["Aluminum 2024-T3"]["b"],
            window.materials["Aluminum 2024-T3"]["epsilon_f_dash"],
            window.materials["Aluminum 2024-T3"]["c"],
        )[0]
        totals.append(result["epsilon_a_local"])
        lives.append(life)

    assert totals[0] < totals[1] < totals[2]
    assert lives[0] >= lives[1] >= lives[2]


def test_kt_plus_q_reference_amplitudes(window):
    cases = [
        (0.0, 400.0),
        (0.5, 600.0),
        (1.0, 800.0),
    ]
    for q, expected in cases:
        configure_lcf_nominal_neuber(window, 800.0, 0.0, basis=LCF_NEUBER_BASIS_KT_Q, k_t=2.0, q=q)
        state = window.resolve_lcf_neuber_state(800.0, 0.0)
        assert math.isclose(state["k_f"], 1.0 + q * (2.0 - 1.0), rel_tol=0, abs_tol=1e-12)
        assert math.isclose(state["sigma_elastic_ref"], expected, rel_tol=0, abs_tol=1e-12)


def test_scalar_neuber_non_neuber_models_unavailable(window):
    configure_lcf_linear_neuber(window, 800.0, 0.0, material="Inconel 718", temperature="537.85")
    availability = window.get_available_corrections(
        "Inconel 718",
        537.85,
        "LCF",
        False,
        False,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
        stress_source=STRESS_SOURCE_LINEAR_FEA,
        lcf_local_correction=LCF_LOCAL_CORRECTION_NEUBER,
    )
    assert availability["None"].enabled
    assert not availability["Morrow"].enabled
    assert not availability["Walker"].enabled
    assert not availability["SWT"].enabled


def test_fully_compressive_lcf_none_neuber_allowed(window):
    configure_lcf_linear_neuber(window, -100.0, -800.0, material="Inconel 718", temperature="537.85")
    window.calculate_life()
    text = window.result_text.toPlainText()

    assert "Neuber Status: ACTIVE" in text
    assert "TEMPERATURE DATA UNAVAILABLE" not in text
    assert "Walker Domain Not Supported" not in text


def test_dynamic_availability_partial_match_stays_enabled(window):
    window.material_box.setCurrentText("Inconel 718")
    window.analysis_mode_box.setCurrentText("Strain-Life / LCF")
    window.update_mean_stress_options("Strain-Life / LCF")
    window.analysis_temperature_input.setText("537.85")
    window.legacy_fallback_box.setChecked(False)
    window.estimated_walker_box.setChecked(False)
    window.mean_stress_box.setCurrentText("Morrow")
    window.refresh_correction_availability()

    availability = window.get_available_corrections(
        "Inconel 718",
        537.85,
        "LCF",
        False,
        False,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
    )
    assert availability["Morrow"].enabled
    assert availability["Morrow"].availability_type == "READY_WITH_CONDITION_WARNING"

    window.mean_stress_box.setCurrentText("Morrow")
    window.refresh_correction_availability()
    assert window.mean_stress_box.currentText() == "Morrow"
