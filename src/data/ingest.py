"""Pipeline ETL de Ingestão, Auditoria e Governança de Dados (`src/data/ingest.py`).

Executa:
1. Leitura dos 6 arquivos CSV em `data/raw/` utilizando encoding `utf-8-sig`.
2. Auditoria linha a linha do catálogo via `ProductAuditor` (65 analisados -> 58 aprovados e 7 em quarentena:
   IDs 135, 136, 137, 139, 140, 142 e 144).
3. Detecção de anomalias cadastrais em clientes (e-mail duplicado `bruno.martins@jmail.com` nos clientes #11 e #43),
   mantendo a integridade referencial no carregamento dos pedidos históricos.
4. Verificação pós-carga (`PRAGMA foreign_key_check` e `PRAGMA integrity_check`).
5. Exportação do laudo técnico completo em `data/processed/data_quality_report.json`.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.config import (
    AUDIT_REPORT_PATH,
    CATEGORIES_CSV,
    CUSTOMERS_CSV,
    DB_PATH,
    ORDER_ITEMS_CSV,
    ORDERS_CSV,
    PRODUCTS_CSV,
    PROMOTIONS_CSV,
)
from src.data.auditor import ProductAuditor
from src.data.database import get_connection, init_db


def load_csv(path: Path) -> List[Dict[str, Any]]:
    """Carrega um arquivo CSV com suporte a UTF-8 com ou sem BOM (`utf-8-sig`)."""
    with open(path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def run_ingestion() -> Dict[str, Any]:
    """Executa o pipeline completo de ingestão no SQLite e exporta `data_quality_report.json`."""
    print("Iniciando pipeline de ingestão e governança de dados...")
    init_db()
    conn = get_connection()
    auditor = ProductAuditor()

    report: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "database_file": str(DB_PATH),
        "metrics": {},
        "quarantined_products": [],
        "empty_categories": [],
        "warnings": [],
    }

    try:
        with conn:
            cursor = conn.cursor()

            # Limpar tabelas na ordem inversa de dependências (filhos antes dos pais)
            cursor.execute("DELETE FROM order_items;")
            cursor.execute("DELETE FROM promotions;")
            cursor.execute("DELETE FROM orders;")
            cursor.execute("DELETE FROM quarantined_products;")
            cursor.execute("DELETE FROM products;")
            cursor.execute("DELETE FROM customers;")
            cursor.execute("DELETE FROM categories;")

            # 1. Ingerir Categorias
            categories_data = load_csv(CATEGORIES_CSV)
            cat_map: Dict[int, str] = {}
            for row in categories_data:
                cid = int(row["category_id"])
                cat_map[cid] = row["name"].strip()
                cursor.execute(
                    "INSERT INTO categories (category_id, name, description) VALUES (?, ?, ?);",
                    (cid, row["name"].strip(), row.get("description", "").strip()),
                )
            print(f"Categorias carregadas: {len(categories_data)}")

            # 2. Ingerir Clientes e detectar e-mails duplicados (#11 e #43)
            customers_data = load_csv(CUSTOMERS_CSV)
            seen_emails: Dict[str, int] = {}
            for row in customers_data:
                cid_val = int(row["customer_id"])
                email_val = row["email"].strip()
                email_key = email_val.lower()
                if email_key in seen_emails:
                    report["warnings"].append(
                        f"DUPLICATE_CUSTOMER_EMAIL: e-mail '{email_val}' compartilhado entre "
                        f"customer_id {seen_emails[email_key]} e {cid_val}"
                    )
                else:
                    seen_emails[email_key] = cid_val

                cursor.execute(
                    "INSERT INTO customers (customer_id, name, phone, email, city) VALUES (?, ?, ?, ?, ?);",
                    (
                        cid_val,
                        row["name"].strip(),
                        row["phone"].strip(),
                        email_val,
                        row["city"].strip(),
                    ),
                )
            print(f"Clientes carregados: {len(customers_data)}")

            # 3. Auditar e Ingerir Produtos (Aprovados vs Quarentena)
            products_data = load_csv(PRODUCTS_CSV)
            approved_count = 0
            quarantined_count = 0
            cat_product_counts: Dict[int, int] = {cid: 0 for cid in cat_map.keys()}

            for row in products_data:
                trust_status, issues = auditor.audit_row(row, cat_map)
                pid = int(row["product_id"])
                cid = int(row["category_id"])
                price = float(row["price_brl"])
                name = row["name"].strip()
                desc = row["description"].strip()
                stock = int(row["stock_quantity"])
                status = row["status"].strip()
                specs = row["specs"].strip()
                created_at = row["created_at"].strip()

                reasons_str = "; ".join(issues) if issues else None

                cursor.execute(
                    """INSERT INTO products 
                       (product_id, price_brl, name, category_id, description, stock_quantity, status, specs, created_at, trust_status, quarantine_reasons)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        pid,
                        price,
                        name,
                        cid,
                        desc,
                        stock,
                        status,
                        specs,
                        created_at,
                        trust_status,
                        reasons_str,
                    ),
                )

                if trust_status == "quarantined":
                    quarantined_count += 1
                    cursor.execute(
                        "INSERT INTO quarantined_products (product_id, name, category_id, price_brl, reasons) VALUES (?, ?, ?, ?, ?);",
                        (pid, name, cid, price, reasons_str),
                    )
                    report["quarantined_products"].append(
                        {
                            "product_id": pid,
                            "name": name,
                            "category": cat_map.get(cid, "Desconhecida"),
                            "price_brl": price,
                            "reasons": issues,
                        }
                    )
                else:
                    approved_count += 1
                    cat_product_counts[cid] = cat_product_counts.get(cid, 0) + 1

            print(
                f"Produtos auditados: {len(products_data)} "
                f"(Aprovados: {approved_count}, Quarentena: {quarantined_count})"
            )

            # Identificar categorias sem produtos aprovados
            for cid, name in cat_map.items():
                if cat_product_counts.get(cid, 0) == 0:
                    report["empty_categories"].append(
                        {
                            "category_id": cid,
                            "name": name,
                            "approved_products_count": 0,
                        }
                    )

            # 4. Ingerir Pedidos
            orders_data = load_csv(ORDERS_CSV)
            for row in orders_data:
                cursor.execute(
                    """INSERT INTO orders 
                       (order_id, customer_id, order_date, status, total_brl, payment_method, tracking_code, estimated_delivery, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        int(row["order_id"]),
                        int(row["customer_id"]),
                        row["order_date"].strip(),
                        row["status"].strip(),
                        float(row["total_brl"]),
                        row.get("payment_method", "").strip() or None,
                        row.get("tracking_code", "").strip() or None,
                        row.get("estimated_delivery", "").strip() or None,
                        row.get("notes", "").strip() or None,
                    ),
                )
            print(f"Pedidos carregados: {len(orders_data)}")

            # 5. Ingerir Itens dos Pedidos
            order_items_data = load_csv(ORDER_ITEMS_CSV)
            for row in order_items_data:
                cursor.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?);",
                    (
                        int(row["order_id"]),
                        int(row["product_id"]),
                        int(row["quantity"]),
                    ),
                )
            print(f"Itens de pedidos carregados: {len(order_items_data)}")

            # 6. Ingerir Promoções
            promotions_data = load_csv(PROMOTIONS_CSV)
            active_promos = 0
            for row in promotions_data:
                is_act = int(row["is_active"])
                if is_act == 1:
                    active_promos += 1
                cursor.execute(
                    "INSERT INTO promotions (promotion_id, product_id, discount_percent, description, is_active) VALUES (?, ?, ?, ?, ?);",
                    (
                        int(row["promotion_id"]),
                        int(row["product_id"]),
                        float(row["discount_percent"]),
                        row["description"].strip(),
                        is_act,
                    ),
                )
            print(
                f"Promoções carregadas: {len(promotions_data)} (Ativas: {active_promos})"
            )

            # 7. Verificação de integridade referencial e estrutural pós-carga
            fk_violations = cursor.execute("PRAGMA foreign_key_check;").fetchall()
            if fk_violations:
                report["warnings"].append(
                    f"Violações de chave estrangeira detectadas: {len(fk_violations)}"
                )

            integrity_status = cursor.execute("PRAGMA integrity_check;").fetchone()[0]
    finally:
        conn.close()

    # Preencher métricas consolidadas no laudo técnico
    report["metrics"] = {
        "total_categories": len(categories_data),
        "total_customers": len(customers_data),
        "total_products": len(products_data),
        "approved_products": approved_count,
        "quarantined_products": quarantined_count,
        "total_orders": len(orders_data),
        "total_order_items": len(order_items_data),
        "total_promotions": len(promotions_data),
        "active_promotions": active_promos,
        "sqlite_integrity_check": integrity_status,
        "foreign_key_violations": len(fk_violations),
    }

    AUDIT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(
        f"Relatório de Governança de Dados salvo com sucesso em: {AUDIT_REPORT_PATH}"
    )
    return report


if __name__ == "__main__":
    run_ingestion()
