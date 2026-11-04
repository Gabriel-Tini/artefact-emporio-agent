"""Módulo de Configuração Centralizada — Empório da Música.

Concentra todos os caminhos de diretórios (`data/raw/` e `data/processed/`),
metadados institucionais da loja (CNPJ, endereço em Campo Grande - MS, contatos,
horário de funcionamento), regras determinísticas de pagamento/parcelamento,
políticas de frete, prazos de pós-venda/garantia e parametrização dos modelos Gemini.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover

    def load_dotenv(dotenv_path: Path | None = None, override: bool = False) -> bool:
        """Fallback leve caso python-dotenv ainda não esteja instalado."""
        if not dotenv_path or not dotenv_path.exists():
            return False
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if override or key not in os.environ:
                os.environ[key] = val
        return True

# ==============================================================================
# 1. Inicialização de Caminhos Base e Variáveis de Ambiente
# ==============================================================================
ROOT_DIR: Path = Path(__file__).resolve().parent.parent
ENV_FILE: Path = ROOT_DIR / ".env"

# Carrega variáveis do arquivo .env (se existir)
load_dotenv(dotenv_path=ENV_FILE, override=False)

# Garante compatibilidade cruzada entre os SDKs (GOOGLE_API_KEY <-> GEMINI_API_KEY)
_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
if _api_key:
    os.environ.setdefault("GOOGLE_API_KEY", _api_key)
    os.environ.setdefault("GEMINI_API_KEY", _api_key)


# ==============================================================================
# 2. Configuração de Diretórios e Arquivos de Dados
# ==============================================================================
@dataclass(frozen=True)
class DataPathsConfig:
    """Padroniza os caminhos de entrada (`data/raw/`) e saída (`data/processed/`)."""

    root_dir: Path = ROOT_DIR
    data_dir: Path = ROOT_DIR / "data"
    raw_dir: Path = ROOT_DIR / "data" / "raw"
    processed_dir: Path = ROOT_DIR / "data" / "processed"

    def resolve_raw_file(self, filename: str) -> Path:
        """Localiza um arquivo bruto em `data/raw/` com fallback seguro para `data/`."""
        candidate_raw = self.raw_dir / filename
        if candidate_raw.exists():
            return candidate_raw
        candidate_fallback = self.data_dir / filename
        if candidate_fallback.exists():
            return candidate_fallback
        return candidate_raw

    def ensure_directories(self) -> None:
        """Garante a existência dos diretórios de dados brutos e processados."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    # --- Arquivos Brutos (CSV e PDF) ---
    @property
    def categories_csv(self) -> Path:
        return self.resolve_raw_file("desafio_tecnico_ai_eng - categories.csv")

    @property
    def products_csv(self) -> Path:
        return self.resolve_raw_file("desafio_tecnico_ai_eng - products.csv")

    @property
    def promotions_csv(self) -> Path:
        return self.resolve_raw_file("desafio_tecnico_ai_eng - promotions.csv")

    @property
    def customers_csv(self) -> Path:
        return self.resolve_raw_file("desafio_tecnico_ai_eng - customers.csv")

    @property
    def orders_csv(self) -> Path:
        return self.resolve_raw_file("desafio_tecnico_ai_eng - orders.csv")

    @property
    def order_items_csv(self) -> Path:
        return self.resolve_raw_file("desafio_tecnico_ai_eng - order_items.csv")

    @property
    def policies_pdf(self) -> Path:
        return self.resolve_raw_file("políticas_da_loja.pdf")

    # --- Artefatos Processados (SQLite, ChromaDB e Relatórios de Governança) ---
    @property
    def sqlite_db_path(self) -> Path:
        return self.processed_dir / "emporio.db"

    @property
    def chroma_db_dir(self) -> Path:
        return self.processed_dir / "chroma_db"

    @property
    def audit_report_path(self) -> Path:
        return self.processed_dir / "data_quality_report.json"

    @property
    def handoff_log_path(self) -> Path:
        return self.processed_dir / "human_handoffs.json"


