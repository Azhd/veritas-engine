# TASK_BOARD.md - Painel de Controle e Handover (Veritas Engine Alpha 1.0)

> **Mecanismo de Coordenação**:
> - **Antigravity (Gemini)**: Arquiteto & Product Manager (define requisitos, audita entregas, inicia testes para o usuário e coordena publicações).
> - **Claude Code**: Tech Lead & Engenheiro Executor (implementa, testa e submete para revisão).
> 
> **Ciclo de Vida das Fases / Tarefas**:
> `BACKLOG` ➔ `EM PROGRESSO` ➔ `PRONTO PARA REVISÃO DO ANTIGRAVITY` ➔ `AGUARDANDO VALIDAÇÃO DO USUÁRIO` ➔ `PUBLICADA NO GITHUB`

---

## 🚨 Regra de Ouro de Versionamento e GitHub

1. **FLUXO DE VALIDAÇÃO OBRIGATÓRIO**:
   - Sempre que uma funcionalidade ou fase for concluída pelo Claude Code e auditada, o status deve obrigatoriamente transitar para `AGUARDANDO VALIDAÇÃO DO USUÁRIO`.
   - O agente ativo deve iniciar o servidor local de testes e demonstrar na tela como o usuário pode validar.
   - **É TERMINANTEMENTE PROIBIDO executar `git push` automático antes da aprovação explícita do usuário no chat.**

2. **GATILHO AUTOMÁTICO DE COMMIT & PUSH**:
   - Enquanto o usuário testa, são permitidos commits locais de segurança (`git commit`).
   - Assim que o usuário enviar no chat **"Validado"**, **"Aprovado"** ou **"Pode subir"**, o agente ativo deve:
     1. **Verificar segredos**: Garantir que `.env` está no `.gitignore` e nenhuma credencial está nos arquivos indexados.
     2. **Commit semântico**: Executar `git add .` e `git commit` no padrão *Conventional Commits*.
     3. **Push remoto**: Executar `git push` para a branch `main` no GitHub.
     4. **Atualizar status**: Marcar a fase no `TASK_BOARD.md` como `PUBLICADA NO GITHUB`.

---

## 🕊️ Princípio Inegociável: Acessibilidade Universal & Custo Zero (Zero-Cost First)

> **"O Veritas Engine deve servir a qualquer cidadão, do estudante de escola pública à família mais humilde."**
> - **Prioridade para IAs 100% Gratuitas**: Suporte de primeira classe para **Google Gemini Free Tier** (grátis com conta Google comum, sem pedir cartão de crédito), **Groq Free Tier** e **Ollama Local** (custo zero de internet/tokens).
> - **Modo Cidadão Sem Chave (Fallback Direto)**: A consulta a dados abertos e evidências primárias de saúde, leis e estatísticas públicas deve funcionar mesmo que o usuário não possua nenhuma chave de IA, entregando os links e números oficiais brutos sem barreiras financeiras.
> - **Pegada Ultraleve**: Baixo consumo de memória e otimização para operar fluidamente em redes 3G/4G e dispositivos modestos.

---

## 🚦 Roadmap Oficial da Versão Alpha 1.0

| Fase | Descrição | Status Atual | Responsável |
| :--- | :--- | :--- | :--- |
| **Fase 1** | **Fundação & Core:** Estrutura FastAPI, Router BYOK multi-provedor (Gemini, Claude, OpenAI, Groq, Ollama) | `PUBLICADA NO GITHUB` | Claude Code |
| **Fase 2** | **Conectores de Fontes Primárias & App do Cidadão:** Módulos multidisciplinares assíncronos (`br_gov`, `fr_gov`, `science_health`, `legal_justice`, `global_geopolitics`, `climate_environment`, `web_archive`) + Modo Custo Zero + App Web (`app/web/`) | `PUBLICADA NO GITHUB` (Alpha 1.2, `v1.2.0-alpha`) | Claude Code |
| **Fase 3** | **Pipeline Multimodal & Forense Digital:** Extração de mídia (`yt-dlp` + FFmpeg), transcrição temporal (Whisper), validação C2PA/EXIF e Dockerização + páginas PT/EN/FR e destaque da confiança | `PUBLICADA NO GITHUB` (`main`) | Claude Code |
| **Fase 4** | **Motor de Contexto e Adaptação de Audiência:** `verdict_engine.py` com relatórios em três modos (`general_family`, `journalism_student`, `law_academic`) | `PRONTO PARA REVISÃO DO ANTIGRAVITY` | Claude Code |
| **Fase 5** | **Testes Alfa e Consolidação de Release:** Suíte completa de testes E2E, documentação e empacotamento da release Alpha 1.0 | `BACKLOG` | Claude Code |

---

## 🎯 FASE 2: Conectores de Fontes Primárias Multidisciplinares

**Status da Fase**: `PUBLICADA NO GITHUB` (Alpha 1.2, tag `v1.2.0-alpha`, mesclada em `main`)  
**Responsável**: Claude Code (Engenheiro Executor)  
**Meta**: Expandir o Veritas Engine para além do factual político básico, dotando o sistema de conectores assíncronos e resilientes para checagem em Saúde/Ciência, Geopolítica Global, Direito/Justiça, Clima/Ambiente, Governos (BR/FR), Histórico da Web e App do Cidadão acessível a custo zero.

---

### [TASK 2.1] Conector de Saúde e Ciência (`science_health.py`)
- [x] Criar módulo `backend/app/connectors/science_health.py`:
  - **PubMed / NCBI E-utilities**:
    - Busca de artigos científicos por termos-chave e autores (`esearch.fcgi`).
    - Obtenção de resumos e metadados com DOI e PMID (`esummary.fcgi` / `efetch.fcgi`).
  - **OMS / WHO GHO (Global Health Observatory)**:
    - Consulta a indicadores de saúde globais e diretrizes oficiais.
  - Implementar mapeamento para o modelo unificado de `Evidence` (com título, autores, revista, ano, DOI, link oficial e snippet).
- [x] Testes unitários com mocks em `backend/tests/test_science_health_connector.py`.

---

### [TASK 2.2] Conector de Geopolítica e Conflitos Globais (`global_geopolitics.py`)
- [x] Criar módulo `backend/app/connectors/global_geopolitics.py`:
  - **ReliefWeb API (ONU / OCHA)**:
    - Consulta a relatórios de crises humanitárias, desastres e zonas de conflito (`api.reliefweb.int/v1/reports`).
  - **GDELT Project API**:
    - Monitoramento de notícias globais, eventos internacionais e declarações de líderes mundiais via GDELT Doc 2.0 API.
  - Formatação padronizada das evidências geopolíticas com data do evento e link oficial do relatório.
