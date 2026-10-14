# TASK_BOARD.md - Painel de Controle e Handover (Veritas Engine)

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
   - O agente ativo (Antigravity ou Claude Code) deve **iniciar o servidor local de testes** e apresentar na tela o passo a passo exato para o usuário testar (endpoints Swagger `/docs`, cURL de exemplo, credenciais de teste).
   - **É TERMINANTEMENTE PROIBIDO executar `git push` automático antes da aprovação explícita do usuário no chat.**

2. **GATILHO AUTOMÁTICO DE COMMIT & PUSH**:
   - Enquanto o usuário testa, são permitidos commits locais de segurança (`git commit`).
   - Assim que o usuário enviar no chat **"Validado"**, **"Aprovado"** ou **"Pode subir"**, o agente ativo deve **automaticamente e sem hesitação**:
     1. **Verificar segredos**: Garantir que `.env` está explicitamente no `.gitignore` e nenhuma chave de API ou credencial está nos arquivos indexados.
     2. **Commit semântico**: Executar `git add .` e `git commit` seguindo o padrão *Conventional Commits* (ex: `feat: implement br_gov transparency API connector`).
     3. **Push remoto**: Executar `git push` para o GitHub (configurando o remote `origin` se for o primeiro envio).
     4. **Atualizar status**: Marcar a fase/tarefa no `TASK_BOARD.md` como `PUBLICADA NO GITHUB`.

---

## 🚦 Visão Geral das Fases

| Fase | Descrição | Status Atual | Responsável |
| :--- | :--- | :--- | :--- |
| **Fase 1** | **Fundação do Veritas Engine: Arquitetura Core, Motor BYOK & Conectores Base (BR/FR)** | `PRONTO PARA REVISÃO DO ANTIGRAVITY` | Claude Code |
| **Fase 2** | Pipeline Multimodal Avançado (C2PA, Forense de Imagem, Whisper para Áudio/Vídeo) | `BACKLOG` | Claude Code |
| **Fase 3** | Conectores Governamentais Avançados (Senado, Transparência/CGU, INSEE, Légifrance) | `BACKLOG` | Claude Code |
| **Fase 4** | Interface Web Reativa (Next.js, Upload Multimodal, Dashboard de Auditoria & Painel BYOK) | `BACKLOG` | Claude Code |
| **Fase 5** | Hardening, Auditoria Criptográfica de Evidências, Dockerização & Release Open Source | `BACKLOG` | Claude Code & Antigravity |

---

## 🎯 FASE 1: Fundação do Veritas Engine (Core, BYOK & Conectores Base)

**Status da Fase**: `PRONTO PARA REVISÃO DO ANTIGRAVITY`  
Status: PRONTO PARA REVISÃO DO ANTIGRAVITY  
**Meta**: Deixar o backend operacional com o motor BYOK ativo (Gemini, Claude, OpenAI, Groq, Ollama), conectores base do Brasil e França funcionais com cache/resiliência, endpoint inicial de fact-checking e suíte de testes passando.

---

### [TASK 1.1] Setup do Ambiente Backend e Estrutura Modular
- [x] Criar a pasta `backend/` com a arquitetura definida no `CLAUDE.md`.
- [x] Criar `backend/requirements.txt` com as dependências essenciais:
  - `fastapi`, `uvicorn[standard]`, `pydantic>=2.0`, `httpx`, `pytest`, `pytest-asyncio`, `python-dotenv`.
  - SDKs de IA: `google-genai` (ou `google-generativeai`), `anthropic`, `openai`, `groq`.
- [x] Criar `.gitignore` na raiz garantindo que `.env`, `__pycache__`, `.pytest_cache`, `.venv` e mídias temporárias fiquem ignorados.
- [x] Criar `backend/.env.example` com placeholders de configuração.
- [x] Criar a aplicação FastAPI base em `backend/app/main.py` com health check (`GET /healthz`) e documentação Swagger ativa.
- [x] Configurar script de inicialização e instruções claras de execução local.

---

### [TASK 1.2] Motor BYOK (Bring Your Own Key) & Provider Factory
- [x] Criar interface abstrata `BaseLLMProvider` em `backend/app/engines/base.py`:
  - Métodos: `generate_text(prompt, system_instruction, temperature)`, `generate_structured(prompt, schema)`.
