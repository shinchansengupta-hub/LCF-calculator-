# LCF Life Calculator

LCF Life Calculator is a small PyQt5 desktop application for engineering fatigue screening.

It currently supports two analysis modes:

- Strain-Life / LCF
- Stress-Life / HCF

The application now supports temperature-aware property lookup from:

- `materials_static.csv`
- `materials_fatigue.csv`

It also keeps the legacy room/reference material table in `materials.csv` for fallback calculations when explicitly enabled.

## What problem it solves

The calculator provides a compact desktop tool for approximate fatigue screening when you need:

- low-cycle fatigue life from a strain-life relation
- high-cycle fatigue life from a basic stress-life relation
- temperature-aware property resolution when source data are available
- a simple plot of the selected fatigue relation with the operating point highlighted

It is intended as an engineering estimate tool, not a certified lifing method.

## Analysis temperature

The GUI includes:

- `Analysis Temperature (°C)`

This input is numeric and finite.

The application uses the selected temperature to resolve available material properties from the temperature-dependent datasets.

Key rules:

- exact source temperatures are used directly
- permitted interpolation is used only where the resolver explicitly allows it
- no extrapolation is performed
- if a required property is outside the source range, the result is reported as unavailable

## Material databases

### `materials.csv`

This is the legacy material registry used by the current calculator for reference/fallback calculations.

It contains one legacy property set per material, including:

- `E_MPa`
- `K_dash`
- `n_dash`
- `sigma_f_dash`
- `b`
- `epsilon_f_dash`
- `c`
- optional `S_u_MPa`
- optional `S_y_MPa`

### `materials_static.csv`

This is the temperature-dependent static/thermal property table.

It is used for properties such as:

- `E_MPa`
- `S_u_MPa`
- `S_y_MPa`
- `CTE`-type fields

### `materials_fatigue.csv`

This is the temperature-dependent fatigue/cyclic property table.

It is used for properties such as:

- `K_dash`
- `n_dash`
- `sigma_f_dash`
- `b`
- `epsilon_f_dash`
- `c`

Current temperature-dependent fatigue coverage is limited and condition-specific. The dataset currently contains a small number of fitted source-backed rows, not a full universal fatigue database.

## Capability classification

Before a temperature-aware calculation is allowed, the application calls the capability resolver in `temperature_capability.py`.

The capability result is one of:

- `FULLY TEMPERATURE RESOLVED`
- `PARTIALLY TEMPERATURE INFORMED`
- `TEMPERATURE DATA UNAVAILABLE`

The result also reports:

- `Static Condition`
- `Fatigue Condition`
- `Condition Compatibility`
- property-level status for every required input

Condition compatibility is conservative:

- `MATCH`
- `PARTIAL_MATCH`
- `MISMATCH`
- `UNKNOWN`

The calculator does not silently treat different heat treatments, product forms, or welded/base-material datasets as equivalent.

## Temperature-aware calculation policy

### Fully temperature-resolved

If the capability resolver returns `FULLY TEMPERATURE RESOLVED`, the calculator uses temperature-resolved properties for the selected mode:

- HCF / None:
  - `sigma_f_dash(T)`
  - `b(T)`
- HCF / Goodman:
  - `sigma_f_dash(T)`
  - `b(T)`
  - `S_u_MPa(T)`
- LCF / None:
  - `E_MPa(T)`
  - `K_dash(T)`
  - `n_dash(T)`
  - `sigma_f_dash(T)`
  - `b(T)`
  - `epsilon_f_dash(T)`
  - `c(T)`
- LCF / Morrow:
  - same property set as LCF / None

### Partial or unavailable data

Many real material cases are only partially temperature-informed.

If required temperature-resolved data are not available, the calculator can optionally use legacy reference constants from `materials.csv`.

That behavior is controlled by:

- `Use legacy fatigue constants when temperature-resolved fatigue data are unavailable`

This option is OFF by default.

If the option is OFF:

- the calculation is blocked when temperature-resolved required properties are unavailable
- the results panel shows which required properties are missing or unavailable

If the option is ON:

- the calculator may use legacy `materials.csv` constants
- the result is explicitly labeled as a legacy or partially temperature-informed estimate
- the UI clearly distinguishes temperature-resolved properties from legacy properties

Important mixing rule:

- LCF does not mix cyclic fatigue constants from different datasets
- HCF Goodman may use temperature-resolved `S_u(T)` only when available, while Basquin fatigue constants remain legacy if fallback is enabled
- a result is never labeled fully temperature-resolved unless the capability resolver says so

## Analysis modes

### 1. Strain-Life / LCF

