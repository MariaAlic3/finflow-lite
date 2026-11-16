# CLAUDE.md — finflow-lite

## Objetivo do projeto

O **finflow-lite** é um projeto de prototipagem para **testar o Langflow com um modelo de linguagem local rodando via Ollama**, usando dados no formato do projeto **FinAI** (transações financeiras sintéticas em `data/transacoes.csv`).

A ideia é validar fluxos de IA (leitura e análise de transações, categorização, resumos financeiros) de forma leve, local e sem custo de API, antes de levar qualquer coisa para o FinAI.

## Modelo padrão: `llama3.2:1b`

- **Modelo:** `llama3.2:1b` (via Ollama, ~1,3 GB)
- **Por quê:** é mais leve e rápido para prototipagem e roda bem localmente sem GPU dedicada.
- **Configuração:** `.env` (não versionado), com o modelo em `.env.example`:
  ```env
  OLLAMA_BASE_URL=http://localhost:11434
  OLLAMA_MODEL=llama3.2:1b
  ```
- No Langflow, use o componente **Ollama** com *Base URL* `http://localhost:11434` e *Model Name* `llama3.2:1b`.
- Não troque o modelo padrão sem pedir à usuária. Existe também o `gpt-oss:latest` instalado na máquina, mas ele **não** é o padrão do projeto.

## Ambiente

- Windows 11, shell padrão **PowerShell**
- Python 3.14 em ambiente virtual `.venv/` na raiz do projeto
- Langflow instalado via `pip` dentro do `.venv`
- Ollama instalado globalmente e rodando como serviço local (porta 11434)

## Comandos principais

```powershell
# Verificar se o Ollama está rodando e quais modelos existem
ollama list

# Baixar o modelo padrão (se não estiver disponível)
ollama pull llama3.2:1b

# Ativar o ambiente virtual
.\.venv\Scripts\Activate.ps1
# (se o PowerShell bloquear: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)

# Instalar/atualizar dependências
pip install langflow

# Variáveis do Langflow (na mesma sessão, antes do `langflow run`)
$env:LANGFLOW_SUPERUSER = "admin"
$env:LANGFLOW_SUPERUSER_PASSWORD = "troque-esta-senha"
$env:LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS = "false"

# Rodar o Langflow (abre em http://127.0.0.1:7860)
langflow run
```

### Variáveis de ambiente do Langflow

- `LANGFLOW_SUPERUSER` / `LANGFLOW_SUPERUSER_PASSWORD`: usuário e senha do administrador usado para entrar na interface. **Nunca grave a senha real em arquivo versionado** (nem no `.env.example`, nem em docs); use placeholders.
- A senha só é aplicada quando o superusuário é criado. Se ele já existe no banco, o Langflow **mantém a senha antiga** e avisa no log ("LANGFLOW_SUPERUSER_PASSWORD was not applied...").
- O banco padrão fica em `.venv/Lib/site-packages/langflow/langflow.db`. `LANGFLOW_CONFIG_DIR` **não** muda isso. Para subir uma instância de teste sem tocar no banco da usuária, use outra porta e `LANGFLOW_DATABASE_URL=sqlite:///<pasta temporária>/isolated.db`.
- `LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS=false`: ver a seção do flow abaixo.

## Dados

- **Arquivo:** `data/transacoes.csv`, com 34 transações de jan–mar/2026.
- Os dados são **sintéticos, gerados para este exercício**, mas seguem o mesmo padrão de colunas do FinAI original: `data,descricao,categoria,valor,tipo` (`valor` sempre positivo; `tipo` = `entrada`/`saida`).
- É a fonte de dados do `flow.json`: o componente **File** do Langflow aponta para `data/transacoes.csv`.

## Flow do Langflow

- `flow.json` = File (CSV) → **Resumo Financeiro (pandas)** → Prompt → Ollama (`llama3.2:1b`) → **Validador** → Chat Output. O Chat Input alimenta o Resumo e o Prompt.
- Princípio: **o pandas calcula e o LLM só redige.** Nunca peça ao LLM para somar, filtrar ou comparar.
- Componentes customizados em `components/`:
  - `resumo_financeiro.py`: agregações com pandas. Detecta mês, categoria e intenção (total, lista ou maior despesa) na pergunta e entrega só o fato pronto; sem intenção reconhecida, entrega o relatório completo.
  - `validador_resposta.py`: se a resposta do LLM recusar, omitir ou inventar um valor em R$, devolve o fato calculado.
  - Cada arquivo precisa ser um **módulo autocontido**, porque o Langflow embute o código-fonte inteiro no `flow.json`.
- **Não edite o `flow.json` à mão.** Altere `scripts/gen_flow.py` ou `components/*.py` e rode `python scripts/gen_flow.py`. O script monta os nós a partir das classes reais do Langflow instalado (`lfx` / `lfx_ollama`).
- O File usa caminho **absoluto e nativo do Windows** (barras invertidas). Caminhos relativos ou com `/` são interpretados como chave de armazenamento interno e falham com `StorageNamespaceError`.
- Ler arquivo local exige `LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS=false`. Defina só no processo, nunca em servidor compartilhado.
- Teste sem interface (Git Bash):
  `PYTHONUTF8=1 LANGFLOW_RESTRICT_LOCAL_FILE_ACCESS=false .venv/Scripts/lfx.exe run flow.json "pergunta" --format text`
