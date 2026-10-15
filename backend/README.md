# Veritas Engine — Backend (Alpha 1.3)

API FastAPI de fact-checking em **fontes primárias** (governos do Brasil e da França, leis e
jurisprudência, ciência e saúde, clima, geopolítica e memória da web), com IA opcional via **BYOK**,
**perícia multimodal** (foto, vídeo e áudio) e o **app do cidadão** servido em `/`.

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

- **App do cidadão: `http://127.0.0.1:8000/`** (escolha do idioma → `/pt/`, `/en/`, `/fr/`) · Swagger (desenvolvedores): `/docs` · ReDoc: `/redoc` · Health: `GET /healthz`

### Dependências de mídia (em camadas)

| Arquivo | Instala | Como |
| --- | --- | --- |
| `requirements.txt` | API + Pillow (EXIF), yt-dlp, python-multipart | `./run.ps1` · `./run.sh` |
| `requirements-media.txt` | + `imageio-ffmpeg` (FFmpeg embutido) e `c2pa-python` (~300 MB no Windows) | `./run.ps1 -Full` · `./run.sh --full` |
| `requirements-whisper.txt` | + `faster-whisper` (transcrição offline; baixa o modelo na 1ª vez) | `./run.ps1 -Whisper` · `./run.sh --whisper` |

Nada disso é obrigatório: sem uma ferramenta, a etapa correspondente é pulada e o laudo explica o
motivo. `GET /api/v1/media/capabilities` mostra o que está disponível. FFmpeg e ExifTool do sistema
(no `PATH`) têm prioridade sobre os embutidos.

### Docker

```bash
docker compose up --build      # na raiz do repositório; abre em http://localhost:8000
```

A imagem (`backend/Dockerfile`, multi-stage) inclui FFmpeg, ExifTool, C2PA e yt-dlp. O `.env` do
backend é lido se existir; a mídia temporária fica no volume `veritas-media` e é apagada após cada
análise. (O build ainda não foi testado: o ambiente de desenvolvimento Windows não tem Docker.)

## App do cidadão (`/`, `/pt/`, `/en/`, `/fr/`)

Página responsiva (HTML/CSS/JS puros em `app/web/`, ~130 KB por idioma, sem build nem dependências):

- **Idiomas:** `/` é a escolha de idioma (sugere o do navegador); `/pt/`, `/en/` e `/fr/` são páginas
  completas, geradas por `app/web_pages.py` a partir do modelo `web/index.html` (`{{chave}}`) e dos
  dicionários `web/i18n/<idioma>.json`. O dicionário vai embutido na página para o `app.js` (sem
  requisição extra nem "piscar" outro idioma). A página envia `language` à API, então a explicação
  da IA e o texto do modo cidadão saem no idioma da página. As notas do servidor (em português) são
  traduzidas na página por `NOTE_RULES`.
- **Confiança:** com IA, uma régua de Falso a Verdadeiro posiciona o veredito. Com confiança de 80%
  ou mais em Verdadeiro/Falso/Enganoso, o cartão fica todo colorido com carimbo (CONFIRMADO / FALSO /
  ENGANOSO); entre 55% e 79% aparece "provavelmente"; abaixo disso, um aviso de confiança baixa.
  A linha do tempo de mídia, o cartão PNG e o texto do WhatsApp mostram o mesmo nível.

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
- **Mídia (Fase 3):** foto/vídeo/áudio (arrastar, colar ou botão) ou link de vídeo vão para
  `POST /api/v1/fact-check/media`. O resultado ganha o bloco **"Perícia da mídia"** (selo C2PA,
  câmera, data, GPS com link para o mapa, software de edição, duração, SHA-256, quadros do vídeo) e a
  **"Linha do tempo"** expansível com o veredito de cada frase. Se a fala não puder ser transcrita, um
  alerta explica como ativar a IA grátis.

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

## Perícia multimodal (`app/forensics/`)

