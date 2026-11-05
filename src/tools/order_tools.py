"""Ferramentas determinísticas de cálculo de frete e consulta segura de pedidos sob LGPD (`src/tools/order_tools.py`)."""

from __future__ import annotations

import re
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

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


def _match_identifier_to_row(ident_str: str, row: Any) -> Optional[str]:
    """
    Verifica se `ident_str` corresponde a um fator cadastral do registro `row` (email, phone ou name).
    Retorna o tipo de fator ('email', 'phone', 'name') se houver correspondência estrita, ou None.
    """
    val = (ident_str or "").strip()
    if not val:
        return None

    # 1. Verificação por E-mail exato
    if "@" in val:
        if val.lower() == (row["email"] or "").strip().lower():
            return "email"
        return None

    # 2. Verificação por Telefone Completo com DDD (mínimo 10 dígitos numéricos)
    digits = re.sub(r"\D", "", val)
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) >= 10:
        row_digits = re.sub(r"\D", "", row["phone"] or "")
        if row_digits.startswith("55") and len(row_digits) in (12, 13):
            row_digits = row_digits[2:]
        if row_digits and digits == row_digits:
            return "phone"
        return None

    # Se possui dígitos mas menos de 10 (ex: número parcial sem DDD), rejeitar imediatamente
    if len(digits) >= 4:
        return None

    # 3. Verificação por Nome Completo exato (sem acentos e insensível a maiúsculas/espaços extras)
    val_norm = " ".join(unaccent_text(val).split())
    row_name_norm = " ".join(unaccent_text((row["name"] or "").strip()).split())
    if val_norm and row_name_norm and len(val_norm.split()) >= 2:
        if val_norm == row_name_norm:
            return "name"

    return None


