# LCF Life Calculator

LCF Life Calculator is a small PyQt5 desktop application for engineering fatigue screening.

It currently supports two analysis modes:

- Strain-Life / LCF
- Stress-Life / HCF

The application now supports temperature-aware property lookup from:

- `materials_static.csv`
- `materials_fatigue.csv`
- `materials_walker.csv`

It also keeps the legacy room/reference material table in `materials.csv` for fallback calculations when explicitly enabled.

## What problem it solves

The calculator provides a compact desktop tool for approximate fatigue screening when you need:

- low-cycle fatigue life from a strain-life relation
- high-cycle fatigue life from a basic stress-life relation
- temperature-aware property resolution when source data are available
- a simple plot of the selected fatigue relation with the operating point highlighted

It is intended as an engineering estimate tool, not a certified lifing method.

## GUI workflow and stress-source assumptions

The primary intended workflow is ANSYS/FEA local-result entry. The GUI is organized into three tabs:

- `Input`
- `Results`
- `Graphs`

The `Input` tab contains setup controls and signed cycle inputs. The `Results` tab contains only a read-only diagnostic/result report. The `Graphs` tab owns the embedded Matplotlib figure and toolbar; plots are no longer opened in a separate OS-level plot window.

The stress source selector has three paths:

- `Local stress from linear-elastic FEA`
- `Local stress/strain from elastic-plastic FEA`
- `Nominal analytical stress`

The default is `Local stress from linear-elastic FEA`.

Permanent input assumptions:

- Mean-stress models require signed stress-cycle information.
- `sigma_max` and `sigma_min` must refer to the same fatigue-critical hotspot and the same physical stress direction/component.
- Equivalent/von Mises stress must not be used as `sigma_max`/`sigma_min` for Goodman or Walker mean-stress correction because tensile/compressive sign and `R` information are lost.
- This is not a global ban on von Mises for all future fatigue workflows; the restriction applies to signed uniaxial mean-stress models.
- Local FEA stress that already resolves geometry concentration must not be multiplied by `K_t` again.
- Nominal analytical stress is the future path where `K_t`/`K_f` notch correction belongs.
- Linear-elastic local FEA and elastic-plastic local FEA are distinct input sources.
- Elastic-plastic FEA that already resolves local plasticity should bypass future Neuber correction.
- Hotspot stresses must be physically meaningful and mesh-converged; mathematical singularities are not valid fatigue inputs.
- Model-specific restrictions must remain method-specific.
- Walker positive-`sigma_max` restrictions must not be automatically imposed on Goodman, Morrow, or None.
- The approved nominal-stress notch method in HCF applies `K_f` to alternating stress only.
- Mean stress remains nominal by default in the HCF nominal-notch path.
- `K_t * sigma_m` is not the default methodology.
- `K_f` must not automatically be applied to both `sigma_max` and `sigma_min`.
- Reconstructed effective extrema and `R` in the nominal-notch path are computational pseudo-cycle quantities, not physical notch-root extrema.
- Direct `K_f` is preferred when defensibly known.
- `K_t + q` provides an estimated `K_f`; the conservative `K_t`-as-`K_f` path is explicit `q = 1` screening only.
- Walker + nominal-notch remains disabled until a defensible notch-adjusted `sigma_max` convention is established.
- This nominal-notch implementation is HCF only; LCF notch plasticity remains separate.
- FEA-local stress paths bypass notch factors entirely.

The nominal-stress notch section currently exposes inactive placeholders for `K_t`, `q`, and `K_f`. The calculator does not currently apply `K_t`, calculate `K_f`, implement Neuber/Glinka, import FEA data automatically, or perform multiaxial/critical-plane fatigue.

## Analysis temperature

The GUI includes:

- `Analysis Temperature (°C)`
- `Compare Applicable Models` action

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

### `materials_walker.csv`

This table stores Walker mean-stress sensitivity parameters.

Current Walker coverage is intentionally limited:

- no calibrated/fitted Walker gamma values are currently stored
- estimated `gamma = 0.5` is available only for Aluminum 2024-T3 and Aluminum 7075-T6 at 24 C
- estimated gamma values require explicit user opt-in
- Walker gamma is not extrapolated to other temperatures

Walker source notes are documented in `materials_walker_sources.md`.

## Capability classification

Before a temperature-aware calculation is allowed, the application calls the capability resolver in `temperature_capability.py`.

