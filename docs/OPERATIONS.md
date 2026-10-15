# Operating Reserve Cart

## Data ownership

The default database is `.local/shop.sqlite3`. The sibling `session.key` signs browser sessions and is created with file mode 0600. Neither belongs in Git. The database contains customer names, emails, notes and private order tokens; anyone with database access already has access to those records. Restrict filesystem access, encrypt backups as appropriate and define a retention policy for your shop.

Use `--database /absolute/path/shop.sqlite3` for the CLI or `SHOP_DATABASE` for the WSGI application. Keep one currency convention (USD minor units in this release). Replace the fictional Stillday branding and sample product descriptions before using the storefront for a real shop.

## Private order links

Order tokens are random 256-bit values. The browser places them in `#order=...` fragments and sends them via the Authorization header. Do not log Authorization headers. Avoid embedding customer links in analytics, issue reports or screenshots of real orders. Links allow viewing and cancellation of unpaid reservations, not reading contact details or recording payments.

Checkout recovery is stored in the browser tab's session storage. Reloading can recover an interrupted request if the session cookie remains valid. Clearing cookies or closing the tab can lose recovery state. Check existing orders before manually recreating an uncertain reservation.

## Deploying

Initialize a database and admin account with the CLI first. For a Unix WSGI deployment:

```bash
python -m pip install gunicorn
SHOP_DATABASE=/absolute/path/shop.sqlite3 SHOP_HTTPS=1 \
  gunicorn --workers 1 --threads 4 --bind 127.0.0.1:5056 'reserve_cart:create_app()'
```

Put a configured HTTPS reverse proxy in front of the loopback listener. `SHOP_HTTPS=1` enables secure cookies; the browser must then use HTTPS. No forwarded proxy headers are implicitly trusted. The included Flask development server is for local evaluation only.

Login throttling is process-local and based on the observed client address. Use one worker, or replace it with a shared limiter. A reverse proxy may cause clients to share a limit. The per-session hold cap is not sufficient for a public product launch: add a deployment-level rate limiter or another abuse-control design before exposing scarce inventory publicly.

## Expiration and external money

Expiry is checked on relevant reads and mutations. A paid order is never auto-expired. An unpaid hold at or beyond its deadline is expired and cannot be marked paid. If payment arrives late, reconcile the external payment and create a new reservation only if stock is still available.

The optional `--sweep` command performs cleanup and exits. Configure scheduling yourself if proactive cleanup is needed. No unattended task is installed by this repository.

Only record a payment after checking the external receipt. Only record a refund after returning money through the original external method. Refund recording is supported before collection; returns after collection need a separate operational process in this release.

## Backups

Use SQLite's backup API or `.backup` command. Do not copy only the main database file while WAL writes are active. Test a restore into a separate directory, run `PRAGMA integrity_check`, and verify known orders and ledger totals. Stop the app before replacing its live database. Deleting the signing key while stopped forces sessions to renew and loses checkout idempotency ownership for those browsers; plan that change carefully.
