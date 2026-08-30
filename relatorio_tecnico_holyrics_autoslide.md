# Relatório técnico — Holyrics AutoSlide

## 1. Visão geral

A separação arquitetural está boa. O projeto já possui módulos distintos para captura de áudio, transcrição local/Groq, matching, decisão, comunicação com Holyrics, estado e interface Flet. Também já existem testes automatizados para várias dessas partes.

O problema atual pode ser resumido assim:

```text
Áudio muito sobreposto
       ↓
Whisper transcreve várias vezes quase o mesmo trecho
       ↓
Rolling transcript duplica partes
       ↓
Fuzzy matching recebe texto contaminado
       ↓
Thresholds baixos
       ↓
Uma transcrição errada pode trocar slide
       ↓
Score baixo na música atual
       ↓
Sistema procura outra música
       ↓
Troca de música cedo demais
       ↓
Contexto antigo continua no buffer
       ↓
Mistura ainda mais
```

Esse ciclo explica bastante o comportamento observado.

---

# 2. PROBLEMA CRÍTICO — o mesmo áudio está sendo transcrito muitas vezes

No `AutomationService`, a duração do chunk vem das configurações, atualmente `0.8s`, enquanto o worker tenta processar novamente aproximadamente a cada `0.18s`.

Em cada ciclo ele faz:

```python
audio_chunk = self.audio_ring_buffer.get_recent(chunk_duration)
```

Na prática:

```text
Transcrição 1
0.00 ───────── 0.80

Transcrição 2
     0.18 ───────── 0.98

Transcrição 3
          0.36 ───────── 1.16

Transcrição 4
               0.54 ───────── 1.34
```

Existe aproximadamente **77,5% de sobreposição entre duas inferências consecutivas**.

A configuração `overlap_duration = 0.2` existe, mas não é ela quem governa esse comportamento.

## Correção proposta

Criar um `ChunkScheduler` baseado em amostras novas, não em `sleep`.

Eu começaria com:

```text
Janela ASR: 2,5 s
Hop:        0,8 s
Overlap:    1,7 s
```

ou:

```text
Janela ASR: 3,0 s
Hop:        1,0 s
```

Só deve existir uma nova transcrição depois que aproximadamente 0,8–1,0 segundo de **áudio novo** entrou no sistema.

---

# 3. PROBLEMA CRÍTICO — o rolling transcript duplica textos

`RollingTranscriptBuffer` simplesmente adiciona cada transcrição e depois junta tudo com espaços. Não existe deduplicação de janelas sobrepostas.

Exemplo:

```text
Whisper 1:
"aquele que"

Whisper 2:
"aquele que acalma"

Whisper 3:
"que acalma o vento"
```

Hoje pode virar:

```text
aquele que aquele que acalma que acalma o vento
```

Quando o RapidFuzz recebe isso, passa a comparar uma letra artificial.

## Correção proposta

Criar:

```text
TranscriptMerger
```

Ele deverá encontrar a sobreposição entre o final da transcrição anterior e o início da nova:

```text
Anterior:
"aquele que acalma"

Nova:
"que acalma o vento"

Resultado:
"aquele que acalma o vento"
```

Preferencialmente manter tokens/segmentos com timestamps em vez de somente concatenar strings.

---

# 4. PROBLEMA CRÍTICO — o trecho mais recente ainda é duplicado outra vez

Depois de colocar `asr_res.text` no rolling transcript, o código recupera `full_transcript`.

Em seguida chama:

```python
_process_matching_and_decision(
    full_transcript,
    recent_transcript=asr_res.text
)
```

Mas, ao tentar encontrar a música, cria:

```python
search_text = f"{transcript} {recent_transcript}"
```

Ou seja, o `recent_transcript` já está dentro de `transcript` e ganha peso duas vezes.

## Correção

Para identificação de música:

```python
search_text = transcript
```

Se for desejável dar maior peso ao trecho recente, isso deve acontecer no algoritmo de score, e não duplicando texto.

---