The capability result is one of:

- `FULLY TEMPERATURE RESOLVED`
- `PARTIALLY TEMPERATURE INFORMED`
- `TEMPERATURE DATA UNAVAILABLE`

When all required properties resolve but the material conditions are only partially compatible, the calculator keeps the partial-match warning visible and uses a ready-with-warning calculation status rather than collapsing to temperature unavailable.

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

Correction-method availability is also conservative:

- correction methods are exposed only when their required properties, temperature bounds, condition rules, and parameter availability are satisfied, or when the user has explicitly enabled an allowed fallback/estimated-parameter path
- disabled means unavailable for the current material, temperature, and option set; it does not mean the equation is unsupported globally
- there is no silent fallback
- there is no silent estimated gamma
- there is no silent `S_u` estimation
- there is no extrapolation

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
- Basquin and strain-life equations use reversals `2Nf` internally; reported `Nf` is cycles, and the calculator does not silently mix cycle and reversal coefficients

The LCF mode uses the uncorrected strain-life relation:

- `epsilon_a = (sigma_f_prime / E) * (2*Nf)^b + epsilon_f_prime * (2*Nf)^c`

LCF mode also offers mean-stress correction:

- `None`
- `Morrow`
- `Walker`
- `SWT`
- `SWT`

LCF mode also offers a separate local elastic-plastic correction path:

- `None`
- `Neuber`

This Neuber path is intentionally limited to:

- `Local stress from linear-elastic FEA`
- `Nominal analytical stress`
- `LCF / None`

It uses the amplitude form of scalar cyclic Neuber with cyclic Ramberg-Osgood constants and does not reconstruct local mean or maximum stress. Because of that, `Morrow`, `Walker`, and `SWT` remain unavailable when LCF Neuber is active.

Neuber is an approximate engineering correction, not a direct local stress solution. The cyclic constants `K_prime` and `n_prime` are required. Linear-elastic FEA local stress is used directly as the pseudo-elastic reference; elastic-plastic FEA bypasses Neuber because it already resolves local plasticity.

When `Neuber` is selected for nominal analytical stress:

- `Original Neuber: K_t`
- `Fatigue-modified Neuber: direct K_f`
- `Fatigue-modified Neuber: K_t + q`

When `Neuber` is selected for local elastic FEA:

- ANSYS local elastic stress is used directly as the pseudo-elastic reference
- `K_t` and `K_f` are not reapplied

When `Morrow` is selected:

- `epsilon_a = ((sigma_f_prime - sigma_m) / E) * (2*Nf)^b + epsilon_f_prime * (2*Nf)^c`

The current implementation:

- computes `sigma_m` from `sigma_max` and `sigma_min`
- applies Morrow only to the elastic fatigue term
- conservatively caps compressive-mean-stress life benefit at the uncorrected life
- uses a monotonic bracketed bisection solve for `Nf`

When `Walker` is selected, the implemented strain-life form uses:

- `epsilon_a,eq = epsilon_a * (sigma_max / sigma_a)^(1 - gamma)`
- `epsilon_a,eq = (sigma_f_prime / E) * (2*Nf)^b + epsilon_f_prime * (2*Nf)^c`

This preserves the existing combined Basquin-Coffin-Manson equation and solves it using the Walker-equivalent strain amplitude. At `R = -1`, where `sigma_max = sigma_a`, the Walker factor is 1 and the calculation reduces to the uncorrected strain-life solution.

When `SWT` is selected, the implemented strain-life form uses:

- `P_SWT = sigma_max * epsilon_a`
- `P_SWT = (sigma_f_prime^2 / E) * (2*Nf)^(2*b) + sigma_f_prime * epsilon_f_prime * (2*Nf)^(b+c)`

Here `epsilon_a` is the total strain amplitude from the existing cyclic Ramberg-Osgood calculation:

- `epsilon_a = sigma_a / E + (sigma_a / K_prime)^(1 / n_prime)`

This is an LCF/strain-life mean-stress method. It is not an elastic-only approximation. The calculation solves for positive `Nf` with the existing bracketed root method.

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
- offers `Mean Stress Correction: None`, `Goodman`, and `Walker`

HCF Goodman is conservative and source-driven:

- `sigma_a_eq = sigma_a / (1 - sigma_m / S_u)`

The application blocks Goodman if a valid `S_u_MPa` value is not available for the selected material/condition.

