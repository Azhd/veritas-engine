# Veritas Engine — Backend (Alpha 1.2)

API FastAPI de fact-checking em **fontes primárias** (governos do Brasil e da França, leis e
jurisprudência, ciência e saúde, clima, geopolítica e memória da web), com IA opcional via **BYOK**,
e o **app do cidadão** servido em `/`.

> Guia de uso para não desenvolvedores (instalação passo a passo e solução de problemas):
> [README principal](../README.md).

**Custo zero primeiro:** tudo funciona **sem chave de IA** (modo cidadão). Para vereditos
explicados, as opções gratuitas e sem cartão vêm primeiro: Google Gemini, Groq e Ollama local.

## Execução local

```bash
# Windows (PowerShell)
./run.ps1
# Linux / macOS
./run.sh
```

Os scripts criam `.venv`, instalam `requirements.txt`, copiam `.env.example` → `.env` (valores
vazios no `.env` significam "usar o padrão") e sobem o Uvicorn em `http://127.0.0.1:8000`.
Porta alternativa: `./run.ps1 -Port 8001` ou `./run.sh 8001`. Manualmente:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m uvicorn app.main:app --reload
```

- **App do cidadão: `http://127.0.0.1:8000/`** · Swagger (desenvolvedores): `/docs` · ReDoc: `/redoc` · Health: `GET /healthz`

## App do cidadão (`/`)

Página única e responsiva (HTML/CSS/JS puros em `app/web/`, ~73 KB, sem build nem dependências):

- **Entrada:** texto, **print/foto** (o texto é lido no próprio aparelho por OCR gratuito, o Tesseract.js,
  baixado só quando uma imagem é enviada) e o **link de onde a informação veio** (auditado na Wayback Machine).
- **Resultado:** selo do veredito, medidor de confiança (com IA), resumo com citações `[E1]` clicáveis
  e cartões das fontes oficiais com área, data, DOI/PMID e link oficial.
- **Tradução:** fontes em inglês/francês têm o botão "Traduzir" (tradutor do próprio navegador quando
  disponível; senão, link para o Google Tradutor).
- **Compartilhar:** mensagem pronta para o WhatsApp, cópia do resumo e **cartão em imagem (PNG)**.
- **IA opcional:** botão "Grátis · sem IA" no topo; Gemini/Groq/Ollama com passo a passo. O botão
  **"Testar e usar esta IA"** valida a chave (`POST /api/v1/byok/test`) antes de ativá-la. A chave
  fica só na memória da aba, ou no `localStorage` se o usuário marcar "Lembrar neste aparelho".
- **Alertas visíveis:** se a IA falhar durante uma checagem, o resultado mostra o motivo em
  linguagem simples; afirmações vagas sobre acontecimentos recebem uma dica pedindo lugar e data.
- **Cache:** os arquivos de `app/web/` são servidos com `Cache-Control: no-cache` (revalidação por
  ETag), para ninguém ficar com versão antiga após uma atualização.

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
| `climate_environment.py` | Copernicus C3S/ECMWF (ERA5 diário), NOAA NCEI (anual) | não |
| `web_archive.py` | Internet Archive (Wayback Machine) | não |

São 18 conectores, 14 sem nenhuma credencial. Fontes sem a credencial ficam registradas como
desativadas (`GET /api/v1/connectors` mostra o motivo) e nunca bloqueiam a checagem.

**Roteamento por domínio:** cada conector declara `domains` (`politics_legislation`,
`economy_statistics`, `health_science`, `legal_justice`, `geopolitics`, `climate_environment`,
`web_history`) e cada alegação só consulta as fontes do seu domínio (saúde → PubMed/OMS; leis →
Senado/STJ/EUR-Lex; clima → Copernicus/NOAA; URL citada → Wayback). Fontes dedicadas ao tema
aparecem primeiro; fontes amplas (PubMed) ficam limitadas a 3 resultados quando as dedicadas já
responderam.

