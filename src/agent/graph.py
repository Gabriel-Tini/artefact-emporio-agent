"""Construção do Grafo Agêntico Multi-Estágio com LangGraph (`src/agent/graph.py`).

Fluxo:
1. `context_router`: Injeta horário comercial e perfil do cliente em `state.system_prompt` sem poluir `state.messages`.
2. `assistant_executor`: Modelo Gemini com as 6 ferramentas determinísticas vinculadas (`bind_tools`) e timeout configurado.
3. `tools`: `ToolNode` executando as funções Python determinísticas.
4. `hallucination_grader`: Auditor determinístico contra alucinação de preços/estoques, venda de acessórios
   e itens em quarentena, com laço de autocorreção e substituição in-place por fallback seguro após 2 tentativas.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, Literal, Optional, Sequence

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.state import AgentState
from src.config import DEFAULT_MODEL_NAME, GEMINI_API_KEY
from src.data.database import unaccent_text
from src.tools.catalog_tools import calculate_payment_conditions, search_catalog
from src.tools.order_tools import calculate_shipping, lookup_customer_orders
from src.tools.policy_tools import register_human_handoff, search_store_policies

# Lista de ferramentas oficiais vinculadas ao agente
ALL_TOOLS = [
    search_catalog,
    calculate_payment_conditions,
    calculate_shipping,
    lookup_customer_orders,
    search_store_policies,
    register_human_handoff,
]

# Constantes monetárias oficiais da política da loja (permitidas sem chamada de tool de produto)
POLICY_ALLOWED_AMOUNTS = {"35", "50", "80", "100", "500", "2000"}

# Modelos sabidamente em quarentena técnica
QUARANTINED_MODEL_PATTERNS = [
    "music man bass 1x",
    "ibanez bass 2x",
    "yamaha bass 3x",
    "yamaha kit 1",
    "pearl kit 2",
    "korg synth 1",
    "roland synth 3",
]

SAFE_FALLBACK_MESSAGE = (
    "Peço desculpas, mas não consegui validar todos os dados necessários no sistema com 100% de precisão neste instante. "
    "Para garantir informações exatas conforme o padrão da Empório da Música, por favor reformule sua pergunta "
    "ou solicite o encaminhamento para nossa equipe pelo WhatsApp (67) 3321-4500."
)

_cached_llm_with_tools = None
_cached_api_key = None


def extract_message_text(content: Any) -> str:
    """Extrai o texto limpo de `AIMessage.content` (suporta string direta ou blocos multimodais do Gemini 3+)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()
    return str(content)


def get_llm():
    """Retorna instância singleton do modelo Gemini com ferramentas vinculadas e timeout configurado."""
    global _cached_llm_with_tools, _cached_api_key
    active_key = (
        GEMINI_API_KEY
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    )
    if _cached_llm_with_tools is None or _cached_api_key != active_key:
        llm_kwargs: Dict[str, Any] = {
            "model": DEFAULT_MODEL_NAME,
            "google_api_key": active_key,
            "timeout": 30.0,
            "max_retries": 2,
        }
        # Modelos da família Gemini 3.x utilizam sampling padrão fixo no SDK
        if not DEFAULT_MODEL_NAME.startswith("gemini-3"):
            llm_kwargs["temperature"] = 0.2

        llm = ChatGoogleGenerativeAI(**llm_kwargs)
        _cached_llm_with_tools = llm.bind_tools(ALL_TOOLS)
        _cached_api_key = active_key
    return _cached_llm_with_tools


# --- NÓS DO GRAFO ---