HCF Walker uses:

- `sigma_eq = sigma_max^(1 - gamma) * sigma_a^gamma`
- `sigma_eq = sigma_f_prime * (2*Nf)^b`

At `R = -1`, `sigma_max = sigma_a`, so `sigma_eq = sigma_a` and the result reduces to the uncorrected Basquin calculation.

For `gamma = 0.5`, `sigma_eq = sqrt(sigma_max * sigma_a)`, which is the elastic stress-life relationship associated with the Smith-Watson-Topper parameter. The calculator does not implement full SWT.

Walker requires:

- positive `sigma_max`
- positive `sigma_a`
- finite `R = sigma_min / sigma_max`, with `R < 1`
- finite `0 < gamma <= 1`

Fully compressive cycles with `sigma_max <= 0` are blocked because the conventional fractional-power Walker form is not directly valid for that domain.

## Engineering Model Assumptions - Walker

Walker is treated here as a condition- and temperature-specific empirical mean-stress model.

The calculator uses one HCF convention:

- `sigma_eq = sigma_max^(1 - gamma) * sigma_a^gamma`

The calculator uses one LCF equivalent-total-strain convention:

- `epsilon_a,eq = epsilon_a * (sigma_max / sigma_a)^(1 - gamma)`

The LCF equivalent-total-strain form is intentional. An earlier elastic-term-only formulation was rejected because it did not recover the existing total strain-life solution at `R = -1` when plastic strain was present. That `R = -1` recovery remains a permanent regression requirement for both Walker HCF and Walker LCF.

For `gamma = 0.5`, the HCF form becomes the elastic SWT-equivalent relationship:

- `sigma_eq = sqrt(sigma_max * sigma_a)`

Full SWT is not implemented.

Walker gamma handling rules:

- no calibrated/fitted Walker gamma values currently exist in this project database
- `gamma = 0.5` entries for Aluminum 2024-T3 and Aluminum 7075-T6 at 24 C are estimated only
- estimated gamma values require explicit user opt-in
- Walker gamma is treated as condition-specific and temperature-specific
- no gamma extrapolation is performed

Current domain restrictions:

- `sigma_max > 0`
- `sigma_a > 0`
- `R < 1`
- `0 < gamma <= 1`

Fully compressive Walker cycles are intentionally unsupported.

Existing static/fatigue condition compatibility rules still apply.

## Engineering Model Assumptions - SWT

Smith-Watson-Topper is treated here as an LCF/strain-life mean-stress method.

The calculator uses one SWT convention:

- `P_SWT = sigma_max * epsilon_a`
- `P_SWT = (sigma_f_prime^2 / E) * (2*Nf)^(2*b) + sigma_f_prime * epsilon_f_prime * (2*Nf)^(b+c)`

Here `epsilon_a` means total strain amplitude from the cyclic Ramberg-Osgood relation already used by the LCF calculator.

Permanent SWT assumptions:

- `sigma_max > 0` is required for conventional SWT
- `sigma_max > 0` is SWT-specific and must not automatically be imposed on Goodman, Morrow, Walker, or None
- fully compressive cycles are unsupported
- SWT depends on the validity of the strain-life and cyclic constants at the selected material condition and temperature
- no extrapolation of material properties
- legacy fallback must remain explicitly identified when used
- Walker `gamma = 0.5` has an elastic SWT-equivalent relationship, but that is not full SWT
- SWT is not automatically preferred over Morrow, Walker, or Goodman
- model selection should ultimately be based on experimental validation, not on whichever prediction is shortest

## Inputs

The GUI accepts:

- Stress source selection
- Material selection
- Analysis mode selection
- Mean stress correction selection
- Analysis Temperature (°C)
- Maximum stress, `sigma_max` in MPa
- Minimum stress, `sigma_min` in MPa
- reserved local total strain amplitude input for future elastic-plastic FEA integration
- inactive nominal-stress notch placeholders for `K_t`, `q`, and `K_f`
- Legacy fatigue fallback checkbox
- Estimated Walker gamma checkbox

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

When `Walker` is selected, the result block also shows:

- stress ratio `R`
- Walker gamma
- Walker gamma basis and source
- Walker equivalent strain amplitude
- uncorrected life and reversals
- Walker-corrected life and reversals
- explicit `ESTIMATED WALKER PARAMETER` labeling when estimated gamma is used