**Resiliência:** timeout de 8 s por consulta, retentativas com backoff exponencial e cache TTL. Exceções
homologadas: downloads em lote (STJ, Copernicus) usam `VERITAS_DATASET_TIMEOUT_SECONDS` (30 s) e
cache longo; GDELT e Wayback são best-effort (GDELT com intervalo mínimo de 5,5 s entre chamadas).

## Testes

```bash
cd backend
.venv/Scripts/python -m pytest -v
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
```

223 testes; nenhum faz chamadas de rede reais (SDKs e APIs públicas são mockados).

## Configuração (`.env`)

Todas as variáveis têm o prefixo `VERITAS_` e são opcionais; a lista completa e comentada está em
[`.env.example`](.env.example). As principais:

| Variável | Para quê |
| --- | --- |
| `DEFAULT_PROVIDER` | IA usada quando a requisição não envia `X-Provider` (vazio = modo cidadão) |
| `ALLOW_ENV_FALLBACK` | Usar chaves do servidor quando o usuário não envia a sua (desligue em produção pública) |
| `GEMINI_MODEL`, `GROQ_MODEL`... | Modelo padrão de cada provedor (Gemini: `gemini-flash-latest`) |
| `CONNECTOR_TIMEOUT_SECONDS` | Timeout por consulta às fontes (8 s) |
| `TRANSPARENCIA_API_KEY`, `PISTE_CLIENT_ID/SECRET`, `RELIEFWEB_APPNAME`, `NCBI_API_KEY` | Credenciais gratuitas opcionais de fontes |

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

| Rota | Descrição |
| --- | --- |
| `POST /api/v1/fact-check/text` | Checagem (`claim`, `country` e `source_url` opcionais); sem IA devolve `SEM_CHAVE_IA_DADOS_BRUTOS` |
| `POST /api/v1/byok/test` | Testa a chave/modelo informados nos headers (`{ok, provider, model, message}`) |
| `GET /api/v1/byok/providers` | Provedores (gratuitos primeiro) com o passo a passo para obter a chave |
| `GET /api/v1/connectors` | Fontes disponíveis, domínios e motivo de desativação |
| `POST /api/v1/connectors/search` | Consulta direta às fontes, sem IA |

Respostas de modelos abertos (Llama/Groq etc.) são validadas de forma tolerante: ids de evidência
numéricos viram `E1`, `"85%"` vira `0.85`, `"true"` vira `VERDADEIRO`, listas longas são cortadas.
Falhas da IA são registradas no log do servidor (sem a chave) e devolvidas em `notes`, com o
motivo dado pelo provedor (trechos parecidos com chaves são ocultados).

**Modelo indisponível:** se o modelo padrão não estiver liberado para a chave do usuário (HTTP 404,
comum nos planos gratuitos), o provedor lista os modelos da chave e escolhe o melhor modelo de
conversa (Groq, Gemini e servidores compatíveis com OpenAI). `POST /api/v1/byok/test` informa o
modelo escolhido e o app passa a enviá-lo em `X-Model`.

## Estrutura

```
app/
├── main.py                     # create_app(), lifespan (warm-up de datasets), /healthz, CORS
├── core/                       # config (pydantic-settings, prefixo VERITAS_), erros → HTTP
├── api/deps.py                 # provedor BYOK opcional por requisição (criado e descartado)
├── api/v1/                     # fact_check.py, connectors.py, byok.py (inclui /byok/test)
├── engines/                    # base.py (BaseLLMProvider), factory.py, providers/, prompt_templates/
├── connectors/                 # base.py, br_gov, fr_gov, legal_justice, science_health,
│                               # global_geopolitics, climate_environment, web_archive,
│                               # piste (OAuth), registry
├── schemas/                    # evidence.py (Domain, Evidence), fact_check.py
├── services/                   # fact_checker.py (pipeline + modo cidadão), claim_heuristics.py
└── web/                        # app do cidadão: index.html, styles.css, app.js
```
