import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from LCF_Life_Calculator import (
    CorrectionAvailability,
    FULL_AVAILABILITY,
    LEGACY_FALLBACK_REQUIRED,
    ESTIMATED_PARAMETER_REQUIRED,
    UNAVAILABLE_CORRECTION,
    LCFApp,
)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = LCFApp()

    test_lcf_none_availability(window)
    test_lcf_morrow_availability(window)
    test_lcf_swt_availability(window)
    test_hcf_goodman_availability(window)
    test_walker_fitted_gamma(window)
    test_walker_estimated_gamma_off(window)
    test_walker_estimated_gamma_on(window)
    test_walker_missing_gamma(window)
    test_walker_out_of_range_gamma(window)
    test_mode_switch_invalidates_old_correction(window)
    test_material_switch_invalidates_old_correction(window)
    test_fallback_toggle_changes_availability(window)
    test_estimated_toggle_changes_availability(window)
    test_no_silent_su_fallback(window)
    test_no_silent_gamma_fallback(window)

    print("test_correction_availability.py PASSED")


def test_lcf_none_availability(window):
    avail = synthetic_case(
        window,
        material="Synthetic LCF Material",
        mode="LCF",
        temperature=25,
        legacy=False,
        estimated=False,
        static_rows=[static_row("Synthetic LCF Material", "Condition A", 25)],
        fatigue_rows=[fatigue_row("Synthetic LCF Material", "Condition A", 25)],
        walker_rows=[],
    )
    assert avail["None"].enabled
    assert avail["None"].availability_type == FULL_AVAILABILITY


def test_lcf_morrow_availability(window):
    full = synthetic_case(
        window,
        material="Synthetic LCF Material",
        mode="LCF",
        temperature=25,
        legacy=False,
        estimated=False,
        static_rows=[static_row("Synthetic LCF Material", "Condition A", 25)],
        fatigue_rows=[fatigue_row("Synthetic LCF Material", "Condition A", 25)],
        walker_rows=[],
    )
    assert full["Morrow"].enabled
    assert full["Morrow"].availability_type == FULL_AVAILABILITY

    legacy = synthetic_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        temperature=24,
        legacy=True,
        estimated=False,
    )
    assert legacy["Morrow"].enabled
    assert legacy["Morrow"].availability_type == LEGACY_FALLBACK_REQUIRED

    unavailable = synthetic_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        temperature=24,
        legacy=False,
        estimated=False,
    )
    assert not unavailable["Morrow"].enabled
    assert unavailable["Morrow"].availability_type == UNAVAILABLE_CORRECTION


def test_lcf_swt_availability(window):
    full = synthetic_case(
        window,
        material="Synthetic LCF Material",
        mode="LCF",
        temperature=25,
        legacy=False,
        estimated=False,
        static_rows=[static_row("Synthetic LCF Material", "Condition A", 25)],
        fatigue_rows=[fatigue_row("Synthetic LCF Material", "Condition A", 25)],
        walker_rows=[],
    )
    assert full["SWT"].enabled
    assert full["SWT"].availability_type == FULL_AVAILABILITY

    legacy = synthetic_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        temperature=24,
        legacy=True,
        estimated=False,
    )
    assert legacy["SWT"].enabled
    assert legacy["SWT"].availability_type == LEGACY_FALLBACK_REQUIRED

    unavailable = synthetic_case(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        temperature=24,
        legacy=False,
        estimated=False,
    )
    assert not unavailable["SWT"].enabled
    assert unavailable["SWT"].availability_type == UNAVAILABLE_CORRECTION