- Comportamento conhecido do `llama3.2:1b` (detalhes no README):
  - com o CSV cru, errou as 3 perguntas de teste;
  - com o fato pronto, reescreve bem totais e maior despesa;
  - recusa cerca de 80% das perguntas do tipo "Liste as transações..." ("não posso fornecer informações financeiras"); nesses casos o validador entra em ação.
  - Ajustar o prompt para resolver uma pergunta costuma quebrar outra. Ao mexer no prompt, **rode de novo as 3 perguntas do README, 3 vezes cada**, e confira se os valores batem com os calculados pelo pandas.
  - O texto de sistema (`SYSTEM_MESSAGE` em `gen_flow.py`) é enviado ao Ollama pelo campo `system_message`.
- Importação pela interface: histórico da conexão Read File → Resumo Financeiro:
  1. **Problema (16/11/2026):** ao importar o `flow.json` na interface, essa conexão veio quebrada e teve de ser refeita à mão, a partir da saída **Raw Content** do Read File (não **File Path**) até o campo **CSV (conteúdo)** (`csv_text`) do Resumo Financeiro. Depois do ajuste, o Playground respondeu R$ 478,50 para alimentação em jan/2026.
  2. **Causa provável:** na interface, o Read File recalcula as saídas para um CSV (Structured Content, Raw Content, File Path), e o `flow.json` não dizia qual saída estava em uso (`selected_output`). `csv_text` é o nome interno certo do campo: "CSV (conteúdo)" é só o nome de exibição.
  3. **Correção (commit `688d3fc`):** o `gen_flow.py` grava `selected_output` em cada nó de origem e escreve os handles das conexões no formato do frontend (chaves ordenadas, sem espaços).
  4. **Verificação (16/11/2026), numa instância isolada na porta 7861:** o login, o Import (`/api/v1/flows/upload/`) e o Playground (`/api/v1/run`, R$ 478,50) funcionaram. As 8 conexões passam nas regras de validação de conexões do frontend 1.13.1, mesmo com as saídas do Read File recalculadas. **Porém o `flow.json` antigo também passa nessas regras**, então a simulação não reproduz a quebra. Falta confirmar **no navegador** se a conexão aparece ligada sem ajuste manual. Até lá, mantenha no README a instrução de ajuste manual.
- Arquivo em UTF-8. No PowerShell 5.1, leia com `Get-Content -Encoding UTF8`, senão os acentos aparecem quebrados.

## Estrutura

```
finflow-lite/
├── .venv/            # ambiente virtual (não versionado)
├── data/
│   └── transacoes.csv  # dados sintéticos no formato do FinAI
├── components/
│   ├── resumo_financeiro.py   # componente customizado: agregações com pandas
│   └── validador_resposta.py  # componente customizado: confere os R$ da resposta
├── flow.json         # flow do Langflow (gerado; não editar à mão)
├── scripts/
│   └── gen_flow.py   # gera o flow.json
├── .env              # configuração local (não versionado)
├── .env.example      # modelo de configuração
├── CLAUDE.md
└── README.md         # passo a passo do setup
```

## Convenção de commits

Siga o padrão do iuricode (https://github.com/iuricode/padroes-de-commits), **escrevendo as mensagens em inglês**.

**Formato:**

```
:emoji: type(optional scope): description
```

- `!` após o tipo/escopo indica breaking change: `feat(api)!: ...`
- Primeira linha curta (o guia recomenda até ~4 palavras); detalhes vão no corpo do commit.
- Links sempre completos, sem encurtadores.

**Tipos:**

| Tipo | Emoji | Uso |
|---|---|---|
| `feat` | ✨ `:sparkles:` | Nova funcionalidade |
| `fix` | 🐛 `:bug:` | Correção de bug |
| `docs` | 📚 `:books:` | Apenas documentação (README, CLAUDE.md…) |
| `test` | 🧪 `:test_tube:` | Criar/alterar testes |
| `build` | 📦 `:package:` / ➕ `:heavy_plus_sign:` / ➖ `:heavy_minus_sign:` | Build e dependências |
| `perf` | ⚡ `:zap:` | Performance |
| `style` | 👌 `:ok_hand:` | Formatação/lint, sem mudar lógica |
| `refactor` | ♻️ `:recycle:` | Reestruturação sem mudar comportamento |
| `chore` | 🔧 `:wrench:` / 🙈 `:see_no_evil:` | Configuração, .gitignore, tarefas de rotina |
| `ci` | 🧱 `:bricks:` | Integração contínua |
| `raw` | 🗃️ `:card_file_box:` | Dados, arquivos de configuração e parâmetros |
| `cleanup` | 🧹 `:broom:` | Remover código comentado/desnecessário |
| `remove` | 🗑️ `:wastebasket:` | Excluir arquivos ou funcionalidades obsoletas |
| `init` | 🎉 `:tada:` | Commit inicial |
| `revert` | 💥 `:boom:` | Reverter um commit anterior |
| `security` | 🔒️ `:lock:` | Correções de segurança |

**Exemplos (em inglês):**

```
:tada: init: initial commit
:books: docs: update README
:sparkles: feat(flow): add transaction categorizer
:bug: fix(csv): handle empty amounts
:wrench: chore: set llama3.2:1b default
:card_file_box: raw: add sample transactions
```
