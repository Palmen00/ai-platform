# Customer Incident Brief

## Incident

Incident code: `CUST-INC-9081`

Customer: Northwind Retail

On 2026-05-06 between 08:10 and 08:20 UTC, invoice search was slow for some
users. The document-indexer service retried Qdrant writes and temporarily
increased queue time. No data loss is confirmed in this brief.

## Current status

The queue was drained after retry workers were restarted. Monitoring shows
normal document-indexer throughput again. Engineering is still reviewing why
Qdrant write latency spiked.

## Customer-facing message requirements

- Acknowledge the slow invoice search.
- Say that no data loss is confirmed.
- Explain that queueing returned to normal after retry workers were restarted.
- Avoid promising a final root cause until engineering completes the review.
- Offer to share a follow-up summary when the review is complete.

## Missing information

The brief does not include customer-specific compensation terms, SLA credits, or
a final root cause.
