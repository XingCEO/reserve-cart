---
name: reservation-state-review
description: Review or extend Reserve Cart checkout and pickup-order behavior, including stock holds, expiration, replay, private order links and external payment recording. Use for changes to reservation or order-state paths in this repository.
---

# Reservation state review

Work from the Reserve Cart checkout. Read `docs/API.md` and the relevant complete functions in `reserve_cart/store.py`. This Skill authorizes no real orders, payments, refunds, customer communications or production changes.

## Establish the state boundary

Draw the allowed transition before editing. `reserved` can become paid, cancelled or expired. Paid can become ready or refunded. Ready can become collected or refunded. Inventory returns only on cancelled, expired or refunded transitions. Collected orders have no return transition in this release.

Locate the write transaction, the expiration check and the event write. A new action must not restore stock twice, silently renew an expired hold or reprice an existing order.

## Choose adversarial examples

- Two sessions reserve the last unit simultaneously.
- A checkout retry arrives after the original hold expired.
- Payment recording arrives exactly at the expiration boundary.
- The same action key arrives twice, then arrives with a changed body.
- An invalid late payment attempt must not preserve expired stock.
- Catalog price/name changes while an order is open.
- A customer capability attempts an admin transition.
- A customer view includes contact data by accident.

Use the injected `now` argument in service tests instead of sleeping. Use a temporary database and separate session owners. Assert both order status and the sum of stock-ledger deltas. Never substitute a real order link for a fixture.

## Verify the customer loop

Run `python -m unittest discover -v`. For UI changes, run `npm run test:e2e` with `PYTHON` set to the intended interpreter. The browser test follows customer and admin paths in separate contexts.

Report the modified transitions, conservation or authorization property tested, checks run and remaining limits. Recording an external payment reference is not evidence that money was transferred.