# 5. PROBLEMA MAIS IMPORTANTE — a música atual não fica realmente travada

O projeto tem `current_song`, mas não possui um verdadeiro estado:

```text
SONG_LOCKED
```

Quando uma música está selecionada e o melhor slide fica abaixo de `60%`, o sistema volta a procurar correspondência em todas as outras músicas. Se outra música passar pelo matcher, ela pode substituir imediatamente a atual e executar `ShowLyrics`.

Isso explica perfeitamente:

```text
Escape
  ↓
transcrição ruim
  ↓
Emaús
  ↓
transcrição seguinte
  ↓
Escape
  ↓
outra frase
  ↓
Os Que Confiam
```

## Correção

Criar uma máquina de estados:

```text
SEARCHING_SONG
       ↓
SONG_CANDIDATE
       ↓
   SONG_LOCKED
       ↓
SONG_TRANSITION_CANDIDATE
       ↓
   SONG_LOCKED
```

Enquanto estiver em `SONG_LOCKED`, a aplicação deve procurar normalmente **somente slides da música atual**.

Outras músicas podem ser avaliadas em segundo plano, mas não podem substituir a atual imediatamente.

---

# 6. Criar um `SongTransitionDecisionEngine`

Hoje existe um bom conceito de `SlideDecisionEngine`, com cooldown, hits e histerese, mas não existe equivalente para mudança de música.

Eu criaria:

```python
SongTransitionDecisionEngine
```

com estado semelhante a:

```text
locked_song
candidate_song
candidate_hits
candidate_started_at
candidate_score_history
candidate_margin_history
last_song_change
```

Valores iniciais:

| Parâmetro | Sugestão |
|---|---:|
| identificação inicial | ≥ 88–90% |
| mudança de música | ≥ 92% |
| margem sobre segundo lugar | ≥ 10–12 |
| confirmações | 3 |
| persistência mínima | 3 s |

Então:

```text
Escape está travada

Emaús → 91%
não troca

Emaús → 93%
1 confirmação

Emaús → 94%
2 confirmações

Emaús → 95%
3 confirmações + tempo mínimo

AGORA troca
```

---

# 7. PROBLEMA CRÍTICO — contexto da música anterior não é limpo

Ao detectar uma nova música, o código atual troca `current_song` e zera alguns campos de slide, mas o `RollingTranscriptBuffer` continua contendo os últimos segundos da música anterior.

Isso é uma fonte direta de contaminação.

## Correção

Criar um único método:

```python
reset_context_for_song_change()
```

Ele deve executar algo equivalente a:

```text
rolling_transcript.clear()

slide_decision.reset()

candidate_slide = None
candidate_score = 0

current_slide = None

limpar histórico do matcher
limpar contexto ASR
```

Somente depois:

```text
ShowLyrics(nova_musica)
```

---

# 8. Thresholds atuais estão agressivos demais

Atualmente os defaults são aproximadamente:

```text
Música                 75%
Margem música           5%
Slide forte            78%
Slide possível         68%
Confirmações            1
Cooldown                0,4 s
```

Para voz cantada com banda/playback, isso é bastante permissivo.

## Sugestão inicial

```text
Música inicial             90%
Troca de música            92%

Margem música              10%

Slide possível             75%
Slide forte                88%

Confirmação forte           2
Confirmação possível        3

Cooldown                  0,9 s
```

Depois calibrar usando gravações reais.

---

# 9. Score de 96% atualmente consegue furar as confirmações

No `SlideDecisionEngine`, existe uma regra que permite a troca quando:

```python
candidate_score >= 96.0
```

mesmo sem atingir as confirmações normais.

Isso parece seguro porque 96% parece muito alto, mas RapidFuzz pode gerar scores altíssimos para frases curtas.

## Correção

Remover esse bypass.

Se quiser manter uma fast-path, limitar a:

```text
slide candidato = atual + 1
score >= 97%
frase contém âncora exclusiva
não existe candidato concorrente próximo
```

Mesmo assim eu ainda preferiria duas evidências.