When `SWT` is selected, the result block also shows:

- total strain amplitude
- SWT parameter `P_SWT`
- uncorrected life and reversals
- SWT-corrected life and reversals
- explicit `Smith-Watson-Topper strain-life estimate` labeling

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

When `Walker` is selected, the result block also shows:

- stress ratio `R`
- Walker gamma
- Walker gamma basis and source
- Walker equivalent stress
- uncorrected life and reversals
- Walker-corrected life and reversals
- explicit `ESTIMATED WALKER PARAMETER` labeling when estimated gamma is used

## Material properties loaded from `materials.csv`

The legacy table still provides the current calculator with:

- material registry entries
- room/reference fatigue constants
- optional `S_u_MPa` and `S_y_MPa` values where available
- legacy material condition metadata

Walker gamma values are not stored in `materials.csv`; they are loaded from `materials_walker.csv`.

## GUI functionality

The desktop interface includes:

- application title
- `Input`, `Results`, and `Graphs` tabs
- stress source drop-down
- material selection drop-down
- analysis mode drop-down
- mean stress correction drop-down
- local elastic-plastic correction drop-down for LCF
- analysis temperature input
- legacy fatigue fallback checkbox
- estimated Walker gamma checkbox
- maximum stress input
- minimum stress input
- compact model-specific guidance/status box
- calculate button
- compare applicable models button
- scrollable read-only result text panel in the `Results` tab
- embedded Matplotlib plot area in the `Graphs` tab

Validation includes:

- numeric checking of stress inputs
- numeric checking of analysis temperature
- `sigma_max >= sigma_min`
- `sigma_a > 0`
- mode-specific material restrictions
- capability-based property availability checks

## Plot functionality

All plots are embedded in the `Graphs` tab. A blocked calculation clears stale graph content and displays `No valid plot for the current calculation.`

### LCF plot

The Strain-Life / LCF plot shows:

- the strain-life curve
- the calculated operating point
- a logarithmic x-axis in reversals to failure

When Morrow is selected, the plot shows:

- the uncorrected strain-life curve
- the Morrow-corrected strain-life curve
- the corrected operating point

When Walker is selected, the plot shows:

- the uncorrected strain-life curve
- the Walker-corrected strain-life curve
- the Walker-corrected operating point

When SWT is selected, the plot shows:

- the standard strain-life curve for context
- the uncorrected operating point
- the SWT-corrected operating point
- an annotation for `P_SWT`

The SWT plot does not draw a separate synthetic SWT curve. It keeps the standard strain-life curve and marks the SWT-predicted operating point to avoid implying a different fatigue law than the one actually solved.

The plot title includes the selected analysis temperature.
If legacy fatigue constants are being used, the title notes that explicitly.

### HCF plot

The Stress-Life / HCF plot shows:

- the Basquin S-N curve
- the calculated operating point
- logarithmic x- and y-axes
- a dynamic range so the result remains visible

When Goodman or Walker is selected, the plot also marks the corrected operating point. Walker plots use the Walker equivalent stress for the corrected point.

The plot title includes the selected analysis temperature.
If legacy fatigue constants are being used, the title notes that explicitly.

## Comparison Mode and Validation

The application also provides a `Compare Applicable Models` action.

This is an additional analysis pass, not a replacement for the normal
single-method workflow. It calculates every applicable model for the current
loading case and shows the predictions side-by-side.

Comparison covers the same model families already implemented in the
calculator:

- LCF comparison:
  - `None`
  - `Morrow`
  - `Walker`
  - `SWT`
- HCF comparison:
  - `None`
  - `Goodman`
  - `Walker`

When LCF Neuber is active, comparison is intentionally limited to `None` because scalar Neuber does not produce defensible local mean or maximum stress for the mean-stress-sensitive LCF models.

Comparison assumptions:

- the lowest predicted life is descriptive only
- the lowest predicted life is not automatically recommended
- model conservatism and model validity are different concepts
- model selection should be based on representative experimental data for the same material condition, temperature, loading regime, and environment
- runouts are censored observations and must not be treated blindly as failures at the runout cycle count
- calibration data and validation data should ideally be separate, especially for Walker gamma fitting
- design allowables, scatter treatment, and safety factors belong to a later reliability/design phase

The comparison result object keeps:

- model name
- analysis mode
- predicted life
- reversals
- availability classification
- temperature capability
- property basis
- condition compatibility
- legacy fallback usage
- estimated-parameter usage
- warnings and assumptions
- status

Comparison availability labels:

- `AVAILABLE_FULL`
- `AVAILABLE_PARTIAL`
- `AVAILABLE_LEGACY`
- `AVAILABLE_ESTIMATED`
- `UNAVAILABLE`

### Experimental fatigue data template

The repository includes `experimental_fatigue_data.csv` as a blank schema
template for future test data. It does not contain invented engineering
observations.

Suggested fields:

- `dataset_id`
- `Material`
- `material_condition`
- `Temperature_C`
- `analysis_mode`
- `sigma_max_MPa`
- `sigma_min_MPa`
- `strain_amplitude`
- `experimental_life_cycles`
- `runout`
- `test_standard`
- `environment`
- `frequency_Hz`
- `strain_rate`
- `source`
- `notes`

### Validation metrics

The reusable `fatigue_validation.py` module provides logarithmic validation
metrics:

- `life_ratio = N_pred / N_exp`
- `log_error = log10(N_pred) - log10(N_exp)`
- `factor_error = max(N_pred / N_exp, N_exp / N_pred)`

Aggregate metrics:

- `mean_log_error`
- `mean_absolute_log_error`
- `RMSE_log10`
- `percentage_within_factor_2`
- `percentage_within_factor_3`

These metrics are intended to support future experimental validation, not
automatic model ranking.

### Walker calibration readiness

`fatigue_validation.py` also reserves structure for future Walker gamma
calibration from suitable multi-R experimental data. Walker gamma must not be
fitted from a single arbitrary test point.

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
9. Click `Calculate Fatigue Life`, or use `Compare Applicable Models` to view all applicable model predictions.

## Repository structure

```text
LCF_Life_Calculator.py              # PyQt5 application source
materials.csv                       # Legacy material registry used for fallback/reference calculations
materials_static.csv                # Temperature-dependent static/thermal properties
materials_fatigue.csv               # Temperature-dependent fatigue/cyclic properties
materials_walker.csv                # Walker gamma parameters
materials_walker_sources.md         # Walker source and convention notes
material_properties.py              # Temperature property resolver
temperature_capability.py           # Temperature capability assessor
fatigue_validation.py               # Validation metrics and comparison result structures
test_walker.py                      # Walker correction regression tests
test_swt.py                         # SWT correction regression tests
test_model_comparison.py            # Model comparison regression tests
test_fatigue_validation.py          # Validation metrics regression tests
validate_materials_static.py        # Static database validation
validate_materials_fatigue.py       # Fatigue database validation
validate_temperature_integration.py # Non-GUI temperature integration validation
experimental_fatigue_data.csv       # Blank template for future experimental validation data
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
7. If using Walker, decide whether to allow estimated Walker gamma.
8. Enter the maximum and minimum stress values.
9. Run the calculation.
10. Optionally use `Compare Applicable Models` to view all applicable model predictions side-by-side.
11. Read the result block and inspect the embedded plot in the `Graphs` tab.

## Current limitations

These limitations come directly from the current implementation and database coverage:

- `Goodman`, `Morrow`, `Walker`, `SWT`, and the baseline equations are approximate engineering methods, not certifiable life predictions.
- Comparison mode reports the lowest mathematical prediction only as descriptive information; it does not automatically select a preferred model.
- Model validity must be established against representative experimental data, not by picking the shortest life.
- Walker performance depends strongly on a fitted material gamma and applicable mean-stress fatigue data.
- The current Walker database has no calibrated/fitted gamma values.
- Estimated Walker gamma is available only for Aluminum 2024-T3 and Aluminum 7075-T6 at 24 C and must be explicitly enabled.
- Walker gamma is not extrapolated outside sourced temperatures.
- Fully compressive Walker cycles with `sigma_max <= 0` are not supported.
- Conventional SWT requires positive `sigma_max`; fully compressive cycles are not supported.
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
- Runouts are not treated as ordinary failures in the validation helpers.
- Calculated life is an equation-based engineering estimate, not a certified or experimentally validated life prediction.
- Very large calculated lives can reflect extrapolation of the fitted fatigue relation when the selected source data are sparse.

## Disclaimer

This tool is intended for engineering calculation support and educational use only. Results should be independently verified before being used for any engineering decision, design signoff, safety-critical assessment, or certification-related work.