- [x] Testes unitários com mocks em `backend/tests/test_geopolitics_connector.py`.

---

### [TASK 2.3] Conector Jurídico e Legislação (`legal_justice.py`)
- [x] Criar módulo `backend/app/connectors/legal_justice.py`:
  - **Legislação Brasileira**:
    - Consulta a leis, decretos federais e portarias vigentes (Portal da Legislação / Planalto).
    - Módulo de consulta a súmulas e teses de repercussão geral (STF / STJ).
  - **Legislação Internacional**:
    - Consulta a normas da União Europeia (EUR-Lex API) e decisões judiciais francesas (Cour de Cassation via PISTE/Légifrance).
  - Retorno de referências estruturadas com número de lei, artigo e ementa oficial.
- [x] Testes unitários com mocks em `backend/tests/test_legal_connector.py`.

---

### [TASK 2.4] Conector de Memória da Web (`web_archive.py`)
- [x] Criar módulo `backend/app/connectors/web_archive.py`:
  - **Wayback Machine Availability API** (`archive.org/wayback/available`):
    - Verificar snapshots históricos de uma URL suspeita.
    - Identificar se uma notícia foi alterada, se o título mudou ou se a página foi apagada após a publicação.
  - Retorno de evidência com data do snapshot original e link do arquivo no Internet Archive.
- [x] Testes unitários com mocks em `backend/tests/test_web_archive_connector.py`.

---

### [TASK 2.5] Consolidação e Refatoração dos Conectores Governamentais (`br_gov.py` & `fr_gov.py`)
- [x] Unificar os conectores existentes do Brasil em `backend/app/connectors/br_gov.py` (Câmara, Senado, IBGE e Portal da Transparência / gov.br).
- [x] Unificar os conectores existentes da França em `backend/app/connectors/fr_gov.py` (data.gouv.fr, INSEE, Légifrance / gouv.fr).
- [x] Atualizar o registro unificado em `backend/app/connectors/registry.py` para instanciar todos os conectores multidisciplinares com cliente HTTP compartilhado e cache TTL.
- [x] Garantir que 100% dos testes existentes continuem passando.

---

### [TASK 2.6] Modo Cidadão Acessível & Consulta Sem Chave (Zero-Cost Direct Fallback)
- [x] Implementar fallback gracioso quando o usuário não fornecer nenhuma chave de IA:
  - Não bloquear o usuário com erro impeditivo (HTTP 400).
  - Executar a busca direta de palavras-chave nos conectores de dados abertos (Câmara, IBGE, data.gouv.fr, PubMed, Planalto).
  - Retornar o relatório com status `SEM_CHAVE_IA_DADOS_BRUTOS` exibindo as evidências e links governamentais oficiais encontrados diretamente para a leitura do cidadão.
- [x] Garantir que o Google Gemini Free Tier e Groq Free Tier tenham tratamento prioritário e instruções de 1 clique sem requisição de cartão de crédito.

---

### [TASK 2.7] Submissão para Auditoria do Antigravity
- [x] Executar a suíte de testes com `pytest backend/tests -v`.
- [x] Atualizar o status da Fase 2 para `PRONTO PARA REVISÃO DO ANTIGRAVITY`.
- [x] Preencher as **Notas de Entrega do Claude Code (Fase 2)** no bloco abaixo.

---

## 🎯 FASE 3: Pipeline Multimodal & Forense Digital

**Status da Fase**: `PUBLICADA NO GITHUB` (mesclada em `main` com as páginas PT/EN/FR e o destaque da confiança; tag de candidata `v1.3.0-rc.1`)  
**Responsável**: Claude Code (Engenheiro Executor)  
**Meta**: Dotar o Veritas Engine da capacidade de ingerir e periciar mídias complexas (vídeos, áudios e imagens/fotos) e URLs externas (YouTube, TikTok, X, etc.), realizando extração de áudio/frames, transcrição temporal alinhada (Whisper), perícia EXIF e validação de proveniência criptográfica (C2PA) para detecção de IA.

---

### [TASK 3.1] Ambiente de Execução & Containerização (FFmpeg, ExifTool, Docker)
- [x] Criar `backend/Dockerfile` multi-stage:
  - Base Python 3.11+ slim.
  - Instalação das ferramentas de sistema: `ffmpeg`, `exiftool`, `libmagic`.
  - Instalação de dependências Python (`requirements.txt` + `yt-dlp`, `c2pa-python`).
- [x] Criar `docker-compose.yml` na raiz com o backend e volume temporário de mídia.
- [x] Adicionar helper no backend checando a disponibilidade de `ffmpeg` e `exiftool` no SO com logs claros e graceful degradation caso ausentes em ambiente Windows/bare-metal.
  - *Claude Code*: `app/forensics/tools.py` + `GET /api/v1/media/capabilities`. FFmpeg do sistema ou embutido via `imageio-ffmpeg`; EXIF de imagem via Pillow quando não há ExifTool. Dependências pesadas (`c2pa-python` ~300 MB no Windows, `imageio-ffmpeg`) ficam em `requirements-media.txt` (`.\run.ps1 -Full`); Whisper offline em `requirements-whisper.txt` (`.\run.ps1 -Whisper`). **Dockerfile/compose não foram construídos nesta máquina (Docker ausente).**

---

### [TASK 3.2] Orquestrador Forense de Mídia (`forensics/media_inspector.py`)
- [x] Criar módulo `backend/app/forensics/media_inspector.py`:
  - Ingestão de upload de arquivo (`UploadFile`) ou download seguro via `yt-dlp` de URL externa (com limite de duração e tamanho máx de 50 MB).
  - Extração da faixa de áudio em WAV mono 16kHz via FFmpeg.
  - Amostragem inteligente de keyframes (quadros representativos) via FFmpeg.
  - Extração e sanitização de metadados EXIF com `exiftool` (data, câmera, geolocalização se presente, software de edição).
- [x] Retornar modelo Pydantic `MediaForensicsReport`.
  - *Claude Code*: upload em streaming com corte em 50 MB (HTTP 413), download direto via httpx ou `yt-dlp` (limite de 15 min), tipo identificado pelos bytes (não pela extensão), SHA-256, áudio WAV 16 kHz mono, até 6 keyframes JPEG 320 px espaçados pela duração, EXIF via ExifTool ou Pillow (saneado). URLs para IPs privados/loopback recusadas (`unsafe_url`). Pasta temporária sempre apagada.

---

