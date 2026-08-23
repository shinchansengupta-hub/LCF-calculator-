import os
import sys
import csv
from types import SimpleNamespace
from dataclasses import dataclass
import numpy as np

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QComboBox,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QCheckBox,
    QPlainTextEdit,
    QSizePolicy,
    QTabWidget,
)
from PyQt5.QtCore import Qt

import matplotlib

matplotlib.use("Qt5Agg")

from PyQt5.QtGui import QIcon
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from material_properties import get_property
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
from fatigue_validation import ComparisonModelResult, ComparisonSummary


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


def is_finite_number(value):
    try:
        return value is not None and np.isfinite(float(value))
    except (TypeError, ValueError):
        return False


FULL_AVAILABILITY = "FULL"
LEGACY_FALLBACK_REQUIRED = "LEGACY_FALLBACK_REQUIRED"
ESTIMATED_PARAMETER_REQUIRED = "ESTIMATED_PARAMETER_REQUIRED"
READY_WITH_CONDITION_WARNING = "READY_WITH_CONDITION_WARNING"
UNAVAILABLE_CORRECTION = "UNAVAILABLE"

STRESS_SOURCE_LINEAR_FEA = "Local stress from linear-elastic FEA"
STRESS_SOURCE_ELASTIC_PLASTIC_FEA = "Local stress/strain from elastic-plastic FEA"
STRESS_SOURCE_NOMINAL = "Nominal analytical stress"

NOTCH_TREATMENT_NONE = "None"
NOTCH_TREATMENT_DIRECT_KF = "Direct K_f"
NOTCH_TREATMENT_KT_Q = "K_t + q"
NOTCH_TREATMENT_CONSERVATIVE_KT = "Conservative K_t as K_f"

LCF_LOCAL_CORRECTION_NONE = "None"
LCF_LOCAL_CORRECTION_NEUBER = "Neuber"
LCF_NEUBER_BASIS_ORIGINAL_KT = "Original Neuber: K_t"
LCF_NEUBER_BASIS_DIRECT_KF = "Fatigue-modified Neuber: direct K_f"
LCF_NEUBER_BASIS_KT_Q = "Fatigue-modified Neuber: K_t + q"

SIMPLE_LCF_NEUBER_UNRESOLVED_REASON = (
    "Simple amplitude Neuber does not establish defensible local mean or maximum stress required by this model."
)

WALKER_NOMINAL_NOTCH_UNRESOLVED_REASON = (
    "Walker nominal-notch transformation is not yet supported because a defensible notch-adjusted sigma_max convention has not been established."
)


@dataclass(frozen=True)
class CorrectionAvailability:
    method_name: str
    enabled: bool
    availability_type: str
    reason: str


