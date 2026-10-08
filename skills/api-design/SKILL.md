---
name: api-design
description: Design and review REST and GraphQL APIs, including resource naming, status codes, pagination, versioning, error bodies, and OpenAPI specs. Use when adding or changing an endpoint, writing an API contract, or reviewing a public interface.
---

# API Design

## REST
- Resources are plural nouns: `/orders/{id}/items`. Verbs belong to HTTP methods, not paths.
- Use the status that matches the outcome: 201 on create with `Location`, 204 on delete, 409 on conflict, 422 on validation failure, 429 with `Retry-After` on rate limits.
- Return one error shape everywhere. Example: `{"error": {"code": "invalid_field", "message": "...", "field": "email"}}`. Never leak stack traces or SQL.
- Paginate every list. Prefer cursor pagination (`next_cursor`) over offset for large or changing data.
- Make PUT and DELETE idempotent. Accept an `Idempotency-Key` header on POST that creates money movement or external side effects.
- Version in the URL (`/v1/`) only when a breaking change is unavoidable. Additive changes do not need a version.

## Compatibility
- Adding an optional field is safe. Removing a field, renaming it, or changing its type is breaking.
- Deprecate with a date and a `Deprecation` or `Sunset` header before removal.

## GraphQL
- Limit query depth and complexity. Set a timeout.
- Resolve related data in batches (DataLoader pattern) to avoid N+1 queries.
- Errors go in the `errors` array with a stable `extensions.code`.

## OpenAPI
- Write the spec before the handler when the contract is new. Generate the client from it, not the other way round.
- Every operation has `operationId`, a request example, and each response code it can return.

## Review checklist
- Authorization checked per object, and per route as well.
- Input validated with a schema at the boundary.
- Response excludes internal fields (password hashes, internal IDs, audit columns).
- Rate limits and size limits set on request bodies.