- [x] Implementar os adaptadores em `backend/app/engines/providers/`:
  - `gemini_provider.py` (Google Gemini)
  - `claude_provider.py` (Anthropic Claude)
  - `openai_provider.py` (OpenAI / GPT-4o)
  - `groq_provider.py` (Groq / Llama 3 rápida)
  - `ollama_provider.py` (Modelos locais via endpoint REST configurável)
- [x] Criar a `ProviderFactory` em `backend/app/engines/factory.py` que instancia o provedor correto a partir dos headers HTTP da requisição (`X-Provider`, `X-API-Key`, `X-Endpoint-URL`) ou variáveis de ambiente de fallback.
- [x] Escrever testes unitários em `backend/tests/test_byok_providers.py` com mocks para validar a injeção dinâmica de chaves sem vazamento de estado.

---

### [TASK 1.3] Conectores Governamentais Base (Brasil & França)
- [x] Criar conector HTTP base em `backend/app/connectors/base.py` com suporte a:
  - Timeout estrito (ex: 8s).
  - Retries automáticos com backoff exponencial para erros transitórios (5xx, timeouts).
  - Cache local em memória (LRU ou dict com TTL) para evitar sobrecarregar os servidores públicos.
- [x] **Conector Brasil (BR)** em `backend/app/connectors/br/`:
  - `camara_connector.py`: Busca de proposições e discursos na API da Câmara dos Deputados (`https://dadosabertos.camara.leg.br/api/v2`).
  - `ibge_connector.py`: Consulta a indicadores econômicos/populacionais (`https://servicodados.ibge.gov.br/api/v1`).
- [x] **Conector França (FR)** em `backend/app/connectors/fr/`:
  - `data_gouv_connector.py`: Consulta a datasets e recursos na API pública (`https://www.data.gouv.fr/api/1/`).
- [x] Escrever testes em `backend/tests/test_gov_connectors.py` usando mocks de respostas HTTP para garantir resiliência e validação dos modelos Pydantic.

---

### [TASK 1.4] Pipeline Inicial de Fact-Checking e Endpoint MVP
- [x] Criar schema Pydantic para o relatório de checagem em `backend/app/schemas/fact_check.py`:
  - `claim`: Afirmação sob análise.
  - `verdict`: Enum (`VERDADEIRO`, `FALSO`, `ENGANOSO`, `INCONCLUSIVO`, `SEM_DADOS_SUFICIENTES`).
  - `confidence_score`: Float de 0.0 a 1.0.
  - `primary_sources`: Lista de URLs e metadados das fontes oficiais consultadas.
  - `explanation`: Síntese justificativa detalhada com menção aos dados públicos encontrados.
- [x] Criar serviço orquestrador `backend/app/services/fact_checker.py`:
  - 1. Recebe o texto da alegação.
  - 2. Identifica o país de contexto (BR, FR ou Ambos) e termos-chave de busca.
  - 3. Consulta os conectores de dados abertos pertinentes.
  - 4. Constrói o prompt com as evidências recuperadas.
  - 5. Executa a análise via provedor BYOK configurado.
  - 6. Retorna o relatório estruturado.
- [x] Criar rota `POST /api/v1/fact-check/text` em `backend/app/api/v1/fact_check.py`.
- [x] Criar testes de integração em `backend/tests/test_fact_check_api.py`.

---

### [TASK 1.5] Handover & Submissão para Auditoria do Antigravity
- [x] Executar toda a suíte de testes com `pytest` e garantir 100% de aprovação.
- [x] Atualizar o status da Fase 1 abaixo para `PRONTO PARA REVISÃO DO ANTIGRAVITY`.
- [x] Preencher o campo **"Notas de Entrega do Claude Code"** abaixo.

---

### [TASK 1.6] Validação do Usuário & Publicação no GitHub
- [ ] Antigravity / Claude Code inicia servidor local (`uvicorn app.main:app --reload`) e exibe rota de testes para o usuário.
- [ ] Alterar status para `AGUARDANDO VALIDAÇÃO DO USUÁRIO`.
- [ ] Aguardar mensagem do usuário ("Validado", "Aprovado", "Pode subir").
- [ ] Verificar ausência de segredos / arquivos `.env`.
- [ ] Executar `git add .` e `git commit -m "feat: ..."` (Conventional Commits).
- [ ] Executar `git push` para o GitHub.
- [ ] Atualizar status para `PUBLICADA NO GITHUB`.