def context_router(state: AgentState) -> Dict[str, Any]:
    """
    Nó 1: Roteador e Injeção de Contexto.
    Constrói o `system_prompt` enriquecido sem poluir a lista `state.messages`.
    """
    now = datetime.now()
    weekday = now.weekday()  # 0 = Seg, 5 = Sáb, 6 = Dom
    hour = now.hour

    is_open = False
    if weekday < 5 and (9 <= hour < 18):
        is_open = True
    elif weekday == 5 and (9 <= hour < 13):
        is_open = True

    status_str = (
        "Aberto (Horário de Expediente Normal)"
        if is_open
        else "Fechado (Fora do Expediente - Informar horário de retorno)"
    )

    customer_info_str = "Nenhum cliente pré-autenticado na sessão."
    if state.customer_context:
        ctx = state.customer_context
        customer_info_str = (
            f"Cliente conectado no WhatsApp: {ctx.get('name')} | "
            f"Telefone: {ctx.get('phone')} | E-mail: {ctx.get('email')} | Cidade: {ctx.get('city')}"
        )

    context_note = (
        f"\n[SISTEMA - CONTEXTO ATUAL DA SESSÃO]\n"
        f"- Data/Hora da Loja: {now.strftime('%d/%m/%Y %H:%M')}\n"
        f"- Status de Funcionamento: {status_str}\n"
        f"- Perfil Conectado: {customer_info_str}\n"
    )

    full_system_text = SYSTEM_PROMPT + context_note

    return {
        "system_prompt": full_system_text,
        "business_hours_status": status_str,
    }


def assistant_executor(state: AgentState) -> Dict[str, Any]:
    """
    Nó 2: Executor Principal com chamada a ferramentas.
    Garante que `SystemMessage` seja sempre a primeira mensagem (índice 0) enviada ao modelo.
    """
    llm_with_tools = get_llm()

    sys_content = state.system_prompt or SYSTEM_PROMPT
    if state.grader_feedback:
        sys_content += (
            f"\n\n[ALERTA DE AUDITORIA INTERNA - CORREÇÃO OBRIGATÓRIA]:\n"
            f"{state.grader_feedback}\n"
            "Reformule sua resposta imediatamente cumprindo estritamente as diretrizes da loja."
        )

    conversation_msgs = [
        m for m in state.messages if not isinstance(m, SystemMessage)
    ]
    input_messages = [SystemMessage(content=sys_content)] + conversation_msgs

    response = llm_with_tools.invoke(input_messages)

    new_tools = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            new_tools.append(tc.get("name", "tool"))

    return {
        "messages": [response],
        "tools_called": new_tools,
        "grader_feedback": None,
    }


def deterministic_anti_hallucination_check(
    last_ai_message: str,
    tools_called: list,
    all_messages: Sequence[BaseMessage] = (),
) -> str:
    """
    Checagem de conformidade determinística:
    1. Impede citação de preços de produtos sem chamada de ferramenta na conversa (permitindo valores de política e valores ditos pelo usuário).
    2. Impede confirmação de venda de acessórios avulsos.
    3. Impede confirmação de estoque/venda de produtos em quarentena técnica.
    """
    text_norm = unaccent_text(last_ai_message)

    has_any_tool_in_history = bool(tools_called) or any(
        isinstance(m, ToolMessage) for m in all_messages
    )

    user_numbers = set()
    for m in all_messages:
        if isinstance(m, HumanMessage) and m.content:
            for num in re.findall(r"\d+", str(m.content).replace(".", "")):
                user_numbers.add(num)

    # 1. Checar menção a preços em R$ sem consulta a ferramentas
    if not has_any_tool_in_history:
        currency_matches = re.findall(r"r\$\s*([\d\.]+)", text_norm)
        for raw_val in currency_matches:
            clean_val = raw_val.replace(".", "").strip()
            if (
                clean_val
                and clean_val not in POLICY_ALLOWED_AMOUNTS
                and clean_val not in user_numbers
            ):
                return (
                    f"FAIL: Você mencionou o valor monetário R$ {raw_val} sem ter consultado o catálogo "
                    "ou as ferramentas do sistema. NUNCA invente preços; chame search_catalog ou calculate_payment_conditions."
                )

    # 2. Checar se tentou confirmar venda de acessórios avulsos sem informar a restrição de escopo
    accessory_terms = [
        "palheta avulsa",
        "palhetas avulsas",
        "jogo de cordas",
        "encordoamento",
        "cabo p10",
        "pedal de efeito",
        "pedal de distorcao",
        "amplificador",
    ]
    refusal_markers = [
        "nao comercializa",
        "nao vendemos",
        "nao trabalhamos",
        "exclusivamente com instrumentos",
        "apenas instrumentos",
        "somente instrumentos",
        "lojas parceiras",
        "infelizmente nao",
    ]
    for acc in accessory_terms:
        if acc in text_norm:
            if not any(ref in text_norm for ref in refusal_markers):
                return (
                    f"FAIL: A loja NÃO comercializa '{acc}'. Você deve informar claramente que a Empório da Música "
                    "trabalha exclusivamente com instrumentos musicais completos."
                )

    # 3. Checar se confirmou disponibilidade/venda de item em quarentena técnica
    quarantine_refusals = [
        "indisponivel",
        "auditoria",
        "quarentena",
        "nao temos",
        "bloqueado",
        "verificacao",
    ]
    for q_pat in QUARANTINED_MODEL_PATTERNS:
        if q_pat in text_norm:
            if not any(q_ref in text_norm for q_ref in quarantine_refusals):
                return (
                    f"FAIL: O modelo '{q_pat}' encontra-se bloqueado em quarentena técnica e não pode ser "
                    "apresentado como disponível para venda."
                )

    return "PASS"


