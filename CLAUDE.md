# CLAUDE.md - Diretrizes Técnicas & Guia do Engenheiro (Veritas Engine)

> **Projeto**: Veritas Engine  
> **Papel do Claude Code**: Engenheiro de Software Líder / Executor Técnico  
> **Papel do Antigravity (Gemini)**: Arquiteto de Sistemas, Tech Lead & Gerente de Produto (PM)  
> **Comunicação Inter-Agentes**: Orquestrada pelo arquivo `TASK_BOARD.md` na raiz do repositório.

---

## 1. Visão Geral do Veritas Engine

O **Veritas Engine** é uma plataforma *open source* de **Fact-Checking Multimodal Descentralizado** de alta precisão. O motor processa afirmações em múltiplos formatos de mídia (Texto, Imagem, Áudio e Vídeo) e realiza cruzamento de dados em tempo real com fontes de autoridade pública (governamentais, estatísticas e legislativas) de múltiplos países, começando por **Brasil** e **França**, operando sob o paradigma **BYOK (Bring Your Own Key)**.

### Pilares Fundamentais:
1. **Multimodalidade Extrema**: Verificação de declarações em texto, fotos (análise forense, EXIF e C2PA), áudios (transcrição Whisper + análise de modulação vocal) e vídeos (demuxing de frames, transcrição temporal e análise contextual).
2. **Conectores Governamentais Nativos**: Integração direta via APIs oficiais e buscas direcionadas a domínios governamentais auditáveis (`gov.br` e `gouv.fr`).
3. **Privacidade e Descentralização (BYOK)**: Nenhuma chave secreta de IA fica retida centralmente. Usuários conectam suas chaves de provedores de nuvem (Google Gemini, Anthropic Claude, OpenAI, Groq) ou usam modelos locais (Ollama, vLLM).
4. **Auditabilidade Total (Cadeia de Evidências)**: Cada verificação produz um relatório contendo a trilha de evidências, pontuação de confiança (*confidence score*), links das fontes primárias e metadados criptográficos.

---

## 2. Arquitetura de Referência do Sistema

```
veritas-engine/
├── backend/
│   ├── app/
│   │   ├── api/                # Rotas REST e WebSockets (FastAPI)
│   │   │   └── v1/
│   │   │       ├── fact_check.py
│   │   │       ├── connectors.py
│   │   │       └── byok.py
│   │   ├── core/               # Configurações globais, segurança, lifespan
│   │   ├── engines/            # Motores de IA e Provedores BYOK
│   │   │   ├── provider_factory.py  # Factory unificada (Gemini, Claude, OpenAI, Groq, Ollama)
│   │   │   └── prompt_templates/    # Prompts de extração de alegações e síntese
│   │   ├── connectors/         # Conectores de APIs Governamentais
│   │   │   ├── br/             # Brasil: Camara, Senado, IBGE, Transparência, GovBR Search
│   │   │   └── fr/             # França: data.gouv.fr, INSEE, Légifrance, GouvFR Search
│   │   ├── multimodal/         # Processamento de mídia
│   │   │   ├── c2pa_forensic.py   # Validação de proveniência C2PA / EXIF
│   │   │   ├── audio_transcriber.py # Whisper / Faster-Whisper
│   │   │   └── video_processor.py   # FFmpeg frame extraction & timeline alignment
│   │   └── schemas/            # Schemas Pydantic de entrada, saída e relatórios
│   ├── tests/                  # Testes unitários e de integração (pytest)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # Interface Web (Next.js 14+ App Router, Tailwind, shadcn/ui)
│   ├── src/
│   │   ├── app/                # Páginas e layout
│   │   ├── components/         # Upload multimodal, Timeline de checagem, BYOK Dialog
│   │   └── lib/                # Client HTTP, state management
│   └── package.json
├── docs/                       # Documentação técnica e arquitetura
├── TASK_BOARD.md               # Painel de controle de sprints e handovers Antigravity <-> Claude Code
└── CLAUDE.md                   # Este arquivo (especificação técnica mestre)
```

