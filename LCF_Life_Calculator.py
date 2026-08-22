import os
import sys
import csv
import numpy as np

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QCheckBox,
    QPlainTextEdit,
    QSizePolicy,
)
from PyQt5.QtCore import Qt

import matplotlib

matplotlib.use("Qt5Agg")

from PyQt5.QtGui import QIcon
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from temperature_capability import (
    FULLY_TEMPERATURE_RESOLVED,
    PARTIALLY_TEMPERATURE_INFORMED,
    UNAVAILABLE as TEMPERATURE_DATA_UNAVAILABLE,
    MATCH,
    PARTIAL_MATCH,
    MISMATCH,
    UNKNOWN,
    assess_temperature_capability,
)


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def parse_optional_float(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if not np.isfinite(parsed):
        return None
    return parsed


class FatiguePlotWindow(QWidget):
    def __init__(self, title):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(title)
        self.resize(900, 650)
        self.setMinimumSize(700, 500)
        layout = QVBoxLayout()
        self.canvas = FigureCanvas(Figure(figsize=(9, 6.5)))
        layout.addWidget(self.canvas)
        self.ax = self.canvas.figure.add_subplot(111)
        self.setLayout(layout)

    def set_plot_title(self, title):
        self.setWindowTitle(title)

    def redraw(self):
        self.canvas.draw()


class LCFApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCF Life Calculator - Core FEA Toolkit")
        self.setWindowIcon(QIcon(resource_path("turbine_blisk_logo.jpg")))

        self.materials = self.load_materials(resource_path("materials.csv"))
        self.static_rows = self.load_table_rows(resource_path("materials_static.csv"))
        self.fatigue_rows = self.load_table_rows(resource_path("materials_fatigue.csv"))

        self.init_ui()
        self.resize(560, 750)
        self.setMinimumSize(520, 700)

    def load_materials(self, filepath):
        materials = {}
        print(f"Loading materials from: {filepath}")
        try:
            with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    print(f"Row read: {row}")
                    name = row["Material"]
                    materials[name] = {
                        "E": float(row["E_MPa"]),
                        "K_dash": float(row["K_dash"]),
                        "n_dash": float(row["n_dash"]),
                        "sigma_f_dash": float(row["sigma_f_dash"]),
                        "b": float(row["b"]),
                        "epsilon_f_dash": float(row["epsilon_f_dash"]),
                        "c": float(row["c"]),
                        "S_u": parse_optional_float(row.get("S_u_MPa", "")),
                        "S_y": parse_optional_float(row.get("S_y_MPa", "")),
                        "material_condition": row.get("material_condition", "").strip(),
                        "property_temperature_C": row.get("property_temperature_C", "").strip(),
                        "property_source": row.get("property_source", "").strip(),
                        "property_basis": row.get("property_basis", "").strip(),
                        "property_notes": row.get("property_notes", "").strip(),
                    }
        except Exception as e:
            print(f"Error loading materials: {e}")
        return materials

    def load_table_rows(self, filepath):
        rows = []
        print(f"Loading temperature table from: {filepath}")
        try:
            with open(filepath, newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
        except Exception as e:
            print(f"Error loading temperature table {filepath}: {e}")
        return rows

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("Low Cycle Fatigue Life Estimator")
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(title)

        material_layout = QHBoxLayout()
        material_layout.setContentsMargins(0, 0, 0, 0)
        material_layout.setSpacing(8)
        material_layout.addWidget(QLabel("Select Material:"))
        self.material_box = QComboBox()
        self.material_box.addItems(self.materials.keys())
        self.material_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        material_layout.addWidget(self.material_box)
        layout.addLayout(material_layout)

        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)
        mode_layout.addWidget(QLabel("Analysis Mode:"))
        self.analysis_mode_box = QComboBox()
        self.analysis_mode_box.addItems(["Strain-Life / LCF", "Stress-Life / HCF"])
        self.analysis_mode_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        mode_layout.addWidget(self.analysis_mode_box)
        layout.addLayout(mode_layout)

        mean_stress_layout = QHBoxLayout()
        mean_stress_layout.setContentsMargins(0, 0, 0, 0)
        mean_stress_layout.setSpacing(8)
        mean_stress_layout.addWidget(QLabel("Mean Stress Correction:"))
        self.mean_stress_box = QComboBox()
        self.mean_stress_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        mean_stress_layout.addWidget(self.mean_stress_box)
        layout.addLayout(mean_stress_layout)

        self.analysis_mode_box.currentTextChanged.connect(self.update_mean_stress_options)
        self.update_mean_stress_options(self.analysis_mode_box.currentText())

        temperature_layout = QHBoxLayout()
        temperature_layout.addWidget(QLabel("Analysis Temperature (Â°C):"))
        self.analysis_temperature_input = QLineEdit()
        self.analysis_temperature_input.setText("21")
        self.analysis_temperature_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        temperature_layout.addWidget(self.analysis_temperature_input)
        layout.addLayout(temperature_layout)

        self.legacy_fallback_box = QCheckBox(
            "Use legacy fatigue constants when temperature-resolved fatigue data are unavailable"
        )
        self.legacy_fallback_box.setChecked(False)
        self.legacy_fallback_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.legacy_fallback_box)

        stress_max_layout = QHBoxLayout()
        stress_max_layout.addWidget(QLabel("Maximum Stress, sigma_max (MPa):"))
        self.sigma_max_input = QLineEdit()
        self.sigma_max_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        stress_max_layout.addWidget(self.sigma_max_input)
        layout.addLayout(stress_max_layout)

        stress_min_layout = QHBoxLayout()
        stress_min_layout.addWidget(QLabel("Minimum Stress, sigma_min (MPa):"))
        self.sigma_min_input = QLineEdit()
        self.sigma_min_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        stress_min_layout.addWidget(self.sigma_min_input)
        layout.addLayout(stress_min_layout)

        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(280)
        self.result_text.setMaximumHeight(320)
        self.result_text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.result_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.result_text.setPlainText(
            "Analysis Temperature (C): -\n"
            "Temperature Capability: -\n"
            "Static Condition: -\n"
            "Fatigue Condition: -\n"
            "Condition Compatibility: -\n"
            "Property Status: -\n"
            "Calculation Status: -\n"
            "Stress Amplitude (MPa): -\n"
            "Mean Stress (MPa): -\n"
            "Elastic Strain Amplitude: -\n"
            "Plastic Strain Amplitude: -\n"
            "Total Strain Amplitude: -\n"
            "Estimated Life (cycles): -\n"
            "Reversals to Failure (2Nf): -"
        )
        layout.addWidget(self.result_text)

        calc_btn = QPushButton("Calculate Fatigue Life")
        calc_btn.clicked.connect(self.calculate_life)
        calc_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(calc_btn)

        self.setLayout(layout)
        self.plot_window = None
        self.resize(600, 700)
        self.setMinimumSize(560, 680)

    def calculate_life(self):
        if self.analysis_mode_box.currentText() == "Stress-Life / HCF":
            self.calculate_hcf()
        else:
            self.calculate_lcf()

    def update_mean_stress_options(self, mode=None):
        if mode is None:
            mode = self.analysis_mode_box.currentText()

        options = ["None"]
        if mode == "Strain-Life / LCF":
            options.append("Morrow")
        elif mode == "Stress-Life / HCF":
            options.append("Goodman")

        self.mean_stress_box.blockSignals(True)
        self.mean_stress_box.clear()
        self.mean_stress_box.addItems(options)
        self.mean_stress_box.setCurrentIndex(0)
        self.mean_stress_box.blockSignals(False)

    def ensure_plot_window(self, title):
        if self.plot_window is None:
            self.plot_window = FatiguePlotWindow(title)
            self.plot_window.destroyed.connect(self.on_plot_window_destroyed)
        else:
            self.plot_window.set_plot_title(title)
        return self.plot_window

    def on_plot_window_destroyed(self, *args):
        self.plot_window = None

    def show_plot_window(self, title):
        plot_window = self.ensure_plot_window(title)
        plot_window.show()
        plot_window.raise_()
        plot_window.activateWindow()
        return plot_window

    def closeEvent(self, event):
        if self.plot_window is not None:
            self.plot_window.close()
        super().closeEvent(event)

    def parse_temperature(self):
        try:
            temperature = float(self.analysis_temperature_input.text())
        except ValueError:
            return None
        if not np.isfinite(temperature):
            return None
        return temperature

    def calculate_lcf(self):
        sigma_max, sigma_min = self.parse_stress_inputs()
        if sigma_max is None:
            return
        temperature = self.parse_temperature()
        if temperature is None:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter a valid numeric and finite analysis temperature.",
            )
            return

        material_name = self.material_box.currentText()
        correction = self.mean_stress_box.currentText()
        static_condition, fatigue_condition = self.get_temperature_conditions(material_name)
        capability = assess_temperature_capability(
            material_name,
            temperature,
            "LCF",
            correction,
            self.static_rows,
            self.fatigue_rows,
            static_condition=static_condition,
            fatigue_condition=fatigue_condition,
        )

        legacy_fallback = self.legacy_fallback_box.isChecked()
        mat = self.materials[material_name]

        sigma_a = abs(sigma_max - sigma_min) / 2
        sigma_m = (sigma_max + sigma_min) / 2
        if sigma_a <= 0:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Calculated stress amplitude must be greater than zero.",
            )
            return

        if capability.capability == FULLY_TEMPERATURE_RESOLVED:
            e_item = self.get_capability_item(capability, "E_MPa")
            k_item = self.get_capability_item(capability, "K_dash")
            n_item = self.get_capability_item(capability, "n_dash")
            sigma_f_item = self.get_capability_item(capability, "sigma_f_dash")
            b_item = self.get_capability_item(capability, "b")
            epsilon_f_item = self.get_capability_item(capability, "epsilon_f_dash")
            c_item = self.get_capability_item(capability, "c")

            E = e_item.value
            K_dash = k_item.value
            n_dash = n_item.value
            sigma_f_dash = sigma_f_item.value
            b = b_item.value
            epsilon_f_dash = epsilon_f_item.value
            c = c_item.value
            calculation_status = "FULLY TEMPERATURE RESOLVED"
            temperature_note = None
        else:
            if not legacy_fallback:
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Strain-Life / LCF",
                    correction,
                    "TEMPERATURE DATA UNAVAILABLE",
                )
                return

            e_item = self.get_capability_item(capability, "E_MPa")
            used_temperature_E = e_item is not None and e_item.status in {"EXACT", "INTERPOLATED"}
            E = e_item.value if used_temperature_E and e_item.value is not None else mat["E"]

            K_dash = mat["K_dash"]
            n_dash = mat["n_dash"]
            sigma_f_dash = mat["sigma_f_dash"]
            b = mat["b"]
            epsilon_f_dash = mat["epsilon_f_dash"]
            c = mat["c"]

            if capability.capability in {PARTIALLY_TEMPERATURE_INFORMED}:
                calculation_status = "LEGACY / PARTIALLY TEMPERATURE-INFORMED ESTIMATE"
            else:
                calculation_status = "LEGACY / TEMPERATURE-UNRESOLVED ESTIMATE"

            temperature_note = None
            if used_temperature_E:
                temperature_note = "Temperature-resolved Young's modulus used with legacy fatigue constants."
            else:
                temperature_note = "Legacy Young's modulus and legacy fatigue constants used."

        if correction == "Morrow":
            self.calculate_lcf_morrow(
                sigma_max,
                sigma_min,
                sigma_a,
                sigma_m,
                E,
                K_dash,
                n_dash,
                sigma_f_dash,
                b,
                epsilon_f_dash,
                c,
                temperature,
                capability,
                calculation_status,
                temperature_note,
                legacy_fallback,
            )
            return

        solve_result = self.solve_life(sigma_a, E, sigma_f_dash, b, epsilon_f_dash, c)
        if solve_result is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                correction,
                calculation_status,
                temperature_note,
                "A valid fatigue life could not be bracketed for the selected material and stress inputs.",
            )
            return

        estimated_life, reversals_to_failure, plot_cycles, rhs, lhs = solve_result
        elastic_strain = sigma_a / E
        plastic_strain = (sigma_a / K_dash) ** (1 / n_dash)
        strain_amplitude = elastic_strain + plastic_strain
        result_lines = self.build_status_lines(
            temperature,
            capability,
            calculation_status,
            temperature_note,
        )
        result_lines.extend(
            [
                "Stress Amplitude (MPa): {0:,.6g}".format(sigma_a),
                "Mean Stress (MPa): {0:,.6g}".format(sigma_m),
                "Elastic Strain Amplitude: {0:,.6g}".format(elastic_strain),
                "Plastic Strain Amplitude: {0:,.6g}".format(plastic_strain),
                "Total Strain Amplitude: {0:,.6g}".format(strain_amplitude),
                "Estimated Life (cycles): {0}".format(self.format_life_value(estimated_life)),
                "Reversals to Failure (2Nf): {0}".format(self.format_life_value(reversals_to_failure)),
            ]
        )
        if legacy_fallback and calculation_status != "FULLY TEMPERATURE RESOLVED":
            result_lines.append("Legacy fatigue constants were used for the strain-life coefficients.")

        self.set_result_text("\n".join(result_lines))
        plot_window = self.show_plot_window("LCF Strain-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_title(
            self.plot_title("Strain-Life Curve", temperature, legacy_fallback, capability)
        )
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Strain Amplitude")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(2 * plot_cycles, rhs, label="Material Curve")
        plot_window.ax.plot(2 * estimated_life, lhs, "ro", label="Your Result")
        plot_window.ax.legend()
        plot_window.redraw()

    def calculate_lcf_morrow(
        self,
        sigma_max,
        sigma_min,
        sigma_a,
        sigma_m,
        E,
        K_dash,
        n_dash,
        sigma_f_dash,
        b,
        epsilon_f_dash,
        c,
        temperature,
        capability,
        calculation_status,
        temperature_note,
        legacy_fallback,
    ):
        elastic_strain = sigma_a / E
        plastic_strain = (sigma_a / K_dash) ** (1 / n_dash)
        strain_amplitude = elastic_strain + plastic_strain

        if not np.isfinite(sigma_f_dash) or not np.isfinite(sigma_m):
            QMessageBox.warning(
                self,
                "Invalid Material Data",
                "Morrow correction requires finite material and stress values.",
            )
            return

        morrow_sigma_f_dash = sigma_f_dash - sigma_m
        if morrow_sigma_f_dash <= 0:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "The Morrow elastic coefficient becomes non-positive for the entered mean stress.",
            )
            return

        uncorrected_result = self.solve_life(
            strain_amplitude, E, sigma_f_dash, b, epsilon_f_dash, c
        )
        if uncorrected_result is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                "Morrow",
                calculation_status,
                temperature_note,
                "A valid uncorrected LCF life could not be bracketed for the selected material and stress inputs.",
            )
            return

        uncorrected_life, uncorrected_reversals, _, _, _ = uncorrected_result

        morrow_raw_result = self.solve_life(
            strain_amplitude,
            E,
            morrow_sigma_f_dash,
            b,
            epsilon_f_dash,
            c,
        )
        if morrow_raw_result is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                "Morrow",
                calculation_status,
                temperature_note,
                "A valid Morrow-corrected LCF life could not be bracketed for the selected material and stress inputs.",
            )
            return

        morrow_raw_life, morrow_raw_reversals, _, _, _ = morrow_raw_result
        cap_message = ""
        morrow_life = morrow_raw_life
        morrow_reversals = morrow_raw_reversals
        if sigma_m < 0 and morrow_raw_life > uncorrected_life:
            morrow_life = uncorrected_life
            morrow_reversals = uncorrected_reversals
            cap_message = "Compressive mean-stress life benefit conservatively capped at uncorrected life."

        plot_lower = max(1e-12, min(uncorrected_life, morrow_life) / 10.0)
        plot_upper = max(1e6, uncorrected_life * 1.25, morrow_life * 1.25)
        plot_cycles = np.logspace(np.log10(plot_lower), np.log10(plot_upper), 1000)
        rhs_uncorrected = self.strain_life_rhs(
            plot_cycles, E, sigma_f_dash, b, epsilon_f_dash, c
        )
        rhs_morrow = self.strain_life_rhs(
            plot_cycles, E, morrow_sigma_f_dash, b, epsilon_f_dash, c
        )

        result_lines = self.build_status_lines(
            temperature,
            capability,
            calculation_status,
            temperature_note,
        )
        result_lines.extend(
            [
                "Stress Amplitude (MPa): {0:,.6g}".format(sigma_a),
                "Mean Stress (MPa): {0:,.6g}".format(sigma_m),
                "Elastic Strain Amplitude: {0:,.6g}".format(elastic_strain),
                "Plastic Strain Amplitude: {0:,.6g}".format(plastic_strain),
                "Total Strain Amplitude: {0:,.6g}".format(strain_amplitude),
                "Uncorrected Life (cycles): {0}".format(self.format_life_value(uncorrected_life)),
                "Morrow-Corrected Life (cycles): {0}".format(self.format_life_value(morrow_life)),
                "Uncorrected Reversals (2Nf): {0}".format(self.format_life_value(uncorrected_reversals)),
                "Morrow-Corrected Reversals (2Nf): {0}".format(self.format_life_value(morrow_reversals)),
            ]
        )
        if cap_message:
            result_lines.append(cap_message)
        if legacy_fallback and calculation_status != "FULLY TEMPERATURE RESOLVED":
            result_lines.append(
                "Legacy fatigue constants were used for the strain-life coefficients."
            )

        self.set_result_text("\n".join(result_lines))
        plot_window = self.show_plot_window("LCF Strain-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_title(
            self.plot_title("Strain-Life Curve", temperature, legacy_fallback, capability)
        )
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Strain Amplitude")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(2 * plot_cycles, rhs_uncorrected, label="Uncorrected Curve")
        plot_window.ax.plot(2 * plot_cycles, rhs_morrow, label="Morrow-Corrected Curve")
        plot_window.ax.plot(2 * morrow_life, strain_amplitude, "ro", label="Morrow Result")
        plot_window.ax.legend()
        plot_window.redraw()

    def calculate_hcf(self):
        sigma_max, sigma_min = self.parse_stress_inputs()
        if sigma_max is None:
            return
        temperature = self.parse_temperature()
        if temperature is None:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter a valid numeric and finite analysis temperature.",
            )
            return

        material_name = self.material_box.currentText()
        if material_name in (
            "SiC/SiC Ceramic Matrix Composite",
            "C/C Composite",
        ):
            QMessageBox.warning(
                self,
                "HCF Not Enabled",
                "Standalone metallic Basquin HCF estimation is not enabled for this material.",
            )
            self.set_result_text(
                "Analysis Mode: Stress-Life / HCF\n"
                "Standalone metallic Basquin HCF estimation is not enabled for this material."
            )
            if self.plot_window is not None:
                self.plot_window.ax.clear()
                self.plot_window.redraw()
            return

        correction = self.mean_stress_box.currentText()
        static_condition, fatigue_condition = self.get_temperature_conditions(material_name)
        capability = assess_temperature_capability(
            material_name,
            temperature,
            "HCF",
            correction,
            self.static_rows,
            self.fatigue_rows,
            static_condition=static_condition,
            fatigue_condition=fatigue_condition,
        )
        legacy_fallback = self.legacy_fallback_box.isChecked()
        mat = self.materials[material_name]

        sigma_a = abs(sigma_max - sigma_min) / 2
        sigma_m = (sigma_max + sigma_min) / 2

        if not np.isfinite(sigma_a) or sigma_a <= 0:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Calculated stress amplitude must be greater than zero.",
            )
            return

        sigma_f_item = self.get_capability_item(capability, "sigma_f_dash")
        b_item = self.get_capability_item(capability, "b")
        su_item = self.get_capability_item(capability, "S_u_MPa")

        if capability.capability == FULLY_TEMPERATURE_RESOLVED:
            sigma_f_dash = sigma_f_item.value
            b = b_item.value
            S_u = su_item.value if correction == "Goodman" else None
            calculation_status = "FULLY TEMPERATURE RESOLVED"
            temperature_note = None
        else:
            if not legacy_fallback:
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Stress-Life / HCF",
                    correction,
                    "TEMPERATURE DATA UNAVAILABLE",
                )
                return

            sigma_f_dash = mat["sigma_f_dash"]
            b = mat["b"]
            if correction == "Goodman":
                if su_item is not None and su_item.status in {"EXACT", "INTERPOLATED"} and su_item.value is not None:
                    S_u = su_item.value
                    temperature_note = (
                        "Goodman strength correction is temperature-informed; Basquin fatigue constants are legacy/temperature-unresolved."
                    )
                else:
                    S_u = mat["S_u"]
                    temperature_note = (
                        "Legacy Goodman strength correction used; Basquin fatigue constants are legacy/temperature-unresolved."
                    )
            else:
                S_u = None
                temperature_note = (
                    "Legacy Basquin fatigue constants used; temperature-resolved fatigue data are unavailable."
                )

            if capability.capability in {PARTIALLY_TEMPERATURE_INFORMED} and correction == "Goodman":
                calculation_status = "LEGACY / PARTIALLY TEMPERATURE-INFORMED ESTIMATE"
            elif capability.capability in {PARTIALLY_TEMPERATURE_INFORMED}:
                calculation_status = "LEGACY / PARTIALLY TEMPERATURE-INFORMED ESTIMATE"
            else:
                calculation_status = "LEGACY / TEMPERATURE-UNRESOLVED ESTIMATE"

        if not np.isfinite(sigma_f_dash) or sigma_f_dash <= 0:
            QMessageBox.warning(
                self,
                "Invalid Material Data",
                "Fatigue strength coefficient must be positive and finite for Basquin HCF.",
            )
            return

        if not np.isfinite(b) or b >= 0:
            QMessageBox.warning(
                self,
                "Invalid Material Data",
                "Fatigue strength exponent must be negative for a valid Basquin HCF relation.",
            )
            return

        basquin_result = self.calculate_basquin_life(sigma_a, sigma_f_dash, b)
        if basquin_result is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Stress-Life / HCF",
                correction,
                calculation_status,
                temperature_note,
                "The HCF life calculation produced an invalid result.",
            )
            return

        estimated_life, reversals_to_failure = basquin_result

        if correction == "Goodman":
            self.calculate_hcf_goodman(
                sigma_max,
                sigma_min,
                sigma_a,
                sigma_m,
                estimated_life,
                reversals_to_failure,
                mat,
                sigma_f_dash,
                b,
                S_u,
                temperature,
                capability,
                calculation_status,
                temperature_note,
                legacy_fallback,
            )
            return

        plot_reversals, plot_curve = self.build_hcf_curve(estimated_life, sigma_f_dash, b)
        if plot_reversals is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Stress-Life / HCF",
                correction,
                calculation_status,
                temperature_note,
                "The HCF curve could not be generated for the selected material and stress inputs.",
            )
            return

        result_lines = self.build_status_lines(
            temperature,
            capability,
            calculation_status,
            temperature_note,
        )
        result_lines.extend(
            [
                "Maximum Stress (MPa): {0:,.6g}".format(sigma_max),
                "Minimum Stress (MPa): {0:,.6g}".format(sigma_min),
                "Stress Amplitude (MPa): {0:,.6g}".format(sigma_a),
                "Mean Stress (MPa): {0:,.6g}".format(sigma_m),
                "Estimated Life (cycles): {0}".format(self.format_life_value(estimated_life)),
                "Reversals to Failure (2Nf): {0}".format(self.format_life_value(reversals_to_failure)),
                "Mean stress calculated but not corrected.",
                "Basquin stress-life estimate; intended for elastic-dominated HCF.",
                "Material fatigue constants do not currently include calibration-range metadata; extrapolated HCF life should be treated as an engineering estimate.",
            ]
        )
        if legacy_fallback and calculation_status != "FULLY TEMPERATURE RESOLVED":
            result_lines.append("Legacy fatigue constants were used for the Basquin relation.")

        self.set_result_text("\n".join(result_lines))
        plot_window = self.show_plot_window("HCF Stress-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_yscale("log")
        plot_window.ax.set_title(
            self.plot_title("Stress-Life (Basquin) Curve", temperature, legacy_fallback, capability)
        )
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Stress Amplitude (MPa)")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(plot_reversals, plot_curve, label="Basquin Curve")
        plot_window.ax.plot(reversals_to_failure, sigma_a, "ro", label="Your Result")
        plot_window.ax.legend()
        plot_window.redraw()

    def calculate_hcf_goodman(
        self,
        sigma_max,
        sigma_min,
        sigma_a,
        sigma_m,
        uncorrected_life,
        uncorrected_reversals,
        mat,
        sigma_f_dash,
        b,
        S_u,
        temperature,
        capability,
        calculation_status,
        temperature_note,
        legacy_fallback,
    ):
        if S_u is None or not np.isfinite(S_u) or S_u <= 0:
            QMessageBox.warning(
                self,
                "Goodman Not Available",
                "Goodman correction is not available for this material because a valid S_u_MPa value is not present in the material database.",
            )
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Stress-Life / HCF",
                "Goodman",
                calculation_status,
                temperature_note,
                "Goodman correction could not be applied because S_u is unavailable.",
            )
            return

        if sigma_m >= S_u:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Goodman correction requires mean stress to be less than the ultimate tensile strength S_u.",
            )
            return

        denominator = 1.0 - sigma_m / S_u
        if not np.isfinite(denominator) or denominator <= 0:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "The Goodman correction denominator is zero or negative for the entered mean stress.",
            )
            return

        sigma_a_eq = sigma_a / denominator
        goodman_raw_result = self.calculate_basquin_life(sigma_a_eq, sigma_f_dash, b)
        if goodman_raw_result is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Stress-Life / HCF",
                "Goodman",
                calculation_status,
                temperature_note,
                "The Goodman-corrected HCF life calculation produced an invalid result.",
            )
            return

        goodman_life_raw, goodman_reversals_raw = goodman_raw_result
        cap_message = ""
        goodman_life = goodman_life_raw
        goodman_reversals = goodman_reversals_raw
        if sigma_m < 0 and goodman_life_raw > uncorrected_life:
            goodman_life = uncorrected_life
            goodman_reversals = uncorrected_reversals
            cap_message = "Compressive mean-stress life benefit conservatively capped at uncorrected life."

        plot_reversals, plot_curve = self.build_hcf_curve(
            uncorrected_life, sigma_f_dash, b, goodman_life
        )
        if plot_reversals is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Stress-Life / HCF",
                "Goodman",
                calculation_status,
                temperature_note,
                "The HCF curve could not be generated for the selected material and stress inputs.",
            )
            return

        result_lines = self.build_status_lines(
            temperature,
            capability,
            calculation_status,
            temperature_note,
        )
        result_lines.extend(
            [
                "Maximum Stress (MPa): {0:,.6g}".format(sigma_max),
                "Minimum Stress (MPa): {0:,.6g}".format(sigma_min),
                "Stress Amplitude (MPa): {0:,.6g}".format(sigma_a),
                "Mean Stress (MPa): {0:,.6g}".format(sigma_m),
                "Ultimate Tensile Strength, S_u (MPa): {0:,.6g}".format(S_u),
                "Goodman Corrected Stress Amplitude (MPa): {0:,.6g}".format(sigma_a_eq),
                "Uncorrected Life (cycles): {0}".format(self.format_life_value(uncorrected_life)),
                "Goodman-Corrected Life (cycles): {0}".format(self.format_life_value(goodman_life)),
                "Uncorrected Reversals (2Nf): {0}".format(self.format_life_value(uncorrected_reversals)),
                "Goodman-Corrected Reversals (2Nf): {0}".format(self.format_life_value(goodman_reversals)),
            ]
        )
        if mat.get("material_condition"):
            result_lines.append(f"Material condition: {mat['material_condition']}")
        if mat.get("property_temperature_C"):
            result_lines.append(f"Property temperature: {mat['property_temperature_C']} C")
        if mat.get("property_basis"):
            result_lines.append(f"Property basis: {mat['property_basis']}")
        if cap_message:
            result_lines.append(cap_message)
        result_lines.append("Goodman mean-stress correction using reference S_u data; engineering estimate only.")
        result_lines.append(
            "Material fatigue constants do not currently include calibration-range metadata; extrapolated HCF life should be treated as an engineering estimate."
        )
        if legacy_fallback and calculation_status != "FULLY TEMPERATURE RESOLVED":
            result_lines.append("Legacy Basquin fatigue constants were used for the HCF relation.")

        self.set_result_text("\n".join(result_lines))
        plot_window = self.show_plot_window("HCF Stress-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_yscale("log")
        plot_window.ax.set_title(
            self.plot_title("Stress-Life (Basquin) Curve", temperature, legacy_fallback, capability)
        )
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Stress Amplitude (MPa)")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(plot_reversals, plot_curve, label="Basquin Curve")
        plot_window.ax.plot(uncorrected_reversals, sigma_a, "ro", label="Uncorrected Result")
        plot_window.ax.plot(goodman_reversals, sigma_a_eq, "go", label="Goodman Result")
        plot_window.ax.legend()
        plot_window.redraw()

    def build_status_lines(self, temperature, capability, calculation_status, temperature_note):
        lines = [
            f"Analysis Temperature (C): {temperature:,.6g}",
            f"Temperature Capability: {self.capability_display_label(capability.capability)}",
            f"Static Condition: {capability.static_condition or '-'}",
            f"Fatigue Condition: {capability.fatigue_condition or '-'}",
            f"Condition Compatibility: {capability.condition_compatibility}",
            "Property Status:",
        ]
        lines.extend(self.build_property_status_lines(capability))
        lines.append(f"Calculation Status: {calculation_status}")
        if capability.summary:
            lines.append(f"Capability Summary: {capability.summary}")
        for warning in capability.warnings:
            lines.append(f"Warning: {warning}")
        if temperature_note:
            lines.append(temperature_note)
        return lines

    def get_temperature_conditions(self, material_name):
        hints = {
            "Aluminum 2024-T3": ("2024-T3", None),
            "Inconel 718": (
                "HAYNES 718 plate, mill annealed + 1325F/8h furnace cool to 1150F/8h air cool",
                "Inconel 718 unified creep-fatigue coefficient dataset at 811 K",
            ),
            "Ti-6Al-4V": (
                "TIMETAL 6-4 / ASTM Grade 5 sheet/plate annealed per ASTM B265",
                None,
            ),
            "Nickel 625": (
                "HAYNES 625 hot-rolled plate, 1925F mill-annealed",
                "Inconel 625 nickel-base superalloy welding joint",
            ),
            "316 Stainless Steel": (
                "ATI 316 / UNS S31600, annealed elevated-properties dataset",
                "316H stainless steel low-cycle fatigue dataset at 600-800 C",
            ),
            "Alloy Steel 4340": ("AISI 4340, normalized, 25 mm round", None),
            "Aluminum 7075-T6": ("7075-T6", None),
            "Haynes 230": ("HAYNES 230 plate, solution annealed", None),
            "Rene 41": ("HAYNES R-41, age hardened 1400F/16h/air cool", None),
        }
        return hints.get(material_name, (None, None))

    def build_property_status_lines(self, capability):
        lines = []
        static_items = [item for item in capability.required_properties if item.property_group == "static"]
        fatigue_items = [item for item in capability.required_properties if item.property_group == "fatigue"]

        if static_items:
            lines.append("  Static:")
            for item in static_items:
                lines.append(self.format_property_line(item))
        if fatigue_items:
            lines.append("  Fatigue:")
            for item in fatigue_items:
                lines.append(self.format_property_line(item))
        if not static_items and not fatigue_items:
            lines.append("  none")
        return lines

    def format_property_line(self, item):
        status_text = item.status.replace("_", " ")
        if item.interpolated and item.status in {"EXACT", "INTERPOLATED"}:
            status_text = f"{status_text} (interpolated)"
        details = []
        if item.source:
            details.append(f"source: {item.source}")
        if item.condition:
            details.append(f"condition: {item.condition}")
        if item.basis:
            details.append(f"basis: {item.basis}")
        detail_text = " | ".join(details)
        if detail_text:
            return f"    {item.property_name}: {status_text} | {detail_text}"
        return f"    {item.property_name}: {status_text}"

    def capability_display_label(self, capability):
        if capability == FULLY_TEMPERATURE_RESOLVED:
            return "FULLY TEMPERATURE RESOLVED"
        if capability == PARTIALLY_TEMPERATURE_INFORMED:
            return "PARTIALLY TEMPERATURE INFORMED"
        return "TEMPERATURE DATA UNAVAILABLE"

    def plot_title(self, base_title, temperature, legacy_fallback, capability):
        suffix = f" - {temperature:,.6g} C"
        if legacy_fallback and capability != FULLY_TEMPERATURE_RESOLVED:
            suffix += " (legacy fatigue constants)"
        return base_title + suffix

    def parse_stress_inputs(self):
        try:
            sigma_max = float(self.sigma_max_input.text())
            sigma_min = float(self.sigma_min_input.text())
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter valid numeric values for both maximum and minimum stress.",
            )
            return None, None

        if not np.isfinite(sigma_max) or not np.isfinite(sigma_min):
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter finite numeric values for both maximum and minimum stress.",
            )
            return None, None

        if sigma_max < sigma_min:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Maximum stress must be greater than or equal to minimum stress.",
            )
            return None, None

        return sigma_max, sigma_min

    def show_unavailable_temperature_result(
        self,
        capability,
        temperature,
        mode_label,
        correction_label,
        calculation_status,
        temperature_note=None,
        extra_message=None,
    ):
        lines = self.build_status_lines(
            temperature,
            capability,
            calculation_status,
            temperature_note,
        )
        lines.append(f"Analysis Mode: {mode_label}")
        lines.append(f"Mean Stress Correction: {correction_label}")
        if extra_message:
            lines.append(extra_message)
        self.set_result_text("\n".join(lines))
        if self.plot_window is not None:
            self.plot_window.ax.clear()
            self.plot_window.redraw()

    def set_result_text(self, text):
        self.result_text.setPlainText(text)
        self.result_text.verticalScrollBar().setValue(0)

    def get_capability_item(self, capability, property_name):
        for item in capability.required_properties:
            if item.property_name == property_name:
                return item
        return None

    def calculate_basquin_life(self, stress_amplitude, sigma_f_dash, b):
        ratio = stress_amplitude / sigma_f_dash
        if not np.isfinite(ratio) or ratio <= 0:
            return None

        reversals_to_failure = np.power(ratio, 1.0 / b)
        estimated_life = 0.5 * reversals_to_failure
        if not np.isfinite(reversals_to_failure) or not np.isfinite(estimated_life):
            return None
        if reversals_to_failure <= 0 or estimated_life <= 0:
            return None

        return estimated_life, reversals_to_failure

    def strain_life_rhs(self, Nf, E, sigma_f_dash, b, epsilon_f_dash, c):
        reversals = 2.0 * Nf
        return (sigma_f_dash / E) * reversals ** b + epsilon_f_dash * reversals ** c

    def build_hcf_curve(self, estimated_life, sigma_f_dash, b, additional_life=None):
        lives = [estimated_life]
        if additional_life is not None:
            lives.append(additional_life)

        reversals = [2.0 * life for life in lives]
        if any(not np.isfinite(value) or value <= 0 for value in reversals):
            return None, None

        plot_lower = max(1e-12, min(reversals) / 1e4)
        plot_upper = max(plot_lower * 10.0, max(reversals) * 1e4)
        if (
            not np.isfinite(plot_lower)
            or not np.isfinite(plot_upper)
            or plot_lower <= 0
            or plot_upper <= plot_lower
        ):
            return None, None

        plot_reversals = np.logspace(np.log10(plot_lower), np.log10(plot_upper), 1000)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            plot_curve = sigma_f_dash * plot_reversals ** b

        if not np.all(np.isfinite(plot_curve)) or np.any(plot_curve <= 0):
            return None, None

        return plot_reversals, plot_curve

    def solve_life(self, target_strain, E, sigma_f_dash, b, epsilon_f_dash, c):
        if not np.isfinite(target_strain) or target_strain <= 0:
            return None

        lower = 1e-12
        upper = 1e3
        max_upper = 1e12

        def f(nf):
            rhs = self.strain_life_rhs(nf, E, sigma_f_dash, b, epsilon_f_dash, c)
            return rhs - target_strain

        f_lower = f(lower)
        if not np.isfinite(f_lower) or f_lower < 0:
            return None

        while True:
            f_upper = f(upper)
            if not np.isfinite(f_upper):
                return None
            if f_upper <= 0:
                break
            if upper >= max_upper:
                return None
            upper *= 10.0

        for _ in range(200):
            mid = 0.5 * (lower + upper)
            f_mid = f(mid)
            if not np.isfinite(f_mid):
                return None
            if abs(f_mid) <= max(1e-12, 1e-8 * target_strain):
                lower = upper = mid
                break
            if f_mid > 0:
                lower = mid
            else:
                upper = mid
            if abs(upper - lower) <= max(1e-12, 1e-8 * mid):
                break

        estimated_life = 0.5 * (lower + upper)
        if not np.isfinite(estimated_life) or estimated_life <= 0:
            return None

        plot_upper = max(1e6, estimated_life * 1.25)
        plot_lower = 1e2
        plot_cycles = np.logspace(np.log10(plot_lower), np.log10(plot_upper), 1000)
        rhs = self.strain_life_rhs(plot_cycles, E, sigma_f_dash, b, epsilon_f_dash, c)
        reversals_to_failure = 2.0 * estimated_life

        return estimated_life, reversals_to_failure, plot_cycles, rhs, target_strain

    def format_life_value(self, value):
        if not np.isfinite(value):
            return "-"
        if abs(value) >= 1e6 or (0 < abs(value) < 1e-3):
            return f"{value:.6e}"
        return f"{value:,.6g}"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LCFApp()
    window.show()
    sys.exit(app.exec_())

