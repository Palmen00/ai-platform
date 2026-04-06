# OCR Decision

This document captures the current OCR decision so we stop re-litigating the same question every session.

## Current Decision

- Primary OCR path: `OCRmyPDF`
- Fallback OCR path: `Tesseract`
- Promising isolated prototype: `Surya`
- Rejected for now: `Marker`, `PaddleOCR`
- Not strong enough to replace the current path: `EasyOCR`

## Why This Is The Current Choice

We are optimizing for the product, not for theoretical benchmark wins.

The chosen OCR path needs to be:

- good enough on real scanned PDFs
- stable on local Windows development and later Ubuntu deployment
- practical to install and support
- predictable enough that other people can run this stack without fighting the environment

`OCRmyPDF` currently gives us the best balance of OCR quality, stability, and integration cost.

## Tool Findings

### OCRmyPDF

- Best overall fit for scanned and weak PDFs in the current product
- Worked reliably in Docker
- Performed well on the broader mixed OCR suite
- Fits well as a selective preprocessing step instead of a total OCR-system replacement

### Tesseract

- Still valuable as the built-in fallback
- Easy to reason about
- Good enough to keep as the safety net when `OCRmyPDF` is unavailable or not the right path

### EasyOCR

- Usable and worth benchmarking
- Did not produce a clear enough quality win to justify replacing the current path
- Slower than the current OCR path in our tests

### PaddleOCR

- Interesting on paper
- Not practical in our environment yet because inference failed in both local Windows and first Docker testing

### Marker

- Not a fit for the local baseline
- Too heavy
- Too much dependency churn
- Timed out on simple runs
- Left background processes behind

### Surya

- More promising than `Marker` on raw OCR quality
- Large first-run model downloads
- Dependency conflicts with parts of the current prototype stack
- Worth keeping as an isolated prototype, not as part of the normal local baseline

## Product Rule Going Forward

- OCR is now considered settled enough for the main product path.
- New OCR experiments should stay in prototype lanes unless they show a clear and repeatable win over `OCRmyPDF`.
- The next main exploration track is `document parsing / structure`, not another round of general OCR-engine swapping.

## Next Related Work

- keep `OCRmyPDF` as the primary OCR engine
- keep `Tesseract` as fallback
- benchmark `Surya` only in an isolated environment if we revisit OCR later
- focus the next evaluation round on document parsing and structure tools such as `Unstructured`
