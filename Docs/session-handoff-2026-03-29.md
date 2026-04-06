# Session Handoff 2026-03-29

This file is a checkpoint so we can resume quickly next session without having to reconstruct what happened.

## What We Finished

- Integrated selective `OCRmyPDF` into the main backend OCR path for weak/scanned PDFs.
- Added OCR engine visibility in Knowledge so documents can show whether `Tesseract` or `OCRmyPDF` was used.
- Improved the Knowledge document list so long filenames truncate correctly and behave better across smaller screens.
- Continued the prototype track for external tools instead of guessing.

## Prototype Results So Far

### Kept / Strong Candidates

- `OCRmyPDF`
  - strongest OCR candidate so far
  - already integrated selectively in the main app
- `GLiNER`
  - still the strongest enrichment/entity candidate
  - useful for broader company/project/entity signals

### Prototype Only For Now

- `Unstructured`
  - useful on some PDFs
  - not strong enough as a full replacement path
- `EasyOCR`
  - works locally
  - not clearly better than the current OCR path
- `PaddleOCR`
  - install worked
  - runtime/inference was not stable enough in our environment
- `Docling`
  - promising on clean PDFs like architecture/roadmap/current-features
  - too heavy and too unstable on larger manuals and OCR-heavy PDFs in the current Windows dev environment
  - not ready for runtime adoption

## Files Added In The Latest Round

- [backend/evals/docling_structure_cases.json](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/evals/docling_structure_cases.json)
- [scripts/eval/run_docling_compare_eval.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/scripts/eval/run_docling_compare_eval.py)
- [scripts/eval/docling-compare.ps1](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/scripts/eval/docling-compare.ps1)

## Docs Updated In The Latest Round

- [scripts/README.md](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/scripts/README.md)
- [Docs/installation-plan.md](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/Docs/installation-plan.md)
- [Docs/current-features.md](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/Docs/current-features.md)
- [Docs/roadmap.md](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/Docs/roadmap.md)

## Important Notes

- This workspace copy is currently not a Git repository, so there is no local commit checkpoint from this session.
- The work is still saved on disk in the project files.
- `Docling` installation introduced a local dependency warning around `typer`, so if we see odd CLI/import behavior later, that should be one of the first things we check.
- `py -3 -m compileall backend` passed after the latest changes.
- `npm run lint` passed after the latest frontend/docs-related changes.

## Best Next Step

Continue the external-tool evaluation track with the same discipline:

1. Test `Marker` or `Surya` next.
2. Benchmark them against real uploaded documents, not only ideal cases.
3. Keep only tools that clearly beat the current stack on quality, stability, or operational fit.

## Suggested Restart Point For Tomorrow

If we pick this up tomorrow, start with:

- confirm the app still runs cleanly after today’s prototype installs
- test `Marker` next, or `Surya` if OCR/layout is the priority
- only consider integration after a clean benchmark result
