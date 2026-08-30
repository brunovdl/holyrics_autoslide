# Holyrics AutoSlide 🎵⚡

**Holyrics AutoSlide** é um sistema inteligente e autônomo para automação de slides no [Holyrics](https://holyrics.com.br/), utilizando **transcrição de áudio em tempo real por IA (Groq Cloud Whisper API)**, **isolamento vocal acústico** e um **motor de decisão heurístico** com latência ultra-baixa (< 400ms).

O software escuta o áudio capturado (microfone ou loopback do sistema/YouTube), filtra o som da voz, transcreve em tempo real, identifica a música e a estrofe cantada e envia comandos HTTP para a API oficial do Holyrics avançando ou saltando slides e músicas automaticamente.

---

## ✨ Principais Recursos

- 🎙️ **Isolamento Vocal por Filtro Passa-Faixa (300Hz - 3400Hz)**:
  - Atenua bumbos, contrabaixos pesados e pratos estridentes da bateria, garantindo que o Whisper receba apenas a voz limpa do cantor.
- ⚡ **Latência Ultra-Baixa (< 400ms)**:
  - Processamento em chunks de 0.8s com o modelo `whisper-large-v3-turbo` na nuvem da Groq (resposta de inferência em ~120-180ms).
- 🧠 **Motor de Decisão & Troca Inteligente de Slides**:
  - Reconhece início de estrofes, refrões repetidos e saltos de estrutura musical sem travar a ordem.
  - Transição automática de músicas da playlist: se o repertório mudar no meio do culto, o sistema detecta e abre a nova letra via `ShowLyrics`.
- 🔄 **Sincronização Contínua & Resiliência a Falhas**:
  - Polling periódico em segundo plano da playlist e apresentação ativa do Holyrics.
  - Sockets HTTP com auto-reset e botão de reconexão manual com indicador visual em tempo real.
- 🖥️ **Interface Gráfica Web Moderna (Flet)**:
  - Dashboard interativo com visualização da música ativa, slide projetado, estrofe candidata, score de confiança, VU meter de áudio em tempo real e monitor de logs.

---

## 🏗️ Arquitetura do Sistema

```
   [ Microfone / Loopback de Áudio ]
                   │
                   ▼
  [ Filtro Passa-Faixa Vocal (300-3400Hz) + VAD ]
                   │
                   ▼
  [ Groq Cloud Whisper API (~150ms) ]
                   │  (Vocabulário Dinâmico da Playlist)
                   ▼
       [ Transcrição em Tempo Real ]
                   │
                   ▼
   [ SlideMatcher & Indexador de Palavras-Chave ]
                   │
                   ▼
      [ Motor de Decisão Heurístico ]
                   │  (Histerese & Cooldown 0.4s)
                   ▼
[ Holyrics API Server (ActionGoToIndex / ShowLyrics) ]
```

---

## 📋 Pré-requisitos

1. **Python 3.10+** (recomendado Python 3.11 ou superior).
2. **Holyrics** instalado e com o **API Server** habilitado:
   - No Holyrics: *Configurações* ➔ *API Server* ➔ Ativar servidor HTTP (porta padrão: `8091`) e gerar um **Token**.
3. **Chave de API da Groq Cloud** (gratuita):
   - Obtenha sua chave em [console.groq.com](https://console.groq.com/keys).

---

## 🚀 Instalação e Configuração

### 1. Clonar o Repositório
```bash
git clone https://github.com/brunovdl/holyrics_autoslide.git
cd holyrics_autoslide
```

### 2. Criar Ambiente Virtual e Instalar Dependências
```bash
python3 -m venv .venv
source .venv/bin/activate  # No Linux/macOS
# .venv\Scripts\activate   # No Windows

pip install -r requirements.txt
```

### 3. Configurar as Variáveis de Ambiente (`.env`)
Copie o arquivo de exemplo e insira suas credenciais:

```bash
cp .env.example .env
```

Edite o arquivo `.env`:
```env
# Conexão com o Holyrics API Server
HOLYRICS_HOST=127.0.0.1      # Ou o IP da máquina do Holyrics na rede local
HOLYRICS_PORT=8091
HOLYRICS_TOKEN=seu_token_api_aqui
HOLYRICS_TIMEOUT=2.0

# API de Transcrição Groq Cloud (Whisper)
GROQ_API_KEY=gsk_sua_chave_groq_aqui
GROQ_MODEL=whisper-large-v3-turbo
```

---

## 🎮 Como Usar

### 1. Iniciar a Aplicação
```bash
python main.py --web
```
A interface será aberta automaticamente no seu navegador padrão (`http://localhost:8550`).

### 2. Modos de Operação no Dashboard
- **Iniciar Monitor**: O sistema escuta o áudio, transcreve e simula as trocas de slides na tela, sem enviar comandos para o Holyrics (ideal para testes/passagem de som).
- **Ativar Automático**: Modo de produção. Os slides do Holyrics são trocados instantaneamente conforme o louvor é cantado.
- **Reconectar**: Força uma reinicialização da conexão com o Holyrics e recarrega as músicas da playlist.
- **Parar**: Pausa a transcrição e o envio de comandos.

---

## 🧪 Testes Automatizados

O projeto possui cobertura completa de testes unitários e de integração:

```bash
pytest -v
```

---

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais detalhes.
