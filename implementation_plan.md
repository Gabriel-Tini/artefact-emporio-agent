# Plano de Arquitetura e Implementação: Agente de Atendimento "Empório da Música"

> [!IMPORTANT]
> **Alinhamento Concluído (`/grill-me`)**: Este plano consolida todas as 10 decisões arquiteturais, de engenharia de dados e de controle de fluxo agêntico tomadas durante nossa entrevista técnica. Nenhum arquivo de código no repositório foi gerado ainda, aguardando sua aprovação final para iniciarmos a construção.

---

## 1. Visão Geral e Diagnóstico dos Dados

O objetivo é construir o protótipo de produção do **Assistente Virtual de Atendimento via WhatsApp da Empório da Música** (Campo Grande - MS), operando como um **RAG Agêntico de Precisão Absoluta (Zero Hallucination)** com capacidade de transbordo humano (*Human Handoff*).

### 1.1 Descobertas Críticas na Auditoria Exploratória dos Dados (`data/`)
Durante a inspeção dos arquivos `.csv` e do manual `políticas_da_loja.pdf`, identificamos armadilhas intencionais de engenharia de dados que corromperiam um agente ingênuo:

1. **Corrupção Grave de Catálogo (`products.csv` - IDs 135 a 144):**
   - **Baixos (`category_id = 2`, IDs 135–138):** O campo `name` indica uma marca/modelo (ex: `ID 135: Music Man Bass 1X`, `ID 137: Yamaha Bass 3X`), enquanto a coluna `description` descreve outro instrumento completamente distinto (ex: *"Contrabaixo elétrico Fender Jazz Bass..."* ou *"Contrabaixo ativo de 5 cordas Ibanez..."*) e o JSON `specs` contradiz ambos (ex: `strings: "4"` para um baixo descrito como 5 cordas).
   - **Baterias (`category_id = 3`, IDs 139–141):** Nomes indicam `Yamaha Kit 1` e `Pearl Kit 2`, mas as descrições citam `Pearl Export` e `Tama 100% Birch`, e os `specs` fixam `shells: "Maple"` para todos.
   - **Teclados (`category_id = 4`, IDs 142–144):** Nomes indicam `Korg Synth 1 Pro` (`R$ 1.127`), mas a descrição afirma ser um *"Sintetizador workstation Roland com 88 teclas pesadas"* e o `specs` diz `keys: "61"`.
2. **Categorias Vazias no Catálogo:**
   - As categorias `6` (*Instrumentos de Sopro - Madeiras*), `7` (*Instrumentos de Sopro - Metais*) e `8` (*Cordas Orquestrais*) existem em `categories.csv`, mas possuem **0 produtos** em `products.csv`.
3. **Integridade Histórica vs. Catálogo Atual:**
   - Existem pedidos históricos (`orders.csv` / `order_items.csv`) que referenciam itens hoje em status `discontinued` (`ID 85`, `ID 130`), fora de estoque (`ID 96`, `stock = 0`) ou que entraram em quarentena (`ID 135` no pedido `order_id = 10`).
4. **Regras de Negócio Estritas no PDF (`políticas_da_loja.pdf`):**
   - **Não-cumulatividade do PIX:** Desconto de 5% no PIX à vista **não** acumula com promoções ativas (`is_active = 1` em `promotions.csv`).
   - **Escalonamento de Parcelas no Cartão (Sem Juros):**
     - Até `3x`: sem parcela mínima (exceto compras abaixo de `R$ 50,00`).
     - `4x` a `6x`: parcela mínima de `R$ 80,00`.
     - `7x` a `12x`: parcela mínima de `R$ 100,00`.
     - Combinação de pagamentos (ex: PIX + Cartão) permitida para compras acima de `R$ 2.000,00`.
   - **Exclusividade de Escopo:** A loja **não comercializa acessórios** (cordas avulsas, palhetas, cabos, cases, pedais, amplificadores).

---

## 2. Arquitetura do Sistema