| Módulo | Função |
| --- | --- |
| `tools.py` | Detecta FFmpeg, ExifTool, Pillow, yt-dlp, C2PA e faster-whisper (`detect_capabilities()`, em cache) |
| `media_inspector.py` | Recebe upload (streaming, limite de 50 MB) ou link (download direto ou yt-dlp, até 15 min), identifica o tipo pelos bytes, calcula SHA-256, lê EXIF, extrai áudio (WAV 16 kHz mono) e quadros-chave (JPEG 320 px). A pasta temporária é sempre apagada |
| `c2pa_validator.py` | Lê o manifesto C2PA e classifica: `AI_GENERATED`, `AI_EDITED`, `CAMERA_CAPTURE`, `EDITED`, `SIGNED_UNKNOWN`, `INVALID_SIGNATURE`, `NO_MANIFEST` ou `UNAVAILABLE` (pelo `digitalSourceType` do IPTC; o nome da ferramenta só decide quando não há tipo declarado) |
| `audio_transcriber.py` | Transcrição com início/fim de cada trecho: **Groq Whisper** (grátis, mesma chave do Groq), **Gemini** (áudio nativo), OpenAI Whisper ou `faster-whisper` local; o áudio sobe em MP3 mono 32 kbps. Depois escolhe até 3 afirmações checáveis com minutagem (IA ou heurística) |

`app/services/media_checker.py` junta tudo: perícia → transcrição → afirmações com minutagem →
checagem de cada uma nas fontes primárias (em sequência, para respeitar os limites dos planos
grátis). Sem IA, devolve a perícia completa e explica como ativar a transcrição.

**Segurança:** links só para hosts públicos (IPs privados/loopback recusados com `unsafe_url`);
tipo de arquivo decidido pelos bytes, não pela extensão; metadados EXIF saneados; nada fica guardado
após a resposta.

## Testes

```bash
cd backend
.venv/Scripts/python -m pytest -v
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
```

298 testes; nenhum faz chamadas de rede reais (SDKs e APIs públicas são mockados). Os testes de
mídia (`tests/test_media_forensics.py`) usam um FFmpeg falso e imagens geradas na hora; os de C2PA
assinam JPEGs com uma cadeia de certificados descartável e são pulados se o `c2pa-python` não estiver
instalado.

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
| `MEDIA_MAX_BYTES`, `MEDIA_MAX_DURATION_SECONDS`, `MEDIA_KEYFRAMES` | Limites da perícia (50 MB, 900 s, 6 quadros) |
| `MEDIA_TMP_DIR`, `WHISPER_LOCAL_MODEL` | Pasta temporária de mídia e modelo do Whisper local (`base`) |

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

# Vídeo, com transcrição grátis pelo Groq Whisper
curl -X POST http://127.0.0.1:8000/api/v1/fact-check/media \
  -H "X-Provider: groq" -H "X-API-Key: $GROQ_KEY" \
  -F "file=@video.mp4" -F "country=BR"
```

| Rota | Descrição |
| --- | --- |
| `POST /api/v1/fact-check/text` | Checagem (`claim`, `country`, `source_url` e `language` = `pt`/`en`/`fr` opcionais); sem IA devolve `SEM_CHAVE_IA_DADOS_BRUTOS` |
| `POST /api/v1/fact-check/media` | Multipart: `file` (até 50 MB) **ou** `url`, mais `claim`, `country` e `language` opcionais. Devolve `forensics` (laudo) e `checks` (afirmações com minutagem e o relatório de cada uma) |
| `GET /api/v1/media/capabilities` | Ferramentas de mídia disponíveis, o que dá para analisar e o que falta instalar |
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
├── web_pages.py                # páginas /pt/, /en/, /fr/ (modelo + dicionário embutido)
├── core/                       # config (pydantic-settings, prefixo VERITAS_), erros → HTTP
├── api/deps.py                 # provedor BYOK opcional por requisição (criado e descartado)
├── api/v1/                     # fact_check.py (/text, /media), connectors.py, byok.py, media.py
├── engines/                    # base.py (BaseLLMProvider), factory.py, providers/, prompt_templates/
├── connectors/                 # base.py, br_gov, fr_gov, legal_justice, science_health,
│                               # global_geopolitics, climate_environment, web_archive,
│                               # piste (OAuth), registry
├── forensics/                  # tools.py, media_inspector.py, c2pa_validator.py, audio_transcriber.py
├── schemas/                    # evidence.py (Domain, Evidence), fact_check.py, forensics.py
├── services/                   # fact_checker.py (pipeline + modo cidadão), media_checker.py,
│                               # claim_heuristics.py
└── web/                        # app do cidadão: home.html (idiomas), index.html (modelo),
                                # styles.css, app.js, home.js, i18n/{pt,en,fr}.json
```
