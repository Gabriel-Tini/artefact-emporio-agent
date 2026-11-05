"""Ferramentas determinísticas de catálogo, estoque, quarentena e cálculo de pagamento (`src/tools/catalog_tools.py`)."""

from __future__ import annotations

import json
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from src.data.database import get_connection, unaccent_text

ALWAYS_ACCESSORIES = [
    "palheta",
    "palhetas",
    "cabo",
    "cabos",
    "case",
    "cases",
    "capa",
    "capas",
    "pedal",
    "pedais",
    "amplificador",
    "amplificadores",
    "encordoamento",
    "correia",
    "correias",
    "afinador avulso",
    "suporte de chao",
    "capotraste",
    "estante de partitura",
    "baqueta",
    "baquetas",
]

SEARCH_STOPWORDS = {
    "de",
    "da",
    "do",
    "das",
    "dos",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "um",
    "uma",
    "uns",
    "umas",
    "com",
    "sem",
    "para",
    "por",
    "que",
    "qual",
    "tem",
}


def money_round(val: float | Decimal) -> float:
    """Arredondamento financeiro padrão (`ROUND_HALF_UP`) para 2 casas decimais."""
    d = Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(d)


def check_accessory_query(query: str) -> Optional[str]:
    """Verifica se a busca é por acessório avulso, fora do escopo da loja (Seção 1 e 7.1)."""
    q_norm = unaccent_text(query)

    for kw in ALWAYS_ACCESSORIES:
        kw_norm = unaccent_text(kw)
        if re.search(r"\b" + re.escape(kw_norm) + r"\b", q_norm):
            return (
                "A Empório da Música trabalha exclusivamente com instrumentos musicais "
                "e não comercializa acessórios avulsos (como palhetas, cabos, cases, pedais ou amplificadores). "
                "Recomendamos consultar lojas parceiras especializadas em acessórios musicais."
            )

    if "corda" in q_norm or "cordas" in q_norm:
        if any(
            term in q_norm
            for term in [
                "jogo de cordas",
                "encordoamento",
                "comprar cordas",
                "cordas avulsas",
                "corda avulsa",
                "corda para",
                "cordas para",
            ]
        ):
            return (
                "A Empório da Música comercializa exclusivamente instrumentos musicais completos. "
                "Não vendemos encordoamentos ou cordas avulsas separadamente."
            )

    return None


def extract_search_terms(query: str) -> List[str]:
    """Extrai termos de busca limpos, sem wildcards SQL e sem stopwords curtas."""
    cleaned = re.sub(r"[%_]", " ", unaccent_text(query))
    words = [
        w
        for w in re.split(r"\s+", cleaned.strip())
        if len(w) > 1 and w not in SEARCH_STOPWORDS
    ]
    return words