---

# 10. SongMatcher está muito vulnerável a frases genéricas

Atualmente ele calcula similaridade com a letra completa e também procura o melhor slide individual. O resultado final pode ser simplesmente o maior score encontrado em um único slide.

Isso é perigoso em músicas cristãs porque várias possuem frases semelhantes:

```text
meu Deus
eu te amo
tua presença
para sempre
és fiel
eu confio
não temerei
```

## Melhoria proposta

Criar um índice discriminativo da playlist.

Exemplo:

```text
"meu Deus"
aparece em 5 músicas
→ peso baixo


"derruba as muralhas"
aparece em 1 música
→ peso muito alto
```

Adicionar:

```text
unique token score
bigrams
trigrams
anchor phrases
frequência inversa na playlist
```

A identificação da música deve depender mais das partes que diferenciam uma música das outras.

---

# 11. `token_set_ratio` precisa ter peso controlado

O matcher utiliza bastante RapidFuzz, inclusive `token_set_ratio`.

Ele é útil para ASR imperfeito, mas ignora bastante a ordem das palavras.

Eu manteria, mas combinaria com:

```text
partial_ratio
ordered bigrams
ordered trigrams
anchor phrases
tokens exclusivos
contexto
```

Nunca deixaria `token_set_ratio` sozinho ser uma evidência decisiva.

---

# 12. Matching por palavra-chave pode inflar demais um slide curto

No `SlideMatcher`, para alguns slides curtos, apenas uma palavra-chave correspondente já consegue elevar bastante o score.

Somando:

```text
keyword boost
+ proximity bonus
+ anticipation bonus
```

o candidato pode passar do threshold sem ter evidência suficiente.

## Correção

Para slide curto exigir:

```text
2 palavras significativas

OU

1 bigrama exclusivo

OU

frase inicial com alta correspondência
```

---

# 13. Rever as stopwords

No conjunto de stopwords existe inclusive:

```text
nao
```

Para letras isso pode ser semanticamente importante:

```text
eu temerei
eu não temerei
```

Recomendo criar uma lista de stopwords específica para letras, e não uma lista excessivamente agressiva.

---

# 14. Matcher deveria procurar slides próximos primeiro

Hoje todos os slides recebem score. Há bônus de proximidade, mas todos continuam concorrendo.

Eu mudaria para:

```text
Slide atual = 5

BUSCA LOCAL

4
5
6
7
```

Se nenhum deles alcançar uma confiança mínima:

```text
BUSCA GLOBAL
```

Isso reduz muito os saltos acidentais.

---

# 15. Threshold variável por tamanho do salto

Sugestão:

```text
5 → 6
>= 85%
2 hits


5 → 7
>= 90%
2 hits


5 → 12
>= 94%
3 hits


5 → 2
>= 92%
3 hits
```

Assim o ministro ainda pode voltar espontaneamente para um refrão, mas a aplicação precisa de bastante evidência para concluir isso.

---

# 16. O prompt do Whisper está olhando para os slides errados

`_build_context_prompt()` utiliza o título e os `start_words` dos **primeiros quatro slides da música**.

Se estamos no slide 10, isso não é o contexto mais útil.

## Correção

Se slide atual = 10:

```text
slide 9
slide 10
slide 11
slide 12
```

podem fornecer o prompt.

Exemplo:

```text
Escape, aquele que acalma..., porque eu não estou...,
o Deus que derruba...
```

Isso tende a ajudar o ASR justamente onde precisamos.

---

# 17. Usar duas janelas textuais diferentes

Não usaria um único rolling transcript para tudo.

## Slide

```text
3–5 segundos
```

Resposta rápida.

## Música

```text
8–12 segundos
```

Mais contexto.

Arquitetura:

```text
TranscriptMerger
       │
       ├── 4 s ──► SlideMatcher
       │
       └── 10 s ─► SongMatcher
```

---

# 18. VAD atual não é VAD de verdade

`EnergyVAD` simplesmente calcula RMS e verifica se a energia passou de um threshold.

