"""Ferramentas de consulta a políticas da loja (RAG Híbrido) e registro de transbordo humano (`src/tools/policy_tools.py`)."""

from __future__ import annotations

import time
import uuid
from typing import Annotated, Any, Dict, Optional

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from src.data.database import get_connection
from src.rag.retriever import get_policy_retriever
from src.tools.order_tools import _match_identifier_to_row


@tool
def search_store_policies(
    query: str, section_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Consulta o Manual de Políticas e Procedimentos oficial da Empório da Música (PDF).
    Utiliza busca híbrida (BM25 + Vetorial Semântica) para recuperar regras de trocas, garantias,
    prazos, formas de pagamento, parcelamento, frete, LGPD e conduta de atendimento.
    """
    retriever = get_policy_retriever()
    results = retriever.search(
        query=query, top_k=3, section_filter=section_number
    )
    return {
        "status": "success",
        "query": query,
        "results_count": len(results),
        "results": results,
    }


@tool
def register_human_handoff(
    customer_name: str,
    contact_phone_or_email: str,
    reason: str,
    details: str,
    confirmation_factor: Optional[str] = None,
    customer_context: Annotated[
        Optional[Dict[str, Any]], InjectedState("customer_context")
    ] = None,
) -> Dict[str, Any]:
    """
    Registra formalmente um atendimento no banco de dados para transbordo humano / encaminhamento à equipe da loja.
    Utilizado para reclamações (SLA 24h úteis), mediação de garantia junto ao fabricante, trocas complexas,
    pedidos de exclusão de dados sob a LGPD ou dúvidas omissas da gerência.
    Quando há um perfil conectado na sessão (`customer_context`), vincula obrigatoriamente ao titular autenticado.
    Quando em modo Visitante Anônimo, solicitações sensíveis sob a LGPD (ex: exclusão de dados) exigem confirmação
    de dois fatores cadastrais do titular (`contact_phone_or_email` + `confirmation_factor` ou `customer_name` completo).
    """
    # Se houver cliente autenticado na sessão, garantir que o ticket seja vinculado estritamente ao titular da sessão (Anti-Spoofing LGPD)
    if customer_context and customer_context.get("customer_id") is not None:
        session_name = (customer_context.get("name") or "").strip()
        session_phone = (customer_context.get("phone") or "").strip()
        session_email = (customer_context.get("email") or "").strip()

        provided_contact = (contact_phone_or_email or "").strip()
        if provided_contact and provided_contact.lower() not in (
            "não informado",
            "nao informado",
        ):
            if _match_identifier_to_row(provided_contact, customer_context) is None:
                return {
                    "status": "unauthorized_mismatch",
                    "message": (
                        "Por segurança e conformidade com a LGPD, solicitações formais ou pedidos de exclusão de dados "
                        "só podem ser registrados para o próprio titular autenticado nesta sessão do WhatsApp."
                    ),
                }

        provided_name = (customer_name or "").strip()
        if provided_name and provided_name.lower() != "cliente":
            # Permite o nome completo ou o primeiro nome do titular da sessão
            first_name_session = session_name.split()[0].lower() if session_name else ""
            if (
                _match_identifier_to_row(provided_name, customer_context) is None
                and provided_name.lower() != first_name_session
            ):
                return {
                    "status": "unauthorized_mismatch",
                    "message": (
                        "Por segurança e conformidade com a LGPD, solicitações formais ou pedidos de exclusão de dados "
                        "só podem ser registrados para o próprio titular autenticado nesta sessão do WhatsApp."
                    ),
                }

        effective_name = session_name or (customer_name or "Cliente").strip()
        effective_contact = (
            session_phone
            or session_email
            or (contact_phone_or_email or "Não informado").strip()
        )
    else:
        # Visitante Anônimo: verificar se é solicitação sensível de LGPD (ex: exclusão/eliminação de dados)
        combined_reason_details = f"{reason or ''} {details or ''}".lower()
        is_lgpd_request = any(
            kw in combined_reason_details
            for kw in ("lgpd", "exclusão", "exclusao", "excluir", "eliminar", "apagar dados", "dados pessoais")
        )
        if is_lgpd_request:
            conn_check = get_connection()
            try:
                cur_check = conn_check.cursor()
                cur_check.execute("SELECT customer_id, name, phone, email, city FROM customers;")
                all_custs = cur_check.fetchall()
            finally:
                conn_check.close()

            candidate_inputs = [
                v.strip()
                for v in (customer_name, contact_phone_or_email, confirmation_factor)
                if v and v.strip() and v.strip().lower() not in ("cliente", "não informado", "nao informado")
            ]
            verified_row = None
            for r in all_custs:
                matched_types = set()
                for cand in candidate_inputs:
                    mtype = _match_identifier_to_row(cand, r)
                    if mtype:
                        matched_types.add(mtype)
                if len(matched_types) >= 2 and ("email" in matched_types or "phone" in matched_types):
                    verified_row = r
                    break

            if verified_row is None:
                return {
                    "status": "verification_required",
                    "message": (
                        "Por segurança e conformidade com a LGPD (prevenção contra exclusão indevida de cadastros por terceiros), "
                        "solicitações de exclusão ou alteração de dados pessoais em sessões não identificadas exigem a confirmação "
                        "simultânea de dois dados cadastrais do titular (ex: Nome Completo + E-mail ou E-mail + Telefone completo com DDD)."
                    ),
                }
            effective_name = verified_row["name"]
            effective_contact = verified_row["phone"] or verified_row["email"]
        else:
            effective_name = (customer_name or "Cliente").strip()
            effective_contact = (contact_phone_or_email or "Não informado").strip()

    unique_suffix = uuid.uuid4().hex[:6].upper()
    protocol = f"EM-{time.strftime('%Y%m%d')}-{unique_suffix}"

    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """INSERT INTO handoff_tickets (protocol, customer_name, contact, reason, details)
                   VALUES (?, ?, ?, ?, ?);""",
                (
                    protocol,
                    effective_name,
                    effective_contact,
                    (reason or "Atendimento especializado").strip(),
                    (details or "").strip(),
                ),
            )
    finally:
        conn.close()

    return {
        "status": "registered",
        "protocol": protocol,
        "customer_name": effective_name,
        "contact": effective_contact,
        "reason": reason,
        "details": details,
        "sla_hours": "Até 24 horas úteis",
        "official_message": (
            f"Solicitação registrada com sucesso no sistema sob o protocolo {protocol}. "
            f"Nossa equipe responsável entrará em contato através do canal oficial do titular ({effective_contact}) "
            "em até 24 horas úteis (Horário de expediente: Seg a Sex das 09:00 às 18:00 e Sáb das 09:00 às 13:00). "
            "Caso precise de acompanhamento imediato, nosso WhatsApp central é (67) 3321-4500."
        ),
    }