### [TASK 3.3] Validador de Proveniência Criptográfica C2PA (`forensics/c2pa_validator.py`)
- [x] Criar módulo `backend/app/forensics/c2pa_validator.py`:
  - Inspeção do manifesto JUMBF de proveniência em imagens (JPEG, PNG, WebP) e vídeos.
  - Integração via `c2pa-python` (ou fallback via subprocess `c2patool`).
  - Identificação de geradores de IA (DALL-E, Midjourney, Adobe Firefly, etc.) e assinaturas de captura original.
- [x] Retorno integrado no laudo pericial da mídia.
  - *Claude Code*: `c2pa-python` (sem `c2patool`). Classificação pelo `digitalSourceType` do IPTC: `AI_GENERATED`, `AI_EDITED`, `CAMERA_CAPTURE`, `EDITED`, `SIGNED_UNKNOWN`, `INVALID_SIGNATURE`, `NO_MANIFEST`, `UNAVAILABLE`. O nome do gerador (DALL-E, Firefly, Midjourney...) só decide quando o manifesto não declara o tipo. Certificado fora da lista de confiança não invalida a assinatura (é o caso comum); adulteração do conteúdo sim.

---

### [TASK 3.4] Transcrição Temporal com Timestamps (`forensics/audio_transcriber.py`)
- [x] Criar módulo `backend/app/forensics/audio_transcriber.py`:
  - Transcrição com alinhamento temporal (`start_time`, `end_time`, `text`) gerando blocos cronológicos.
  - Suporte a 3 motores (Free-Tier first):
    1. Whisper Local via `faster-whisper` / `whisper` (offline, custo zero).
    2. Provedores BYOK com suporte a áudio multimodal (Gemini ou OpenAI Whisper API).
    3. Fallback gracioso se nenhum motor de áudio estiver configurado.
  - Identificação de afirmações com marcação de minutagem (ex: *"Aos 01:23 do vídeo: ..."*).
  - *Claude Code*: motores, em ordem: **Groq Whisper** (`whisper-large-v3-turbo`, grátis com a mesma chave do Groq), **Gemini** (áudio nativo, saída JSON com tempos), OpenAI Whisper, `faster-whisper` local (`run.ps1 -Whisper`). O áudio sobe em MP3 mono 32 kbps (~15 min cabem no limite de 25 MB do Groq). Sem motor, a perícia segue e o laudo explica como ativar. Até 3 afirmações com minutagem (IA ou heurística).

---

### [TASK 3.5] Endpoints REST de Mídia & Integração com o App do Cidadão
- [x] Criar rota `POST /api/v1/fact-check/media` em `backend/app/api/v1/fact_check.py`:
  - Aceita `multipart/form-data` com arquivo de mídia ou URL externa.
  - Roda perícia forense (EXIF, C2PA), transcrição e despacha afirmações para o motor de checagem.
- [x] Atualizar o App do Cidadão (`backend/app/web/`):
  - Drag & drop para vídeos e áudios, e campo para colar URL de vídeo.
  - Visualização da timeline com vereditos por trecho do vídeo/áudio.
  - *Claude Code*: orquestração em `app/services/media_checker.py`; afirmações checadas em sequência (limites dos planos grátis). No app: botão "Enviar foto, vídeo ou áudio" (também arrastar/colar), links do YouTube/TikTok/X/Instagram detectados no campo de link, blocos **"Perícia da mídia"** e **"Linha do tempo"** (itens expansíveis com veredito e fontes), manchete "Gerada por IA"/"Contém afirmação falsa" etc.

---

### [TASK 3.6] Testes Automatizados Forenses & Handover
- [x] Criar testes unitários com mocks em `backend/tests/test_media_forensics.py`:
  - Teste de metadados EXIF sintéticos.
  - Teste de manifesto C2PA com fixture assinado/não assinado.
  - Teste de transcrição e segmentação temporal.
  - Teste da rota `POST /api/v1/fact-check/media`.
- [x] Garantir 100% de aprovação na suíte de testes (`pytest backend/tests -v`).
- [x] Atualizar a documentação (pedido do usuário, vale para todas as fases): `README.md` da raiz (como iniciar, o que o app faz, tabela de fases e versões) e `backend/README.md` (rotas, fontes, configuração, estrutura).
- [x] Atualizar status para `PRONTO PARA REVISÃO DO ANTIGRAVITY`.

---

## 🎯 FASE 4: Motor de Contexto e Adaptação de Audiência

**Status da Fase**: `PRONTO PARA REVISÃO DO ANTIGRAVITY` (branch `feat/fase-4-audiences`, commit local, sem push)
**Responsável**: Claude Code (Engenheiro Executor)
**Meta**: O mesmo conjunto de fatos e evidências oficiais, sintetizado para três públicos (`general_family`, `journalism_student`, `law_academic`), conforme o CLAUDE.md §2.3 e §4.3. *As tarefas abaixo foram detalhadas pelo Claude Code a partir do roadmap, pois o board não trazia tarefas da Fase 4.*

### [TASK 4.1] Esquemas de audiência (`schemas/audience.py`)
- [x] `AudienceMode` (`general_family`, `journalism_student`, `law_academic`) e `AudienceReport` com seções estruturadas (linha do tempo, histórico de arquivo, citações, referências jurídicas, pontos-chave, contradições), renderizáveis em qualquer idioma da página.

### [TASK 4.2] Motor de veredito com adaptação (`engines/verdict_engine.py`)
- [x] Instruções de estilo por público no prompt do veredito (sem chamada extra de IA); `LLMVerdict` ganha `key_points` e `contradictions` (validação tolerante).
- [x] Seções determinísticas, sem IA: linha do tempo, histórico da página no Internet Archive, ABNT NBR 6023 e APA 7 (DOI/PMID), nível de evidência (alto / retratado), referências jurídicas.
- [x] Regra: público nunca altera evidências, veredito nem confiança.

### [TASK 4.3] API
- [x] `audience_mode` em `POST /api/v1/fact-check/text` (JSON) e `POST /api/v1/fact-check/media` (formulário); padrão `general_family`; `FactCheckReport.audience` também no modo cidadão.

### [TASK 4.4] App do cidadão
- [x] Seletor "Para quem é a explicação?" (3 cartões, lembrado no aparelho, nos 3 idiomas).
- [x] Família: quadro "Por que é falso/verdadeiro, em 1 minuto", usado também no texto do WhatsApp. Jornalismo: método OSINT, linha do tempo, contradições, histórico da página, roteiro para refazer. Direito e pesquisa: fundamentos, referências jurídicas, ABNT/APA com botão copiar.
- [x] Troca de público após o resultado sem nova requisição; botão "Reescrever para este público" quando a explicação da IA foi escrita para outro.

