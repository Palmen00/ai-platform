# Architecture Decision Record: Document Intelligence Backfill

## Decision

Document intelligence backfill should run as an idle maintenance task rather
than blocking normal upload or chat requests.

## Context

Large document libraries can contain hundreds of files. Recomputing document
families, topic profiles, commercial summaries, and similarity metadata during
normal browsing would make the app feel slow.

## Consequences

Positive:

- Users can continue chatting while metadata is improved in the background.
- Operators can force a refresh when they need immediate consistency.
- The app can use low-impact mode on smaller test machines.

Negative:

- Newly uploaded documents may have weaker metadata for a short period.
- Status screens must explain pending and stale document counts clearly.

## Rejected alternative

Running all intelligence enrichment synchronously during upload was rejected
because it made upload latency unpredictable.
