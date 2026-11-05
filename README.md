[ 🇺🇸 English ](README.md) | [ 🇧🇷 Português ](README.pt-BR.md)

---

# 🎸 Virtual Customer Service Agent — Empório da Música

> **Production Prototype — AI Engineering & Data Governance**  
> **Store:** *Empório da Música Instrumentos Musicais Ltda.* (Tax ID / CNPJ `12.345.678/0001-90` — Campo Grande - MS, Brazil)  
> **Stack:** **Python 3.12**, **LangGraph**, **LangChain**, **Gemini API (`gemini-3.5-flash-lite` / `google-genai`)**, **SQLite (WAL Mode)**, **ChromaDB**, **BM25 (`rank-bm25`)**, **Chainlit**.

---

## 1. Architecture Overview

The system implements a **Multi-Stage Agentic RAG with Absolute Precision (Zero Hallucination)** operating as a WhatsApp virtual assistant for B2C customer service and internal operations support:

<p align="center">
  <img src="assets/arquitetura_sistema.jpg" alt="System Architecture Overview" width="650">
</p>

### Directory Structure

<p align="center">
  <img src="assets/estrutura_diretorios.jpg" alt="Project Directory Structure" width="700">
</p>

### 1.1 Technical Stack Rationale & Trade-offs

The choice of technological stack was guided by strict criteria of robustness, conversational latency, immediate reproducibility, and deterministic integrity control:

- **Python 3.12:**
  - *Why we chose it:* The de facto standard ecosystem for Artificial Intelligence, data manipulation, and LLM orchestration. Delivers modern typing (`typing`, `TypedDict`, `Annotated`), high runtime performance, and seamless compatibility with official Google SDKs (`google-genai`), LangGraph, and vector databases.

- **LangGraph:**
  - *Why we chose it:* Enables modeling the conversational execution flow as a Cyclic Directed Graph with Typed State (`AgentState`). This paradigm made it possible to implement the evaluator node (`hallucination_grader`) with a deterministic self-correction loop (up to 2 retries) and safe in-place fallback, eliminating the fragility of linear chains and preventing infinite generation loops.

- **Gemini 3.5 Flash Lite (`gemini-3.5-flash-lite` via `google-genai`):**
  - *Why we chose it:* Best market balance between ultra-low latency (indispensable for real-time messaging such as WhatsApp), cost-efficiency per million tokens, and exceptional fidelity in structured tool calls (*Function Calling* with Pydantic/JSON Schema validation).

- **SQLite with WAL Mode (*Write-Ahead Logging*):**
  - *Why we chose it:* Self-contained with **zero external infrastructure or managed cloud dependencies** to execute and test the evaluator. With WAL mode enabled (`PRAGMA journal_mode=WAL;`), it delivers high read concurrency without table locks, ensuring microsecond latencies for catalog and order history queries.

- **Hybrid RAG: ChromaDB + BM25 with RRF (*Reciprocal Rank Fusion*):**
  - *Why we chose it:* The `políticas_da_loja.pdf` document contains exact normative rules (strict deadlines such as *"7 days"*, installment percentages, carrier acronyms) alongside broad semantic concepts (*"right of withdrawal"*, *"damage coverage"*). Pure vector RAG can fail on exact lexical keywords, while pure BM25 misses synonyms and semantic intent. Fusion via RRF unites the strengths of both with 100% local execution and zero managed search costs.

- **Chainlit:**
  - *Why we chose it:* Purpose-built for conversational interfaces with native asynchronous execution (`async/await`), faithful simulation of the WhatsApp mobile/web experience, transparent visual inspection of intermediate steps (*Steps / Tool Calls*), and real-time session/profile controls. Furthermore, it streamlines UI delivery, allowing engineering efforts to focus 100% on agent quality, security, and governance.

---

## 2. Data Governance & Audit Pipeline

During raw data ingestion (`data/raw/`), the heuristic engine `ProductAuditor` (`src/data/auditor.py`) audits all tables and the policy PDF, neutralizing catalog anomalies before they reach the LLM:

1. **Severe Inconsistencies in Catalog (`products.csv` — IDs 135 to 144):**
   - **Basses (`IDs 135, 136, 137`):** Commercial titles state `Music Man Bass 1X`, `Ibanez Bass 2X` (with an unrealistic price of `R$ 441.00`), and `Yamaha Bass 3X`, while descriptions cite competing brand models (`Fender Jazz Bass`, `Fender Precision split-coil`, `Ibanez 5-string`) and the JSON `specs` contradicts string counts (`strings: "4"`).
   - **Drum Sets (`IDs 139, 140`):** Titles announce `Yamaha Kit 1` and `Pearl Kit 2`, but descriptions specify `Pearl Export` (Poplar/Mahogany shells) and `Tama 100% Birch`, contradicting the `specs` attribute (`shells: "Maple"`).
   - **Keyboards (`IDs 142, 144`):** Titles list `Korg Synth 1 Pro` and `Roland Synth 3 Pro`, while descriptions detail `Roland SuperNATURAL 88-key` synths (against `keys: "61"` in `specs`) and `Yamaha` workstations.
2. **Safe Quarantine Policy:**
   - Out of **65 analyzed products**, **58 were approved** (`trust_status = 'approved'`) and the **7 corrupted items (`IDs 135, 136, 137, 139, 140, 142, and 144`) were isolated in the `quarantined_products` table**.
   - Catalog search tools query exclusively approved products. If a customer explicitly inquires about a quarantined model, the agent transparently clarifies that the item is temporarily unavailable due to technical batch/specification audits and proactively suggests approved alternatives from the same category.
3. **Customer, Order, and Category Integrity (`data/processed/data_quality_report.json`):**
   - **Customer Anomaly:** Detected and reported shared email `bruno.martins@jmail.com` across customers `#11` (*Bruno Carvalho Martins*) and `#43` (*Bruno Martins*), while preserving referential integrity across 20 orders and 22 items (including historic order `order_id = 10` referencing quarantined item `product_id = 135`).
   - **Empty Categories:** Flagged categories `6` (*Woodwinds*), `7` (*Brass*), and `8` (*Orchestral Strings*) having `0` products registered.
   - **Promotions:** Strict separation between **4 active promotions (`is_active = 1`)** and **21 expired promotions (`is_active = 0`)**.

---

## 3. Hybrid RAG over `políticas_da_loja.pdf`

The official 8-page, 10-section store policy manual is parsed and indexed end-to-end in `src/rag/`:

- **Hierarchical Decomposition (`src/rag/pdf_parser.py`):** Structured extraction of all 10 sections into **15 semantic chunks (`PolicyChunk`)**, preserving 100% of normative rules: operating hours (Mon–Fri 09:00–18:00, Sat 09:00–13:00), payment and installment criteria, right of withdrawal (7 calendar days), defective item exchanges (30 days in-store and 90 days legal warranty under CDC), preference-based exchanges (7 days with price adjustments), non-eligible items (hygiene-restricted mouthpieces, custom instruments, final clearance items), accessory exclusions, and LGPD data privacy mandates.
- **Normalized Lexical Search (`BM25Okapi` + `tokenize_pt`):** Unicode diacritic normalization (`NFKD`), punctuation stripping, and Portuguese stopword filtering, fine-tuned for exact lexical tokens (`PIX`, `5%`, `Jadlog`, `SEDEX`, `PAC`, `Campo Grande`, `7 dias`, `30 dias`, `90 dias`, `boquilha`, `LGPD`).
- **Vector Search (`ChromaDB`):** Persisted in `data/processed/chroma_db` with automatic embedding dimensionality verification (`embedding_backend`) and singleton initialization protected by `threading.Lock()`.
- **Reciprocal Rank Fusion (RRF):** Merges candidate rankings by pruning zero-score BM25 documents (`<= 0.0`) with balanced weights (`1.5` for exact BM25 keyword matches, `1.0` for semantic vector similarity).

---

## 4. Information Security & LGPD Compliance (Zero-Trust)