```mermaid
flowchart TD
    subgraph UI["Interface Chainlit (Simulador WhatsApp)"]
        Chat["Chat do Cliente + Seletor de Perfil WhatsApp"]
        Steps["cl.Step (Rastreabilidade de Tools, Quarentena e RAG)"]
    end

    subgraph DataLayer["Camada de Dados & Ingestão (ETL + Audit)"]
        CSV["Arquivos CSV Brutos"] --> Audit["Pipeline de Auditoria e Sanitização"]
        Audit -->|Aprovados| SQLite[("SQLite (emporio.db)\nTabelas Confiáveis")]
        Audit -->|Corrompidos IDs 135-144| Quarantine[("Tabela product_quarantine\n+ audit_report.json")]
        PDF["políticas_da_loja.pdf"] --> Chunking["Chunking Hierárquico por Seção"]
        Chunking --> Chroma[("ChromaDB Local\n(Gemini Embeddings)")]
        Chunking --> BM25["Índice BM25 em Memória"]
    end

    subgraph LangGraph["Orquestração Agêntica (LangGraph + LangChain + Gemini)"]
        Entry(["Mensagem do Usuário"]) --> Router["1. Nó Router / Intent & Guardrail\n(Escopo, Horário, Identificação)"]
        Router -->|Consulta / Atendimento| Executor["2. Nó Agente Executor\n(Gemini + Tool Calling)"]
        Router -->|Reclamação / Exceção| Handoff["4. Nó Human Handoff\n(Protocolo + Ticket 24h úteis)"]
        
        Executor <-->|Tools Determinísticas| Tools["Suite de Tools Python\n(Catálogo, Preço/PIX, Pedidos, RAG Híbrido)"]
        Tools --> SQLite
        Tools --> Quarantine
        Tools --> Chroma
        Tools --> BM25

        Executor --> Grader["3. Nó Auditor / Hallucination Grader\n(Valida Preços, Estoque, Regras e Quarentena)"]
        Grader -->|Aprovado| Output(["Resposta Final ao Cliente"])
        Grader -->|Violação Detectada\n(Max 2 Retries)| Executor
    end

    Chat <--> Entry
    Output --> Chat
    Handoff --> Chat
```

---

## 3. Detalhamento dos Módulos e Decisões Técnicas

### 3.1 Engenharia de Dados: Auditoria, Sanitização e Quarentena (`src/data/`)
1. **Validador Determinístico de Integridade (`pipeline.py`):**
   - Inspeciona cruzamento de Marcas (`Yamaha`, `Fender`, `Gibson`, `Ibanez`, `PRS`, `Music Man`, `Pearl`, `Tama`, `Korg`, `Roland`, `Nord`, `Tagima`, `Giannini`, `Rozini`, `Crafter`, `Martin`, `Taylor`, `Takamine`, `Shelby`, `Kala`, `Ohana`, `Kalani`) e especificações (`strings`, `keys`, `shells`) entre `name`, `description` e `specs`.
   - **Política de Quarentena:** Produtos com conflito estrutural irreconciliável (como os IDs `135` a `144`) são marcados com `trust_status = 'quarantined'` e movidos/registrados na tabela `quarantined_products` com o motivo exato da reprovação (ex: `BRAND_MISMATCH: Name='Korg Synth 1 Pro' vs Desc='Roland 88 teclas'`).
   - **Visão Segura do Catálogo:** As ferramentas de busca e recomendação consultam exclusivamente produtos com `trust_status = 'approved'`. Se o cliente perguntar especificamente por um modelo ou categoria afetada (ex: Baixos, Baterias, Teclados), a ferramenta informa ao agente que o item encontra-se bloqueado para auditoria técnica de estoque/cadastro, impedindo qualquer venda com informação enganosa (Seção 7.1 do PDF).
   - **Preservação de Pedidos Históricos:** A consulta de pedidos (`get_customer_orders`) faz `LEFT JOIN` incluindo o catálogo completo para não quebrar o histórico do pedido `order_id = 10` (`product_id = 135`), sinalizando a nota de auditoria interna sem expor erro técnico ao cliente.
   - **Artefato de Governança:** Gera automaticamente `data/processed/data_quality_report.json` e `data/processed/emporio.db`.

### 3.2 RAG Híbrido Estruturado sobre `políticas_da_loja.pdf` (`src/rag/`)
1. **Extração e Chunking Hierárquico Semântico:**
   - Extração limpa do PDF estruturando-o pelas **10 Seções e Subseções oficiais** (`1. Sobre a Empório`, `2. Horário`, `3. Formas de Pagamento`, `4. Trocas e Devoluções`, `5. Frete e Entregas`, `6. Promoções`, `7. Atendimento WhatsApp`, `8. Garantia`, `9. LGPD`, `10. Disposições Finais`).
   - Cada chunk preserva no cabeçalho contextual e nos metadados: `section_id`, `section_title`, `subsection_title`, `page_number` e `keywords`.
