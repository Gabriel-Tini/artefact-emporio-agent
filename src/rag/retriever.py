"""Motor de Recuperação Híbrida (`src/rag/retriever.py` — BM25 + ChromaDB).

Implementa:
- `tokenize_pt()`: normalização de diacríticos (NFKD sem acento), remoção de pontuações aderidas
  e filtragem de stopwords em português, preservando números e siglas de domínio (`5%`, `30`, `90`, `lgpd`).
- Reciprocal Rank Fusion (RRF) estrito: descarta pontuação para documentos com score BM25 nulo (`<= 0.0`)
  e pondera match léxico exato (`1.5`) com similaridade vetorial (`1.0`).
- Alinhamento dimensional automático no ChromaDB (`embedding_backend` salvo nos metadados da coleção)
  e inicialização singleton protegida por `threading.Lock()`.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi

from src.config import CHROMA_DIR, EMBEDDING_MODEL_NAME, GEMINI_API_KEY
from src.rag.pdf_parser import PolicyChunk, get_hierarchical_policy_chunks

PT_STOPWORDS = {
    "a",
    "as",
    "o",
    "os",
    "um",
    "uma",
    "uns",
    "umas",
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
    "por",
    "para",
    "per",
    "com",
    "sem",
    "sob",
    "sobre",
    "e",
    "ou",
    "mas",
    "se",
    "que",
    "qual",
    "quais",
    "como",
    "quando",
    "onde",
    "ao",
    "aos",
    "pelo",
    "pela",
    "pelos",
    "pelas",
    "meu",
    "minha",
    "meus",
    "minhas",
    "seu",
    "sua",
    "seus",
    "suas",
    "este",
    "esta",
    "isso",
    "aquilo",
    "ser",
    "estar",
    "ter",
    "tiver",
    "foi",
    "sao",
    "eh",
    "acontece",
    "fazer",
    "posso",
    "pode",
    "quero",
    "gostaria",
    "saber",
}


def tokenize_pt(text: str) -> List[str]:
    """Normaliza texto em português para indexação e busca léxica BM25."""
    if not text:
        return []
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(
        c for c in normalized if not unicodedata.combining(c)
    ).lower()
    raw_tokens = re.findall(r"[a-z0-9]+", ascii_text)
    filtered = [
        t
        for t in raw_tokens
        if t not in PT_STOPWORDS and (len(t) > 1 or t.isdigit())
    ]
    return filtered if filtered else raw_tokens


class HybridPolicyRetriever:
    """Retriever Híbrido combinando BM25Okapi + ChromaDB via Reciprocal Rank Fusion (RRF)."""

    def __init__(self) -> None:
        self.chunks: List[PolicyChunk] = get_hierarchical_policy_chunks()
        self.bm25_corpus = [
            tokenize_pt(
                f"{c.section_title} {c.subsection_title} {' '.join(c.keywords)} {c.content}"
            )
            for c in self.chunks
        ]
        self.bm25 = BM25Okapi(self.bm25_corpus)
        self._chroma_collection = None
        self._embeddings_model = None
        self._use_gemini_embeddings = False
        self._init_chroma()

    def _init_chroma(self) -> None:
        """Inicializa a coleção ChromaDB local garantindo consistência dimensional."""
        try:
            import chromadb

            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))

            desired_backend = "default_onnx"
            if GEMINI_API_KEY:
                try:
                    from langchain_google_genai import GoogleGenerativeAIEmbeddings

                    test_emb = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL_NAME)
                    _ = test_emb.embed_query("teste")
                    self._embeddings_model = test_emb
                    self._use_gemini_embeddings = True
                    desired_backend = f"gemini_{EMBEDDING_MODEL_NAME}"
                except Exception:
                    self._embeddings_model = None
                    self._use_gemini_embeddings = False
                    desired_backend = "default_onnx"

            collection = client.get_or_create_collection(
                name="emporio_policies",
                metadata={"embedding_backend": desired_backend},
            )

            col_meta = collection.metadata or {}
            current_backend = col_meta.get("embedding_backend", "unknown")

            if (
                collection.count() != len(self.chunks)
                or current_backend != desired_backend
            ):
                client.delete_collection(name="emporio_policies")
                collection = client.create_collection(
                    name="emporio_policies",
                    metadata={"embedding_backend": desired_backend},
                )
                self._chroma_collection = collection
                self._index_chroma()
            else:
                self._chroma_collection = collection
        except Exception as exc:
            print(
                f"[Aviso RAG] Não foi possível inicializar ChromaDB persistente ({exc}). "
                "Operando com BM25 normalizado."
            )
            self._chroma_collection = None

    def _index_chroma(self) -> None:
        """Indexa os chunks hierárquicos no ChromaDB com metadados completos."""
        if not self._chroma_collection:
            return

        documents = [c.content for c in self.chunks]
        metadatas = [
            {
                "section_id": str(c.section_id),
                "section_title": c.section_title,
                "subsection_id": c.subsection_id,
                "subsection_title": c.subsection_title,
                "page_number": int(c.page_number),
                "keywords": ", ".join(c.keywords),
            }
            for c in self.chunks
        ]
        ids = [c.chunk_id for c in self.chunks]

        if self._use_gemini_embeddings and self._embeddings_model is not None:
            try:
                vectors = self._embeddings_model.embed_documents(documents)
                self._chroma_collection.add(
                    documents=documents,
                    embeddings=vectors,
                    metadatas=metadatas,
                    ids=ids,
                )
                return
            except Exception as exc:
                print(
                    f"[Aviso RAG] Falha ao indexar com Gemini Embeddings ({exc}). Usando ONNX local."
                )
                self._use_gemini_embeddings = False
                self._embeddings_model = None

        self._chroma_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )

    def search(
        self, query: str, top_k: int = 3, section_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Executa busca híbrida ponderada com Reciprocal Rank Fusion (RRF)."""
        sec_str = str(section_filter).strip() if section_filter else None

        # 1. Ranking BM25 (apenas para scores estritamente > 0.0)
        tokenized_query = tokenize_pt(query)
        bm25_scores = (
            self.bm25.get_scores(tokenized_query)
            if tokenized_query
            else [0.0] * len(self.chunks)
        )

        positive_bm25_indices = [
            i
            for i, score in enumerate(bm25_scores)
            if score > 0.0 and (not sec_str or self.chunks[i].section_id == sec_str)
        ]
        ranked_bm25_indices = sorted(
            positive_bm25_indices, key=lambda i: bm25_scores[i], reverse=True
        )

        # 2. Ranking Semântico ChromaDB (com dimensionalidade alinhada e pré-filtro)
        chroma_ids_ranked: List[str] = []
        if self._chroma_collection and self._chroma_collection.count() > 0:
            try:
                where_clause = {"section_id": sec_str} if sec_str else None
                n_res = len(self.chunks)
                if self._use_gemini_embeddings and self._embeddings_model is not None:
                    q_vec = self._embeddings_model.embed_query(query)
                    chroma_results = self._chroma_collection.query(
                        query_embeddings=[q_vec],
                        n_results=n_res,
                        where=where_clause,
                    )
                else:
                    chroma_results = self._chroma_collection.query(
                        query_texts=[query],
                        n_results=n_res,
                        where=where_clause,
                    )
                if (
                    chroma_results
                    and "ids" in chroma_results
                    and chroma_results["ids"]
                ):
                    chroma_ids_ranked = chroma_results["ids"][0]
            except Exception as exc:
                print(f"[Aviso RAG] Erro na consulta vetorial ChromaDB: {exc}")

        # 3. Reciprocal Rank Fusion (RRF) sobre candidatos elegíveis
        candidate_chunks = [
            c for c in self.chunks if not sec_str or c.section_id == sec_str
        ]
        rrf_scores: Dict[str, float] = {c.chunk_id: 0.0 for c in candidate_chunks}
        k_const = 60

        # Peso maior para match léxico exato no BM25 (1.5 vs 1.0)
        for rank, idx in enumerate(ranked_bm25_indices):
            cid = self.chunks[idx].chunk_id
            if cid in rrf_scores:
                rrf_scores[cid] += 1.5 / (k_const + rank + 1)

        for rank, cid in enumerate(chroma_ids_ranked):
            if cid in rrf_scores:
                rrf_scores[cid] += 1.0 / (k_const + rank + 1)

        sorted_chunks = sorted(
            candidate_chunks,
            key=lambda c: (
                rrf_scores.get(c.chunk_id, 0.0),
                bm25_scores[self.chunks.index(c)],
            ),
            reverse=True,
        )

        results = []
        for c in sorted_chunks[:top_k]:
            results.append(
                {
                    "chunk_id": c.chunk_id,
                    "section": f"{c.section_id}. {c.section_title}",
                    "subsection": f"{c.subsection_id} {c.subsection_title}",
                    "page": c.page_number,
                    "score": round(rrf_scores.get(c.chunk_id, 0.0), 4),
                    "content": c.content,
                }
            )

        return results


# Singleton Thread-Safe protegido por threading.Lock()
_global_retriever: Optional[HybridPolicyRetriever] = None
_retriever_lock = threading.Lock()


def get_policy_retriever() -> HybridPolicyRetriever:
    """Retorna a instância singleton thread-safe do `HybridPolicyRetriever`."""
    global _global_retriever
    if _global_retriever is None:
        with _retriever_lock:
            if _global_retriever is None:
                _global_retriever = HybridPolicyRetriever()
    return _global_retriever