---

## 3. Especificação dos Componentes Críticos

### 3.1. Arquitetura BYOK (Bring Your Own Key)
- As chaves de API nunca devem ser salvas de forma exposta no backend para usuários anônimos.
- O cliente frontend envia as credenciais via *headers* criptografados ou em sessão segura transitória:
  - `X-Provider`: `gemini` | `anthropic` | `openai` | `groq` | `ollama`
  - `X-API-Key`: Chave do provedor (quando aplicável)
  - `X-Endpoint-URL`: URL personalizada (essencial para servidores Ollama ou compatíveis com OpenAI)
- O backend deve implementar uma interface `BaseLLMProvider` abstrata com métodos padronizados:
  - `generate(prompt: str, system: str, temperature: float) -> str`
  - `generate_stream(...) -> AsyncGenerator[str, None]`
  - `analyze_multimodal(media_bytes: bytes, mime_type: str, prompt: str) -> FactCheckOutput`

### 3.2. Conectores Governamentais Oficiais
Cada conector deve implementar caching (TTL configurável) e resiliência com retries automáticos.

#### A. Conectores do Brasil (BR)
- **Câmara dos Deputados**: API REST v2 (`https://dadosabertos.camara.leg.br/api/v2`) para proposições, discursos, presenças e votações.
- **Senado Federal**: Dados Abertos (`https://legis.senado.leg.br/dadosabertos/`) para matérias legislativas e relatorias.
- **IBGE**: APIs de Séries Históricas e Pesquisas (`https://servicodados.ibge.gov.br/api/v1/`).
- **Portal da Transparência (CGU)**: API de emendas parlamentares, benefícios ao cidadão e contratos federais.
- **Gov.br Verified Search**: Mecanismo de busca programática restrito a `site:gov.br` para conferência de notas oficiais e portarias.

#### B. Conectores da França (FR)
- **data.gouv.fr**: API v1 (`https://www.data.gouv.fr/api/1/`) para datasets nacionais e fontes abertas.
- **INSEE**: API de estatísticas econômicas e populacionais (`https://api.insee.fr/`).
- **Légifrance (DILA / PISTE)**: Consulta a códigos legais, leis vigentes e decretos oficiais.
- **Gouv.fr Verified Search**: Mecanismo de busca programática restrito a `site:gouv.fr`.

### 3.3. Pipeline Multimodal e C2PA
- **C2PA (Coalition for Content Provenance and Authenticity)**: Extração e validação de manifesto de proveniência criptográfica (verificar se a imagem/áudio/vídeo foi gerada por IA ou manipulada pós-captura).
- **Áudio**: Extração de faixas via FFmpeg e transcrição via Whisper com identificação de *timestamps* e *speakers*.
- **Vídeo**: Amostragem inteligente de *key-frames* representativos e sincronização com a transcrição textual para verificação frame a frame.

---

## 4. Regra de Ouro: Protocolo de Comunicação Antigravity <-> Claude Code

> ⚠️ **ATENÇÃO CLAUDE CODE: NUNCA INICIE UMA NOVA FASE SEM APROVAÇÃO FORMAL DO ANTIGRAVITY.**

1. **Leitura Contínua**: Sempre leia o `TASK_BOARD.md` antes de agir para saber sua atribuição atual.
2. **Execução Autônoma e Rigorosa**: Ao trabalhar em uma tarefa:
   - Escreva código modular, tipado (TypeScript no frontend, Type Hints estritos no Python backend com Pydantic v2).
   - Crie testes automatizados para toda lógica de negócio e conectores.
   - Trate erros de rede, limites de taxa (rate limits) e ausência de chaves com elegância.
