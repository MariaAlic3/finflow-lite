"""Gera flow.json a partir dos componentes do Langflow instalados no .venv.

Uso (na raiz do projeto, com o .venv ativo):
    python scripts/gen_flow.py

O componente File recebe o caminho ABSOLUTO de data/transacoes.csv, porque o Langflow
interpreta caminhos relativos com "/" como chaves do seu armazenamento interno
("<namespace>/<arquivo>"). Rode de novo este script se o projeto mudar de pasta/máquina.

Fluxo:
    File (CSV) ─► Prompt {dados} ─► Ollama ─► Chat Output
    Chat Input ─► Prompt {pergunta}
"""
import json
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

TEMPLATE = """Você é um assistente financeiro. Use as transações abaixo (CSV) para responder à pergunta.
Colunas: data, descricao, categoria, valor (sempre positivo), tipo (entrada/saida).

TRANSAÇÕES:
{dados}

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

prompt = PromptComponent()
prompt_n = node(prompt, "Prompt-fin01", 450, 150)
pnode = prompt_n["data"]["node"]
pnode["template"]["template"]["value"] = TEMPLATE
process_prompt_template(TEMPLATE, name="template", custom_fields=pnode.setdefault("custom_fields", {}),
                        frontend_node_template=pnode["template"])

ollama_n = node(ChatOllamaComponent(), "OllamaModel-fin01", 900, 150)
ot = ollama_n["data"]["node"]["template"]
ot["base_url"]["value"] = "http://localhost:11434"
ot["model_name"]["value"] = "llama3.2:1b"
ot["model_name"]["options"] = ["llama3.2:1b"]
ot["temperature"]["value"] = 0.1
if "num_ctx" in ot:
    ot["num_ctx"]["value"] = 8192

chat_out = node(ChatOutput(), "ChatOutput-fin01", 1350, 150)

nodes = [chat_in, file_n, prompt_n, ollama_n, chat_out]
by_id = {n["id"]: n for n in nodes}


def out_types(n, name):
    for o in n["data"]["node"]["outputs"]:
        if o["name"] == name:
            return o["types"]
    raise KeyError(f"{n['id']} sem output {name}: {[o['name'] for o in n['data']['node']['outputs']]}")


def enc(d):
    return json.dumps(d, ensure_ascii=False).replace('"', "œ")


def edge(src, out, tgt, field):
    s, t = by_id[src], by_id[tgt]
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
    edge("File-fin01", "message", "Prompt-fin01", "dados"),
    edge("ChatInput-fin01", "message", "Prompt-fin01", "pergunta"),
    edge("Prompt-fin01", "prompt", "OllamaModel-fin01", "input_value"),
    edge("OllamaModel-fin01", "text_output", "ChatOutput-fin01", "input_value"),
]

flow = {
    "name": "finflow-lite - Perguntas sobre transações",
    "description": (
        "Lê data/transacoes.csv (dados sintéticos no formato FinAI) e envia as transações ao "
        "llama3.2:1b (Ollama) para responder perguntas em linguagem natural."
    ),
    "is_component": False,
    "data": {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.7}},
}
OUT.write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")
print("ok", OUT)
