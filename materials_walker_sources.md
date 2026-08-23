# Walker Mean-Stress Gamma Sources

This file documents Walker gamma values used by `materials_walker.csv`.

## Equation Convention

The calculator uses one Walker convention:

`sigma_eq = sigma_max^(1 - gamma) * sigma_a^gamma`

where:

- `sigma_eq` is the Walker equivalent stress used with Basquin.
- `sigma_max` is maximum cycle stress.
- `sigma_a` is stress amplitude.
- `gamma` is the Walker mean-stress sensitivity exponent.
- `R = sigma_min / sigma_max`.

At `R = -1`, `sigma_max = sigma_a`, so `sigma_eq = sigma_a` and Walker reduces to the fully reversed Basquin case.

For strain-life, the same convention is used as an equivalent-strain amplitude:

`epsilon_a,eq = epsilon_a * (sigma_max / sigma_a)^(1 - gamma)`

and life is solved from:

`epsilon_a,eq = (sigma_f_dash / E) * (2Nf)^b + epsilon_f_dash * (2Nf)^c`

At `R = -1`, this reduces to the uncorrected combined Basquin-Coffin-Manson relation at the solved life.

Note: an earlier elastic-term-only strain-life formulation was rejected because it did not recover the existing total strain-life solution at `R = -1` when plastic strain was present. The equivalent-total-strain form above is the intentionally retained Walker LCF model.

For `gamma = 0.5`, the stress-life Walker parameter becomes:

`sigma_eq = sqrt(sigma_max * sigma_a)`

This is the stress-life/SWT elastic-equivalent relationship. The implemented strain-life Walker form is an equivalent-strain mean-stress correction and should not be interpreted as a full SWT implementation.

## Sources

### Dowling, Calhoun, and Arcari, 2009

- Title: Mean stress effects in stress-life fatigue and the Walker equation
- Authors: N. E. Dowling, C. A. Calhoun, A. Arcari
- Journal: Fatigue & Fracture of Engineering Materials & Structures, 32, 163-179
- DOI: 10.1111/j.1460-2695.2008.01322.x
- Use here: Supports the Walker stress-life equation, the fitted gamma concept, and the relationship between gamma and mean-stress sensitivity.
- Limitation: The project does not currently include material-specific fitted gamma values from this paper.

### Dowling, 2009

- Title: Mean stress effects in strain-life fatigue
- Author: N. E. Dowling
- Journal: Fatigue & Fracture of Engineering Materials & Structures, 32, 1004-1019
- DOI: 10.1111/j.1460-2695.2009.01404.x
- Use here: Supports incorporating Walker mean-stress behavior into strain-life calculations and notes that `gamma = 0.5` may be applied as an estimate for precipitation-hardened 2000/7000-series aluminum alloys when non-zero mean-stress data are unavailable.
- Limitation: Estimated gamma is not a calibrated material property.

## Current Coverage

No calibrated/fitted Walker gamma values are currently stored.

Estimated `gamma = 0.5` is stored only for:

- Aluminum 2024-T3 at 24 C
- Aluminum 7075-T6 at 24 C

These estimated rows require explicit user opt-in in the GUI. They are not used silently and are not labeled calibrated.
