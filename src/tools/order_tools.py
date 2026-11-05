"""Ferramentas determinísticas de cálculo de frete e consulta segura de pedidos sob LGPD (`src/tools/order_tools.py`)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from src.data.database import get_connection, unaccent_text

OTHER_STATE_INDICATORS = [
    "rj",
    "rio de janeiro",
    "sp",
    "sao paulo",
    "mg",
    "minas gerais",
    "pr",
    "parana",
    "sc",
    "santa catarina",
    "rs",
    "al",
    "alagoas",
    "rn",
    "ba",
    "pe",
]


@tool
def calculate_shipping(
    destination_city: str,
    order_total_brl: float = 0.0,
    is_large_instrument: bool = False,
    product_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Calcula as opções e prazos de frete conforme a Política de Frete e Entregas (Seção 5 do Manual).
    Distingue a Região Metropolitana de Campo Grande - MS de envios para outras cidades (Correios PAC/SEDEX e Jadlog).
    Se product_id for informado, detecta automaticamente se é um instrumento de grande porte (baterias, pianos/teclados, contrabaixos).
    """
    city_norm = unaccent_text(destination_city.strip())

    # Detecção determinística de instrumento de grande porte via product_id (Seção 5.2)
    large_instrument_detected = bool(is_large_instrument)
    if product_id is not None and not large_instrument_detected:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT category_id, name FROM products WHERE product_id = ?;",
                (int(product_id),),
            )
            prod = cursor.fetchone()
            if prod:
                # Categorias: 2 (Baixos), 3 (Baterias e Percussão), 4 (Teclados e Pianos)
                if prod["category_id"] in (2, 3, 4):
                    large_instrument_detected = True
        finally:
            conn.close()

    # Verificar se é Campo Grande - MS (e não o bairro homônimo em outro estado)
    has_other_state = any(
        re.search(r"\b" + re.escape(st) + r"\b", city_norm)
        for st in OTHER_STATE_INDICATORS
    )
    is_campo_grande_ms = ("campo grande" in city_norm) and not has_other_state

    if is_campo_grande_ms:
        # Seção 5.1: Acima de R$ 500,00 frete grátis; abaixo de R$ 500,00 taxa fixa de R$ 35,00
        is_free = float(order_total_brl) > 500.0
        shipping_cost = 0.0 if is_free else 35.0
        return {
            "status": "success",
            "region": "Região Metropolitana de Campo Grande - MS",
            "delivery_type": "Motoboy Próprio da Loja",
            "is_free_shipping": is_free,
            "shipping_cost_brl": shipping_cost,
            "estimated_days": "1 a 3 dias úteis",
            "policy_rule": (
                "Frete grátis para pedidos acima de R$ 500,00. "
                "Para pedidos abaixo de R$ 500,00, taxa fixa de R$ 35,00. "
                "O cliente será contactado por telefone pelo motoboy antes da entrega."
            ),
        }
    else:
        note_large = (
            "Instrumentos de grande porte (baterias acústicas, pianos digitais, contrabaixos) "
            "podem exigir frete especial com cotação individual."
        )
        return {
            "status": "success",
            "region": f"Envio para Outras Cidades ({destination_city.strip()})",
            "is_large_instrument": large_instrument_detected,
            "options": [
                {
                    "carrier": "SEDEX (Correios)",
                    "estimated_days": "2 a 5 dias úteis",
                    "tracking": "Sim (enviado por e-mail e WhatsApp)",
                    "insurance": "Incluído contra extravio e danos",
                },
                {
                    "carrier": "Jadlog (.package)",
                    "estimated_days": "3 a 8 dias úteis",
                    "tracking": "Sim (enviado por e-mail e WhatsApp)",
                    "insurance": "Incluído contra extravio e danos",
                },
                {
                    "carrier": "PAC (Correios)",
                    "estimated_days": "5 a 12 dias úteis",
                    "tracking": "Sim (enviado por e-mail e WhatsApp)",
                    "insurance": "Incluído contra extravio e danos",
                },
            ],
            "general_policy": (
                "O valor do frete é calculado automaticamente com base no CEP de destino, peso e dimensões do produto. "
                "Todos os envios incluem seguro contra extravios e danos durante o transporte. "
                "Em caso de avaria, o cliente deve recusar o recebimento e entrar em contato imediatamente com a loja."
            ),
            "large_instrument_note": note_large,
        }


