"""Componente customizado do Langflow: Resumo Financeiro (pandas).

Recebe o conteúdo bruto de data/transacoes.csv (saída "Raw Content" do componente File)
e a pergunta do usuário, calcula as agregações com pandas e devolve um texto com os
FATOS já calculados. O LLM só reescreve esses fatos em linguagem natural; ele não
precisa filtrar, somar ou comparar nada.

Agregações:
- soma de despesas e receitas por mês;
- soma de despesas por categoria e mês, com as transações que compõem cada soma;
- maior despesa de cada mês e do período inteiro.

Se a pergunta citar meses (janeiro, fev, março...) e/ou categorias (alimentação,
moradia...), os dados são recortados para esses meses/categorias. Se a pergunta tiver
uma intenção reconhecível (total, lista ou maior despesa), sai SÓ o fato que a
responde; caso contrário, sai o relatório completo. Nos testes, o llama3.2:1b
errava e até recusava quando recebia o relatório inteiro, mas acerta quando recebe
um único fato pronto.

Este arquivo precisa ser um módulo autocontido: o Langflow guarda o código-fonte
inteiro dele no flow.json.
"""

import io
import re
import unicodedata

import pandas as pd

from lfx.custom import Component
from lfx.io import MessageTextInput, Output
from lfx.schema.message import Message

MESES = {
    1: ("janeiro", "jan"), 2: ("fevereiro", "fev"), 3: ("marco", "mar"), 4: ("abril", "abr"),
    5: ("maio", "mai"), 6: ("junho", "jun"), 7: ("julho", "jul"), 8: ("agosto", "ago"),
    9: ("setembro", "set"), 10: ("outubro", "out"), 11: ("novembro", "nov"), 12: ("dezembro", "dez"),
}
NOME_MES = {1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio", 6: "junho", 7: "julho",
            8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"}


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower()


def brl(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(ts: pd.Timestamp) -> str:
    return ts.strftime("%d/%m/%Y")


def rotulo_mes(periodo: pd.Period) -> str:
    return f"{NOME_MES[periodo.month]} de {periodo.year}"


def carregar(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text))
    df.columns = [c.strip().lower() for c in df.columns]
    esperadas = {"data", "descricao", "categoria", "valor", "tipo"}
    faltando = esperadas - set(df.columns)
    if faltando:
        msg = f"CSV sem as colunas esperadas do FinAI: {sorted(faltando)}"
        raise ValueError(msg)
    df["data"] = pd.to_datetime(df["data"], format="%Y-%m-%d")
    df["valor"] = pd.to_numeric(df["valor"])
    df["categoria"] = df["categoria"].str.strip().str.lower()
    df["tipo"] = df["tipo"].str.strip().str.lower()
    df["mes"] = df["data"].dt.to_period("M")
    return df


def detectar_filtros(pergunta: str, df: pd.DataFrame) -> tuple[list[int], list[str]]:
    q = normalizar(pergunta or "")
    meses = [n for n, (longo, curto) in MESES.items() if re.search(rf"\b({longo}|{curto})\b", q)]
    categorias = [c for c in df["categoria"].unique() if re.search(rf"\b{re.escape(normalizar(c))}\b", q)]
    return meses, categorias


def detectar_intencao(pergunta: str) -> str | None:
    """Identifica o que a pergunta pede: 'maior', 'lista' ou 'total'. None = não identificado."""
    q = normalizar(pergunta or "")
    if re.search(r"\b(maior|mais cara|mais alta)\b", q):
        return "maior"
    if re.search(r"\b(liste|listar|lista|quais|detalhe|detalhar|mostre)\b", q):
        return "lista"
    if re.search(r"\b(total|soma|somar|quanto|gastei|gastos?|despesas?)\b", q):
        return "total"
    return None


def periodo_txt(base: pd.DataFrame) -> str:
    return ", ".join(rotulo_mes(p) for p in sorted(base["mes"].unique()))


def fato_principal(base: pd.DataFrame, cats_q: list[str], intencao: str) -> str | None:
    """Monta só o fato que responde à pergunta. None se não houver dados para isso."""
    desp = base[base["tipo"] == "saida"]
    if cats_q:
        desp = desp[desp["categoria"].isin(cats_q)]
    if desp.empty:
        return None
    periodo = periodo_txt(desp)
    escopo = f"com {', '.join(cats_q)} " if cats_q else ""

    if intencao == "maior":
        r = desp.loc[desp["valor"].idxmax()]
        return (
            f"A maior despesa {escopo}em {periodo} foi {r['descricao']} ({r['categoria']}), "
            f"no valor de {brl(r['valor'])}, em {data_br(r['data'])}."
        )
    if intencao == "total":
        return (
            f"O total de despesas {escopo}em {periodo} foi {brl(desp['valor'].sum())} "
            f"({len(desp)} transação(ões))."
        )
    if intencao == "lista":
        # Em frase corrida, não em lista com marcadores: nos testes o llama3.2:1b recusava
        # ("não posso fornecer informações financeiras") quando recebia lista com "- ".
        itens = [f"{r.descricao} em {data_br(r.data)} ({brl(r.valor)})" for r in desp.sort_values("data").itertuples()]
        juntos = itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]
        return (
            f"Em {periodo} houve {len(desp)} despesa(s) {escopo.strip()}, somando {brl(desp['valor'].sum())}: {juntos}."
        )
    return None


