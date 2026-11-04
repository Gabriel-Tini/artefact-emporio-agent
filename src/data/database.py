"""Gerenciador do banco de dados SQLite relacional (`emporio.db`).

Implementa:
- Modo WAL (`PRAGMA journal_mode = WAL`) e `busy_timeout = 5000` para leituras e escritas concorrentes sem lock.
- Integridade referencial ativa (`PRAGMA foreign_keys = ON`).
- Funções escalares determinísticas registradas no SQLite:
  * `unaccent(text)`: remoção de acentos/diacríticos e normalização lowercase.
  * `clean_digits(text)`: higienização de telefones, CPFs e CEPs mantendo apenas dígitos.
- Schema completo com 8 tabelas (`categories`, `customers`, `products`, `quarantined_products`,
  `orders`, `order_items`, `promotions` e `handoff_tickets`), constraints `CHECK` e índices de performance.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Optional

from src.config import DB_PATH


def unaccent_text(val: Optional[str]) -> str:
    """Remove acentos/diacríticos e converte para minúsculas para buscas insensíveis no SQLite."""
    if val is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(val))
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    return without_accents.lower()


def clean_digits_sql(val: Optional[str]) -> str:
    """Extrai apenas dígitos numéricos de uma string (ex: higienização de telefones/CPFs)."""
    if val is None:
        return ""
    return re.sub(r"\D", "", str(val))


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    price_brl REAL NOT NULL CHECK (price_brl >= 0),
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    description TEXT,
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    status TEXT NOT NULL CHECK (status IN ('active', 'discontinued', 'coming_soon')),
    specs TEXT,
    created_at TEXT,
    trust_status TEXT NOT NULL DEFAULT 'approved' CHECK (trust_status IN ('approved', 'quarantined')),
    quarantine_reasons TEXT,
    FOREIGN KEY (category_id) REFERENCES categories (category_id)
);

CREATE TABLE IF NOT EXISTS quarantined_products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category_id INTEGER,
    price_brl REAL,
    reasons TEXT NOT NULL,
    quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products (product_id),
    FOREIGN KEY (category_id) REFERENCES categories (category_id)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')),
    total_brl REAL NOT NULL CHECK (total_brl >= 0),
    payment_method TEXT,
    tracking_code TEXT,
    estimated_delivery TEXT,
    notes TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    UNIQUE (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES orders (order_id),
    FOREIGN KEY (product_id) REFERENCES products (product_id)
);

CREATE TABLE IF NOT EXISTS promotions (
    promotion_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    discount_percent REAL NOT NULL CHECK (discount_percent >= 0 AND discount_percent <= 100),
    description TEXT NOT NULL,
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
    FOREIGN KEY (product_id) REFERENCES products (product_id)
);

CREATE TABLE IF NOT EXISTS handoff_tickets (
    protocol TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    contact TEXT NOT NULL,
    reason TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para buscas rápidas e seguras
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_trust ON products(trust_status);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_promotions_product ON promotions(product_id, is_active);
"""


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Retorna uma conexão SQLite configurada com WAL mode, busy_timeout, Row factory e funções customizadas."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.create_function("unaccent", 1, unaccent_text)
    conn.create_function("clean_digits", 1, clean_digits_sql)
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Inicializa as tabelas, constraints e índices no banco SQLite."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA_SQL)
    finally:
        conn.close()
