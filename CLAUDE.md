# CLAUDE.md - Diretrizes Técnicas & Guia do Engenheiro (Veritas Engine Alpha 1.0)

> **Projeto**: Veritas Engine (Alpha 1.0)  
> **Missão**: Infraestrutura Pública e Universal de Verdade, Contexto Histórico e Perícia Digital  
> **Papel do Claude Code**: Engenheiro de Software Líder / Executor Técnico  
> **Papel do Antigravity (Gemini)**: Arquiteto de Sistemas, Tech Lead & Gerente de Produto (PM)  
> **Comunicação Inter-Agentes**: Orquestrada pelo arquivo `TASK_BOARD.md` na raiz do repositório.

---

## 1. Visão & Manifesto do Veritas Engine Alpha 1.0

O **Veritas Engine** não é apenas um checador de fatos político: é uma **infraestrutura pública e universal de verdade, contexto histórico e perícia digital**, projetada para empoderar qualquer cidadão — **estudantes, jornalistas investigativos, famílias e pesquisadores acadêmicos** — contra a desinformação em qualquer área do conhecimento humano:

1. **Geopolítica & Conflitos**: Monitoramento de guerras, tratados internacionais e crises humanitárias.
2. **Saúde, Biologia & Ciência**: Validação de evidências médicas, artigos científicos, pandemias e ensaios clínicos contra pseudociência.
3. **Direito & Justiça**: Consulta direta a acórdãos, códigos de lei, súmulas e jurisprudência vinculante.
4. **Cotidiano & Cidadania**: Estatísticas demográficas, econômicas, inflação, programas sociais e orçamentos públicos.

---

## 2. Pilares de Engenharia

1. **Multimodalidade Extrema & Perícia Digital**:
   - Inspeção de **Texto**, **Vídeo** (extração de frames e áudio com `yt-dlp` + `ffmpeg`), **Áudio** (transcrição com timestamps via `Whisper`), **Imagens** (metadados EXIF e validação de proveniência criptográfica **C2PA** via `c2pa-python`).
2. **Cruzamento em Tempo Real com Fontes Primárias Globais**:
   - APIs de dados abertos governamentais, bases de pesquisas biomédicas, organismos internacionais e acórdãos judiciais.
3. **Modos de Audiência Adaptativos (`audience_mode`)**:
   - O mesmo conjunto de fatos e evidências oficiais é sintetizado sob medida para o público-alvo:
     - `general_family`: Linguagem simples, direta, didática, sem jargões e pronta para compartilhamento familiar e em redes sociais.
     - `journalism_student`: Trilha investigativa completa (OSINT), metodologia de checagem, linha do tempo e metadados forenses.
     - `law_academic`: Foco estrito em jurisprudência, artigos de lei, acórdãos e citações científicas com DOI/PubMed ID.
4. **Arquitetura BYOK (Bring Your Own Key) & Privacidade Descentralizada**:
   - Nenhuma chave de IA é retida em banco central. Usuários conectam Google Gemini, Anthropic Claude, OpenAI, Groq ou modelos locais via **Ollama**.
5. **Acessibilidade Financeira Universal & Custo Zero (Zero-Cost / Free-Tier First)**:
   - **Princípio da Inclusão Cidadã**: O Veritas Engine foi concebido para ser utilizado por **qualquer cidadão, especialmente os mais desprovidos de recursos, estudantes de escolas públicas e famílias de baixa renda**. Não pode haver exigência de cartões de crédito internacionais, planos pagos ou barreiras financeiras.
   - **Prioridade Absoluta para IAs Gratuitas**:
     * **Google Gemini (Free Tier / Google AI Studio)**: Chaves 100% gratuitas geradas em 1 minuto apenas com uma conta Google comum, sem pedir cartão de crédito (modelos Flash).
     * **Groq Cloud (Free Tier)**: Inferência ultrarrápida gratuita com modelos de código aberto (Llama 3).
     * **Modelos Locais Offline (Ollama)**: Custo ZERO absoluto de tokens e dados.
     * **Modo Cidadão Sem IA (Fallback Direto de Dados)**: Se o usuário não tiver nenhuma chave de IA ou estiver com conexão ultra-restrita, o Veritas Engine **não trava**: ele realiza a busca direta nas APIs públicas (Câmara, IBGE, data.gouv.fr, PubMed) e entrega as fontes oficiais brutas e números oficiais diretamente na tela.
   - **Design Leve & Baixo Consumo**: O backend e a interface devem operar com baixíssimo consumo de memória e banda de internet, viáveis em celulares modestos e redes 3G/4G populares.