### [TASK 4.5] Testes e handover
- [x] `tests/test_audience_modes.py` + extensão dos testes de idioma/mídia; documentação; status `PRONTO PARA REVISÃO DO ANTIGRAVITY`.

---

## 📝 Registro de Handovers e Comunicação

### 1. Parecer de Auditoria da Fase 1 (Antigravity - Gemini)

- **Status da Auditoria**: `APROVADO & PUBLICADO NO GITHUB`
- **Data da Avaliação**: 2026-10-14
- **Avaliação de Arquitetura**:
  - Fundação do Veritas Engine implementada com excelente rigor técnico e modularidade.
  - Motor BYOK operando com isolamento estrito de chaves por requisição.
  - Conectores governamentais base testados com 92 testes unitários.
- **Commit Registrado**: `096b7cc` na branch `main`.

---

### 2. Parecer de Auditoria da Fase 2 (Antigravity - Gemini)

- **Status da Auditoria**: `APROVADO COM LOUVOR & LIBERADO PARA TESTE DO USUÁRIO`
- **Data da Avaliação**: 2026-10-15
- **Avaliação de Arquitetura e Engenharia**:
  - **Amplitude de Fontes**: Entrega exemplar de 7 conectores multidisciplinares assíncronos (`br_gov`, `fr_gov`, `science_health`, `legal_justice`, `global_geopolitics`, `web_archive` e a excelente extensão proativa `climate_environment` com Copernicus/NOAA).
  - **Princípio Custo Zero**: Implementação primorosa da TASK 2.6 (Modo Cidadão). A consulta direta sem chave funciona com tempo de resposta de 0.2s a 1.3s com fontes oficiais reais.
  - **App do Cidadão (`app/web/`)**: Aprovado como interface oficial leve do Veritas Alpha 1.0. A solução de OCR no cliente com Tesseract.js sob demanda é genial por manter custo zero de servidor e privacidade total.
  - **Decisões Técnicas Homologadas**:
    1. *STJ Precedentes*: Exceção de timeout de 30s aprovada para downloads em lote com cache de 24h e warm-up em background.
    2. *GDELT & Wayback*: Política de best-effort mantida com fallback gracioso para garantir resiliência.
    3. *Dockerfile & Docker Compose*: Encaixados oficialmente na Fase 3 como Task 3.1.
  - **Qualidade de Testes**: **215 testes unitários e de integração passando com 100% de sucesso**.
- **Decisão**: `FASE 2 HOMOLOGADA. STATUS ALTERADO PARA 'AGUARDANDO VALIDAÇÃO DO USUÁRIO'. LIBERADA FASE 3 (PIPELINE MULTIMODAL & FORENSE) PARA O CLAUDE CODE.`

---

### 3. Notas de Entrega do Claude Code (Fase 2)

- **Status da Entrega**: `PRONTO PARA REVISÃO DO ANTIGRAVITY`
- **Data da Entrega**: 2026-10-14
- **Arquivos Criados/Modificados** (tudo em `backend/`):
  - **Novos conectores**: `app/connectors/br_gov.py` (Câmara, Senado, IBGE, Transparência), `fr_gov.py` (data.gouv.fr, INSEE Melodi, Légifrance), `legal_justice.py` (Legislação Federal, STJ precedentes, EUR-Lex, Cour de cassation/Judilibre), `science_health.py` (PubMed, OMS/WHO GHO), `global_geopolitics.py` (ReliefWeb, GDELT), `web_archive.py` (Wayback Machine), `piste.py` (OAuth PISTE compartilhado).
  - **Removidos**: `app/connectors/br/` e `app/connectors/fr/` (conteúdo consolidado em `br_gov.py` / `fr_gov.py`).
  - **Base e registro**: `connectors/base.py` (domínios, `_request` genérico GET/POST/texto, TTL por item, `disabled_reason`, `from_settings`, `warm_up`), `connectors/registry.py` (16 conectores, cliente HTTP + cache TTL compartilhados, warm-up em background).
  - **Pipeline / modo cidadão**: `services/fact_checker.py`, `services/claim_heuristics.py` (novo), `schemas/evidence.py` (`Domain`, campos acadêmicos), `schemas/fact_check.py` (`SEM_CHAVE_IA_DADOS_BRUTOS`, `ai_used`), `engines/prompt_templates/fact_check.py`.
  - **API**: `api/deps.py` (provedor opcional), `api/v1/fact_check.py`, `api/v1/connectors.py`, `api/v1/byok.py` (gratuitos primeiro), `engines/factory.py` (ordem Gemini → Groq → Ollama → pagos), `main.py`.
  - **Config/deps**: `core/config.py`, `.env.example` (credenciais opcionais), `requirements.txt` (+`defusedxml`), `README.md`.
  - **Testes novos**: `tests/test_science_health_connector.py`, `test_geopolitics_connector.py`, `test_legal_connector.py`, `test_web_archive_connector.py`, `test_gov_consolidated.py`, `test_claim_heuristics.py`; atualizados `conftest.py`, `test_fact_check_api.py`, `test_gov_connectors.py`.
- **Comandos de Teste Executados**:
  ```bash
  cd backend
  .venv/Scripts/python -m pytest tests/ -v
  .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
  ```
- **Evidências / Resultados dos Testes**:
  - `pytest`: **196 passed, 0 failed** (Python 3.13, Windows 11), sem rede: byok 43 · claim_heuristics 21 · fact_check_api 35 · geopolitics 10 · gov_connectors 25 · gov_consolidated 10 · legal 21 · science_health 15 · web_archive 16. `ruff` limpo.
  - **Validação ao vivo** (APIs reais, fora da suíte):
    - OK: Câmara, Senado, IBGE, Legislação Federal (Lei 12.965/2014, Decreto 11.000/2022, LC 101/2000), STJ precedentes, data.gouv.fr, INSEE, EUR-Lex, PubMed, OMS, Wayback (quando o Internet Archive responde a tempo).
    - Lentos/instáveis hoje: **GDELT** (10–15 s, HTTP 429) e **Wayback CDX** (2–30 s) estouram com frequência o limite de 8 s; falham de forma graciosa em `connector_failures`.
    - **Não validados ao vivo** (sem credenciais): Transparência, Légifrance, Judilibre, ReliefWeb. Testados só com mocks.
  - **Modo cidadão ponta a ponta** (servidor real, sem chave): "vacinas causam autismo" → PubMed com meta-análises que refutam; "inflação passou de 10%" → IPCA/IBGE; "Lei 12.965/2014..." → Senado + 3 temas do STJ; "chômage en France" → INSEE. Todas HTTP 200 em 0,2–1,3 s.
  - Chamada **real** ao Gemini com chave inválida → HTTP 200 em modo cidadão, sem vazar a chave.
