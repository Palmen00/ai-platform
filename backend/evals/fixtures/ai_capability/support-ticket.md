# Support Ticket SUP-4421

## Customer

Customer: Fabrikam Manufacturing

## Problem

The customer reports that uploaded CAD invoice attachments are visible in the
Knowledge list but do not appear in chat answers. The issue started after a
manual backend restart at 14:30 UTC.

## Observations

- Authentication works.
- New chat messages are saved.
- Two documents have `processing_status=processed` and `indexing_status=pending`.
- Qdrant health is green.
- The customer did not run `verify.sh` after the restart.

## Requested outcome

Support wants a concise technical reply explaining what to check first and how
to avoid deleting customer data.
