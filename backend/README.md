# Veritas Engine — Backend (Fase 1)

API FastAPI de fact-checking com motor **BYOK** (Gemini, Claude, OpenAI, Groq, Ollama) e
conectores oficiais **BR** (Câmara dos Deputados, IBGE) e **FR** (data.gouv.fr).

## Execução local

```bash
# Windows (PowerShell)
./run.ps1
# Linux / macOS
./run.sh
```

Os scripts criam `.venv`, instalam `requirements.txt`, copiam `.env.example` → `.env` e sobem o
Uvicorn em `http://127.0.0.1:8000`. Manualmente:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m uvicorn app.main:app --reload
```

- Swagger: `http://127.0.0.1:8000/docs` (a raiz `/` redireciona para lá) · ReDoc: `/redoc` · Health: `GET /healthz`

## Testando pelo Swagger (`/docs`)

1. **Sem chave de IA:** `POST /api/v1/connectors/search` → escolha um exemplo → *Execute*.
   Retorna os dados oficiais da Câmara, do IBGE e do data.gouv.fr.
2. **Botão Authorize (cadeado):** preencha `X-Provider` e `X-API-Key` uma única vez; todas as
   requisições passam a enviá-los. Para Ollama local basta `X-Provider = ollama`.
   As chaves ficam só na memória da aba (não vão para o `localStorage`).
3. **`POST /api/v1/fact-check/text`:** escolha um dos exemplos prontos (BR/FR) e execute.

Chaves gratuitas para teste: Gemini (https://aistudio.google.com/apikey) e
Groq (https://console.groq.com/keys).

## Testes

```bash
cd backend
.venv/Scripts/python -m pytest -v
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
```

Nenhum teste faz chamadas de rede reais (SDKs e APIs públicas são mockados).

## BYOK — como chamar

| Header | Obrigatório | Descrição |
| --- | --- | --- |
| `X-Provider` | sim (salvo `VERITAS_DEFAULT_PROVIDER`) | `gemini` · `anthropic` (alias `claude`) · `openai` · `groq` · `ollama` |
| `X-API-Key` | sim, exceto Ollama | Chave do usuário; usada só durante a requisição |
| `X-Endpoint-URL` | não | Apenas `ollama` e `openai` (servidores compatíveis, ex. vLLM) |
| `X-Model` | não | Sobrescreve o modelo padrão do provedor |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/fact-check/text \
  -H "Content-Type: application/json" \
  -H "X-Provider: ollama" -H "X-Endpoint-URL: http://localhost:11434" \
  --data-binary '{"claim": "A taxa de desemprego no Brasil caiu em 2026."}'
```

`GET /api/v1/byok/providers` lista provedores, modelos padrão e se há chave de fallback no servidor.
`GET /api/v1/connectors` lista as fontes oficiais; `POST /api/v1/connectors/search` consulta-as sem IA.

## Estrutura

```
app/
├── main.py                     # create_app(), lifespan, /healthz, CORS
├── core/                       # config (pydantic-settings, prefixo VERITAS_), erros → HTTP
├── api/deps.py                 # provedor BYOK por requisição (criado e descartado)
├── api/v1/                     # fact_check.py, connectors.py, byok.py
├── engines/                    # base.py (BaseLLMProvider), factory.py, providers/, prompt_templates/
├── connectors/                 # base.py (timeout/retry/backoff/TTL cache), br/, fr/, registry.py
├── schemas/                    # evidence.py, fact_check.py
└── services/fact_checker.py    # orquestrador do pipeline
```
