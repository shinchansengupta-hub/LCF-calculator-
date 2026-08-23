import math
import os
import re
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

    test_swt_tensile_mean_stress_case(window)
    test_swt_fully_reversed_case(window)
    test_swt_positive_mean_stress_reduces_life(window)
    test_swt_sigma_max_nonpositive_blocked(window)
    test_swt_fallback_off_disables_method(window)
    test_swt_fallback_on_enables_method(window)
    test_swt_no_silent_fallback(window)
    test_swt_no_extrapolation(window)
    test_swt_auto_reset_when_unavailable(window)
    test_morrow_regression(window)
    test_walker_regression(window)
    test_goodman_regression(window)
    test_lcf_none_regression(window)
    test_hcf_regression(window)
    test_dynamic_availability_regression(window)

    print("test_swt.py PASSED")


def test_swt_tensile_mean_stress_case(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        correction="SWT",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Smith-Watson-Topper strain-life estimate." in text
    corrected = parse_life(text, "SWT-Corrected LCF Life (cycles)")
    uncorrected = parse_life(text, "Uncorrected Life (cycles)")
    assert corrected is not None and corrected > 0
    assert uncorrected is not None and uncorrected > 0
    assert corrected < uncorrected


def test_swt_fully_reversed_case(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        correction="SWT",
        temperature=24,
        sigma_max=200,
        sigma_min=-200,
        legacy=True,
        estimated=False,
    )
    corrected = parse_life(text, "SWT-Corrected LCF Life (cycles)")
    assert corrected is not None and corrected > 0
    assert "Mean Stress (MPa): 0" in text or "Mean Stress (MPa): 0.0" in text


def test_swt_positive_mean_stress_reduces_life(window):
    reversed_text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        correction="SWT",
        temperature=24,
        sigma_max=200,
        sigma_min=-200,
        legacy=True,
        estimated=False,
    )
    tensile_text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        correction="SWT",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    reversed_life = parse_life(reversed_text, "SWT-Corrected LCF Life (cycles)")
    tensile_life = parse_life(tensile_text, "SWT-Corrected LCF Life (cycles)")
    assert reversed_life is not None and tensile_life is not None
    assert tensile_life < reversed_life


def test_swt_sigma_max_nonpositive_blocked(window):
    warnings_seen.clear()
    run_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        correction="SWT",
        temperature=24,
        sigma_max=-100,
        sigma_min=-500,
        legacy=True,
        estimated=False,
    )
    assert any(
        title == "SWT Domain Not Supported"
        and "positive maximum cycle stress" in message
        for title, message in warnings_seen
    )


def test_swt_fallback_off_disables_method(window):
    avail = window.get_available_corrections(
        "Aluminum 2024-T3",
        24,
        "LCF",
        False,
        False,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
    )
    assert not avail["SWT"].enabled
    assert avail["SWT"].availability_type == "UNAVAILABLE"


def test_swt_fallback_on_enables_method(window):
    avail = window.get_available_corrections(
        "Aluminum 2024-T3",
        24,
        "LCF",
        True,
        False,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
    )
    assert avail["SWT"].enabled
    assert avail["SWT"].availability_type == "LEGACY_FALLBACK_REQUIRED"


def test_swt_no_silent_fallback(window):
    avail = window.get_available_corrections(
        "High-Temp Alloy",
        24,
        "LCF",
        False,
        False,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
    )
    assert not avail["SWT"].enabled


def test_swt_no_extrapolation(window):
    static_rows = [
        {
            "Material": "Synthetic SWT Material",
            "material_condition": "Condition A",
            "Temperature_C": "25",
            "E_MPa": "200000",
            "property_source": "Synthetic static source",
            "property_basis": "Synthetic test data",
            "interpolation_allowed": "No",
        }
    ]
    fatigue_rows = [
        {
            "Material": "Synthetic SWT Material",
            "material_condition": "Condition A",
            "Temperature_C": "25",
            "K_dash": "1000",
            "n_dash": "0.12",
            "sigma_f_dash": "1200",
            "b": "-0.09",
            "epsilon_f_dash": "0.08",
            "c": "-0.55",
            "property_source": "Synthetic fatigue source",
            "property_basis": "Synthetic test data",
            "interpolation_allowed": "No",
        }
    ]
    avail = window.get_available_corrections(
        "Synthetic SWT Material",
        100,
        "LCF",
        False,
        False,
        static_rows,
        fatigue_rows,
        [],
    )
    assert not avail["SWT"].enabled


def test_swt_auto_reset_when_unavailable(window):
    configure_window(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        temperature=24,
        legacy=True,
        estimated=False,
        correction="SWT",
    )
    assert window.mean_stress_box.currentText() == "SWT"
    window.legacy_fallback_box.setChecked(False)
    window.refresh_correction_availability()
    assert window.mean_stress_box.currentText() == "None"


def test_morrow_regression(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        correction="Morrow",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Morrow-Corrected Life (cycles)" in text


def test_walker_regression(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="HCF",
        correction="Walker",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=True,
    )
    assert "Walker-Corrected Life (cycles)" in text


def test_goodman_regression(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="HCF",
        correction="Goodman",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Goodman-Corrected Life (cycles)" in text


def test_lcf_none_regression(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        correction="None",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Estimated Life (cycles)" in text


def test_hcf_regression(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="HCF",
        correction="None",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Estimated Life (cycles)" in text


def test_dynamic_availability_regression(window):
    avail = window.get_available_corrections(
        "Aluminum 2024-T3",
        24,
        "LCF",
        True,
        False,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
    )
    assert avail["SWT"].enabled
    assert avail["Morrow"].enabled


def run_case(
    window,
    *,
    material,
    mode,
    correction,
    temperature,
    sigma_max,
    sigma_min,
    legacy,
    estimated,
):
    mode_label = normalize_mode_label(mode)
    warnings_seen.clear()
    window.material_box.setCurrentText(material)
    window.analysis_mode_box.setCurrentText(mode_label)
    window.update_mean_stress_options(mode_label)
    window.analysis_temperature_input.setText(str(temperature))
    window.legacy_fallback_box.setChecked(legacy)
    window.estimated_walker_box.setChecked(estimated)
    window.mean_stress_box.setCurrentText(correction)
    window.refresh_correction_availability()
    window.sigma_max_input.setText(str(sigma_max))
    window.sigma_min_input.setText(str(sigma_min))
    window.calculate_life()
    return window.result_text.toPlainText()


def configure_window(window, *, material, mode, temperature, legacy, estimated, correction):
    mode_label = normalize_mode_label(mode)
    window.material_box.setCurrentText(material)
    window.analysis_mode_box.setCurrentText(mode_label)
    window.update_mean_stress_options(mode_label)
    window.analysis_temperature_input.setText(str(temperature))
    window.legacy_fallback_box.setChecked(legacy)
    window.estimated_walker_box.setChecked(estimated)
    window.mean_stress_box.setCurrentText(correction)
    window.refresh_correction_availability()


def normalize_mode_label(mode):
    if mode == "LCF":
        return "Strain-Life / LCF"
    if mode == "HCF":
        return "Stress-Life / HCF"
    return mode


def parse_life(text, label):
    for line in text.splitlines():
        if line.startswith(f"{label}:"):
            value = line.split(":", 1)[1].strip()
            if value == "-":
                return None
            try:
                return float(value.replace(",", ""))
            except ValueError:
                return None
    return None


if __name__ == "__main__":
    main()
