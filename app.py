"""Aplicação Chainlit — Simulador de Atendimento WhatsApp da Empório da Música (`app.py`)."""

from __future__ import annotations

from typing import Any, Dict, List

import chainlit as cl
from chainlit.input_widget import Select
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langgraph.graph.message import add_messages

from src.agent.graph import create_customer_service_graph, extract_message_text
from src.agent.state import AgentState
from src.config import DB_PATH, STORE_INFO
from src.data.database import get_connection
from src.data.ingest import run_ingestion


def format_customer_option(c: Dict[str, Any]) -> str:
    """Formata de forma única a opção de cliente para o seletor lateral."""
    return f"[#{c['customer_id']}] {c['name']} ({c['phone']}) - {c['city']}"


def load_sample_customers() -> List[Dict[str, Any]]:
    """Carrega lista de clientes de exemplo para simulação no Chainlit (inicializa o banco caso ausente)."""
    if not DB_PATH.exists():
        run_ingestion()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT customer_id, name, phone, email, city FROM customers ORDER BY customer_id ASC LIMIT 15;"
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@cl.on_chat_start
async def on_chat_start():
    """Inicialização da sessão de atendimento."""
    graph = create_customer_service_graph()
    cl.user_session.set("graph", graph)
    cl.user_session.set("messages", [])
    cl.user_session.set("customer_context", None)

    sample_customers = load_sample_customers()
    cl.user_session.set("sample_customers", sample_customers)

    customer_options = ["Visitante Anônimo (Não Identificado)"] + [
        format_customer_option(c) for c in sample_customers
    ]

    await cl.ChatSettings(
        [
            Select(
                id="simulated_customer",
                label="Simular Perfil de WhatsApp Conectado",
                values=customer_options,
                initial_index=0,
                description="Selecione um cliente para simular a identificação pelo número de WhatsApp.",
            )
        ]
    ).send()

    welcome_content = f"""👋 **Bem-vindo à Central de Atendimento da {STORE_INFO['name']}!**
*Sua música começa aqui.* 🎸🥁🎹

📍 **Endereço:** {STORE_INFO['address']}  
⏰ **Horário de Atendimento:** Segunda a Sexta (09h às 18h) | Sábado (09h às 13h)  
📞 **Telefone/WhatsApp Executivo da Empresa:** {STORE_INFO['phone']} | 📱 **Central de Atendimento pelo WhatsApp:** {STORE_INFO['whatsapp']}  
✉️ **E-mail Oficial:** {STORE_INFO['email']}

> ℹ️ **Aviso de Transparência:** Você está no canal oficial de atendimento virtual da **{STORE_INFO['legal_name']}** (CNPJ `{STORE_INFO['cnpj']}`). Para sua segurança, nossos únicos números oficiais são o Telefone/WhatsApp Executivo da loja física (`{STORE_INFO['phone']}`) e esta Central de Atendimento Remoto via WhatsApp (`{STORE_INFO['whatsapp']}`). Todas as informações de catálogo, estoque, pagamentos e pedidos são consultadas em tempo real em nosso sistema sob proteção da LGPD.

Como posso ajudar você hoje?
"""
    await cl.Message(content=welcome_content).send()


@cl.on_settings_update
async def setup_agent(settings):
    """Atualiza o perfil do cliente simulado com correspondência exata e isolamento de sessão LGPD."""
    selected_val = settings.get("simulated_customer")
    sample_customers = cl.user_session.get("sample_customers", [])

    # Limpar o histórico de mensagens ao trocar de perfil para impedir vazamento de dados entre sessões (LGPD)
    cl.user_session.set("messages", [])

    if selected_val and selected_val != "Visitante Anônimo (Não Identificado)":
        for c in sample_customers:
            if format_customer_option(c) == selected_val:
                cl.user_session.set("customer_context", c)
                await cl.Message(
                    content=(
                        f"📱 **Simulador WhatsApp**: Número conectado alterado para "
                        f"`{c['name']}` ({c['phone']}) - {c['city']}. "
                        "*(Histórico anterior isolado por proteção LGPD)*."
                    )
                ).send()
                return

    cl.user_session.set("customer_context", None)
    await cl.Message(
        content="📱 **Simulador WhatsApp**: Sessão alterada para **Visitante Anônimo**. *(Histórico anterior isolado por proteção LGPD)*."
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Processamento de mensagens dos clientes via LangGraph com preservação de estado e rollback."""
    graph = cl.user_session.get("graph")
    stored_messages: List[BaseMessage] = list(
        cl.user_session.get("messages", [])
    )
    customer_context = cl.user_session.get("customer_context")

    user_input = message.content
    working_messages: List[BaseMessage] = add_messages(
        stored_messages, [HumanMessage(content=user_input)]
    )

    initial_state = AgentState(
        messages=working_messages,
        customer_context=customer_context,
        tools_called=[],
        grader_feedback=None,
        retry_count=0,
    )

    try:
        async for event in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue

                if "messages" in node_output and node_output["messages"]:
                    working_messages = add_messages(
                        working_messages, node_output["messages"]
                    )

                if node_name == "tools":
                    tool_msgs = node_output.get("messages", [])
                    for tm in tool_msgs:
                        if isinstance(tm, ToolMessage):
                            async with cl.Step(
                                name=f"🛠️ Ferramenta: {tm.name}", type="tool"
                            ) as step:
                                step.output = str(tm.content)[:600] + (
                                    "..."
                                    if len(str(tm.content)) > 600
                                    else ""
                                )

                elif node_name == "grader":
                    feedback = node_output.get("grader_feedback")
                    if feedback:
                        async with cl.Step(
                            name="🛡️ Auditor Anti-Alucinação", type="system"
                        ) as step:
                            step.output = (
                                f"Aviso de correção disparado: {feedback}"
                            )

        final_output = ""
        for m in reversed(working_messages):
            if isinstance(m, AIMessage) and not (
                hasattr(m, "tool_calls") and m.tool_calls
            ):
                final_output = extract_message_text(m.content)
                break

        if final_output:
            cl.user_session.set("messages", working_messages)
            await cl.Message(content=final_output).send()
        else:
            fallback = (
                "Desculpe, tive uma oscilação na consulta. Pode repetir sua dúvida?"
            )
            await cl.Message(content=fallback).send()

    except Exception as exc:
        error_msg = f"⚠️ Ocorreu um erro no processamento: {str(exc)}"
        await cl.Message(content=error_msg).send()
