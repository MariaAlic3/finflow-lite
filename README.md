# finflow-lite

Projeto de prototipagem com [Langflow](https://www.langflow.org/) usando um LLM local via [Ollama](https://ollama.com/).

## Modelo padrão: `llama3.2:1b`

O modelo escolhido como padrão do projeto é o **`llama3.2:1b`**, por ser **mais leve (~1,3 GB) e rápido para prototipagem**, rodando bem localmente sem exigir GPU dedicada.

A configuração fica em `.env` (modelo em `.env.example`):

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b
```

No Langflow, use o componente **Ollama** com *Base URL* `http://localhost:11434` e *Model Name* `llama3.2:1b`.

## Dados de teste: `data/transacoes.csv`

Os dados em `data/transacoes.csv` são **sintéticos, gerados para este exercício**: não são transações reais. Eles cobrem **janeiro a março de 2026** com lançamentos variados (salário, aluguel, mercado, transporte, lazer, saúde etc.) e mantêm **o mesmo padrão de colunas do projeto FinAI original**:

| Coluna | Descrição | Exemplo |
|---|---|---|
| `data` | Data da transação (`AAAA-MM-DD`) | `2026-01-03` |
| `descricao` | Descrição do lançamento | `Aluguel` |
| `categoria` | Categoria (ex.: `receita`, `moradia`, `alimentacao`, `transporte`, `lazer`, `saude`) | `moradia` |
| `valor` | Valor em reais, sempre positivo, com ponto decimal | `1250.00` |
| `tipo` | `entrada` ou `saida` | `saida` |

Esse arquivo é a fonte de dados do flow (`flow.json`): o componente **File** do Langflow aponta para `data/transacoes.csv`.

## O flow (`flow.json`)

```
File (data/transacoes.csv) ─► Resumo Financeiro (pandas) ─► Prompt {fatos} ─► Ollama (llama3.2:1b) ─► Validador ─► Chat Output
Chat Input (pergunta) ──────► Resumo Financeiro {pergunta}     Prompt {pergunta}
                              Resumo Financeiro ─────────────────────────────────────────────────────► Validador {fatos}
```

A ideia é: **o pandas calcula e o LLM só redige**.

| Etapa | O que faz |
|---|---|
| **Resumo Financeiro** (`components/resumo_financeiro.py`) | Lê o CSV com pandas e calcula a soma por categoria e mês, os totais mensais e a maior despesa do mês e do período. A partir dos meses e categorias citados na pergunta e da intenção dela (*total*, *lista* ou *maior despesa*), entrega **só o fato que responde à pergunta**, já calculado. Se a pergunta não tiver uma intenção reconhecível, entrega o relatório completo. |
| **Prompt + Ollama** | O `llama3.2:1b` recebe o fato pronto e só o reescreve em linguagem natural, sem fazer contas. |
| **Validador** (`components/validador_resposta.py`) | Confere se a resposta do modelo tem **exatamente** os valores em R$ dos fatos. Se o modelo recusar, deixar um valor de fora ou inventar um número, devolve o fato calculado no lugar. |

O `flow.json` é gerado pelo script `scripts/gen_flow.py`, a partir dos componentes instalados no `.venv` e dos componentes customizados em `components/`, cujo código vai embutido no `flow.json`:

```powershell
python scripts/gen_flow.py
```

**Caminho do CSV:** no `flow.json`, o componente File guarda o caminho **absoluto** de `data/transacoes.csv`. O Langflow interpreta caminhos relativos com `/` (ex.: `data/transacoes.csv`) como chaves do armazenamento interno dele, e não como arquivos no disco. Se o projeto mudar de pasta ou de máquina, rode o script de novo.

**Acesso a arquivos locais:** por padrão (`LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS=true`), o Langflow só lê arquivos enviados pela própria interface. Para o File ler direto do disco, é preciso desativar essa restrição. Isso é aceitável numa máquina local, com um único usuário, mas **nunca em um servidor compartilhado**.

Para rodar o flow pelo terminal, sem abrir a interface (Git Bash):

```bash
PYTHONUTF8=1 LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS=false \
  .venv/Scripts/lfx.exe run flow.json "Qual foi a maior despesa de março de 2026?" --format text
```

Na interface: use **Import** e selecione `flow.json`. Como alternativa, sem desativar a restrição, envie o `transacoes.csv` pelo próprio componente File.

### Resultado dos testes (13/11/2026)

#### Versão 1: CSV cru direto para o LLM ❌

Na primeira versão, o CSV inteiro ia direto no prompt. O `llama3.2:1b` **errou as 3 perguntas**:

| Pergunta | Resposta do modelo | Resposta correta |
|---|---|---|
| Total gasto com alimentação em jan/2026 | R$ 2.410,00 | **R$ 478,50** (Supermercado 380,50 + Restaurante 98,00) |
| Transações de alimentação em jan/2026 | Supermercado e *Academia (saude)* | Supermercado e Restaurante |
| Maior despesa de mar/2026 | Combustível, "R$ 2.240,00" | **Aluguel, R$ 1.250,00** (Combustível foi R$ 240,00) |

#### Versão 2: pandas + LLM redator + validador ✅

As mesmas 3 perguntas, **3 execuções de cada** pelo `flow.json` completo. **Os números bateram nas 9 execuções:**

| Pergunta | Respostas obtidas (3/3 corretas) | Quem redigiu |
|---|---|---|
| Total gasto com alimentação em jan/2026 | "O total de gastos com alimentação em janeiro de 2026 foi de **R$ 478,50**." | LLM nas 3 |
| Transações de alimentação em jan/2026 | **Supermercado em 04/01/2026 (R$ 380,50)** e **Restaurante em 11/01/2026 (R$ 98,00)**, total **R$ 478,50** | LLM em 1–2 de 3, validador nas demais (varia a cada rodada) |
| Maior despesa de mar/2026 | "A maior despesa em março de 2026 foi **Aluguel (moradia)**, no valor de **R$ 1.250,00**, em 03/03/2026." | LLM nas 3 |

#### O que aprendemos com o `llama3.2:1b`

- **Com o fato já calculado**, ele reescreve totais e maior despesa corretamente: 10 de 10 em testes diretos no Ollama.
- **Ele recusa de forma errática.** Diante de "Liste as transações... com data e valor", responde "não posso fornecer informações financeiras" em cerca de **8 de cada 10** tentativas, mesmo com a resposta pronta no prompt e com uma mensagem de sistema dizendo que os dados são de teste. Ajustar o prompt resolvia uma pergunta e quebrava outra.
- **Relatório grande atrapalha.** Quando recebia todas as agregações de uma vez, ele escolhia o fato errado ou misturava formatos. Por isso o Resumo Financeiro entrega só o fato que responde à pergunta.
- **Por isso existe o Validador.** O número que chega ao usuário sai sempre do pandas. Quando o modelo falha, a resposta perde naturalidade, mas não fica errada.

**Limitação atual:** a detecção de intenção usa palavras-chave (`total`, `quanto`, `gastos`, `liste`, `quais`, `maior`...). Perguntas fora desses padrões recebem o relatório completo, e aí a qualidade da redação volta a depender do modelo. O validador continua barrando números inventados nesse caso.

## Comparação com o FinAI

O **FinAI** e o **finflow-lite** usam o mesmo esquema de dados e chamam um LLM local via Ollama, mas organizam o trabalho de formas diferentes.

| | FinAI | finflow-lite |
|---|---|---|
| Orquestração | Nenhum framework: Python puro | Langflow (orquestração visual) |
| Chamada ao modelo | `requests` direto na API HTTP do Ollama | Componente **Ollama** do Langflow |
| Onde fica a lógica | No próprio código Python | Em nós do flow, com componentes customizados em `components/` |
| Contas e conferência | Escritas à mão no código, se necessárias | Pandas calcula (**Resumo Financeiro**) e o **Validador** confere cada valor em R$ |

**FinAI: Python puro com `requests`.** O código monta o prompt e faz um `POST` direto para o Ollama, sem nenhuma camada no meio. É simples de ler, tem poucas dependências e deixa o controle total com quem escreve o código. Em compensação, tudo o que cerca a chamada ao modelo (preparar dados, conferir a resposta, tratar recusas) precisa ser escrito e mantido à mão. Cada mudança no pipeline é uma mudança de código.

**finflow-lite: Langflow + pipeline de componentes.** O fluxo fica visível como um grafo (File → Resumo Financeiro → Prompt → Ollama → Validador → Chat Output). Dá para trocar o modelo, editar o prompt ou religar etapas pela interface. O ponto central, porém, não é a orquestração visual. São os dois componentes customizados, criados para compensar limitações **observadas na prática** no `llama3.2:1b`:

- o modelo erra contas, filtros e comparações → o **pandas calcula** e o LLM só redige;
- o modelo recusa ou inventa valores de forma errática → o **validador** garante que o número final venha sempre do pandas.

**Conclusão.** Com um modelo pequeno, a qualidade da resposta depende menos do framework e mais de **quanto trabalho se tira do LLM**. O Langflow não resolveu sozinho nenhum dos erros da Versão 1. O que resolveu foi tirar as contas do modelo e conferir a saída dele. Essas duas ideias valem para o FinAI também e poderiam ser aplicadas em Python puro, como funções antes e depois da chamada `requests`. O Langflow ajuda a prototipar, visualizar e testar o pipeline rápido. O Python puro do FinAI continua sendo a opção mais enxuta para levar a produção uma lógica já validada aqui.

## Ambiente

- Windows 11 / PowerShell
- Python 3.14.3
- Langflow 1.13.1 (instalado via pip; foi a versão que o pip resolveu no Python 3.14)

## Comandos usados no setup

### 1. Verificar se o Ollama está instalado e rodando

```powershell
ollama list
```

### 2. Baixar o modelo

```powershell
ollama pull llama3.2:1b
ollama list   # confirmar que llama3.2:1b aparece
```

### 3. Criar e ativar o ambiente virtual Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

> Se o PowerShell bloquear a ativação, rode antes:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 4. Instalar o Langflow

```powershell
pip install langflow
```

## Como rodar

```powershell
.\.venv\Scripts\Activate.ps1
langflow run
```

A interface abre em http://127.0.0.1:7860. O Ollama precisa estar rodando em segundo plano.