# ==============================================================================
# 3. Metadados Institucionais da Loja (Seções 1, 2 e 7 do Manual)
# ==============================================================================
@dataclass(frozen=True)
class StoreMetadataConfig:
    """Metadados oficiais da Empório da Música em Campo Grande - MS."""

    razao_social: str = "Empório da Música Instrumentos Musicais Ltda."
    nome_fantasia: str = "Empório da Música"
    slogan: str = "Sua música começa aqui."
    cnpj: str = "12.345.678/0001-90"
    ano_fundacao: int = 2008
    versao_manual: str = "2.1 — Junho de 2025"

    # Localização Física
    logradouro: str = "Rua 14 de Maio, 3200 — Centro"
    cidade: str = "Campo Grande"
    uf: str = "MS"
    cep: str = "79202-333"
    endereco_completo: str = (
        "Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333"
    )

    # Canais de Contato
    telefone_principal: str = "(67) 3341-4444"
    whatsapp_atendimento: str = "(67) 3321-4500"
    email_contato: str = "contato@emporiodamusica.com.br"

    # Horário de Funcionamento (Presencial e WhatsApp)
    horario_seg_a_sex: Tuple[str, str] = ("09:00", "18:00")
    horario_sabado: Tuple[str, str] = ("09:00", "13:00")
    abre_domingos_e_feriados: bool = False
    sla_resposta_whatsapp_minutos: int = 5

    # Escopo Comercial Estrito (Seção 1 e 7.1)
    escopo_exclusivo: str = "Instrumentos musicais"
    acessorios_nao_comercializados: Tuple[str, ...] = (
        "cordas",
        "encordoamento",
        "palhetas",
        "cabos",
        "cases",
        "capas",
        "bags",
        "pedais",
        "pedaleiras",
        "amplificadores",
        "cubos",
        "fontes",
        "suportes",
        "afinadores",
        "correias",
        "baquetas",
    )


# ==============================================================================
# 4. Regras de Pagamento, Descontos e Parcelamento (Seções 3 e 6 do Manual)
# ==============================================================================
@dataclass(frozen=True)
class InstallmentTier:
    """Representa uma faixa de parcelamento no cartão de crédito."""

    min_installments: int
    max_installments: int
    min_installment_value_brl: float
    min_total_purchase_brl: float
    interest_rate_monthly: float = 0.0


@dataclass(frozen=True)
class PaymentRulesConfig:
    """Regras financeiras determinísticas para PIX, Cartão e Boleto."""

    # PIX à vista (Seção 3 e 6.2)
    pix_discount_rate: float = 0.05  # 5% de desconto sobre o preço de tabela
    pix_cumulative_with_promotions: bool = False  # NUNCA acumula com promoção ativa

    # Cartão de Crédito (Seção 3 e 3.1)
    credit_card_max_installments: int = 12
    credit_card_interest_rate: float = 0.0  # Sem juros em todas as faixas válidas
    min_purchase_for_installments_brl: float = 50.00  # Abaixo de R$ 50 é apenas à vista

    # Escalonamento de Parcelas Mínimas (Seção 3.1)
    tier_1_to_3x: InstallmentTier = field(
        default_factory=lambda: InstallmentTier(
            min_installments=1,
            max_installments=3,
            min_installment_value_brl=0.0,
            min_total_purchase_brl=50.00,
            interest_rate_monthly=0.0,
        )
    )
    tier_4_to_6x: InstallmentTier = field(
        default_factory=lambda: InstallmentTier(
            min_installments=4,
            max_installments=6,
            min_installment_value_brl=80.00,
            min_total_purchase_brl=320.00,
            interest_rate_monthly=0.0,
        )
    )
    tier_7_to_12x: InstallmentTier = field(
        default_factory=lambda: InstallmentTier(
            min_installments=7,
            max_installments=12,
            min_installment_value_brl=100.00,
            min_total_purchase_brl=700.00,
            interest_rate_monthly=0.0,
        )
    )

    # Pagamento Combinado (ex: PIX + Cartão) e Boleto
    combined_payment_min_purchase_brl: float = 2000.00
    boleto_compensation_business_days: int = 3
    allow_rain_check_on_out_of_stock: bool = False


