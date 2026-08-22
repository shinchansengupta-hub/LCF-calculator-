# Temperature-Dependent Fatigue and Cyclic Property Sources

This file documents the compact `property_source` identifiers used in
`materials_fatigue.csv`.

The stored values are source-reported fitted fatigue/cyclic constants for
specific material conditions and test programs. They are not certified design
allowables. Do not merge these constants with a different heat treatment,
product form, environment, or temperature without source justification.

## IntechOpen unified creep-fatigue Table 9

- Source title: A Unified Creep-Fatigue Equation with Application to Engineering Design
- Organization/publisher: IntechOpen
- URL: https://www.intechopen.com/chapters/57480
- Material: Inconel 718
- Condition: Source presents an Inconel 718 creep-fatigue coefficient set at 811 K.
- Temperature points: 811 K, stored as 537.85 C
- Constants taken: `epsilon_f_dash`, `c`, `sigma_f_dash`, `b`, `K_dash`, `n_dash`
- Source location: Table 9, "The creep-fatigue-related coefficients for Inconel 718 and GP91 casting steel"
- Notes: The table gives coefficients for strain-life, stress-life, and strain-stress relations intended for a creep-fatigue design example. This condition is not automatically equivalent to the HAYNES 718 plate static dataset.

## Acta Metallurgica Sinica 2014 Inconel 625 weld LCF Table 1

- Source title: Influence of Temperature on Low-Cycle Fatigue Behavior of Inconel 625 Nickel-Based Superalloy Welding Joint
- Authors: Wang Yuanyuan, Chen Lijia, Wang Baosen
- Journal/year: Acta Metallurgica Sinica, 2014
- DOI: 10.11900/0412.1961.2014.00241
- URL: https://www.ams.org.cn/EN/10.11900/0412.1961.2014.00241
- Material: Inconel 625 nickel-based superalloy welding joint
- Condition/product form: Welded joint
- Temperature points: 25 C and 760 C
- Constants taken: `epsilon_f_dash`, `c`, `sigma_f_dash`, `b`, `K_dash`, `n_dash`
- Source location: Table 1, "Strain fatigue parameters of Inconel 625 alloy welding joint at different temperatures"
- Notes: The source reports `epsilon_f_dash` in percent. Values are stored in `materials_fatigue.csv` as dimensionless strain. This welded-joint dataset is not equivalent to HAYNES 625 hot-rolled plate static data.

## Materials 2026 316H LCF Table 5

- Source title: Tensile and Low-Cycle Fatigue Behavior, Fracture Mechanisms, and Life Predictions of 316H Stainless Steel at 600~800 C
- Journal/year: Materials, 2026
- URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC13027990/
- Material: 316H stainless steel
- Condition/product form: Forged bar, solution treated at 1050 +/- 5 C for 40 min and water quenched, per the paper's methods
- Temperature points: 600 C, 650 C, and 800 C
- Constants taken: `sigma_f_dash`, `b`, `epsilon_f_dash`, `c`, `K_dash`, `n_dash`
- Source location: Table 5, "Low-cycle fatigue fitting parameters of 316H stainless steel at 600-800 C"
- Notes: This is a 316H high-temperature LCF dataset and should not be silently merged with ATI 316 annealed ASTM A240 plate/sheet static data.