- **Decisões Técnicas e Observações**:
  1. **TASK 2.6 (modo cidadão)**: sem `X-Provider`, com configuração inválida, chave rejeitada, cota gratuita esgotada (429) ou provedor fora do ar, a checagem devolve **HTTP 200** com `verdict = SEM_CHAVE_IA_DADOS_BRUTOS`, `ai_used = false`, as fontes oficiais e o motivo em `notes` (com links das chaves gratuitas). **Mudança de comportamento**: os antigos 400/401/429/502 desse endpoint deixaram de existir. Se a IA falhar só no veredito, as evidências já coletadas são reaproveitadas (sem nova consulta).
  2. **Free tier first**: `GET /api/v1/byok/providers` lista Gemini, Groq e Ollama primeiro, com `free_tier`, `requires_credit_card`, `get_key_url` e passo a passo de 1 clique; Swagger e README reescritos nessa ordem.
  3. **Roteamento por domínio**: cada conector declara `domains`; a triagem (IA ou heurística) identifica os domínios da alegação e só as fontes pertinentes são consultadas (saúde → PubMed/OMS; leis → Senado/STJ/EUR-Lex; URL citada → Wayback). Sem domínio identificado, vale o comportamento da Fase 1 (política + economia). EUR-Lex entra para contexto FR.
  4. **Sem IA, ainda útil**: `claim_heuristics.py` detecta país, domínios, URLs, citações de lei e traduz termos com um glossário offline PT/FR→EN, para PubMed/OMS/GDELT/EUR-Lex funcionarem sem LLM.
  5. **ReliefWeb**: a API v1 pedida no board foi **desativada (HTTP 410)**; a v2 exige `appname` **aprovado** pela ONU/OCHA. Implementado com `VERITAS_RELIEFWEB_APPNAME`; desativado até alguém solicitar o appname.
  6. **Planalto / LexML**: o Planalto não tem API e o LexML agora fica atrás de verificação anti-robô. Usei a **Legislação Federal do Senado** (mesmo acervo de normas federais), consultada por citação (tipo/número/ano); a busca por texto livre dessa API retorna vazio.
  7. **STF / STJ**: o STF não tem API aberta. Usei o dataset aberto **"precedentes qualificados" do STJ** (1.209 teses firmadas, 151 súmulas originadas, 360 vínculos com temas de repercussão geral do STF). É um CSV de ~2,5 MB que leva ~9 s para baixar: **exceção ao limite de 8 s** só para downloads em lote (`VERITAS_DATASET_TIMEOUT_SECONDS=30`, cache de 24 h, pré-carregado em background na inicialização). Peço validação dessa exceção.
  8. **EUR-Lex**: o `FILTER(CONTAINS(...))` levava 22–30 s; troquei pelo índice de texto do Virtuoso (`bif:contains`), que responde em **~0,1 s**.
  9. **GDELT e Wayback**: mantive o limite de 8 s do CLAUDE.md. GDELT sem retentativas (política de 1 requisição a cada 5 s); Wayback com no máximo 50 versões e `fastLatest` para a captura mais recente; a Availability API do Internet Archive está respondendo vazio em ~10 s e virou só fallback. **Decisão para o Antigravity**: aceitar essas fontes como best-effort ou definir um timeout maior por fonte.
  10. **Credenciais opcionais** (todas gratuitas): Transparência (`VERITAS_TRANSPARENCIA_API_KEY`), PISTE para Légifrance + Judilibre (um único token OAuth compartilhado e renovado antes de expirar), NCBI opcional. Sem credencial, o conector aparece como desativado em `GET /api/v1/connectors` e nunca bloqueia nada.
  11. **INSEE**: usei a API **Melodi** (aberta, sem chave) para o catálogo de ~150 datasets oficiais; a `api.insee.fr` clássica exige chave. Os valores numéricos das séries ainda não são baixados (link `data_api` incluído na evidência).
  12. **Evidência acadêmica**: `Evidence`/`SourceReference` ganharam `authors`, `venue`, `published_at` e `identifiers` (DOI, PMID, CELEX, norma, tema STJ, snapshot), base para o modo `law_academic` da Fase 4. PubMed marca `high_level_evidence` (meta-análise, revisão sistemática, ECR) e `retracted`.
  13. **Segurança**: XML do PubMed lido com `defusedxml`; termos sanitizados contra injeção em OData (OMS) e SPARQL (EUR-Lex); erros do OAuth PISTE nunca repetem o corpo da resposta (pode conter o segredo).
  14. **Pendência herdada da Fase 1**: o roadmap atualizado cita "Dockerfile com FFmpeg/ExifTool e Docker Compose" na Fase 1, mas isso não estava nas tarefas da Fase 1 quando ela foi entregue e **não existe no repositório**. Sugiro incluir na Fase 3 (que precisa de FFmpeg) ou criar uma tarefa própria.
  15. Nenhum commit ou push foi feito nesta fase: tudo está no working tree, aguardando auditoria e validação do usuário.

---

#### Adendo 2026-10-15: App do cidadão (pedido direto do usuário durante a validação)
- **Contexto**: ao testar, o usuário pediu uma interface bonita e simples em vez do Swagger: texto de um lado, resultado visual do outro, com fontes, tradução e entrada por imagem.
- **Entregue**: página única em `backend/app/web/` (`index.html`, `styles.css`, `app.js`; ~73 KB, sem build nem framework), servida em `GET /`. O Swagger continua em `/docs`.
  - Entrada por texto, **print/foto** (OCR Tesseract.js no navegador, carregado sob demanda: custo zero) e **link da fonte** (novo campo opcional `source_url` em `POST /api/v1/fact-check/text`, auditado na Wayback).
  - Resultado visual: selo do veredito, medidor de confiança, citações `[E1]` clicáveis, cartões de fontes por área com DOI/PMID/data, botão **Traduzir** (Translator API do navegador com tempo-limite; senão, link do Google Tradutor), compartilhamento no WhatsApp e **cartão PNG**.
  - Responsiva (celular/desktop), modo escuro automático, `prefers-reduced-motion`, dados externos sempre inseridos como texto (nunca HTML).
  - Arquivos estáticos com `Cache-Control: no-cache` (revalidação por ETag), para ninguém ficar com versão antiga após atualizações.
