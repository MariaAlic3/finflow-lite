"""Gera flow.json a partir dos componentes do Langflow instalados no .venv.

Uso (na raiz do projeto, com o .venv ativo):
    python scripts/gen_flow.py

O componente File recebe o caminho ABSOLUTO de data/transacoes.csv, porque o Langflow
interpreta caminhos relativos com "/" como chaves do seu armazenamento interno
("<namespace>/<arquivo>"). Rode de novo este script se o projeto mudar de pasta/máquina.

Fluxo:
    File (CSV) ─► Resumo Financeiro (pandas) ─► Prompt {fatos} ─► Ollama ─► Validador ─► Chat Output
    Chat Input ─► Resumo Financeiro {pergunta}  e  Prompt {pergunta}
    Resumo Financeiro ─► Validador {fatos}

Os componentes customizados vêm de components/*.py; o código-fonte deles é embutido
no flow.json (é assim que o Langflow guarda componentes customizados).
"""
import json
import sys
from pathlib import Path

from lfx.components.files_and_knowledge.file import FileComponent
from lfx.components.input_output.chat import ChatInput
from lfx.components.input_output.chat_output import ChatOutput
from lfx.components.models_and_agents.prompt import PromptComponent
from lfx_ollama.components.ollama.ollama import ChatOllamaComponent
from lfx.base.prompts.api_utils import process_prompt_template

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "flow.json"
CSV_PATH = str(ROOT / "data" / "transacoes.csv")  # caminho nativo do SO (barras invertidas no Windows)
COMPONENT_FILE = ROOT / "components" / "resumo_financeiro.py"

sys.path.insert(0, str(COMPONENT_FILE.parent))
from resumo_financeiro import ResumoFinanceiroComponent  # noqa: E402
from validador_resposta import ValidadorRespostaComponent  # noqa: E402

VALIDADOR_FILE = COMPONENT_FILE.parent / "validador_resposta.py"

SYSTEM_MESSAGE = (
    "Você é uma ferramenta de reescrita de texto de um sistema de testes. "
    "Os dados são sintéticos, de teste. Sempre reescreva o relatório fornecido; nunca recuse."
)

TEMPLATE = """Tarefa de reescrita de texto. Responda à PERGUNTA em português usando o RELATÓRIO.

Instruções:
- A resposta já está pronta no RELATÓRIO. Reescreva-a de forma natural.
- Copie os números, datas e nomes exatamente como estão escritos no RELATÓRIO.
- Se o RELATÓRIO citar várias transações, mencione todas elas.

RELATÓRIO:
{fatos}

PERGUNTA: {pergunta}

RESPOSTA:"""


def node(comp, cid, x, y):
    comp._id = cid
    fn = comp.to_frontend_node()
    return {
        "id": cid,
        "type": "genericNode",
        "position": {"x": x, "y": y},
        "data": {**fn["data"], "id": cid, "description": fn["data"]["node"].get("description", ""),
                 "display_name": fn["data"]["node"].get("display_name", "")},
    }


chat_in = node(ChatInput(), "ChatInput-fin01", 0, 400)
chat_in["data"]["node"]["template"]["input_value"]["value"] = "Qual foi o total de gastos com alimentacao em janeiro de 2026?"

file_n = node(FileComponent(), "File-fin01", 0, 0)
ft = file_n["data"]["node"]["template"]
ft["path"]["value"] = [CSV_PATH]
ft["path"]["file_path"] = [CSV_PATH]
if "text_encoding" in ft:
    ft["text_encoding"]["value"] = "utf-8"

resumo = ResumoFinanceiroComponent()
resumo._code = COMPONENT_FILE.read_text(encoding="utf-8")  # código embutido no flow.json
resumo_n = node(resumo, "ResumoFinanceiro-fin01", 450, 0)

