"""Módulo de Orquestração Agêntica Multi-Estágio com LangGraph (`src/agent/`)."""

from src.agent.graph import (
    ALL_TOOLS,
    SAFE_FALLBACK_MESSAGE,
    assistant_executor,
    context_router,
    create_customer_service_graph,
    deterministic_anti_hallucination_check,
    extract_message_text,
    hallucination_grader,
)
from src.agent.prompts import GRADER_SYSTEM_PROMPT, SYSTEM_PROMPT
from src.agent.state import AgentState, merge_traces

__all__ = [
    "ALL_TOOLS",
    "SAFE_FALLBACK_MESSAGE",
    "AgentState",
    "merge_traces",
    "SYSTEM_PROMPT",
    "GRADER_SYSTEM_PROMPT",
    "context_router",
    "assistant_executor",
    "hallucination_grader",
    "deterministic_anti_hallucination_check",
    "extract_message_text",
    "create_customer_service_graph",
]
