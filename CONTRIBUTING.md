# Contributing

Start with a concrete customer or shop workflow and a synthetic fixture. Add a failing test before changing reservations, stock, expiry or order transitions. Run the Python suite and the browser suite when UI behavior changes.

A reservation deducts stock once. Cancellation, expiry or a recorded pre-collection refund restores it once. A paid order must not expire. Prices come from the server and remain on the original order. Customer capability access must not expose contact data or admin actions.

Do not commit real customer records, credentials, private order tokens or databases. Discuss payment-provider integration, email delivery and new dependencies before expanding the scope. Keep the operating guide and API contract accurate.