- **Testes**: 200 passed (novos: página e assets servidos, ausência de injeção de HTML no JS, validação de `source_url`). Verificação manual no navegador: desktop e celular, resultado com e sem IA (simulado), OCR de um print real (100% do texto) e geração do cartão PNG.
- **Ponto para o Antigravity**: esta página antecipa parte da "interface de validação" prevista no roadmap (Fase 5), sem Next.js. Sugiro decidir se ela vira a base da interface oficial ou se continua como página leve de validação. Limitação observada: sem IA, boatos com palavras genéricas podem não achar fontes (a busca por palavras-chave é literal); com Gemini/Groq gratuitos a triagem melhora.

---

#### Adendo 2026-10-15 (2): correções a partir dos testes reais do usuário
- **Nova área "Clima e ambiente"** (`app/connectors/climate_environment.py`, domínio `climate_environment`): Copernicus C3S/ECMWF (ERA5 diário, "Climate Pulse") e NOAA NCEI (anomalias anuais), sem chave. Calculam médias anuais, ranking dos anos mais quentes, anos-recorde e recordes consecutivos. Motivo: o teste do usuário sobre o Copernicus não tinha nenhuma fonte climática. Validado ao vivo: ambas confirmam 2023 e 2024 como recordes consecutivos; 2025 em 3º lugar. **Extensão de escopo para avaliação do Antigravity** (é um 7º módulo de conectores).
- **IA que falhava em silêncio**: o usuário ativou o Groq e o resultado voltou sem IA, com o motivo escondido. Correções:
  - `POST /api/v1/byok/test` testa a chave na hora; a página só ativa a IA se o teste passar e mostra o erro em linguagem simples;
  - alerta visível no resultado quando a IA falha;
  - opção "Lembrar neste aparelho" (localStorage, desligada por padrão);
  - log no servidor do motivo da falha (sem a chave);
  - validação tolerante das respostas de modelos abertos (ids `[1, 2]` → `E1, E2`, `"85%"`, `"true"`, listas longas, país/idioma por extenso).
- **Modelo Gemini padrão**: `gemini-flash-latest` (apelido do Google para o Flash atual), em vez de `gemini-2.5-flash`.
- **Afirmações vagas** (acontecimentos sem lugar/data/autor): dica visível pedindo detalhes, em vez de busca vazia sem explicação.
- **Busca sem IA**: palavras genéricas ignoradas ("vídeos", "redes sociais", "confirmando"...), glossário PT/FR→EN ampliado (geopolítica, clima); "União Europeia" sozinha não aciona mais a área jurídica.
- **Ordem das fontes**: fontes dedicadas ao tema aparecem primeiro; fontes amplas (PubMed) ficam limitadas a 3 quando as dedicadas já responderam.
- **GDELT**: intervalo mínimo de 5,5 s entre chamadas e pausa de 60 s após HTTP 429 (evita bloqueio).
- **Testes**: 215 passed (novo `tests/test_climate_and_ai_robustness.py`). Verificado no navegador: afirmação do Copernicus, teste de chave inválida (erro claro, IA não ativada) e alerta de falha da IA no resultado.

---

### 4. Validação do Usuário & Publicação Remota (Fase 2)
*(Preenchido após o gatilho de aprovação do usuário)*

- **Status de Publicação**: `PUBLICADA NO GITHUB` como **Alpha 1.2**: branch `feat/fase-2-fontes-primarias` mesclada em `main` (merge commit) e tag `v1.2.0-alpha`, a pedido explícito do usuário no chat em 2026-10-15, após validar localmente o app e o conector Groq ("conector groq funcional! quero que faça o push correto da versão alpha 1.2").
- **Instruções de Teste Apresentadas**: `cd backend` → `.\run.ps1` → abrir `http://127.0.0.1:8000` (app do cidadão) ou `/docs` (API). Passo a passo e solução de problemas no `backend/README.md`.
- **Aprovação do Usuário**: [x] SIM (validação local + pedido de publicação da Alpha 1.2) | [ ] NÃO
- **Commit Hash**: merge da Fase 2 em `main` (tag `v1.2.0-alpha`); commits da fase: `5a5106c`, `f386efe`, `2e23b89`, `1182a8f`, `6e74b67`. Tag anterior de candidata: `v0.2.0-rc.1`.
- **Correções feitas durante a validação do usuário**: diagnóstico de chaves recusadas (motivo do provedor, chaves mascaradas/incompletas, caracteres invisíveis), Gemini 400 "API key not valid" tratado como erro de chave, e escolha automática de modelo quando o padrão não está liberado para a conta (Groq respondia `model_not_found` para `llama-3.3-70b-versatile`). 223 testes passando.
- **Branch / Repositório Remoto**: `main` → https://github.com/Azhd/veritas-engine (Alpha 1.2) · branch da fase preservada: `feat/fase-2-fontes-primarias`.

---

### 5. Notas de Entrega do Claude Code (Fase 3)

- **Status da Entrega**: `PRONTO PARA REVISÃO DO ANTIGRAVITY`
- **Data da Entrega**: 2026-10-15
- **Branch**: `feat/fase-3-forense-multimodal` (a partir da `main` / `v1.2.0-alpha`). Commits locais: `52249d0` (3.1), `6def7e0` (3.2 + 3.3), `1e7a09b` (3.4), `cb373b2` (3.5) e o commit de documentação (3.6). **Nenhum push.**
- **Arquivos Criados/Modificados**:
  - **Novos**: `backend/app/forensics/` (`tools.py`, `media_inspector.py`, `c2pa_validator.py`, `audio_transcriber.py`), `app/schemas/forensics.py`, `app/api/v1/media.py`, `app/services/media_checker.py`, `backend/Dockerfile`, `backend/.dockerignore`, `docker-compose.yml`, `.gitattributes`, `backend/requirements-media.txt`, `backend/requirements-whisper.txt`, `tests/test_media_forensics.py`, `tests/c2pa_fixtures.py`.
  - **Modificados**: `engines/base.py` (`supports_audio`, `transcribe_audio`, `TranscriptionResult`), provedores Groq/OpenAI/Gemini (transcrição), `api/v1/fact_check.py` (`/media`), `api/deps.py`, `main.py`, `schemas/fact_check.py` (`TimedCheck`, `MediaFactCheckReport`), `core/config.py` e `.env.example` (limites de mídia), `requirements.txt` (Pillow, yt-dlp, python-multipart), `run.ps1`/`run.sh` (`-Full`, `-Whisper`), app web (`index.html`, `app.js`, `styles.css`), `README.md` e `backend/README.md`.
- **Comandos de Teste Executados**:
  ```bash
  cd backend
  .venv/Scripts/python -m pytest tests/ -q
  .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .
  ```