@tool
def lookup_customer_orders(
    identifier: str, order_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Consulta o histórico de pedidos e status de entrega de um cliente de forma segura (LGPD).
    Requer identificação estrita através do e-mail completo ou telefone completo (mínimo 8 dígitos numéricos).
    """
    ident = (identifier or "").strip()
    if not ident:
        return {
            "status": "invalid_identifier",
            "message": "Por favor, informe seu e-mail completo ou telefone completo com DDD para localizarmos seu pedido com segurança (LGPD).",
            "orders": [],
        }

    conn = get_connection()
    try:
        cursor = conn.cursor()
        customers = []

        if "@" in ident:
            cursor.execute(
                """SELECT customer_id, name, phone, email, city
                   FROM customers
                   WHERE LOWER(TRIM(email)) = LOWER(?);""",
                (ident,),
            )
            customers = cursor.fetchall()
        else:
            # Blindagem contra enumeração: exige no mínimo 8 dígitos numéricos
            clean_phone = re.sub(r"\D", "", ident)
            if len(clean_phone) < 8:
                return {
                    "status": "invalid_identifier",
                    "message": (
                        "Por proteção de dados (LGPD), não realizamos buscas com números parciais ou curtos. "
                        "Por favor, informe o número de telefone completo (ex: (67) 99812-3456) ou seu e-mail cadastrado."
                    ),
                    "orders": [],
                }

            cursor.execute(
                """SELECT customer_id, name, phone, email, city
                   FROM customers
                   WHERE clean_digits(phone) = ?
                      OR (LENGTH(?) >= 8 AND SUBSTR(clean_digits(phone), -LENGTH(?)) = ?);""",
                (clean_phone, clean_phone, clean_phone, clean_phone),
            )
            customers = cursor.fetchall()

        if not customers:
            return {
                "status": "not_found",
                "message": (
                    "Não localizamos nenhum cadastro com o telefone ou e-mail informado. "
                    "Por questões de privacidade (LGPD), verifique se o número ou e-mail digitado é exatamente o mesmo utilizado na compra."
                ),
                "orders": [],
            }

        customer_ids = [c["customer_id"] for c in customers]
        primary_customer = customers[0]

        placeholders = ",".join("?" for _ in customer_ids)
        sql = f"""
            SELECT o.order_id, o.customer_id, o.order_date, o.status, o.total_brl, o.payment_method,
                   o.tracking_code, o.estimated_delivery, o.notes
            FROM orders o
            WHERE o.customer_id IN ({placeholders})
        """
        params: List[Any] = list(customer_ids)

        if order_id is not None:
            sql += " AND o.order_id = ?"
            params.append(int(order_id))

        sql += " ORDER BY o.order_date DESC;"
        cursor.execute(sql, params)
        order_rows = cursor.fetchall()

        orders_list = []
        for o in order_rows:
            oid = o["order_id"]
            cursor.execute(
                """SELECT oi.quantity, p.product_id, p.name, p.price_brl, p.trust_status, p.quarantine_reasons
                   FROM order_items oi
                   JOIN products p ON oi.product_id = p.product_id
                   WHERE oi.order_id = ?;""",
                (oid,),
            )
            items_rows = cursor.fetchall()
            items = []
            for it in items_rows:
                item_dict: Dict[str, Any] = {
                    "product_id": it["product_id"],
                    "name": it["name"],
                    "quantity": it["quantity"],
                    "unit_price_catalog_brl": float(it["price_brl"]),
                }
                if it["trust_status"] == "quarantined":
                    item_dict["technical_audit_warning"] = (
                        "Atenção: Este modelo encontra-se em auditoria técnica de lote/especificações pela qualidade. "
                        "Caso o cliente tenha dúvidas sobre as especificações do item, ofereça suporte prioritário da equipe."
                    )
                items.append(item_dict)

            orders_list.append(
                {
                    "order_id": o["order_id"],
                    "order_date": o["order_date"],
                    "status": o["status"],
                    "total_paid_brl": float(o["total_brl"]),
                    "payment_method": o["payment_method"],
                    "tracking_code": o["tracking_code"],
                    "tracking_instructions": (
                        "O rastreamento pode ser consultado diretamente no site dos Correios ou da Jadlog."
                        if o["tracking_code"]
                        else None
                    ),
                    "estimated_delivery": o["estimated_delivery"],
                    "cancellation_or_order_notes": o["notes"],
                    "items": items,
                }
            )

        return {
            "status": "success",
            "customer": {
                "customer_id": primary_customer["customer_id"],
                "name": primary_customer["name"],
                "city": primary_customer["city"],
            },
            "total_orders": len(orders_list),
            "orders": orders_list,
        }
    finally:
        conn.close()