Isso significa:

```text
bateria alta
= atividade

guitarra alta
= atividade

instrumental
= atividade
```

E portanto o Whisper pode receber uma introdução instrumental e hallucinar alguma coisa.

## Melhoria

No mínimo:

```text
pré-processamento
↓
energy gate
↓
ASR
↓
estabilidade textual
↓
matcher
```

E nenhuma ação deve ser tomada quando a transcrição estiver instável.

---

# 19. O filtro 300–3400 Hz não é isolamento vocal

O projeto aplica um passa-faixa de aproximadamente 300–3400 Hz antes do Whisper.

Isso pode atenuar:

```text
baixo
bumbo
pratos
```

mas não separa a voz de:

```text
guitarra
teclado
caixa
outros vocais
```

Além disso, pode remover harmônicos importantes da voz cantada.

O README chama isso de “isolamento vocal”, o que é tecnicamente mais forte do que a implementação realmente entrega.

## Sugestão

Tornar opcional:

```text
Filtro vocal experimental
[ ligado/desligado ]
```

e começar testando com ele **desligado**.

Fazer A/B:

```text
RAW

300–3400

80–7000
```

e medir precisão.

---

# 20. O filtro também é aplicado da maneira errada para streaming

É utilizado:

```python
signal.sosfiltfilt(...)
```

em cada chunk isoladamente.

Cada bloco começa do zero, podendo introduzir artefatos nas bordas.

Se o filtro for mantido, utilizar filtragem streaming com estado entre chunks.

---

# 21. O VAD roda antes do filtro

No `AutomationService`:

```text
áudio
↓
EnergyVAD
↓
passa-faixa
↓
Whisper
```

Ou seja, o bumbo que supostamente seria filtrado já pode ter ativado o VAD.

Se o filtro continuar existindo:

```text
áudio
↓
pré-processamento
↓
gate
↓
Whisper
```

---

# 22. Há processamento demais dentro do callback de áudio

O callback de `sounddevice` faz:

```text
copy
↓
mono
↓
dtype
↓
RMS
↓
Peak
↓
resampling
↓
callback seguinte
```

Callbacks de áudio deveriam retornar o mais rapidamente possível.

## Arquitetura melhor

```text
sounddevice callback
       ↓
copiar chunk
       ↓
queue
       ↓
RETORNAR


worker
  ↓
mono
  ↓
resample
  ↓
meter
  ↓
filter
  ↓
buffer
```

Isso reduz risco de perda de áudio.

---

# 23. Resampling não é ideal para streaming

Está sendo utilizado `scipy.signal.resample`.

Eu consideraria:

```text
soxr
```

ou outro resampler adequado para streaming.

---

# 24. Captura pode abrir todos os canais de uma interface

O código utiliza:

```python
channels = max_in
```

quando existem canais de entrada.

Imagine uma interface:

```text
16 entradas
```

A aplicação pode acabar abrindo as 16 e depois fazendo média.

Isso pode destruir a qualidade da voz.

## Correção

Permitir:

```text
Dispositivo: Interface USB

Canal:
[ 1 ]
[ 2 ]
[ 3 ]
...
[ Stereo 1/2 ]
```

Default:

```text
microfone → 1 canal
loopback → 2 canais
```

---

# 25. A identificação de loopback no Windows está problemática

A lógica atual considera loopback WASAPI quando existe:

```text
"loopback" no nome
OU
max_input_channels > 0
```

Na prática, isso pode fazer um microfone WASAPI aparecer como loopback.

---

# 26. `LoopbackAudioSource` não implementa WASAPI loopback real de forma específica

Atualmente ele basicamente localiza um ID e o repassa para `DeviceAudioSource`, que utiliza `sounddevice.InputStream`.

Recomendo adapters reais:

```text
MicrophoneAudioSource

WindowsWasapiLoopbackSource

LinuxMonitorAudioSource

WavAudioSource
```

No Windows, avaliar tecnicamente:

```text
PyAudioWPatch
soundcard
WASAPI loopback específico
```

No Linux:

```text
PipeWire/PulseAudio monitor source
```

---

# 27. Há um fallback perigoso no loopback

Quando não encontra um loopback, `get_default_device("loopback")` pode devolver simplesmente o primeiro dispositivo da lista.

Isso não deveria acontecer.

Se o usuário pediu:

```text
Áudio do sistema
```

e não existe loopback:

```text
❌ Nenhuma saída capturável encontrada
```

Nunca:

```text
usar microfone silenciosamente
```

---

# 28. Groq abre uma nova conexão HTTP a cada transcrição

No `GroqWhisperTranscriber` existe:

```python
with httpx.Client(...) as client:
    response = client.post(...)
```

dentro de `transcribe()`.

Ou seja, uma nova instância HTTP é criada continuamente.

## Correção

Criar um cliente persistente:

```python
self.client = httpx.Client(...)
```

e reutilizá-lo com keep-alive.

No shutdown:

```python
self.client.close()
```

---

# 29. O número de chamadas Groq pode ficar extremamente alto

Considerando uma tentativa aproximadamente a cada 0,18–0,20 s:

```text
até ~5 chamadas/s

≈ 300 chamadas/minuto
```

em cenário ideal de latência baixa.

E grande parte representa áudio repetido.

O novo `ChunkScheduler` resolve boa parte disso.

---

# 30. Implementar backpressure: “latest wins”

Se Groq ficar lenta:

```text
chunk 10
chunk 11
chunk 12
chunk 13
...
```

não interessa transcrever tudo 10 segundos depois.

Para slide ao vivo:

> áudio velho deve ser descartado.

Criar:

```text
max ASR queue = 1 ou 2
```

Quando houver atraso:

```text
descartar chunk velho
manter o mais recente
```

Exibir:

```text
Pipeline lag: 420 ms
Dropped ASR chunks: 3
```

---

# 31. Configuração Groq e Faster Whisper estão misturadas

`TranscriptionSettings.model` tem como padrão o modelo Groq, e quando não existe API key o mesmo valor pode ser passado ao `FasterWhisperTranscriber`.

Separar:

```text
provider = groq | local

groq_model =
  whisper-large-v3-turbo

local_model =
  small
  medium
  large-v3
  turbo
```

---

# 32. Não selecionar engine apenas porque existe API key

Hoje:

```text
tem GROQ_API_KEY
→ Groq

não tem
→ Faster Whisper
```

Melhor UI:

```text
Engine de transcrição

(•) Groq Cloud
( ) Faster Whisper Local
```

Opcionalmente:

```text
Fallback automático para local
```

---

# 33. A transcrição Groq não entrega confiança significativa para o decision engine

O modelo `TranscriptionResult` suporta:

```text
avg_logprob
no_speech_prob
```

O Faster Whisper preenche parte dessas informações.

Já a implementação Groq atual basicamente devolve o texto.

## Melhoria

Adicionar um conceito próprio:

```text
ASR Stability
```

Exemplo:

```text
janela 1:
"aquele que acalma"

janela 2:
"aquele que acalma o vento"

janela 3:
"aquele que acalma o vento"

estabilidade alta
```

versus:

```text
"ele veio"
"eu vivo"
"meu rio"

estabilidade baixa
```

Matcher deveria receber também essa informação.

---

# 34. Melhorar sincronização com Holyrics

O projeto já faz um trabalho interessante para diferenciar mudanças automáticas de intervenção manual usando timestamp e último slide enviado.

Eu evoluiria para:

```python
CommandTracker
```

registrando:

```text
type
song_id
slide
sent_at
expires_at
```

Exemplo:

```text
SHOW_LYRICS
Escape
slide 3
22:15:31.500
```

Quando polling detectar mudança, primeiro verifica se corresponde a um comando enviado.

---

# 35. `ShowLyrics(initial_index)` faz trabalho duplicado

O cliente envia:

```text
ShowLyrics
initial_index = X
```

e depois executa:

