import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox

from LCF_Life_Calculator import (
    LCFApp,
    LCF_LOCAL_CORRECTION_NEUBER,
    LCF_NEUBER_BASIS_DIRECT_KF,
    LCF_NEUBER_BASIS_KT_Q,
    LCF_NEUBER_BASIS_ORIGINAL_KT,
    SIMPLE_LCF_NEUBER_UNRESOLVED_REASON,
    STRESS_SOURCE_ELASTIC_PLASTIC_FEA,
    STRESS_SOURCE_LINEAR_FEA,
    STRESS_SOURCE_NOMINAL,
)


def make_window():
    app = QApplication.instance() or QApplication(sys.argv)
    return LCFApp()


def configure_lcf_window(
    window,
    *,
    source=STRESS_SOURCE_LINEAR_FEA,
    local_correction="None",
    basis=LCF_NEUBER_BASIS_ORIGINAL_KT,
    correction="None",
    sigma_max=500.0,
    sigma_min=100.0,
    k_t=None,
    q=None,
    k_f=None,
):
    window.analysis_mode_box.setCurrentText("Strain-Life / LCF")
    window.stress_source_box.setCurrentText(source)
    window.material_box.setCurrentText("Aluminum 2024-T3")
    window.analysis_temperature_input.setText("24")
    window.legacy_fallback_box.setChecked(True)
    window.local_correction_box.setCurrentText(local_correction)
    window.lcf_neuber_basis_box.setCurrentText(basis)
    window.mean_stress_box.setCurrentText(correction)
    if k_t is not None:
        window.lcf_kt_input.setText(str(k_t))
    if q is not None:
        window.lcf_q_input.setText(str(q))
    if k_f is not None:
        window.lcf_kf_input.setText(str(k_f))
    window.update_mean_stress_options("Strain-Life / LCF")
    window.update_stress_source_ui()
    window.update_lcf_local_correction_ui()
    window.refresh_correction_availability()
    window.sigma_max_input.setText(str(sigma_max))
    window.sigma_min_input.setText(str(sigma_min))


def run_lcf_case(window, **kwargs):
    configure_lcf_window(window, **kwargs)
    window.calculate_life()


def test_solver_returns_finite_positive_values():
    window = make_window()
    result = window.solve_neuber_local_response(400.0, 70000.0, 1000.0, 0.2)
    assert result is not None
    assert result["sigma_a_local"] > 0
    assert result["epsilon_a_local"] > 0
    assert result["epsilon_a_elastic"] > 0
    assert result["epsilon_a_plastic"] > 0


def test_neuber_product_and_range_amplitude_equivalence():
    window = make_window()
    sigma_elastic_ref = 400.0
    E = 70000.0
    result = window.solve_neuber_local_response(sigma_elastic_ref, E, 1000.0, 0.2)
    assert result is not None
    lhs = result["sigma_a_local"] * result["epsilon_a_local"]
    rhs = (sigma_elastic_ref ** 2) / E
    assert abs(lhs - rhs) <= max(1e-10, 1e-8 * rhs)

    delta_sigma = 2.0 * result["sigma_a_local"]
    delta_epsilon = 2.0 * result["epsilon_a_local"]
    delta_s = 2.0 * sigma_elastic_ref
    assert abs(delta_sigma * delta_epsilon - (delta_s ** 2) / E) <= max(1e-10, 1e-8 * (delta_s ** 2) / E)


def test_total_strain_equals_elastic_plus_plastic():
    window = make_window()
    result = window.solve_neuber_local_response(350.0, 70000.0, 1000.0, 0.2)
    assert result is not None
    total = result["epsilon_a_elastic"] + result["epsilon_a_plastic"]
    assert abs(result["epsilon_a_local"] - total) <= 1e-12


def test_original_kt_path_uses_kt():
    window = make_window()
    configure_lcf_window(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_ORIGINAL_KT,
        k_t=2.5,
    )
    state = window.resolve_lcf_neuber_state(500.0, 100.0)
    assert state["active"]
    assert state["valid"]
    assert state["basis_code"] == "ORIGINAL_NEUBER_KT"
    assert abs(state["sigma_elastic_ref"] - 500.0) <= 1e-12


def test_direct_kf_path_uses_kf():
    window = make_window()
    configure_lcf_window(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_DIRECT_KF,
        k_f=2.25,
    )
    state = window.resolve_lcf_neuber_state(500.0, 100.0)
    assert state["active"]
    assert state["valid"]
    assert state["basis_code"] == "FATIGUE_MODIFIED_NEUBER_KF"
    assert abs(state["sigma_elastic_ref"] - 450.0) <= 1e-12


def test_kt_plus_q_derives_kf():
    window = make_window()
    configure_lcf_window(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_KT_Q,
        k_t=3.0,
        q=0.5,
    )
    state = window.resolve_lcf_neuber_state(500.0, 100.0)
    assert state["valid"]
    assert abs(state["k_f"] - 2.0) <= 1e-12
    assert abs(state["sigma_elastic_ref"] - 400.0) <= 1e-12


def test_q_boundaries_are_enforced():
    window = make_window()
    configure_lcf_window(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_KT_Q,
        k_t=3.0,
        q=0.0,
    )
    state = window.resolve_lcf_neuber_state(500.0, 100.0)
    assert state["valid"]
    assert abs(state["k_f"] - 1.0) <= 1e-12

    configure_lcf_window(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_KT_Q,
        k_t=3.0,
        q=1.0,
    )
    state = window.resolve_lcf_neuber_state(500.0, 100.0)
    assert state["valid"]
    assert abs(state["k_f"] - 3.0) <= 1e-12

    configure_lcf_window(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_KT_Q,
        k_t=3.0,
        q=1.2,
    )
    state = window.resolve_lcf_neuber_state(500.0, 100.0)
    assert not state["valid"]


