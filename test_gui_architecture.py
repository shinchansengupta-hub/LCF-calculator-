import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox

from LCF_Life_Calculator import (
    LCFApp,
    STRESS_SOURCE_ELASTIC_PLASTIC_FEA,
    STRESS_SOURCE_LINEAR_FEA,
    STRESS_SOURCE_NOMINAL,
)


warnings_seen = []


def warning_stub(parent, title, message):
    warnings_seen.append((title, message))
    return QMessageBox.Ok


QMessageBox.warning = warning_stub


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = LCFApp()

    test_three_tabs_exist(window)
    test_input_results_graphs_separation(window)
    test_stress_source_selector_defaults_and_switches(window)
    test_linear_fea_hides_nominal_notch_controls(window)
    test_nominal_source_exposes_future_notch_section(window)
    test_goodman_walker_guidance_warns_against_von_mises(window)
    test_walker_specific_restriction_does_not_propagate_to_none(window)
    test_successful_calculation_populates_results_and_graphs(window)
    test_failed_calculation_clears_stale_graph(window)
    test_model_comparison_plot_uses_graphs_tab(window)

    print("test_gui_architecture.py PASSED")


def test_three_tabs_exist(window):
    assert window.tabs.count() == 3
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "Input",
        "Results",
        "Graphs",
    ]


def test_input_results_graphs_separation(window):
    assert window.tabs.indexOf(window.result_text) == -1
    assert window.result_text.isReadOnly()
    assert window.tabs.indexOf(window.plot_window) == -1
    assert window.plot_window.canvas is not None
    assert window.plot_window.ax is not None


def test_stress_source_selector_defaults_and_switches(window):
    assert window.stress_source_box.currentText() == STRESS_SOURCE_LINEAR_FEA
    assert [window.stress_source_box.itemText(i) for i in range(window.stress_source_box.count())] == [
        STRESS_SOURCE_LINEAR_FEA,
        STRESS_SOURCE_ELASTIC_PLASTIC_FEA,
        STRESS_SOURCE_NOMINAL,
    ]
    window.stress_source_box.setCurrentText(STRESS_SOURCE_ELASTIC_PLASTIC_FEA)
    assert not window.local_strain_input.isHidden()
    assert window.local_strain_input.isEnabled()


def test_linear_fea_hides_nominal_notch_controls(window):
    window.stress_source_box.setCurrentText(STRESS_SOURCE_LINEAR_FEA)
    assert window.notch_group.isHidden()
    assert window.kt_input.isEnabled() is False
    assert window.q_input.isEnabled() is False
    assert window.kf_input.isEnabled() is False


def test_nominal_source_exposes_future_notch_section(window):
    window.analysis_mode_box.setCurrentText("Stress-Life / HCF")
    window.stress_source_box.setCurrentText(STRESS_SOURCE_NOMINAL)
    assert not window.notch_group.isHidden()
    assert "not yet enabled" in window.notch_status_label.text()
    assert window.kt_input.isEnabled() is False
    assert window.q_input.isEnabled() is False
    assert window.kf_input.isEnabled() is False


def test_goodman_walker_guidance_warns_against_von_mises(window):
    configure_window(window, mode="Stress-Life / HCF", correction="Goodman")
    goodman_text = window.guidance_text.toPlainText()
    assert "von Mises" in goodman_text
    assert "sigma_m/R" in goodman_text

    configure_window(window, mode="Stress-Life / HCF", correction="Walker")
    walker_text = window.guidance_text.toPlainText()
    assert "von Mises" in walker_text
    assert "positive sigma_max" in walker_text


def test_walker_specific_restriction_does_not_propagate_to_none(window):
    configure_window(window, mode="Stress-Life / HCF", correction="None")
    text = window.guidance_text.toPlainText()
    assert "Walker requires a positive sigma_max" not in text
    assert "None: no Walker/SWT-specific positive sigma_max restriction" in text


def test_successful_calculation_populates_results_and_graphs(window):
    run_hcf_case(window, sigma_max=500, sigma_min=100)
    text = window.result_text.toPlainText()
    assert window.tabs.currentIndex() == 1
    assert "Stress Source Used: Local stress from linear-elastic FEA" in text
    assert "Estimated Life (cycles)" in text
    assert window.plot_window.ax.has_data()


def test_failed_calculation_clears_stale_graph(window):
    run_hcf_case(window, sigma_max=500, sigma_min=100)
    assert window.plot_window.ax.has_data()

    window.sigma_max_input.setText("100")
    window.sigma_min_input.setText("100")
    window.calculate_life()
    assert window.tabs.currentIndex() == 1
    assert not window.plot_window.ax.has_data()
    assert any(
        "No valid plot for the current calculation." in text.get_text()
        for text in window.plot_window.ax.texts
    )


def test_model_comparison_plot_uses_graphs_tab(window):
    run_hcf_case(window, sigma_max=500, sigma_min=100)
    window.compare_applicable_models()
    assert window.tabs.currentIndex() == 1
    assert "MODEL COMPARISON" in window.result_text.toPlainText()
    assert window.plot_window.ax.get_yscale() == "log"
    assert window.plot_window.ax.has_data()


def configure_window(window, *, mode, correction):
    window.stress_source_box.setCurrentText(STRESS_SOURCE_LINEAR_FEA)
    window.material_box.setCurrentText("Aluminum 2024-T3")
    window.analysis_mode_box.setCurrentText(mode)
    window.update_mean_stress_options(mode)
    window.analysis_temperature_input.setText("24")
    window.legacy_fallback_box.setChecked(True)
    window.estimated_walker_box.setChecked(True)
    window.mean_stress_box.setCurrentText(correction)
    window.refresh_correction_availability()


def run_hcf_case(window, *, sigma_max, sigma_min):
    warnings_seen.clear()
    configure_window(window, mode="Stress-Life / HCF", correction="None")
    window.sigma_max_input.setText(str(sigma_max))
    window.sigma_min_input.setText(str(sigma_min))
    window.calculate_life()


if __name__ == "__main__":
    main()