@tool
def search_catalog(
    query: Optional[str] = None,
    category_name: Optional[str] = None,
    max_price: Optional[float] = None,
    only_in_stock: bool = False,
) -> Dict[str, Any]:
    """
    Busca instrumentos musicais no catálogo oficial aprovado da Empório da Música.
    Suporta buscas com ou sem acentos (ex: 'violao' ou 'violão') e filtra por nome, descrição e especificações.
    Retorna preços, estoque, especificações técnicas e promoções vigentes.
    Se o produto estiver fora de estoque, descontinuado ou em quarentena técnica, retorna automaticamente alternativas disponíveis.
    """
    if query:
        accessory_notice = check_accessory_query(query)
        if accessory_notice:
            return {
                "status": "out_of_scope",
                "message": accessory_notice,
                "products": [],
            }

    conn = get_connection()
    try:
        cursor = conn.cursor()
        search_words = extract_search_terms(query) if query else []

        # 1. Montar query sobre produtos aprovados (insensível a acentos via função SQLite unaccent)
        sql = """
            SELECT p.product_id, p.name, p.price_brl, p.stock_quantity, p.status, p.specs, p.description,
                   c.name AS category_name,
                   pr.discount_percent, pr.description AS promo_name, pr.is_active AS promo_is_active
            FROM products p
            JOIN categories c ON p.category_id = c.category_id
            LEFT JOIN promotions pr ON p.product_id = pr.product_id AND pr.is_active = 1
            WHERE p.trust_status = 'approved'
        """
        params: List[Any] = []

        for w in search_words:
            sql += (
                " AND (unaccent(p.name) LIKE ? OR unaccent(p.description) LIKE ? "
                "OR unaccent(p.specs) LIKE ? OR unaccent(c.name) LIKE ?)"
            )
            like_w = f"%{w}%"
            params.extend([like_w, like_w, like_w, like_w])

        if category_name and category_name.strip():
            cat_norm = re.sub(r"[%_]", "", unaccent_text(category_name.strip()))
            if cat_norm:
                sql += " AND unaccent(c.name) LIKE ?"
                params.append(f"%{cat_norm}%")

        if max_price is not None:
            sql += " AND p.price_brl <= ?"
            params.append(float(max_price))

        if only_in_stock:
            sql += " AND p.stock_quantity > 0 AND p.status = 'active'"

        sql += (
            " ORDER BY (CASE WHEN p.stock_quantity > 0 AND p.status = 'active' THEN 0 ELSE 1 END), "
            "p.price_brl ASC LIMIT 10;"
        )

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        results = []
        seen_pids = set()
        for r in rows:
            pid = r["product_id"]
            if pid in seen_pids:
                continue
            seen_pids.add(pid)

            specs_dict = {}
            try:
                specs_dict = json.loads(r["specs"]) if r["specs"] else {}
            except Exception:
                pass

            promo_info = None
            final_price = float(r["price_brl"])
            if r["promo_is_active"] == 1 and r["discount_percent"] is not None:
                disc = float(r["discount_percent"])
                final_price = money_round(
                    Decimal(str(r["price_brl"]))
                    * (Decimal("1") - Decimal(str(disc)) / Decimal("100"))
                )
                promo_info = {
                    "campaign": r["promo_name"],
                    "discount_percent": disc,
                    "promotional_price": final_price,
                }

            item = {
                "product_id": pid,
                "name": r["name"],
                "category": r["category_name"],
                "original_price_brl": float(r["price_brl"]),
                "current_price_brl": final_price,
                "stock_quantity": r["stock_quantity"],
                "status": r["status"],
                "is_available": (r["stock_quantity"] > 0 and r["status"] == "active"),
                "specs": specs_dict,
                "promotion": promo_info,
            }
            results.append(item)

        # 2. Verificar se a busca atingiu algum modelo específico em quarentena
        quarantined_matches = []
        if search_words:
            q_sql = """
                SELECT qp.product_id, qp.name, qp.reasons, c.name AS category_name
                FROM quarantined_products qp
                LEFT JOIN categories c ON qp.category_id = c.category_id
                WHERE 1=1
            """
            q_params: List[Any] = []
            for w in search_words:
                q_sql += " AND unaccent(qp.name) LIKE ?"
                q_params.append(f"%{w}%")
            cursor.execute(q_sql, q_params)
            quarantined_matches = [dict(qr) for qr in cursor.fetchall()]

        if not results and quarantined_matches:
            q_item = quarantined_matches[0]
            alt_list = []
            if q_item.get("category_name"):
                cursor.execute(
                    """SELECT p.product_id, p.name, p.price_brl, p.stock_quantity, p.status, c.name AS category_name
                       FROM products p
                       JOIN categories c ON p.category_id = c.category_id
                       WHERE p.trust_status = 'approved' AND c.name = ? AND p.stock_quantity > 0 AND p.status = 'active'
                       ORDER BY p.price_brl ASC LIMIT 3;""",
                    (q_item["category_name"],),
                )
                alt_list = [
                    {
                        "product_id": ar["product_id"],
                        "name": ar["name"],
                        "category": ar["category_name"],
                        "price_brl": float(ar["price_brl"]),
                        "stock_quantity": ar["stock_quantity"],
                    }
                    for ar in cursor.fetchall()
                ]
            return {
                "status": "quarantined_notice",
                "message": (
                    f"O item '{q_item['name']}' encontra-se temporariamente indisponível no sistema "
                    "para auditoria técnica de lote e especificações. No momento não temos unidades liberadas deste modelo."
                ),
                "products": [],
                "suggested_alternatives": alt_list,
            }

        # 3. Se algum produto encontrado estiver sem estoque ou descontinuado, sugerir alternativas disponíveis da categoria
        alternatives = []
        if results and not all(r["is_available"] for r in results):
            target_cat = results[0]["category"]
            cursor.execute(
                """SELECT p.product_id, p.name, p.price_brl, p.stock_quantity, p.status, c.name AS category_name
                   FROM products p
                   JOIN categories c ON p.category_id = c.category_id
                   WHERE p.trust_status = 'approved' AND c.name = ? AND p.stock_quantity > 0 AND p.status = 'active'
                   ORDER BY p.price_brl ASC LIMIT 3;""",
                (target_cat,),
            )
            for ar in cursor.fetchall():
                if ar["product_id"] not in [
                    r["product_id"] for r in results if r["is_available"]
                ]:
                    alternatives.append(
                        {
                            "product_id": ar["product_id"],
                            "name": ar["name"],
                            "category": ar["category_name"],
                            "price_brl": float(ar["price_brl"]),
                            "stock_quantity": ar["stock_quantity"],
                        }
                    )

        return {
            "status": "success",
            "total_found": len(results),
            "products": results,
            "suggested_alternatives": alternatives,
        }
    finally:
        conn.close()