To prevent personal data leaks (Brazilian Data Protection Law - LGPD nº 13.709/2018, Art. 5, I and Art. 46), **IDOR (*Insecure Direct Object Reference*) / BOLA (*Broken Object Level Authorization*)** vulnerabilities, and **Logistics Interception Frauds**, the system implements native deterministic safeguards:

1. **Strict Session Ownership Binding:**
   - In sessions authenticated by WhatsApp phone number (`customer_context`), the `lookup_customer_orders` tool locks order lookups strictly to the session holder's `customer_id`.
   - Any attempt to query third-party emails, phones, or names is rejected with `status = "unauthorized_mismatch"` **before issuing queries to the `orders` database table**, preventing external customer data from ever leaking into the LLM context.
2. **Two-Factor Knowledge Authentication (2FA) for Anonymous Visitors:**
   - In unauthenticated sessions (*Anonymous Visitor*), submitting an isolated email or phone number is rejected with `status = "verification_required"`.
   - The user must provide a simultaneous combination of **two profile data points belonging to the exact same account holder** (`Email + Full Phone with Area Code` or `Email/Phone + Exact Full Name`).
   - Strict validation blocks deriving names from email handles and rejects partial phone numbers without area codes (`< 10 digits`).
3. **Anti-Spoofing on Human Handoff and Data Erasure:**
   - In `register_human_handoff`, requests for personal data deletion or modification submitted by anonymous users mandate prior 2-factor verification, neutralizing malicious account tampering.
4. **Data Minimization & Graph Anti-Hallucination Guardrails:**
   - The `context_router` masks the customer's email (`l***s@jmail.com`) when injecting session context into the system prompt.
   - The `hallucination_grader` node audits generated answers, blocking unauthorized tracking codes (`BR...BR`) or clear-text exposure of complete customer emails.
   - The Chainlit interface automatically purges message history when switching customer profiles in the sidebar, preventing cross-session data contamination.

### 4.1 Practical Compliance Evidence (Screenshots)

Real simulation tests confirm the efficacy of cybersecurity guardrails and strict LGPD compliance:

| 1. IDOR Blocking (Third-Party Email) | 2. Refusal to Disclose Third-Party Data | 3. Email Minimization & Masking |
| :---: | :---: | :---: |
| ![IDOR Blocking](assets/01_lgpd_bloqueio_idor_email_terceiro.png) | ![Refusal to Disclose Data](assets/02_lgpd_recusa_revelacao_dados_terceiro.png) | ![Email Masking](assets/03_lgpd_mascaramento_email_titular.png) |
| *Immediate block when attempting to query orders using an email not belonging to the session.* | *Strict refusal to disclose identity or order records from third-party customer accounts.* | *Privacy preservation displaying masked email (`r***a@jmail.com`).* |

---

## 5. How to Run the Project

### 5.1 Prerequisites
- **Python 3.12** installed (on Windows, available via `py -3.12`).
- Google Gemini API key (`GOOGLE_API_KEY` or `GEMINI_API_KEY`).

### 5.2 Virtual Environment & Secrets Configuration
```powershell
# 1. Create and activate Python 3.12 virtual environment (if not already created)
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1   # On Windows PowerShell
# or: source .venv/bin/activate  # On Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
Copy-Item .env.example .env
# Edit .env with your API key and gemini-3.5-flash-lite model:
# GOOGLE_API_KEY=your_key_here
# GEMINI_API_KEY=your_key_here
# GEMINI_MODEL=gemini-3.5-flash-lite
```

### 5.3 Run Ingestion & Audit Pipeline
```powershell
python -m src.data.ingest
```
*(Creates the relational SQLite database `data/processed/emporio.db` in WAL mode and exports audit report `data/processed/data_quality_report.json`)*.

### 5.4 Launch WhatsApp Simulator (Chainlit)
```powershell
chainlit run app.py -w
```
Open in your browser: **`http://localhost:8000`**

---

## 6. Manual Test Suite in Chainlit (10 Critical Scenarios)