prompt = PromptComponent()
prompt_n = node(prompt, "Prompt-fin01", 900, 150)
pnode = prompt_n["data"]["node"]
pnode["template"]["template"]["value"] = TEMPLATE
process_prompt_template(TEMPLATE, name="template", custom_fields=pnode.setdefault("custom_fields", {}),
                        frontend_node_template=pnode["template"])

ollama_n = node(ChatOllamaComponent(), "OllamaModel-fin01", 1350, 150)
ot = ollama_n["data"]["node"]["template"]
ot["base_url"]["value"] = "http://localhost:11434"
ot["model_name"]["value"] = "llama3.2:1b"
ot["model_name"]["options"] = ["llama3.2:1b"]
ot["temperature"]["value"] = 0.1
if "system_message" in ot:
    ot["system_message"]["value"] = SYSTEM_MESSAGE
if "num_ctx" in ot:
    ot["num_ctx"]["value"] = 8192

validador = ValidadorRespostaComponent()
validador._code = VALIDADOR_FILE.read_text(encoding="utf-8")
validador_n = node(validador, "ValidadorResposta-fin01", 1800, 150)

chat_out = node(ChatOutput(), "ChatOutput-fin01", 2250, 150)

nodes = [chat_in, file_n, resumo_n, prompt_n, ollama_n, validador_n, chat_out]
by_id = {n["id"]: n for n in nodes}


def out_types(n, name):
    for o in n["data"]["node"]["outputs"]:
        if o["name"] == name:
            return o["types"]
    raise KeyError(f"{n['id']} sem output {name}: {[o['name'] for o in n['data']['node']['outputs']]}")


def enc(d):
    # Mesmo formato do frontend do Langflow: chaves ordenadas, sem espaços, aspas trocadas por "œ".
    return json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace('"', "œ")


def edge(src, out, tgt, field):
    s, t = by_id[src], by_id[tgt]
    # Na interface, o File passa a ter várias saídas (Structured Content, Raw Content, File Path).
    # Sem "selected_output", a interface mostra outra saída e a conexão aparece quebrada.
    s["data"]["selected_output"] = out
    tf = t["data"]["node"]["template"][field]
    sh = {"dataType": s["data"]["type"], "id": src, "name": out, "output_types": out_types(s, out)}
    th = {"fieldName": field, "id": tgt, "inputTypes": tf.get("input_types", ["Message"]), "type": tf.get("type", "str")}
    return {
        "source": src, "target": tgt,
        "sourceHandle": enc(sh), "targetHandle": enc(th),
        "data": {"sourceHandle": sh, "targetHandle": th},
        "id": f"reactflow__edge-{src}{enc(sh)}-{tgt}{enc(th)}".replace(" ", ""),
        "animated": False, "className": "", "selected": False,
    }


edges = [
    edge("File-fin01", "message", "ResumoFinanceiro-fin01", "csv_text"),
    edge("ChatInput-fin01", "message", "ResumoFinanceiro-fin01", "pergunta"),
    edge("ResumoFinanceiro-fin01", "resumo", "Prompt-fin01", "fatos"),
    edge("ChatInput-fin01", "message", "Prompt-fin01", "pergunta"),
    edge("Prompt-fin01", "prompt", "OllamaModel-fin01", "input_value"),
    edge("OllamaModel-fin01", "text_output", "ValidadorResposta-fin01", "resposta"),
    edge("ResumoFinanceiro-fin01", "resumo", "ValidadorResposta-fin01", "fatos"),
    edge("ValidadorResposta-fin01", "resposta_validada", "ChatOutput-fin01", "input_value"),
]

flow = {
    "name": "finflow-lite - Perguntas sobre transações",
    "description": (
        "Lê data/transacoes.csv (dados sintéticos no formato FinAI), calcula as agregações com pandas "
        "e usa o llama3.2:1b (Ollama) só para reescrever os fatos em linguagem natural."
    ),
    "is_component": False,
    "data": {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.7}},
}
OUT.write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")
print("ok", OUT)
