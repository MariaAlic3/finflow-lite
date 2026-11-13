"""Componente customizado do Langflow: Validador de Resposta.

Fica depois do Ollama. Compara a resposta do LLM com os FATOS calculados pelo
componente Resumo Financeiro (pandas):

- se a resposta for uma recusa ("não posso fornecer..."), ou
- se faltar algum valor em R$ dos fatos, ou
- se aparecer algum valor em R$ que não está nos fatos (número inventado),

a resposta do LLM é descartada e o próprio fato calculado é devolvido.
Assim, o número que chega ao usuário é sempre o calculado pelo pandas.

Motivo: nos testes, o llama3.2:1b reescrevia corretamente totais e maior despesa,
mas recusava ~80% das vezes perguntas como "Liste as transações...", mesmo com o
fato pronto no prompt.

Este arquivo precisa ser um módulo autocontido: o Langflow guarda o código-fonte
inteiro dele no flow.json.
"""

import re

from lfx.custom import Component
from lfx.io import MessageTextInput, Output
from lfx.schema.message import Message

PADRAO_VALOR = re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*,\d{2}")
PADRAO_RECUSA = re.compile(
    r"\b(n[aã]o posso|n[aã]o consigo|n[aã]o [eé] poss[ií]vel|desculpe)\b", re.IGNORECASE
)


def valores(texto: str) -> set[str]:
    return {v.replace(" ", "") for v in PADRAO_VALOR.findall(texto or "")}


def validar(resposta: str, fatos: str) -> tuple[str, str]:
    """Devolve (texto_final, motivo). motivo == 'ok' quando a resposta do LLM foi mantida."""
    resposta = (resposta or "").strip()
    if not resposta:
        return fatos, "resposta vazia"
    if PADRAO_RECUSA.search(resposta[:120]):
        return fatos, "LLM recusou"
    esperados, obtidos = valores(fatos), valores(resposta)
    if esperados - obtidos:
        return fatos, f"faltaram valores: {sorted(esperados - obtidos)}"
    if obtidos - esperados:
        return fatos, f"valores inventados: {sorted(obtidos - esperados)}"
    return resposta, "ok"


class ValidadorRespostaComponent(Component):
    display_name = "Validador de Resposta"
    description = (
        "Confere se a resposta do LLM usa exatamente os valores calculados pelo pandas; "
        "se o LLM recusar ou errar um número, devolve o fato calculado."
    )
    icon = "shield-check"
    name = "ValidadorResposta"

    inputs = [
        MessageTextInput(
            name="resposta",
            display_name="Resposta do LLM",
            input_types=["Message"],
            required=True,
        ),
        MessageTextInput(
            name="fatos",
            display_name="Fatos calculados",
            info="Saída do componente Resumo Financeiro (pandas).",
            input_types=["Message"],
            required=True,
        ),
    ]

    outputs = [
        Output(display_name="Resposta validada", name="resposta_validada", method="build_resposta"),
    ]

    def build_resposta(self) -> Message:
        texto, motivo = validar(self.resposta, self.fatos)
        self.status = f"[{motivo}] {texto}"
        if motivo != "ok":
            self.log(f"Resposta do LLM substituída pelo fato calculado ({motivo}).")
        return Message(text=texto)
