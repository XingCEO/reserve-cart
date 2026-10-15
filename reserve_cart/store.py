"""Atomic stock reservations and an explicit pickup-order state machine."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins(username TEXT PRIMARY KEY,password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products(
 id INTEGER PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL,
 category TEXT NOT NULL,price_cents INTEGER NOT NULL CHECK(price_cents>=0),
 stock INTEGER NOT NULL CHECK(stock>=0),active INTEGER NOT NULL DEFAULT 1,
 art TEXT NOT NULL DEFAULT 'vase'
);
CREATE TABLE IF NOT EXISTS orders(
 id INTEGER PRIMARY KEY,token TEXT UNIQUE NOT NULL,owner TEXT NOT NULL,
 request_key TEXT NOT NULL,request_hash TEXT NOT NULL,
 customer_name TEXT NOT NULL,email TEXT NOT NULL,note TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('reserved','paid','ready','collected','cancelled','expired','refunded')),
 total_cents INTEGER NOT NULL,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,
 UNIQUE(owner,request_key)
);
CREATE INDEX IF NOT EXISTS expiring_orders ON orders(status,expires_at);
CREATE TABLE IF NOT EXISTS order_items(
 id INTEGER PRIMARY KEY,order_id INTEGER NOT NULL REFERENCES orders(id),product_id INTEGER NOT NULL REFERENCES products(id),
 name TEXT NOT NULL,sku TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),unit_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY,order_id INTEGER NOT NULL REFERENCES orders(id),action TEXT NOT NULL,
 actor TEXT NOT NULL,note TEXT NOT NULL,created_at INTEGER NOT NULL,
 request_key TEXT,request_hash TEXT,UNIQUE(order_id,request_key)
);
CREATE TABLE IF NOT EXISTS stock_ledger(
 id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL REFERENCES products(id),delta INTEGER NOT NULL,
 reason TEXT NOT NULL,order_id INTEGER REFERENCES orders(id),created_at INTEGER NOT NULL
);
"""