```text
ActionGoToIndex(X)
```

Como `initial_index` já foi validado e funciona corretamente, deveria bastar:

```text
ShowLyrics(initial_index=X)
```

Reduz uma requisição e possíveis efeitos visuais intermediários.

---

# 36. Cliente síncrono do Holyrics também recria HTTP client

`post_sync()` cria um `httpx.Client` a cada comando.

Não é tão crítico quanto Groq porque existem muito menos comandos, mas pode ser melhorado.

Arquitetura ideal:

```text
Automation worker
       ↓
Holyrics command queue
       ↓
async command worker
       ↓
httpx.AsyncClient persistente
```

---

# 37. Parser possui risco com índice zero

Há código no estilo:

```python
data.get("slide") or data.get("index")
```

Se algum campo válido for:

```python
0
```

Python considera falso.

Mais robusto:

```python
first_not_none(...)
```

Mesmo que o endpoint atual devolva 1-based, vale corrigir.

---

# 38. Existe um problema de tratamento de exceção no `HolyricsService`

O módulo captura:

```python
httpx.ConnectError
httpx.ConnectTimeout
...
```

mas no código analisado não aparece `import httpx` no início do arquivo.

Isso deve ser corrigido e testado simulando desconexão.

---

# 39. Muitos erros estão sendo escondidos com `except Exception: pass`

Isso aparece no estado, sincronização, UI e inicialização.

Durante desenvolvimento de uma aplicação em tempo real isso é perigoso.

Em vez de:

```python
except Exception:
    pass
```

usar:

```python
except Exception as exc:
    logger.exception(...)
```

Se for um erro esperado, pode limitar a frequência do log para não poluir a interface.

---

# 40. Estado e UI podem sofrer concorrência

`AppState` possui listeners e os chama diretamente.

O `AutomationService` roda worker em outra thread, enquanto Holyrics e UI utilizam asyncio/Flet.

Recomendo uma fila de eventos:

```text
Audio/ASR thread
       ↓
AppEventQueue
       ↓
Main/UI loop
       ↓
AppState
       ↓
Flet
```

Isso também simplifica debugging.

---

# 41. Métricas de dropped frames não estão realmente implementadas

Existem:

```text
dropped_frames
audio_dropped_frames
```

no buffer/estado.

Mas falta conectá-las a eventos reais.

Medir:

```text
audio callback overflow
queue overflow
ASR chunks descartados
pipeline lag
queue depth
```

---

# 42. Cache das músicas pode manter uma letra antiga

`HolyricsService` usa cache baseado no ID da música. Se a letra for alterada no Holyrics mantendo o mesmo ID, existe risco de continuar usando o objeto cacheado.

Adicionar:

```text
Forçar recarga de letras
```

e/ou TTL/hash.

---

# 43. requirements.txt está vazio

O repositório possui `requirements.txt` vazio, enquanto as dependências estão no `pyproject.toml`.

Mas o README manda:

```bash
pip install -r requirements.txt
```

## Correção

Eu utilizaria:

```bash
pip install -e .
```

e manteria `pyproject.toml` como fonte oficial de dependências.

---

# 44. Falta `python-dotenv` nas dependências mostradas

`defaults.py` importa:

```python
from dotenv import load_dotenv
```

Mas o `pyproject.toml` analisado não lista `python-dotenv`.

Adicionar.

---

# 45. Alguns testes dependem do ambiente do desenvolvedor

Por exemplo, há teste esperando:

```text
192.168.1.137
```

como host.

Testes automatizados não deveriam depender do `.env` real da máquina.

Usar:

```python
AppSettings(
    holyrics=HolyricsSettings(
        host="test-host"
    )
)
```

ou fixture equivalente.

---

# 46. Testes atuais não reproduzem o principal problema

Os testes de matcher cobrem identificação simples e refrão repetido, o que é bom.

Mas precisamos adicionar cenários de regressão específicos:

| Cenário | Resultado esperado |
|---|---|
| 1 chunk errado aponta outra música | manter música atual |
| 2 chunks errados | manter |
| 3–4 chunks consistentes em outra música | trocar |
| contexto A permanece ao iniciar B | deve ser limpo |
| refrão repetido | usar proximidade |
| cantor volta ao refrão | permitir com confiança alta |
| instrumental | nenhuma troca |
| Groq lenta | descartar backlog |
| Holyrics offline | não cair |
| áudio sobreposto | deduplicar transcript |
| palavras genéricas de duas músicas | não trocar sem margem |

---

# 47. O teste de “UI não bloqueante” precisa ser mais forte

Hoje há teste cujo principal check é que o ring buffer existe.

Deveria simular:

```text
ASR demora 2 segundos
+
áudio continua chegando
+
UI tick continua funcionando
```

e verificar que não cresce fila indefinidamente.

---

# Arquitetura alvo recomendada

```text
       Microfone / Loopback / WAV
                  │
                  ▼
          RAW AUDIO CALLBACK
                  │
                  ▼
           Raw Audio Queue
                  │
                  ▼
       Audio Processing Worker
     mono / resample / optional DSP
                  │
                  ▼
          Streaming Buffer
                  │
                  ▼
          Chunk Scheduler
       janela 2.5s / hop 0.8s
                  │
                  ▼
            ASR Engine
          Groq ou Local
                  │
                  ▼
         TranscriptMerger
                  │
          ┌───────┴────────┐
          │                │
          ▼                ▼
     últimos 4s       últimos 10s
          │                │
          ▼                ▼
   SlideMatcher       SongMatcher
          │                │
          │       SongStateMachine
          │                │
          └───────┬────────┘
                  ▼
        Decision Coordinator
                  │
                  ▼
          Holyrics Queue
                  │
                  ▼
        Holyrics API Server
```

---

# Ordem que eu passaria para o agente

## Fase 1
Corrigir scheduler de áudio, deduplicação do transcript e cliente HTTP persistente da Groq.

## Fase 2
Implementar `SongStateMachine`, `SongTransitionDecisionEngine`, travamento de música e limpeza total de contexto.

## Fase 3
Recalibrar thresholds, remover bypass de 96%, busca local de slides e regras diferentes para saltos grandes.

## Fase 4
Melhorar prompt contextual, SongMatcher discriminativo e estabilidade temporal do ASR.

## Fase 5
Refatorar captura de áudio, loopback Windows/Linux, canais e DSP/VAD.

## Fase 6
Corrigir robustez, exceções, dependências, estado concorrente e ampliar testes.

---

# Configuração inicial que eu testaria após a refatoração

```yaml
audio:
  transcription_window: 2.5
  transcription_hop: 0.8

transcript:
  slide_window: 4.0
  song_window: 10.0

song:
  initial_threshold: 90
  transition_threshold: 92
  margin: 10
  confirmations: 3
  transition_min_duration: 3.0

slide:
  possible_threshold: 75
  strong_threshold: 88
  strong_confirmations: 2
  possible_confirmations: 3

decision:
  cooldown: 0.9
  large_jump_threshold: 94
  backward_jump_threshold: 92

audio_processing:
  bandpass_filter: false
```

---

# Diretriz principal para o agente

A mudança conceitual mais importante para orientar o agente é esta:

> **O Whisper não deve decidir a música nem o slide. Ele deve apenas produzir evidências. A decisão final deve vir de uma máquina de estados que conhece a música atual, o slide atual, a sequência provável, o histórico e a estabilidade das últimas transcrições.**

Isso deve ser tratado como requisito central da próxima refatoração.

---

# Conclusão

Não recomendo reescrever o sistema em Node.js.

O problema está muito mais relacionado a:

```text
pipeline temporal
sobreposição excessiva
deduplicação
matching
thresholds
máquina de estados
captura de áudio
estabilidade da transcrição
```

do que à linguagem.

A base do projeto pode ser preservada e evoluída com refatorações direcionadas, com foco em precisão e estabilidade para uso ao vivo.