2. **Motor de Busca Híbrida (`EnsembleRetriever`):**
   - **Busca Densa (Semântica):** `Chroma` persistido em `data/processed/chroma_db` utilizando `GoogleGenerativeAIEmbeddings` (`models/gemini-embedding-001`).
   - **Busca Esparsa (Léxica):** `BM25Retriever` (`rank_bm25`) calibrado para termos exatos (`PIX`, `5%`, `Jadlog`, `SEDEX`, `PAC`, `boquilha`, `7 dias`, `30 dias`, `90 dias`, `LGPD`, `Campo Grande`, `R$ 500,00`).
   - Fusão via **Reciprocal Rank Fusion (RRF)** (`weights=[0.5, 0.5]`).

### 3.3 Suite de Ferramentas Determinísticas (`src/tools/`)
Proibição total de SQL livre gerado pelo LLM. Todas as consultas passam por funções Python tipadas com schemas Pydantic:
1. `search_catalog(query, category_name, max_price, strings_type, has_electronics, only_in_stock)`:
   - Busca apenas em produtos **aprovados** (`trust_status = 'approved'`).
   - Retorna status (`active`, `discontinued`, `coming_soon`), quantidade em estoque, especificações técnicas, promoção ativa (se `is_active = 1`), e **sugere automaticamente alternativas em estoque** da mesma categoria quando o item buscado está esgotado (`stock_quantity = 0`), descontinuado ou em quarentena.
2. `calculate_payment_conditions(product_id, quantity)`:
   - Calcula em Python puro (zero matemática no LLM):
     - Preço de tabela original.
     - Verifica se há promoção ativa (`is_active = 1`) ou promoções expiradas (`is_active = 0`) para informar com transparência (Seção 6.2 e 7.3).
     - **Regra do PIX (5%):** Aplica 5% de desconto **apenas** se o produto não estiver com promoção ativa.
     - **Tabela de Parcelamento Cartão (1x a 12x):** Calcula exatamente o número máximo de parcelas sem juros respeitando os pisos de `R$ 50` (até 3x), `R$ 80` (4x a 6x) e `R$ 100` (7x a 12x), além de avisar sobre pagamento combinado acima de `R$ 2.000,00`.
3. `calculate_shipping_policy(city, order_total_brl, product_id)`:
   - Aplica deterministicamente a Seção 5 do PDF:
     - **Campo Grande / Região Metropolitana:** Frete Grátis acima de `R$ 500,00`, ou taxa fixa de `R$ 35,00` (abaixo de `R$ 500,00`), prazo `1 a 3 dias úteis` via motoboy próprio.
     - **Outras Cidades (ex: Dourados, Três Lagoas, Corumbá, Ponta Porã):** Lista modalidades `PAC (5-12 dias úteis)`, `SEDEX (2-5 dias úteis)` e `Jadlog (3-8 dias úteis)`, com seguro incluso e alerta de cotação especial para instrumentos de grande porte.
4. `lookup_customer_orders(phone_or_email, customer_name_confirmation, order_id)`:
   - Exige verificação de identidade compatível com a LGPD (Seção 9 do PDF): valida a combinação do contato (`phone` ou `email`) antes de retornar status do pedido, código de rastreio (`tracking_code`), previsão de entrega (`estimated_delivery`), itens comprados e notas de cancelamento (`notes`).
5. `search_store_policies(query, section_filter)`:
   - Consulta o **Hybrid RAG** (ChromaDB + BM25) retornando os trechos exatos do Manual de Políticas com citação da seção e página.
6. `register_human_handoff(customer_identifier, reason_category, summary)`:
   - Registra formalmente solicitações de **Reclamação**, **Acionamento de Garantia/Troca/Devolução**, **Exclusão de Dados LGPD** ou **Dúvidas Omissas para Gerência**, gerando protocolo e informando o prazo oficial de retorno (ex: `24 horas úteis` para reclamações).

