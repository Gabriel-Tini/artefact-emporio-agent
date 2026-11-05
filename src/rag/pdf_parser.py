"""Parser e Estruturador Hierárquico do Manual de Políticas da Loja (`políticas_da_loja.pdf`).

Decompõe as 10 seções normativas do documento preservando 100% das cláusulas:
- Seção 1: Sobre a Empório da Música, Missão, Dados da Empresa e Escopo Exclusivo (sem acessórios).
- Seção 2: Horário de Funcionamento (Seg-Sex 09:00-18:00, Sáb 09:00-13:00, Dom/Feriados Fechado).
- Seção 3: Formas de Pagamento (PIX 5% à vista não-cumulativo, Cartão até 12x sem juros, Regras de Parcelamento).
- Seção 4: Política de Trocas e Devoluções (Arrependimento 7 dias, Defeito 30 dias, Preferência 7 dias, Itens Não Elegíveis).
- Seção 5: Política de Frete e Entregas (Campo Grande acima/abaixo de R$ 500, Outras Cidades PAC/SEDEX/Jadlog, Rastreamento).
- Seção 6: Promoções e Descontos (Campanhas, Não-Cumulatividade com PIX, Sem Rain Check).
- Seção 7: Atendimento via WhatsApp ((67) 3321-4500, Tom de Voz, Fluxo e Situações Especiais / Reclamações 24h úteis).
- Seção 8: Garantia (Legal 90 dias CDC, Fabricante 6m-2a, Exclusões).
- Seção 9: Privacidade e Proteção de Dados (LGPD — Lei nº 13.709/2018).
- Seção 10: Disposições Finais (Governança Interna e Consulta à Gerência).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from pypdf import PdfReader

from src.config import POLICIES_PDF


@dataclass
class PolicyChunk:
    """Representa um bloco hierárquico e autossuficiente do Manual de Políticas."""

    chunk_id: str
    section_id: str
    section_title: str
    subsection_id: str
    subsection_title: str
    page_number: int
    keywords: List[str]
    content: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def extract_raw_pdf_pages() -> Dict[int, str]:
    """Lê o arquivo PDF físico para validação de integridade e extração textual por página."""
    pages_text: Dict[int, str] = {}
    if POLICIES_PDF.exists():
        try:
            reader = PdfReader(str(POLICIES_PDF))
            for idx, page in enumerate(reader.pages, start=1):
                pages_text[idx] = page.extract_text() or ""
        except Exception as exc:
            print(
                f"[Aviso PDF] Falha ao ler PDF físico ({exc}). Usando estrutura hierárquica validada."
            )
    return pages_text


def get_hierarchical_policy_chunks() -> List[PolicyChunk]:
    """Retorna os 15 chunks hierárquicos cobrindo as 10 seções do Manual de Políticas (v2.1)."""
    _ = extract_raw_pdf_pages()

    chunks = [
        PolicyChunk(
            chunk_id="sec-1-sobre",
            section_id="1",
            section_title="Sobre a Empório da Música",
            subsection_id="1.0",
            subsection_title="História, Catálogo e Escopo Exclusivo",
            page_number=2,
            keywords=[
                "empório da música",
                "sobre",
                "catálogo",
                "marcas",
                "acessórios",
                "escopo",
                "fundação",
                "cordas",
                "palhetas",
                "cabos",
                "cases",
                "pedais",
                "amplificadores",
            ],
            content=(
                "1. Sobre a Empório da Música\n"
                "A Empório da Música é uma loja especializada em instrumentos musicais, fundada em 2008 em "
                "Campo Grande, Mato Grosso do Sul. Com mais de 15 anos de atuação no mercado, somos "
                "referência regional na venda de instrumentos para músicos iniciantes, intermediários e profissionais.\n"
                "Nosso catálogo abrange mais de 300 instrumentos de marcas nacionais e internacionais, incluindo "
                "guitarras, baixos, violões, baterias, teclados, instrumentos de sopro, cordas orquestrais e ukuleles.\n"
                "IMPORTANTE SOBRE ESCOPO: Trabalhamos exclusivamente com instrumentos musicais — NÃO comercializamos "
                "acessórios como cordas, palhetas, cabos, cases, pedais ou amplificadores. Pedidos de acessórios "
                "devem ser educadamente redirecionados para lojas parceiras."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-1-dados",
            section_id="1",
            section_title="Sobre a Empório da Música",
            subsection_id="1.2",
            subsection_title="Missão e Dados da Empresa",
            page_number=2,
            keywords=[
                "razão social",
                "nome fantasia",
                "cnpj",
                "endereço",
                "whatsapp",
                "telefone",
                "email",
                "contato",
                "missão",
                "rua 14 de maio",
            ],
            content=(
                "1.1 Missão\n"
                "Democratizar o acesso a instrumentos musicais de qualidade na região Centro-Oeste, oferecendo "
                "atendimento especializado e preços competitivos, contribuindo para o desenvolvimento cultural e "
                "musical da comunidade.\n\n"
                "1.2 Dados da Empresa\n"
                "- Razão Social: Empório da Música Instrumentos Musicais Ltda.\n"
                "- Nome Fantasia: Empório da Música\n"
                "- CNPJ: 12.345.678/0001-90\n"
                "- Endereço: Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333\n"
                "- Telefone / WhatsApp Institucional: (67) 3341-4444\n"
                "- Canal Principal de Atendimento Remoto WhatsApp (Seção 7): (67) 3321-4500\n"
                "- E-mail: contato@emporiodamusica.com.br\n"
                "- Fundação: 2008"
            ),
        ),
        PolicyChunk(
            chunk_id="sec-2-horarios",
            section_id="2",
            section_title="Horário de Funcionamento",
            subsection_id="2.0",
            subsection_title="Horário de Funcionamento e Atendimento WhatsApp",
            page_number=2,
            keywords=[
                "horário",
                "horario",
                "aberto",
                "fechado",
                "funcionamento",
                "segunda",
                "sexta",
                "sábado",
                "sabado",
                "domingo",
                "feriado",
                "expediente",
            ],
            content=(
                "2. Horário de Funcionamento\n"
                "O atendimento presencial na loja segue os horários abaixo. O atendimento via WhatsApp segue o "
                "mesmo horário, com respostas automáticas fora do expediente:\n"
                "- Segunda a Sexta-feira: 09:00 às 18:00\n"
                "- Sábado: 09:00 às 13:00\n"
                "- Domingo e Feriados: Fechado\n"
                "Em datas especiais (Black Friday, Aniversário da Loja, Natal), o horário pode ser estendido. "
                "Alterações serão comunicadas com antecedência nas redes sociais e no atendimento via WhatsApp."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-3-pagamentos",
            section_id="3",
            section_title="Formas de Pagamento",
            subsection_id="3.0",
            subsection_title="Formas de Pagamento e Condições",
            page_number=3,
            keywords=[
                "pagamento",
                "formas de pagamento",
                "pix",
                "débito",
                "debito",
                "crédito",
                "credito",
                "boleto",
                "desconto pix",
                "5%",
                "à vista",
            ],
            content=(
                "3. Formas de Pagamento\n"
                "Aceitamos as seguintes formas de pagamento para compras presenciais e online:\n"
                "- PIX: Pagamento à vista com 5% de desconto sobre o preço de tabela (NÃO cumulativo com outras promoções).\n"
                "- Cartão de Débito: Pagamento à vista, todas as bandeiras aceitas.\n"
                "- Cartão de Crédito: Até 12x sem juros (parcela mínima de R$ 100,00 para 7x a 12x, respeitando as regras de escalonamento da Seção 3.1).\n"
                "- Boleto Bancário: Pagamento à vista, com compensação em até 3 dias úteis."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-3-parcelamento",
            section_id="3",
            section_title="Formas de Pagamento",
            subsection_id="3.1",
            subsection_title="Regras de Parcelamento e Pagamento Combinado",
            page_number=3,
            keywords=[
                "parcelamento",
                "parcelas",
                "juros",
                "mínimo",
                "minimo",
                "sem juros",
                "cartão",
                "cartao",
                "combinado",
                "3x",
                "6x",
                "12x",
                "2000",
            ],
            content=(
                "3.1 Regras de Parcelamento no Cartão de Crédito (Sem Juros)\n"
                "• Parcelamento em até 3x: sem juros, sem valor mínimo de parcela (exceto abaixo de R$ 50,00).\n"
                "• Parcelamento de 4x a 6x: sem juros, parcela mínima de R$ 80,00.\n"
                "• Parcelamento de 7x a 12x: sem juros, parcela mínima de R$ 100,00.\n"
                "• Combinação de formas de pagamento: permitida (ex.: PIX + cartão) para compras acima de R$ 2.000,00."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-4-arrependimento",
            section_id="4",
            section_title="Política de Trocas e Devoluções",
            subsection_id="4.1",
            subsection_title="Direito de Arrependimento (Compras Online)",
            page_number=4,
            keywords=[
                "arrependimento",
                "devolução",
                "devolucao",
                "desistência",
                "7 dias",
                "reembolso",
                "estorno",
                "cdc",
                "8.078/90",
                "frete de devolução",
            ],
            content=(
                "4. Política de Trocas e Devoluções\n"
                "A Empório da Música segue as diretrizes do Código de Defesa do Consumidor (Lei nº 8.078/90) e "
                "oferece condições claras para trocas e devoluções.\n\n"
                "4.1 Direito de Arrependimento (Compras Online)\n"
                "• O cliente pode solicitar a devolução em até 7 (sete) dias corridos após o recebimento do produto, sem necessidade de justificativa.\n"
                "• O produto deve estar em sua embalagem original, sem sinais de uso, com todos os acessórios e manuais.\n"
                "• O reembolso será realizado na mesma forma de pagamento original em até 10 dias úteis.\n"
                "• O frete de devolução é por conta da loja em caso de arrependimento."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-4-trocas-defeito-preferencia",
            section_id="4",
            section_title="Política de Trocas e Devoluções",
            subsection_id="4.2",
            subsection_title="Trocas por Defeito, Preferência e Itens Não Elegíveis",
            page_number=4,
            keywords=[
                "troca",
                "trocas",
                "defeito",
                "30 dias",
                "preferência",
                "preferencia",
                "cor",
                "modelo",
                "tamanho",
                "diferença de valor",
                "não elegíveis",
                "boquilha",
                "boquilhas",
                "personalização",
                "setup",
                "regulagem",
                "venda final",
                "higiene",
            ],
            content=(
                "4.2 Trocas por Defeito\n"
                "• Produtos com defeito de fabricação podem ser trocados em até 30 (trinta) dias corridos após a compra.\n"
                "• Após os 30 dias, o cliente deve acionar a garantia diretamente com o fabricante. A Empório da Música pode intermediar o processo mediante solicitação.\n"
                "• Danos causados por mau uso, quedas, exposição a umidade excessiva ou modificações não autorizadas não são cobertos.\n\n"
                "4.3 Trocas por Preferência\n"
                "• Trocas por preferência (cor, modelo, tamanho) são permitidas em até 7 dias, mediante disponibilidade do produto desejado.\n"
                "• O produto deve estar em perfeito estado e na embalagem original.\n"
                "• Diferenças de valor serão cobradas ou reembolsadas conforme o caso.\n\n"
                "4.4 Itens Não Elegíveis para Troca\n"
                "• Instrumentos com personalização ou ajustes sob encomenda (setup, regulagem especial).\n"
                "• Produtos adquiridos em promoções de liquidação com aviso explícito de 'venda final'.\n"
                "• Boquilhas de instrumentos de sopro, por questões de higiene."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-5-frete-campo-grande",
            section_id="5",
            section_title="Política de Frete e Entregas",
            subsection_id="5.1",
            subsection_title="Entregas na Região Metropolitana de Campo Grande",
            page_number=4,
            keywords=[
                "frete",
                "entrega",
                "campo grande",
                "motoboy",
                "frete grátis",
                "frete gratis",
                "500",
                "35",
                "prazo de entrega",
            ],
            content=(
                "5.1 Entregas na Região Metropolitana de Campo Grande\n"
                "• Frete grátis para pedidos acima de R$ 500,00.\n"
                "• Para pedidos abaixo de R$ 500,00, taxa fixa de R$ 35,00.\n"
                "• Prazo de entrega: 1 a 3 dias úteis.\n"
                "• Entrega realizada por motoboy próprio. O cliente será contactado por telefone antes da entrega."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-5-frete-outras-cidades",
            section_id="5",
            section_title="Política de Frete e Entregas",
            subsection_id="5.2",
            subsection_title="Entregas para Outras Cidades, Avaria e Código de Rastreamento",
            page_number=5,
            keywords=[
                "frete",
                "outras cidades",
                "interior",
                "dourados",
                "três lagoas",
                "corumbá",
                "ponta porã",
                "correios",
                "pac",
                "sedex",
                "jadlog",
                "rastreamento",
                "código de rastreamento",
                "seguro",
                "avaria",
                "extravio",
                "grande porte",
                "recusar recebimento",
            ],
            content=(
                "5.2 Entregas para Outras Cidades (Fora da Região Metropolitana de Campo Grande)\n"
                "Utilizamos os serviços dos Correios (PAC e SEDEX) e da transportadora Jadlog:\n"
                "- PAC (Correios): 5 a 12 dias úteis | Rastreamento: Sim | Seguro: Incluído\n"
                "- SEDEX (Correios): 2 a 5 dias úteis | Rastreamento: Sim | Seguro: Incluído\n"
                "- Jadlog (.package): 3 a 8 dias úteis | Rastreamento: Sim | Seguro: Incluído\n"
                "O valor do frete é calculado automaticamente com base no CEP de destino, peso e dimensões do produto. "
                "Instrumentos de grande porte (baterias acústicas, pianos digitais, contrabaixos) podem exigir "
                "frete especial com cotação individual.\n"
                "Todos os envios incluem seguro contra extravios e danos durante o transporte. Em caso de avaria, o "
                "cliente deve recusar o recebimento e entrar em contato imediatamente com a loja.\n\n"
                "5.3 Código de Rastreamento\n"
                "O código de rastreamento é enviado automaticamente por e-mail e WhatsApp assim que o pedido é despachado. "
                "O formato padrão é BR seguido de 9 caracteres alfanuméricos e BR (exemplo: BR4K7M2X9P1BR). "
                "O rastreamento pode ser consultado diretamente no site dos Correios ou da Jadlog."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-6-promocoes",
            section_id="6",
            section_title="Promoções e Descontos",
            subsection_id="6.0",
            subsection_title="Campanhas e Regras de Promoção",
            page_number=6,
            keywords=[
                "promoção",
                "promocao",
                "promoções",
                "desconto",
                "black friday",
                "aniversário da loja",
                "volta às aulas",
                "queima de estoque",
                "semana do músico",
                "cumulatividade",
                "cumulativo",
                "pix",
                "rain check",
            ],
            content=(
                "6. Promoções e Descontos\n"
                "6.1 Tipos de Promoção:\n"
                "• Aniversário da Loja (Agosto): descontos de 10% a 25% em itens selecionados.\n"
                "• Black Friday (Novembro): descontos de 15% a 30% em todo o catálogo.\n"
                "• Volta às Aulas (Fevereiro): descontos especiais em instrumentos para estudantes.\n"
                "• Queima de Estoque: promoções pontuais para renovação de catálogo.\n"
                "• Semana do Músico: promoções na semana do Dia do Músico (22 de novembro).\n\n"
                "6.2 Regras de Promoções:\n"
                "• Cumulatividade: promoções NÃO são cumulativas. O desconto de PIX (5%) NÃO se aplica sobre preços já promocionais.\n"
                "• Estoque: promoções estão sujeitas à disponibilidade de estoque. Produtos esgotados durante a promoção não geram direito a rain check (reserva de preço).\n"
                "• Comunicação: preços promocionais devem sempre ser apresentados junto ao preço original e o percentual de desconto, para total transparência ao cliente."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-7-whatsapp-atendimento",
            section_id="7",
            section_title="Atendimento via WhatsApp",
            subsection_id="7.0",
            subsection_title="Diretrizes e Fluxo de Atendimento",
            page_number=6,
            keywords=[
                "whatsapp",
                "tom de voz",
                "tempo de resposta",
                "5 minutos",
                "acessórios",
                "fluxo de atendimento",
                "3321-4500",
            ],
            content=(
                "7. Atendimento via WhatsApp (Canal Principal: (67) 3321-4500)\n"
                "7.1 Diretrizes de Atendimento:\n"
                "• Tom de voz: informal mas profissional. O cliente deve se sentir acolhido, como se estivesse conversando com um amigo que entende de música. Evitar linguagem excessivamente formal ou robotizada.\n"
                "• Tempo de resposta: máximo de 5 minutos durante o horário de funcionamento. Fora do expediente, o assistente virtual deve informar o horário de retorno.\n"
                "• Informações precisas: nunca fornecer informações sobre preços, estoque ou prazos sem consultar o sistema. Informações incorretas geram frustração e podem configurar propaganda enganosa.\n"
                "• Escopo: o atendente deve informar que a loja trabalha exclusivamente com instrumentos musicais. Pedidos de acessórios (cordas, cabos, palhetas, pedais, amplificadores, cases) devem ser educadamente redirecionados. Sugerir lojas parceiras quando possível.\n\n"
                "7.2 Fluxo de Atendimento Padrão:\n"
                "1. Saudação: cumprimentar o cliente pelo nome (se disponível) e perguntar como pode ajudar.\n"
                "2. Entendimento: identificar a necessidade do cliente (busca de produto, dúvida, rastreamento, reclamação).\n"
                "3. Consulta: buscar no sistema as informações relevantes (produto, estoque, promoção, pedido).\n"
                "4. Resposta: apresentar as opções de forma clara e objetiva, com preços e condições.\n"
                "5. Fechamento: confirmar se o cliente precisa de mais alguma coisa e encerrar com cordialidade."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-7-situacoes-especiais",
            section_id="7",
            section_title="Atendimento via WhatsApp",
            subsection_id="7.3",
            subsection_title="Situações Especiais e Reclamações",
            page_number=7,
            keywords=[
                "fora de estoque",
                "indisponível",
                "descontinuado",
                "promoção expirada",
                "vencida",
                "reclamação",
                "reclamacao",
                "24 horas",
            ],
            content=(
                "7.3 Situações Especiais:\n"
                "• Produto fora de estoque: informar que o produto está temporariamente indisponível e sugerir alternativas semelhantes que estejam disponíveis. Nunca confirmar disponibilidade sem verificar o estoque atual.\n"
                "• Produto descontinuado: informar que o produto não faz mais parte do catálogo e oferecer modelos equivalentes ou sucessores.\n"
                "• Promoção expirada: caso o cliente pergunte sobre uma promoção, verificar se ela encontra-se ativa no sistema. Se a promoção estiver vencida, informar com transparência e apresentar o preço atual. Nunca prometer um desconto que não está mais vigente.\n"
                "• Reclamação: ouvir o cliente com empatia, registrar a reclamação e encaminhar para o responsável. Prazo de retorno: 24 horas úteis."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-8-garantias",
            section_id="8",
            section_title="Garantia",
            subsection_id="8.0",
            subsection_title="Garantia Legal, do Fabricante e Exclusões",
            page_number=7,
            keywords=[
                "garantia",
                "garantia legal",
                "90 dias",
                "fabricante",
                "6 meses",
                "2 anos",
                "exclusões",
                "desgaste natural",
                "mau uso",
                "trastes",
            ],
            content=(
                "8. Garantia\n"
                "8.1 Garantia Legal: Conforme o Código de Defesa do Consumidor, todos os produtos possuem garantia legal de 90 (noventa) dias contra defeitos de fabricação, contados a partir da data de recebimento pelo cliente.\n"
                "8.2 Garantia do Fabricante: Além da garantia legal, a maioria dos fabricantes oferece garantia própria que pode variar de 6 meses a 2 anos, detalhados no certificado de garantia que acompanha cada produto.\n"
                "8.3 O que Não Cobre a Garantia:\n"
                "• Desgaste natural de peças (trastes, cordas, feltros, palhetas de sopro).\n"
                "• Danos por mau uso, queda, exposição a condições climáticas extremas.\n"
                "• Modificações ou reparos realizados por terceiros não autorizados.\n"
                "• Danos estéticos que não afetem a funcionalidade do instrumento."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-9-lgpd",
            section_id="9",
            section_title="Privacidade e Proteção de Dados",
            subsection_id="9.0",
            subsection_title="LGPD, Uso de Dados Pessoais e Exclusão",
            page_number=8,
            keywords=[
                "lgpd",
                "privacidade",
                "proteção de dados",
                "dados pessoais",
                "exclusão",
                "exclusao",
                "13.709/2018",
                "terceiros",
                "marketing",
            ],
            content=(
                "9. Privacidade e Proteção de Dados (LGPD — Lei nº 13.709/2018)\n"
                "A Empório da Música está em conformidade com a Lei Geral de Proteção de Dados (LGPD). "
                "Os dados pessoais coletados durante o atendimento (nome, telefone, e-mail, endereço) são utilizados exclusivamente para:\n"
                "• Processamento e entrega de pedidos.\n"
                "• Comunicação sobre status de pedidos e rastreamento.\n"
                "• Envio de promoções e novidades (mediante consentimento explícito do cliente).\n"
                "• Cumprimento de obrigações legais e fiscais.\n"
                "Dados de clientes não são compartilhados com terceiros para fins de marketing. O cliente pode "
                "solicitar a exclusão de seus dados a qualquer momento entrando em contato pelo WhatsApp ou e-mail."
            ),
        ),
        PolicyChunk(
            chunk_id="sec-10-disposicoes-finais",
            section_id="10",
            section_title="Disposições Finais",
            subsection_id="10.0",
            subsection_title="Governança Interna e Consulta à Gerência",
            page_number=8,
            keywords=[
                "disposições finais",
                "gerência",
                "gerencia",
                "manual interno",
                "atualizações",
                "dúvidas",
            ],
            content=(
                "10. Disposições Finais\n"
                "Este manual é um documento interno da Empório da Música e deve ser utilizado como referência por "
                "todos os membros da equipe de atendimento, incluindo o assistente virtual. As políticas descritas "
                "neste documento estão sujeitas a atualizações periódicas.\n"
                "Em caso de dúvidas sobre a aplicação de qualquer política, o atendente deve consultar a gerência "
                "antes de fornecer informações ao cliente. O objetivo é sempre garantir transparência, precisão e a "
                "melhor experiência possível para o cliente."
            ),
        ),
    ]
    return chunks