- **Evidências / Resultados dos Testes**:
  - `pytest`: **275 passed, 0 failed** (Python 3.13, Windows 11, com `requirements-media.txt` instalado), sem rede. Novos: 52 em `test_media_forensics.py` (detecção de ferramentas, identificação por bytes, SSRF (inclusive em redirecionamentos), limites de upload, EXIF sintético com GPS, inspetor com FFmpeg falso, C2PA assinado/não assinado/adulterado/IA/câmera/editado, transcrição Groq/Gemini/local, afirmações com minutagem, rota `/media`). `ruff` limpo.
  - **Validação ao vivo** (fora da suíte): vídeo real (duração + 6 keyframes), foto com EXIF (câmera, data, GPS, Photoshop), C2PA com JPEGs assinados localmente (IA, câmera, editado, IA editada, sem manifesto, adulterado), rota `/media` ponta a ponta no servidor e no navegador (imagem "Gerada por IA", quadros do vídeo, alerta de transcrição, linha do tempo), URL para `127.0.0.1` → HTTP 400 `unsafe_url`. Formato da chamada ao Groq Whisper conferido contra a API real (HTTP 401 com chave falsa).
  - **Não validado**: build da imagem Docker (Docker ausente nesta máquina) e transcrição real com chave válida do Groq/Gemini (o usuário pode testar com a própria chave).
- **Decisões Técnicas e Observações**:
  1. **Custo zero e leveza**: dependências pesadas são opcionais em camadas (`requirements-media.txt` com `c2pa-python` ~300 MB no Windows e `imageio-ffmpeg`; `requirements-whisper.txt` com `faster-whisper`). Sem elas o app sobe igual e cada etapa ausente é explicada no laudo. A imagem Docker traz tudo.
  2. **Transcrição grátis sem instalar nada**: Groq Whisper usa a mesma chave gratuita do Groq já suportada; Gemini transcreve com áudio nativo. Whisper local é a opção offline.
  3. **Sem IA**: a rota `/media` devolve a perícia completa (C2PA, EXIF, quadros) e explica como ativar a transcrição; nunca vira erro.
  4. **Segurança**: SSRF bloqueado (IPs privados/loopback/link-local; no download direto, cada redirecionamento é checado antes de ser seguido. **Limitação**: no yt-dlp só o endereço inicial é checado, pois ele segue redirecionamentos por conta própria; para produção pública, sugiro rodar o container sem acesso à rede interna), limite de bytes aplicado durante o streaming, tipo pelo conteúdo, metadados saneados, arquivos temporários sempre apagados, nenhuma mídia guardada.
  5. **Taxa dos planos grátis**: as afirmações de uma mídia são checadas em sequência (máximo 3).
  6. **C2PA**: certificados de teste/não confiáveis não invalidam a leitura (`signingCredential.untrusted` é não fatal); só a adulteração do conteúdo vira `INVALID_SIGNATURE`. Para o Antigravity: avaliar se o app deve mostrar ao cidadão quando o assinante não está numa lista de confiança.
  7. **`libmagic`** (pedido na TASK 3.1) não foi usado: a identificação de tipo é feita pelos primeiros bytes em Python puro, sem dependência de sistema.

---

#### Adendo 2026-10-15 (Fase 3): páginas PT/EN/FR e destaque da confiança (pedido direto do usuário)
- **Branch**: `feat/multilingue-confiance`, criada a partir da tag `v1.3.0-rc.1` (= Fase 3 entregue, commit `cdb542e`), que preserva a versão anterior. Status: `PUBLICADA NO GITHUB` (ver seção 6).
- **Pedido**: (1) deixar bem visível quando a confiança é alta e o fato é verdadeiro, e de outro jeito quando é quase certo que é falso; (2) páginas de idioma separadas em inglês, francês e português para todo tipo de pesquisa.
- **Entregue**:
  - `/` virou a **escolha de idioma** (3 cartões; sugere o idioma do navegador). `/pt/`, `/en/` e `/fr/` são páginas completas geradas por `app/web_pages.py` a partir de `web/index.html` (modelo `{{chave}}`) e de `web/i18n/{pt,en,fr}.json` (~300 textos cada, mesmas chaves). Botões **PT · EN · FR** no topo de todas as páginas.
  - Todo tipo de pesquisa funciona nos 3 idiomas: texto, print/foto (OCR no idioma da página), link, vídeo/áudio. A página envia `language` (novo campo opcional em `POST /api/v1/fact-check/text` e no formulário de `/media`); a explicação da IA e o texto do modo cidadão saem nesse idioma (inglês adicionado ao modo cidadão).
  - Afirmações **em inglês sem IA**: detecção de idioma por palavras funcionais (o idioma da página desempata), palavras vazias e gatilhos de área em inglês, e as palavras da própria afirmação passam a consultar PubMed/OMS/GDELT/EUR-Lex.
  - Notas e erros do servidor (em português) são traduzidos na página (`NOTE_RULES` no `app.js`); o resumo C2PA é montado no idioma da página a partir dos campos estruturados.
  - **Confiança**: régua **Falso ↔ Verdadeiro** com marcador animado em todo veredito com IA. ≥ 80% em Verdadeiro/Falso/Enganoso → cartão todo colorido (verde; vermelho listrado; laranja), ícone grande e **carimbo** "CONFIRMADO" / "FALSO" / "ENGANOSO"; 55–79% → "provavelmente…"; < 55% → cartão discreto com "confiança baixa: leia as fontes". Mesma lógica na linha do tempo de mídia (pílula sólida + %), no cartão PNG e no texto do WhatsApp.
