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
   - O agente ativo (Antigravity ou Claude Code) deve **iniciar o servidor local de testes** e apresentar na tela o passo a passo exato para o usuário testar (endpoints Swagger `/docs`, cURL de exemplo, interface web).
   - **É TERMINANTEMENTE PROIBIDO executar `git push` automático antes da aprovação explícita do usuário no chat.**

2. **GATILHO AUTOMÁTICO DE COMMIT & PUSH**:
   - Enquanto o usuário testa, são permitidos commits locais de segurança (`git commit`).
   - Assim que o usuário enviar no chat **"Validado"**, **"Aprovado"** ou **"Pode subir"**, o agente ativo deve **automaticamente e sem hesitação**:
     1. **Verificar segredos**: Garantir que `.env` está explicitamente no `.gitignore` e nenhuma chave de API ou credencial está nos arquivos indexados.
     2. **Commit semântico**: Executar `git add .` e `git commit` seguindo o padrão *Conventional Commits* (ex: `feat: implement web playground and byok modal`).
     3. **Push remoto**: Executar `git push` para o GitHub na branch `main`.
     4. **Atualizar status**: Marcar a fase/tarefa no `TASK_BOARD.md` como `PUBLICADA NO GITHUB`.

---

## 🚦 Visão Geral das Fases

| Fase | Descrição | Status Atual | Responsável |
| :--- | :--- | :--- | :--- |
| **Fase 1** | **Fundação do Veritas Engine: Arquitetura Core, Motor BYOK & Conectores Base (BR/FR)** | `PUBLICADA NO GITHUB` | Claude Code |
| **Fase 2** | **Interface Web Reativa & Playground BYOK Integrado (UI/UX)** | `EM PROGRESSO` | Claude Code |
| **Fase 3** | Pipeline Multimodal Avançado (C2PA, Forense de Imagem, Whisper para Áudio/Vídeo) | `BACKLOG` | Claude Code |
| **Fase 4** | Conectores Governamentais Avançados (Senado, Transparência/CGU, INSEE, Légifrance) | `BACKLOG` | Claude Code |
| **Fase 5** | Hardening, Auditoria Criptográfica de Evidências, Dockerização & Release Open Source | `BACKLOG` | Claude Code & Antigravity |

---

## 🎯 FASE 2: Interface Web Reativa & Playground BYOK Integrado (UI/UX)

**Status da Fase**: `EM PROGRESSO`  
**Responsável**: Claude Code (Engenheiro Executor)  
**Meta**: Eliminar a dependência do Swagger para testes humanos, entregando uma interface web limpa, moderna, em tema escuro, servida diretamente pelo backend FastAPI em `http://127.0.0.1:8000/`. A interface deve guiar o usuário com links diretos para obter as chaves de cada provedor, oferecer campo espaçoso de texto com exemplos em 1 clique e exibir o veredito com links diretos para os portais oficiais (`.gov.br` e `.gouv.fr`).

---

### [TASK 2.1] Arquitetura de UI e Assets Estáticos no Backend
- [ ] Configurar montagem de diretório de arquivos estáticos em `backend/app/main.py`:
  - `static_dir = Path(__file__).resolve().parent / "static"`
  - Montar `/static` via `StaticFiles(directory=static_dir)` (se existir).
  - Criar rota raiz `GET /` que retorna `FileResponse(static_dir / "index.html")`.
- [ ] Criar o arquivo `backend/app/static/index.html` com layout SPA moderno:
  - Estilização via Tailwind CSS (CDN) com tema dark (`slate-950`, `slate-900`, `slate-800`).
  - Tipografia limpa (Inter/System Font) e ícones inline limpos ou Lucide.
  - Header com logotipo do Veritas Engine, badge de versão (`v0.1.0`), link para Swagger `/docs` e botão de status de conexão BYOK.

---

### [TASK 2.2] Modal Inteligente BYOK com Links Diretos de Conexão
- [ ] Criar modal ou drawer responsivo acessível pelo botão **"🔑 Conectar Minha Chave"** no topo.
- [ ] Seletor de Provedor com cartões visuais para:
  - **Google Gemini** (Recomendado / Grátis)
  - **Groq** (Llama 3.3 / Rápido)
  - **OpenAI** (GPT-4o)
  - **Anthropic Claude** (Claude Sonnet)
  - **Ollama** (Modelo Local offline)
- [ ] **Links oficiais diretos e instruções claras para cada provedor**:
  - Gemini: link direto para `https://aistudio.google.com/app/apikey` com texto: *"Obter chave gratuita no Google AI Studio"*.
  - Groq: link direto para `https://console.groq.com/keys` com texto: *"Obter chave no Groq Cloud"*.
  - OpenAI: link direto para `https://platform.openai.com/api-keys`.
  - Anthropic: link direto para `https://console.anthropic.com/settings/keys`.
  - Ollama: link direto para `https://ollama.com/download` com instrução do comando de terminal `ollama run llama3.1`.
- [ ] Input para a chave de API (com toggle de visualização/máscara de senha).
- [ ] Input para endpoint customizado (visível quando Ollama estiver selecionado, default `http://localhost:11434`).
- [ ] Persistência segura e estritamente local em `localStorage` do navegador (`veritas_provider`, `veritas_api_key`, `veritas_endpoint_url`).
- [ ] Indicador visual no cabeçalho: se a chave estiver configurada, badge verde com o nome do provedor ativo (ex: `GEMINI ATIVO` 🟢); se não, badge âmbar pulsante (`CONFIGURAR CHAVE` 🟡).