Use the table below in the simulator to validate all business rules, deterministic calculations, and safety guardrails:

| Scenario | Customer Message in Chat | Expected Agent Behavior |
| :--- | :--- | :--- |
| **1. Catalog & PIX** | *"Olá! Quero começar a tocar violão. Vocês têm algum modelo com cordas de nylon? Qual o preço e se tem desconto no PIX?"* | Invokes `search_catalog` and `calculate_payment_conditions`. Recommends approved models such as **Tagima Memphis AC-39** (`R$ 429.90` $\rightarrow$ **`R$ 408.41` on PIX**) or **Yamaha C40** (`R$ 599.90` $\rightarrow$ **`R$ 569.91` on PIX**), computing **exactly 5% discount** on regular retail price. <br><br> ![Catalog Search](assets/04_busca_catalogo_instrumentos_cordas.png) |
| **2. Non-Cumulative PIX** | *"Gostei do violão Crafter HT-100 Folk. Se eu pagar no PIX, consigo mais 5% além da promoção?"* | Detects active promotion *'Exclusive Discount'* (`18% off`, from `R$ 2,399.00` down to **`R$ 1,967.18`**) and **strictly applies Section 6.2**: explains that the 5% PIX discount is **NOT cumulative** with already discounted items. |
| **3. Scope Enforcing (Accessories)** | *"Vocês vendem jogo de cordas de nylon ou palhetas avulsas?"* | Triggers deterministic scope guardrail (Sections 1 and 7.1): politely clarifies that Empório da Música sells **exclusively complete musical instruments** and advises checking partner shops for standalone accessories. |
| **4. Out of Stock** | *"Tem o violão Giannini GF-3D Dreadnought?"* | Queries the catalog, detects `stock_quantity = 0` (Section 7.3), and **proactively recommends available in-stock alternatives** within the same category (e.g., *Tagima Memphis AC-39*, *Rozini RC-104*, *Shelby SN-100*). |
| **5. Data Quarantine** | *"Estou procurando o contrabaixo Music Man Bass 1X. Tem para pronta entrega?"* | Detects quarantined item (`ID 135`): transparently informs the customer that the model is unavailable due to technical batch/spec auditing, preventing misleading sales and suggesting approved options (such as *Music Man Bass 4X*). <br><br> ![Quarantined Model](assets/05_quarentena_modelo_indisponivel.png) |
| **6. Shipping (Campo Grande)** | *"Quanto custa o frete para entregar aqui no Centro de Campo Grande?"* | Invokes `calculate_shipping`: explains that across the Campo Grande - MS metro area, orders **above `R$ 500.00` qualify for Free Shipping**, while orders below `R$ 500.00` carry a **fixed `R$ 35.00` fee**, delivered via **in-house courier within 1 to 3 business days**. |
| **7. Shipping (Other Cities)** | *"Vocês entregam em Dourados - MS? Quais as opções e prazos?"* | Lists all 3 official national carriers (Section 5.2): **SEDEX (Correios)** (`2 to 5 business days`), **Jadlog (.package)** (`3 to 8 business days`), and **PAC (Correios)** (`5 to 12 business days`), all including tracking and full insurance against transit loss/damage. |
| **8. LGPD & Order Lookup (Zero-Trust / Anti-IDOR)** | *"Qual o status do meu pedido? Meu e-mail é lucas.mendes@jmail.com e meu telefone é (67) 99812-3456"* | Applies deterministic LGPD security (Zero-Trust): if authenticated as account holder on WhatsApp, strictly binds lookup to session `customer_id` (blocking third-party leaked emails with `unauthorized_mismatch` without touching order records). If in **Anonymous Visitor** mode, requires **two simultaneous matching profile factors** (e.g., Email + Phone or Email + Full Name) before returning order **`order_id = 4`** (`BRQM7890123BR`). |
| **9. Return & Exchange Policies** | *"Comprei um ukulele pela internet e chegou ontem, mas me arrependi. Posso devolver?"* | Queries Hybrid RAG (`search_store_policies`, Section 4.1): confirms the right of withdrawal within **7 calendar days** of delivery without justification, with 100% refund in up to **10 business days** and store-covered return freight. <br><br> ![Returns and Exchanges](assets/Arrependimento%20e%20Trocas.png) |
| **10. Escalation / Human Handoff** | *"O meu violão chegou com uma rachadura no tampo e o afinador quebrado. Quero fazer uma reclamação formal!"* | Empathizes with the customer (Section 7.3) and invokes `register_human_handoff`: persists ticket to SQLite (`handoff_tickets`), generates unique protocol formatted as **`EM-YYYYMMDD-XXXXXX`**, and confirms official SLA callback within **24 business hours**. |