- **Testes**: 298 passed (novo `tests/test_i18n_and_confidence.py`, 21 testes: páginas, redirecionamento `/en` → `/en/`, paridade de chaves e de `{marcadores}` entre os 3 dicionários, toda chave usada no JS/modelo existe, escape do JSON embutido, idioma da resposta no prompt e no modo cidadão, `language` na rota de mídia, detecção de idioma). `ruff` limpo.
- **Verificado no navegador**: escolha de idioma; página EN com checagem real sem IA (PubMed + OMS, explicação em inglês); resultados simulados com IA: Falso 96% (PT), Verdadeiro 93% (EN), Enganoso 68% e Verdadeiro 40% (FR, celular, modo claro); cartão PNG em francês; laudo de mídia simulado em inglês (C2PA, alerta de transcrição, linha do tempo). Corrigida a sobreposição do seletor de idioma com a marca no celular.
- **Não verificado**: veredito real com IA nos 3 idiomas (precisa de chave do usuário). A rota `/` deixou de abrir o app direto: quem tinha o link antigo passa pela escolha de idioma.
- **Para o Antigravity**: a API continua devolvendo `notes` em português (a tradução é feita na página). Se terceiros forem consumir a API em outros idiomas, sugiro mover essas mensagens para um catálogo no backend.
- **Correções após o teste real do usuário (Groq, página FR)**:
  - Vereditos "Inconclusivo" e "Sem dados suficientes" não mostram mais porcentagem: a confiança do modelo nesses casos mede o quanto ele tem certeza de que *não dá para decidir*, e aparecia como "20% de confiança" ao lado de 6 fontes, parecendo baixa confiabilidade. Agora: marcador no centro da régua e "nem verdadeiro nem falso". "Sem dados suficientes" com fontes encontradas diz que as fontes não tratam diretamente da afirmação (antes dizia que nenhuma fonte foi encontrada).
  - **EUR-Lex**: buscava a frase exata ("european copyright directive") ou palavras francesas contra títulos em inglês, e não achava a Diretiva (UE) 2019/790. Agora busca palavras (AND), remove palavras genéricas (europeia, adotada...), tenta termos em inglês e depois a língua da afirmação (títulos em FR/PT), e reduz a busca até 2 palavras no mínimo. Novo campo `language` em `EvidenceQuery`. Verificado ao vivo: "La directive européenne sur le droit d'auteur a été adoptée en 2019" → Diretiva 2019/790.
  - Limite conhecido: "decreto secreto" (boato das patinetes) só pode ser desmentido pela ausência no Légifrance, que exige credencial PISTE gratuita (desativado sem ela).
  - 300 testes passando.

---

### 6. Validação do Usuário & Publicação Remota (Fase 3 + páginas PT/EN/FR)

- **Status de Publicação**: `PUBLICADA NO GITHUB` na `main`.
- **Histórico**: o próprio usuário enviou as branches `feat/fase-3-forense-multimodal` e `feat/multilingue-confiance` e mesclou a Fase 3 + páginas PT/EN/FR na `main` (merge `4c42d63`). Depois de testar localmente com o Groq (página FR), pediu no chat em 2026-10-15: "Push sur la version stable sans ma clé api bien sûr". As correções feitas a partir desse teste (confiança dos vereditos indecisos, busca no EUR-Lex, gatilhos de clima e glossário paracetamol/gravidez) foram mescladas na `main` e enviadas.
- **Varredura de segredos**: `.env` ignorado pelo `.gitignore`; só `backend/.env.example` (valores vazios) é versionado; nenhum padrão de chave (`gsk_`, `AIza`, `sk-ant-`, `sk-proj-`) nos commits enviados. A chave do usuário fica só no navegador/`.env` local.
- **Aprovação do Usuário**: [x] SIM | [ ] NÃO
- **Branch / Repositório Remoto**: `main` → https://github.com/Azhd/veritas-engine · branches preservadas: `feat/fase-3-forense-multimodal`, `feat/multilingue-confiance`.

---

#### Adendo 2026-10-15 (pós Alpha 1.3): qualidade das fontes (branch `feat/qualite-sources`, commit local, sem push)
- **EUR-Lex**: o ano citado ("adotado em 2024") e o tipo de ato (diretiva / regulamento / decisão, em PT/FR/EN) restringem a busca primeiro e são relaxados se nada aparecer; os resultados são reordenados (ato do ano citado → leis do Parlamento e do Conselho → retificações/atos de execução por último), pois a ordem por data colocava emendas recentes antes do ato original. A sigla "AI"/"IA" (só em maiúsculas: "ia" é verbo em português) vira "artificial intelligence". Afirmação que fala da Europa consulta o EUR-Lex mesmo com país BR, e ele vem primeiro. Verificado ao vivo: o AI Act (Regulamento (UE) 2024/1689) aparece em 1º nas afirmações em PT, EN e FR; a Diretiva 2019/790 continua em 1º/2º.
- **Brasil em qualquer idioma**: "Brésil"/"Brazil" reconhecidos; o IBGE aceita gatilhos em FR/EN (population, habitants, inhabitants, chômage, unemployment, inflation, prix...). Verificado ao vivo: "Le Brésil compte plus de 200 millions d'habitants" / "Brazil has more than 200 million inhabitants" → população IBGE 2026 = 214.211.951.
- **Anos citados** (`ClaimAnalysis.years`, `EvidenceQuery.years`), sem confundir com números de lei ou valores.
- **Testes**: 317 passed (novo `tests/test_source_quality.py`, 17 testes). `ruff` limpo.

---

### 7. Notas de Entrega do Claude Code (Fase 4)

- **Status da Entrega**: `PRONTO PARA REVISÃO DO ANTIGRAVITY`
- **Data da Entrega**: 2026-10-15
- **Branch**: `feat/fase-4-audiences`, criada de `feat/qualite-sources` (que traz as melhorias de fontes pós Alpha 1.3, ainda não publicadas). Commits locais, **sem push**.
- **Arquivos**: novos `app/schemas/audience.py`, `app/engines/verdict_engine.py`, `tests/test_audience_modes.py`; alterados `schemas/fact_check.py` (`audience_mode`, `LLMVerdict.key_points/contradictions`, `FactCheckReport.audience`), `prompt_templates/fact_check.py`, `services/fact_checker.py`, `services/media_checker.py`, `api/v1/fact_check.py`, app web (`index.html`, `app.js`, `styles.css`, `i18n/*.json` com 54 textos novos por idioma), READMEs.
- **Testes**: **328 passed**, `ruff` limpo.
- **Verificado**: ao vivo sem IA (FR, "Les vaccins ROR provoquent l'autisme"): referências ABNT/APA corretas com DOI e selo de alto nível de evidência na meta-análise, linha do tempo de 2014 a 2025, troca para Jornalismo sem nova requisição; com resultado de IA simulado: quadro "Pourquoi c'est faux, en 1 minute", texto do WhatsApp com os pontos, aviso de reescrita ao trocar de público; seletor no celular (EN).
- **Não verificado**: explicações reais da IA nos três estilos (precisa da chave do usuário).
- **Decisões**:
  1. Uma única chamada de IA por checagem: o estilo vai no prompt do veredito, e as seções objetivas são calculadas sem IA. Trocar de público reaproveita tudo; só a explicação precisa ser reescrita (nova checagem, sob demanda).
  2. ABNT segue a convenção brasileira em português ("Disponível em", "Acesso em") e APA em inglês, em qualquer idioma da página, como pedem as normas.
  3. Não há "modo" no servidor que esconda dados: a resposta traz todas as seções; o público decide o que o app mostra primeiro (auditabilidade).
