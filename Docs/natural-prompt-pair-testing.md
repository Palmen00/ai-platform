# Natural Prompt Pair Testing

## Purpose

This test checks whether normal human questions reach the same intent as precise prompts.

Each case has two prompt variants:

- Perfect prompt: clear, explicit, and close to what a tester would write.
- Human prompt: shorter, messier, and closer to how users usually ask.

The goal is not to hardcode exact answers. The goal is to confirm that natural prompts still:

- find the same relevant document or document family
- avoid false "I do not have access" style replies
- return a useful answer instead of a vague refusal
- preserve follow-up context when the user says "that one" or similar
- work across newly uploaded documents, not only the current FS test files

## Canonical Sheet

The question sheet lives at:

```text
backend/evals/natural_prompt_pair_cases.json
```

## Runner

Run against a live backend:

```powershell
py -3 scripts/tests/run_natural_prompt_pair_suite.py --base-url http://192.168.1.105:8000 --username Admin --password password
```

Optional model override:

```powershell
py -3 scripts/tests/run_natural_prompt_pair_suite.py --base-url http://192.168.1.105:8000 --model gemma4:e2b
```

## How It Scores

The runner builds materialized questions from the currently uploaded and indexed documents.

It then asks both prompt variants and marks a case as passed when:

- the perfect prompt succeeds
- the human prompt succeeds
- the human prompt does not produce a fallback/refusal phrase
- required sources are returned when the case needs grounded document access
- the human prompt's sources overlap with the perfect prompt's sources where source comparison is meaningful
- required metadata such as the latest document name appears when the case explicitly asks for it

Reports are written to:

```text
temp/natural-prompt-pairs/
```