@tool
def lookup_customer_orders(
    identifier: Optional[str] = None,
    confirmation_factor: Optional[str] = None,
    order_id: Optional[int] = None,
    customer_context: Annotated[
        Optional[Dict[str, Any]], InjectedState("customer_context")
    ] = None,
) -> Dict[str, Any]:
    """
    Consulta o histórico de pedidos e status de entrega de um cliente sob proteção estrita da LGPD (Zero-Trust).
    - Se a sessão já possui um cliente autenticado no WhatsApp (`customer_context`), a consulta é estritamente
      travada ao titular da sessão (bloqueia imediatamente com `unauthorized_mismatch` qualquer tentativa de
      consultar e-mail, telefone ou nome de terceiros).
    - Se o usuário for um Visitante Anônimo (não pré-autenticado pelo WhatsApp), exige obrigatoriamente DOIS
      fatores cadastrais distintos do mesmo titular (`identifier` + `confirmation_factor`, ex: E-mail + Telefone
      cadastrado ou E-mail/Telefone + Nome Completo).
    """
    ident = (identifier or "").strip()
    conf = (confirmation_factor or "").strip()

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # ======================================================================
        # CASO 1: SESSÃO AUTENTICADA NO WHATSAPP (Strict Session Ownership Check)
        # ======================================================================
        if customer_context and customer_context.get("customer_id") is not None:
            session_cid = int(customer_context["customer_id"])
            cursor.execute(
                "SELECT customer_id, name, phone, email, city FROM customers WHERE customer_id = ?;",
                (session_cid,),
            )
            session_row = cursor.fetchone()
            if not session_row:
                return {
                    "status": "unauthorized_mismatch",
                    "message": (
                        "Por segurança e conformidade com a LGPD, só posso consultar pedidos vinculados ao titular deste número de WhatsApp."
                    ),
                    "orders": [],
                }

            # Se o LLM passou identifier ou confirmation_factor, validar se pertencem estritamente ao titular da sessão
            for provided_val in (ident, conf):
                if not provided_val:
                    continue
                matched_factor = _match_identifier_to_row(provided_val, session_row)
                if matched_factor is None:
                    # Bloqueio determinístico imediato ANTES de tocar na tabela orders (Anti-IDOR / Anti-BOLA)
                    return {
                        "status": "unauthorized_mismatch",
                        "message": (
                            "Por segurança e conformidade com a LGPD, só posso consultar pedidos vinculados ao titular deste número de WhatsApp."
                        ),
                        "security_instruction": (
                            "BLOQUEIO LGPD (IDOR/BOLA PREVENTED): O identificador informado NÃO pertence ao titular "
                            "conectado nesta sessão do WhatsApp. NENHUM dado de terceiro foi carregado. "
                            "Informe ao usuário que, por segurança e conformidade com a LGPD, você só pode consultar "
                            "pedidos vinculados ao titular deste número de WhatsApp e NUNCA revele dados de terceiros."
                        ),
                        "orders": [],
                    }

            authorized_customers = [session_row]

        # ======================================================================
        # CASO 2: VISITANTE ANÔNIMO (2-Factor Knowledge Check Obrigatório)
        # ======================================================================
        else:
            if not ident:
                return {
                    "status": "verification_required",
                    "message": (
                        "Como você está falando de um número ainda não identificado na sessão, por segurança e conformidade "
                        "com a LGPD precisamos confirmar dois dados cadastrais da sua compra: por favor, informe seu "
                        "**e-mail cadastrado** junto com seu **telefone completo (com DDD)** ou **nome completo**."
                    ),
                    "orders": [],
                }

            # Validar formato mínimo se o identificador ou fator de confirmação parecer telefone parcial sem DDD (< 10 dígitos)
            for candidate_val in (ident, conf):
                if candidate_val and "@" not in candidate_val:
                    clean_digits_cand = re.sub(r"\D", "", candidate_val)
                    if clean_digits_cand.startswith("55") and len(clean_digits_cand) in (12, 13):
                        clean_digits_cand = clean_digits_cand[2:]
                    if clean_digits_cand and len(clean_digits_cand) < 10:
                        return {
                            "status": "invalid_identifier",
                            "message": (
                                "Por proteção de dados (LGPD), não realizamos buscas com números de telefone parciais ou sem DDD. "
                                "Para visitantes não identificados automaticamente, informe seu telefone completo com DDD (mínimo 10 dígitos) "
                                "combinado com seu e-mail ou nome completo cadastrado."
                            ),
                            "orders": [],
                        }

            if not conf:
                return {
                    "status": "verification_required",
                    "message": (
                        "Por segurança e conformidade com a LGPD (prevenção contra acesso não autorizado), apenas um "
                        "identificador isolado não é suficiente em sessões anônimas. Por favor, confirme também um "
                        "**segundo dado cadastral** do titular (ex: seu **telefone completo com DDD** ou **nome completo** "
                        "vinculado ao e-mail, ou **e-mail + telefone**)."
                    ),
                    "orders": [],
                }

            cursor.execute(
                "SELECT customer_id, name, phone, email, city FROM customers;"
            )
            all_customers = cursor.fetchall()

            matched_customers = []
            for row in all_customers:
                f1 = _match_identifier_to_row(ident, row)
                f2 = _match_identifier_to_row(conf, row)
                # Exige que ambos os fatores façam match no MESMO customer_id e sejam fatores distintos
                # (ex: email + phone, email + name, ou phone + name), sendo pelo menos um deles email ou phone
                if (
                    f1 is not None
                    and f2 is not None
                    and f1 != f2
                    and ("email" in (f1, f2) or "phone" in (f1, f2))
                ):
                    matched_customers.append(row)

            if not matched_customers:
                return {
                    "status": "not_found_or_mismatch",
                    "message": (
                        "Não foi possível validar a titularidade com a combinação de dados informada. "
                        "Por segurança e conformidade com a LGPD, verifique se o e-mail, telefone completo (com DDD) "
                        "e nome completo correspondem exatamente ao mesmo cadastro utilizado na compra."
                    ),
                    "orders": [],
                }

            authorized_customers = matched_customers

        # ======================================================================
        # CONSULTA DE PEDIDOS (Somente após autorização determinística)
        # ======================================================================
        customer_ids = [c["customer_id"] for c in authorized_customers]
        primary_customer = authorized_customers[0]

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

