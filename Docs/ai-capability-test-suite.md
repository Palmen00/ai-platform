# AI Capability Test Suite

This suite is the broad acceptance/regression test for Local AI OS AI behavior.
It is designed to catch practical answer-quality failures that unit tests miss:
weak retrieval, brittle prompts, hallucinated facts, poor uncertainty handling,
bad code output, and unsafe secret leakage.

Latest expanded live run:

- Date: 2026-05-06
- Scope: full `59` case suite against the live AI server
- Result: `4/59`
- Report: `temp/ai-capability-suite/ai-capability-suite-20260506-140425.md`
- Main failure signals: missing required facts, weak list/table formatting,
  missing alternative expected terms, code block shape, source mismatch, and
  uncertainty handling

## Files

- Runner: `scripts/tests/run_ai_capability_suite.py`
- Fixtures: `backend/evals/fixtures/ai_capability/`
- Reports: `temp/ai-capability-suite/`

## Coverage

The suite runs every case twice:

- `perfect_prompt`: clean, explicit, well-scoped user wording
- `human_prompt`: realistic messy wording with typos, abbreviations, Swedish,
  English, incomplete context, or casual phrasing

Current categories:

- `perfect_prompts`: direct, clean requests against API/runbook material
- `human_prompts`: messy user phrasing against the same knowledge
- `coding`: code explanation and runnable Python code generation
- `metrics`: interpreting service metrics, error rates, latency, and CPU
- `statistics`: reasoning about lift, uncertainty, and rollout readiness
- `troubleshooting`: log and runbook based debugging
- `rag_retrieval`: document-scoped retrieval and follow-up questions
- `writing`: customer email, incident report, and action-plan drafting
- `safety_and_uncertainty`: missing information, prompt-leak attempts, and
  grounded refusal behavior

The current suite contains `59` cases. Because each case has both a perfect and
a human prompt, a full run sends `118` chat prompts plus fixture upload/indexing
checks.

## Fixture Documents

The fixture set intentionally looks like realistic company knowledge:

- `developer-runbook.md`: health checks, deploy commands, backup boundaries
- `payments-api.md`: auth, invoice retry endpoint, error codes, rate limits
- `backup_worker.py`: script to explain and use for code-related answers
- `metrics-snapshot.csv`: service request/error/latency/CPU metrics
- `incident-log.log`: Qdrant timeout and model queue incident log lines
- `statistics-study.md`: onboarding experiment with activation lift
- `troubleshooting-notes.md`: saved-chat loading runbook
- `customer-incident-brief.md`: incident content for customer-facing writing
- `security-policy.md`: auth, secret handling, uploads, and audit expectations
- `deployment-manifest.yaml`: backend replica, resources, env, and probes
- `database-migration.sql`: conversation ownership and audit-event schema
- `windows-maintenance.ps1`: Windows log cleanup script
- `support-ticket.md`: realistic customer ticket about indexed documents
- `release-notes-rc4.md`: rc4 highlights, known issues, and update guidance
- `error-playbook.md`: 502 chat, 422 upload, and 429 login troubleshooting
- `sales-kpi.csv`: business KPI data for calculations
- `performance-baseline.json`: target vs latest performance metrics
- `architecture-decision.md`: idle document-intelligence backfill decision

## Running

Local backend:

```powershell
py -3 scripts\tests\run_ai_capability_suite.py `
  --base-url http://127.0.0.1:8000 `
  --username Admin `
  --password password
```

Live server:

```powershell
py -3 scripts\tests\run_ai_capability_suite.py `
  --base-url http://192.168.1.105:8000 `
  --username Admin `
  --password password
```

Useful options:

- `--max-cases 3`: run only the first few cases while iterating
- `--category writing`: run only one category; can be repeated
- `--case-id api_retry_endpoint`: run a specific case; can be repeated
- `--list-cases`: print the available cases without contacting the server
- `--fail-fast`: stop at the first failing case
- `--skip-upload`: require existing processed fixture documents
- `--no-reuse-existing`: always upload fresh fixture documents
- `--cleanup`: delete fixture documents uploaded during this run after reporting
- `--model gemma4:e2b`: force a specific model instead of backend default

Examples:

```powershell
py -3 scripts\tests\run_ai_capability_suite.py --list-cases
```

```powershell
py -3 scripts\tests\run_ai_capability_suite.py `
  --base-url http://192.168.1.105:8000 `
  --username Admin `
  --password password `
  --category metrics `
  --cleanup
```

```powershell
py -3 scripts\tests\run_ai_capability_suite.py `
  --base-url http://192.168.1.105:8000 `
  --username Admin `
  --password password `
  --case-id statistics_missing_p_value `
  --cleanup
```

## Pass / Fail Rules

A case passes only when both prompt variants pass. Validation checks include:

- required answer terms are present
- at least one expected alternative term is present where wording can vary
- required fixture sources are returned for grounded RAG cases
- uncertainty/refusal language is used when information is missing
- forbidden terms are not present
- severe secret-like values are not leaked
- generated Python code parses with `ast.parse` when code generation is tested
- bullet/table shape is present when the task requires structured output

The test intentionally does not require exact full answers. It checks behavior,
grounding, structure, and critical facts so the model can answer naturally.

## Adding New Cases

1. Add or update a fixture in `backend/evals/fixtures/ai_capability/`.
2. Add a `PromptPairCase` in `_build_cases()` inside
   `scripts/tests/run_ai_capability_suite.py`.
3. Include both a perfect prompt and a human prompt.
4. Prefer assertions based on source facts, required structure, and safety
   behavior instead of exact wording.
5. Run with `--max-cases` first, then run the full suite.

Good assertions are stable facts such as endpoint names, incident IDs, exact
commands, known metric labels, and required source names. Avoid asserting long
sentences, stylistic phrasing, or model-specific wording.
