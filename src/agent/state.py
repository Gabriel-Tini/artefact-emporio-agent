"""Estado tipado para o grafo multi-estágio do LangGraph (`src/agent/state.py`).

Separa `system_prompt` de `messages` para garantir que o redutor `add_messages`
nunca desloque a `SystemMessage` da posição raiz (índice 0) em conversas multi-turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, Optional, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def merge_traces(existing: List[str], new_traces: List[str]) -> List[str]:
    """Combina listas de rastreamento de ferramentas chamadas no turno."""
    combined = list(existing or [])
    for t in new_traces or []:
        if t not in combined:
            combined.append(t)
    return combined


@dataclass
class AgentState:
    """Estado de execução do Grafo de Atendimento da Empório da Música."""

    messages: Annotated[Sequence[BaseMessage], add_messages] = field(
        default_factory=list
    )
    system_prompt: str = ""
    customer_context: Optional[Dict[str, Any]] = None
    business_hours_status: str = "Aberto (Horário de Expediente)"
    tools_called: Annotated[List[str], merge_traces] = field(default_factory=list)
    grader_feedback: Optional[str] = None
    retry_count: int = 0
