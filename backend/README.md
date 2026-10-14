# Veritas Engine — Backend (Alpha 1.0 · Fase 2)

API FastAPI de fact-checking em **fontes primárias** (governos do Brasil e da França, leis e
jurisprudência, ciência e saúde, geopolítica e memória da web), com IA opcional via **BYOK**.

**Custo zero primeiro:** tudo funciona **sem chave de IA** (modo cidadão). Para vereditos
explicados, as opções gratuitas e sem cartão vêm primeiro: Google Gemini, Groq e Ollama local.

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

1. **Sem chave nenhuma:** `POST /api/v1/fact-check/text` → escolha um exemplo (saúde, jurídico,
   geopolítica, economia, memória da web) → *Execute*. A resposta traz as fontes oficiais com
   `verdict = SEM_CHAVE_IA_DADOS_BRUTOS`.
2. **Com IA gratuita:** crie uma chave do Gemini (https://aistudio.google.com/apikey) ou do Groq
   (https://console.groq.com/keys), clique em **Authorize** (cadeado) e preencha `X-Provider` e
   `X-API-Key`. Para Ollama local basta `X-Provider = ollama`. As chaves ficam só na memória da aba.
3. Repita a checagem: agora vem veredito, confiança e explicação com citações `[E1]`, `[E2]`.

Se a chave for inválida ou a cota gratuita acabar, a resposta **não vira erro**: volta ao modo
cidadão e explica o motivo em `notes`.

## Fontes primárias (`app/connectors/`)

| Módulo | Fontes | Chave? |
| --- | --- | --- |
| `br_gov.py` | Câmara dos Deputados, Senado Federal, IBGE (SIDRA) | não |
| `br_gov.py` | Portal da Transparência (emendas parlamentares) | `VERITAS_TRANSPARENCIA_API_KEY` (grátis) |
| `fr_gov.py` | data.gouv.fr, INSEE (Melodi) | não |
| `fr_gov.py` | Légifrance (DILA) | `VERITAS_PISTE_CLIENT_ID/SECRET` (grátis) |
| `legal_justice.py` | Legislação Federal (Senado/Planalto), STJ precedentes (teses, súmulas, RG do STF), EUR-Lex | não |
| `legal_justice.py` | Cour de cassation (Judilibre) | PISTE (grátis) |
| `science_health.py` | PubMed (NCBI), OMS/WHO GHO | não (`VERITAS_NCBI_API_KEY` opcional) |
| `global_geopolitics.py` | GDELT | não |
| `global_geopolitics.py` | ReliefWeb (ONU/OCHA) | `VERITAS_RELIEFWEB_APPNAME` aprovado |
| `web_archive.py` | Internet Archive (Wayback Machine) | não |

Fontes sem a credencial ficam registradas como desativadas (`GET /api/v1/connectors` mostra o
motivo) e nunca bloqueiam a checagem. Cada alegação só consulta as fontes do seu domínio
(saúde → PubMed/OMS; leis → Senado/STJ/EUR-Lex; URL citada → Wayback...).

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
| `X-Provider` | não (sem ele: modo cidadão) | `gemini` · `groq` · `ollama` · `anthropic` (alias `claude`) · `openai` |
| `X-API-Key` | sim, exceto Ollama | Chave do usuário; usada só durante a requisição |
| `X-Endpoint-URL` | não | Apenas `ollama` e `openai` (servidores compatíveis, ex. vLLM) |
| `X-Model` | não | Sobrescreve o modelo padrão do provedor |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/fact-check/text \
  -H "Content-Type: application/json" \
  --data-binary '{"claim": "Vacinas causam autismo em crianças."}'
```

`GET /api/v1/byok/providers` lista os provedores (gratuitos primeiro) com o passo a passo para
obter a chave. `POST /api/v1/connectors/search` consulta as fontes diretamente.

## Estrutura

```
app/
├── main.py                     # create_app(), lifespan (warm-up de datasets), /healthz, CORS
├── core/                       # config (pydantic-settings, prefixo VERITAS_), erros → HTTP
├── api/deps.py                 # provedor BYOK opcional por requisição (criado e descartado)
├── api/v1/                     # fact_check.py, connectors.py, byok.py
├── engines/                    # base.py (BaseLLMProvider), factory.py, providers/, prompt_templates/
├── connectors/                 # base.py, br_gov, fr_gov, legal_justice, science_health,
│                               # global_geopolitics, web_archive, piste (OAuth), registry
├── schemas/                    # evidence.py (Domain, Evidence), fact_check.py
└── services/                   # fact_checker.py (pipeline + modo cidadão), claim_heuristics.py
```
