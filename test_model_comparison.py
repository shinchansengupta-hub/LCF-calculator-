import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox

from LCF_Life_Calculator import LCFApp


warnings_seen = []


def warning_stub(parent, title, message):
    warnings_seen.append((title, message))
    return QMessageBox.Ok


QMessageBox.warning = warning_stub


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = LCFApp()

    test_lcf_comparison_includes_all_models(window)
    test_hcf_comparison_includes_all_models(window)
    test_unavailable_model_remains_listed(window)
    test_legacy_and_estimated_statuses_preserved(window)
    test_no_recommendation_language(window)
    test_lowest_life_descriptive_only(window)
    test_comparison_plot_uses_predicted_lives(window)

    print("test_model_comparison.py PASSED")


def test_lcf_comparison_includes_all_models(window):
    summary, text = run_comparison(
        window,
        material="Aluminum 2024-T3",
        mode="Strain-Life / LCF",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=True,
    )
    assert [result.model_name for result in summary.model_results] == ["None", "Morrow", "Walker", "SWT"]
    assert "MODEL COMPARISON" in text


def test_hcf_comparison_includes_all_models(window):
    summary, text = run_comparison(
        window,
        material="Aluminum 2024-T3",
        mode="Stress-Life / HCF",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=True,
    )
    assert [result.model_name for result in summary.model_results] == ["None", "Goodman", "Walker"]
    assert "MODEL COMPARISON" in text


def test_unavailable_model_remains_listed(window):
    summary, text = run_comparison(
        window,
        material="High-Temp Alloy",
        mode="Stress-Life / HCF",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=False,
        estimated=False,
    )
    goodman = next(result for result in summary.model_results if result.model_name == "Goodman")
    assert goodman.status == "UNAVAILABLE"
    assert "S_u" in goodman.reason or "S_u_MPa" in goodman.reason
    assert "UNAVAILABLE" in text


def test_legacy_and_estimated_statuses_preserved(window):
    summary, _ = run_comparison(
        window,
        material="Aluminum 2024-T3",
        mode="Strain-Life / LCF",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=True,
    )
    none_result = next(result for result in summary.model_results if result.model_name == "None")
    walker_result = next(result for result in summary.model_results if result.model_name == "Walker")
    assert none_result.legacy_fallback_used
    assert none_result.availability in {"AVAILABLE_PARTIAL", "AVAILABLE_LEGACY"}
    assert walker_result.estimated_parameter_used
    assert walker_result.availability == "AVAILABLE_ESTIMATED"


def test_no_recommendation_language(window):
    _, text = run_comparison(
        window,
        material="Aluminum 2024-T3",
        mode="Strain-Life / LCF",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=True,
    )
    assert "RECOMMENDED" not in text
    assert "BEST" not in text


def test_lowest_life_descriptive_only(window):
    _, text = run_comparison(
        window,
        material="Aluminum 2024-T3",
        mode="Strain-Life / LCF",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=True,
    )
    assert "Lowest predicted life:" in text
    assert "not automatically the preferred" in text


def test_comparison_plot_uses_predicted_lives(window):
    summary, _ = run_comparison(
        window,
        material="Aluminum 2024-T3",
        mode="Strain-Life / LCF",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=True,
    )
    assert window.plot_window is not None
    assert window.plot_window.ax.get_yscale() == "log"

    available = [result for result in summary.model_results if result.predicted_life_cycles is not None]
    offsets = window.plot_window.ax.collections[0].get_offsets()
    plotted_lives = sorted(float(point[1]) for point in offsets)
    expected_lives = sorted(float(result.predicted_life_cycles) for result in available)
    assert len(plotted_lives) == len(expected_lives)
    for plotted, expected in zip(plotted_lives, expected_lives):
        assert abs(plotted - expected) / expected < 1e-9


def run_comparison(window, *, material, mode, temperature, sigma_max, sigma_min, legacy, estimated):
    warnings_seen.clear()
    window.material_box.setCurrentText(material)
    window.analysis_mode_box.setCurrentText(mode)
    window.update_mean_stress_options(mode)
    window.analysis_temperature_input.setText(str(temperature))
    window.sigma_max_input.setText(str(sigma_max))
    window.sigma_min_input.setText(str(sigma_min))
    window.legacy_fallback_box.setChecked(legacy)
    window.estimated_walker_box.setChecked(estimated)
    window.compare_applicable_models()
    return window.last_comparison_result, window.result_text.toPlainText()


if __name__ == "__main__":
    main()