class Error(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def integer(value, label, low=0, high=100_000_000):
    if type(value) is not int or not low <= value <= high:
        raise Error(f"{label} must be an integer from {low} to {high}")
    return value


def text(value, label, limit=120, empty=False):
    if (
        not isinstance(value, str)
        or len(value.strip()) > limit
        or (not empty and not value.strip())
    ):
        raise Error(f"Check {label} (maximum {limit} characters)")
    return value.strip()


def connect(path):
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
    finally:
        db.close()


@contextmanager
def transaction(path):
    db = connect(path)
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()


def digest(payload):
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def request_identity(payload):
    key = text(payload.get("idempotency_key"), "request key", 100)
    if not re.fullmatch("[A-Za-z0-9_-]{8,100}", key):
        raise Error(
            "Use a unique request key with 8–100 letters, digits, hyphens or underscores"
        )
    return key, digest(payload)


def restore(db, order_id, reason, now):
    for item in db.execute(
        "SELECT product_id,quantity FROM order_items WHERE order_id=?", (order_id,)
    ).fetchall():
        db.execute(
            "UPDATE products SET stock=stock+? WHERE id=?",
            (item["quantity"], item["product_id"]),
        )
        db.execute(
            "INSERT INTO stock_ledger(product_id,delta,reason,order_id,created_at) VALUES(?,?,?,?,?)",
            (item["product_id"], item["quantity"], reason, order_id, now),
        )


def expire(db, now):
    ids = [
        r[0]
        for r in db.execute(
            "SELECT id FROM orders WHERE status='reserved' AND expires_at<=?", (now,)
        )
    ]
    for order_id in ids:
        restore(db, order_id, "Reservation expired", now)
        db.execute("UPDATE orders SET status='expired' WHERE id=?", (order_id,))
        db.execute(
            "INSERT INTO events(order_id,action,actor,note,created_at) VALUES(?,?,?,?,?)",
            (order_id, "expired", "system", "Reservation window ended", now),
        )
    return len(ids)


def snapshot(db, order, private=False):
    result = {
        key: order[key]
        for key in ["id", "status", "total_cents", "created_at", "expires_at"]
    }
    result["items"] = [
        dict(row)
        for row in db.execute(
            "SELECT id,product_id,name,sku,quantity,unit_cents FROM order_items WHERE order_id=? ORDER BY id",
            (order["id"],),
        )
    ]
    result["timeline"] = [
        dict(row)
        for row in db.execute(
            "SELECT action,created_at FROM events WHERE order_id=? ORDER BY id",
            (order["id"],),
        )
    ]
    if private:
        result.update(
            customer_name=order["customer_name"],
            email=order["email"],
            note=order["note"],
        )
        result["timeline"] = [
            dict(row)
            for row in db.execute(
                "SELECT action,actor,note,created_at FROM events WHERE order_id=? ORDER BY id",
                (order["id"],),
            )
        ]
    return result


def sweep(path, now=None):
    now = int(time.time()) if now is None else now
    with transaction(path) as db:
        return expire(db, now)


def catalog(path, now=None):
    now = int(time.time()) if now is None else now
    with transaction(path) as db:
        expire(db, now)
        return [
            dict(row)
            for row in db.execute("SELECT * FROM products WHERE active=1 ORDER BY id")
        ]


def reserve(path, owner, payload, now=None, ttl=1800):
    now = int(time.time()) if now is None else now
    key, hashed = request_identity(payload)
    name = text(payload.get("name"), "name", 100)
    email = text(payload.get("email"), "email", 200)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise Error("Enter a valid email address")
    note = text(payload.get("note", ""), "pickup note", 400, True)
    lines = payload.get("items")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 30:
        raise Error("Choose 1–30 product lines")
    integer(ttl, "Reservation duration", 60, 86400)
    with transaction(path) as db:
        expire(db, now)
        old = db.execute(
            "SELECT * FROM orders WHERE owner=? AND request_key=?", (owner, key)
        ).fetchone()
        if old:
            if old["request_hash"] != hashed:
                raise Error("This request key belongs to a different checkout", 409)
            return {**snapshot(db, old), "token": old["token"]}
        if (
            db.execute(
                "SELECT count(*) FROM orders WHERE owner=? AND status='reserved'",
                (owner,),
            ).fetchone()[0]
            >= 3
        ):
            raise Error("Finish or cancel an existing reservation first", 429)
        selected = []
        seen = set()
        total = 0
        for line in lines:
            if not isinstance(line, dict):
                raise Error("Each cart line must be an object")
            pid = integer(line.get("product_id"), "Product", 1)
            qty = integer(line.get("quantity"), "Quantity", 1, 20)
            if pid in seen:
                raise Error("Combine duplicate product lines")
            seen.add(pid)
            product = db.execute(
                "SELECT * FROM products WHERE id=? AND active=1", (pid,)
            ).fetchone()
            if not product or product["stock"] < qty:
                raise Error(
                    "An item is no longer available in that quantity. Refresh your bag.",
                    409,
                )
            total += product["price_cents"] * qty
            selected.append((product, qty))
        integer(total, "Order total")
        token = secrets.token_urlsafe(32)
        cur = db.execute(
            "INSERT INTO orders(token,owner,request_key,request_hash,customer_name,email,note,status,total_cents,created_at,expires_at) VALUES(?,?,?,?,?,?,?,'reserved',?,?,?)",
            (token, owner, key, hashed, name, email, note, total, now, now + ttl),
        )
        order_id = cur.lastrowid
        for product, qty in selected:
            db.execute(
                "UPDATE products SET stock=stock-? WHERE id=?", (qty, product["id"])
            )
            db.execute(
                "INSERT INTO order_items(order_id,product_id,name,sku,quantity,unit_cents) VALUES(?,?,?,?,?,?)",
                (
                    order_id,
                    product["id"],
                    product["name"],
                    product["sku"],
                    qty,
                    product["price_cents"],
                ),
            )
            db.execute(
                "INSERT INTO stock_ledger(product_id,delta,reason,order_id,created_at) VALUES(?,?,?,?,?)",
                (product["id"], -qty, "Reserved", order_id, now),
            )
        db.execute(
            "INSERT INTO events(order_id,action,actor,note,created_at) VALUES(?,?,?,?,?)",
            (order_id, "reserved", "customer", "Stock reserved", now),
        )
        return {
            **snapshot(
                db,
                db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone(),
            ),
            "token": token,
        }


def get_order(path, token, now=None):
    now = int(time.time()) if now is None else now
    with transaction(path) as db:
        expire(db, now)
        order = db.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
        if not order:
            raise Error("Order link not found", 404)
        return snapshot(db, order)


def transition(path, payload, actor, order_id=None, token=None, now=None):
    now = int(time.time()) if now is None else now
    key, hashed = request_identity(payload)
    action = payload.get("action")
    note = text(payload.get("note", ""), "note", 400, True)
    if actor == "customer" and action != "cancel":
        raise Error("Customers can only cancel an unpaid reservation", 403)
    transitions = {
        "pay": ({"reserved"}, "paid"),
        "ready": ({"paid"}, "ready"),
        "collect": ({"ready"}, "collected"),
        "cancel": ({"reserved"}, "cancelled"),
        "refund": ({"paid", "ready"}, "refunded"),
    }
    if action not in transitions:
        raise Error("Unknown order action")
    if action in ("pay", "refund") and not note:
        raise Error("Add an external payment or refund reference")
    # Expiration is a separate committed maintenance transaction so an invalid
    # payment attempt cannot roll it back and retain already-expired stock.
    sweep(path, now)
    with transaction(path) as db:
        expire(db, now)
        order = (
            db.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
            if token
            else db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        )
        if not order:
            raise Error("Order not found", 404)
        old = db.execute(
            "SELECT request_hash FROM events WHERE order_id=? AND request_key=?",
            (order["id"], key),
        ).fetchone()
        if old:
            if old[0] != hashed:
                raise Error("Request key was already used for a different action", 409)
            return snapshot(db, order, private=actor != "customer")
        allowed, target = transitions[action]
        if order["status"] not in allowed:
            raise Error(f"Cannot {action} an order that is {order['status']}", 409)
        if action in ("cancel", "refund"):
            restore(db, order["id"], target, now)
        db.execute("UPDATE orders SET status=? WHERE id=?", (target, order["id"]))
        db.execute(
            "INSERT INTO events(order_id,action,actor,note,created_at,request_key,request_hash) VALUES(?,?,?,?,?,?,?)",
            (order["id"], target, actor, note, now, key, hashed),
        )
        return snapshot(
            db,
            db.execute("SELECT * FROM orders WHERE id=?", (order["id"],)).fetchone(),
            private=actor != "customer",
        )


def admin_state(path, now=None):
    now = int(time.time()) if now is None else now
    with transaction(path) as db:
        expire(db, now)
        return {
            "products": [
                dict(r) for r in db.execute("SELECT * FROM products ORDER BY id")
            ],
            "orders": [
                snapshot(db, r, True)
                for r in db.execute(
                    "SELECT * FROM orders ORDER BY id DESC LIMIT 100"
                ).fetchall()
            ],
        }


def save_product(path, payload, product_id=None):
    name = text(payload.get("name"), "name")
    description = text(payload.get("description"), "description", 1000)
    category = text(payload.get("category"), "category", 50)
    price = integer(payload.get("price_cents"), "price")
    art = payload.get("art", "vase")
    if art not in ("vase", "cup", "lamp", "bowl", "tray", "carafe"):
        raise Error("Choose a supported product illustration")
    now = int(time.time())
    with transaction(path) as db:
        if product_id is None:
            sku = text(payload.get("sku"), "SKU", 60)
            stock = integer(payload.get("stock", 0), "stock", 0, 1_000_000)
            if db.execute("SELECT 1 FROM products WHERE sku=?", (sku,)).fetchone():
                raise Error("SKU already exists", 409)
            cur = db.execute(
                "INSERT INTO products(sku,name,description,category,price_cents,stock,art) VALUES(?,?,?,?,?,?,?)",
                (sku, name, description, category, price, stock, art),
            )
            product_id = cur.lastrowid
            db.execute(
                "INSERT INTO stock_ledger(product_id,delta,reason,created_at) VALUES(?,?,?,?)",
                (product_id, stock, "Opening stock", now),
            )
        else:
            active = integer(payload.get("active", 1), "active", 0, 1)
            if (
                db.execute(
                    "UPDATE products SET name=?,description=?,category=?,price_cents=?,art=?,active=? WHERE id=?",
                    (name, description, category, price, art, active, product_id),
                ).rowcount
                != 1
            ):
                raise Error("Product not found", 404)
        return {"id": product_id}


def adjust_stock(path, product_id, payload):
    delta = integer(payload.get("delta"), "adjustment", -1_000_000, 1_000_000)
    reason = text(payload.get("reason"), "reason", 200)
    with transaction(path) as db:
        if (
            db.execute(
                "UPDATE products SET stock=stock+? WHERE id=? AND stock+? BETWEEN 0 AND 1000000",
                (delta, product_id, delta),
            ).rowcount
            != 1
        ):
            raise Error("Adjustment would make stock invalid", 409)
        db.execute(
            "INSERT INTO stock_ledger(product_id,delta,reason,created_at) VALUES(?,?,?,?)",
            (product_id, delta, reason, int(time.time())),
        )
        return {"ok": True}
