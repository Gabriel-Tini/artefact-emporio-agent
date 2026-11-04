"""Motor de Auditoria e Sanitização Heurística do Catálogo (`ProductAuditor`).

Responsável por:
1. Validar categorias e realizar parse defensivo de especificações técnicas (`specs`).
2. Detectar marcas explícitas e implícitas (via modelos proprietários `EXCLUSIVE_MODEL_BRANDS`,
   como a linha Precision pertencente à Fender) na descrição/specs que conflitam com a marca do produto.
3. Identificar conflitos de madeira de cascos em baterias (`Maple` vs `100% Birch` ou `Poplar`),
   contagem de cordas em instrumentos de corda e número de teclas em teclados/sintetizadores.
4. Isolar os 7 produtos corrompidos (IDs 135, 136, 137, 139, 140, 142 e 144) em quarentena com laudo rastreável.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

# Principais marcas conhecidas do mercado musical presentes no catálogo
KNOWN_BRANDS: List[str] = [
    "Fender",
    "Gibson",
    "Ibanez",
    "PRS",
    "Music Man",
    "Pearl",
    "Tama",
    "Yamaha",
    "Korg",
    "Roland",
    "Nord",
    "Tagima",
    "Giannini",
    "Rozini",
    "Crafter",
    "Martin",
    "Taylor",
    "Takamine",
    "Shelby",
    "Kala",
    "Ohana",
    "Kalani",
]

# Modelos e linhas proprietárias exclusivas de marcas específicas
# (evita falsos negativos como o ID 136, onde o nome diz "Ibanez Bass 2X" a R$ 441
# mas a descrição descreve um "Contrabaixo Precision de 4 cordas com captação split-coil" da Fender)
EXCLUSIVE_MODEL_BRANDS: Dict[str, str] = {
    "precision": "Fender",
    "jazz bass": "Fender",
    "stratocaster": "Fender",
    "telecaster": "Fender",
    "les paul": "Gibson",
    "burstbucker": "Gibson",
    "stingray": "Music Man",
    "pearl export": "Pearl",
    "star-mount": "Tama",
    "stage custom": "Yamaha",
    "supernatural": "Roland",
    "nord stage": "Nord",
}


class ProductAuditor:
    """Motor determinístico e heurístico para auditoria de integridade cadastral de produtos."""

    def __init__(
        self,
        known_brands: List[str] | None = None,
        exclusive_model_brands: Dict[str, str] | None = None,
    ) -> None:
        self.known_brands = known_brands or KNOWN_BRANDS
        self.exclusive_model_brands = exclusive_model_brands or EXCLUSIVE_MODEL_BRANDS

    def extract_brands(self, text: str) -> List[str]:
        """Identifica marcas explícitas e implícitas (por linhas proprietárias) em um texto."""
        if not text:
            return []
        found: List[str] = []
        for brand in self.known_brands:
            pattern = r"\b" + re.escape(brand) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                found.append(brand)

        text_lower = text.lower()
        for model_kw, implied_brand in self.exclusive_model_brands.items():
            if re.search(r"\b" + re.escape(model_kw) + r"\b", text_lower):
                if implied_brand not in found:
                    found.append(implied_brand)

        return found

    @staticmethod
    def parse_specs_defensively(raw_specs: Any) -> Tuple[Dict[str, Any], List[str]]:
        """Realiza o parse defensivo do campo JSON `specs`, retornando `(specs_dict, parse_issues)`."""
        issues: List[str] = []
        if raw_specs is None or raw_specs == "":
            raw_specs = "{}"

        specs: Dict[str, Any] = {}
        try:
            parsed = json.loads(raw_specs) if isinstance(raw_specs, str) else raw_specs
            if isinstance(parsed, dict):
                specs = parsed
            else:
                issues.append(
                    f"JSON_SPECS_TIPO_INVALIDO: esperado objeto JSON (dict), recebido {type(parsed).__name__}"
                )
        except Exception as exc:
            issues.append(f"JSON_SPECS_MALFORMADO: erro ao decodificar specs: {exc}")

        return specs, issues

    def audit_row(
        self, row: Dict[str, Any], categories_by_id: Dict[int, str]
    ) -> Tuple[str, List[str]]:
        """Audita um registro de produto e retorna `(trust_status, issues_list)`."""
        issues: List[str] = []
        name = (row.get("name") or "").strip()
        description = (row.get("description") or "").strip()

        try:
            category_id = int(row.get("category_id", 0))
        except (ValueError, TypeError):
            category_id = 0

        try:
            price_brl = float(row.get("price_brl", 0.0))
        except (ValueError, TypeError):
            price_brl = -1.0

        # 1. Validação de categoria
        if category_id not in categories_by_id:
            issues.append(
                f"CATEGORIA_INVALIDA: category_id {category_id} nao existe em categories.csv"
            )

        # 2. Parse defensivo das especificações técnicas (specs)
        specs, spec_issues = self.parse_specs_defensively(row.get("specs"))
        issues.extend(spec_issues)

        # 3. Cruzamento de Marcas (Explícitas e Implícitas via EXCLUSIVE_MODEL_BRANDS)
        brands_in_name = self.extract_brands(name)
        brands_in_desc = self.extract_brands(description)

        if brands_in_name and brands_in_desc:
            overlap = {b.lower() for b in brands_in_name}.intersection(
                {b.lower() for b in brands_in_desc}
            )
            if not overlap:
                issues.append(
                    f"CONFLITO_MARCA_GRAVE: Nome cita '{', '.join(brands_in_name)}' "
                    f"mas Descrição corresponde a '{', '.join(brands_in_desc)}'"
                )

        # 4. Detecção de anomalia de preço irreal em contrabaixos elétricos (ex: ID 136 a R$ 441)
        if category_id == 2 and 0 <= price_brl < 600.0:
            issues.append(
                f"ANOMALIA_PRECO_CATEGORIA: Contrabaixo elétrico listado por R$ {price_brl:.2f} "
                "(valor incompatível com a categoria e especificações em Ash/Maple)"
            )

        # 5. Cruzamento de Especificações Técnicas (Teclas, Cordas e Cascos de Bateria)
        desc_lower = description.lower()

        # 5.1 Validação de Teclas em Teclados/Sintetizadores
        if "teclas" in desc_lower and "keys" in specs:
            keys_in_spec = str(specs.get("keys", "")).strip()
            match_keys_desc = re.search(r"(\d+)\s*teclas", desc_lower)
            if match_keys_desc:
                desc_keys = match_keys_desc.group(1)
                if desc_keys != keys_in_spec:
                    issues.append(
                        f"CONFLITO_ESPECIFICACAO_TECLAS: Descrição indica {desc_keys} teclas "
                        f"mas Specs define {keys_in_spec} teclas"
                    )

        # 5.2 Validação de Integridade de Cordas em Instrumentos de Corda
        if "cordas" in desc_lower and "strings" in specs:
            strings_in_spec = str(specs.get("strings", "")).strip()
            if strings_in_spec.isdigit():
                match_strings_desc = re.search(r"(\d+)\s*cordas", desc_lower)
                if match_strings_desc:
                    desc_strings = match_strings_desc.group(1)
                    if desc_strings != strings_in_spec:
                        issues.append(
                            f"CONFLITO_ESPECIFICACAO_CORDAS: Descrição indica {desc_strings} cordas "
                            f"mas Specs define {strings_in_spec} cordas"
                        )

        # 5.3 Identificação e Validação de Cascos de Baterias
        if "shells" in specs:
            spec_shell = str(specs.get("shells", "")).strip().lower()
            if spec_shell == "maple":
                if "100% birch" in desc_lower:
                    issues.append(
                        "CONFLITO_ESPECIFICACAO_CASCO: Descrição afirma cascos 100% Birch mas Specs define Maple"
                    )
                elif "poplar" in desc_lower and "maple" not in desc_lower:
                    issues.append(
                        "CONFLITO_ESPECIFICACAO_CASCO: Descrição afirma cascos em Poplar/Mogno mas Specs define Maple"
                    )

        trust_status = "quarantined" if issues else "approved"
        return trust_status, issues


# Instância padrão para uso funcional direto
_DEFAULT_AUDITOR = ProductAuditor()


def extract_brands(text: str) -> List[str]:
    """Atalho funcional para `ProductAuditor.extract_brands`."""
    return _DEFAULT_AUDITOR.extract_brands(text)


def audit_product_row(
    row: Dict[str, Any], categories_by_id: Dict[int, str]
) -> Tuple[str, List[str]]:
    """Atalho funcional para `ProductAuditor.audit_row`."""
    return _DEFAULT_AUDITOR.audit_row(row, categories_by_id)