---

### [TASK 2.3] Formulário de Checagem & Exemplos Rápidos em 1 Clique
- [ ] Seletor de país/contexto oficial com botões visíveis:
  - `🇧🇷 Brasil` (Câmara + IBGE)
  - `🇫🇷 França` (data.gouv.fr)
  - `🌐 Ambos / Automático`
- [ ] Textarea ampla, limpa e responsiva para colar notícias, boatos ou declarações.
- [ ] Bloco de **Exemplos Rápidos em 1 Clique** (ao clicar, preenche automaticamente o texto e o país no formulário):
  - *🇧🇷 Censo e População (IBGE)*: `"O IBGE divulgou dados sobre a população do Brasil."`
  - *🏛️ Proposição na Câmara*: `"A Câmara dos Deputados aprovou a taxação de compras internacionais."`
  - *🇫🇷 Données Officielles (France)*: `"L'INSEE et data.gouv.fr ont publié les données officielles du chômage."`
- [ ] Botão de envio destacado: **"🔍 Verificar com Fontes Oficiais"**.
- [ ] Animação de carregamento (Live Feedback) com indicadores dos conectores consultados em tempo real (Câmara, IBGE, data.gouv.fr).

---

### [TASK 2.4] Painel de Resultados: Veredito, Confiança e Fontes Clicáveis
- [ ] Card de Veredito com design semântico e contrastante:
  - `🟢 VERDADEIRO` (verde esmeralda)
  - `🔴 FALSO` (vermelho rosa)
  - `🟡 ENGANOSO` (âmbar dourado)
  - `⚪ INCONCLUSIVO / SEM DADOS` (cinza ardósia)
- [ ] Barra visual de confiança com porcentagem calculada (ex: `92% de confiança`).
- [ ] Seção da citação da afirmação auditada.
- [ ] Seção de **Parecer Técnico Oficial** exibindo a síntese gerada pela IA ancorada nas evidências.
- [ ] Seção de **Fontes Primárias Oficiais Consultadas**:
  - Card individual para cada fonte encontrada retornada pela API.
  - Exibição de: Órgão/Publicador (`publisher`), Título do documento (`title`), resumo do registro oficial (`snippet`).
  - Botão com link externo direto: **"Abrir Fonte Oficial ↗"** (`target="_blank"` com `rel="noopener noreferrer"`) para os portais oficiais (`.gov.br` ou `.gouv.fr`).
- [ ] Tratamento elegante de erros (ex: chave inválida, erro de conexão, 401, 429) com botão "Configurar Chave" para correção imediata.

---

### [TASK 2.5] Testes Automatizados e Handover
- [ ] Adicionar teste unitário/integração em `backend/tests/test_fact_check_api.py` verificando que a rota `GET /` retorna 200 e serve o arquivo HTML.
- [ ] Executar a suíte de testes com `pytest backend/tests -v` e garantir 100% de aprovação (todos os 92 testes anteriores + novo teste da UI).
- [ ] Atualizar o status da Fase 2 para `PRONTO PARA REVISÃO DO ANTIGRAVITY`.
- [ ] Preencher as **Notas de Entrega do Claude Code** no bloco abaixo com os comandos e evidências.

---

## 📝 Registro de Handovers e Comunicação

### 1. Parecer de Auditoria da Fase 1 (Antigravity - Gemini)

- **Status da Auditoria**: `APROVADO & PUBLICADO`
- **Data da Avaliação**: 2026-10-14
- **Avaliação de Arquitetura**:
  - Excelente estruturação modular: isolamento limpo entre adaptadores BYOK (`engines/providers/`), conectores com resiliência (`connectors/base.py`) e pipeline de checagem (`services/fact_checker.py`).
  - Suíte de testes automatizados impecável: 92 testes unitários e de integração passando em 3.5s sem chamadas externas não mockadas.
  - Implementação do cache TTL/LRU e backoff exponencial garantem conformidade com as regras de uso de APIs governamentais abertas.
- **Conformidade de Segurança e BYOK**:
  - Chaves de API gerenciadas via `SecretStr`, sem vazamento em logs ou responses.
  - Dependência transitória no FastAPI com descarte no `aclose()`.
- **Decisão**: `FASE 1 HOMOLOGADA. LIBERADA FASE 2 (UI/UX PLAYGROUND) PARA O CLAUDE CODE.`

---

### 2. Notas de Entrega do Claude Code (Fase 2)
*(O Claude Code deve preencher este bloco ao concluir a Fase 2)*

- **Status da Entrega**: `AGUARDANDO EXECUÇÃO DO CLAUDE CODE`
- **Data da Entrega**: *A preencher*
- **Arquivos Criados/Modificados**:
  - *Listar arquivos aqui*
- **Comandos de Teste Executados**:
  ```bash
  cd backend
  .venv/Scripts/python -m pytest tests/ -v
  ```
- **Evidências / Resultados dos Testes**:
  - *Resumo dos resultados de testes aqui*
- **Decisões Técnicas e Observações**:
  - *Notas para o Antigravity aqui*

---

### 3. Validação do Usuário & Publicação Remota (Fase 2)
*(Preenchido após o gatilho de aprovação do usuário)*

- **Status de Publicação**: `PENDENTE`
- **Instruções de Teste Apresentadas**:
- **Aprovação do Usuário**: [ ] SIM | [ ] NÃO
- **Commit Hash**:
- **Branch / Repositório Remoto**: `main`