def test_hcf_goodman_availability(window):
    full = synthetic_case(
        window,
        material="Synthetic HCF Material",
        mode="HCF",
        temperature=25,
        legacy=False,
        estimated=False,
        static_rows=[static_row("Synthetic HCF Material", "Condition A", 25)],
        fatigue_rows=[fatigue_row("Synthetic HCF Material", "Condition A", 25)],
        walker_rows=[],
    )
    assert full["Goodman"].enabled
    assert full["Goodman"].availability_type == FULL_AVAILABILITY

    legacy = synthetic_case(
        window,
        material="Aluminum 2024-T3",
        mode="HCF",
        temperature=24,
        legacy=True,
        estimated=False,
    )
    assert legacy["Goodman"].enabled
    assert legacy["Goodman"].availability_type == LEGACY_FALLBACK_REQUIRED

    unavailable = synthetic_case(
        window,
        material="High-Temp Alloy",
        mode="HCF",
        temperature=24,
        legacy=True,
        estimated=False,
    )
    assert not unavailable["Goodman"].enabled
    assert unavailable["Goodman"].availability_type == UNAVAILABLE_CORRECTION


def test_walker_fitted_gamma(window):
    full = synthetic_case(
        window,
        material="Synthetic Walker Material",
        mode="HCF",
        temperature=25,
        legacy=False,
        estimated=False,
        static_rows=[static_row("Synthetic Walker Material", "Condition A", 25)],
        fatigue_rows=[fatigue_row("Synthetic Walker Material", "Condition A", 25)],
        walker_rows=[walker_row("Synthetic Walker Material", "Condition A", 25, 0.42, "FITTED")],
    )
    assert full["Walker"].enabled
    assert full["Walker"].availability_type == FULL_AVAILABILITY


def test_walker_estimated_gamma_off(window):
    avail = synthetic_case(
        window,
        material="Aluminum 2024-T3",
        mode="HCF",
        temperature=24,
        legacy=False,
        estimated=False,
    )
    assert not avail["Walker"].enabled
    assert avail["Walker"].availability_type == ESTIMATED_PARAMETER_REQUIRED


def test_walker_estimated_gamma_on(window):
    avail = synthetic_case(
        window,
        material="Aluminum 2024-T3",
        mode="HCF",
        temperature=24,
        legacy=False,
        estimated=True,
    )
    assert avail["Walker"].enabled
    assert avail["Walker"].availability_type == ESTIMATED_PARAMETER_REQUIRED


def test_walker_missing_gamma(window):
    avail = synthetic_case(
        window,
        material="High-Temp Alloy",
        mode="HCF",
        temperature=24,
        legacy=True,
        estimated=True,
    )
    assert not avail["Walker"].enabled
    assert avail["Walker"].availability_type == UNAVAILABLE_CORRECTION


def test_walker_out_of_range_gamma(window):
    avail = synthetic_case(
        window,
        material="Synthetic Walker Material",
        mode="HCF",
        temperature=100,
        legacy=False,
        estimated=True,
        static_rows=[static_row("Synthetic Walker Material", "Condition A", 25)],
        fatigue_rows=[fatigue_row("Synthetic Walker Material", "Condition A", 25)],
        walker_rows=[walker_row("Synthetic Walker Material", "Condition A", 25, 0.42, "FITTED")],
    )
    assert not avail["Walker"].enabled
    assert avail["Walker"].availability_type == UNAVAILABLE_CORRECTION


def test_mode_switch_invalidates_old_correction(window):
    configure_window(
        window,
        material="Aluminum 2024-T3",
        mode="LCF",
        temperature=24,
        legacy=True,
        estimated=True,
        correction="Morrow",
    )
    assert window.mean_stress_box.currentText() == "Morrow"
    window.analysis_mode_box.setCurrentText("Stress-Life / HCF")
    window.update_mean_stress_options("Stress-Life / HCF")
    window.refresh_correction_availability()
    assert window.mean_stress_box.currentText() == "None"


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


def test_material_switch_invalidates_old_correction(window):
    configure_window(
        window,
        material="Aluminum 2024-T3",
        mode="HCF",
        temperature=24,
        legacy=True,
        estimated=True,
        correction="Walker",
    )
    assert window.mean_stress_box.currentText() == "Walker"
    window.material_box.setCurrentText("High-Temp Alloy")
    window.refresh_correction_availability()
    assert window.mean_stress_box.currentText() == "None"


