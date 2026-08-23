import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox

from LCF_Life_Calculator import (
    LCFApp,
    NOTCH_TREATMENT_CONSERVATIVE_KT,
    NOTCH_TREATMENT_DIRECT_KF,
    NOTCH_TREATMENT_KT_Q,
    NOTCH_TREATMENT_NONE,
    STRESS_SOURCE_ELASTIC_PLASTIC_FEA,
    STRESS_SOURCE_LINEAR_FEA,
    STRESS_SOURCE_NOMINAL,
    WALKER_NOMINAL_NOTCH_UNRESOLVED_REASON,
)


warnings_seen = []


def warning_stub(parent, title, message):
    warnings_seen.append((title, message))
    return QMessageBox.Ok


QMessageBox.warning = warning_stub


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = LCFApp()

    test_no_notch_baseline_unchanged(window)
    test_direct_kf_scales_alternating_stress(window)
    test_kt_q_derives_kf(window)
    test_q_boundaries_and_validation(window)
    test_goodman_uses_kf_only_on_alternating_stress(window)
    test_pseudo_cycle_reconstruction_is_consistent(window)
    test_walker_disabled_for_nominal_notch(window)
    test_walker_available_for_local_fea(window)
    test_local_fea_hides_notch_controls(window)
    test_elastic_plastic_fea_hides_notch_controls(window)
    test_local_fea_does_not_apply_notch_factors(window)
    test_model_comparison_marks_nominal_notch_walker_unavailable(window)
    test_existing_basquin_goodman_walker_paths_still_run(window)
    test_correction_availability_updates(window)
    test_gui_architecture_still_passes(window)

    print("test_hcf_notch.py PASSED")


def configure_window(window, *, source, mode="Stress-Life / HCF", correction="None"):
    window.stress_source_box.setCurrentText(source)
    window.material_box.setCurrentText("Aluminum 2024-T3")
    window.analysis_mode_box.setCurrentText(mode)
    window.update_mean_stress_options(mode)
    window.analysis_temperature_input.setText("24")
    window.legacy_fallback_box.setChecked(True)
    window.estimated_walker_box.setChecked(True)
    window.mean_stress_box.setCurrentText(correction)
    window.refresh_correction_availability()


def set_nominal_notch(window, treatment, *, k_t=None, q=None, k_f=None):
    window.stress_source_box.setCurrentText(STRESS_SOURCE_NOMINAL)
    window.analysis_mode_box.setCurrentText("Stress-Life / HCF")
    window.update_mean_stress_options("Stress-Life / HCF")
    window.notch_treatment_box.setCurrentText(treatment)
    if k_t is not None:
        window.kt_input.setText(str(k_t))
    if q is not None:
        window.q_input.setText(str(q))
    if k_f is not None:
        window.kf_input.setText(str(k_f))
    window.refresh_correction_availability()


def run_hcf_case(window, *, source, correction="None", sigma_max=500, sigma_min=100):
    warnings_seen.clear()
    configure_window(window, source=source, correction=correction)
    window.sigma_max_input.setText(str(sigma_max))
    window.sigma_min_input.setText(str(sigma_min))
    window.calculate_life()


def test_no_notch_baseline_unchanged(window):
    set_nominal_notch(window, NOTCH_TREATMENT_NONE)
    state = window.resolve_hcf_notch_state(500.0, 100.0)
    assert not state["notch"]["active"]
    assert state["sigma_a_eff"] == state["sigma_a_nom"]
    assert state["sigma_m_eff"] == state["sigma_m_nom"]


def test_direct_kf_scales_alternating_stress(window):
    set_nominal_notch(window, NOTCH_TREATMENT_DIRECT_KF, k_f=2.5)
    state = window.resolve_hcf_notch_state(500.0, 100.0)
    assert state["notch"]["active"]
    assert abs(state["sigma_a_eff"] - 500.0) < 1e-12
    assert abs(state["sigma_m_eff"] - 300.0) < 1e-12


def test_kt_q_derives_kf(window):
    set_nominal_notch(window, NOTCH_TREATMENT_KT_Q, k_t=3.0, q=0.5)
    state = window.resolve_hcf_notch_state(500.0, 100.0)
    assert state["notch"]["valid"]
    assert abs(state["notch"]["k_f"] - 2.0) < 1e-12
    assert abs(state["sigma_a_eff"] - 400.0) < 1e-12


def test_q_boundaries_and_validation(window):
    set_nominal_notch(window, NOTCH_TREATMENT_KT_Q, k_t=3.0, q=0.0)
    state = window.resolve_hcf_notch_state(500.0, 100.0)
    assert state["notch"]["valid"]
    assert state["notch"]["k_f"] == 1.0

    set_nominal_notch(window, NOTCH_TREATMENT_KT_Q, k_t=3.0, q=1.0)
    state = window.resolve_hcf_notch_state(500.0, 100.0)
    assert state["notch"]["valid"]
    assert state["notch"]["k_f"] == 3.0

    set_nominal_notch(window, NOTCH_TREATMENT_KT_Q, k_t=3.0, q=1.2)
    state = window.resolve_hcf_notch_state(500.0, 100.0)
    assert not state["notch"]["valid"]