This mode uses the current strain-life workflow:

- inputs `sigma_max` and `sigma_min`
- computes stress amplitude:
  - `sigma_a = abs(sigma_max - sigma_min) / 2`
- computes mean stress:
  - `sigma_m = (sigma_max + sigma_min) / 2`
- computes elastic strain amplitude:
  - `epsilon_e,a = sigma_a / E`
- computes plastic strain amplitude using cyclic Ramberg-Osgood:
  - `epsilon_p,a = (sigma_a / K_prime)^(1 / n_prime)`
- computes total strain amplitude:
  - `epsilon_a = epsilon_e,a + epsilon_p,a`
- solves the combined Basquin-Coffin-Manson strain-life relation numerically for `Nf`
- reports both cycles to failure `Nf` and reversals to failure `2Nf`

The LCF mode uses the uncorrected strain-life relation:

- `epsilon_a = (sigma_f_prime / E) * (2*Nf)^b + epsilon_f_prime * (2*Nf)^c`

LCF mode also offers mean-stress correction:

- `None`
- `Morrow`

When `Morrow` is selected:

- `epsilon_a = ((sigma_f_prime - sigma_m) / E) * (2*Nf)^b + epsilon_f_prime * (2*Nf)^c`

The current implementation:

- computes `sigma_m` from `sigma_max` and `sigma_min`
- applies Morrow only to the elastic fatigue term
- conservatively caps compressive-mean-stress life benefit at the uncorrected life
- uses a monotonic bracketed bisection solve for `Nf`

### 2. Stress-Life / HCF

This mode uses a standalone Basquin stress-life relation:

- `sigma_a = sigma_f_prime * (2*Nf)^b`
- `Nf = 0.5 * (sigma_a / sigma_f_prime)^(1 / b)`

It uses the same `sigma_max` and `sigma_min` inputs to compute stress amplitude and mean stress.

Mean stress is currently calculated for display and, when Goodman is selected, used only if the selected data are available.

HCF mode:

- does not assume an endurance limit
- is intended for elastic-dominated fatigue
- displays an S-N style curve with log-log axes
- highlights the calculated operating point
- offers `Mean Stress Correction: None` and `Mean Stress Correction: Goodman`

HCF Goodman is conservative and source-driven:

- `sigma_a_eq = sigma_a / (1 - sigma_m / S_u)`

The application blocks Goodman if a valid `S_u_MPa` value is not available for the selected material/condition.

## Inputs

The GUI accepts:

- Material selection
- Analysis mode selection
- Mean stress correction selection
- Analysis Temperature (°C)
- Maximum stress, `sigma_max` in MPa
- Minimum stress, `sigma_min` in MPa
- Legacy fatigue fallback checkbox

Derived quantities used by both modes:

- stress amplitude, `sigma_a`
- mean stress, `sigma_m`

## Outputs

### Common temperature-aware outputs

The results area now includes:

- Analysis Temperature
- Temperature Capability
- Static Condition
- Fatigue Condition
- Condition Compatibility
- property status lines for resolved/unavailable/interpolated inputs
- Calculation Status

### LCF outputs

The Strain-Life / LCF mode displays:

- stress amplitude
- mean stress
- elastic strain amplitude
- plastic strain amplitude
- total strain amplitude
- estimated life in cycles
- reversals to failure `2Nf`

When `Morrow` is selected, the result block also shows:

- uncorrected life in cycles
- Morrow-corrected life in cycles
- uncorrected reversals `2Nf`
- Morrow-corrected reversals `2Nf`

If fallback is enabled and only part of the temperature data are available, the result is clearly labeled as a legacy or partially temperature-informed estimate.

### HCF outputs

The Stress-Life / HCF mode displays:

- maximum stress
- minimum stress
- stress amplitude
- mean stress
- estimated life in cycles
- reversals to failure `2Nf`
- a note that mean stress is calculated but not corrected when Goodman is not selected
- a note that the estimate is Basquin-based and intended for elastic-dominated HCF
- a note that the material constants do not currently include full calibration-range metadata

When `Goodman` is selected, the result block also shows:

- ultimate tensile strength, `S_u`
- Goodman-corrected stress amplitude
- uncorrected life and reversals
- Goodman-corrected life and reversals

## Material properties loaded from `materials.csv`

The legacy table still provides the current calculator with:

- material registry entries
- room/reference fatigue constants
- optional `S_u_MPa` and `S_y_MPa` values where available
- legacy material condition metadata

## GUI functionality

The desktop interface includes:

