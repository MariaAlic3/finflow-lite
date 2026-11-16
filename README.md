# finflow-lite

Projeto de prototipagem com [Langflow](https://www.langflow.org/) usando um LLM local via [Ollama](https://ollama.com/).

## Objetivo

O finflow-lite existe para **testar o Langflow com um modelo de linguagem local (`llama3.2:1b`, via Ollama)** respondendo perguntas sobre transações financeiras. Tudo roda na máquina, sem custo de API.

Os dados são **sintéticos**, mas seguem **o mesmo padrão de colunas do projeto FinAI**. Assim, o que funcionar aqui pode ser levado para o FinAI sem adaptar os dados.

Perguntas que o flow responde, por exemplo:

- "Qual foi o total de gastos com alimentação em janeiro de 2026?"
- "Liste as transações de alimentação de janeiro de 2026."
- "Qual foi a maior despesa de março de 2026?"

## Arquitetura

```
                      ┌──────────────────────────────────────────────────────────────┐
                      │                                                              ▼
File (data/transacoes.csv) ─► Resumo Financeiro (pandas) ─► Prompt ─► Ollama (llama3.2:1b) ─► Validador ─► Chat Output
                                     ▲                         ▲
Chat Input (pergunta) ───────────────┴─────────────────────────┘
```

Em resumo: **File → Resumo Financeiro → Prompt → Ollama → Validador → Chat Output**. O Chat Input entrega a pergunta ao Resumo Financeiro e ao Prompt, e o Resumo Financeiro também entrega os fatos ao Validador.

A ideia central é: **o pandas calcula e o LLM só redige.**

| Etapa | Componente | O que faz |
|---|---|---|
| 1. Leitura | **Read File** (nativo) | Lê `data/transacoes.csv` e entrega o conteúdo bruto (saída **Raw Content**). |
| 2. Cálculo | **Resumo Financeiro (pandas)** (`components/resumo_financeiro.py`) | Lê o CSV com pandas e calcula a soma por categoria e mês, os totais mensais e a maior despesa do mês e do período. A partir dos meses e categorias citados na pergunta e da intenção dela (*total*, *lista* ou *maior despesa*), entrega **só o fato que responde à pergunta**, já calculado. Se a pergunta não tiver uma intenção reconhecível, entrega o relatório completo. |
| 3. Instrução | **Prompt Template** (nativo) | Monta o pedido com `{fatos}` e `{pergunta}`: "a resposta já está pronta, reescreva de forma natural". |
| 4. Redação | **Ollama** (nativo, `llama3.2:1b`, temperatura 0.1) | Recebe o fato pronto e só o reescreve em linguagem natural, sem fazer contas. |
| 5. Conferência | **Validador de Resposta** (`components/validador_resposta.py`) | Confere se a resposta do modelo tem **exatamente** os valores em R$ dos fatos. Se o modelo recusar, deixar um valor de fora ou inventar um número, devolve o fato calculado no lugar. |
| 6. Saída | **Chat Output** (nativo) | Mostra a resposta final no Playground ou no terminal. |

### Como o `flow.json` é gerado

O `flow.json` **não é editado à mão**. Ele é gerado por `scripts/gen_flow.py`, que monta cada nó a partir das classes reais do Langflow instalado no `.venv` (`lfx` / `lfx_ollama`) e embute no JSON o código-fonte dos componentes customizados de `components/`:

```powershell
python scripts/gen_flow.py
```

Para mudar o flow, altere `scripts/gen_flow.py` ou `components/*.py` e rode o script de novo.

**O `flow.json` não é versionado** (está no `.gitignore`), porque guarda o caminho absoluto do CSV na sua máquina. Depois de clonar o repositório, gere o arquivo localmente com `python scripts/gen_flow.py` antes de rodar o projeto (passo 5 do setup).

## Ferramentas e versões

| Ferramenta | Versão | Papel |
|---|---|---|
| Windows 11 / PowerShell | — | Ambiente de desenvolvimento |
| Python | 3.14.3 | Ambiente virtual `.venv` |
| Langflow | **1.13.1** (via pip; foi a versão que o pip resolveu no Python 3.14) | Orquestração visual do flow |
| Ollama | 0.40.16 | Servidor local do modelo (porta 11434) |
| Modelo | **`llama3.2:1b`** (~1,3 GB) | Redação das respostas |
| pandas | 2.3.3 (instalado junto com o Langflow) | Cálculos no componente Resumo Financeiro |

### Por que o `llama3.2:1b`

É **leve (~1,3 GB) e rápido para prototipagem** e roda bem localmente sem GPU dedicada. A configuração fica em `.env` (modelo em `.env.example`):

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b
```

## Dados de teste: `data/transacoes.csv`

Os dados em `data/transacoes.csv` são **sintéticos, gerados para este exercício**: não são transações reais. São 34 lançamentos de **janeiro a março de 2026** (salário, aluguel, mercado, transporte, lazer, saúde etc.), com **o mesmo padrão de colunas do projeto FinAI original**:

| Coluna | Descrição | Exemplo |
|---|---|---|
| `data` | Data da transação (`AAAA-MM-DD`) | `2026-01-03` |
| `descricao` | Descrição do lançamento | `Aluguel` |
| `categoria` | Categoria (ex.: `receita`, `moradia`, `alimentacao`, `transporte`, `lazer`, `saude`) | `moradia` |
| `valor` | Valor em reais, sempre positivo, com ponto decimal | `1250.00` |
| `tipo` | `entrada` ou `saida` | `saida` |

## Como rodar do zero

### 1. Instalar o Ollama e baixar o modelo

Instale o Ollama em https://ollama.com/download e confirme que ele está rodando:

```powershell
ollama list
ollama pull llama3.2:1b
ollama list   # confirmar que llama3.2:1b aparece
```

### 2. Criar e ativar o ambiente virtual Python

Na raiz do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

> Se o PowerShell bloquear a ativação, rode antes:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 3. Instalar o Langflow

```powershell
pip install langflow   # neste projeto: 1.13.1, que já traz o pandas
```

### 4. Criar o `.env`

```powershell
Copy-Item .env.example .env
```

### 5. Gerar o `flow.json`

O `flow.json` não vem no repositório: gere-o antes de importar o flow no Langflow ou de rodar o `lfx run`.

```powershell
python scripts/gen_flow.py
```

**Caminho do CSV:** o componente File guarda o caminho **absoluto** de `data/transacoes.csv`. O Langflow interpreta caminhos relativos com `/` (ex.: `data/transacoes.csv`) como chaves do armazenamento interno dele, e não como arquivos no disco. Se o projeto mudar de pasta ou de máquina, rode o script de novo.

### 6. Definir as variáveis de ambiente do Langflow

Antes de subir o Langflow, defina na **mesma sessão do PowerShell**:

```powershell
$env:LANGFLOW_SUPERUSER = "admin"
$env:LANGFLOW_SUPERUSER_PASSWORD = "troque-esta-senha"
$env:LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS = "false"
```

| Variável | Para quê |
|---|---|
| `LANGFLOW_SUPERUSER` | Usuário administrador que o Langflow cria ao iniciar; é com ele que você entra na interface. |
| `LANGFLOW_SUPERUSER_PASSWORD` | Senha desse usuário. Escolha a sua e **não a coloque em arquivos versionados**. |
| `LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS` | Por padrão (`true`), o Langflow só lê arquivos enviados pela própria interface. Com `false`, o componente File lê `data/transacoes.csv` direto do disco. |

> ⚠️ Desativar a restrição de arquivos locais é aceitável numa máquina local, com um único usuário, mas **nunca em um servidor compartilhado**. Se preferir não desativar, envie o `transacoes.csv` pelo próprio componente File na interface.

As variáveis valem só para a sessão atual do terminal. Ao abrir um novo PowerShell, defina-as de novo.

### 7. Subir o Langflow e importar o flow

```powershell
langflow run
```

A interface abre em http://127.0.0.1:7860 (o Ollama precisa estar rodando em segundo plano). Entre com o usuário e a senha do passo 6, clique em **Import**, selecione `flow.json` e abra o **Playground** para fazer perguntas.

### Alternativa: rodar pelo terminal, sem interface

Não precisa de superusuário nem de `langflow run`. No Git Bash:

```bash
PYTHONUTF8=1 LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS=false \
  .venv/Scripts/lfx.exe run flow.json "Qual foi a maior despesa de março de 2026?" --format text
```

## Resultado dos testes (13/11/2026)

### Versão 1: CSV cru direto para o LLM ❌

Na primeira versão, o CSV inteiro ia direto no prompt. O `llama3.2:1b` **errou as 3 perguntas**:

| Pergunta | Resposta do modelo | Resposta correta |
|---|---|---|
| Total gasto com alimentação em jan/2026 | R$ 2.410,00 | **R$ 478,50** (Supermercado 380,50 + Restaurante 98,00) |
| Transações de alimentação em jan/2026 | Supermercado e *Academia (saude)* | Supermercado e Restaurante |
| Maior despesa de mar/2026 | Combustível, "R$ 2.240,00" | **Aluguel, R$ 1.250,00** (Combustível foi R$ 240,00) |

### Versão 2: pandas + LLM redator + validador ✅

As mesmas 3 perguntas, **3 execuções de cada** pelo `flow.json` completo. **Os números bateram nas 9 execuções:**

| Pergunta | Respostas obtidas (3/3 corretas) | Quem redigiu |
|---|---|---|
| Total gasto com alimentação em jan/2026 | "O total de gastos com alimentação em janeiro de 2026 foi de **R$ 478,50**." | LLM nas 3 |
| Transações de alimentação em jan/2026 | **Supermercado em 04/01/2026 (R$ 380,50)** e **Restaurante em 11/01/2026 (R$ 98,00)**, total **R$ 478,50** | LLM em 1–2 de 3, validador nas demais (varia a cada rodada) |
| Maior despesa de mar/2026 | "A maior despesa em março de 2026 foi **Aluguel (moradia)**, no valor de **R$ 1.250,00**, em 03/03/2026." | LLM nas 3 |

### O que aprendemos com o `llama3.2:1b`

- **Com o fato já calculado**, ele reescreve totais e maior despesa corretamente: 10 de 10 em testes diretos no Ollama.
- **Ele recusa de forma errática.** Diante de "Liste as transações... com data e valor", responde "não posso fornecer informações financeiras" em cerca de **8 de cada 10** tentativas, mesmo com a resposta pronta no prompt e com uma mensagem de sistema dizendo que os dados são de teste. Ajustar o prompt resolvia uma pergunta e quebrava outra.
- **Relatório grande atrapalha.** Quando recebia todas as agregações de uma vez, ele escolhia o fato errado ou misturava formatos. Por isso o Resumo Financeiro entrega só o fato que responde à pergunta.
- **Por isso existe o Validador.** O número que chega ao usuário sai sempre do pandas. Quando o modelo falha, a resposta perde naturalidade, mas não fica errada.

**Limitação atual:** a detecção de intenção usa palavras-chave (`total`, `quanto`, `gastos`, `liste`, `quais`, `maior`...). Perguntas fora desses padrões recebem o relatório completo, e aí a qualidade da redação volta a depender do modelo. O validador continua barrando números inventados nesse caso.

## Testado na interface gráfica

Além do terminal (`lfx run`), o flow foi importado e testado na interface do Langflow 1.13.1.

### Problema encontrado: conexão Read File → Resumo Financeiro quebrada

Ao importar o `flow.json` pela interface, **a conexão entre o Read File e o Resumo Financeiro (pandas) veio quebrada**. As outras conexões vieram certas.

- **Sintoma:** o campo de entrada do Resumo Financeiro aparece com o nome de exibição **"CSV (conteúdo)"**, enquanto no JSON gerado a conexão aponta para o nome interno **`csv_text`**. Os dois nomes não batiam, e a ligação teve de ser refeita.
- **Saída certa do Read File:** na interface, o Read File mostra mais de uma saída para um CSV (**Structured Content**, **Raw Content** e **File Path**). O Resumo Financeiro espera o **conteúdo** do arquivo, então a ligação tem de sair de **Raw Content**. Ligar em **File Path** faz o pandas receber o caminho do arquivo como se fosse o CSV, e o cálculo falha.

**Como ajustar na interface:**

1. Apague a conexão quebrada, se ela aparecer.
2. No Read File, escolha a saída **Raw Content** (não **File Path**).
3. Arraste de **Raw Content** até o campo **CSV (conteúdo)** do Resumo Financeiro.

### Resultado após o ajuste ✅

Com a conexão refeita, o **Playground** respondeu corretamente à pergunta sobre **alimentação em janeiro de 2026: R$ 478,50** (Supermercado R$ 380,50 + Restaurante R$ 98,00), o mesmo valor obtido pelo terminal.

### Correção no `gen_flow.py`

O Read File muda as próprias saídas quando a interface carrega o arquivo, e o `flow.json` não dizia qual delas estava em uso. Por isso o `scripts/gen_flow.py` agora:

- grava em cada nó a saída usada pela conexão (`selected_output`; no Read File, `message` = **Raw Content**);
- escreve os identificadores das conexões no mesmo formato que a interface usa (chaves em ordem alfabética, sem espaços).

O `csv_text` continua sendo o nome interno correto do campo: **"CSV (conteúdo)"** é só o nome de exibição dele.

> **Limitação conhecida:** a correção foi conferida pelo terminal (`lfx run` respondeu R$ 478,50), mas **ainda não foi testada numa nova importação pela interface**. Se a conexão vier quebrada de novo, faça o ajuste manual acima.

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

## Estrutura do projeto

```
finflow-lite/
├── components/
│   ├── resumo_financeiro.py   # componente customizado: agregações com pandas
│   └── validador_resposta.py  # componente customizado: confere os R$ da resposta
├── data/
│   └── transacoes.csv         # dados sintéticos no formato do FinAI
├── scripts/
│   └── gen_flow.py            # gera o flow.json
├── flow.json                  # flow do Langflow (gerado localmente; não versionado)
├── .env.example               # modelo de configuração do Ollama
├── CLAUDE.md
└── README.md
```