@tool
def calculate_payment_conditions(
    product_id: int, quantity: int = 1
) -> Dict[str, Any]:
    """
    Calcula as condições de pagamento exatas e determinísticas para um produto:
    - Preço original vs promocional (com transparência).
    - Regra estrita de PIX: 5% de desconto à vista SOMENTE se não houver promoção ativa (não-cumulativo).
    - Parcelamento no Cartão sem juros (1x a 12x) respeitando:
      • Até 3x: sem valor mínimo de parcela (exceto compras com total abaixo de R$ 50,00).
      • 4x a 6x: parcela mínima de R$ 80,00.
      • 7x a 12x: parcela mínima de R$ 100,00.
    - Aviso de pagamento combinado para compras acima de R$ 2.000,00.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            """SELECT p.product_id, p.name, p.price_brl, p.stock_quantity, p.status, p.trust_status,
                      pr.promotion_id, pr.discount_percent, pr.description AS promo_name, pr.is_active
               FROM products p
               LEFT JOIN promotions pr ON p.product_id = pr.product_id
               WHERE p.product_id = ?
               ORDER BY pr.is_active DESC, pr.promotion_id DESC;""",
            (int(product_id),),
        )
        rows = cursor.fetchall()

        if not rows:
            return {
                "status": "error",
                "message": f"Produto ID {product_id} não encontrado.",
            }

        row = rows[0]
        if row["trust_status"] == "quarantined":
            return {
                "status": "error",
                "message": f"Produto '{row['name']}' encontra-se em quarentena técnica. Venda e condições bloqueadas.",
            }

        qty = max(1, int(quantity))
        base_unit_dec = Decimal(str(row["price_brl"]))
        subtotal_original = money_round(base_unit_dec * Decimal(qty))

        has_active_promo = row["is_active"] == 1
        active_promo_name = row["promo_name"] if has_active_promo else None
        active_discount_pct = (
            float(row["discount_percent"]) if has_active_promo else 0.0
        )

        if has_active_promo:
            discount_factor = Decimal("1") - (
                Decimal(str(active_discount_pct)) / Decimal("100")
            )
            unit_price_effective = money_round(base_unit_dec * discount_factor)
            total_effective = money_round(
                Decimal(str(unit_price_effective)) * Decimal(qty)
            )
            # Regra Seção 6.2: PIX não acumula desconto de 5% sobre preço já promocional
            pix_discount_pct = 0.0
            pix_total = total_effective
            pix_explanation = (
                f"O desconto de 5% do PIX não é cumulativo com a promoção vigente '{active_promo_name}' "
                f"({active_discount_pct}% off), conforme política da loja (Seção 6.2)."
            )
        else:
            unit_price_effective = float(base_unit_dec)
            total_effective = subtotal_original
            pix_discount_pct = 5.0
            pix_total = money_round(Decimal(str(total_effective)) * Decimal("0.95"))
            pix_explanation = "5% de desconto à vista aplicado sobre o preço de tabela para pagamento via PIX."

        # Simulação de Parcelamento no Cartão (Sem Juros) - Seção 3.1 do Manual:
        # • 1x: sempre disponível (pagamento à vista no crédito).
        # • 2x a 3x: sem juros, sem valor mínimo de parcela (exceto compras abaixo de R$ 50,00).
        # • 4x a 6x: sem juros, parcela mínima de R$ 80,00.
        # • 7x a 12x: sem juros, parcela mínima de R$ 100,00.
        installment_options = []
        max_installments = 1

        for n in range(1, 13):
            installment_value = money_round(Decimal(str(total_effective)) / Decimal(n))
            is_allowed = False

            if n == 1:
                is_allowed = True
            elif 2 <= n <= 3:
                if total_effective >= 50.0:
                    is_allowed = True
            elif 4 <= n <= 6:
                if installment_value >= 80.0:
                    is_allowed = True
            elif 7 <= n <= 12:
                if installment_value >= 100.0:
                    is_allowed = True

            if is_allowed:
                max_installments = n
                installment_options.append(
                    {
                        "installments": n,
                        "monthly_value_brl": installment_value,
                        "total_brl": total_effective,
                    }
                )

        # Verificar histórico de promoção expirada para transparência (Seção 7.3)
        expired_promo_notice = None
        if not has_active_promo:
            expired_rows = [
                r
                for r in rows
                if r["promotion_id"] is not None and r["is_active"] == 0
            ]
            if expired_rows:
                exp = expired_rows[0]
                expired_promo_notice = (
                    f"A promoção '{exp['promo_name']}' ({exp['discount_percent']}%) para este produto já expirou "
                    "e não está mais ativa no sistema."
                )

        return {
            "status": "success",
            "product_id": row["product_id"],
            "product_name": row["name"],
            "quantity": qty,
            "pricing": {
                "unit_price_table_brl": float(base_unit_dec),
                "subtotal_table_brl": subtotal_original,
                "has_active_promotion": has_active_promo,
                "active_promotion_name": active_promo_name,
                "active_discount_percent": active_discount_pct,
                "effective_total_brl": total_effective,
                "expired_promo_notice": expired_promo_notice,
            },
            "payment_methods": {
                "pix": {
                    "discount_percent": pix_discount_pct,
                    "total_brl": pix_total,
                    "explanation": pix_explanation,
                },
                "debit_card": {
                    "condition": "À vista",
                    "total_brl": total_effective,
                },
                "boleto": {
                    "condition": "À vista (compensação em até 3 dias úteis)",
                    "total_brl": total_effective,
                },
                "credit_card": {
                    "max_installments_without_interest": max_installments,
                    "max_installment_summary": (
                        f"{max_installments}x de R$ {money_round(Decimal(str(total_effective)) / Decimal(max_installments)):.2f} sem juros"
                        if max_installments > 1
                        else "1x (à vista)"
                    ),
                    "options": installment_options,
                },
                "combined_payment": {
                    "allowed": total_effective > 2000.0,
                    "rule": "Permitida combinação de formas de pagamento (ex: PIX + Cartão) para compras acima de R$ 2.000,00.",
                },
            },
        }
    finally:
        conn.close()