def test_fallback_toggle_changes_availability(window):
    window.material_box.setCurrentText("Aluminum 2024-T3")
    window.analysis_mode_box.setCurrentText("LCF")
    window.update_mean_stress_options("LCF")
    window.analysis_temperature_input.setText("24")
    window.estimated_walker_box.setChecked(False)
    window.legacy_fallback_box.setChecked(False)
    window.refresh_correction_availability()
    assert not window.get_available_corrections(
        "Aluminum 2024-T3",
        24,
        "LCF",
        False,
        False,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
    )["Morrow"].enabled

    window.legacy_fallback_box.setChecked(True)
    window.refresh_correction_availability()
    assert window.get_available_corrections(
        "Aluminum 2024-T3",
        24,
        "LCF",
        True,
        False,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
    )["Morrow"].enabled


def test_estimated_toggle_changes_availability(window):
    window.material_box.setCurrentText("Aluminum 2024-T3")
    window.analysis_mode_box.setCurrentText("HCF")
    window.update_mean_stress_options("HCF")
    window.analysis_temperature_input.setText("24")
    window.legacy_fallback_box.setChecked(False)
    window.estimated_walker_box.setChecked(False)
    window.refresh_correction_availability()
    assert not window.get_available_corrections(
        "Aluminum 2024-T3",
        24,
        "HCF",
        False,
        False,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
    )["Walker"].enabled

    window.estimated_walker_box.setChecked(True)
    window.refresh_correction_availability()
    assert window.get_available_corrections(
        "Aluminum 2024-T3",
        24,
        "HCF",
        False,
        True,
        window.static_rows,
        window.fatigue_rows,
        window.walker_rows,
    )["Walker"].enabled


def test_no_silent_su_fallback(window):
    avail = synthetic_case(
        window,
        material="High-Temp Alloy",
        mode="HCF",
        temperature=24,
        legacy=True,
        estimated=False,
    )
    assert not avail["Goodman"].enabled
    assert "S_u_MPa" in avail["Goodman"].reason or "S_u" in avail["Goodman"].reason


def test_no_silent_gamma_fallback(window):
    avail = synthetic_case(
        window,
        material="High-Temp Alloy",
        mode="HCF",
        temperature=24,
        legacy=True,
        estimated=True,
    )
    assert not avail["Walker"].enabled
    assert "gamma" in avail["Walker"].reason.lower()


def synthetic_case(
    window,
    *,
    material,
    mode,
    temperature,
    legacy,
    estimated,
    static_rows=None,
    fatigue_rows=None,
    walker_rows=None,
):
    static_rows = static_rows if static_rows is not None else window.static_rows
    fatigue_rows = fatigue_rows if fatigue_rows is not None else window.fatigue_rows
    walker_rows = walker_rows if walker_rows is not None else window.walker_rows
    return window.get_available_corrections(
        material,
        temperature,
        mode,
        legacy,
        estimated,
        static_rows,
        fatigue_rows,
        walker_rows,
    )


def configure_window(window, *, material, mode, temperature, legacy, estimated, correction):
    window.material_box.setCurrentText(material)
    window.analysis_mode_box.setCurrentText(mode)
    window.update_mean_stress_options(mode)
    window.analysis_temperature_input.setText(str(temperature))
    window.legacy_fallback_box.setChecked(legacy)
    window.estimated_walker_box.setChecked(estimated)
    window.mean_stress_box.setCurrentText(correction)
    window.refresh_correction_availability()


def static_row(material, condition, temperature):
    return {
        "Material": material,
        "material_condition": condition,
        "Temperature_C": str(temperature),
        "E_MPa": "200000",
        "S_u_MPa": "900",
        "property_source": "Synthetic static source",
        "property_basis": "Synthetic test data",
        "interpolation_allowed": "Yes",
    }


def fatigue_row(material, condition, temperature):
    return {
        "Material": material,
        "material_condition": condition,
        "Temperature_C": str(temperature),
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


def walker_row(material, condition, temperature, gamma, basis):
    return {
        "Material": material,
        "material_condition": condition,
        "Temperature_C": str(temperature),
        "Walker_gamma": str(gamma),
        "property_source": "Synthetic walker source",
        "property_basis": basis,
        "interpolation_allowed": "No",
    }


if __name__ == "__main__":
    main()
