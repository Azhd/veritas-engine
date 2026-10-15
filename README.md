# Veritas Engine

**Verifique antes de compartilhar.** O Veritas confere notícias, mensagens e afirmações em
**fontes oficiais e científicas**, de graça, e mostra de onde tirou cada informação.

- Funciona **sem cadastro e sem chave de IA**: você recebe os dados oficiais encontrados.
- Com uma **IA gratuita** (Google Gemini, Groq ou Ollama no seu computador), recebe também um
  veredito explicado: Verdadeiro, Falso, Enganoso...
- Aceita **texto, print/foto** (o texto da imagem é lido no próprio aparelho) e **o link de onde a
  informação veio**.
- Leve: a página inteira tem cerca de 80 KB e funciona no celular.

> **Status:** Alpha 1.0 em desenvolvimento. A versão mais recente está na branch
> [`feat/fase-2-fontes-primarias`](https://github.com/Azhd/veritas-engine/tree/feat/fase-2-fontes-primarias)
> (tag `v0.2.0-rc.1`). A `main` contém a versão estável anterior (Fase 1).

---

## Como iniciar o app (Windows)

Você precisa do **Python 3.11 ou mais novo** ([python.org](https://www.python.org/downloads/);
na instalação, marque **"Add python.exe to PATH"**) e do **Git**.

1. **Baixe o projeto** (só na primeira vez). Abra o **PowerShell** e rode:
   ```powershell
   git clone https://github.com/Azhd/veritas-engine.git
   cd veritas-engine
   git switch feat/fase-2-fontes-primarias
   ```
   Se você já tem o projeto, entre na pasta dele e atualize com `git pull`.
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

### Se algo der errado

| Problema | Solução |
| --- | --- |
| "a execução de scripts foi desabilitada" | `powershell -ExecutionPolicy Bypass -File .\run.ps1` |
| A porta 8000 já está em uso | `.\run.ps1 -Port 8001` e abra `http://127.0.0.1:8001` |
| "python não é reconhecido" | Reinstale o Python marcando **"Add python.exe to PATH"** |
| O app abriu sem as novidades | Rode `git branch`: a branch com `*` deve ser `feat/fase-2-fontes-primarias` |
| A página parece antiga | Recarregue com **Ctrl + F5** |

---

## Como usar

1. Cole o texto, cole um print (**Ctrl + V**) ou envie uma foto.
2. (Opcional) Cole o **link** de onde a informação veio: o Veritas verifica no Internet Archive se a
   página foi alterada ou apagada.
3. Clique em **Verificar agora**.

O resultado mostra o selo do veredito, um resumo em português simples e os cartões das fontes
oficiais, com data, identificadores (DOI, PMID, número da lei...) e o botão **"Abrir fonte oficial"**.
Fontes em inglês ou francês têm o botão **"Traduzir"**. Dá para enviar o resultado no WhatsApp,
copiar o resumo ou baixar um cartão em imagem.

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
| 1 | Fundação: API, motor de IA "traga sua própria chave" (Gemini, Groq, Ollama, Claude, OpenAI) | Publicada (`main`) |
| 2 | Fontes primárias em 7 áreas, modo cidadão sem chave e app web | Aguardando validação (`feat/fase-2-fontes-primarias`) |
| 3 | Vídeo, áudio e imagens: transcrição com minutagem, metadados EXIF, detecção de IA (C2PA), Docker | Próxima |
| 4 | Relatórios por público: família, estudante de jornalismo, área jurídica/acadêmica | Planejada |
| 5 | Testes completos e release Alpha 1.0 | Planejada |

O andamento detalhado de cada fase está no [TASK_BOARD.md](TASK_BOARD.md).

### Versões

| Tag | Conteúdo |
| --- | --- |
| `v0.2.0-rc.1` | Fase 2 (candidata a release): fontes primárias, modo cidadão, app web, clima |

---

## Para desenvolvedores

- API documentada (Swagger): **http://127.0.0.1:8000/docs**
- Detalhes técnicos, configuração e testes: [backend/README.md](backend/README.md)
- Diretrizes de engenharia: [CLAUDE.md](CLAUDE.md)

```powershell
cd backend
.venv\Scripts\python -m pytest -q      # 216 testes, nenhum acessa a internet
```