# ==============================================================================
# 5. Regras de Frete, Entregas e Rastreamento (Seção 5 do Manual)
# ==============================================================================
@dataclass(frozen=True)
class CarrierModality:
    """Modalidade de envio para cidades fora da Região Metropolitana."""

    name: str
    min_business_days: int
    max_business_days: int
    has_tracking: bool = True
    has_insurance: bool = True


@dataclass(frozen=True)
class ShippingRulesConfig:
    """Políticas determinísticas de frete local e nacional."""

    # Região Metropolitana de Campo Grande (Seção 5.1)
    local_city: str = "Campo Grande"
    local_state: str = "MS"
    local_free_shipping_threshold_brl: float = 500.00
    local_fixed_fee_below_threshold_brl: float = 35.00
    local_delivery_business_days: Tuple[int, int] = (1, 3)
    local_delivery_method: str = (
        "Motoboy próprio (cliente contactado por telefone antes da entrega)"
    )

    # Entregas para Outras Cidades (Seção 5.2)
    national_modalities: Dict[str, CarrierModality] = field(
        default_factory=lambda: {
            "PAC": CarrierModality(
                name="PAC (Correios)",
                min_business_days=5,
                max_business_days=12,
            ),
            "SEDEX": CarrierModality(
                name="SEDEX (Correios)",
                min_business_days=2,
                max_business_days=5,
            ),
            "JADLOG": CarrierModality(
                name="Jadlog (.package)",
                min_business_days=3,
                max_business_days=8,
            ),
        }
    )

    # Instrumentos de Grande Porte (Exigem cotação individual especial)
    oversized_instrument_types: Tuple[str, ...] = (
        "baterias acústicas",
        "pianos digitais",
        "contrabaixos",
    )

    # Formato de Código de Rastreamento (Seção 5.3)
    tracking_code_pattern: str = r"^BR[A-Z0-9]{9}BR$"
    tracking_code_example: str = "BR4K7M2X9P1BR"


# ==============================================================================
# 6. Políticas de Trocas, Devoluções, Garantia e LGPD (Seções 4, 7, 8 e 9)
# ==============================================================================
@dataclass(frozen=True)
class AfterSalesPolicyConfig:
    """Prazos legais e operacionais de trocas, garantias e transbordo humano."""

    regret_return_calendar_days: int = 7  # Direito de arrependimento (online)
    preference_exchange_calendar_days: int = 7  # Troca por cor, modelo ou tamanho
    defect_store_exchange_calendar_days: int = 30  # Troca direta na loja por defeito
    refund_processing_business_days: int = 10  # Reembolso na mesma forma de pagamento
    legal_warranty_calendar_days: int = 90  # Garantia legal CDC (Lei 8.078/90)
    manufacturer_warranty_months_range: Tuple[int, int] = (6, 24)
    complaint_response_business_hours: int = 24  # Prazo de retorno para reclamações

    non_exchangeable_items: Tuple[str, ...] = (
        "Instrumentos com personalização ou ajustes sob encomenda (setup, regulagem especial)",
        "Produtos adquiridos em promoções de liquidação com aviso explícito de 'venda final'",
        "Boquilhas de instrumentos de sopro, por questões de higiene",
    )


# ==============================================================================
# 7. Configuração dos Modelos Gemini e Agente
# ==============================================================================
@dataclass(frozen=True)
class AIModelConfig:
    """Configurações de LLM, Embeddings e controle de retentativas do grafo."""

    api_key: str = _api_key
    llm_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    embedding_model: str = os.getenv(
        "GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001"
    )
    temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.0"))
    max_grader_retries: int = 2
    chroma_collection_name: str = "emporio_da_musica_policies"


# ==============================================================================
# Instâncias Globais Singleton para Importação Direta
# ==============================================================================
PATHS = DataPathsConfig()
STORE_METADATA = StoreMetadataConfig()
PAYMENT_RULES = PaymentRulesConfig()
SHIPPING_RULES = ShippingRulesConfig()
AFTER_SALES_POLICY = AfterSalesPolicyConfig()
AI_CONFIG = AIModelConfig()
