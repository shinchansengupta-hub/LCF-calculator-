# LCF Life Calculator

LCF Life Calculator is a small PyQt5 desktop application for engineering fatigue screening. It currently provides two analysis modes:

- Strain-Life / LCF
- Stress-Life / HCF

The application loads material constants from `materials.csv`, accepts a maximum and minimum stress, computes the stress amplitude and mean stress, and then evaluates either a strain-life low-cycle fatigue estimate or a standalone Basquin stress-life high-cycle fatigue estimate.

## What problem it solves

The calculator supports quick fatigue screening when you need a compact desktop tool for:

- low-cycle fatigue life from a strain-life relation
- high-cycle fatigue life from a basic stress-life relation
- a simple plot of the selected fatigue relation with the operating point highlighted

It is intended as an engineering estimate tool, not a certified lifing method.

## Analysis modes

### 1. Strain-Life / LCF

This mode uses the currently implemented strain-life workflow:

- Inputs `sigma_max` and `sigma_min`
- Computes stress amplitude:
  - `sigma_a = abs(sigma_max - sigma_min) / 2`
- Computes mean stress:
  - `sigma_m = (sigma_max + sigma_min) / 2`
- Computes elastic strain amplitude:
  - `epsilon_e,a = sigma_a / E`
- Computes plastic strain amplitude using cyclic Ramberg-Osgood:
  - `epsilon_p,a = (sigma_a / K_prime)^(1 / n_prime)`
- Computes total strain amplitude:
  - `epsilon_a = epsilon_e,a + epsilon_p,a`
- Solves the combined Basquin-Coffin-Manson strain-life relation numerically for `Nf`
- Reports both cycles to failure `Nf` and reversals to failure `2Nf`

The implemented strain-life relation is:

- `epsilon_a = (sigma_f_prime / E) * (2*Nf)^b + epsilon_f_prime * (2*Nf)^c`

The LCF life solve uses a monotonic bracketed bisection method rather than a fixed-grid nearest-point search.

### 2. Stress-Life / HCF

This mode uses a standalone Basquin stress-life relation:

- `sigma_a = sigma_f_prime * (2*Nf)^b`
- `Nf = 0.5 * (sigma_a / sigma_f_prime)^(1 / b)`

It uses the same `sigma_max` and `sigma_min` inputs to compute stress amplitude and mean stress, but mean stress is currently calculated only for display and is not corrected.

The HCF mode:

- does not assume an endurance limit
- is intended for elastic-dominated fatigue
- displays an S-N style curve with log-log axes
- highlights the calculated operating point

## Inputs

The GUI currently accepts:

- Material selection
- Analysis mode selection
- Maximum stress, `sigma_max` in MPa
- Minimum stress, `sigma_min` in MPa

Derived quantities used by both modes:

- Stress amplitude, `sigma_a`
- Mean stress, `sigma_m`

## Outputs

### LCF outputs

The Strain-Life / LCF mode displays:

- Stress amplitude
- Mean stress
- Elastic strain amplitude
- Plastic strain amplitude
- Total strain amplitude
- Estimated life in cycles
- Reversals to failure `2Nf`

It also shows a strain-life plot with:

- x-axis: `2Nf (Reversals)`
- y-axis: `Strain Amplitude`

### HCF outputs

The Stress-Life / HCF mode displays:

- Analysis mode label
- Maximum stress
- Minimum stress
- Stress amplitude
- Mean stress
- Estimated life in cycles
- Reversals to failure `2Nf`
- A note that mean stress is calculated but not corrected
- A note that the estimate is a Basquin stress-life estimate intended for elastic-dominated HCF
- A note that the material constants do not currently include calibration-range metadata

The HCF plot is a log-log S-N style plot with:

- x-axis: `2Nf (Reversals)`
- y-axis: `Stress Amplitude (MPa)`

## Material properties loaded from `materials.csv`

The application currently loads the following columns:

- `Material`
- `E_MPa`
- `K_dash`
- `n_dash`
- `sigma_f_dash`
- `b`
- `epsilon_f_dash`
- `c`

The material list currently includes:

- Aluminum 2024-T3
- Inconel 718
- High-Temp Alloy
- Ti-6Al-4V
- Nickel 625
- 316 Stainless Steel
- Alloy Steel 4340
- Aluminum 7075-T6
- Titanium Aluminide (TiAl)
- SiC/SiC Ceramic Matrix Composite
- C/C Composite
- Haynes 230
- Rene 41

Notes:

- `E_MPa` is used numerically as Young's modulus in MPa.
- The same `sigma_f_dash` and `b` values are reused for the Basquin HCF calculation.
- `SiC/SiC Ceramic Matrix Composite` and `C/C Composite` are intentionally not enabled for standalone metallic Basquin HCF estimation.

## GUI functionality

The desktop interface includes:

- Application title
- Material selection drop-down
- Analysis mode drop-down
- Maximum stress input
- Minimum stress input
- Calculate button
- Result label
- Embedded Matplotlib plot

Validation includes:

- numeric checking of both stress inputs
- `sigma_max >= sigma_min`
- `sigma_a > 0`
- HCF-specific checks on material suitability and parameter validity

## Plot functionality

### LCF plot

The Strain-Life / LCF plot shows:

- the combined strain-life curve
- the calculated operating point
- a logarithmic x-axis in reversals to failure

### HCF plot

The Stress-Life / HCF plot shows:

- the Basquin S-N curve
- the calculated operating point
- logarithmic x- and y-axes
- a dynamic range so the result remains visible

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

The script expects `materials.csv` and `turbine_blisk_logo.jpg` to be available alongside the Python file when running from source.

## How to use `LCF_Life_Calculator.exe`

The repository includes a Windows executable version of the same application.

1. Place the executable in the repository folder, or in a folder that also contains any required packaged resources if applicable.
2. Double-click `LCF_Life_Calculator.exe`, or run it from a terminal.
3. Select a material.
4. Select the analysis mode.
5. Enter `sigma_max` and `sigma_min`.
6. Click `Calculate Fatigue Life`.

## Repository structure

```text
LCF_Life_Calculator.py              # PyQt5 application source
materials.csv                       # Material property table used by the app
requirements.txt                    # Python dependency pins
LCF_Life_Calculator.exe             # Windows executable build of the calculator
turbine_blisk_logo.jpg              # Window icon used by the app
LCF_Calculator_Engineering_Audit.txt# Engineering audit and roadmap notes
README.md                           # Project documentation
REFERENCES/                         # Source PDF references
```

## Short usage workflow

1. Open the app.
2. Pick a material.
3. Choose `Strain-Life / LCF` or `Stress-Life / HCF`.
4. Enter the maximum and minimum stress values.
5. Run the calculation.
6. Read the result block and inspect the plot.

## Current limitations

These limitations come directly from the current implementation:

- No mean-stress correction is applied in HCF mode.
- No variable-amplitude cumulative damage is implemented.
- No temperature-dependent fatigue properties are implemented.
- No thermo-mechanical fatigue model is implemented.
- No endurance limit is assumed in HCF mode.
- Material fatigue constants currently lack calibration-range metadata.
- Calculated life is an equation-based engineering estimate, not a certified or experimentally validated life prediction.
- Very large calculated lives can reflect extrapolation of the fitted fatigue relation.
- The tool does not provide load spectra, creep, or TMF capability.
- The tool is limited to the material constants currently stored in `materials.csv`.

## Disclaimer

This tool is intended for engineering calculation support and educational use only. Results should be independently verified before being used for any engineering decision, design signoff, safety-critical assessment, or certification-related work.
