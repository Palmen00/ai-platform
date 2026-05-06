# Payments API Reference

## Authentication

Every request must include an `Authorization: Bearer <token>` header. Tokens
expire after 60 minutes. The API also accepts an `Idempotency-Key` header for
write operations.

## Invoice retry endpoint

Use this endpoint when an invoice payment failed because the upstream processor
timed out:

`POST /v1/invoices/{invoice_id}/retry`

Required JSON body:

```json
{
  "reason": "processor_timeout",
  "requested_by": "support-agent"
}
```

Successful response:

```json
{
  "status": "queued",
  "retry_job_id": "rj_8f21"
}
```

## Rate limits

The default tenant limit is 600 requests per minute. The invoice retry endpoint
has a stricter limit of 30 requests per minute per tenant.

## Error codes

- `400 invalid_reason`: the retry reason is missing or unsupported.
- `401 unauthenticated`: the bearer token is missing or expired.
- `404 invoice_not_found`: the invoice id does not exist.
- `409 retry_already_queued`: a retry job already exists for the invoice.
- `429 rate_limited`: the tenant exceeded the endpoint limit.

## Pagination

List endpoints use cursor pagination. The response field `next_cursor` is empty
when there are no more records.
