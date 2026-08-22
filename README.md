# LCF Life Calculator

LCF Life Calculator is a small PyQt5 desktop application for estimating low-cycle fatigue life from a selected material and a single user-entered maximum bending stress. It loads material constants from `materials.csv`, computes a strain amplitude from the stress input, and finds an approximate fatigue life by matching that strain to a strain-life curve.

## What problem it solves

The application helps with a common engineering screening task: estimating low-cycle fatigue life for a known material under a single stress level. It is useful when you need a quick, interactive check of strain-life behavior without building a full fatigue analysis workflow.

## Methodology implemented

The source code implements a strain-life approach based on:

- Elastic strain term from Hooke's law:
  - `epsilon_e = sigma / E`
- Plastic strain term using a power-law fit:
  - `epsilon_p = (sigma / K')^(1 / n')`
- Total strain amplitude:
  - `epsilon_a = epsilon_e + epsilon_p`
- Strain-life curve evaluation using the Coffin-Manson-Basquin form:
  - `epsilon_a = (sigma_f' / E) * (2Nf)^b + epsilon_f' * (2Nf)^c`

The application does not solve this equation analytically. Instead, it generates a dense logarithmic range of life values and selects the closest match between the computed strain amplitude and the strain-life curve.

## Inputs

The GUI accepts:

- Material selection from the loaded material list
- Maximum bending stress in MPa

The selected material supplies these constants from `materials.csv`:

- `E(KPa)`
- `K_dash`
- `n_dash`
- `sigma_f_dash`
- `b`
- `epsilon_f_dash`
- `c`

## Outputs

The application displays:

- Estimated life in cycles
- A strain-life plot
- A highlighted result point on the plot

## Material properties loaded from `materials.csv`

The application loads the following materials:

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

Each row provides the material constants used by the calculator. The code reads the CSV directly and uses the values as supplied.

## GUI functionality

The desktop interface includes:

- A title label
- A material drop-down list
- A stress input field
- A calculate button
- A result label
- An embedded Matplotlib plot

Validation is limited to checking that the stress entry can be converted to a numeric value. If not, the app shows a warning dialog.

## Plot functionality

The embedded plot shows:

- The material strain-life curve
- A red marker for the calculated result
- A logarithmic x-axis labeled `2Nf (Reversals)`
- A y-axis labeled `Strain Amplitude`
- Grid lines and a legend

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
4. Enter a numeric maximum bending stress.
5. Click `Calculate Fatigue Life`.

## Repository structure

```text
LCF_Life_Calculator.py      # PyQt5 application source
materials.csv               # Material property table used by the app
requirements.txt            # Python dependency pins
LCF_Life_Calculator.exe     # Windows executable build of the calculator
turbine_blisk_logo.jpg      # Window icon used by the app
README.md                   # Project documentation
```

## Short usage workflow

1. Open the app.
2. Pick a material.
3. Enter the maximum bending stress.
4. Run the calculation.
5. Read the estimated life and inspect the strain-life plot.

## Current limitations

These limitations come directly from the current implementation:

- The calculator uses one stress input only; it does not accept a load history, spectrum loading, or cycle-by-cycle damage accumulation.
- There is no mean-stress correction.
- There is no notch or geometry factor input.
- The result is found by a brute-force nearest-match search over a fixed life range from `10^2` to `10^6` reversals.
- The app does not perform detailed unit checking or conversion.
- The code assumes the selected material parameters are valid and complete in `materials.csv`.
- Error handling is minimal beyond invalid numeric stress input and a basic material-loading `try/except`.
- The method is a screening-level strain-life estimate, not a substitute for a full fatigue assessment.

## Disclaimer

This tool is intended for engineering calculation support and educational use only. Results should be independently verified before being used for any engineering decision, design signoff, safety-critical assessment, or certification-related work.