---

## 📝 Registro de Handovers e Comunicação

### 1. Notas de Entrega do Claude Code (Fase 1)

- **Status da Entrega**: `PRONTO PARA REVISÃO DO ANTIGRAVITY`
- **Data da Entrega**: 2026-10-14
- **Arquivos Criados/Modificados**:
  - Raiz: `.gitignore` (novo: `.env`, `__pycache__`, `.pytest_cache`, `.venv`, mídias temporárias), `TASK_BOARD.md` (este handover).
  - `backend/`: `requirements.txt`, `pyproject.toml` (pytest + ruff), `.env.example`, `README.md`, `run.ps1`, `run.sh`.
  - **Core**: `app/main.py` (`create_app()`, lifespan, CORS, `GET /healthz`, Swagger em `/docs`), `app/core/config.py` (pydantic-settings, prefixo `VERITAS_`), `app/core/errors.py` (hierarquia de erros → HTTP 400/401/429/502/503 com corpo `{"error": {code, message}}`).
  - **BYOK (1.2)**: `app/engines/base.py` (`BaseLLMProvider` com `generate_text` / `generate_structured`, `ProviderCredentials`), `app/engines/factory.py` (`ProviderFactory`), `app/engines/json_utils.py`, `app/engines/providers/{gemini,claude,openai,groq,ollama}_provider.py`, `app/engines/providers/_errors.py`.
  - **Conectores (1.3)**: `app/connectors/base.py` (`BaseGovConnector`, `TTLCache`, `build_http_client`), `app/connectors/br/camara_connector.py`, `app/connectors/br/ibge_connector.py`, `app/connectors/fr/data_gouv_connector.py`, `app/connectors/registry.py`.
  - **Pipeline (1.4)**: `app/schemas/evidence.py`, `app/schemas/fact_check.py`, `app/engines/prompt_templates/fact_check.py`, `app/services/fact_checker.py`, `app/api/deps.py`, `app/api/v1/fact_check.py` (`POST /api/v1/fact-check/text`), `app/api/v1/byok.py` (`GET /api/v1/byok/providers`, extra).
  - **Testes**: `tests/conftest.py`, `tests/test_byok_providers.py`, `tests/test_gov_connectors.py`, `tests/test_fact_check_api.py`.
- **Comandos de Teste Executados**:
  ```bash
  cd backend
  python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
  .venv/Scripts/python -m pytest -v
  .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
  ```
- **Evidências / Resultados dos Testes**:
  - `pytest`: **92 passed, 0 failed** (Python 3.13.14, Windows 11): `test_byok_providers.py` 43 · `test_gov_connectors.py` 24 · `test_fact_check_api.py` 25. Nenhum teste acessa a rede.
  - `ruff check` e `ruff format --check`: sem apontamentos.
  - Smoke test com Uvicorn real: `/healthz` 200, `/docs` 200, `POST /api/v1/fact-check/text` sem chave → 400 `provider_configuration_error` (comportamento esperado).
  - Smoke test **ao vivo** dos 3 conectores contra as APIs públicas reais (fora da suíte): Câmara (proposições), IBGE (IPCA 12m, desocupação PNAD, população estimada) e data.gouv.fr (datasets) retornaram evidências válidas.
  - **Não validado**: chamadas reais aos 5 provedores de IA (sem chaves disponíveis nesta sessão); os adaptadores foram testados com SDKs/HTTP mockados.
