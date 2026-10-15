# Veritas Engine

**Verifique antes de compartilhar.** O Veritas confere notícias, mensagens e afirmações em
**fontes oficiais e científicas**, de graça, e mostra de onde tirou cada informação.

- Funciona **sem cadastro e sem chave de IA**: você recebe os dados oficiais encontrados.
- Com uma **IA gratuita** (Google Gemini, Groq ou Ollama no seu computador), recebe também um
  veredito explicado: Verdadeiro, Falso, Enganoso...
- Aceita **texto, print/foto** (o texto da imagem é lido no próprio aparelho) e **o link de onde a
  informação veio**.
- **Novo (Fase 3):** analisa **fotos, vídeos e áudios** (arquivo ou link do YouTube, TikTok, X,
  Instagram): diz se a imagem foi **gerada por IA** (credenciais C2PA), mostra câmera, data e local
  da foto, transcreve a fala com **minutagem** e confere cada afirmação nas fontes oficiais.
- **Em português, inglês e francês:** cada idioma tem a sua página (`/pt/`, `/en/`, `/fr/`), e as
  explicações da IA vêm no idioma escolhido.
- **Confiança bem visível:** quando a IA tem alta confiança, o resultado vira um cartão colorido
  com carimbo (**CONFIRMADO** em verde ou **FALSO** em vermelho) e uma régua de Falso a Verdadeiro.
- Leve: cada página tem cerca de 130 KB e funciona no celular.

> **Status:** versão **Alpha 1.3** (tag `v1.3.0-alpha`) publicada na `main`: perícia de vídeo, áudio e
> imagens (Fase 3), páginas em português, inglês e francês e destaque da confiança. Próxima etapa:
> Fase 4 (relatórios por público).

---

## Como iniciar o app (Windows)