### 3.4 Grafo Agêntico Multi-Estágio com LangGraph (`src/agent/`)
- **Estado Tipado (`AgentState`):** Mantém histórico de mensagens (`messages`), perfil do cliente identificado (`customer_context`), contexto de horário de atendimento (`business_hours_status`), logs de ferramentas executadas no turno (`tool_traces`), status de auditoria (`grader_feedback`) e contador de retentativas (`retry_count`).
- **Nó 1 — `context_router`:** Enriquecimento de contexto (verifica se o horário simulado ou real está dentro do expediente Seg-Sex 09h–18h / Sáb 09h–13h e injeta dados do perfil selecionado no Chainlit se disponível).
- **Nó 2 — `assistant_executor`:** Modelo Gemini (`ChatGoogleGenerativeAI` via `langchain-google-genai`) vinculado às 6 ferramentas determinísticas com System Prompt ancorado nas diretrizes da Seção 7 do manual.
- **Nó 3 — `tools_node`:** `ToolNode` do LangGraph executando as ferramentas determinísticas.
- **Nó 4 — `hallucination_grader` (Self-Correction):** Validador que verifica a resposta rascunhada pelo `assistant_executor` contra os resultados das tools:
  - Bloqueia menção a preços, estoques ou descontos sem chamada prévia de tool no turno/conversa.
  - Bloqueia soma indevida de desconto PIX (5%) em produto já promocional.
  - Bloqueia venda de acessórios ou de itens em quarentena.
  - Caso detecte desvio, devolve instrução corretiva ao `assistant_executor` (até 2 retentativas).

---

## 4. Estrutura de Diretórios do Projeto

```text
c:\Users\hgabr\OneDrive\Documentos\AI Engineer\Artefact\Agent\
├── data/                                  # Dados originais fornecidos (.csv e .pdf)
│   └── processed/                         # Gerados pelo pipeline (emporio.db, chroma_db/, data_quality_report.json)
├── src/
│   ├── __init__.py
│   ├── config.py                          # Configurações, variáveis de ambiente, modelos Gemini e constantes
│   ├── data/
│   │   ├── __init__.py
│   │   ├── auditor.py                     # Regras de detecção de anomalias e quarentena (IDs 135-144, etc.)
│   │   ├── database.py                    # Schema SQLite e queries parametrizadas seguras
│   │   └── ingest.py                      # Pipeline ETL: CSV -> Auditoria -> SQLite + Relatório JSON
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py                  # Extrator e Chunking Hierárquico por Seção do PDF
│   │   └── retriever.py                   # ChromaDB (Gemini Embeddings) + BM25 EnsembleRetriever
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── catalog_tools.py               # Busca de catálogo, quarentena, alternativas e cálculo de pagamento/PIX
│   │   ├── order_tools.py                 # Autenticação LGPD, consulta de pedidos, rastreio e frete
│   │   └── policy_tools.py                # Consulta ao RAG Híbrido e registro de Human Handoff
│   └── agent/
│       ├── __init__.py
│       ├── state.py                       # Definição do AgentState (LangGraph)
│       ├── prompts.py                     # Prompts do Executor e do Auditor/Grader
│       └── graph.py                       # Construção do StateGraph (Router -> Executor <-> Tools -> Grader)
├── app.py                                 # Aplicação Chainlit (Chat WhatsApp + Seletor de Perfil + Steps)
├── chainlit.md                            # Tela de boas-vindas e instruções rápidas no Chainlit
├── requirements.txt                       # Dependências travadas e limpas
├── .env.example                           # Template de configuração (GEMINI_API_KEY / GOOGLE_API_KEY)
└── README.md                              # Documentação de Arquitetura, Relatório de Dados e Roteiro de Testes Manuais
```

---

## 5. Sequência de Execução (Próximos Passos após Aprovação)

1. **Ambiente & Dependências:** Configurar `requirements.txt` e validar ambiente Python local com `langchain-google-genai`, `langgraph`, `chromadb`, `rank-bm25`, `pypdf`/`pymupdf`, `chainlit` e `pydantic`.
2. **Pipeline de Dados & Quarentena:** Implementar e executar `src/data/ingest.py`, gerando `emporio.db` e `data_quality_report.json` (auditando todas as tabelas e isolando os registros corrompidos).
3. **Indexação Hybrid RAG:** Implementar e executar a ingestão hierárquica de `políticas_da_loja.pdf` no ChromaDB + BM25.
4. **Ferramentas & Grafo LangGraph:** Implementar as 6 tools determinísticas e o grafo Multi-Estágio com o nó `hallucination_grader`.
5. **Interface Chainlit & Documentação:** Construir o `app.py` com seletor de perfil (simulando clientes reais do `customers.csv` ou visitante anônimo) e redigir o `README.md` + `Agent.md` com o roteiro completo de testes manuais cobrindo todos os casos de borda.
6. **Governança Obsidian:** Registrar a nota do projeto e o log de execução no seu Cérebro Agêntico (`D:\Obsidian`) seguindo a Regra Global de Zero Nós Órfãos.
