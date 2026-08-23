# Handbook Mining

Local fatigue-data mining utilities for the ASM Metals Handbook / Desk Edition PDF.

## Purpose

This folder is a discovery layer only. It searches the handbook locally, records page-level hits, and prepares candidate records for later human review before anything is copied into the calculator databases.

## Important Assumptions

- Handbook data are not automatically compatible with a calculator material merely because the alloy name matches.
- Material condition, heat treatment, product form, temperature, loading mode, environment, and test conditions matter.
- Source-reported values must be distinguished from values derived from figures or fitted later.
- Printed handbook page number and PDF page number are both retained where possible.
- No database value is replaced automatically.
- Conflicting sources are preserved for engineering review.
- A handbook curve is not equivalent to source-reported fitted fatigue constants.
- Curve digitization and parameter fitting must be separately documented.
- Runouts must not be treated as failures.
- Data used for model calibration should ideally be separated from validation data.
- Walker gamma must not be fitted from one arbitrary fatigue point.
- The lowest predicted fatigue life is not automatically the validated model.
- Design allowables must not be inferred automatically from handbook typical/reference values.

## Inputs

The default PDF path is:

`REFERENCES/metals-handbook-desk-edition-2nd-edition_compress.pdf`

The scripts do not upload the PDF and do not use OCR on the first pass.

## Outputs

Generated files are written to `handbook_mining/output/`:

- `handbook_metadata.json`
- `search_index.csv`
- `candidate_data.csv`
- `fatigue_database_audit.csv`
- `extraction_log.txt`
- `materials/`
- `general_fatigue/`

Context page snippets are written as text files under the material folders so you can review nearby pages without creating huge duplicate PDFs.

## Workflow

1. Build or reuse the page-level index.
2. Review page hits and candidate rows.
3. Inspect context pages for the strongest matches.
4. Compare handbook support against the current databases without modifying them.

## Commands

Run a fresh scan:

```powershell
python handbook_mining\handbook_search.py --rebuild
```

Reuse an existing cache when the PDF has not changed:

```powershell
python handbook_mining\handbook_search.py
```

Review candidates:

```powershell
python handbook_mining\handbook_review.py --material "Ti-6Al-4V"
python handbook_mining\handbook_review.py --category LCF
python handbook_mining\handbook_review.py --keyword "R ratio"
python handbook_mining\handbook_review.py --top 30
```

Review the audit:

```powershell
python handbook_mining\handbook_review.py --audit --material "Inconel 718"
```

## Extraction Policy

- Native PDF text extraction is used first.
- OCR is intentionally deferred.
- Curves are flagged for later digitization rather than being converted into numeric constants during the discovery pass.
- Source-reported values, curve references, and inferred context are kept separate.

## Notes

The output folder is ignored by Git so the local mining cache and extracted page snippets do not get committed accidentally.
