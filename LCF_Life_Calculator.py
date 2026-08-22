import os
import sys
import csv
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QComboBox,
    QLineEdit, QPushButton, QMessageBox
)
import matplotlib
matplotlib.use('Qt5Agg')

from PyQt5.QtGui import QIcon
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Ensure compatibility with PyInstaller packaged .exe
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class LCFApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCF Life Calculator – Core FEA Toolkit™")
        self.setWindowIcon(QIcon(resource_path("turbine_blisk_logo.jpg")))

        # Load materials from CSV
        self.materials = self.load_materials(resource_path("materials.csv"))

        self.init_ui()

    def load_materials(self, filepath):
        materials = {}
        print(f"Loading materials from: {filepath}")
        try:
            with open(filepath, newline='', encoding='utf-8-sig') as csvfile:
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
                    }
        except Exception as e:
            print(f"Error loading materials: {e}")
        return materials

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("🔧 Low Cycle Fatigue Life Estimator")
        layout.addWidget(title)

        material_layout = QHBoxLayout()
        material_layout.addWidget(QLabel("Select Material:"))
        self.material_box = QComboBox()
        self.material_box.addItems(self.materials.keys())
        material_layout.addWidget(self.material_box)
        layout.addLayout(material_layout)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Analysis Mode:"))
        self.analysis_mode_box = QComboBox()
        self.analysis_mode_box.addItems(["Strain-Life / LCF", "Stress-Life / HCF"])
        mode_layout.addWidget(self.analysis_mode_box)
        layout.addLayout(mode_layout)

        stress_max_layout = QHBoxLayout()
        stress_max_layout.addWidget(QLabel("Maximum Stress, sigma_max (MPa):"))
        self.sigma_max_input = QLineEdit()
        stress_max_layout.addWidget(self.sigma_max_input)
        layout.addLayout(stress_max_layout)

        stress_min_layout = QHBoxLayout()
        stress_min_layout.addWidget(QLabel("Minimum Stress, sigma_min (MPa):"))
        self.sigma_min_input = QLineEdit()
        stress_min_layout.addWidget(self.sigma_min_input)
        layout.addLayout(stress_min_layout)

        self.result_label = QLabel(
            "Stress Amplitude (MPa): -\n"
            "Mean Stress (MPa): -\n"
            "Elastic Strain Amplitude: -\n"
            "Plastic Strain Amplitude: -\n"
            "Total Strain Amplitude: -\n"
            "Estimated Life (cycles): -\n"
            "Reversals to Failure (2Nf): -"
        )
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        self.canvas = FigureCanvas(Figure(figsize=(5, 3)))
        layout.addWidget(self.canvas)
        self.ax = self.canvas.figure.add_subplot(111)
        self.ax.set_title("Strain-Life Curve")
        self.ax.set_xlabel("2Nf (Reversals)")
        self.ax.set_ylabel("Strain Amplitude")

        calc_btn = QPushButton("Calculate Fatigue Life")
        calc_btn.clicked.connect(self.calculate_life)
        layout.addWidget(calc_btn)

        self.setLayout(layout)

    def calculate_life(self):
        if self.analysis_mode_box.currentText() == "Stress-Life / HCF":
            self.calculate_hcf()
        else:
            self.calculate_lcf()

    def calculate_lcf(self):
        try:
            sigma_max = float(self.sigma_max_input.text())
            sigma_min = float(self.sigma_min_input.text())
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter valid numeric values for both maximum and minimum stress."
            )
            return

        if sigma_max < sigma_min:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Maximum stress must be greater than or equal to minimum stress."
            )
            return

        mat = self.materials[self.material_box.currentText()]
        E, K_dash, n_dash = mat["E"], mat["K_dash"], mat["n_dash"]
        sigma_f_dash, b = mat["sigma_f_dash"], mat["b"]
        epsilon_f_dash, c = mat["epsilon_f_dash"], mat["c"]

        sigma_a = abs(sigma_max - sigma_min) / 2
        sigma_m = (sigma_max + sigma_min) / 2

        if sigma_a <= 0:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Calculated stress amplitude must be greater than zero."
            )
            return

        elastic_strain = sigma_a / E
        plastic_strain = (sigma_a / K_dash) ** (1 / n_dash)
        strain_amplitude = elastic_strain + plastic_strain

        solve_result = self.solve_life(
            strain_amplitude, E, sigma_f_dash, b, epsilon_f_dash, c
        )
        if solve_result is None:
            QMessageBox.warning(
                self,
                "No Valid Solution",
                "A valid fatigue life could not be bracketed for the selected material and stress inputs."
            )
            self.result_label.setText(
                "Stress Amplitude (MPa): -\n"
                "Mean Stress (MPa): -\n"
                "Elastic Strain Amplitude: -\n"
                "Plastic Strain Amplitude: -\n"
                "Total Strain Amplitude: -\n"
                "Estimated Life (cycles): -\n"
                "Reversals to Failure (2Nf): -"
            )
            self.ax.clear()
            self.canvas.draw()
            return

        estimated_life, reversals_to_failure, plot_cycles, rhs, lhs = solve_result

        self.result_label.setText(
            f"Stress Amplitude (MPa): {sigma_a:,.6g}\n"
            f"Mean Stress (MPa): {sigma_m:,.6g}\n"
            f"Elastic Strain Amplitude: {elastic_strain:,.6g}\n"
            f"Plastic Strain Amplitude: {plastic_strain:,.6g}\n"
            f"Total Strain Amplitude: {strain_amplitude:,.6g}\n"
            f"Estimated Life (cycles): {estimated_life:,}\n"
            f"Reversals to Failure (2Nf): {reversals_to_failure:,}"
        )

        self.ax.clear()
        self.ax.set_xscale("log")
        self.ax.set_title("Strain-Life Curve")
        self.ax.set_xlabel("2Nf (Reversals)")
        self.ax.set_ylabel("Strain Amplitude")
        self.ax.grid(True, which='both', linestyle='--', linewidth=0.5)
        self.ax.plot(2 * plot_cycles, rhs, label="Material Curve")
        self.ax.plot(2 * estimated_life, lhs, 'ro', label="Your Result")
        self.ax.legend()
        self.canvas.draw()

    def calculate_hcf(self):
        try:
            sigma_max = float(self.sigma_max_input.text())
            sigma_min = float(self.sigma_min_input.text())
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter valid numeric values for both maximum and minimum stress."
            )
            return

        if sigma_max < sigma_min:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Maximum stress must be greater than or equal to minimum stress."
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
                "Standalone metallic Basquin HCF estimation is not enabled for this material."
            )
            self.result_label.setText(
                "Analysis Mode: Stress-Life / HCF\n"
                "Standalone metallic Basquin HCF estimation is not enabled for this material."
            )
            self.ax.clear()
            self.canvas.draw()
            return

        mat = self.materials[material_name]
        sigma_f_dash = mat["sigma_f_dash"]
        b = mat["b"]

        sigma_a = abs(sigma_max - sigma_min) / 2
        sigma_m = (sigma_max + sigma_min) / 2

        if not np.isfinite(sigma_a) or sigma_a <= 0:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Calculated stress amplitude must be greater than zero."
            )
            return

        if not np.isfinite(sigma_f_dash) or sigma_f_dash <= 0:
            QMessageBox.warning(
                self,
                "Invalid Material Data",
                "Fatigue strength coefficient must be positive and finite for Basquin HCF."
            )
            return

        if not np.isfinite(b) or b >= 0:
            QMessageBox.warning(
                self,
                "Invalid Material Data",
                "Fatigue strength exponent must be negative for a valid Basquin HCF relation."
            )
            return

        ratio = sigma_a / sigma_f_dash
        if not np.isfinite(ratio) or ratio <= 0:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "A valid positive stress amplitude is required for Basquin HCF."
            )
            return

        reversals_to_failure = np.power(ratio, 1.0 / b)
        estimated_life = 0.5 * reversals_to_failure

        if not np.isfinite(reversals_to_failure) or not np.isfinite(estimated_life):
            QMessageBox.warning(
                self,
                "No Valid Solution",
                "The HCF life calculation produced a non-finite result."
            )
            return

        if reversals_to_failure <= 0 or estimated_life <= 0:
            QMessageBox.warning(
                self,
                "No Valid Solution",
                "The HCF life calculation produced a non-positive result."
            )
            return

        plot_reversals, plot_curve = self.build_hcf_curve(estimated_life, sigma_f_dash, b)
        if plot_reversals is None:
            QMessageBox.warning(
                self,
                "No Valid Solution",
                "The HCF curve could not be generated for the selected material and stress inputs."
            )
            return

        life_text = self.format_life_value(estimated_life)
        reversals_text = self.format_life_value(reversals_to_failure)

        self.result_label.setText(
            "Analysis Mode: Stress-Life / HCF\n"
            f"Maximum Stress (MPa): {sigma_max:,.6g}\n"
            f"Minimum Stress (MPa): {sigma_min:,.6g}\n"
            f"Stress Amplitude (MPa): {sigma_a:,.6g}\n"
            f"Mean Stress (MPa): {sigma_m:,.6g}\n"
            f"Estimated Life (cycles): {life_text}\n"
            f"Reversals to Failure (2Nf): {reversals_text}\n"
            "Mean stress calculated but not corrected.\n"
            "Basquin stress-life estimate; intended for elastic-dominated HCF.\n"
            "Material fatigue constants do not currently include calibration-range metadata; extrapolated HCF life should be treated as an engineering estimate."
        )

        self.ax.clear()
        self.ax.set_xscale("log")
        self.ax.set_yscale("log")
        self.ax.set_title("Stress-Life (Basquin) Curve")
        self.ax.set_xlabel("2Nf (Reversals)")
        self.ax.set_ylabel("Stress Amplitude (MPa)")
        self.ax.grid(True, which='both', linestyle='--', linewidth=0.5)
        self.ax.plot(plot_reversals, plot_curve, label="Basquin Curve")
        self.ax.plot(reversals_to_failure, sigma_a, 'ro', label="Your Result")
        self.ax.legend()
        self.canvas.draw()

    def strain_life_rhs(self, Nf, E, sigma_f_dash, b, epsilon_f_dash, c):
        reversals = 2.0 * Nf
        return (sigma_f_dash / E) * reversals ** b + epsilon_f_dash * reversals ** c

    def build_hcf_curve(self, estimated_life, sigma_f_dash, b):
        reversals_to_failure = 2.0 * estimated_life
        if not np.isfinite(reversals_to_failure) or reversals_to_failure <= 0:
            return None, None

        plot_lower = max(1e-12, reversals_to_failure / 1e4)
        plot_upper = max(plot_lower * 10.0, reversals_to_failure * 1e4)
        if not np.isfinite(plot_lower) or not np.isfinite(plot_upper) or plot_lower <= 0 or plot_upper <= plot_lower:
            return None, None

        plot_reversals = np.logspace(np.log10(plot_lower), np.log10(plot_upper), 1000)
        with np.errstate(over='ignore', under='ignore', invalid='ignore'):
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
        reversals_to_failure = int(round(2.0 * estimated_life))
        estimated_life = int(round(estimated_life))

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