def test_invalid_inputs_are_rejected():
    window = make_window()

    configure_lcf_window(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_ORIGINAL_KT,
        k_t=0.9,
    )
    assert not window.resolve_lcf_neuber_state(500.0, 100.0)["valid"]

    configure_lcf_window(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_DIRECT_KF,
        k_f=0.9,
    )
    assert not window.resolve_lcf_neuber_state(500.0, 100.0)["valid"]

    configure_lcf_window(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_KT_Q,
        k_t=3.0,
        q=-0.1,
    )
    assert not window.resolve_lcf_neuber_state(500.0, 100.0)["valid"]


def test_zero_reference_returns_zero_local_response():
    window = make_window()
    result = window.solve_neuber_local_response(0.0, 70000.0, 1000.0, 0.2)
    assert result is not None
    assert result["sigma_a_local"] == 0.0
    assert result["epsilon_a_local"] == 0.0


def test_missing_cyclic_properties_block_neuber():
    window = make_window()
    material = "Aluminum 2024-T3"
    saved_k = window.materials[material]["K_dash"]
    try:
        window.materials[material]["K_dash"] = None
        configure_lcf_window(
            window,
            source=STRESS_SOURCE_LINEAR_FEA,
            local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        )
        window.calculate_life()
        text = window.result_text.toPlainText()
        assert "Neuber correction requires finite material properties" in text or "could not be bracketed" in text
    finally:
        window.materials[material]["K_dash"] = saved_k


def test_linear_fea_path_does_not_reapply_kt_or_kf():
    window = make_window()
    run_lcf_case(
        window,
        source=STRESS_SOURCE_LINEAR_FEA,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
    )
    text = window.result_text.toPlainText()
    assert "Neuber Status: ACTIVE" in text
    assert "ANSYS local elastic stress is used directly as the Neuber pseudo-elastic reference" in text
    assert "K_t:" not in text or "K_f:" not in text


def test_elastic_plastic_fea_bypasses_neuber_controls():
    window = make_window()
    configure_lcf_window(
        window,
        source=STRESS_SOURCE_ELASTIC_PLASTIC_FEA,
        local_correction="None",
    )
    assert window.local_correction_box.isHidden()
    assert window.lcf_neuber_group.isHidden()


def test_neuber_none_result_is_available():
    window = make_window()
    run_lcf_case(
        window,
        source=STRESS_SOURCE_LINEAR_FEA,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        sigma_max=500.0,
        sigma_min=100.0,
    )
    text = window.result_text.toPlainText()
    assert "Neuber Status: ACTIVE" in text
    assert "LCF Model: None" in text
    assert "Estimated Life (cycles)" in text
    assert window.tabs.currentIndex() == 1


def test_nominal_neuber_result_mentions_factor_basis():
    window = make_window()
    run_lcf_case(
        window,
        source=STRESS_SOURCE_NOMINAL,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
        basis=LCF_NEUBER_BASIS_KT_Q,
        k_t=3.0,
        q=0.5,
    )
    text = window.result_text.toPlainText()
    assert "Neuber Factor Basis: Fatigue-modified Neuber: K_t + q" in text
    assert "K_f: 2" in text
    assert "Local total strain amplitude" in text


def test_morrow_walker_swt_unavailable_under_neuber():
    window = make_window()
    configure_lcf_window(
        window,
        source=STRESS_SOURCE_LINEAR_FEA,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
    )
    availability = window.get_available_corrections(
        window.material_box.currentText(),
        window.parse_temperature(),
        "LCF",
        window.legacy_fallback_box.isChecked(),
        window.estimated_walker_box.isChecked(),
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
    assert SIMPLE_LCF_NEUBER_UNRESOLVED_REASON in availability["Morrow"].reason


def test_model_comparison_respects_neuber_availability():
    window = make_window()
    configure_lcf_window(
        window,
        source=STRESS_SOURCE_LINEAR_FEA,
        local_correction=LCF_LOCAL_CORRECTION_NEUBER,
    )
    window.compare_applicable_models()
    text = window.result_text.toPlainText()
    assert "MODEL COMPARISON" in text
    assert "Morrow" in text
    assert "Walker" in text
    assert "SWT" in text
    assert SIMPLE_LCF_NEUBER_UNRESOLVED_REASON in text


def test_existing_lcf_none_behavior_still_runs():
    window = make_window()
    run_lcf_case(
        window,
        source=STRESS_SOURCE_LINEAR_FEA,
        local_correction="None",
    )
    text = window.result_text.toPlainText()
    assert "LCF Model: None" not in text
    assert "Estimated Life (cycles)" in text
    assert "Neuber Status: ACTIVE" not in text


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    _ = app
    test_solver_returns_finite_positive_values()
    test_neuber_product_and_range_amplitude_equivalence()
    test_total_strain_equals_elastic_plus_plastic()
    test_original_kt_path_uses_kt()
    test_direct_kf_path_uses_kf()
    test_kt_plus_q_derives_kf()
    test_q_boundaries_are_enforced()
    test_invalid_inputs_are_rejected()
    test_zero_reference_returns_zero_local_response()
    test_missing_cyclic_properties_block_neuber()
    test_linear_fea_path_does_not_reapply_kt_or_kf()
    test_elastic_plastic_fea_bypasses_neuber_controls()
    test_neuber_none_result_is_available()
    test_nominal_neuber_result_mentions_factor_basis()
    test_morrow_walker_swt_unavailable_under_neuber()
    test_model_comparison_respects_neuber_availability()
    test_existing_lcf_none_behavior_still_runs()
    print("test_lcf_neuber.py PASSED")