---

## 7. Known Limitations

- **Simulated Customer Service Channel vs. Production:**
  - The project utilizes **Chainlit** as a demonstration and validation interface. While it accurately simulates the conversational WhatsApp user experience with session context isolation, it operates in a local interactive web environment rather than being hooked directly into live webhooks of the **Meta Cloud API (WhatsApp Business)**.
- **Web Session Authentication:**
  - Customer profile switching is handled via the simulator's native dropdown menu (facilitating fast evaluation tests), rather than through a strict cryptographic authentication flow utilizing signed session keys or tokens (JWT).
- **Static Policy Vector Indexing:**
  - Hybrid RAG parses and indexes `políticas_da_loja.pdf` during initial bootstrap. In an enterprise setting with daily policy updates, an automated continuous reindexing pipeline (CDC / event-driven) would be recommended.

---

## 8. What I Would Do with More Time

Given additional engineering runway and extended scope for enterprise cloud deployment, the following enhancements would be prioritized:

1. **Official Integration with Meta Cloud API (WhatsApp Business):**
   - Build an asynchronous gateway in **FastAPI** supporting bidirectional Meta webhooks, HMAC-SHA256 payload verification, interactive messaging (quick reply buttons, product lists), and official HSM (*Highly Structured Messages*) templates.
2. **Secure 2FA Authentication via WhatsApp:**
   - Implement an in-conversation two-step verification flow: dispatching a temporary 6-digit OTP code via SMS/WhatsApp to confirm identity prior to disclosing or altering sensitive personal records protected by LGPD.
3. **Domain-Specific Model Fine-Tuning:**
   - Execute Supervised Fine-Tuning (SFT) or DPO (*Direct Preference Optimization*) on open-source or Gemini models using a curated corpus of Brazilian lutherie jargon, instrument maintenance terms, and musician colloquialisms (e.g., truss rod adjustment, active vs. passive pickups, tonewood varieties like jacarandá and marupá), minimizing prompt token footprint and boosting dialogue naturalness.
4. **Continuous Observability Pipeline (LLMOps):**
   - Full instrumentation with **LangSmith** or **OpenTelemetry** to monitor end-to-end latency in real time, token expenditure, self-correction retry frequency in `hallucination_grader`, and user satisfaction scores.

---

## 9. Use of AI Coding Assistants

In developing this project, a cutting-edge collaborative model was adopted using state-of-the-art AI assistance:

- **Tools Used:**
  - **Antigravity 2.0** integrated into the VSCode ecosystem, powered by **Gemini 3.8 Flash** and **Gemini Argon** models.
- **Methodology (Agentic Pair Programming & Human-in-the-Loop):**
  - The assistant was leveraged as a coding companion to accelerate boilerplate development, scaffold ETL data pipelines, fast-track Hybrid RAG implementation (ChromaDB + BM25), and structure multi-stage nodes in LangGraph.
  - **Human-in-the-Loop (HITL) Development:** The programming workflow predominantly adopted a Human-in-the-Loop approach, establishing intermediate checkpoints and deliberate stops for human confirmation and approval prior to enacting substantive code and architectural changes.
  - **Strict Human Oversight:** The entirety of system architecture, relational data modeling, store business rules, anti-IDOR cybersecurity hardening, and strict LGPD compliance was designed, guided, reviewed, and validated line by line by me, ensuring complete quality, security, and technical compliance in the delivered codebase.