Você precisa do **Python 3.11 ou mais novo** ([python.org](https://www.python.org/downloads/);
na instalação, marque **"Add python.exe to PATH"**) e do **Git**.

1. **Baixe o projeto** (só na primeira vez). Abra o **PowerShell** e rode:
   ```powershell
   git clone https://github.com/Azhd/veritas-engine.git
   cd veritas-engine
   ```
   Se você já tem o projeto, entre na pasta dele e atualize com `git switch main` e depois
   `git pull`.
2. **Entre na pasta do backend:**
   ```powershell
   cd backend
   ```
3. **Inicie o app:**
   ```powershell
   .\run.ps1
   ```
   Na primeira vez ele instala o que falta (1 a 2 minutos).
4. Quando aparecer `Uvicorn running on http://127.0.0.1:8000`, abra no navegador:
   **http://127.0.0.1:8000**
5. Para desligar: volte ao PowerShell e aperte **Ctrl + C**.

**Linux / macOS:** `cd backend` e depois `./run.sh`.

### Perícia completa de mídia (opcional)

O app básico já lê fotos (câmera, data, GPS) e baixa vídeos por link. Para extrair o áudio e os
quadros de vídeos e detectar imagens feitas por IA, instale os extras **uma vez**:

```powershell
.\run.ps1 -Full       # + FFmpeg e C2PA (~300 MB no Windows)
.\run.ps1 -Whisper    # tudo do -Full + transcrição offline no seu computador
```

Linux / macOS: `./run.sh --full` ou `./run.sh --whisper`. Depois de instalado, `.\run.ps1` sozinho
já usa os extras. Para transcrever a fala **não é preciso** o `-Whisper`: a chave grátis do **Groq**
ou do **Gemini** (veja abaixo) faz isso.

**Com Docker** (tudo incluído, inclusive FFmpeg e ExifTool), na pasta raiz do projeto:

```bash
docker compose up --build
```

e abra **http://localhost:8000**.

### Se algo der errado

| Problema | Solução |
| --- | --- |
| "a execução de scripts foi desabilitada" | `powershell -ExecutionPolicy Bypass -File .\run.ps1` |
| A porta 8000 já está em uso | `.\run.ps1 -Port 8001` e abra `http://127.0.0.1:8001` |
| "python não é reconhecido" | Reinstale o Python marcando **"Add python.exe to PATH"** |
| O app abriu sem as novidades | Rode `git switch main` e `git pull`, e reinicie o app |
| A página parece antiga | Recarregue com **Ctrl + F5** |

---

## Como usar

Ao abrir **http://127.0.0.1:8000**, escolha o idioma: **Português**, **English** ou **Français**.
Dá para trocar a qualquer momento pelos botões **PT · EN · FR** no topo da página.

1. Cole o texto, cole um print (**Ctrl + V**) ou envie uma foto, um vídeo ou um áudio (até 50 MB).
2. (Opcional) Cole o **link** de onde a informação veio: o Veritas verifica no Internet Archive se a
   página foi alterada ou apagada. Se for link de vídeo (YouTube, TikTok, X, Instagram), o vídeo é
   analisado.
3. Clique em **Verificar agora**.

O resultado mostra o selo do veredito, um resumo em linguagem simples (no idioma da página) e os
cartões das fontes oficiais, com data, identificadores (DOI, PMID, número da lei...) e o botão
**"Abrir fonte oficial"**. Fontes em outro idioma têm o botão **"Traduzir"**.

Com IA, a **confiança** aparece de três jeitos:

| Confiança | Como aparece |
| --- | --- |
| **Alta** (80% ou mais) | Cartão inteiro colorido com carimbo: verde **CONFIRMADO** quando é verdadeiro, vermelho listrado **FALSO** quando é quase certo que é falso, laranja **ENGANOSO** |
| **Média** (55% a 79%) | Cartão na cor do veredito, com "Provavelmente verdadeiro/falso" |
| **Baixa** (menos de 55%) | Cartão discreto com o aviso "leia as fontes antes de concluir" |

Em todos os casos, uma **régua de Falso a Verdadeiro** mostra onde o veredito ficou. O cartão em
imagem e a mensagem do WhatsApp também levam o nível de confiança. Dá para enviar o resultado no WhatsApp,
copiar o resumo ou baixar um cartão em imagem.

Para fotos, vídeos e áudios aparecem também:

- **Perícia da mídia:** credenciais de conteúdo (C2PA: "Gerada por IA", "Foto de câmera", "Editada"...),
  câmera, data, local no mapa, programa de edição, duração, impressão digital (SHA-256) e os quadros
  principais do vídeo.
- **Linha do tempo:** as frases checáveis ditas no vídeo/áudio, com o minuto (ex.: `02:15`) e o
  veredito de cada uma. Clique em uma frase para ver as fontes.

Sem IA, a perícia funciona igual; a fala só é transcrita com uma IA grátis (Groq ou Gemini) ou com
o `-Whisper` instalado.

### Veredito explicado por IA, de graça

1. Clique em **"Grátis · sem IA"**, no topo da página.
2. Escolha **Google Gemini** ou **Groq** (gratuitos, sem cartão de crédito) e siga os 3 passos
   para criar a chave. Com o **Ollama** instalado no seu computador, não precisa de chave.
3. Cole a chave e clique em **"Testar e usar esta IA"**: o app confirma na hora se a chave funciona.

A chave fica só no seu navegador (ou na aba, se você não marcar "Lembrar neste aparelho"). O
servidor usa a chave apenas durante cada verificação e nunca a guarda.

---

## O que o Veritas consulta

| Área | Fontes |
| --- | --- |
| Governo e Congresso | Câmara dos Deputados, Senado Federal, data.gouv.fr (França), Portal da Transparência* |
| Estatísticas oficiais | IBGE (inflação, desemprego, população), INSEE (França) |
| Leis e tribunais | Legislação Federal (Senado/Planalto), STJ (teses, súmulas e repercussão geral do STF), EUR-Lex (União Europeia), Légifrance* e Cour de cassation* |
| Ciência e saúde | PubMed (artigos científicos), Organização Mundial da Saúde |
| Clima e ambiente | Copernicus (União Europeia), NOAA (EUA) |
| Mundo e conflitos | GDELT, ReliefWeb (ONU)* |
| Memória da web | Internet Archive (Wayback Machine) |

\* Precisam de uma credencial gratuita configurada no servidor; sem ela, ficam desligadas e não
atrapalham nada. As demais funcionam sem cadastro.

Cada afirmação só consulta as áreas a que pertence (saúde vai para PubMed e OMS; leis vão para o
Senado, o STJ e o EUR-Lex...). Se uma fonte não responder a tempo, a verificação continua com as
outras.

---

## Fases do projeto (Alpha 1.0)

| Fase | Conteúdo | Status |
| --- | --- | --- |
| 1 | Fundação: API, motor de IA "traga sua própria chave" (Gemini, Groq, Ollama, Claude, OpenAI) | Publicada |
| 2 | Fontes primárias em 7 áreas, modo cidadão sem chave e app web | Publicada (Alpha 1.2) |
| 3 | Vídeo, áudio e imagens: transcrição com minutagem, metadados EXIF, detecção de IA (C2PA), Docker; páginas PT/EN/FR | Publicada (Alpha 1.3) |
| 4 | Relatórios por público: família, estudante de jornalismo, área jurídica/acadêmica | Planejada |
| 5 | Testes completos e release Alpha 1.0 | Planejada |

O andamento detalhado de cada fase está no [TASK_BOARD.md](TASK_BOARD.md).

### Versões

| Tag | Conteúdo |
| --- | --- |
| `v1.3.0-alpha` | **Alpha 1.3** (Fase 3 validada): perícia de mídia (C2PA, EXIF, quadros, transcrição com minutagem), Docker, páginas PT/EN/FR, régua e carimbo de confiança, busca no EUR-Lex por palavras |
| `v1.3.0-rc.1` | Candidata a release da Fase 3 (antes das páginas em 3 idiomas) |
| `v1.2.0-alpha` | **Alpha 1.2** (Fase 2 validada): fontes primárias em 7 áreas, modo cidadão, app web, clima, diagnóstico de chaves e escolha automática de modelo de IA |
| `v0.2.0-rc.1` | Candidata a release da Fase 2 (antes da validação) |

---

## Para desenvolvedores

- API documentada (Swagger): **http://127.0.0.1:8000/docs**
- Detalhes técnicos, configuração e testes: [backend/README.md](backend/README.md)
- Diretrizes de engenharia: [CLAUDE.md](CLAUDE.md)

```powershell
cd backend
.venv\Scripts\python -m pytest -q      # 298 testes, nenhum acessa a internet
```