def hallucination_grader(state: AgentState) -> Dict[str, Any]:
    """
    Nó 3: Grader / Auditor Anti-Alucinação.
    Valida a conformidade da resposta gerada. Caso exceda o limite de retentativas (2),
    substitui in-place a mensagem reprovada por `SAFE_FALLBACK_MESSAGE`, impedindo vazamento ao cliente.
    """
    last_msg: Optional[AIMessage] = None
    for m in reversed(state.messages):
        if isinstance(m, AIMessage) and not (
            hasattr(m, "tool_calls") and m.tool_calls
        ):
            last_msg = m
            break

    last_text = extract_message_text(last_msg.content) if last_msg else ""
    if not last_msg or not last_text:
        return {"grader_feedback": None}

    det_result = deterministic_anti_hallucination_check(
        last_text,
        state.tools_called,
        state.messages,
    )

    if det_result.startswith("FAIL"):
        new_retry = state.retry_count + 1
        if new_retry >= 2:
            # Substituir in-place (mesmo ID) a mensagem reprovada para jamais vazar alucinação ao cliente
            safe_replacement = AIMessage(
                content=SAFE_FALLBACK_MESSAGE,
                id=last_msg.id,
            )
            return {
                "messages": [safe_replacement],
                "grader_feedback": None,
                "retry_count": new_retry,
            }
        return {
            "grader_feedback": det_result,
            "retry_count": new_retry,
        }

    return {"grader_feedback": None}


def route_after_executor(state: AgentState) -> Literal["tools", "grader"]:
    """Decide se o assistente solicitou chamada de ferramenta ou gerou resposta final."""
    last_msg = state.messages[-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return "grader"


def route_after_grader(state: AgentState) -> Literal["executor", "__end__"]:
    """Decide se a resposta foi aprovada ou necessita de autocorreção."""
    if state.grader_feedback and state.retry_count < 2:
        return "executor"
    return END


def create_customer_service_graph():
    """Constrói e compila o `StateGraph` completo de atendimento."""
    workflow = StateGraph(AgentState)

    workflow.add_node("router", context_router)
    workflow.add_node("executor", assistant_executor)
    workflow.add_node("tools", ToolNode(ALL_TOOLS))
    workflow.add_node("grader", hallucination_grader)

    workflow.add_edge(START, "router")
    workflow.add_edge("router", "executor")

    workflow.add_conditional_edges(
        "executor",
        route_after_executor,
        {
            "tools": "tools",
            "grader": "grader",
        },
    )
    workflow.add_edge("tools", "executor")

    workflow.add_conditional_edges(
        "grader",
        route_after_grader,
        {
            "executor": "executor",
            END: END,
        },
    )

    return workflow.compile()