def test_goodman_uses_kf_only_on_alternating_stress(window):
    set_nominal_notch(window, NOTCH_TREATMENT_DIRECT_KF, k_f=2.0)
    state = window.resolve_hcf_notch_state(500.0, 100.0)
    assert state["sigma_a_nom"] == 200.0
    assert state["sigma_m_nom"] == 300.0
    assert state["sigma_a_eff"] == 400.0
    assert state["sigma_m_eff"] == 300.0


def test_pseudo_cycle_reconstruction_is_consistent(window):
    set_nominal_notch(window, NOTCH_TREATMENT_DIRECT_KF, k_f=2.0)
    state = window.resolve_hcf_notch_state(500.0, 100.0)
    assert state["pseudo_sigma_max"] == state["sigma_m_eff"] + state["sigma_a_eff"]
    assert state["pseudo_sigma_min"] == state["sigma_m_eff"] - state["sigma_a_eff"]
    if state["pseudo_sigma_max"] != 0:
        assert abs(state["pseudo_r"] - state["pseudo_sigma_min"] / state["pseudo_sigma_max"]) < 1e-12


def test_walker_disabled_for_nominal_notch(window):
    set_nominal_notch(window, NOTCH_TREATMENT_DIRECT_KF, k_f=2.0)
    availability = window.get_available_corrections(
        window.material_box.currentText(),
        window.parse_temperature(),
        "HCF",
        window.legacy_fallback_box.isChecked(),
        window.estimated_walker_box.isChecked(),
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
        stress_source=STRESS_SOURCE_NOMINAL,
    )
    assert not availability["Walker"].enabled
    assert WALKER_NOMINAL_NOTCH_UNRESOLVED_REASON in availability["Walker"].reason


def test_walker_available_for_local_fea(window):
    configure_window(window, source=STRESS_SOURCE_LINEAR_FEA, correction="Walker")
    availability = window.get_available_corrections(
        window.material_box.currentText(),
        window.parse_temperature(),
        "HCF",
        window.legacy_fallback_box.isChecked(),
        window.estimated_walker_box.isChecked(),
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
        stress_source=STRESS_SOURCE_LINEAR_FEA,
    )
    assert availability["Walker"].enabled
    assert availability["Walker"].availability_type in {
        "FULL",
        "LEGACY_FALLBACK_REQUIRED",
        "ESTIMATED_PARAMETER_REQUIRED",
    }


def test_local_fea_hides_notch_controls(window):
    configure_window(window, source=STRESS_SOURCE_LINEAR_FEA, correction="None")
    assert window.notch_group.isHidden()
    assert not window.kt_input.isEnabled()
    assert not window.q_input.isEnabled()
    assert not window.kf_input.isEnabled()


def test_elastic_plastic_fea_hides_notch_controls(window):
    configure_window(window, source=STRESS_SOURCE_ELASTIC_PLASTIC_FEA, correction="None")
    assert window.notch_group.isHidden()
    assert not window.kt_input.isEnabled()
    assert not window.q_input.isEnabled()
    assert not window.kf_input.isEnabled()


def test_local_fea_does_not_apply_notch_factors(window):
    run_hcf_case(window, source=STRESS_SOURCE_LINEAR_FEA, correction="None")
    text = window.result_text.toPlainText()
    assert "Notch Treatment:" not in text
    assert "Fatigue-Effective Stress Amplitude" in text


def test_model_comparison_marks_nominal_notch_walker_unavailable(window):
    set_nominal_notch(window, NOTCH_TREATMENT_DIRECT_KF, k_f=2.0)
    window.mean_stress_box.setCurrentText("None")
    window.refresh_correction_availability()
    run_hcf_case(window, source=STRESS_SOURCE_NOMINAL, correction="None")
    window.compare_applicable_models()
    comparison_text = window.result_text.toPlainText()
    assert "Walker" in comparison_text
    assert "unavailable" in comparison_text.lower() or WALKER_NOMINAL_NOTCH_UNRESOLVED_REASON in comparison_text


def test_existing_basquin_goodman_walker_paths_still_run(window):
    run_hcf_case(window, source=STRESS_SOURCE_LINEAR_FEA, correction="None")
    assert "Estimated Life (cycles)" in window.result_text.toPlainText()

    run_hcf_case(window, source=STRESS_SOURCE_LINEAR_FEA, correction="Goodman")
    assert "Goodman-Corrected Life (cycles)" in window.result_text.toPlainText()

    run_hcf_case(window, source=STRESS_SOURCE_LINEAR_FEA, correction="Walker")
    assert "Walker" in window.result_text.toPlainText()


def test_correction_availability_updates(window):
    configure_window(window, source=STRESS_SOURCE_NOMINAL, correction="None")
    set_nominal_notch(window, NOTCH_TREATMENT_DIRECT_KF, k_f=2.0)
    window.mean_stress_box.setCurrentText("Walker")
    window.refresh_correction_availability()
    assert window.mean_stress_box.currentText() == "None"


def test_gui_architecture_still_passes(window):
    assert window.tabs.count() == 3
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "Input",
        "Results",
        "Graphs",
    ]
    assert window.result_text.isReadOnly()
    assert window.plot_window.canvas is not None
    assert window.plot_window.ax is not None


if __name__ == "__main__":
    main()
