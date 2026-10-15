# Reserve Cart API

Get `GET /api/session` first and retain the cookie and returned CSRF token. Every mutation requires JSON and `X-CSRF-Token`. All prices use integer USD minor units. Public APIs never accept a client-calculated total.

| Route | Contract |
| --- | --- |
| GET `/api/products` | Active catalog and available stock; releases expired holds |
| POST `/api/checkout` | name, email, optional note, idempotency_key, items[{product_id,quantity}] |
| GET `/api/order` | Requires `Authorization: Bearer <private-token>` |
| POST `/api/order/cancel` | Same private token; action=cancel, idempotency_key, optional note |
| POST `/api/admin/login` | username, password; rotates CSRF token |
| POST `/api/admin/logout` | Clears the browser session |
| GET `/api/admin/state` | Authenticated: all products and latest 100 orders with contact details |
| POST `/api/admin/orders/{id}` | Authenticated: action, idempotency_key, note |
| POST `/api/admin/products` | Authenticated: sku, name, description, category, price_cents, stock, art |
| POST `/api/admin/products/{id}` | Authenticated: name, description, category, price_cents, art, active |
| POST `/api/admin/products/{id}/stock` | Authenticated: delta, reason; adjusts available, unreserved stock |

Checkout example:

```json
{"idempotency_key":"unique-checkout-request","name":"Ada Example","email":"ada@example.org","note":"Saturday pickup","items":[{"product_id":1,"quantity":2}]}
```

The result includes `id`, `token`, `status`, `total_cents`, Unix timestamps, original-price `items` and `timeline`. A replay returns the current status of the same order, including an expired or cancelled state; it does not create a fresh hold. Preserve the original request body and session cookie during retries. A new browser session is a new idempotency namespace.

Admin actions: `pay`, `ready`, `collect`, `cancel`, `refund`. Payment/refund actions require a nonempty external reference in `note`. The app does not verify that reference with a payment provider. Action keys are unique per order; a repeated key with a changed body returns a conflict.

Illustration choices: `cup`, `lamp`, `vase`, `carafe`, `bowl`, `tray`. `active` is integer 0 or 1. New products default to active. Product names/descriptions are text, never HTML. Individual cart quantities are integers 1–20, with at most 30 distinct product lines.

Errors return `{"error":"message"}`. Status codes: 400 validation, 401 authentication/capability missing, 403 CSRF/forbidden action, 404 unknown order/product, 409 inventory/state/request-key conflict, 413 oversized request, 415 wrong content type, 429 session reservation limit or login limit, 503 database busy. A checkout replay returns 201, just like the initial successful checkout.