3. **Protocolo de Entrega (Handover)**:
   - Assim que você concluir a implementação e validar os testes locais de uma tarefa/fase:
     1. Edite o arquivo `TASK_BOARD.md`.
     2. Mude o status da respectiva tarefa/fase para:
        ```markdown
        Status: PRONTO PARA REVISÃO DO ANTIGRAVITY
        ```
     3. Adicione uma seção **"Notas de Entrega do Claude Code"** no `TASK_BOARD.md` detalhando:
        - O que foi construído (arquivos criados/modificados).
        - Testes executados e comandos para reproduzi-los.
        - Pontos de atenção ou decisões arquiteturais tomadas.
4. **Auditoria do Antigravity**: O Antigravity (Gemini) irá auditar o código entregue, rodar validações e preparar o ambiente de testes locais.
5. **Apresentação e Teste Local**: Uma vez que o código esteja auditado e pronto para o usuário, o status em `TASK_BOARD.md` muda para:
   ```markdown
   Status: AGUARDANDO VALIDAÇÃO DO USUÁRIO
   ```
   O agente ativo (Antigravity ou Claude Code) deve iniciar o servidor local de testes e apresentar na tela as instruções detalhadas de como o usuário pode testar a funcionalidade (endpoints, Swagger `/docs`, exemplos com cURL/payloads).

---

## 5. Regra de Ouro de Versionamento e GitHub

> 🚨 **REGRA ABSOLUTA DE CONTROLE DE CÓDIGO E PUBLICAÇÃO**

### 5.1. Fluxo de Validação Obrigatório
- **Proibição de Push Precoce**: É **TERMINANTEMENTE PROIBIDO** executar `git push` para o GitHub de forma automática antes da aprovação explícita e inequívoca do usuário.
- **Commits Locais**: Durante o desenvolvimento e enquanto o usuário testa localmente, é permitido realizar commits locais de segurança (`git commit`) para manter o histórico de alterações rastreável.
- **Transição de Status**: Nenhuma funcionalidade ou fase avança para publicação remota sem transitar pelo status `AGUARDANDO VALIDAÇÃO DO USUÁRIO` com o servidor de teste ativo e instruções demonstradas na tela.

### 5.2. Gatilho Automático de Commit & Push
Assim que o usuário responder no chat com **"Validado"**, **"Aprovado"**, **"Pode subir"** (ou termos equivalentes de aprovação explícita), o agente ativo deve executar **imediatamente e de forma automatizada** os seguintes passos:

1. **Varredura de Segurança & Segredos**:
   - Verificar se há segredos, senhas ou chaves de API expostas no código.
   - Garantir obrigatoriamente que arquivos `.env` e credenciais locais estejam listados no `.gitignore` e não estejam indexados no Git (`git status`).
2. **Git Add & Commit Convencional**:
   - Executar `git add .`.
   - Criar o commit semântico seguindo rigorosamente o padrão *Conventional Commits* (ex: `feat: implement br_gov transparency API connector`, `feat: setup byok provider factory and fastapi core`).
3. **Git Push Remoto**:
   - Executar `git push` para a branch atual no GitHub (configurando o remote `origin` se for o primeiro envio).
4. **Atualização do Task Board**:
   - Atualizar o `TASK_BOARD.md` marcando a respectiva funcionalidade/fase com o status:
     ```markdown
     Status: PUBLICADA NO GITHUB
     ```

---

## 6. Padrões de Código e Boas Práticas

- **Linguagem Backend**: Python 3.11+.
  - Gerenciador de dependências: `pip` / `requirements.txt` (ou Poetry / uv se preferir, manter simples).
  - Linter/Formatter: Ruff ou Black + Flake8.
- **Linguagem Frontend**: TypeScript, React 18+, Next.js 14+ (App Router).
- **Padrão de Nomenclatura**:
  - Python: `snake_case` para funções/variáveis, `PascalCase` para classes, `SCREAMING_SNAKE_CASE` para constantes.
  - TypeScript: `camelCase` para funções/variáveis, `PascalCase` para componentes e interfaces.
- **Commits Git**: Padrão Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`).