def resumir(df: pd.DataFrame, pergunta: str = "") -> str:
    meses_q, cats_q = detectar_filtros(pergunta, df)
    base = df[df["data"].dt.month.isin(meses_q)] if meses_q else df
    if base.empty:
        return "Não há transações no(s) mês(es) citado(s) na pergunta."

    # Caminho principal: a pergunta tem uma intenção reconhecível -> entrega só o fato pronto.
    intencao = detectar_intencao(pergunta)
    if intencao:
        fato = fato_principal(base, cats_q, intencao)
        if fato:
            return fato

    # Fallback: relatório completo de agregações.
    return relatorio_completo(base, cats_q)


def relatorio_completo(base: pd.DataFrame, cats_q: list[str]) -> str:

    desp = base[base["tipo"] == "saida"]
    linhas: list[str] = []

    linhas.append(f"Período considerado: {periodo_txt(base)}.")
    if cats_q:
        linhas.append(f"Categoria(s) citada(s) na pergunta: {', '.join(cats_q)}.")
    linhas.append("")

    # 1) Despesas por categoria e mês (com as transações que compõem cada soma)
    linhas.append("DESPESAS POR CATEGORIA E MÊS:")
    alvo = desp[desp["categoria"].isin(cats_q)] if cats_q else desp
    if alvo.empty:
        linhas.append("- Nenhuma despesa encontrada para esse filtro.")
    for (mes, cat), grupo in alvo.groupby(["mes", "categoria"], sort=True):
        itens = "; ".join(
            f"{r.descricao} em {data_br(r.data)}: {brl(r.valor)}" for r in grupo.sort_values("data").itertuples()
        )
        linhas.append(
            f"- {cat}, {rotulo_mes(mes)}: total {brl(grupo['valor'].sum())} "
            f"({len(grupo)} transação(ões): {itens})"
        )
    linhas.append("")

    # 2) Maior despesa de cada mês e do período
    if not desp.empty:
        linhas.append("MAIOR DESPESA:")
        for mes, grupo in desp.groupby("mes", sort=True):
            r = grupo.loc[grupo["valor"].idxmax()]
            linhas.append(
                f"- {rotulo_mes(mes)}: {r['descricao']} ({r['categoria']}), {brl(r['valor'])}, em {data_br(r['data'])}"
            )
        if desp["mes"].nunique() > 1:
            r = desp.loc[desp["valor"].idxmax()]
            linhas.append(
                f"- Período inteiro: {r['descricao']} ({r['categoria']}), {brl(r['valor'])}, em {data_br(r['data'])}"
            )
        linhas.append("")

    # 3) Totais por mês (só quando a pergunta não é sobre uma categoria específica)
    if not cats_q:
        linhas.append("TOTAIS POR MÊS:")
        for mes, grupo in base.groupby("mes", sort=True):
            entradas = grupo.loc[grupo["tipo"] == "entrada", "valor"].sum()
            saidas = grupo.loc[grupo["tipo"] == "saida", "valor"].sum()
            linhas.append(
                f"- {rotulo_mes(mes)}: receitas {brl(entradas)}, despesas {brl(saidas)}, saldo {brl(entradas - saidas)}"
            )

    return "\n".join(linhas).strip()


class ResumoFinanceiroComponent(Component):
    display_name = "Resumo Financeiro (pandas)"
    description = (
        "Calcula com pandas as agregações do transacoes.csv (soma por categoria e mês, "
        "maior despesa) e devolve os fatos prontos para o LLM só reescrever."
    )
    icon = "calculator"
    name = "ResumoFinanceiro"

    inputs = [
        MessageTextInput(
            name="csv_text",
            display_name="CSV (conteúdo)",
            info="Conteúdo bruto do transacoes.csv. Conecte a saída 'Raw Content' do componente File.",
            input_types=["Message"],
            required=True,
        ),
        MessageTextInput(
            name="pergunta",
            display_name="Pergunta",
            info="Pergunta do usuário; usada para recortar meses e categorias citados.",
            input_types=["Message"],
        ),
    ]

    outputs = [
        Output(display_name="Resumo", name="resumo", method="build_resumo"),
    ]

    def build_resumo(self) -> Message:
        df = carregar(self.csv_text)
        texto = resumir(df, self.pergunta or "")
        self.status = texto
        return Message(text=texto)
