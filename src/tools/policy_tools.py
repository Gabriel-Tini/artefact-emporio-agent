"""Ferramentas de consulta a políticas da loja (RAG Híbrido) e registro de transbordo humano (`src/tools/policy_tools.py`)."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from langchain_core.tools import tool

from src.data.database import get_connection
from src.rag.retriever import get_policy_retriever


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
) -> Dict[str, Any]:
    """
    Registra formalmente um atendimento no banco de dados para transbordo humano / encaminhamento à equipe da loja.
    Utilizado para reclamações (SLA 24h úteis), mediação de garantia junto ao fabricante, trocas complexas,
    pedidos de exclusão de dados sob a LGPD ou dúvidas omissas da gerência.
    """
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
                    (customer_name or "Cliente").strip(),
                    (contact_phone_or_email or "Não informado").strip(),
                    (reason or "Atendimento especializado").strip(),
                    (details or "").strip(),
                ),
            )
    finally:
        conn.close()

    return {
        "status": "registered",
        "protocol": protocol,
        "customer_name": customer_name,
        "contact": contact_phone_or_email,
        "reason": reason,
        "details": details,
        "sla_hours": "Até 24 horas úteis",
        "official_message": (
            f"Solicitação registrada com sucesso no sistema sob o protocolo {protocol}. "
            f"Nossa equipe responsável entrará em contato através do canal informado ({contact_phone_or_email}) "
            "em até 24 horas úteis (Horário de expediente: Seg a Sex das 09:00 às 18:00 e Sáb das 09:00 às 13:00). "
            "Caso precise de acompanhamento imediato, nosso WhatsApp central é (67) 3321-4500."
        ),
    }