- **Decisões Técnicas e Observações**:
  1. **Divergência CLAUDE.md × TASK_BOARD**: segui o TASK_BOARD (atribuição vigente): `engines/base.py` + `engines/factory.py` (e não `provider_factory.py`) e métodos `generate_text` / `generate_structured`. `generate_stream` e `analyze_multimodal` (citados no CLAUDE.md §3.1) ficam para a Fase 2. Sugiro alinhar o CLAUDE.md.
  2. **Isolamento BYOK**: um provedor (e cliente SDK) novo por requisição, descartado (`aclose`) ao fim via dependência FastAPI; chave guardada em `SecretStr`, oculta em `repr`. Erros dos SDKs são convertidos em mensagens genéricas, sem repassar o corpo do provedor (que pode ecoar dados). Testes cobrem chaves distintas por requisição e ausência da chave nas respostas.
  3. **Fallback de ambiente**: sem `X-API-Key`, usa `VERITAS_<PROVIDER>_API_KEY` se `VERITAS_ALLOW_ENV_FALLBACK=true` (padrão). **Para deploy público/multi-tenant recomendo `false`**, senão usuários anônimos consomem a chave do servidor.
  4. **SSRF / `X-Endpoint-URL`**: aceito apenas para `ollama` e `openai` (OpenAI-compatible), só `http(s)` absoluto, sem credenciais embutidas, desligável com `VERITAS_ALLOW_CUSTOM_ENDPOINTS=false`. Não há bloqueio de IPs privados porque o caso de uso principal é Ollama em `localhost`; em deploy público isso precisa de allowlist (item para a Fase 5).
  5. **Saída estruturada**: Gemini usa `response_json_schema` nativo; Ollama usa `format` com JSON Schema; OpenAI/Groq usam `json_object`; Claude via instrução de sistema. Em todos, validação final por Pydantic com 1 retentativa informando o erro.
  6. **Claude**: o SDK `anthropic` atual não expõe `temperature` em `messages.create`; o parâmetro é aceito pela interface mas não repassado. Modelo padrão `claude-sonnet-5-5` (configurável).
  7. **Auditabilidade do veredito**: `primary_sources` contém **apenas** evidências realmente recuperadas pelos conectores (IDs `E1..En`); citações inventadas pelo LLM são descartadas e registradas em `notes`. Vereditos `VERDADEIRO`/`FALSO`/`ENGANOSO` sem nenhuma citação válida são rebaixados para `INCONCLUSIVO` (havia evidências) ou `SEM_DADOS_SUFICIENTES` (não havia), com confiança limitada a 0.5.
  8. **Triagem (passo 2)**: LLM extrai país/termos/pessoas/temas; se a saída for inválida, cai para heurística local (marcadores BR/FR + stopwords). Erros de autenticação/limite **não** caem para heurística: propagam como 401/429. `country` no corpo da requisição força o contexto.
  9. **Resiliência dos conectores**: timeout de 8s, até 3 retries com backoff exponencial (0.5s, 1s, 2s; teto 8s) em timeout/erro de transporte/408/425/429/5xx, respeitando `Retry-After`; 4xx não é retentado. Cache TTL+LRU em memória compartilhado (15 min, 1024 entradas); erros não são cacheados. Falha de um conector não derruba a checagem: aparece em `connector_failures`.
  10. **IBGE**: o endpoint v1 de projeção populacional (`/api/v1/projecoes/populacao`) hoje responde **404**; a população vem da tabela SIDRA 6579 (estimativas anuais). Indicadores do catálogo: IPCA 12m (1737/2265), desocupação PNAD (4099/4099), população (6579/9324), todos validados ao vivo.
  11. **TLS**: o servidor do IBGE não envia a cadeia de certificados completa, o que quebra o bundle `certifi` do Python. Adicionei `truststore` (usa o repositório de certificados do SO). A verificação TLS continua ativa.
  12. **Câmara**: sem filtro de data a API devolve só itens recentes; o conector usa `dataApresentacaoInicio` = hoje − 6 anos (proposições) e últimos 365 dias (discursos, apenas para pessoas citadas, no máximo 2 por checagem).
  13. Nenhum commit nem push foi feito: os arquivos estão no working tree (branch `master`). A TASK 1.6 (validação do usuário + publicação) fica para depois da auditoria, conforme o ciclo de vida.

---

### 2. Parecer de Auditoria do Antigravity (Gemini)
*(O Antigravity preencherá este bloco após auditar a entrega do Claude Code)*

- **Status da Auditoria**: `PENDENTE`
- **Data da Avaliação**: *Aguardando entrega do Claude Code*
- **Avaliação de Arquitetura**:
- **Conformidade de Segurança e BYOK**:
- **Decisão**: [ ] APROVADO PARA TESTE DO USUÁRIO | [ ] AJUSTES SOLICITADOS

---

### 3. Validação do Usuário & Publicação Remota
*(Preenchido após o gatilho de aprovação do usuário)*

- **Status de Publicação**: `PENDENTE`
- **Instruções de Teste Apresentadas**:
- **Aprovação do Usuário**: [ ] SIM (`chat: "Validado" / "Aprovado"`) | [ ] NÃO
- **Commit Hash**:
- **Branch / Repositório Remoto**:
