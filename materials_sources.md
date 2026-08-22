# Temperature-Dependent Static Material Property Sources

This file documents the compact `property_source` identifiers used in `materials_static.csv`.
Values are reference engineering data for calculator support, not certified design allowables.

## ASM/MatWeb 2024-T3

- Material: Aluminum 2024-T3
- Condition: 2024-T3
- Source type: ASM/MatWeb material data sheet
- URL: https://asm.matweb.com/search/SpecificMaterial.asp?bassnum=MA2024T3
- Notes: Includes AA typical room-temperature values, listed elevated tensile values, and mean CTE ranges.

## ASM/MatWeb 7075-T6

- Material: Aluminum 7075-T6 / 7075-T651
- Condition: 7075-T6
- Source type: ASM/MatWeb material data sheet
- URL: https://asm.matweb.com/search/SpecificMaterial.asp?bassnum=MA7075T6&lang=en
- Notes: Includes AA typical room-temperature values and mean CTE ranges.

## Haynes 718

- Material: HAYNES 718 / INCONEL 718 family
- Condition: Plate, mill annealed + 1325 F / 8 h, furnace cool to 1150 F / 8 h, air cool
- Source type: Haynes International alloy page
- URL: https://haynesintl.com/en/alloys/alloy-portfolio/high-temperature-alloys/haynes-718/
- Notes: Includes tensile data for the stated plate heat treatment and physical property series.

## Haynes 625

- Material: HAYNES 625 / Nickel 625 family
- Condition: Hot-rolled plate, 1925 F mill annealed
- Source type: Haynes International alloy page
- URL: https://haynesintl.com/en/alloys/alloy-portfolio/high-temperature-alloys/haynes-625/
- Notes: Includes tensile data for hot-rolled mill-annealed plate and physical property series.

## Haynes 230

- Material: HAYNES 230
- Condition: Plate, solution annealed
- Source type: Haynes International alloy page
- URL: https://haynesintl.com/en/alloys/alloy-portfolio/high-temperature-alloys/haynes-230/
- Notes: Includes tensile data for solution-annealed plate and physical property series.

## Haynes R-41

- Material: HAYNES R-41 / Rene 41 family
- Condition: Age hardened 1400 F / 16 h / air cool
- Source type: Haynes International alloy page
- URL: https://haynesintl.com/en/alloys/alloy-portfolio/high-temperature-alloys/haynes-r-41/
- Notes: Includes tensile data for the stated age-hardened condition and limited physical properties.

## TIMET/MatWeb and Metalcor

- Material: Ti-6Al-4V / ASTM Grade 5
- Condition: TIMETAL 6-4 / ASTM Grade 5 sheet/plate, annealed per ASTM B265
- Source type: TIMET data via MatWeb plus Metalcor room-temperature physical data
- MatWeb URL: https://www.matweb.com/search/datasheet_print.aspx?matguid=a1fc12bc5d04434a8e617a745f46624b
- Metalcor URL: https://www.metalcor.de/en/datenblatt/125/
- Notes: Used only for room-temperature strength and basic physical properties for the stated annealed sheet/plate condition.

## MaterialHub SLUB Dresden

- Material: Ti-6Al-4V
- Condition: MaterialHub resonant test dataset
- Source type: MaterialHub published measured dataset
- URL: https://www.materialhub.de/en/materials/slub-dresden-ti-6al-4v
- Notes: Used for E(T) and CTE(T). Stored as a separate condition rather than merged with TIMETAL sheet/plate strength values.

## ATI 316 technical data sheet

- Material: ATI 316 / UNS S31600
- Condition: Annealed flat-rolled ATI 316 elevated-properties dataset
- Source type: ATI technical data sheet
- URL: https://www.atimaterials.com/products/Pages/ati-316.aspx
- Notes: Room-temperature minimum values are on the ATI product page; elevated tensile values are representative data from the ATI 316 technical data sheet.

## PPPL 316 SS property table

- Material: 316 stainless steel
- Condition: Generic 316 SS thermal and structural property table
- Source type: Princeton Plasma Physics Laboratory material property table
- URL: https://aries.pppl.gov/LIB/PROPS/PANOS/ss.html
- Notes: Used for E(T), listed CTE, thermal conductivity, specific heat, density, and Poisson ratio where available. Stored as a separate generic condition.

## ASM/MatWeb 4340 normalized 25 mm round

- Material: AISI 4340
- Condition: Normalized, 25 mm round
- Source type: ASM/MatWeb material data sheet
- URL: https://asm.matweb.com/search/SpecificMaterial.asp?bassnum=M434AC
- Notes: Includes room-temperature normalized strength data and selected mean CTE data. No elevated tensile series was added.
