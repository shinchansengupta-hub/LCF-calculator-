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


def run_case(window, *, material, mode, correction, temperature, sigma_max, sigma_min, legacy):
    warnings_seen.clear()
    window.material_box.setCurrentText(material)
    window.analysis_mode_box.setCurrentText(mode)
    window.update_mean_stress_options(mode)
    window.mean_stress_box.setCurrentText(correction)
    window.analysis_temperature_input.setText(str(temperature))
    window.sigma_max_input.setText(str(sigma_max))
    window.sigma_min_input.setText(str(sigma_min))
    window.legacy_fallback_box.setChecked(legacy)
    window.calculate_life()
    return window.result_label.text(), list(warnings_seen), window.ax.get_title()


def require_contains(text, fragment, label):
    if fragment not in text:
        raise AssertionError(f"{label} missing fragment: {fragment}\n{text}")


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = LCFApp()

    cases = [
        (
            "A. Inconel 718 exact fatigue temperature",
            dict(
                material="Inconel 718",
                mode="Strain-Life / LCF",
                correction="None",
                temperature=537.85,
                sigma_max=500,
                sigma_min=100,
                legacy=False,
            ),
        ),
        (
            "B. Nickel 625 exact fatigue temperature and mismatch",
            dict(
                material="Nickel 625",
                mode="Stress-Life / HCF",
                correction="Goodman",
                temperature=760,
                sigma_max=500,
                sigma_min=100,
                legacy=False,
            ),
        ),
        (
            "C. 316 / 316H mismatch",
            dict(
                material="316 Stainless Steel",
                mode="Strain-Life / LCF",
                correction="None",
                temperature=600,
                sigma_max=500,
                sigma_min=100,
                legacy=False,
            ),
        ),
        (
            "D. Aluminum 2024-T3 static only, no fatigue data",
            dict(
                material="Aluminum 2024-T3",
                mode="Stress-Life / HCF",
                correction="Goodman",
                temperature=24,
                sigma_max=500,
                sigma_min=100,
                legacy=False,
            ),
        ),
        (
            "E. Temperature outside static range",
            dict(
                material="Aluminum 7075-T6",
                mode="Strain-Life / LCF",
                correction="None",
                temperature=-100,
                sigma_max=500,
                sigma_min=100,
                legacy=False,
            ),
        ),
        (
            "F. Temperature outside fatigue range",
            dict(
                material="Nickel 625",
                mode="Stress-Life / HCF",
                correction="None",
                temperature=1200,
                sigma_max=500,
                sigma_min=100,
                legacy=False,
            ),
        ),
        (
            "G. Goodman with temperature-resolved S_u but unresolved Basquin",
            dict(
                material="Aluminum 2024-T3",
                mode="Stress-Life / HCF",
                correction="Goodman",
                temperature=24,
                sigma_max=500,
                sigma_min=100,
                legacy=False,
            ),
        ),
        (
            "H. Legacy fallback OFF",
            dict(
                material="Nickel 625",
                mode="Strain-Life / LCF",
                correction="None",
                temperature=600,
                sigma_max=500,
                sigma_min=100,
                legacy=False,
            ),
        ),
        (
            "I. Legacy fallback ON",
            dict(
                material="Nickel 625",
                mode="Strain-Life / LCF",
                correction="None",
                temperature=600,
                sigma_max=500,
                sigma_min=100,
                legacy=True,
            ),
        ),
        (
            "J. Legacy room-temperature HCF",
            dict(
                material="Aluminum 2024-T3",
                mode="Stress-Life / HCF",
                correction="None",
                temperature=21,
                sigma_max=500,
                sigma_min=100,
                legacy=True,
            ),
        ),
    ]

    for label, kwargs in cases:
        text, warnings, title = run_case(window, **kwargs)
        print(label)
        print(title)
        print(text.splitlines()[0:8])
        print(warnings)
        print("-" * 60)

    require_contains(
        run_case(
            window,
            material="Aluminum 2024-T3",
            mode="Stress-Life / HCF",
            correction="Goodman",
            temperature=24,
            sigma_max=500,
            sigma_min=100,
            legacy=False,
        )[0],
        "TEMPERATURE DATA UNAVAILABLE",
        "Fallback-off Goodman block",
    )

    require_contains(
        run_case(
            window,
            material="Aluminum 2024-T3",
            mode="Stress-Life / HCF",
            correction="Goodman",
            temperature=24,
            sigma_max=500,
            sigma_min=100,
            legacy=True,
        )[0],
        "LEGACY",
        "Fallback-on legacy estimate",
    )

    print("validate_temperature_integration.py PASSED")


if __name__ == "__main__":
    main()