---

## 3. Arquitetura de Referência do Monorepo

```
veritas-engine/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── fact_check.py        # Endpoints REST e streaming de auditoria
│   │   │       ├── byok.py              # Descoberta de provedores suportados
│   │   │       └── media.py             # Upload e inspeção forense multimodal
│   │   ├── core/                        # Configurações globais (pydantic-settings), erros
│   │   ├── engines/                     # Motores de IA e Provedores BYOK
│   │   │   ├── base.py                  # BaseLLMProvider & ProviderCredentials
│   │   │   ├── factory.py               # ProviderFactory dinâmica
│   │   │   ├── providers/               # Gemini, Claude, OpenAI, Groq, Ollama
│   │   │   └── verdict_engine.py        # Motor de síntese com adaptação de audiência
│   │   ├── connectors/                  # Conectores Multidisciplinares de Fontes Primárias
│   │   │   ├── base.py                  # BaseGovConnector com TTL cache e retries exponenciais
│   │   │   ├── br_gov.py                # Brasil: Câmara, Senado, IBGE, Transparência, GovBR Search
│   │   │   ├── fr_gov.py                # França: data.gouv.fr, INSEE, Légifrance, GouvFR Search
│   │   │   ├── global_geopolitics.py    # ONU (ReliefWeb/UN Data), GDELT Project, conflitos globais
│   │   │   ├── science_health.py        # PubMed (NCBI API), OMS/WHO (estudos e validações médicas)
│   │   │   ├── legal_justice.py         # STF, Planalto, EUR-Lex, Cour de Cassation
│   │   │   └── web_archive.py           # Wayback Machine (Internet Archive API)
│   │   ├── forensics/                   # Perícia Multimodal
│   │   │   ├── media_inspector.py       # Orquestrador forense (yt-dlp, ffmpeg, exif, c2pa)
│   │   │   ├── audio_transcriber.py     # Transcrição com timestamps (Whisper)
│   │   │   └── c2pa_validator.py        # Validação criptográfica de IA e proveniência
│   │   └── schemas/                     # Modelos Pydantic v2
│   │       ├── audience.py              # Enums de modos de audiência
│   │       ├── evidence.py              # Evidências primárias padronizadas
│   │       ├── fact_check.py            # Relatório de verificação estruturado
│   │       └── forensics.py             # Metadados de mídia e laudo pericial
│   ├── tests/                           # Suíte de testes automatizados (pytest)
│   ├── Dockerfile                       # Container com Python, FFmpeg, yt-dlp, ExifTool
│   ├── docker-compose.yml
│   └── requirements.txt
├── docs/                                # Especificações de arquitetura e APIs
├── TASK_BOARD.md                        # Quadro de Sprints e Handover Oficial
└── CLAUDE.md                            # Este arquivo
```

---

## 4. Detalhamento dos Módulos Críticos

### 4.1. Conectores Multidisciplinares (`/backend/app/connectors/`)
Todos os conectores devem herdar de `BaseGovConnector` (ou equivalente compartilhado) com cache TTL, timeout estrito (máximo 8s) e retries com backoff exponencial.

* **`br_gov.py`**:
  * Câmara dos Deputados (`dadosabertos.camara.leg.br/api/v2`)
  * Senado Federal (`legis.senado.leg.br/dadosabertos/`)
  * IBGE Séries Históricas e Demografia (`servicodados.ibge.gov.br/api/v1`)
  * Portal da Transparência (CGU)
* **`fr_gov.py`**:
  * data.gouv.fr API v1
  * INSEE Estatísticas e Demografia (`api.insee.fr`)
  * Légifrance (DILA / PISTE API)
* **`global_geopolitics.py`**:
  * **ReliefWeb API (ONU / OCHA)**: Dados de crises humanitárias e relatórios de zonas de guerra.
  * **GDELT Project API**: Monitoramento mundial de eventos, declarações de líderes e cobertura geopolítica global.