- application title
- material selection drop-down
- analysis mode drop-down
- mean stress correction drop-down
- analysis temperature input
- legacy fatigue fallback checkbox
- maximum stress input
- minimum stress input
- calculate button
- result label
- embedded Matplotlib plot

Validation includes:

- numeric checking of stress inputs
- numeric checking of analysis temperature
- `sigma_max >= sigma_min`
- `sigma_a > 0`
- mode-specific material restrictions
- capability-based property availability checks

## Plot functionality

### LCF plot

The Strain-Life / LCF plot shows:

- the strain-life curve
- the calculated operating point
- a logarithmic x-axis in reversals to failure

When Morrow is selected, the plot shows:

- the uncorrected strain-life curve
- the Morrow-corrected strain-life curve
- the corrected operating point

The plot title includes the selected analysis temperature.
If legacy fatigue constants are being used, the title notes that explicitly.

### HCF plot

The Stress-Life / HCF plot shows:

- the Basquin S-N curve
- the calculated operating point
- logarithmic x- and y-axes
- a dynamic range so the result remains visible

The plot title includes the selected analysis temperature.
If legacy fatigue constants are being used, the title notes that explicitly.

## Installation

To run from source:

1. Install Python 3.
2. Install the Python dependencies listed in `requirements.txt`.

Example:

```bash
pip install -r requirements.txt
```

## Python dependencies

The project depends on:

- `matplotlib==3.10.9`
- `numpy==2.2.6`
- `PyQt5==5.15.11`

## How to run the Python application

From the repository root:

```bash
python LCF_Life_Calculator.py
```

The script expects the CSV datasets and `turbine_blisk_logo.jpg` to be available alongside the Python file when running from source.

## How to use `LCF_Life_Calculator.exe`

The repository includes a Windows executable version of the same application.

1. Place the executable in the repository folder, or in a folder that also contains any required packaged resources if applicable.
2. Double-click `LCF_Life_Calculator.exe`, or run it from a terminal.
3. Select a material.
4. Select the analysis mode.
5. Select the mean stress correction option.
6. Enter the analysis temperature.
7. Decide whether to allow legacy fatigue fallback.
8. Enter `sigma_max` and `sigma_min`.
9. Click `Calculate Fatigue Life`.

## Repository structure

```text
LCF_Life_Calculator.py              # PyQt5 application source
materials.csv                       # Legacy material registry used for fallback/reference calculations
materials_static.csv                # Temperature-dependent static/thermal properties
materials_fatigue.csv               # Temperature-dependent fatigue/cyclic properties
material_properties.py              # Temperature property resolver
temperature_capability.py           # Temperature capability assessor
validate_materials_static.py        # Static database validation
validate_materials_fatigue.py       # Fatigue database validation
validate_temperature_integration.py # Non-GUI temperature integration validation
README.md                           # Project documentation
requirements.txt                    # Python dependency pins
LCF_Life_Calculator.exe             # Windows executable build of the calculator
turbine_blisk_logo.jpg              # Window icon used by the app
LCF_Calculator_Engineering_Audit.txt # Engineering audit and roadmap notes
REFERENCES/                         # Source reference documents
```

## Short usage workflow

1. Open the app.
2. Pick a material.
3. Choose `Strain-Life / LCF` or `Stress-Life / HCF`.
4. Choose the mean stress correction if needed.
5. Enter the analysis temperature.
6. Decide whether to allow legacy fatigue fallback.
7. Enter the maximum and minimum stress values.
8. Run the calculation.
9. Read the result block and inspect the plot.

## Current limitations

These limitations come directly from the current implementation and database coverage:

- `Goodman`, `Morrow`, and the baseline equations are approximate engineering methods, not certifiable life predictions.
- The temperature-dependent fatigue database currently has only limited condition-specific datasets.
- Material/source/test-condition matching remains essential.
- No extrapolation is performed outside sourced temperature limits.
- Temperature-resolved fatigue coverage is incomplete for many materials.
- Legacy fallback can still produce useful reference estimates, but those results must not be labeled fully temperature-resolved.
- Mean-stress corrections remain approximate engineering methods.
- No variable-amplitude cumulative damage is implemented.
- No temperature-dependent fatigue interpolation beyond explicit resolver permission is implemented.
- No thermo-mechanical fatigue model is implemented.
- No endurance limit is assumed in HCF mode.
- Calculated life is an equation-based engineering estimate, not a certified or experimentally validated life prediction.
- Very large calculated lives can reflect extrapolation of the fitted fatigue relation when the selected source data are sparse.

## Disclaimer

This tool is intended for engineering calculation support and educational use only. Results should be independently verified before being used for any engineering decision, design signoff, safety-critical assessment, or certification-related work.
