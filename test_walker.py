import math
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

    test_hcf_walker_r_minus_one_reduces_to_basquin(window)
    test_lcf_walker_r_minus_one_reduces_to_uncorrected(window)
    test_positive_mean_stress_reduces_hcf_life(window)
    test_gamma_half_swt_elastic_relation(window)
    test_missing_gamma_blocks_calibrated_walker(window)
    test_estimated_gamma_requires_opt_in(window)
    test_estimated_gamma_label(window)
    test_fully_compressive_cycle_blocked(window)
    test_out_of_temperature_gamma_blocked(window)
    test_goodman_regression(window)
    test_morrow_regression(window)
    test_hcf_none_regression(window)
    test_lcf_none_regression(window)

    print("test_walker.py PASSED")


def test_hcf_walker_r_minus_one_reduces_to_basquin(window):
    # Permanent regression guard: Walker must recover the uncorrected HCF
    # solution at R = -1.
    mat = window.materials["Aluminum 2024-T3"]
    sigma_max = 200.0
    sigma_min = -200.0
    sigma_a = abs(sigma_max - sigma_min) / 2.0
    gamma = 0.5
    sigma_eq = window.walker_equivalent_stress(sigma_max, sigma_a, gamma)
    uncorrected = window.calculate_basquin_life(sigma_a, mat["sigma_f_dash"], mat["b"])
    walker = window.calculate_basquin_life(sigma_eq, mat["sigma_f_dash"], mat["b"])
    assert close(sigma_eq, sigma_a)
    assert close(uncorrected[0], walker[0])


def test_lcf_walker_r_minus_one_reduces_to_uncorrected(window):
    # Permanent regression guard: Walker LCF must recover the existing
    # uncorrected strain-life solution at R = -1.
    mat = window.materials["Aluminum 2024-T3"]
    sigma_max = 200.0
    sigma_min = -200.0
    sigma_a = abs(sigma_max - sigma_min) / 2.0
    E = mat["E"]
    strain = sigma_a / E + (sigma_a / mat["K_dash"]) ** (1.0 / mat["n_dash"])
    uncorrected = window.solve_life(
        strain,
        E,
        mat["sigma_f_dash"],
        mat["b"],
        mat["epsilon_f_dash"],
        mat["c"],
    )

    def rhs(nf):
        return window.walker_lcf_rhs(
            nf,
            E,
            sigma_max,
            sigma_a,
            mat["sigma_f_dash"],
            mat["b"],
            mat["epsilon_f_dash"],
            mat["c"],
            0.5,
        )

    walker = window.solve_life_with_rhs(strain, rhs)
    assert close(uncorrected[0], walker[0], rel=2e-6)


def test_positive_mean_stress_reduces_hcf_life(window):
    mat = window.materials["Aluminum 2024-T3"]
    sigma_max = 500.0
    sigma_min = 100.0
    sigma_a = 200.0
    gamma = 0.5
    sigma_eq = window.walker_equivalent_stress(sigma_max, sigma_a, gamma)
    uncorrected = window.calculate_basquin_life(sigma_a, mat["sigma_f_dash"], mat["b"])
    walker = window.calculate_basquin_life(sigma_eq, mat["sigma_f_dash"], mat["b"])
    assert sigma_eq > sigma_a
    assert walker[0] < uncorrected[0]


def test_gamma_half_swt_elastic_relation(window):
    sigma_max = 500.0
    sigma_a = 200.0
    sigma_eq = window.walker_equivalent_stress(sigma_max, sigma_a, 0.5)
    assert close(sigma_eq * sigma_eq, sigma_max * sigma_a)


def test_missing_gamma_blocks_calibrated_walker(window):
    text = run_case(
        window,
        material="High-Temp Alloy",
        mode="Stress-Life / HCF",
        correction="Walker",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Walker gamma is unavailable at the selected temperature." in text


def test_estimated_gamma_requires_opt_in(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="Stress-Life / HCF",
        correction="Walker",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Estimated Walker gamma requires explicit opt-in." in text


def test_estimated_gamma_label(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="Stress-Life / HCF",
        correction="Walker",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=True,
    )
    assert "ESTIMATED WALKER PARAMETER" in text
    assert "Walker-Corrected Life" in text


def test_fully_compressive_cycle_blocked(window):
    warnings_seen.clear()
    run_case(
        window,
        material="Aluminum 2024-T3",
        mode="Stress-Life / HCF",
        correction="Walker",
        temperature=24,
        sigma_max=-100,
        sigma_min=-500,
        legacy=True,
        estimated=True,
    )
    assert any("Walker Domain Not Supported" in title for title, _ in warnings_seen)


def test_out_of_temperature_gamma_blocked(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="Stress-Life / HCF",
        correction="Walker",
        temperature=100,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=True,
    )
    assert "Walker gamma is unavailable at the selected temperature." in text


def test_goodman_regression(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="Stress-Life / HCF",
        correction="Goodman",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Goodman-Corrected Life" in text


def test_morrow_regression(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="Strain-Life / LCF",
        correction="Morrow",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Morrow-Corrected Life" in text


def test_hcf_none_regression(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="Stress-Life / HCF",
        correction="None",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Estimated Life" in text


def test_lcf_none_regression(window):
    text = run_case(
        window,
        material="Aluminum 2024-T3",
        mode="Strain-Life / LCF",
        correction="None",
        temperature=24,
        sigma_max=500,
        sigma_min=100,
        legacy=True,
        estimated=False,
    )
    assert "Estimated Life" in text


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
    warnings_seen.clear()
    window.material_box.setCurrentText(material)
    window.analysis_mode_box.setCurrentText(mode)
    window.update_mean_stress_options(mode)
    window.analysis_temperature_input.setText(str(temperature))
    window.sigma_max_input.setText(str(sigma_max))
    window.sigma_min_input.setText(str(sigma_min))
    window.legacy_fallback_box.setChecked(legacy)
    window.estimated_walker_box.setChecked(estimated)
    window.mean_stress_box.setCurrentText(correction)
    window.calculate_life()
    return window.result_text.toPlainText()


def close(first, second, rel=1e-9):
    return math.isclose(first, second, rel_tol=rel, abs_tol=1e-12)


if __name__ == "__main__":
    main()
