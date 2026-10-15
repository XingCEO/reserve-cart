import argparse
import os
import secrets
from . import create_app, create_admin, store


def main():
    parser = argparse.ArgumentParser(
        description="Reserve Cart — a limited-stock pickup shop"
    )
    parser.add_argument("--database", default=".local/shop.sqlite3")
    parser.add_argument("--port", type=int, default=5056)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--sweep", action="store_true", help="Release expired reservations and exit"
    )
    args = parser.parse_args()
    app = create_app({"DATABASE": args.database})
    if args.sweep:
        print(f"Released {store.sweep(args.database)} expired reservations")
        return
    db = store.connect(args.database)
    try:
        exists = db.execute("SELECT 1 FROM admins").fetchone()
    finally:
        db.close()
    if not exists:
        password = os.environ.get("SHOP_ADMIN_PASSWORD")
        if not password:
            if not args.demo:
                parser.error("Set SHOP_ADMIN_PASSWORD (12+ characters), or use --demo")
            password = secrets.token_urlsafe(15)
            print(f"Demo admin password: {password}", flush=True)
        create_admin(args.database, password)
        if args.demo:
            for sku, name, description, category, price, stock, art in [
                (
                    "FN-01",
                    "The everyday cup",
                    "A generous, softly rounded cup for slow mornings. Matte terracotta glaze, made for the daily ritual.",
                    "Ceramics",
                    2800,
                    12,
                    "cup",
                ),
                (
                    "FN-02",
                    "Arc table lamp",
                    "A quiet pool of warm light. An illustrated sample product for your own limited collection.",
                    "Living",
                    8900,
                    6,
                    "lamp",
                ),
                (
                    "FN-03",
                    "Stem vase",
                    "A sculptural silhouette for a single branch or a handful of stems. Warm sand finish.",
                    "Ceramics",
                    4200,
                    8,
                    "vase",
                ),
                (
                    "FN-04",
                    "Pour carafe",
                    "A balanced shape for water, flowers or whatever the afternoon needs. Sage ceramic finish.",
                    "Table",
                    4800,
                    10,
                    "carafe",
                ),
                (
                    "FN-05",
                    "Gather bowl",
                    "A shallow bowl with room for fruit, keys and the things that find their way home.",
                    "Table",
                    3600,
                    9,
                    "bowl",
                ),
                (
                    "FN-06",
                    "Oak catchall",
                    "A simple resting place for the everyday essentials. Natural wood tone, rounded corners.",
                    "Living",
                    3200,
                    14,
                    "tray",
                ),
            ]:
                store.save_product(
                    args.database,
                    dict(
                        sku=sku,
                        name=name,
                        description=description,
                        category=category,
                        price_cents=price,
                        stock=stock,
                        art=art,
                    ),
                )
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
