# Natural Prompt Scenario Testing

## Purpose

This suite expands the smaller prompt-pair smoke test into a broader set of real user situations.

Each case still compares:

- a perfect prompt that states the intent clearly
- a human prompt that is shorter, messier, or more conversational

The suite is grouped by area so regressions are easier to understand.

## Areas

- Onboarding: what the assistant can do, document usage, auth, and safe mode.
- Discovery: latest upload, inventory, document types, and topic search.
- Summarization: short summaries, business summaries, key points, and follow-up questions.
- Extraction: titles, entities, actions, dates, and risks.
- OCR: scanned or OCR-read documents.
- Comparison: similar documents, related documents, and change-style questions.
- Business Workflows: policies, invoices, agreements, reports, presentations, code, and spreadsheets.
- Follow-up Context: "that one", "it", and follow-up actions or risks.

## Run

```powershell
py -3 scripts/tests/run_natural_prompt_scenario_suite.py --base-url http://192.168.1.105:8000 --username Admin --password password
```

For a smaller sampled run:

```powershell
py -3 scripts/tests/run_natural_prompt_scenario_suite.py --base-url http://192.168.1.105:8000 --max-cases 12
```

The canonical scenario sheet lives at:

```text
backend/evals/natural_prompt_scenario_cases.json
```

Reports are written to:

```text
temp/natural-prompt-scenarios/
```

## Notes

The suite adapts to the documents currently available on the server. Cases that require a missing document type, such as OCR or spreadsheets, are skipped during materialization instead of hard failing.

The score is behavioral, not a hardcoded answer key. A case passes when the human prompt reaches a useful answer comparable to the perfect prompt, avoids fallback/refusal language, and returns expected source behavior where relevant.