class FatiguePlotWindow(QWidget):
    def __init__(self, title):
        super().__init__()
        self.plot_title_label = QLabel(title)
        self.plot_title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.plot_title_label)
        self.canvas = FigureCanvas(Figure(figsize=(9, 6.5)))
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        self.ax = self.canvas.figure.add_subplot(111)
        self.setLayout(layout)

    def set_plot_title(self, title):
        self.plot_title_label.setText(title)

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
        self.walker_rows = self.load_table_rows(resource_path("materials_walker.csv"))

        self.init_ui()
        self.resize(600, 700)
        self.setMinimumSize(560, 680)

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
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        title = QLabel("Low Cycle Fatigue Life Estimator")
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        main_layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.tabs, 1)

        input_tab = QWidget()
        input_layout = QVBoxLayout(input_tab)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(8)
        input_layout.setAlignment(Qt.AlignTop)

        setup_group = QGroupBox("Analysis Setup")
        setup_layout = QFormLayout(setup_group)
        setup_layout.setContentsMargins(10, 10, 10, 10)
        setup_layout.setSpacing(6)
        setup_layout.setLabelAlignment(Qt.AlignLeft)

        self.stress_source_box = QComboBox()
        self.stress_source_box.addItems(
            [
                STRESS_SOURCE_LINEAR_FEA,
                STRESS_SOURCE_ELASTIC_PLASTIC_FEA,
                STRESS_SOURCE_NOMINAL,
            ]
        )
        self.stress_source_box.setCurrentText(STRESS_SOURCE_LINEAR_FEA)
        self.stress_source_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        setup_layout.addRow("Stress Source", self.stress_source_box)

        self.material_box = QComboBox()
        self.material_box.addItems(self.materials.keys())
        self.material_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        setup_layout.addRow("Material", self.material_box)

        self.analysis_mode_box = QComboBox()
        self.analysis_mode_box.addItems(["Strain-Life / LCF", "Stress-Life / HCF"])
        self.analysis_mode_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        setup_layout.addRow("Analysis Mode", self.analysis_mode_box)

        self.mean_stress_box = QComboBox()
        self.mean_stress_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        setup_layout.addRow("Mean Stress Correction", self.mean_stress_box)

        self.local_correction_box = QComboBox()
        self.local_correction_box.addItems([LCF_LOCAL_CORRECTION_NONE, LCF_LOCAL_CORRECTION_NEUBER])
        self.local_correction_box.setCurrentText(LCF_LOCAL_CORRECTION_NONE)
        self.local_correction_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        setup_layout.addRow("Local Elastic-Plastic Correction", self.local_correction_box)

        self.correction_status_label = QLabel("Correction availability: -")
        self.correction_status_label.setWordWrap(True)
        self.correction_status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        setup_layout.addRow("", self.correction_status_label)
        input_layout.addWidget(setup_group)

        self.analysis_mode_box.currentTextChanged.connect(self.update_mean_stress_options)
        self.update_mean_stress_options(self.analysis_mode_box.currentText())

        temperature_layout = QHBoxLayout()
        temperature_layout.setContentsMargins(0, 0, 0, 0)
        temperature_layout.setSpacing(8)
        temperature_layout.addWidget(QLabel("Analysis Temperature (°C)"))
        self.analysis_temperature_input = QLineEdit()
        self.analysis_temperature_input.setText("21")
        self.analysis_temperature_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        temperature_layout.addWidget(self.analysis_temperature_input)
        input_layout.addLayout(temperature_layout)

        options_group = QGroupBox("Analysis Options")
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(10, 10, 10, 10)
        options_layout.setSpacing(6)

        self.legacy_fallback_box = QCheckBox(
            "Use legacy fatigue constants when temperature-resolved fatigue data are unavailable"
        )
        self.legacy_fallback_box.setChecked(False)
        self.legacy_fallback_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        options_layout.addWidget(self.legacy_fallback_box)

        self.estimated_walker_box = QCheckBox(
            "Use estimated Walker gamma when calibrated gamma is unavailable"
        )
        self.estimated_walker_box.setChecked(False)
        self.estimated_walker_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        options_layout.addWidget(self.estimated_walker_box)
        input_layout.addWidget(options_group)

        loading_group = QGroupBox("Loading")
        loading_layout = QFormLayout(loading_group)
        loading_layout.setContentsMargins(10, 10, 10, 10)
        loading_layout.setSpacing(6)
        loading_layout.setLabelAlignment(Qt.AlignLeft)

        self.sigma_max_input = QLineEdit()
        self.sigma_max_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        loading_layout.addRow("Signed sigma_max (MPa)", self.sigma_max_input)

        self.sigma_min_input = QLineEdit()
        self.sigma_min_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        loading_layout.addRow("Signed sigma_min (MPa)", self.sigma_min_input)

        self.local_strain_input = QLineEdit()
        self.local_strain_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.local_strain_input.setPlaceholderText("Reserved for later direct strain input")
        loading_layout.addRow("Total strain amplitude", self.local_strain_input)
        input_layout.addWidget(loading_group)

        self.lcf_neuber_group = QGroupBox("LCF Neuber Factor Basis")
        lcf_neuber_layout = QFormLayout(self.lcf_neuber_group)
        lcf_neuber_layout.setContentsMargins(10, 10, 10, 10)
        lcf_neuber_layout.setSpacing(6)
        lcf_neuber_layout.setLabelAlignment(Qt.AlignLeft)

        self.lcf_neuber_basis_box = QComboBox()
        self.lcf_neuber_basis_box.addItems(
            [
                LCF_NEUBER_BASIS_ORIGINAL_KT,
                LCF_NEUBER_BASIS_DIRECT_KF,
                LCF_NEUBER_BASIS_KT_Q,
            ]
        )
        self.lcf_neuber_basis_box.setCurrentText(LCF_NEUBER_BASIS_ORIGINAL_KT)
        self.lcf_neuber_basis_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lcf_neuber_layout.addRow("Neuber Factor Basis", self.lcf_neuber_basis_box)

        self.lcf_kt_input = QLineEdit()
        self.lcf_kt_input.setPlaceholderText("K_t")
        lcf_neuber_layout.addRow("K_t", self.lcf_kt_input)

        self.lcf_q_input = QLineEdit()
        self.lcf_q_input.setPlaceholderText("q")
        lcf_neuber_layout.addRow("q", self.lcf_q_input)

        self.lcf_kf_input = QLineEdit()
        self.lcf_kf_input.setPlaceholderText("K_f")
        lcf_neuber_layout.addRow("K_f", self.lcf_kf_input)

        self.lcf_neuber_computed_label = QLabel("K_f used: -")
        self.lcf_neuber_computed_label.setWordWrap(True)
        lcf_neuber_layout.addRow("", self.lcf_neuber_computed_label)

        self.lcf_neuber_status_label = QLabel(
            "Simple scalar Neuber is available only for LCF + None."
        )
        self.lcf_neuber_status_label.setWordWrap(True)
        lcf_neuber_layout.addRow("", self.lcf_neuber_status_label)
        input_layout.addWidget(self.lcf_neuber_group)

        self.notch_group = QGroupBox("Future Nominal-Stress Notch Inputs")
        notch_layout = QFormLayout(self.notch_group)
        notch_layout.setContentsMargins(10, 10, 10, 10)
        notch_layout.setSpacing(6)

        self.notch_treatment_box = QComboBox()
        self.notch_treatment_box.addItems(
            [
                NOTCH_TREATMENT_NONE,
                NOTCH_TREATMENT_DIRECT_KF,
                NOTCH_TREATMENT_KT_Q,
                NOTCH_TREATMENT_CONSERVATIVE_KT,
            ]
        )
        self.notch_treatment_box.setCurrentText(NOTCH_TREATMENT_NONE)
        self.notch_treatment_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        notch_layout.addRow("Notch Treatment", self.notch_treatment_box)

        self.kt_input = QLineEdit()
        self.kt_input.setPlaceholderText("K_t")
        notch_layout.addRow("K_t", self.kt_input)

        self.q_input = QLineEdit()
        self.q_input.setPlaceholderText("q")
        notch_layout.addRow("q", self.q_input)

        self.kf_input = QLineEdit()
        self.kf_input.setPlaceholderText("K_f")
        notch_layout.addRow("K_f", self.kf_input)

        self.notch_computed_label = QLabel("K_f used: -")
        self.notch_computed_label.setWordWrap(True)
        notch_layout.addRow("", self.notch_computed_label)

        self.notch_status_label = QLabel(
            "Nominal-stress notch correction is not yet enabled."
        )
        self.notch_status_label.setWordWrap(True)
        notch_layout.addRow("", self.notch_status_label)
        input_layout.addWidget(self.notch_group)

        self.guidance_text = QPlainTextEdit()
        self.guidance_text.setReadOnly(True)
        self.guidance_text.setMaximumHeight(140)
        self.guidance_text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.guidance_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        guidance_group = QGroupBox("Model-Specific Guidance")
        guidance_layout = QVBoxLayout(guidance_group)
        guidance_layout.setContentsMargins(10, 10, 10, 10)
        guidance_layout.addWidget(self.guidance_text)
        input_layout.addWidget(guidance_group)

        calc_btn = QPushButton("Calculate Fatigue Life")
        calc_btn.clicked.connect(self.calculate_life)
        calc_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        input_layout.addWidget(calc_btn)

        compare_btn = QPushButton("Compare Applicable Models")
        compare_btn.clicked.connect(self.compare_applicable_models)
        compare_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        input_layout.addWidget(compare_btn)
        input_layout.addStretch(1)

        results_tab = QWidget()
        results_tab_layout = QVBoxLayout(results_tab)
        results_tab_layout.setContentsMargins(8, 8, 8, 8)
        results_tab_layout.setSpacing(8)
        results_group = QGroupBox("Analysis Results")
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(10, 10, 10, 10)
        results_layout.setSpacing(6)

        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(320)
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
        results_layout.addWidget(self.result_text)
        results_tab_layout.addWidget(results_group)

        graphs_tab = QWidget()
        graphs_layout = QVBoxLayout(graphs_tab)
        graphs_layout.setContentsMargins(8, 8, 8, 8)
        graphs_layout.setSpacing(8)
        self.plot_window = FatiguePlotWindow("Fatigue Graphs")
        graphs_layout.addWidget(self.plot_window)

        self.tabs.addTab(input_tab, "Input")
        self.tabs.addTab(results_tab, "Results")
        self.tabs.addTab(graphs_tab, "Graphs")
        self.setLayout(main_layout)
        self.material_box.currentTextChanged.connect(self.refresh_correction_availability)
        self.analysis_temperature_input.textChanged.connect(self.refresh_correction_availability)
        self.legacy_fallback_box.stateChanged.connect(self.refresh_correction_availability)
        self.estimated_walker_box.stateChanged.connect(self.refresh_correction_availability)
        self.stress_source_box.currentTextChanged.connect(self.update_stress_source_ui)
        self.local_correction_box.currentTextChanged.connect(self.update_lcf_local_correction_ui)
        self.lcf_neuber_basis_box.currentTextChanged.connect(self.update_lcf_local_correction_ui)
        self.lcf_kt_input.textChanged.connect(self.refresh_correction_availability)
        self.lcf_q_input.textChanged.connect(self.refresh_correction_availability)
        self.lcf_kf_input.textChanged.connect(self.refresh_correction_availability)
        self.notch_treatment_box.currentTextChanged.connect(self.update_notch_treatment_ui)
        self.stress_source_box.currentTextChanged.connect(self.update_model_guidance)
        self.analysis_mode_box.currentTextChanged.connect(self.update_model_guidance)
        self.analysis_mode_box.currentTextChanged.connect(self.update_lcf_local_correction_ui)
        self.mean_stress_box.currentTextChanged.connect(self.update_model_guidance)
        self.material_box.currentTextChanged.connect(self.update_model_guidance)
        self.analysis_temperature_input.textChanged.connect(self.update_model_guidance)
        self.kt_input.textChanged.connect(self.refresh_correction_availability)
        self.q_input.textChanged.connect(self.refresh_correction_availability)
        self.kf_input.textChanged.connect(self.refresh_correction_availability)
        self.notch_treatment_box.currentTextChanged.connect(self.refresh_correction_availability)
        self.update_stress_source_ui()
        self.update_model_guidance()
        self.refresh_correction_availability()
        self.last_comparison_result = None
        self.resize(1100, 720)
        self.setMinimumSize(1000, 700)

    def calculate_life(self):
        if self.analysis_mode_box.currentText() == "Stress-Life / HCF":
            self.calculate_hcf()
        else:
            self.calculate_lcf()

    def compare_applicable_models(self):
        sigma_max, sigma_min = self.parse_stress_inputs()
        if sigma_max is None:
            return

        temperature = self.parse_temperature()
        if temperature is None:
            self.show_blocked_result(
                "Invalid Input",
                "Please enter a valid numeric and finite analysis temperature.",
            )
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter a valid numeric and finite analysis temperature.",
            )
            return

        material_name = self.material_box.currentText()
        analysis_mode = self.normalize_mode_name(self.analysis_mode_box.currentText())
        if analysis_mode not in {"LCF", "HCF"}:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please select a valid analysis mode before running a comparison.",
            )
            return

        legacy_fallback = self.legacy_fallback_box.isChecked()
        allow_estimated_walker = self.estimated_walker_box.isChecked()
        static_condition, fatigue_condition = self.get_temperature_conditions(material_name)
        walker_condition = self.get_walker_condition(material_name)
        capability = assess_temperature_capability(
            material_name,
            temperature,
            analysis_mode,
            self.mean_stress_box.currentText(),
            self.static_rows,
            self.fatigue_rows,
            walker_rows=self.walker_rows,
            static_condition=static_condition,
            fatigue_condition=fatigue_condition,
            walker_condition=walker_condition,
        )
        availability = self.get_available_corrections(
            material_name,
            temperature,
            analysis_mode,
            legacy_fallback,
            allow_estimated_walker,
            self.static_rows,
            self.fatigue_rows,
            self.walker_rows,
        )

        summary = self.build_comparison_summary(
            material_name,
            temperature,
            self.analysis_mode_box.currentText(),
            sigma_max,
            sigma_min,
            capability,
            availability,
            legacy_fallback,
            allow_estimated_walker,
        )
        self.last_comparison_result = summary
        self.set_result_text(self.format_comparison_summary(summary))
        self.show_comparison_plot(summary)

    def update_mean_stress_options(self, mode=None):
        if mode is None:
            mode = self.analysis_mode_box.currentText()
        mode = self.normalize_mode_name(mode)

        options = ["None"]
        if mode == "LCF":
            if hasattr(self, "local_correction_box") and self.local_correction_box.currentText() == LCF_LOCAL_CORRECTION_NEUBER:
                options = ["None"]
            else:
                options.extend(["Morrow", "Walker", "SWT"])
        elif mode == "HCF":
            options.extend(["Goodman", "Walker"])

        self.mean_stress_box.blockSignals(True)
        self.mean_stress_box.clear()
        self.mean_stress_box.addItems(options)
        self.mean_stress_box.setCurrentIndex(0)
        self.mean_stress_box.blockSignals(False)
        if hasattr(self, "analysis_temperature_input"):
            self.refresh_correction_availability()
        if hasattr(self, "guidance_text"):
            self.update_model_guidance()

    def update_stress_source_ui(self, *args):
        source = self.stress_source_box.currentText()
        is_elastic_plastic_fea = source == STRESS_SOURCE_ELASTIC_PLASTIC_FEA
        is_nominal = source == STRESS_SOURCE_NOMINAL
        is_hcf = self.normalize_mode_name(self.analysis_mode_box.currentText()) == "HCF"

        self.local_strain_input.setVisible(is_elastic_plastic_fea)
        self.local_strain_input.setEnabled(is_elastic_plastic_fea)
        show_notch_group = is_nominal and is_hcf
        self.notch_group.setVisible(show_notch_group)
        self.notch_group.setEnabled(is_nominal and is_hcf)

        if not show_notch_group:
            self.notch_status_label.setText(
                "Notch geometry is assumed to be resolved by FEA; K_t/K_f is not reapplied."
            )

        self.update_lcf_local_correction_ui()
        self.update_model_guidance()
        self.update_notch_treatment_ui()

    def update_lcf_local_correction_ui(self, *args):
        source = self.stress_source_box.currentText()
        mode = self.normalize_mode_name(self.analysis_mode_box.currentText())
        is_lcf = mode == "LCF"
        is_linear_fea = source == STRESS_SOURCE_LINEAR_FEA
        is_elastic_plastic = source == STRESS_SOURCE_ELASTIC_PLASTIC_FEA
        is_nominal = source == STRESS_SOURCE_NOMINAL
        local_correction = self.local_correction_box.currentText() if hasattr(self, "local_correction_box") else LCF_LOCAL_CORRECTION_NONE

        show_local_correction = is_lcf and not is_elastic_plastic
        self.local_correction_box.setVisible(show_local_correction)
        self.local_correction_box.setEnabled(show_local_correction)
        if not show_local_correction:
            self.local_correction_box.blockSignals(True)
            self.local_correction_box.setCurrentText(LCF_LOCAL_CORRECTION_NONE)
            self.local_correction_box.blockSignals(False)
            local_correction = LCF_LOCAL_CORRECTION_NONE

        show_lcf_neuber_group = is_lcf and local_correction == LCF_LOCAL_CORRECTION_NEUBER and is_nominal
        self.lcf_neuber_group.setVisible(show_lcf_neuber_group)
        self.lcf_neuber_group.setEnabled(show_lcf_neuber_group)

        if show_lcf_neuber_group:
            basis = self.lcf_neuber_basis_box.currentText()
            show_k_t = basis in {LCF_NEUBER_BASIS_ORIGINAL_KT, LCF_NEUBER_BASIS_KT_Q}
            show_q = basis == LCF_NEUBER_BASIS_KT_Q
            show_k_f = basis == LCF_NEUBER_BASIS_DIRECT_KF
            self.set_lcf_neuber_row_visibility(self.lcf_kt_input, show_k_t)
            self.set_lcf_neuber_row_visibility(self.lcf_q_input, show_q)
            self.set_lcf_neuber_row_visibility(self.lcf_kf_input, show_k_f)
        else:
            self.set_lcf_neuber_row_visibility(self.lcf_kt_input, False)
            self.set_lcf_neuber_row_visibility(self.lcf_q_input, False)
            self.set_lcf_neuber_row_visibility(self.lcf_kf_input, False)

        lcf_state = self.resolve_lcf_neuber_state(0.0, 0.0, stress_source=source, analysis_mode=mode)
        if show_lcf_neuber_group:
            if lcf_state["valid"] and lcf_state["basis_code"] == "ORIGINAL_NEUBER_KT" and lcf_state.get("k_t") is not None:
                self.lcf_neuber_computed_label.setText(f"K_t used: {lcf_state['k_t']:,.6g}")
            elif lcf_state["valid"] and lcf_state.get("k_f") is not None:
                self.lcf_neuber_computed_label.setText(f"K_f used: {lcf_state['k_f']:,.6g} | {lcf_state['basis']}")
            else:
                self.lcf_neuber_computed_label.setText(f"K_f used: - | {lcf_state.get('reason') or lcf_state['basis']}")
            self.lcf_neuber_status_label.setText(
                "Fatigue-modified Neuber uses an explicit factor basis for nominal stress; local mean/max stress are not reconstructed."
            )
        elif is_lcf and local_correction == LCF_LOCAL_CORRECTION_NEUBER and is_linear_fea:
            self.lcf_neuber_computed_label.setText("K_f used: -")
            self.lcf_neuber_status_label.setText(
                "ANSYS local elastic stress is used directly as the Neuber pseudo-elastic reference. K_t/K_f is not reapplied."
            )
        elif is_elastic_plastic:
            self.lcf_neuber_computed_label.setText("K_f used: -")
            self.lcf_neuber_status_label.setText(
                "Local plasticity is assumed to be resolved by nonlinear FEA; Neuber correction is bypassed."
            )
        elif is_lcf:
            self.lcf_neuber_computed_label.setText("K_f used: -")
            self.lcf_neuber_status_label.setText(
                "Simple amplitude Neuber is available only for local elastic FEA or nominal analytical stress."
            )
        else:
            self.lcf_neuber_computed_label.setText("K_f used: -")
            self.lcf_neuber_status_label.setText(
                "Simple amplitude Neuber is unavailable outside LCF."
            )

        if hasattr(self, "mean_stress_box"):
            self.update_mean_stress_options(mode)
        if hasattr(self, "guidance_text"):
            self.update_model_guidance()
        self.refresh_correction_availability()

    def update_notch_treatment_ui(self, *args):
        source = self.stress_source_box.currentText()
        is_nominal = source == STRESS_SOURCE_NOMINAL
        is_nominal_hcf = is_nominal and self.normalize_mode_name(self.analysis_mode_box.currentText()) == "HCF"
        treatment = self.notch_treatment_box.currentText()

        show_group = is_nominal_hcf
        self.notch_group.setVisible(show_group)
        self.notch_group.setEnabled(is_nominal_hcf)

        if not show_group:
            self.set_notch_row_visibility(self.kt_input, False)
            self.set_notch_row_visibility(self.q_input, False)
            self.set_notch_row_visibility(self.kf_input, False)
            self.notch_computed_label.setText("K_f used: -")
            return

        show_k_t = treatment in {NOTCH_TREATMENT_KT_Q, NOTCH_TREATMENT_CONSERVATIVE_KT}
        show_q = treatment == NOTCH_TREATMENT_KT_Q
        show_k_f = treatment == NOTCH_TREATMENT_DIRECT_KF

        self.set_notch_row_visibility(self.kt_input, show_k_t)
        self.set_notch_row_visibility(self.q_input, show_q)
        self.set_notch_row_visibility(self.kf_input, show_k_f)

        context = self.parse_nominal_notch_state()
        if context["active"] and context["valid"]:
            self.notch_computed_label.setText(
                "K_f used: {0:,.6g} | {1}".format(context["k_f"], context["basis"])
            )
        elif context["active"]:
            self.notch_computed_label.setText("K_f used: - | " + context["reason"])
        else:
            self.notch_computed_label.setText("K_f used: -")

        if context["active"] and not context["valid"]:
            self.notch_status_label.setText(context["reason"])
        elif context["active"]:
            self.notch_status_label.setText(
                "Pseudo-cycle values are reconstructed for calculation plumbing and are not physical notch-root extrema."
            )
        else:
            self.notch_status_label.setText(
                "Nominal-stress notch correction is not yet enabled."
            )

        self.update_model_guidance()
        self.refresh_correction_availability()

    def set_form_row_visibility(self, form_group, widget, visible):
        label = form_group.layout().labelForField(widget)
        if label is not None:
            label.setVisible(visible)
        widget.setVisible(visible)
        widget.setEnabled(visible)

    def set_notch_row_visibility(self, widget, visible):
        self.set_form_row_visibility(self.notch_group, widget, visible)

    def set_lcf_neuber_row_visibility(self, widget, visible):
        self.set_form_row_visibility(self.lcf_neuber_group, widget, visible)

    def update_model_guidance(self, *args):
        if not hasattr(self, "guidance_text"):
            return

        source = self.stress_source_box.currentText()
        mode = self.normalize_mode_name(self.analysis_mode_box.currentText())
        correction = self.mean_stress_box.currentText()
        material = self.material_box.currentText()
        temperature = self.analysis_temperature_input.text()
        notch_state = self.parse_nominal_notch_state()

        lines = [
            f"Stress source: {source}",
            f"Material / temperature: {material} at {temperature} C",
        ]

        if source == STRESS_SOURCE_LINEAR_FEA:
            lines.extend(
                [
                    "Use signed local sigma_max and sigma_min from the same hotspot and same physical stress direction/component.",
                    "Geometry stress concentration is assumed to be resolved by FEA. Do not apply K_t again.",
                    "For Goodman/Walker mean-stress correction, do not use Equivalent (von Mises) Stress as sigma_max/sigma_min because sign and R information are lost.",
                ]
            )
        elif source == STRESS_SOURCE_ELASTIC_PLASTIC_FEA:
            lines.extend(
                [
                    "Use signed local sigma_max and sigma_min from the same hotspot and same physical stress direction/component.",
                    "Direct elastic-plastic FEA strain input is reserved for a later solver integration.",
                    "Do not apply K_t or Neuber to local elastic-plastic FEA output that already resolves local plasticity.",
                    "For Goodman/Walker mean-stress correction, do not use Equivalent (von Mises) Stress as sigma_max/sigma_min because sign and R information are lost.",
                ]
            )
        elif source == STRESS_SOURCE_NOMINAL:
            local_correction = self.local_correction_box.currentText() if hasattr(self, "local_correction_box") else LCF_LOCAL_CORRECTION_NONE
            lines.extend(
                [
                    "Use signed nominal sigma_max and sigma_min for the same physical stress direction/component.",
                ]
            )
            if mode == "HCF" and notch_state["active"]:
                lines.append("Do not silently multiply stresses by K_t; HCF nominal-notch correction uses an explicit factor basis.")
                lines.append(f"Notch treatment: {notch_state['treatment']}")
                lines.append(f"K_f used: {notch_state.get('k_f_label', '-')}")
                if notch_state.get("basis"):
                    lines.append(f"K_f basis: {notch_state['basis']}")
                if notch_state.get("k_t") is not None:
                    lines.append(f"K_t: {notch_state['k_t']:,.6g}")
                if notch_state.get("q") is not None:
                    lines.append(f"q: {notch_state['q']:,.6g}")
                if notch_state.get("k_f") is not None:
                    lines.append(f"K_f: {notch_state['k_f']:,.6g}")
            elif mode == "HCF":
                lines.append("HCF nominal-stress notch correction is available through an explicit factor basis.")
                lines.append("Notch treatment: None")
            elif mode == "LCF" and local_correction == LCF_LOCAL_CORRECTION_NEUBER:
                lines.append("LCF Neuber uses an explicit factor basis for nominal stress; local mean/max stress are not reconstructed.")
                lines.append("Nominal analytical stress uses simple scalar Neuber when Local Elastic-Plastic Correction is set to Neuber.")
            elif mode == "LCF":
                lines.append("Nominal analytical stress uses the existing LCF strain-life relation without local elastic-plastic correction.")

        if correction == "Goodman" and mode == "HCF":
            lines.append(
                "Goodman HCF: use signed local normal stress; von Mises is not suitable for sigma_m/R evaluation."
            )
        elif correction == "Walker":
            if source == STRESS_SOURCE_NOMINAL and notch_state["active"]:
                lines.append(WALKER_NOMINAL_NOTCH_UNRESOLVED_REASON)
            else:
                lines.append(
                    "Walker: use signed local normal stress in a consistent direction; Walker requires a positive sigma_max under the current formulation."
                )
        elif correction == "SWT":
            lines.append("SWT LCF: requires positive sigma_max and total strain amplitude.")
        elif correction == "Morrow":
            lines.append("Morrow: requires signed mean stress and strain-life constants.")
        else:
            lines.append("None: no Walker/SWT-specific positive sigma_max restriction is imposed.")

        lines.append(
            "Hotspot stresses must be physically meaningful and mesh-converged; mathematical singularities are not valid fatigue inputs."
        )
        self.guidance_text.setPlainText("\n".join(lines))

    def parse_nominal_notch_state(self):
        source = self.stress_source_box.currentText()
        mode = self.normalize_mode_name(self.analysis_mode_box.currentText())
        treatment = self.notch_treatment_box.currentText()
        if source != STRESS_SOURCE_NOMINAL or mode != "HCF":
            return {
                "applies": False,
                "active": False,
                "valid": True,
                "treatment": NOTCH_TREATMENT_NONE,
                "basis": "",
                "reason": "",
                "k_t": None,
                "q": None,
                "k_f": None,
                "k_f_label": "-",
                "conservative": False,
                "pseudo_cycle": False,
            }

        if treatment == NOTCH_TREATMENT_NONE:
            return {
                "applies": True,
                "active": False,
                "valid": True,
                "treatment": treatment,
                "basis": "No notch correction.",
                "reason": "",
                "k_t": None,
                "q": None,
                "k_f": None,
                "k_f_label": "-",
                "conservative": False,
                "pseudo_cycle": False,
            }

        k_t = parse_optional_float(self.kt_input.text())
        q = parse_optional_float(self.q_input.text())
        k_f = parse_optional_float(self.kf_input.text())

        if treatment == NOTCH_TREATMENT_DIRECT_KF:
            if k_f is None or not np.isfinite(k_f) or k_f < 1:
                return {
                    "applies": True,
                    "active": True,
                    "valid": False,
                    "treatment": treatment,
                    "basis": "Direct K_f input",
                    "reason": "Direct K_f mode requires a finite K_f >= 1.",
                    "k_t": k_t,
                    "q": q,
                    "k_f": k_f,
                    "k_f_label": "-",
                    "conservative": False,
                    "pseudo_cycle": True,
                }
            return {
                "applies": True,
                "active": True,
                "valid": True,
                "treatment": treatment,
                "basis": "Direct K_f input",
                "reason": "",
                "k_t": k_t,
                "q": q,
                "k_f": k_f,
                "k_f_label": f"{k_f:,.6g}",
                "conservative": False,
                "pseudo_cycle": True,
            }

        if treatment == NOTCH_TREATMENT_KT_Q:
            if k_t is None or not np.isfinite(k_t) or k_t < 1:
                return {
                    "applies": True,
                    "active": True,
                    "valid": False,
                    "treatment": treatment,
                    "basis": "K_f derived from K_t + q",
                    "reason": "K_t + q mode requires a finite K_t >= 1.",
                    "k_t": k_t,
                    "q": q,
                    "k_f": None,
                    "k_f_label": "-",
                    "conservative": False,
                    "pseudo_cycle": True,
                }
            if q is None or not np.isfinite(q) or q < 0 or q > 1:
                return {
                    "applies": True,
                    "active": True,
                    "valid": False,
                    "treatment": treatment,
                    "basis": "K_f derived from K_t + q",
                    "reason": "K_t + q mode requires a finite 0 <= q <= 1.",
                    "k_t": k_t,
                    "q": q,
                    "k_f": None,
                    "k_f_label": "-",
                    "conservative": False,
                    "pseudo_cycle": True,
                }
            k_f = 1.0 + q * (k_t - 1.0)
            return {
                "applies": True,
                "active": True,
                "valid": True,
                "treatment": treatment,
                "basis": "K_f derived from K_t + q",
                "reason": "",
                "k_t": k_t,
                "q": q,
                "k_f": k_f,
                "k_f_label": f"{k_f:,.6g}",
                "conservative": False,
                "pseudo_cycle": True,
            }

        if treatment == NOTCH_TREATMENT_CONSERVATIVE_KT:
            if k_t is None or not np.isfinite(k_t) or k_t < 1:
                return {
                    "applies": True,
                    "active": True,
                    "valid": False,
                    "treatment": treatment,
                    "basis": "Conservative screening assumption: q = 1",
                    "reason": "Conservative K_t as K_f mode requires a finite K_t >= 1.",
                    "k_t": k_t,
                    "q": q,
                    "k_f": None,
                    "k_f_label": "-",
                    "conservative": True,
                    "pseudo_cycle": True,
                }
            return {
                "applies": True,
                "active": True,
                "valid": True,
                "treatment": treatment,
                "basis": "Conservative screening assumption: q = 1",
                "reason": "",
                "k_t": k_t,
                "q": 1.0,
                "k_f": k_t,
                "k_f_label": f"{k_t:,.6g}",
                "conservative": True,
                "pseudo_cycle": True,
            }

        return {
            "applies": True,
            "active": False,
            "valid": True,
            "treatment": NOTCH_TREATMENT_NONE,
            "basis": "",
            "reason": "",
            "k_t": None,
            "q": None,
            "k_f": None,
            "k_f_label": "-",
            "conservative": False,
                "pseudo_cycle": False,
            }

    def resolve_lcf_neuber_state(self, sigma_max_nom, sigma_min_nom, stress_source=None, analysis_mode=None):
        source = stress_source or self.stress_source_box.currentText()
        mode = self.normalize_mode_name(analysis_mode or self.analysis_mode_box.currentText())
        local_correction = self.local_correction_box.currentText() if hasattr(self, "local_correction_box") else LCF_LOCAL_CORRECTION_NONE
        sigma_a_nom = abs(sigma_max_nom - sigma_min_nom) / 2.0
        sigma_m_nom = (sigma_max_nom + sigma_min_nom) / 2.0
        r_nom = sigma_min_nom / sigma_max_nom if np.isfinite(sigma_max_nom) and sigma_max_nom != 0 else None

        inactive_state = {
            "applies": False,
            "active": False,
            "valid": True,
            "basis": "",
            "basis_code": "",
            "reason": "",
            "k_t": None,
            "q": None,
            "k_f": None,
            "sigma_elastic_ref": sigma_a_nom,
            "sigma_a_nom": sigma_a_nom,
            "sigma_m_nom": sigma_m_nom,
            "r_nom": r_nom,
            "sigma_a_local": sigma_a_nom,
            "epsilon_a_local": None,
            "epsilon_a_elastic": None,
            "epsilon_a_plastic": None,
            "source": source,
            "mode": mode,
        }

        if mode != "LCF" or local_correction != LCF_LOCAL_CORRECTION_NEUBER:
            return inactive_state
        if source == STRESS_SOURCE_ELASTIC_PLASTIC_FEA:
            return {
                **inactive_state,
                "active": False,
                "valid": False,
                "reason": "Local plasticity is assumed to be resolved by nonlinear FEA; Neuber correction is bypassed.",
            }
        if source not in {STRESS_SOURCE_LINEAR_FEA, STRESS_SOURCE_NOMINAL}:
            return inactive_state

        if source == STRESS_SOURCE_LINEAR_FEA:
            return {
                **inactive_state,
                "applies": True,
                "active": True,
                "valid": True,
                "basis": "ANSYS local elastic stress reference",
                "basis_code": "LINEAR_ELASTIC_FEA_REFERENCE",
                "reason": "",
                "sigma_elastic_ref": sigma_a_nom,
            }

        basis = self.lcf_neuber_basis_box.currentText()
        k_t = parse_optional_float(self.lcf_kt_input.text())
        q = parse_optional_float(self.lcf_q_input.text())
        k_f = parse_optional_float(self.lcf_kf_input.text())

        if basis == LCF_NEUBER_BASIS_ORIGINAL_KT:
            if k_t is None or not np.isfinite(k_t) or k_t < 1:
                return {
                    **inactive_state,
                    "applies": True,
                    "active": True,
                    "valid": False,
                    "basis": LCF_NEUBER_BASIS_ORIGINAL_KT,
                    "basis_code": "ORIGINAL_NEUBER_KT",
                    "reason": "Original Neuber mode requires a finite K_t >= 1.",
                    "k_t": k_t,
                }
            return {
                **inactive_state,
                "applies": True,
                "active": True,
                "valid": True,
                "basis": LCF_NEUBER_BASIS_ORIGINAL_KT,
                "basis_code": "ORIGINAL_NEUBER_KT",
                "reason": "",
                "k_t": k_t,
                "sigma_elastic_ref": k_t * sigma_a_nom,
            }

        if basis == LCF_NEUBER_BASIS_DIRECT_KF:
            if k_f is None or not np.isfinite(k_f) or k_f < 1:
                return {
                    **inactive_state,
                    "applies": True,
                    "active": True,
                    "valid": False,
                    "basis": LCF_NEUBER_BASIS_DIRECT_KF,
                    "basis_code": "FATIGUE_MODIFIED_NEUBER_KF",
                    "reason": "Direct K_f mode requires a finite K_f >= 1.",
                    "k_f": k_f,
                }
            return {
                **inactive_state,
                "applies": True,
                "active": True,
                "valid": True,
                "basis": LCF_NEUBER_BASIS_DIRECT_KF,
                "basis_code": "FATIGUE_MODIFIED_NEUBER_KF",
                "reason": "",
                "k_f": k_f,
                "sigma_elastic_ref": k_f * sigma_a_nom,
            }

        if basis == LCF_NEUBER_BASIS_KT_Q:
            if k_t is None or not np.isfinite(k_t) or k_t < 1:
                return {
                    **inactive_state,
                    "applies": True,
                    "active": True,
                    "valid": False,
                    "basis": LCF_NEUBER_BASIS_KT_Q,
                    "basis_code": "FATIGUE_MODIFIED_NEUBER_ESTIMATED_KF",
                    "reason": "K_t + q mode requires a finite K_t >= 1.",
                    "k_t": k_t,
                    "q": q,
                }
            if q is None or not np.isfinite(q) or q < 0 or q > 1:
                return {
                    **inactive_state,
                    "applies": True,
                    "active": True,
                    "valid": False,
                    "basis": LCF_NEUBER_BASIS_KT_Q,
                    "basis_code": "FATIGUE_MODIFIED_NEUBER_ESTIMATED_KF",
                    "reason": "K_t + q mode requires a finite 0 <= q <= 1.",
                    "k_t": k_t,
                    "q": q,
                }
            k_f = 1.0 + q * (k_t - 1.0)
            return {
                **inactive_state,
                "applies": True,
                "active": True,
                "valid": True,
                "basis": LCF_NEUBER_BASIS_KT_Q,
                "basis_code": "FATIGUE_MODIFIED_NEUBER_ESTIMATED_KF",
                "reason": "",
                "k_t": k_t,
                "q": q,
                "k_f": k_f,
                "sigma_elastic_ref": k_f * sigma_a_nom,
            }

        return {
            **inactive_state,
            "applies": True,
            "active": True,
            "valid": False,
            "basis": basis or "-",
            "basis_code": "",
            "reason": "Unknown Neuber factor basis selection.",
        }

    def solve_neuber_local_response(self, sigma_elastic_ref, E, K_dash, n_dash):
        # Scalar Neuber returns local stress/strain amplitudes only; it does not
        # reconstruct local extrema or mean stress for Morrow/Walker/SWT.
        if not all(is_finite_number(value) for value in (sigma_elastic_ref, E, K_dash, n_dash)):
            return None
        if sigma_elastic_ref < 0 or E <= 0 or K_dash <= 0 or n_dash <= 0:
            return None
        if sigma_elastic_ref == 0:
            return {
                "sigma_a_local": 0.0,
                "epsilon_a_elastic": 0.0,
                "epsilon_a_plastic": 0.0,
                "epsilon_a_local": 0.0,
            }

        target = (sigma_elastic_ref ** 2) / E

        def f(sigma_local):
            if sigma_local < 0 or not np.isfinite(sigma_local):
                return np.nan
            with np.errstate(over="ignore", invalid="ignore"):
                strain_local = sigma_local / E + (sigma_local / K_dash) ** (1.0 / n_dash)
                return sigma_local * strain_local - target

        lower = 0.0
        upper = sigma_elastic_ref
        f_lower = f(lower)
        f_upper = f(upper)
        if not np.isfinite(f_lower) or f_lower > 0:
            return None
        if not np.isfinite(f_upper) or f_upper < 0:
            return None

        tolerance = max(1e-12, 1e-8 * target)
        max_iterations = 200
        sigma_local = upper
        for _ in range(max_iterations):
            sigma_local = 0.5 * (lower + upper)
            f_mid = f(sigma_local)
            if not np.isfinite(f_mid):
                return None
            if abs(f_mid) <= tolerance or abs(upper - lower) <= max(1e-12, 1e-8 * sigma_local):
                break
            if f_mid > 0:
                upper = sigma_local
            else:
                lower = sigma_local
        else:
            return None

        epsilon_a_elastic = sigma_local / E
        epsilon_a_plastic = (sigma_local / K_dash) ** (1.0 / n_dash)
        epsilon_a_local = epsilon_a_elastic + epsilon_a_plastic
        if not all(np.isfinite(value) for value in (sigma_local, epsilon_a_elastic, epsilon_a_plastic, epsilon_a_local)):
            return None
        if sigma_local < 0 or epsilon_a_local < 0:
            return None
        return {
            "sigma_a_local": sigma_local,
            "epsilon_a_elastic": epsilon_a_elastic,
            "epsilon_a_plastic": epsilon_a_plastic,
            "epsilon_a_local": epsilon_a_local,
        }

    def refresh_correction_availability(self, *args):
        material = self.material_box.currentText()
        mode = self.analysis_mode_box.currentText()
        temperature = self.parse_temperature()
        use_legacy_fallback = self.legacy_fallback_box.isChecked()
        allow_estimated_walker = self.estimated_walker_box.isChecked()

        availability = self.get_available_corrections(
            material,
            temperature,
            mode,
            use_legacy_fallback,
            allow_estimated_walker,
            self.static_rows,
            self.fatigue_rows,
            self.walker_rows,
        )
        self.apply_correction_availability(availability)

    def apply_correction_availability(self, availability):
        current_text = self.mean_stress_box.currentText()
        summary_parts = []

        for index in range(self.mean_stress_box.count()):
            method_name = self.mean_stress_box.itemText(index)
            item = self.mean_stress_box.model().item(index)
            method_status = availability.get(
                method_name,
                CorrectionAvailability(method_name, False, UNAVAILABLE_CORRECTION, "Not applicable."),
            )
            item.setEnabled(method_status.enabled)
            item.setToolTip(method_status.reason)
            summary_parts.append(
                self.format_correction_availability_summary(method_status)
            )

        selected_status = availability.get(current_text)
        if selected_status is not None and not selected_status.enabled and current_text != "None":
            self.mean_stress_box.blockSignals(True)
            self.mean_stress_box.setCurrentText("None")
            self.mean_stress_box.blockSignals(False)
            summary_parts.append(f"Selection reset to None: {selected_status.reason}")

        self.correction_status_label.setText(
            "Correction availability: " + "; ".join(summary_parts)
        )
        self.correction_status_label.setToolTip(
            self.correction_status_label.text()
        )
        if hasattr(self, "guidance_text"):
            self.update_model_guidance()

    def format_correction_availability_summary(self, status):
        if status.enabled and status.availability_type == FULL_AVAILABILITY:
            suffix = "available"
        elif status.enabled and status.availability_type == READY_WITH_CONDITION_WARNING:
            suffix = "available with condition warning"
        elif status.enabled and status.availability_type == LEGACY_FALLBACK_REQUIRED:
            suffix = "available with legacy fallback"
        elif status.enabled and status.availability_type == ESTIMATED_PARAMETER_REQUIRED:
            suffix = "available with estimated gamma"
        else:
            suffix = f"unavailable - {status.reason}"
        return f"{status.method_name}: {suffix}"

    def get_available_corrections(
        self,
        material,
        temperature_C,
        analysis_mode,
        use_legacy_fallback,
        allow_estimated_walker,
        static_rows,
        fatigue_rows,
        walker_rows,
        stress_source=None,
        notch_state=None,
        lcf_local_correction=None,
    ):
        # Availability is conservative: a correction can be supported in the
        # literature yet still be disabled here if the current material,
        # temperature, condition, or explicit fallback/estimate assumptions are
        # not satisfied.
        mode = self.normalize_mode_name(analysis_mode)
        if mode not in {"LCF", "HCF"}:
            return {}

        temperature = self.parse_finite_temperature(temperature_C)
        source = stress_source or self.stress_source_box.currentText()
        source_is_nominal = source == STRESS_SOURCE_NOMINAL and mode == "HCF"
        lcf_neuber_active = False
        if mode == "LCF":
            local_correction = lcf_local_correction
            if local_correction is None and hasattr(self, "local_correction_box"):
                local_correction = self.local_correction_box.currentText()
            lcf_neuber_active = (
                source in {STRESS_SOURCE_LINEAR_FEA, STRESS_SOURCE_NOMINAL}
                and local_correction == LCF_LOCAL_CORRECTION_NEUBER
            )
        if notch_state is None and source_is_nominal:
            notch_state = self.parse_nominal_notch_state()
        if notch_state is None:
            notch_state = {
                "active": False,
                "valid": True,
                "treatment": NOTCH_TREATMENT_NONE,
                "reason": "",
            }

        methods = ["None"]
        if mode == "LCF":
            methods.extend(["Morrow", "Walker", "SWT"])
        else:
            methods.extend(["Goodman", "Walker"])

        if mode == "HCF" and material in {
            "SiC/SiC Ceramic Matrix Composite",
            "C/C Composite",
        }:
            reason = "Standalone metallic Basquin HCF estimation is not enabled for this material."
            return {
                method: CorrectionAvailability(method, False, UNAVAILABLE_CORRECTION, reason)
                for method in methods
            }

        if temperature is None:
            reason = "Analysis temperature is invalid or not finite."
            return {
                method: CorrectionAvailability(method, False, UNAVAILABLE_CORRECTION, reason)
                for method in methods
            }

        if source_is_nominal and notch_state.get("active") and not notch_state.get("valid", True):
            reason = notch_state.get("reason") or "Nominal notch inputs are invalid."
            return {
                method: CorrectionAvailability(method, False, UNAVAILABLE_CORRECTION, reason)
                for method in methods
            }

        static_condition, fatigue_condition = self.get_temperature_conditions(material)
        walker_condition = self.get_walker_condition(material)

        capability_cache = {}

        def capability_for(correction):
            if correction not in capability_cache:
                capability_cache[correction] = assess_temperature_capability(
                    material,
                    temperature,
                    mode,
                    correction,
                    static_rows,
                    fatigue_rows,
                    walker_rows=walker_rows,
                    static_condition=static_condition,
                    fatigue_condition=fatigue_condition,
                    walker_condition=walker_condition,
                )
            return capability_cache[correction]

        availability = {}
        for method in methods:
            if method == "None":
                capability = capability_for("None")
                availability[method] = self._evaluate_none_availability(
                    material,
                    mode,
                    capability,
                    use_legacy_fallback,
                )
            elif method == "Morrow":
                if lcf_neuber_active:
                    availability[method] = CorrectionAvailability(
                        "Morrow",
                        False,
                        UNAVAILABLE_CORRECTION,
                        SIMPLE_LCF_NEUBER_UNRESOLVED_REASON,
                    )
                    continue
                capability = capability_for("Morrow")
                availability[method] = self._evaluate_morrow_availability(
                    capability,
                    use_legacy_fallback,
                )
            elif method == "Goodman":
                capability = capability_for("Goodman")
                availability[method] = self._evaluate_goodman_availability(
                    capability,
                    use_legacy_fallback,
                )
            elif method == "Walker":
                if lcf_neuber_active:
                    availability[method] = CorrectionAvailability(
                        "Walker",
                        False,
                        UNAVAILABLE_CORRECTION,
                        SIMPLE_LCF_NEUBER_UNRESOLVED_REASON,
                    )
                    continue
                capability = capability_for("Walker")
                if source_is_nominal and notch_state.get("active"):
                    availability[method] = CorrectionAvailability(
                        "Walker",
                        False,
                        UNAVAILABLE_CORRECTION,
                        WALKER_NOMINAL_NOTCH_UNRESOLVED_REASON,
                    )
                else:
                    availability[method] = self._evaluate_walker_availability(
                        capability,
                        use_legacy_fallback,
                        allow_estimated_walker,
                    )
            elif method == "SWT":
                if lcf_neuber_active:
                    availability[method] = CorrectionAvailability(
                        "SWT",
                        False,
                        UNAVAILABLE_CORRECTION,
                        SIMPLE_LCF_NEUBER_UNRESOLVED_REASON,
                    )
                    continue
                capability = capability_for("SWT")
                availability[method] = self._evaluate_swt_availability(
                    capability,
                    use_legacy_fallback,
                )
        return availability

    def parse_finite_temperature(self, temperature_C):
        if temperature_C is None:
            return None
        try:
            temperature = float(temperature_C)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(temperature):
            return None
        return temperature

    def all_required_properties_resolved(self, capability):
        return bool(capability) and not capability.unresolved_properties

    def condition_warning_required(self, capability):
        return self.all_required_properties_resolved(capability) and capability.condition_compatibility == PARTIAL_MATCH

    def condition_mismatch_blocked(self, capability):
        return self.all_required_properties_resolved(capability) and capability.condition_compatibility == MISMATCH

    def calculation_uses_legacy_constants(self, calculation_status):
        return str(calculation_status).startswith("LEGACY")

    def normalize_mode_name(self, analysis_mode):
        value = str(analysis_mode).strip()
        if value in {"LCF", "Strain-Life / LCF"}:
            return "LCF"
        if value in {"HCF", "Stress-Life / HCF"}:
            return "HCF"
        return value

    def _evaluate_none_availability(self, material, mode, capability, use_legacy_fallback):
        if mode == "HCF" and material in {
            "SiC/SiC Ceramic Matrix Composite",
            "C/C Composite",
        }:
            reason = "Standalone metallic Basquin HCF estimation is not enabled for this material."
            return CorrectionAvailability("None", False, UNAVAILABLE_CORRECTION, reason)

        if self.all_required_properties_resolved(capability):
            if self.condition_mismatch_blocked(capability):
                return CorrectionAvailability(
                    "None",
                    False,
                    UNAVAILABLE_CORRECTION,
                    "All required properties are resolved, but the current material conditions are not conservatively compatible.",
                )
            if self.condition_warning_required(capability):
                return CorrectionAvailability(
                    "None",
                    True,
                    READY_WITH_CONDITION_WARNING,
                    "All required properties are resolved, but condition compatibility is PARTIAL_MATCH.",
                )
            return CorrectionAvailability(
                "None",
                True,
                FULL_AVAILABILITY,
                "Temperature-resolved calculation is available.",
            )

        if use_legacy_fallback:
            return CorrectionAvailability(
                "None",
                True,
                LEGACY_FALLBACK_REQUIRED,
                "Legacy fallback is required for the current temperature/material combination.",
            )

        return CorrectionAvailability(
            "None",
            False,
            UNAVAILABLE_CORRECTION,
            "Required temperature-resolved properties are unavailable and legacy fallback is off.",
        )

    def _evaluate_morrow_availability(self, capability, use_legacy_fallback):
        if self.all_required_properties_resolved(capability):
            if self.condition_mismatch_blocked(capability):
                return CorrectionAvailability(
                    "Morrow",
                    False,
                    UNAVAILABLE_CORRECTION,
                    "All required properties are resolved, but the current material conditions are not conservatively compatible.",
                )
            if self.condition_warning_required(capability):
                return CorrectionAvailability(
                    "Morrow",
                    True,
                    READY_WITH_CONDITION_WARNING,
                    "All required properties are resolved, but condition compatibility is PARTIAL_MATCH.",
                )
            return CorrectionAvailability(
                "Morrow",
                True,
                FULL_AVAILABILITY,
                "Temperature-resolved LCF properties are available.",
            )
        if use_legacy_fallback:
            return CorrectionAvailability(
                "Morrow",
                True,
                LEGACY_FALLBACK_REQUIRED,
                "Legacy fatigue fallback is required for Morrow.",
            )
        return CorrectionAvailability(
            "Morrow",
            False,
            UNAVAILABLE_CORRECTION,
            "Morrow requires temperature-resolved LCF properties or legacy fatigue fallback.",
        )

    def _evaluate_goodman_availability(self, capability, use_legacy_fallback):
        su_item = self.get_capability_item(capability, "S_u_MPa")
        if su_item is None or su_item.status not in {"EXACT", "INTERPOLATED"} or su_item.value is None:
            return CorrectionAvailability(
                "Goodman",
                False,
                UNAVAILABLE_CORRECTION,
                "Goodman correction is not available because a valid S_u_MPa value is missing at the selected temperature.",
            )
        if self.all_required_properties_resolved(capability):
            if self.condition_mismatch_blocked(capability):
                return CorrectionAvailability(
                    "Goodman",
                    False,
                    UNAVAILABLE_CORRECTION,
                    "All required properties are resolved, but the current material conditions are not conservatively compatible.",
                )
            if self.condition_warning_required(capability):
                return CorrectionAvailability(
                    "Goodman",
                    True,
                    READY_WITH_CONDITION_WARNING,
                    "All required properties are resolved, but condition compatibility is PARTIAL_MATCH.",
                )
            return CorrectionAvailability(
                "Goodman",
                True,
                FULL_AVAILABILITY,
                "Temperature-resolved Goodman inputs are available.",
            )
        if use_legacy_fallback:
            return CorrectionAvailability(
                "Goodman",
                True,
                LEGACY_FALLBACK_REQUIRED,
                "Legacy Basquin fatigue fallback is required for Goodman.",
            )
        return CorrectionAvailability(
            "Goodman",
            False,
            UNAVAILABLE_CORRECTION,
            "Goodman requires temperature-resolved fatigue constants or legacy fatigue fallback.",
        )

    def _evaluate_walker_availability(self, capability, use_legacy_fallback, allow_estimated_walker):
        gamma_item = self.get_capability_item(capability, "Walker_gamma")
        if gamma_item is None or gamma_item.status not in {"EXACT", "INTERPOLATED"} or gamma_item.value is None:
            return CorrectionAvailability(
                "Walker",
                False,
                UNAVAILABLE_CORRECTION,
                "Walker gamma is unavailable at the selected temperature.",
            )

        is_estimated = "estimated" in (gamma_item.basis or "").lower()
        if is_estimated and not allow_estimated_walker:
            return CorrectionAvailability(
                "Walker",
                False,
                ESTIMATED_PARAMETER_REQUIRED,
                "Estimated Walker gamma requires explicit opt-in.",
            )

        if self.all_required_properties_resolved(capability):
            if self.condition_mismatch_blocked(capability):
                return CorrectionAvailability(
                    "Walker",
                    False,
                    UNAVAILABLE_CORRECTION,
                    "All required properties are resolved, but the current material conditions are not conservatively compatible.",
                )
            if self.condition_warning_required(capability) and not is_estimated:
                return CorrectionAvailability(
                    "Walker",
                    True,
                    READY_WITH_CONDITION_WARNING,
                    "All required properties are resolved, but condition compatibility is PARTIAL_MATCH.",
                )
        if self.all_required_properties_resolved(capability) and not is_estimated:
            return CorrectionAvailability(
                "Walker",
                True,
                FULL_AVAILABILITY,
                "Temperature-resolved Walker inputs are available.",
            )

        if use_legacy_fallback:
            return CorrectionAvailability(
                "Walker",
                True,
                LEGACY_FALLBACK_REQUIRED if not is_estimated else ESTIMATED_PARAMETER_REQUIRED,
                "Legacy fatigue fallback is required for Walker." if not is_estimated else "Estimated Walker gamma is enabled; legacy fatigue fallback is required.",
            )

        if is_estimated and allow_estimated_walker:
            return CorrectionAvailability(
                "Walker",
                True,
                ESTIMATED_PARAMETER_REQUIRED,
                "Estimated Walker gamma is enabled.",
            )

        return CorrectionAvailability(
            "Walker",
            False,
            UNAVAILABLE_CORRECTION,
            "Walker requires temperature-resolved fatigue properties or an explicit fallback path.",
        )

    def _evaluate_swt_availability(self, capability, use_legacy_fallback):
        if self.all_required_properties_resolved(capability):
            if self.condition_mismatch_blocked(capability):
                return CorrectionAvailability(
                    "SWT",
                    False,
                    UNAVAILABLE_CORRECTION,
                    "All required properties are resolved, but the current material conditions are not conservatively compatible.",
                )
            if self.condition_warning_required(capability):
                return CorrectionAvailability(
                    "SWT",
                    True,
                    READY_WITH_CONDITION_WARNING,
                    "All required properties are resolved, but condition compatibility is PARTIAL_MATCH.",
                )
            return CorrectionAvailability(
                "SWT",
                True,
                FULL_AVAILABILITY,
                "Temperature-resolved LCF properties are available.",
            )
        if use_legacy_fallback:
            return CorrectionAvailability(
                "SWT",
                True,
                LEGACY_FALLBACK_REQUIRED,
                "Legacy fatigue fallback is required for SWT.",
            )
        return CorrectionAvailability(
            "SWT",
            False,
            UNAVAILABLE_CORRECTION,
            "SWT requires temperature-resolved LCF properties or legacy fatigue fallback.",
        )

    def ensure_plot_window(self, title):
        self.plot_window.set_plot_title(title)
        return self.plot_window

    def on_plot_window_destroyed(self, *args):
        pass

    def show_plot_window(self, title):
        plot_window = self.ensure_plot_window(title)
        plot_window.ax.set_axis_on()
        return plot_window

    def close_plot_window(self):
        self.clear_graph("No valid plot for the current calculation.")

    def closeEvent(self, event):
        super().closeEvent(event)

    def clear_graph(self, message):
        plot_window = self.ensure_plot_window("Fatigue Graphs")
        plot_window.ax.clear()
        plot_window.ax.text(
            0.5,
            0.5,
            message,
            transform=plot_window.ax.transAxes,
            ha="center",
            va="center",
        )
        plot_window.ax.set_axis_off()
        plot_window.redraw()

    def show_blocked_result(self, title, message):
        self.set_result_text(
            "\n".join(
                [
                    f"Calculation Status: BLOCKED - {title}",
                    message,
                ]
            )
        )
        self.clear_graph("No valid plot for the current calculation.")

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
            self.show_blocked_result(
                "Invalid Input",
                "Please enter a valid numeric and finite analysis temperature.",
            )
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter a valid numeric and finite analysis temperature.",
            )
            return

        material_name = self.material_box.currentText()
        correction = self.mean_stress_box.currentText()
        static_condition, fatigue_condition = self.get_temperature_conditions(material_name)
        walker_condition = self.get_walker_condition(material_name)
        capability = assess_temperature_capability(
            material_name,
            temperature,
            "LCF",
            correction,
            self.static_rows,
            self.fatigue_rows,
            walker_rows=self.walker_rows,
            static_condition=static_condition,
            fatigue_condition=fatigue_condition,
            walker_condition=walker_condition,
        )
        availability = self.get_available_corrections(
            material_name,
            temperature,
            "LCF",
            self.legacy_fallback_box.isChecked(),
            self.estimated_walker_box.isChecked(),
            self.static_rows,
            self.fatigue_rows,
            self.walker_rows,
        )
        selected_availability = availability.get(correction)
        if selected_availability is None or not selected_availability.enabled:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                correction,
                "TEMPERATURE DATA UNAVAILABLE",
                None,
                selected_availability.reason if selected_availability else "Selected correction is unavailable.",
            )
            return

        legacy_fallback = self.legacy_fallback_box.isChecked()
        mat = self.materials[material_name]

        sigma_a = abs(sigma_max - sigma_min) / 2
        sigma_m = (sigma_max + sigma_min) / 2
        if sigma_a <= 0:
            self.show_blocked_result(
                "Invalid Input",
                "Calculated stress amplitude must be greater than zero.",
            )
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Calculated stress amplitude must be greater than zero.",
            )
            return

        if self.all_required_properties_resolved(capability) and not self.condition_mismatch_blocked(capability):
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
            calculation_status = "READY_WITH_CONDITION_WARNING" if self.condition_warning_required(capability) else "FULLY TEMPERATURE RESOLVED"
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

        local_correction = (
            self.local_correction_box.currentText()
            if self.normalize_mode_name(self.analysis_mode_box.currentText()) == "LCF" and hasattr(self, "local_correction_box")
            else LCF_LOCAL_CORRECTION_NONE
        )
        lcf_neuber_active = local_correction == LCF_LOCAL_CORRECTION_NEUBER
        if lcf_neuber_active and correction != "None":
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                correction,
                calculation_status,
                temperature_note,
                SIMPLE_LCF_NEUBER_UNRESOLVED_REASON,
            )
            return

        lcf_neuber_state = None
        lcf_neuber_result = None
        if lcf_neuber_active:
            lcf_neuber_state = self.resolve_lcf_neuber_state(
                sigma_max,
                sigma_min,
                stress_source=self.stress_source_box.currentText(),
                analysis_mode="LCF",
            )
            if not lcf_neuber_state["active"] or not lcf_neuber_state["valid"]:
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Strain-Life / LCF",
                    "None",
                    calculation_status,
                    temperature_note,
                    lcf_neuber_state.get("reason") or SIMPLE_LCF_NEUBER_UNRESOLVED_REASON,
                )
                return
            if not all(
                is_finite_number(value)
                for value in (E, K_dash, n_dash, sigma_f_dash, b, epsilon_f_dash, c, lcf_neuber_state["sigma_elastic_ref"])
            ):
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Strain-Life / LCF",
                    "None",
                    calculation_status,
                    temperature_note,
                    "Neuber correction requires finite material properties and a finite pseudo-elastic reference stress amplitude.",
                )
                return
            lcf_neuber_result = self.solve_neuber_local_response(
                lcf_neuber_state["sigma_elastic_ref"],
                E,
                K_dash,
                n_dash,
            )
            if lcf_neuber_result is None:
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Strain-Life / LCF",
                    "None",
                    calculation_status,
                    temperature_note,
                    "Neuber local stress-strain solution could not be bracketed for the selected material and stress inputs.",
                )
                return
            if lcf_neuber_result["epsilon_a_local"] == 0:
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Strain-Life / LCF",
                    "None",
                    calculation_status,
                    temperature_note,
                    "Neuber pseudo-elastic reference amplitude is zero; no finite fatigue life can be calculated.",
                )
                return

            estimated_life_result = self.solve_life(
                lcf_neuber_result["epsilon_a_local"],
                E,
                sigma_f_dash,
                b,
                epsilon_f_dash,
                c,
            )
            if estimated_life_result is None:
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Strain-Life / LCF",
                    "None",
                    calculation_status,
                    temperature_note,
                    "A valid Neuber-corrected LCF life could not be bracketed for the selected material and stress inputs.",
                )
                return

            estimated_life, reversals_to_failure, plot_cycles, rhs, lhs = estimated_life_result
            result_lines = self.build_status_lines(
                temperature,
                capability,
                calculation_status,
                temperature_note,
            )
            result_lines.extend(
                [
                    "Stress Source: {0}".format(self.stress_source_box.currentText()),
                    "Neuber Status: ACTIVE",
                    "Neuber Factor Basis: {0}".format(lcf_neuber_state["basis"]),
                ]
            )
            if lcf_neuber_state.get("k_t") is not None:
                result_lines.append("K_t: {0:,.6g}".format(lcf_neuber_state["k_t"]))
            if lcf_neuber_state.get("q") is not None:
                result_lines.append("q: {0:,.6g}".format(lcf_neuber_state["q"]))
            if lcf_neuber_state.get("k_f") is not None:
                result_lines.append("K_f: {0:,.6g}".format(lcf_neuber_state["k_f"]))
            result_lines.extend(
                [
                    "Elastic pseudo-reference stress amplitude (MPa): {0:,.6g}".format(lcf_neuber_state["sigma_elastic_ref"]),
                    "Local Neuber stress amplitude (MPa): {0:,.6g}".format(lcf_neuber_result["sigma_a_local"]),
                    "Local elastic strain amplitude: {0:,.6g}".format(lcf_neuber_result["epsilon_a_elastic"]),
                    "Local plastic strain amplitude: {0:,.6g}".format(lcf_neuber_result["epsilon_a_plastic"]),
                    "Local total strain amplitude: {0:,.6g}".format(lcf_neuber_result["epsilon_a_local"]),
                    "LCF Model: None",
                    "Estimated Life (cycles): {0}".format(self.format_life_value(estimated_life)),
                    "Reversals to Failure (2Nf): {0}".format(self.format_life_value(reversals_to_failure)),
                    "Neuber is an approximate local elastic-plastic correction and is not a substitute for nonlinear cyclic FEA.",
                ]
            )
            if lcf_neuber_state["basis_code"] == "LINEAR_ELASTIC_FEA_REFERENCE":
                result_lines.append(
                    "ANSYS local elastic stress is used directly as the Neuber pseudo-elastic reference. K_t/K_f is not reapplied."
                )
            else:
                result_lines.append(
                    "Nominal analytical stress was corrected using an explicit Neuber factor basis before solving the local stress-strain response."
                )
            if self.calculation_uses_legacy_constants(calculation_status):
                result_lines.append("Legacy fatigue constants were used for the strain-life coefficients.")

            self.set_result_text("\n".join(result_lines))
            plot_window = self.show_plot_window("LCF Strain-Life Plot")
            plot_window.ax.clear()
            plot_window.ax.set_xscale("log")
            plot_window.ax.set_title(
                self.plot_title("Strain-Life Curve", temperature, self.calculation_uses_legacy_constants(calculation_status), capability)
            )
            plot_window.ax.set_xlabel("2Nf (Reversals)")
            plot_window.ax.set_ylabel("Strain Amplitude")
            plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
            plot_window.ax.plot(2 * plot_cycles, rhs, label="Material Curve")
            plot_window.ax.plot(2 * estimated_life, lcf_neuber_result["epsilon_a_local"], "ro", label="Neuber Result")
            plot_window.ax.annotate(
                f"Neuber\nsigma_a={lcf_neuber_result['sigma_a_local']:.6g}\nepsilon_a={lcf_neuber_result['epsilon_a_local']:.6g}",
                (2 * estimated_life, lcf_neuber_result["epsilon_a_local"]),
                textcoords="offset points",
                xytext=(10, 10),
                fontsize=8,
            )
            plot_window.ax.legend()
            plot_window.redraw()
            return

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

        if correction == "Walker":
            gamma_info = self.resolve_walker_gamma(
                capability,
                material_name,
                temperature,
                allow_estimated=self.estimated_walker_box.isChecked(),
            )
            if gamma_info is None:
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Strain-Life / LCF",
                    "Walker",
                    calculation_status,
                    temperature_note,
                    "Walker gamma is unavailable at the selected temperature. Enable estimated Walker gamma only where an estimated value is explicitly present.",
                )
                return
            self.calculate_lcf_walker(
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
                gamma_info,
                temperature,
                capability,
                calculation_status,
                temperature_note,
                legacy_fallback,
            )
            return

        if correction == "SWT":
            self.calculate_lcf_swt(
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
        if self.calculation_uses_legacy_constants(calculation_status):
            result_lines.append("Legacy fatigue constants were used for the strain-life coefficients.")

        self.set_result_text("\n".join(result_lines))
        plot_window = self.show_plot_window("LCF Strain-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_title(
            self.plot_title("Strain-Life Curve", temperature, self.calculation_uses_legacy_constants(calculation_status), capability)
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
        if self.calculation_uses_legacy_constants(calculation_status):
            result_lines.append(
                "Legacy fatigue constants were used for the strain-life coefficients."
            )

        self.set_result_text("\n".join(result_lines))
        plot_window = self.show_plot_window("LCF Strain-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_title(
            self.plot_title("Strain-Life Curve", temperature, self.calculation_uses_legacy_constants(calculation_status), capability)
        )
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Strain Amplitude")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(2 * plot_cycles, rhs_uncorrected, label="Uncorrected Curve")
        plot_window.ax.plot(2 * plot_cycles, rhs_morrow, label="Morrow-Corrected Curve")
        plot_window.ax.plot(2 * morrow_life, strain_amplitude, "ro", label="Morrow Result")
        plot_window.ax.legend()
        plot_window.redraw()

    def calculate_lcf_swt(
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
        # Conventional SWT is defined for tensile-dominated loading through
        # sigma_max * epsilon_a. The sigma_max > 0 restriction here is SWT-
        # specific and must not be copied to Goodman, Morrow, Walker, or None.
        if sigma_max <= 0:
            message = (
                "Conventional SWT requires a positive maximum cycle stress; fully compressive cycles are not supported."
            )
            QMessageBox.warning(self, "SWT Domain Not Supported", message)
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                "SWT",
                calculation_status,
                temperature_note,
                message,
            )
            return

        if not all(
            np.isfinite(value)
            for value in (E, K_dash, n_dash, sigma_f_dash, b, epsilon_f_dash, c, sigma_a, sigma_m)
        ):
            QMessageBox.warning(
                self,
                "Invalid Material Data",
                "SWT correction requires finite material constants and stress inputs.",
            )
            return

        elastic_strain = sigma_a / E
        plastic_strain = (sigma_a / K_dash) ** (1 / n_dash)
        strain_amplitude = elastic_strain + plastic_strain

        if (
            not np.isfinite(strain_amplitude)
            or strain_amplitude <= 0
            or not np.isfinite(sigma_max)
        ):
            QMessageBox.warning(
                self,
                "Invalid Material Data",
                "SWT correction requires finite, positive strain amplitude and material data.",
            )
            return

        swt_parameter = sigma_max * strain_amplitude
        if not np.isfinite(swt_parameter) or swt_parameter <= 0:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "The SWT damage parameter must be positive and finite.",
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
                "SWT",
                calculation_status,
                temperature_note,
                "A valid uncorrected LCF life could not be bracketed for the selected material and stress inputs.",
            )
            return

        uncorrected_life, uncorrected_reversals, _, _, _ = uncorrected_result

        swt_result = self.solve_life_with_rhs(
            swt_parameter,
            lambda nf: self.swt_rhs(nf, E, sigma_f_dash, b, epsilon_f_dash, c),
        )
        if swt_result is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                "SWT",
                calculation_status,
                temperature_note,
                "A valid SWT-corrected LCF life could not be bracketed for the selected material and stress inputs.",
            )
            return

        swt_life, swt_reversals = swt_result
        plot_lower = max(1e-12, min(uncorrected_life, swt_life) / 10.0)
        plot_upper = max(1e6, uncorrected_life * 1.25, swt_life * 1.25)
        plot_cycles = np.logspace(np.log10(plot_lower), np.log10(plot_upper), 1000)
        rhs_uncorrected = self.strain_life_rhs(plot_cycles, E, sigma_f_dash, b, epsilon_f_dash, c)

        result_lines = self.build_status_lines(
            temperature,
            capability,
            calculation_status,
            temperature_note,
        )
        result_lines.extend(
            [
                "Analysis Mode: Strain-Life / LCF",
                "Mean Stress Correction: SWT",
                "Maximum Stress (MPa): {0:,.6g}".format(sigma_max),
                "Minimum Stress (MPa): {0:,.6g}".format(sigma_min),
                "Stress Amplitude (MPa): {0:,.6g}".format(sigma_a),
                "Mean Stress (MPa): {0:,.6g}".format(sigma_m),
                "Elastic Strain Amplitude: {0:,.6g}".format(elastic_strain),
                "Plastic Strain Amplitude: {0:,.6g}".format(plastic_strain),
                "Total Strain Amplitude: {0:,.6g}".format(strain_amplitude),
                "SWT Parameter: {0:,.6g}".format(swt_parameter),
                "Uncorrected Life (cycles): {0}".format(self.format_life_value(uncorrected_life)),
                "SWT-Corrected LCF Life (cycles): {0}".format(self.format_life_value(swt_life)),
                "Uncorrected Reversals (2Nf): {0}".format(self.format_life_value(uncorrected_reversals)),
                "SWT-Corrected Reversals (2Nf): {0}".format(self.format_life_value(swt_reversals)),
                "Smith-Watson-Topper strain-life estimate.",
                "SWT uses P_SWT = sigma_max * epsilon_a with epsilon_a as total strain amplitude.",
            ]
        )
        if self.calculation_uses_legacy_constants(calculation_status):
            result_lines.append(
                "Legacy fatigue constants were used for the strain-life coefficients."
            )

        self.set_result_text("\n".join(result_lines))
        title = "Strain-Life SWT Curve"
        plot_window = self.show_plot_window("LCF Strain-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_title(self.plot_title(title, temperature, self.calculation_uses_legacy_constants(calculation_status), capability))
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Strain Amplitude")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(2 * plot_cycles, rhs_uncorrected, label="Uncorrected Curve")
        plot_window.ax.plot(2 * uncorrected_life, strain_amplitude, "ro", label="Uncorrected Result")
        plot_window.ax.plot(2 * swt_life, strain_amplitude, "bs", label="SWT Result")
        plot_window.ax.annotate(
            f"P_SWT = {swt_parameter:,.6g}",
            (2 * swt_life, strain_amplitude),
            textcoords="offset points",
            xytext=(8, 8),
            ha="left",
        )
        plot_window.ax.legend()
        plot_window.redraw()

    def calculate_lcf_walker(
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
        gamma_info,
        temperature,
        capability,
        calculation_status,
        temperature_note,
        legacy_fallback,
    ):
        if sigma_max <= 0:
            message = "Walker correction requires positive maximum stress. Fully compressive cycles are not supported by this implementation."
            self.show_blocked_result("Walker Domain Not Supported", message)
            QMessageBox.warning(
                self,
                "Walker Domain Not Supported",
                message,
            )
            return

        R = sigma_min / sigma_max
        if not np.isfinite(R) or R >= 1:
            message = "Walker correction requires a finite stress ratio R less than 1."
            self.show_blocked_result("Walker Domain Not Supported", message)
            QMessageBox.warning(
                self,
                "Walker Domain Not Supported",
                message,
            )
            return

        gamma = gamma_info["gamma"]
        elastic_strain = sigma_a / E
        plastic_strain = (sigma_a / K_dash) ** (1 / n_dash)
        strain_amplitude = elastic_strain + plastic_strain
        walker_factor = self.walker_strain_factor(sigma_max, sigma_a, gamma)
        if walker_factor is None:
            QMessageBox.warning(
                self,
                "Walker Calculation Failed",
                "Walker equivalent strain factor could not be calculated for the entered stresses and gamma.",
            )
            return
        walker_equivalent_strain = strain_amplitude * walker_factor

        uncorrected_result = self.solve_life(
            strain_amplitude, E, sigma_f_dash, b, epsilon_f_dash, c
        )
        if uncorrected_result is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                "Walker",
                calculation_status,
                temperature_note,
                "A valid uncorrected LCF life could not be bracketed for the selected material and stress inputs.",
            )
            return

        uncorrected_life, uncorrected_reversals, _, _, _ = uncorrected_result

        def walker_rhs(nf):
            return self.walker_lcf_rhs(
                nf,
                E,
                sigma_max,
                sigma_a,
                sigma_f_dash,
                b,
                epsilon_f_dash,
                c,
                gamma,
            )

        walker_result = self.solve_life_with_rhs(strain_amplitude, walker_rhs)
        if walker_result is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                "Walker",
                calculation_status,
                temperature_note,
                "A valid Walker-corrected LCF life could not be bracketed for the selected material and stress inputs.",
            )
            return

        walker_life, walker_reversals = walker_result
        plot_lower = max(1e-12, min(uncorrected_life, walker_life) / 10.0)
        plot_upper = max(1e6, uncorrected_life * 1.25, walker_life * 1.25)
        plot_cycles = np.logspace(np.log10(plot_lower), np.log10(plot_upper), 1000)
        rhs_uncorrected = self.strain_life_rhs(
            plot_cycles, E, sigma_f_dash, b, epsilon_f_dash, c
        )
        rhs_walker = walker_rhs(plot_cycles)
        if not np.all(np.isfinite(rhs_walker)) or np.any(rhs_walker <= 0):
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Strain-Life / LCF",
                "Walker",
                calculation_status,
                temperature_note,
                "The Walker-corrected LCF curve could not be generated for the selected material and stress inputs.",
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
                "Analysis Mode: Strain-Life / LCF",
                "Mean Stress Correction: Walker",
                "Maximum Stress (MPa): {0:,.6g}".format(sigma_max),
                "Minimum Stress (MPa): {0:,.6g}".format(sigma_min),
                "Stress Amplitude (MPa): {0:,.6g}".format(sigma_a),
                "Mean Stress (MPa): {0:,.6g}".format(sigma_m),
                "Stress Ratio, R: {0:,.6g}".format(R),
                "Walker gamma: {0:,.6g}".format(gamma),
                "Walker gamma basis: {0}".format(gamma_info["basis"]),
                "Walker gamma source: {0}".format(gamma_info["source"]),
                "Walker equivalent strain amplitude: {0:,.6g}".format(walker_equivalent_strain),
                "Elastic Strain Amplitude: {0:,.6g}".format(elastic_strain),
                "Plastic Strain Amplitude: {0:,.6g}".format(plastic_strain),
                "Total Strain Amplitude: {0:,.6g}".format(strain_amplitude),
                "Uncorrected Life (cycles): {0}".format(self.format_life_value(uncorrected_life)),
                "Walker-Corrected Life (cycles): {0}".format(self.format_life_value(walker_life)),
                "Uncorrected Reversals (2Nf): {0}".format(self.format_life_value(uncorrected_reversals)),
                "Walker-Corrected Reversals (2Nf): {0}".format(self.format_life_value(walker_reversals)),
                "Walker strain-life correction uses epsilon_a,eq = epsilon_a * (sigma_max/sigma_a)^(1-gamma).",
            ]
        )
        if gamma_info["estimated"]:
            result_lines.append("ESTIMATED WALKER PARAMETER - not a calibrated material gamma.")
        if self.calculation_uses_legacy_constants(calculation_status):
            result_lines.append(
                "Legacy fatigue constants were used for the strain-life coefficients."
            )

        self.set_result_text("\n".join(result_lines))
        title = "Strain-Life Walker Curve"
        if gamma_info["estimated"]:
            title += " - Estimated gamma"
        plot_window = self.show_plot_window("LCF Strain-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_title(self.plot_title(title, temperature, self.calculation_uses_legacy_constants(calculation_status), capability))
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Strain Amplitude")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(2 * plot_cycles, rhs_uncorrected, label="Uncorrected Curve")
        plot_window.ax.plot(2 * plot_cycles, rhs_walker, label="Walker-Corrected Curve")
        plot_window.ax.plot(2 * walker_life, strain_amplitude, "ro", label="Walker Result")
        plot_window.ax.legend()
        plot_window.redraw()

    def calculate_hcf(self):
        sigma_max, sigma_min = self.parse_stress_inputs()
        if sigma_max is None:
            return
        temperature = self.parse_temperature()
        if temperature is None:
            self.show_blocked_result(
                "Invalid Input",
                "Please enter a valid numeric and finite analysis temperature.",
            )
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
            self.close_plot_window()
            return

        correction = self.mean_stress_box.currentText()
        static_condition, fatigue_condition = self.get_temperature_conditions(material_name)
        walker_condition = self.get_walker_condition(material_name)
        capability = assess_temperature_capability(
            material_name,
            temperature,
            "HCF",
            correction,
            self.static_rows,
            self.fatigue_rows,
            walker_rows=self.walker_rows,
            static_condition=static_condition,
            fatigue_condition=fatigue_condition,
            walker_condition=walker_condition,
        )
        availability = self.get_available_corrections(
            material_name,
            temperature,
            "HCF",
            self.legacy_fallback_box.isChecked(),
            self.estimated_walker_box.isChecked(),
            self.static_rows,
            self.fatigue_rows,
            self.walker_rows,
        )
        selected_availability = availability.get(correction)
        if selected_availability is None or not selected_availability.enabled:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Stress-Life / HCF",
                correction,
                "TEMPERATURE DATA UNAVAILABLE",
                None,
                selected_availability.reason if selected_availability else "Selected correction is unavailable.",
            )
            return
        legacy_fallback = self.legacy_fallback_box.isChecked()
        mat = self.materials[material_name]
        hcf_context = self.resolve_hcf_notch_state(sigma_max, sigma_min)
        notch_state = hcf_context["notch"]
        if notch_state["active"] and not notch_state["valid"]:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Stress-Life / HCF",
                correction,
                calculation_status,
                temperature_note,
                notch_state["reason"],
            )
            return

        sigma_a = hcf_context["sigma_a_nom"]
        sigma_m = hcf_context["sigma_m_nom"]
        sigma_a_eff = hcf_context["sigma_a_eff"]
        sigma_m_eff = hcf_context["sigma_m_eff"]

        if not np.isfinite(sigma_a) or sigma_a <= 0:
            self.show_blocked_result(
                "Invalid Input",
                "Calculated stress amplitude must be greater than zero.",
            )
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Calculated stress amplitude must be greater than zero.",
            )
            return

        sigma_f_item = self.get_capability_item(capability, "sigma_f_dash")
        b_item = self.get_capability_item(capability, "b")
        su_item = self.get_capability_item(capability, "S_u_MPa")

        if self.all_required_properties_resolved(capability) and not self.condition_mismatch_blocked(capability):
            sigma_f_dash = sigma_f_item.value
            b = b_item.value
            S_u = su_item.value if correction == "Goodman" else None
            calculation_status = "READY_WITH_CONDITION_WARNING" if self.condition_warning_required(capability) else "FULLY TEMPERATURE RESOLVED"
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

        sigma_a_for_basquin = sigma_a_eff if notch_state["active"] else sigma_a
        basquin_result = self.calculate_basquin_life(sigma_a_for_basquin, sigma_f_dash, b)
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
                hcf_context,
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

        if correction == "Walker":
            if notch_state["active"]:
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Stress-Life / HCF",
                    "Walker",
                    calculation_status,
                    temperature_note,
                    WALKER_NOMINAL_NOTCH_UNRESOLVED_REASON,
                )
                return
            gamma_info = self.resolve_walker_gamma(
                capability,
                material_name,
                temperature,
                allow_estimated=self.estimated_walker_box.isChecked(),
            )
            if gamma_info is None:
                self.show_unavailable_temperature_result(
                    capability,
                    temperature,
                    "Stress-Life / HCF",
                    "Walker",
                    calculation_status,
                    temperature_note,
                    "Walker gamma is unavailable at the selected temperature. Enable estimated Walker gamma only where an estimated value is explicitly present.",
                )
                return
            self.calculate_hcf_walker(
                sigma_max,
                sigma_min,
                sigma_a,
                sigma_m,
                estimated_life,
                reversals_to_failure,
                sigma_f_dash,
                b,
                gamma_info,
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
        if notch_state["active"]:
            result_lines.extend(
                [
                    "Stress Source: Nominal analytical stress",
                    f"Notch Treatment: {notch_state['treatment']}",
                    f"K_f basis: {notch_state['basis']}",
                    "Nominal sigma_max (MPa): {0:,.6g}".format(sigma_max),
                    "Nominal sigma_min (MPa): {0:,.6g}".format(sigma_min),
                    "Nominal sigma_a (MPa): {0:,.6g}".format(sigma_a),
                    "Nominal sigma_m (MPa): {0:,.6g}".format(sigma_m),
                    "Nominal R: {0:,.6g}".format(hcf_context["r_nom"]) if hcf_context["r_nom"] is not None else "Nominal R: -",
                    "Effective sigma_a (MPa): {0:,.6g}".format(sigma_a_eff),
                    "Effective sigma_m (MPa): {0:,.6g}".format(sigma_m_eff),
                ]
            )
        result_lines.extend(
            [
                "Maximum Stress (MPa): {0:,.6g}".format(sigma_max),
                "Minimum Stress (MPa): {0:,.6g}".format(sigma_min),
                "Stress Amplitude (MPa): {0:,.6g}".format(sigma_a),
                "Mean Stress (MPa): {0:,.6g}".format(sigma_m),
                "Fatigue-Effective Stress Amplitude (MPa): {0:,.6g}".format(sigma_a_for_basquin),
                "Estimated Life (cycles): {0}".format(self.format_life_value(estimated_life)),
                "Reversals to Failure (2Nf): {0}".format(self.format_life_value(reversals_to_failure)),
                "Mean stress calculated but not corrected.",
                "Basquin stress-life estimate; intended for elastic-dominated HCF.",
                "Material fatigue constants do not currently include calibration-range metadata; extrapolated HCF life should be treated as an engineering estimate.",
            ]
        )
        if self.calculation_uses_legacy_constants(calculation_status):
            result_lines.append("Legacy fatigue constants were used for the Basquin relation.")

        self.set_result_text("\n".join(result_lines))
        plot_window = self.show_plot_window("HCF Stress-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_yscale("log")
        plot_window.ax.set_title(
            self.plot_title("Stress-Life (Basquin) Curve", temperature, self.calculation_uses_legacy_constants(calculation_status), capability)
        )
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Stress Amplitude (MPa)")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(plot_reversals, plot_curve, label="Basquin Curve")
        plot_window.ax.plot(
            reversals_to_failure,
            sigma_a_for_basquin,
            "ro",
            label="Your Result",
        )
        plot_window.ax.legend()
        plot_window.redraw()

    def calculate_hcf_goodman(
        self,
        sigma_max,
        sigma_min,
        sigma_a,
        sigma_m,
        hcf_context,
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

        notch_state = hcf_context["notch"]
        sigma_a_effective = hcf_context["sigma_a_eff"]
        sigma_m_effective = hcf_context["sigma_m_eff"]
        sigma_a_pre_goodman = sigma_a_effective if notch_state["active"] else sigma_a
        sigma_m_pre_goodman = sigma_m_effective if notch_state["active"] else sigma_m

        if sigma_m_pre_goodman >= S_u:
            self.show_blocked_result(
                "Invalid Input",
                "Goodman correction requires mean stress to be less than the ultimate tensile strength S_u.",
            )
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Goodman correction requires mean stress to be less than the ultimate tensile strength S_u.",
            )
            return

        denominator = 1.0 - sigma_m_pre_goodman / S_u
        if not np.isfinite(denominator) or denominator <= 0:
            self.show_blocked_result(
                "Invalid Input",
                "The Goodman correction denominator is zero or negative for the entered mean stress.",
            )
            QMessageBox.warning(
                self,
                "Invalid Input",
                "The Goodman correction denominator is zero or negative for the entered mean stress.",
            )
            return

        sigma_a_eq = sigma_a_pre_goodman / denominator
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
        if notch_state["active"]:
            result_lines.extend(
                [
                    "Stress Source: Nominal analytical stress",
                    f"Notch Treatment: {notch_state['treatment']}",
                    f"K_f basis: {notch_state['basis']}",
                    "Nominal sigma_max (MPa): {0:,.6g}".format(sigma_max),
                    "Nominal sigma_min (MPa): {0:,.6g}".format(sigma_min),
                    "Nominal sigma_a (MPa): {0:,.6g}".format(sigma_a),
                    "Nominal sigma_m (MPa): {0:,.6g}".format(sigma_m),
                    "Nominal R: {0:,.6g}".format(hcf_context["r_nom"]) if hcf_context["r_nom"] is not None else "Nominal R: -",
                    "Effective sigma_a (MPa): {0:,.6g}".format(sigma_a_effective),
                    "Effective sigma_m (MPa): {0:,.6g}".format(sigma_m_effective),
                    "K_f used (factor): {0:,.6g}".format(notch_state["k_f"]),
                ]
            )
        result_lines.extend(
            [
                "Maximum Stress (MPa): {0:,.6g}".format(sigma_max),
                "Minimum Stress (MPa): {0:,.6g}".format(sigma_min),
                "Stress Amplitude (MPa): {0:,.6g}".format(sigma_a),
                "Mean Stress (MPa): {0:,.6g}".format(sigma_m),
                "Ultimate Tensile Strength, S_u (MPa): {0:,.6g}".format(S_u),
                "Fatigue-Effective Stress Amplitude (MPa): {0:,.6g}".format(sigma_a_pre_goodman),
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
        if self.calculation_uses_legacy_constants(calculation_status):
            result_lines.append("Legacy Basquin fatigue constants were used for the HCF relation.")

        self.set_result_text("\n".join(result_lines))
        plot_window = self.show_plot_window("HCF Stress-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_yscale("log")
        plot_window.ax.set_title(
            self.plot_title("Stress-Life (Basquin) Curve", temperature, self.calculation_uses_legacy_constants(calculation_status), capability)
        )
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Stress Amplitude (MPa)")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(plot_reversals, plot_curve, label="Basquin Curve")
        plot_window.ax.plot(
            uncorrected_reversals,
            sigma_a_pre_goodman,
            "ro",
            label="Uncorrected Result",
        )
        plot_window.ax.plot(goodman_reversals, sigma_a_eq, "go", label="Goodman Result")
        plot_window.ax.legend()
        plot_window.redraw()

    def calculate_hcf_walker(
        self,
        sigma_max,
        sigma_min,
        sigma_a,
        sigma_m,
        uncorrected_life,
        uncorrected_reversals,
        sigma_f_dash,
        b,
        gamma_info,
        temperature,
        capability,
        calculation_status,
        temperature_note,
        legacy_fallback,
    ):
        if sigma_max <= 0:
            message = "Walker correction requires positive maximum stress. Fully compressive cycles are not supported by this implementation."
            self.show_blocked_result("Walker Domain Not Supported", message)
            QMessageBox.warning(
                self,
                "Walker Domain Not Supported",
                message,
            )
            return

        R = sigma_min / sigma_max
        if not np.isfinite(R) or R >= 1:
            message = "Walker correction requires a finite stress ratio R less than 1."
            self.show_blocked_result("Walker Domain Not Supported", message)
            QMessageBox.warning(
                self,
                "Walker Domain Not Supported",
                message,
            )
            return

        gamma = gamma_info["gamma"]
        sigma_eq = self.walker_equivalent_stress(sigma_max, sigma_a, gamma)
        if sigma_eq is None:
            QMessageBox.warning(
                self,
                "Walker Calculation Failed",
                "Walker equivalent stress could not be calculated for the entered stresses and gamma.",
            )
            return

        walker_result = self.calculate_basquin_life(sigma_eq, sigma_f_dash, b)
        if walker_result is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Stress-Life / HCF",
                "Walker",
                calculation_status,
                temperature_note,
                "The Walker-corrected HCF life calculation produced an invalid result.",
            )
            return

        walker_life, walker_reversals = walker_result
        plot_reversals, plot_curve = self.build_hcf_curve(
            uncorrected_life, sigma_f_dash, b, walker_life
        )
        if plot_reversals is None:
            self.show_unavailable_temperature_result(
                capability,
                temperature,
                "Stress-Life / HCF",
                "Walker",
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
                "Analysis Mode: Stress-Life / HCF",
                "Mean Stress Correction: Walker",
                "Maximum Stress (MPa): {0:,.6g}".format(sigma_max),
                "Minimum Stress (MPa): {0:,.6g}".format(sigma_min),
                "Stress Amplitude (MPa): {0:,.6g}".format(sigma_a),
                "Mean Stress (MPa): {0:,.6g}".format(sigma_m),
                "Stress Ratio, R: {0:,.6g}".format(R),
                "Walker gamma: {0:,.6g}".format(gamma),
                "Walker gamma basis: {0}".format(gamma_info["basis"]),
                "Walker gamma source: {0}".format(gamma_info["source"]),
                "Walker equivalent stress (MPa): {0:,.6g}".format(sigma_eq),
                "Uncorrected Life (cycles): {0}".format(self.format_life_value(uncorrected_life)),
                "Walker-Corrected Life (cycles): {0}".format(self.format_life_value(walker_life)),
                "Uncorrected Reversals (2Nf): {0}".format(self.format_life_value(uncorrected_reversals)),
                "Walker-Corrected Reversals (2Nf): {0}".format(self.format_life_value(walker_reversals)),
                "Walker mean-stress correction using sigma_eq = sigma_max^(1-gamma) * sigma_a^gamma.",
                "Basquin stress-life estimate; intended for elastic-dominated HCF.",
            ]
        )
        if gamma_info["estimated"]:
            result_lines.append("ESTIMATED WALKER PARAMETER - not a calibrated material gamma.")
        if self.calculation_uses_legacy_constants(calculation_status):
            result_lines.append("Legacy Basquin fatigue constants were used for the HCF relation.")

        self.set_result_text("\n".join(result_lines))
        title = "Stress-Life (Basquin/Walker) Curve"
        if gamma_info["estimated"]:
            title += " - Estimated gamma"
        plot_window = self.show_plot_window("HCF Stress-Life Plot")
        plot_window.ax.clear()
        plot_window.ax.set_xscale("log")
        plot_window.ax.set_yscale("log")
        plot_window.ax.set_title(self.plot_title(title, temperature, self.calculation_uses_legacy_constants(calculation_status), capability))
        plot_window.ax.set_xlabel("2Nf (Reversals)")
        plot_window.ax.set_ylabel("Stress Amplitude / Walker Equivalent Stress (MPa)")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)
        plot_window.ax.plot(plot_reversals, plot_curve, label="Basquin Curve")
        plot_window.ax.plot(uncorrected_reversals, sigma_a, "ro", label="Uncorrected Result")
        plot_window.ax.plot(walker_reversals, sigma_eq, "go", label="Walker Result")
        plot_window.ax.legend()
        plot_window.redraw()

    def build_status_lines(self, temperature, capability, calculation_status, temperature_note):
        lines = [
            f"Analysis Temperature (C): {temperature:,.6g}",
            f"Temperature Capability: {self.capability_display_label(capability.capability)}",
            f"Static Condition: {capability.static_condition or '-'}",
            f"Fatigue Condition: {capability.fatigue_condition or '-'}",
            f"Walker Condition: {getattr(capability, 'walker_condition', '') or '-'}",
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

    def get_walker_condition(self, material_name):
        hints = {
            "Aluminum 2024-T3": "2024-T3",
            "Aluminum 7075-T6": "7075-T6",
        }
        return hints.get(material_name)

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
        walker_items = [item for item in capability.required_properties if item.property_group == "walker"]
        if walker_items:
            lines.append("  Walker:")
            for item in walker_items:
                lines.append(self.format_property_line(item))
        if not static_items and not fatigue_items and not walker_items:
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
            self.show_blocked_result(
                "Invalid Input",
                "Please enter valid numeric values for both maximum and minimum stress.",
            )
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter valid numeric values for both maximum and minimum stress.",
            )
            return None, None

        if not np.isfinite(sigma_max) or not np.isfinite(sigma_min):
            self.show_blocked_result(
                "Invalid Input",
                "Please enter finite numeric values for both maximum and minimum stress.",
            )
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter finite numeric values for both maximum and minimum stress.",
            )
            return None, None

        if sigma_max < sigma_min:
            self.show_blocked_result(
                "Invalid Input",
                "Maximum stress must be greater than or equal to minimum stress.",
            )
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
        self.close_plot_window()

    def set_result_text(self, text):
        if "Stress Source Used:" not in text:
            text = "\n".join(self.build_input_interpretation_lines() + ["", text])
        self.result_text.setPlainText(text)
        self.result_text.verticalScrollBar().setValue(0)
        if hasattr(self, "tabs"):
            self.tabs.setCurrentIndex(1)

    def build_input_interpretation_lines(self):
        source = self.stress_source_box.currentText()
        mode = self.analysis_mode_box.currentText()
        correction = self.mean_stress_box.currentText()
        material = self.material_box.currentText()
        material_condition = self.materials.get(material, {}).get("material_condition") or "-"
        notch_state = self.parse_nominal_notch_state()

        lines = [
            "INPUT INTERPRETATION",
            f"Stress Source Used: {source}",
            f"Input Interpretation: signed sigma_max and sigma_min are treated as one uniaxial stress cycle at one hotspot/direction.",
            f"Material: {material}",
            f"Material condition: {material_condition}",
            f"Analysis Mode: {mode}",
            f"Mean Stress Correction: {correction}",
        ]
        if self.normalize_mode_name(mode) == "LCF":
            local_correction = self.local_correction_box.currentText() if hasattr(self, "local_correction_box") else LCF_LOCAL_CORRECTION_NONE
            lines.append(f"Local Elastic-Plastic Correction: {local_correction}")
            if local_correction == LCF_LOCAL_CORRECTION_NEUBER:
                neuber_state = self.resolve_lcf_neuber_state(
                    parse_optional_float(self.sigma_max_input.text()) or 0.0,
                    parse_optional_float(self.sigma_min_input.text()) or 0.0,
                )
                lines.append(f"Neuber Status: {'ACTIVE' if neuber_state['active'] else 'INACTIVE'}")
                if neuber_state.get("basis"):
                    lines.append(f"Neuber Factor Basis: {neuber_state['basis']}")
                if neuber_state.get("k_t") is not None:
                    lines.append(f"K_t: {neuber_state['k_t']:,.6g}")
                if neuber_state.get("q") is not None:
                    lines.append(f"q: {neuber_state['q']:,.6g}")
                if neuber_state.get("k_f") is not None:
                    lines.append(f"K_f: {neuber_state['k_f']:,.6g}")

        sigma_max_val = parse_optional_float(self.sigma_max_input.text())
        sigma_min_val = parse_optional_float(self.sigma_min_input.text())
        if sigma_max_val is not None and sigma_min_val is not None:
            sigma_a = abs(sigma_max_val - sigma_min_val) / 2.0
            sigma_m = (sigma_max_val + sigma_min_val) / 2.0
            lines.extend(
                [
                    f"Maximum Stress, sigma_max (MPa): {sigma_max_val:,.6g}",
                    f"Minimum Stress, sigma_min (MPa): {sigma_min_val:,.6g}",
                    f"Stress Amplitude, sigma_a (MPa): {sigma_a:,.6g}",
                    f"Mean Stress, sigma_m (MPa): {sigma_m:,.6g}",
                ]
            )
            if sigma_max_val != 0:
                lines.append(f"Stress Ratio, R: {sigma_min_val / sigma_max_val:,.6g}")
            else:
                lines.append("Stress Ratio, R: undefined because sigma_max is zero")

        if source == STRESS_SOURCE_LINEAR_FEA:
            lines.append("Source assumption: linear-elastic FEA already resolves geometry stress concentration; K_t is not applied again.")
        elif source == STRESS_SOURCE_ELASTIC_PLASTIC_FEA:
            lines.append("Source assumption: direct elastic-plastic FEA strain input is reserved for a later solver integration; K_t and Neuber are not applied.")
            strain_value = self.local_strain_input.text().strip()
            lines.append(f"Local total strain amplitude input: {strain_value or '-'}")
        elif source == STRESS_SOURCE_NOMINAL:
            if self.normalize_mode_name(mode) == "HCF":
                lines.append("Source assumption: nominal-stress notch correction is applied in HCF as a preprocessing stage.")
                lines.append(f"Notch Treatment: {notch_state['treatment']}")
                if notch_state.get("basis"):
                    lines.append(f"K_f basis: {notch_state['basis']}")
                if notch_state.get("k_t") is not None:
                    lines.append(f"K_t: {notch_state['k_t']:,.6g}")
                if notch_state.get("q") is not None:
                    lines.append(f"q: {notch_state['q']:,.6g}")
                if notch_state.get("k_f") is not None:
                    lines.append(f"K_f used: {notch_state['k_f']:,.6g}")
                lines.append("Current ductile HCF nominal-notch method applies K_f to alternating stress only.")
                lines.append("Mean stress remains nominal by default.")
                if notch_state.get("active"):
                    lines.append("Pseudo-cycle values are reconstructed for calculation plumbing and are not physical notch-root extrema.")
            else:
                local_correction = self.local_correction_box.currentText() if hasattr(self, "local_correction_box") else LCF_LOCAL_CORRECTION_NONE
                lines.append("Source assumption: nominal analytical stress is only corrected locally when LCF Neuber is explicitly selected.")
                lines.append(f"Local Elastic-Plastic Correction: {local_correction}")
                if local_correction == LCF_LOCAL_CORRECTION_NEUBER:
                    lcf_state = self.resolve_lcf_neuber_state(
                        parse_optional_float(self.sigma_max_input.text()) or 0.0,
                        parse_optional_float(self.sigma_min_input.text()) or 0.0,
                    )
                    lines.append(f"Neuber Status: {'ACTIVE' if lcf_state['active'] else 'INACTIVE'}")
                    if lcf_state.get("basis"):
                        lines.append(f"Neuber Factor Basis: {lcf_state['basis']}")
                    if lcf_state.get("k_t") is not None:
                        lines.append(f"K_t: {lcf_state['k_t']:,.6g}")
                    if lcf_state.get("q") is not None:
                        lines.append(f"q: {lcf_state['q']:,.6g}")
                    if lcf_state.get("k_f") is not None:
                        lines.append(f"K_f: {lcf_state['k_f']:,.6g}")
                else:
                    lines.append("Nominal analytical stress uses the existing LCF strain-life relation without local elastic-plastic correction.")
            sigma_max_nom = parse_optional_float(self.sigma_max_input.text())
            sigma_min_nom = parse_optional_float(self.sigma_min_input.text())
            if sigma_max_nom is not None and sigma_min_nom is not None:
                sigma_a_nominal = abs(sigma_max_nom - sigma_min_nom) / 2.0
                sigma_m_nominal = (sigma_max_nom + sigma_min_nom) / 2.0
                lines.append(f"Nominal Stress Amplitude, sigma_a_nom (MPa): {sigma_a_nominal:,.6g}")
                lines.append(f"Nominal Mean Stress, sigma_m_nom (MPa): {sigma_m_nominal:,.6g}")

        if mode == "LCF":
            local_correction = self.local_correction_box.currentText() if hasattr(self, "local_correction_box") else LCF_LOCAL_CORRECTION_NONE
            lines.append(f"Local Elastic-Plastic Correction: {local_correction}")
            if local_correction == LCF_LOCAL_CORRECTION_NEUBER:
                if source == STRESS_SOURCE_LINEAR_FEA:
                    lines.append("LCF Neuber uses ANSYS local elastic stress directly as the pseudo-elastic reference; K_t/K_f is not reapplied.")
                elif source == STRESS_SOURCE_NOMINAL:
                    lcf_state = self.resolve_lcf_neuber_state(
                        parse_optional_float(self.sigma_max_input.text()) or 0.0,
                        parse_optional_float(self.sigma_min_input.text()) or 0.0,
                    )
                    lines.append(f"Neuber Status: {'ACTIVE' if lcf_state['active'] else 'INACTIVE'}")
                    if lcf_state.get("basis"):
                        lines.append(f"Neuber Factor Basis: {lcf_state['basis']}")
                    if lcf_state.get("k_t") is not None:
                        lines.append(f"K_t: {lcf_state['k_t']:,.6g}")
                    if lcf_state.get("q") is not None:
                        lines.append(f"q: {lcf_state['q']:,.6g}")
                    if lcf_state.get("k_f") is not None:
                        lines.append(f"K_f: {lcf_state['k_f']:,.6g}")
                else:
                    lines.append("Local plasticity is assumed to be resolved by nonlinear FEA; Neuber correction is bypassed.")
            else:
                lines.append("LCF None uses the existing strain-life relation without local elastic-plastic correction.")

        if correction in {"Goodman", "Walker"}:
            lines.append("ANSYS guidance: use signed local normal stress in a consistent direction; do not use Equivalent (von Mises) Stress for sigma_max/sigma_min mean-stress correction.")

        return lines

    def resolve_hcf_notch_state(self, sigma_max_nom, sigma_min_nom, stress_source=None, analysis_mode=None):
        source = stress_source or self.stress_source_box.currentText()
        mode = self.normalize_mode_name(analysis_mode or self.analysis_mode_box.currentText())
        sigma_a_nom = abs(sigma_max_nom - sigma_min_nom) / 2.0
        sigma_m_nom = (sigma_max_nom + sigma_min_nom) / 2.0
        r_nom = sigma_min_nom / sigma_max_nom if np.isfinite(sigma_max_nom) and sigma_max_nom != 0 else None

        state = self.parse_nominal_notch_state() if source == STRESS_SOURCE_NOMINAL and mode == "HCF" else {
            "applies": False,
            "active": False,
            "valid": True,
            "treatment": NOTCH_TREATMENT_NONE,
            "basis": "",
            "reason": "",
            "k_t": None,
            "q": None,
            "k_f": None,
            "k_f_label": "-",
            "conservative": False,
            "pseudo_cycle": False,
        }

        if not state["active"] or not state["valid"]:
            sigma_a_eff = sigma_a_nom
            sigma_m_eff = sigma_m_nom
            pseudo_max = sigma_max_nom
            pseudo_min = sigma_min_nom
            pseudo_r = r_nom
        else:
            k_f = state["k_f"]
            sigma_a_eff = k_f * sigma_a_nom
            sigma_m_eff = sigma_m_nom
            pseudo_max = sigma_m_eff + sigma_a_eff
            pseudo_min = sigma_m_eff - sigma_a_eff
            pseudo_r = pseudo_min / pseudo_max if pseudo_max != 0 else None

        return {
            "source": source,
            "mode": mode,
            "sigma_a_nom": sigma_a_nom,
            "sigma_m_nom": sigma_m_nom,
            "r_nom": r_nom,
            "sigma_a_eff": sigma_a_eff,
            "sigma_m_eff": sigma_m_eff,
            "pseudo_sigma_max": pseudo_max,
            "pseudo_sigma_min": pseudo_min,
            "pseudo_r": pseudo_r,
            "notch": state,
        }

    def build_comparison_summary(
        self,
        material_name,
        temperature,
        analysis_mode,
        sigma_max,
        sigma_min,
        capability,
        availability,
        legacy_fallback,
        allow_estimated_walker,
    ):
        mode_key = self.normalize_mode_name(analysis_mode)
        sigma_a = abs(sigma_max - sigma_min) / 2
        sigma_m = (sigma_max + sigma_min) / 2
        model_names = ["None", "Morrow", "Walker", "SWT"] if mode_key == "LCF" else ["None", "Goodman", "Walker"]
        model_results = []
        warnings = list(capability.warnings)
        assumptions = [
            "Comparison reports mathematically predicted lives side-by-side.",
            "The lowest predicted life is descriptive only and is not automatically recommended.",
            "Model conservatism and model validity are different concepts.",
        ]

        for model_name in model_names:
            model_result = self.build_model_comparison_result(
                model_name,
                material_name,
                temperature,
                analysis_mode,
                sigma_max,
                sigma_min,
                sigma_a,
                sigma_m,
                capability,
                availability.get(model_name),
                legacy_fallback,
                allow_estimated_walker,
            )
            model_results.append(model_result)
            warnings.extend(model_result.warnings)

        available_results = [
            result
            for result in model_results
            if result.predicted_life_cycles is not None and result.status != "UNAVAILABLE"
        ]
        if available_results:
            lowest_result = min(available_results, key=lambda result: result.predicted_life_cycles)
            lowest_model = lowest_result.model_name
            lowest_life = lowest_result.predicted_life_cycles
        else:
            lowest_model = None
            lowest_life = None

        return ComparisonSummary(
            material=material_name,
            temperature_C=temperature,
            analysis_mode=analysis_mode,
            sigma_max_MPa=sigma_max,
            sigma_min_MPa=sigma_min,
            sigma_a_MPa=sigma_a,
            sigma_m_MPa=sigma_m,
            model_results=model_results,
            lowest_predicted_life_model=lowest_model,
            lowest_predicted_life_cycles=lowest_life,
            warnings=self.unique_strings(warnings),
            assumptions=assumptions,
        )

    def build_model_comparison_result(
        self,
        model_name,
        material_name,
        temperature,
        analysis_mode,
        sigma_max,
        sigma_min,
        sigma_a,
        sigma_m,
        capability,
        availability,
        legacy_fallback,
        allow_estimated_walker,
    ):
        temperature_label = self.capability_display_label(capability.capability)
        if availability is None or not availability.enabled:
            reason = availability.reason if availability is not None else "Selected model is unavailable."
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode=self.normalize_mode_name(analysis_mode),
                predicted_life_cycles=None,
                reversals=None,
                availability="UNAVAILABLE",
                temperature_capability=temperature_label,
                property_basis=self.comparison_property_basis(capability, model_name, legacy_fallback, unavailable_reason=reason),
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=False,
                estimated_parameter_used=False,
                warnings=self.unique_strings(list(capability.warnings) + [reason]),
                assumptions=self.comparison_assumptions(model_name),
                status="UNAVAILABLE",
                reason=reason,
            )

        if self.normalize_mode_name(analysis_mode) == "LCF":
            return self.build_lcf_comparison_result(
                model_name,
                material_name,
                temperature,
                sigma_max,
                sigma_min,
                sigma_a,
                sigma_m,
                capability,
                availability,
                legacy_fallback,
                allow_estimated_walker,
            )
        return self.build_hcf_comparison_result(
            model_name,
            material_name,
            temperature,
            sigma_max,
            sigma_min,
            sigma_a,
            sigma_m,
            capability,
            availability,
            legacy_fallback,
            allow_estimated_walker,
        )

    def build_lcf_comparison_result(
        self,
        model_name,
        material_name,
        temperature,
        sigma_max,
        sigma_min,
        sigma_a,
        sigma_m,
        capability,
        availability,
        legacy_fallback,
        allow_estimated_walker,
    ):
        mat = self.materials[material_name]
        terms = self.resolve_lcf_terms(capability, mat, legacy_fallback)
        if terms is None:
            reason = availability.reason if availability is not None else "Required LCF properties are unavailable."
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode="LCF",
                predicted_life_cycles=None,
                reversals=None,
                availability="UNAVAILABLE",
                temperature_capability=self.capability_display_label(capability.capability),
                property_basis=self.comparison_property_basis(capability, model_name, legacy_fallback, unavailable_reason=reason),
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=False,
                estimated_parameter_used=False,
                warnings=self.unique_strings(list(capability.warnings) + [reason]),
                assumptions=self.comparison_assumptions(model_name),
                status="UNAVAILABLE",
                reason=reason,
            )

        E = terms["E"]
        K_dash = terms["K_dash"]
        n_dash = terms["n_dash"]
        sigma_f_dash = terms["sigma_f_dash"]
        b = terms["b"]
        epsilon_f_dash = terms["epsilon_f_dash"]
        c = terms["c"]
        temperature_note = terms["temperature_note"]
        calculation_status = terms["calculation_status"]
        property_basis = terms["property_basis"]
        used_legacy = terms["used_legacy_fallback"]
        used_temperature = terms["used_temperature_properties"]
        warnings = list(capability.warnings)
        lcf_neuber_state = self.resolve_lcf_neuber_state(
            sigma_max,
            sigma_min,
            stress_source=self.stress_source_box.currentText(),
            analysis_mode="LCF",
        )

        if model_name == "None":
            sigma_a_for_model = sigma_a
            if lcf_neuber_state["active"]:
                if not lcf_neuber_state["valid"]:
                    return self.unavailable_comparison_result(
                        model_name,
                        "LCF",
                        capability,
                        availability,
                        legacy_fallback,
                        lcf_neuber_state.get("reason") or SIMPLE_LCF_NEUBER_UNRESOLVED_REASON,
                        temperature_note,
                        property_basis,
                    )
                neuber_result = self.solve_neuber_local_response(
                    lcf_neuber_state["sigma_elastic_ref"],
                    E,
                    K_dash,
                    n_dash,
                )
                if neuber_result is None:
                    return self.unavailable_comparison_result(
                        model_name,
                        "LCF",
                        capability,
                        availability,
                        legacy_fallback,
                        "Neuber local stress-strain solution could not be bracketed for the selected material and stress inputs.",
                        temperature_note,
                        property_basis,
                    )
                sigma_a_for_model = neuber_result["epsilon_a_local"]

            solve_result = self.solve_life(sigma_a_for_model, E, sigma_f_dash, b, epsilon_f_dash, c)
            if solve_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "A valid uncorrected LCF life could not be bracketed for the selected material and stress inputs.",
                    temperature_note,
                    property_basis,
                )
            life, reversals, _, _, _ = solve_result
            availability_label = self.comparison_availability_label(
                capability,
                availability,
                used_legacy,
                estimated_parameter_used=False,
                used_temperature=used_temperature,
            )
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode="LCF",
                predicted_life_cycles=life,
                reversals=reversals,
                availability=availability_label,
                temperature_capability=self.capability_display_label(capability.capability),
                property_basis=property_basis,
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=used_legacy,
                estimated_parameter_used=False,
                warnings=self.unique_strings(warnings + ([temperature_note] if temperature_note else []) + (["Legacy fatigue constants were used for the strain-life coefficients."] if used_legacy and self.calculation_uses_legacy_constants(calculation_status) else [])),
                assumptions=self.comparison_assumptions(model_name),
                status=availability_label,
                reason="",
            )

        if model_name == "Morrow":
            if not np.isfinite(sigma_f_dash) or not np.isfinite(sigma_m):
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "Morrow correction requires finite material and stress values.",
                    temperature_note,
                    property_basis,
                )
            morrow_sigma_f_dash = sigma_f_dash - sigma_m
            if morrow_sigma_f_dash <= 0:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "The Morrow elastic coefficient becomes non-positive for the entered mean stress.",
                    temperature_note,
                    property_basis,
                )
            uncorrected_result = self.solve_life(sigma_a, E, sigma_f_dash, b, epsilon_f_dash, c)
            if uncorrected_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "A valid uncorrected LCF life could not be bracketed for the selected material and stress inputs.",
                    temperature_note,
                    property_basis,
                )
            uncorrected_life, uncorrected_reversals, _, _, _ = uncorrected_result
            morrow_raw_result = self.solve_life(sigma_a, E, morrow_sigma_f_dash, b, epsilon_f_dash, c)
            if morrow_raw_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "A valid Morrow-corrected LCF life could not be bracketed for the selected material and stress inputs.",
                    temperature_note,
                    property_basis,
                )
            morrow_life_raw, morrow_reversals_raw, _, _, _ = morrow_raw_result
            morrow_life = morrow_life_raw
            morrow_reversals = morrow_reversals_raw
            cap_message = None
            if sigma_m < 0 and morrow_life_raw > uncorrected_life:
                morrow_life = uncorrected_life
                morrow_reversals = uncorrected_reversals
                cap_message = "Compressive mean-stress life benefit conservatively capped at uncorrected life."
            availability_label = self.comparison_availability_label(
                capability,
                availability,
                used_legacy,
                estimated_parameter_used=False,
                used_temperature=used_temperature,
            )
            warnings.extend(
                [temperature_note] if temperature_note else []
            )
            if cap_message:
                warnings.append(cap_message)
            if used_legacy and self.calculation_uses_legacy_constants(calculation_status):
                warnings.append("Legacy fatigue constants were used for the strain-life coefficients.")
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode="LCF",
                predicted_life_cycles=morrow_life,
                reversals=morrow_reversals,
                availability=availability_label,
                temperature_capability=self.capability_display_label(capability.capability),
                property_basis=property_basis,
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=used_legacy,
                estimated_parameter_used=False,
                warnings=self.unique_strings(warnings),
                assumptions=self.comparison_assumptions(model_name),
                status=availability_label,
                reason=cap_message or "",
            )

        if model_name == "Walker":
            gamma_info = self.resolve_walker_gamma(
                capability,
                material_name,
                temperature,
                allow_estimated=allow_estimated_walker,
            )
            if gamma_info is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "Walker gamma is unavailable at the selected temperature. Enable estimated Walker gamma only where an estimated value is explicitly present.",
                    temperature_note,
                    property_basis,
                )
            gamma = gamma_info["gamma"]
            elastic_strain = sigma_a / E
            plastic_strain = (sigma_a / K_dash) ** (1 / n_dash)
            strain_amplitude = elastic_strain + plastic_strain
            walker_factor = self.walker_strain_factor(sigma_max, sigma_a, gamma)
            if walker_factor is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "Walker equivalent strain factor could not be calculated for the entered stresses and gamma.",
                    temperature_note,
                    property_basis,
                )
            walker_equivalent_strain = strain_amplitude * walker_factor
            uncorrected_result = self.solve_life(strain_amplitude, E, sigma_f_dash, b, epsilon_f_dash, c)
            if uncorrected_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "A valid uncorrected LCF life could not be bracketed for the selected material and stress inputs.",
                    temperature_note,
                    property_basis,
                )
            uncorrected_life, uncorrected_reversals, _, _, _ = uncorrected_result
            walker_result = self.solve_life_with_rhs(
                strain_amplitude,
                lambda nf: self.walker_lcf_rhs(
                    nf,
                    E,
                    sigma_max,
                    sigma_a,
                    sigma_f_dash,
                    b,
                    epsilon_f_dash,
                    c,
                    gamma,
                ),
            )
            if walker_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "A valid Walker-corrected LCF life could not be bracketed for the selected material and stress inputs.",
                    temperature_note,
                    property_basis,
                )
            walker_life, walker_reversals = walker_result
            availability_label = self.comparison_availability_label(
                capability,
                availability,
                used_legacy,
                estimated_parameter_used=gamma_info["estimated"],
                used_temperature=used_temperature,
            )
            warnings.extend(
                [temperature_note] if temperature_note else []
            )
            if gamma_info["estimated"]:
                warnings.append("ESTIMATED WALKER PARAMETER - not a calibrated material gamma.")
            if used_legacy and self.calculation_uses_legacy_constants(calculation_status):
                warnings.append("Legacy fatigue constants were used for the strain-life coefficients.")
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode="LCF",
                predicted_life_cycles=walker_life,
                reversals=walker_reversals,
                availability=availability_label,
                temperature_capability=self.capability_display_label(capability.capability),
                property_basis=self.comparison_property_basis(
                    capability,
                    model_name,
                    legacy_fallback,
                    property_basis=property_basis,
                    gamma_info=gamma_info,
                ),
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=used_legacy,
                estimated_parameter_used=gamma_info["estimated"],
                warnings=self.unique_strings(warnings),
                assumptions=self.comparison_assumptions(model_name, gamma_info=gamma_info),
                status=availability_label,
                reason="",
            )

        if model_name == "SWT":
            if sigma_max <= 0:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "Conventional SWT requires a positive maximum cycle stress; fully compressive cycles are not supported.",
                    temperature_note,
                    property_basis,
                )
            if not all(is_finite_number(value) for value in (E, K_dash, n_dash, sigma_f_dash, b, epsilon_f_dash, c, sigma_a, sigma_m)):
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "SWT correction requires finite material constants and stress inputs.",
                    temperature_note,
                    property_basis,
                )
            elastic_strain = sigma_a / E
            plastic_strain = (sigma_a / K_dash) ** (1 / n_dash)
            strain_amplitude = elastic_strain + plastic_strain
            if not np.isfinite(strain_amplitude) or strain_amplitude <= 0:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "SWT correction requires finite, positive strain amplitude and material data.",
                    temperature_note,
                    property_basis,
                )
            swt_parameter = sigma_max * strain_amplitude
            if not np.isfinite(swt_parameter) or swt_parameter <= 0:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "The SWT damage parameter must be positive and finite.",
                    temperature_note,
                    property_basis,
                )
            uncorrected_result = self.solve_life(strain_amplitude, E, sigma_f_dash, b, epsilon_f_dash, c)
            if uncorrected_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "A valid uncorrected LCF life could not be bracketed for the selected material and stress inputs.",
                    temperature_note,
                    property_basis,
                )
            uncorrected_life, uncorrected_reversals, _, _, _ = uncorrected_result
            swt_result = self.solve_life_with_rhs(
                swt_parameter,
                lambda nf: self.swt_rhs(nf, E, sigma_f_dash, b, epsilon_f_dash, c),
            )
            if swt_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "LCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "A valid SWT-corrected LCF life could not be bracketed for the selected material and stress inputs.",
                    temperature_note,
                    property_basis,
                )
            swt_life, swt_reversals = swt_result
            availability_label = self.comparison_availability_label(
                capability,
                availability,
                used_legacy,
                estimated_parameter_used=False,
                used_temperature=used_temperature,
            )
            warnings.extend(
                [temperature_note] if temperature_note else []
            )
            if used_legacy and self.calculation_uses_legacy_constants(calculation_status):
                warnings.append("Legacy fatigue constants were used for the strain-life coefficients.")
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode="LCF",
                predicted_life_cycles=swt_life,
                reversals=swt_reversals,
                availability=availability_label,
                temperature_capability=self.capability_display_label(capability.capability),
                property_basis=property_basis,
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=used_legacy,
                estimated_parameter_used=False,
                warnings=self.unique_strings(warnings),
                assumptions=self.comparison_assumptions(model_name, swt_parameter=swt_parameter),
                status=availability_label,
                reason="",
            )

        return self.unavailable_comparison_result(
            model_name,
            "LCF",
            capability,
            availability,
            legacy_fallback,
            "Unsupported comparison model.",
            temperature_note,
            property_basis,
        )

    def build_hcf_comparison_result(
        self,
        model_name,
        material_name,
        temperature,
        sigma_max,
        sigma_min,
        sigma_a,
        sigma_m,
        capability,
        availability,
        legacy_fallback,
        allow_estimated_walker,
    ):
        mat = self.materials[material_name]
        terms = self.resolve_hcf_terms(capability, mat, legacy_fallback, model_name)
        if terms is None:
            reason = availability.reason if availability is not None else "Required HCF properties are unavailable."
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode="HCF",
                predicted_life_cycles=None,
                reversals=None,
                availability="UNAVAILABLE",
                temperature_capability=self.capability_display_label(capability.capability),
                property_basis=self.comparison_property_basis(capability, model_name, legacy_fallback, unavailable_reason=reason),
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=False,
                estimated_parameter_used=False,
                warnings=self.unique_strings(list(capability.warnings) + [reason]),
                assumptions=self.comparison_assumptions(model_name),
                status="UNAVAILABLE",
                reason=reason,
            )

        sigma_f_dash = terms["sigma_f_dash"]
        b = terms["b"]
        S_u = terms["S_u"]
        temperature_note = terms["temperature_note"]
        calculation_status = terms["calculation_status"]
        property_basis = terms["property_basis"]
        used_legacy = terms["used_legacy_fallback"]
        used_temperature = terms["used_temperature_properties"]
        warnings = list(capability.warnings)
        hcf_context = self.resolve_hcf_notch_state(sigma_max, sigma_min, analysis_mode="HCF")
        notch_state = hcf_context["notch"]
        sigma_a_for_model = hcf_context["sigma_a_eff"] if notch_state["active"] and notch_state["valid"] else sigma_a
        sigma_m_for_model = hcf_context["sigma_m_eff"] if notch_state["active"] and notch_state["valid"] else sigma_m

        if model_name == "None":
            basquin_result = self.calculate_basquin_life(sigma_a_for_model, sigma_f_dash, b)
            if basquin_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "The HCF life calculation produced an invalid result.",
                    temperature_note,
                    property_basis,
                )
            life, reversals = basquin_result
            availability_label = self.comparison_availability_label(
                capability,
                availability,
                used_legacy,
                estimated_parameter_used=False,
                used_temperature=used_temperature,
            )
            warnings.extend(
                [temperature_note] if temperature_note else []
            )
            if used_legacy and self.calculation_uses_legacy_constants(calculation_status):
                warnings.append("Legacy fatigue constants were used for the Basquin relation.")
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode="HCF",
                predicted_life_cycles=life,
                reversals=reversals,
                availability=availability_label,
                temperature_capability=self.capability_display_label(capability.capability),
                property_basis=property_basis,
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=used_legacy,
                estimated_parameter_used=False,
                warnings=self.unique_strings(warnings),
                assumptions=self.comparison_assumptions(model_name),
                status=availability_label,
                reason="",
            )

        if model_name == "Goodman":
            if S_u is None or not np.isfinite(S_u) or S_u <= 0:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "Goodman correction is not available for this material because a valid S_u_MPa value is not present in the material database.",
                    temperature_note,
                    property_basis,
                )
            if sigma_m_for_model >= S_u:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "Goodman correction requires mean stress to be less than the ultimate tensile strength S_u.",
                    temperature_note,
                    property_basis,
                )
            denominator = 1.0 - sigma_m_for_model / S_u
            if not np.isfinite(denominator) or denominator <= 0:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "The Goodman correction denominator is zero or negative for the entered mean stress.",
                    temperature_note,
                    property_basis,
                )
            sigma_a_eq = sigma_a_for_model / denominator
            uncorrected_result = self.calculate_basquin_life(sigma_a_for_model, sigma_f_dash, b)
            if uncorrected_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "The HCF life calculation produced an invalid result.",
                    temperature_note,
                    property_basis,
                )
            uncorrected_life, uncorrected_reversals = uncorrected_result
            goodman_raw_result = self.calculate_basquin_life(sigma_a_eq, sigma_f_dash, b)
            if goodman_raw_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "The Goodman-corrected HCF life calculation produced an invalid result.",
                    temperature_note,
                    property_basis,
                )
            goodman_life_raw, goodman_reversals_raw = goodman_raw_result
            goodman_life = goodman_life_raw
            goodman_reversals = goodman_reversals_raw
            cap_message = None
            if sigma_m_for_model < 0 and goodman_life_raw > uncorrected_life:
                goodman_life = uncorrected_life
                goodman_reversals = uncorrected_reversals
                cap_message = "Compressive mean-stress life benefit conservatively capped at uncorrected life."
            availability_label = self.comparison_availability_label(
                capability,
                availability,
                used_legacy,
                estimated_parameter_used=False,
                used_temperature=used_temperature,
            )
            warnings.extend(
                [temperature_note] if temperature_note else []
            )
            if cap_message:
                warnings.append(cap_message)
            if used_legacy and self.calculation_uses_legacy_constants(calculation_status):
                warnings.append("Legacy Basquin fatigue constants were used for the HCF relation.")
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode="HCF",
                predicted_life_cycles=goodman_life,
                reversals=goodman_reversals,
                availability=availability_label,
                temperature_capability=self.capability_display_label(capability.capability),
                property_basis=property_basis,
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=used_legacy,
                estimated_parameter_used=False,
                warnings=self.unique_strings(warnings),
                assumptions=self.comparison_assumptions(model_name),
                status=availability_label,
                reason=cap_message or "",
            )

        if model_name == "Walker":
            if notch_state["active"]:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    WALKER_NOMINAL_NOTCH_UNRESOLVED_REASON,
                    temperature_note,
                    property_basis,
                )
            gamma_info = self.resolve_walker_gamma(
                capability,
                material_name,
                temperature,
                allow_estimated=allow_estimated_walker,
            )
            if gamma_info is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "Walker gamma is unavailable at the selected temperature.",
                    temperature_note,
                    property_basis,
                )
            gamma = gamma_info["gamma"]
            sigma_eq = self.walker_equivalent_stress(sigma_max, sigma_a, gamma)
            if sigma_eq is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "Walker equivalent stress could not be calculated for the entered stresses and gamma.",
                    temperature_note,
                    property_basis,
                )
            walker_result = self.calculate_basquin_life(sigma_eq, sigma_f_dash, b)
            if walker_result is None:
                return self.unavailable_comparison_result(
                    model_name,
                    "HCF",
                    capability,
                    availability,
                    legacy_fallback,
                    "The Walker-corrected HCF life calculation produced an invalid result.",
                    temperature_note,
                    property_basis,
                )
            walker_life, walker_reversals = walker_result
            availability_label = self.comparison_availability_label(
                capability,
                availability,
                used_legacy,
                estimated_parameter_used=gamma_info["estimated"],
                used_temperature=used_temperature,
            )
            warnings.extend(
                [temperature_note] if temperature_note else []
            )
            if gamma_info["estimated"]:
                warnings.append("ESTIMATED WALKER PARAMETER - not a calibrated material gamma.")
        if self.calculation_uses_legacy_constants(calculation_status):
            warnings.append("Legacy fatigue constants were used for the HCF relation.")
            return ComparisonModelResult(
                model_name=model_name,
                analysis_mode="HCF",
                predicted_life_cycles=walker_life,
                reversals=walker_reversals,
                availability=availability_label,
                temperature_capability=self.capability_display_label(capability.capability),
                property_basis=self.comparison_property_basis(
                    capability,
                    model_name,
                    legacy_fallback,
                    property_basis=property_basis,
                    gamma_info=gamma_info,
                ),
                condition_compatibility=capability.condition_compatibility,
                legacy_fallback_used=used_legacy,
                estimated_parameter_used=gamma_info["estimated"],
                warnings=self.unique_strings(warnings),
                assumptions=self.comparison_assumptions(model_name, gamma_info=gamma_info),
                status=availability_label,
                reason="",
            )

        return self.unavailable_comparison_result(
            model_name,
            "HCF",
            capability,
            availability,
            legacy_fallback,
            "Unsupported comparison model.",
            temperature_note,
            property_basis,
        )

    def resolve_lcf_terms(self, capability, mat, legacy_fallback):
        if self.all_required_properties_resolved(capability) and not self.condition_mismatch_blocked(capability):
            e_item = self.get_capability_item(capability, "E_MPa")
            k_item = self.get_capability_item(capability, "K_dash")
            n_item = self.get_capability_item(capability, "n_dash")
            sigma_f_item = self.get_capability_item(capability, "sigma_f_dash")
            b_item = self.get_capability_item(capability, "b")
            epsilon_f_item = self.get_capability_item(capability, "epsilon_f_dash")
            c_item = self.get_capability_item(capability, "c")
            items = [e_item, k_item, n_item, sigma_f_item, b_item, epsilon_f_item, c_item]
            if any(item is None or item.value is None for item in items):
                return None
            return {
                "E": e_item.value,
                "K_dash": k_item.value,
                "n_dash": n_item.value,
                "sigma_f_dash": sigma_f_item.value,
                "b": b_item.value,
                "epsilon_f_dash": epsilon_f_item.value,
                "c": c_item.value,
                "property_basis": self.property_basis_summary(items),
                "temperature_note": None,
                "calculation_status": "READY_WITH_CONDITION_WARNING" if self.condition_warning_required(capability) else "FULLY TEMPERATURE RESOLVED",
                "used_temperature_properties": True,
                "used_legacy_fallback": False,
            }

        if not legacy_fallback:
            return None

        e_item = self.get_capability_item(capability, "E_MPa")
        used_temperature_E = e_item is not None and e_item.status in {"EXACT", "INTERPOLATED"} and e_item.value is not None
        E = e_item.value if used_temperature_E else mat["E"]
        property_basis = "Temperature-resolved Young's modulus used with legacy fatigue constants." if used_temperature_E else "Legacy Young's modulus and legacy fatigue constants used."
        return {
            "E": E,
            "K_dash": mat["K_dash"],
            "n_dash": mat["n_dash"],
            "sigma_f_dash": mat["sigma_f_dash"],
            "b": mat["b"],
            "epsilon_f_dash": mat["epsilon_f_dash"],
            "c": mat["c"],
            "property_basis": property_basis,
            "temperature_note": "Temperature-resolved Young's modulus used with legacy fatigue constants." if used_temperature_E else "Legacy Young's modulus and legacy fatigue constants used.",
            "calculation_status": "LEGACY / PARTIALLY TEMPERATURE-INFORMED ESTIMATE" if capability.capability == PARTIALLY_TEMPERATURE_INFORMED else "LEGACY / TEMPERATURE-UNRESOLVED ESTIMATE",
            "used_temperature_properties": used_temperature_E,
            "used_legacy_fallback": True,
        }

    def resolve_hcf_terms(self, capability, mat, legacy_fallback, model_name):
        if self.all_required_properties_resolved(capability) and not self.condition_mismatch_blocked(capability):
            sigma_f_item = self.get_capability_item(capability, "sigma_f_dash")
            b_item = self.get_capability_item(capability, "b")
            su_item = self.get_capability_item(capability, "S_u_MPa")
            items = [sigma_f_item, b_item]
            if any(item is None or item.value is None for item in items):
                return None
            if model_name == "Goodman" and (su_item is None or su_item.value is None):
                return None
            return {
                "sigma_f_dash": sigma_f_item.value,
                "b": b_item.value,
                "S_u": su_item.value if model_name == "Goodman" else None,
                "property_basis": self.property_basis_summary([item for item in [sigma_f_item, b_item, su_item if model_name == "Goodman" else None] if item is not None]),
                "temperature_note": None,
                "calculation_status": "READY_WITH_CONDITION_WARNING" if self.condition_warning_required(capability) else "FULLY TEMPERATURE RESOLVED",
                "used_temperature_properties": True,
                "used_legacy_fallback": False,
            }

        if not legacy_fallback:
            return None

        sigma_f_item = self.get_capability_item(capability, "sigma_f_dash")
        b_item = self.get_capability_item(capability, "b")
        used_temperature_sigma_f = sigma_f_item is not None and sigma_f_item.status in {"EXACT", "INTERPOLATED"} and sigma_f_item.value is not None
        used_temperature_b = b_item is not None and b_item.status in {"EXACT", "INTERPOLATED"} and b_item.value is not None
        sigma_f_dash = sigma_f_item.value if used_temperature_sigma_f else mat["sigma_f_dash"]
        b = b_item.value if used_temperature_b else mat["b"]

        if model_name == "Goodman":
            su_item = self.get_capability_item(capability, "S_u_MPa")
            used_temperature_su = su_item is not None and su_item.status in {"EXACT", "INTERPOLATED"} and su_item.value is not None
            if not used_temperature_su and mat.get("S_u") is None:
                return None
            S_u = su_item.value if used_temperature_su else mat["S_u"]
            property_basis = (
                "Temperature-resolved S_u used with legacy Basquin fatigue constants."
                if used_temperature_su
                else "Legacy Goodman strength correction used; Basquin fatigue constants are legacy/temperature-unresolved."
            )
            temperature_note = property_basis
        else:
            S_u = None
            property_basis = "Legacy Basquin fatigue constants used; temperature-resolved fatigue data are unavailable."
            temperature_note = property_basis

        used_temperature_properties = used_temperature_sigma_f or used_temperature_b or (model_name == "Goodman" and "Temperature-resolved S_u" in property_basis)
        calculation_status = "LEGACY / PARTIALLY TEMPERATURE-INFORMED ESTIMATE" if capability.capability == PARTIALLY_TEMPERATURE_INFORMED else "LEGACY / TEMPERATURE-UNRESOLVED ESTIMATE"
        return {
            "sigma_f_dash": sigma_f_dash,
            "b": b,
            "S_u": S_u,
            "property_basis": property_basis,
            "temperature_note": temperature_note,
            "calculation_status": calculation_status,
            "used_temperature_properties": used_temperature_properties,
            "used_legacy_fallback": True,
        }

    def property_basis_summary(self, items):
        bases = []
        for item in items:
            if item is None:
                continue
            basis = getattr(item, "basis", "") or ""
            if basis and basis not in bases:
                bases.append(basis)
        return "; ".join(bases) if bases else "-"

    def comparison_property_basis(self, capability, model_name, legacy_fallback, property_basis=None, gamma_info=None, unavailable_reason=None):
        if unavailable_reason:
            return unavailable_reason
        if property_basis:
            return property_basis
        if gamma_info is not None:
            pieces = [f"Walker gamma basis: {gamma_info['basis']}"]
            if gamma_info.get("estimated"):
                pieces.append("estimated Walker gamma")
            return "; ".join(pieces)
        if legacy_fallback and capability.capability != FULLY_TEMPERATURE_RESOLVED:
            return "Legacy fatigue constants"
        return "-"

    def comparison_availability_label(self, capability, availability, used_legacy, estimated_parameter_used, used_temperature):
        if availability is None or not availability.enabled:
            return "UNAVAILABLE"
        if estimated_parameter_used:
            return "AVAILABLE_ESTIMATED"
        if capability.capability == FULLY_TEMPERATURE_RESOLVED:
            return "AVAILABLE_FULL"
        if used_legacy and used_temperature:
            return "AVAILABLE_PARTIAL"
        if used_legacy:
            return "AVAILABLE_LEGACY"
        if capability.capability == PARTIALLY_TEMPERATURE_INFORMED:
            return "AVAILABLE_PARTIAL"
        return "AVAILABLE_FULL"

    def comparison_assumptions(self, model_name, gamma_info=None, swt_parameter=None):
        assumptions = []
        if model_name == "None":
            assumptions.append("No mean-stress correction applied.")
        elif model_name == "Morrow":
            assumptions.append("Morrow acts only on the elastic fatigue term.")
        elif model_name == "Walker":
            assumptions.append("Walker uses the documented sigma_max^(1-gamma) * sigma_a^gamma convention.")
            assumptions.append("R = -1 recovery remains a regression requirement.")
            if gamma_info is not None and gamma_info.get("estimated"):
                assumptions.append("Walker gamma is an estimated parameter, not a calibrated material fit.")
        elif model_name == "SWT":
            assumptions.append("SWT uses sigma_max * epsilon_a with total strain amplitude.")
            assumptions.append("Conventional SWT requires positive sigma_max and does not support fully compressive cycles.")
            if swt_parameter is not None:
                assumptions.append(f"SWT parameter P_SWT = {swt_parameter:,.6g}.")
        elif model_name == "Goodman":
            assumptions.append("Goodman is a reference S_u-based engineering estimate.")
        return assumptions

    def unavailable_comparison_result(
        self,
        model_name,
        analysis_mode,
        capability,
        availability,
        legacy_fallback,
        reason,
        temperature_note,
        property_basis,
    ):
        warnings = list(capability.warnings)
        if temperature_note:
            warnings.append(temperature_note)
        warnings.append(reason)
        return ComparisonModelResult(
            model_name=model_name,
            analysis_mode=analysis_mode,
            predicted_life_cycles=None,
            reversals=None,
            availability="UNAVAILABLE",
            temperature_capability=self.capability_display_label(capability.capability),
            property_basis=property_basis,
            condition_compatibility=capability.condition_compatibility,
            legacy_fallback_used=legacy_fallback and capability.capability != FULLY_TEMPERATURE_RESOLVED,
            estimated_parameter_used=False,
            warnings=self.unique_strings(warnings),
            assumptions=self.comparison_assumptions(model_name),
            status="UNAVAILABLE",
            reason=reason,
        )

    def unique_strings(self, values):
        ordered = []
        for value in values:
            if not value:
                continue
            if value not in ordered:
                ordered.append(value)
        return ordered

    def format_comparison_summary(self, summary):
        lines = [
            "MODEL COMPARISON",
            f"Material: {summary.material}",
            f"Analysis Mode: {summary.analysis_mode}",
            f"Analysis Temperature (C): {summary.temperature_C:,.6g}",
            f"Maximum Stress (MPa): {summary.sigma_max_MPa:,.6g}",
            f"Minimum Stress (MPa): {summary.sigma_min_MPa:,.6g}",
            f"Stress Amplitude (MPa): {summary.sigma_a_MPa:,.6g}",
            f"Mean Stress (MPa): {summary.sigma_m_MPa:,.6g}",
            "",
            f"{'Model':<12} {'Availability':<22} {'Life (cycles)':<16} {'Reversals':<16} Notes",
            "-" * 90,
        ]

        for result in summary.model_results:
            life = self.format_life_value(result.predicted_life_cycles) if result.predicted_life_cycles is not None else "-"
            reversals = self.format_life_value(result.reversals) if result.reversals is not None else "-"
            note = result.reason or ("; ".join(result.warnings[-2:]) if result.warnings else "")
            lines.append(
                f"{result.model_name:<12} {result.availability:<22} {life:<16} {reversals:<16} {note}"
            )

        lines.append("")
        if summary.lowest_predicted_life_model and summary.lowest_predicted_life_cycles is not None:
            lines.append(
                "Lowest predicted life: {0} — {1} cycles".format(
                    summary.lowest_predicted_life_model,
                    self.format_life_value(summary.lowest_predicted_life_cycles),
                )
            )
        else:
            lines.append("Lowest predicted life: -")
        lines.append(
            "The lowest mathematical prediction is not automatically the preferred or validated engineering model."
        )

        if summary.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in summary.warnings:
                lines.append(f"- {warning}")
        if summary.assumptions:
            lines.append("")
            lines.append("Comparison assumptions:")
            for assumption in summary.assumptions:
                lines.append(f"- {assumption}")
        return "\n".join(lines)

    def show_comparison_plot(self, summary):
        available = [
            result
            for result in summary.model_results
            if result.predicted_life_cycles is not None and result.status != "UNAVAILABLE"
        ]
        if not available:
            self.close_plot_window()
            return

        plot_window = self.show_plot_window("Fatigue Model Comparison")
        plot_window.ax.clear()
        plot_window.ax.set_yscale("log")
        capability_label = FULLY_TEMPERATURE_RESOLVED
        if any(result.legacy_fallback_used for result in summary.model_results):
            capability_label = PARTIALLY_TEMPERATURE_INFORMED
        plot_window.ax.set_title(
            self.plot_title(
                "Fatigue Model Comparison",
                summary.temperature_C,
                any(result.legacy_fallback_used for result in summary.model_results),
                capability_label,
            )
        )
        plot_window.ax.set_xlabel("Model")
        plot_window.ax.set_ylabel("Predicted Life (cycles)")
        plot_window.ax.grid(True, which="both", linestyle="--", linewidth=0.5)

        x_positions = np.arange(len(summary.model_results))
        plot_window.ax.scatter(
            [idx for idx, result in enumerate(summary.model_results) if result.predicted_life_cycles is not None],
            [result.predicted_life_cycles for result in summary.model_results if result.predicted_life_cycles is not None],
            s=60,
            label="Available model predictions",
        )
        plot_window.ax.set_xticks(x_positions)
        plot_window.ax.set_xticklabels([result.model_name for result in summary.model_results])

        for idx, result in enumerate(summary.model_results):
            if result.predicted_life_cycles is not None:
                plot_window.ax.annotate(
                    self.format_life_value(result.predicted_life_cycles),
                    (idx, result.predicted_life_cycles),
                    textcoords="offset points",
                    xytext=(0, 8),
                    ha="center",
                    fontsize=8,
                )
            else:
                plot_window.ax.text(
                    idx,
                    0.02,
                    "UNAVAILABLE",
                    transform=plot_window.ax.get_xaxis_transform(),
                    ha="center",
                    va="bottom",
                    rotation=90,
                    fontsize=8,
                    color="gray",
                )

        if available:
            y_min = max(min(result.predicted_life_cycles for result in available) / 10.0, 1e-12)
            y_max = max(result.predicted_life_cycles for result in available) * 10.0
            if np.isfinite(y_min) and np.isfinite(y_max) and y_max > y_min:
                plot_window.ax.set_ylim(y_min, y_max)

        plot_window.ax.legend()
        plot_window.redraw()

    def get_capability_item(self, capability, property_name):
        for item in capability.required_properties:
            if item.property_name == property_name:
                return item
        return None

    def resolve_walker_gamma(self, capability, material_name, temperature, allow_estimated):
        gamma_item = self.get_capability_item(capability, "Walker_gamma")
        if gamma_item is not None and gamma_item.status in {"EXACT", "INTERPOLATED"}:
            return self.build_walker_gamma_info(gamma_item, allow_estimated)

        walker_condition = self.get_walker_condition(material_name)
        if walker_condition is None:
            return None

        result = get_property(
            self.walker_rows,
            material_name,
            "Walker_gamma",
            temperature,
            walker_condition,
        )
        if result.status not in {"EXACT", "INTERPOLATED"}:
            return None

        gamma_item = SimpleNamespace(
            property_name="Walker_gamma",
            value=result.value,
            status=result.status,
            source=result.source,
            condition=result.condition,
            basis=result.basis,
            interpolated=result.interpolated,
            warning=result.warning,
        )

        return self.build_walker_gamma_info(gamma_item, allow_estimated)

    def build_walker_gamma_info(self, gamma_item, allow_estimated):
        gamma = gamma_item.value
        if gamma is None or not np.isfinite(gamma) or gamma <= 0 or gamma > 1:
            return None

        basis = gamma_item.basis or ""
        is_estimated = "estimated" in basis.lower()
        if is_estimated and not allow_estimated:
            return None

        return {
            "gamma": gamma,
            "basis": basis or "-",
            "source": gamma_item.source or "-",
            "condition": gamma_item.condition or "-",
            "status": gamma_item.status,
            "interpolated": gamma_item.interpolated,
            "estimated": is_estimated,
        }

    def walker_equivalent_stress(self, sigma_max, sigma_a, gamma):
        # Walker HCF convention:
        # sigma_eq = sigma_max^(1-gamma) * sigma_a^gamma
        # The sigma_max > 0 requirement is specific to this Walker domain;
        # it must not be propagated to Goodman, Morrow, or None modes.
        if sigma_max <= 0 or sigma_a <= 0:
            return None
        if gamma <= 0 or gamma > 1 or not np.isfinite(gamma):
            return None
        sigma_eq = (sigma_max ** (1.0 - gamma)) * (sigma_a ** gamma)
        if not np.isfinite(sigma_eq) or sigma_eq <= 0:
            return None
        return sigma_eq

    def swt_rhs(self, Nf, E, sigma_f_dash, b, epsilon_f_dash, c):
        # SWT convention:
        # P_SWT = sigma_max * epsilon_a = (sigma_f'^2 / E) * (2Nf)^(2b)
        #          + sigma_f' * epsilon_f' * (2Nf)^(b+c)
        reversals = 2.0 * Nf
        return (sigma_f_dash ** 2 / E) * reversals ** (2.0 * b) + sigma_f_dash * epsilon_f_dash * reversals ** (b + c)

    def walker_lcf_rhs(
        self,
        Nf,
        E,
        sigma_max,
        sigma_a,
        sigma_f_dash,
        b,
        epsilon_f_dash,
        c,
        gamma,
    ):
        # Walker LCF convention:
        # epsilon_a,eq = epsilon_a * (sigma_max / sigma_a)^(1-gamma)
        # This equivalent-total-strain form is intentional. A prior
        # elastic-term-only variant was rejected because it did not recover
        # the existing R = -1 strain-life solution when plastic strain was
        # present.
        factor = self.walker_strain_factor(sigma_max, sigma_a, gamma)
        if factor is None:
            return np.nan
        return self.strain_life_rhs(Nf, E, sigma_f_dash, b, epsilon_f_dash, c) / factor

    def walker_strain_factor(self, sigma_max, sigma_a, gamma):
        # The sigma_max > 0 requirement is specific to this Walker domain;
        # it must not be propagated to Goodman, Morrow, or None modes.
        if sigma_max <= 0 or sigma_a <= 0:
            return None
        if gamma <= 0 or gamma > 1 or not np.isfinite(gamma):
            return None
        factor = (sigma_max / sigma_a) ** (1.0 - gamma)
        if not np.isfinite(factor) or factor <= 0:
            return None
        return factor

    def solve_life_with_rhs(self, target_strain, rhs_function):
        if not np.isfinite(target_strain) or target_strain <= 0:
            return None

        lower = 1e-12
        upper = 1e3
        max_upper = 1e12

        def f(nf):
            return rhs_function(nf) - target_strain

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
        return estimated_life, 2.0 * estimated_life

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

