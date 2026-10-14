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
| **Fase 1** | **Fundação & Core:** Estrutura FastAPI, Dockerfile com FFmpeg/ExifTool, Docker Compose e Router BYOK multi-provedor (Gemini, Claude, OpenAI, Groq, Ollama) | `PUBLICADA NO GITHUB` | Claude Code |
| **Fase 2** | **Conectores de Fontes Primárias:** Módulos assíncronos em `connectors/` (`br_gov.py`, `fr_gov.py`, `science_health.py`, `legal_justice.py`, `global_geopolitics.py`, `web_archive.py`) | `PRONTO PARA REVISÃO DO ANTIGRAVITY` | Claude Code |
| **Fase 3** | **Pipeline Multimodal & Forense:** Motor de extração de mídia (`yt-dlp` + FFmpeg), transcrição temporal (Whisper) e validação de imagem/C2PA em `forensics/media_inspector.py` | `BACKLOG` | Claude Code |
| **Fase 4** | **Motor de Contexto e Adaptação de Audiência:** `verdict_engine.py` com relatórios em três modos (`general_family`, `journalism_student`, `law_academic`) | `BACKLOG` | Claude Code |
| **Fase 5** | **Testes Alfa e Interface de Validação:** Testes integrados ponta a ponta com `pytest`, rota funcional no FastAPI e playground web | `BACKLOG` | Claude Code |

---

## 🎯 FASE 2: Conectores de Fontes Primárias Multidisciplinares

**Status da Fase**: `PRONTO PARA REVISÃO DO ANTIGRAVITY`  
Status: PRONTO PARA REVISÃO DO ANTIGRAVITY  
**Responsável**: Claude Code (Engenheiro Executor)  
**Meta**: Expandir o Veritas Engine para além do factual político básico, dotando o sistema de conectores assíncronos e resilientes para checagem em Saúde/Ciência, Geopolítica Global, Direito/Justiça, Governos (BR/FR) e Histórico da Web.

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

### 2. Notas de Entrega do Claude Code (Fase 2)

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

### 3. Validação do Usuário & Publicação Remota (Fase 2)
*(Preenchido após o gatilho de aprovação do usuário)*

- **Status de Publicação**: `PENDENTE`
- **Instruções de Teste Apresentadas**:
- **Aprovação do Usuário**: [ ] SIM | [ ] NÃO
- **Commit Hash**:
- **Branch / Repositório Remoto**: `main`