* **`science_health.py`**:
  * **PubMed / NCBI E-utilities API**: Verificação de artigos médicos revisados por pares, ensaios clínicos e identificadores PMID/DOI.
  * **OMS / WHO GHO (Global Health Observatory) API**: Dados estatísticos mundiais de saúde, vacinas e diretrizes oficiais.
* **`legal_justice.py`**:
  * Jurisprudência e Legislação: Portal da Legislação do Planalto, repositórios de acórdãos judiciais, EUR-Lex (União Europeia) e jurisprudência comparada.
* **`web_archive.py`**:
  * **Wayback Machine Availability API**: Confere histórico de páginas da web, identificando alterações retroativas, notas de retificação ou matérias apagadas.

---

### 4.2. Forense de Mídia (`/backend/app/forensics/`)
* **Vídeo**: Download/extração via `yt-dlp` e amostragem de keyframes via `ffmpeg` para análise de manipulação temporal.
* **Áudio**: Transcrição via `Whisper` gerando blocos textuais alinhados com `start_time` e `end_time` para verificação minuto a minuto.
* **Imagem & C2PA**:
  * Leitura e validação de manifestos criptográficos C2PA (`c2pa-python`). Identifica se a imagem foi gerada por ferramentas de IA generativa (DALL-E, Midjourney, Adobe Firefly, etc.) ou se teve assinatura de câmera preservada.
  * Extração de metadados EXIF com `exiftool` (modelo da câmera, data de captura, geolocalização).

---

### 4.3. Modos de Audiência Adaptativos (`audience_mode`)
A síntese do `verdict_engine.py` ajusta dinamicamente a estrutura de comunicação:

1. **`general_family`**:
   - Linguagem empática, direta e de fácil assimilação.
   - Parágrafos curtos, analogias práticas e destaque para *"Por que isso é falso/verdadeiro em 1 minuto"*.
   - Cartão de resumo ideal para WhatsApp e redes sociais.
2. **`journalism_student`**:
   - Metodologia OSINT (Open Source Intelligence).
   - Linha do tempo dos acontecimentos, contradições entre fontes, metadados das postagens e histórico de republicações.
3. **`law_academic`**:
   - Linguagem técnico-jurídica ou científica.
   - Indicação precisa de artigos constitucionais, leis vigentes, acórdãos e referências científicas formais (estilo ABNT / APA com DOI e PubMed ID).

---

## 5. Regra de Ouro de Versionamento e GitHub

> 🚨 **REGRA ABSOLUTA DE CONTROLE DE CÓDIGO E PUBLICAÇÃO**

### 5.1. Fluxo de Validação Obrigatório
- **Proibição de Push Precoce**: É **TERMINANTEMENTE PROIBIDO** executar `git push` para o GitHub de forma automática antes da aprovação explícita e inequívoca do usuário no chat.
- **Commits Locais**: Durante o desenvolvimento e enquanto o usuário testa localmente, é permitido realizar commits locais de segurança (`git commit`) para manter o histórico de alterações rastreável.
- **Transição de Status**: Nenhuma funcionalidade ou fase avança para publicação remota sem transitar pelo status `AGUARDANDO VALIDAÇÃO DO USUÁRIO` com instruções demonstradas na tela.

### 5.2. Gatilho Automático de Commit & Push
Assim que o usuário responder no chat com **"Validado"**, **"Aprovado"** ou **"Pode subir"**, o agente ativo deve executar **imediatamente e de forma automatizada**:
1. **Varredura de Segredos**: Garantir que `.env` está explicitamente no `.gitignore` e nenhuma credencial está nos arquivos indexados.
2. **Commit Semântico**: Executar `git add .` e `git commit` seguindo rigorosamente o padrão *Conventional Commits*.
3. **Git Push Remoto**: Executar `git push` para a branch `main` no GitHub.
4. **Atualização do Task Board**: Atualizar o `TASK_BOARD.md` marcando a etapa como `PUBLICADA NO GITHUB`.

---

## 6. Padrões de Código e Boas Práticas

- **Linguagem Backend**: Python 3.11+.
- **Tipagem**: Type Hints estritos e validação estrutural com **Pydantic v2**.
- **Resiliência**: Tratamento de exceções com fallback gracioso — a falha em um conector externo nunca deve derrubar o pipeline geral de checagem.
- **Testes**: Cobertura com `pytest` e fixtures sem chamadas desnecessárias à rede externa em ambiente de CI.
