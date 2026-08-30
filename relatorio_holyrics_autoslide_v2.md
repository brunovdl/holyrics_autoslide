# Holyrics AutoSlide — Revisão Técnica V2 e Plano de Evolução para Baixa Latência e Alta Precisão

**Projeto:** `brunovdl/holyrics_autoslide`  
**Revisão baseada no commit:** `8a114b3fce380b452c3e1917d12ffab1b5e18310`  
**Data da revisão:** 29/08/2026  
**Objetivo:** reduzir drasticamente trocas erradas, evitar mistura entre músicas e diminuir o tempo entre o canto e a troca do slide no Holyrics.

---

## 1. Resumo executivo

A refatoração mais recente melhorou significativamente a arquitetura do Holyrics AutoSlide. Foram introduzidos componentes importantes como:

- `ChunkScheduler`;
- `TranscriptMerger`;
- `SongStateMachine`;
- `SongTransitionDecisionEngine`;
- busca local de slides;
- regras mais rígidas para saltos grandes;
- conexão HTTP persistente com a Groq;
- testes específicos para scheduler, merger e máquina de estados.

Essas mudanças atacam diretamente os principais problemas da primeira versão: filas de áudio atrasadas, troca precipitada de música, repetição de transcrição e falsos positivos de slide.

Entretanto, ainda existem problemas estruturais que podem causar:

- atraso perceptível na troca de slides;
- retranscrição de janelas quase idênticas;
- contaminação do histórico textual;
- identificação incorreta de refrões;
- divergência entre a música exibida no Holyrics e a música que a máquina de estados considera ativa;
- feedback negativo do prompt do Whisper durante transições;
- processamento excessivo dentro do callback de áudio;
- dependência excessiva de transcrição aberta para um problema que, na prática, é de rastreamento de uma letra conhecida.

A conclusão principal desta revisão é:

> **Não é recomendável migrar o projeto de Python para Node.js para tentar resolver precisão ou latência. O maior ganho virá de uma mudança no desenho do reconhecimento e do pipeline, não da linguagem.**

O problema mais importante neste momento é que a aplicação continua tratando a transcrição como a fonte principal de verdade. Para atingir precisão muito alta, a arquitetura deveria ser invertida:

> **O Holyrics e a letra conhecida devem definir o universo de possibilidades; o ASR deve servir apenas como evidência para localizar onde o cantor está dentro dessa letra.**

Essa mudança é muito mais relevante do que simplesmente trocar a Groq por outro serviço.

---

# 2. O que melhorou na refatoração atual

## 2.1. Máquina de estados de música

A criação de `SongStateMachine` e `SongTransitionDecisionEngine` foi uma das melhores mudanças realizadas.

A aplicação agora formaliza estados como:

- `SEARCHING_SONG`;
- `SONG_CANDIDATE`;
- `SONG_LOCKED`;
- `SONG_TRANSITION_CANDIDATE`.

Isso reduz o risco de uma única transcrição ruim fazer a aplicação saltar para outra música da playlist.

A transição exige:

- score mínimo;
- margem em relação à segunda música;
- confirmações consecutivas;
- tempo mínimo de candidatura.

Esse mecanismo é muito mais seguro que tomar a decisão diretamente a partir do melhor resultado do matcher.

---

## 2.2. Separação entre janela de slide e janela de música

A utilização de uma janela curta para slide e uma janela maior para identificação de música é conceitualmente correta.

Atualmente o sistema trabalha aproximadamente com:

- janela curta de cerca de 4 segundos para slides;
- janela longa de cerca de 10 segundos para música.

Isso é melhor do que usar o mesmo contexto para as duas decisões, pois:

- slide precisa reagir rapidamente;
- música precisa de mais contexto e deve ser conservadora.

---

## 2.3. `ChunkScheduler`

A introdução do scheduler baseado em quantidade real de amostras foi positiva.

A ideia de:

- janela acústica de 2,5 s;
- avanço a cada 0,8 s;
- política de backpressure;
- descarte do atraso antigo;

é adequada para um sistema que precisa operar próximo do tempo real.

O conceito de **latest wins** também é correto: em automação de apresentação, um resultado atrasado geralmente não tem valor. É melhor descartar áudio antigo do que trocar o slide com vários segundos de atraso.

---

## 2.4. `TranscriptMerger`

Separar a fusão de transcrições em um componente próprio foi uma boa decisão.

A aplicação não deve simplesmente concatenar as respostas de janelas sobrepostas, pois isso gera sequências como:

```text
Aquele que acalma o vento
que acalma o vento e o mar
vento e o mar é o meu Deus
```

sem deduplicação.

O novo componente já resolve o caso de sobreposição exata.

Ainda há melhorias necessárias, tratadas posteriormente neste documento.

---

## 2.5. Busca local de slides

Priorizar a região próxima do slide atual é uma decisão correta.

Em uma música normal, a maior probabilidade é:

```text
slide atual -> próximo slide
```

seguida de possibilidades como:

```text
slide atual -> atual + 2
slide atual -> refrão anterior
```

Isso permite usar contexto temporal, em vez de comparar todos os slides como se todos fossem igualmente prováveis.

---

## 2.6. Regras diferentes por distância do salto

O `SlideDecisionEngine` ficou mais robusto ao exigir evidências diferentes dependendo da distância entre o slide atual e o candidato.

Isso é importante porque:

- `N -> N+1` é uma transição natural;
- `N -> N+2` é menos comum;
- `N -> slide distante` precisa de evidência forte;
- retorno para refrão precisa ser permitido, mas não pode ocorrer por uma coincidência fraca.

---

## 2.7. Cliente HTTP persistente na Groq

Reutilizar `httpx.Client` evita criar uma nova conexão TCP/TLS para cada transcrição.

Isso reduz overhead de rede e é uma melhoria válida para o pipeline atual.

---

# 3. Problemas encontrados que ainda precisam ser corrigidos

Os itens abaixo estão em ordem de prioridade.

---

# P0 — Correções críticas

## 3.1. `ChunkScheduler` pode processar praticamente a mesma janela mais de uma vez

### Problema

O scheduler mantém `_last_processed_total`, porém `get_chunk_for_inference()` sempre busca:

```python
ring_buffer.get_recent(window_duration)
```

Ou seja: a janela retornada termina sempre no áudio mais recente disponível.

Se o worker estiver atrasado por aproximadamente dois hops, pode ocorrer a seguinte situação:

1. existe backlog;
2. o scheduler entrega a janela mais recente de 2,5 s;
3. `_last_processed_total` avança apenas um hop;
4. o loop imediatamente considera que ainda existe outro hop pendente;
5. `get_recent(2.5)` retorna outra janela quase igual à anterior;
6. o Whisper recebe conteúdo repetido;
7. o merger precisa tentar corrigir uma duplicação que poderia ter sido evitada na origem.

### Correção recomendada

Como a política desejada é **latest wins**, depois que uma janela atual for entregue ao ASR:

```python
self._last_processed_total = current_total
```

O backlog antigo deve ser contabilizado apenas como métrica:

```python
dropped_hops = max(0, diff // hop_samples - 1)
self.dropped_chunks += dropped_hops
```

Não deve existir tentativa de “recuperar” áudio atrasado em uma automação de slides.

### Testes necessários

Criar testes para:

- backlog de 2 hops;
- backlog de 5 hops;
- garantir que duas inferências consecutivas não sejam disparadas sem áudio novo real;
- validar `dropped_chunks`;
- validar que após `get_chunk_for_inference()` não exista imediatamente outro chunk disponível sem novas amostras.

---

## 3.2. Estado do Holyrics e `SongStateMachine` podem divergir

### Problema

`HolyricsService.sync_current_presentation()` pode alterar diretamente:

```python
state.current_song
```

porém o `SongTransitionDecisionEngine` mantém seu próprio:

```python
state_machine.locked_song
```

Isso permite um estado inconsistente:

```text
Holyrics / UI: música B
SongStateMachine: música A
```

Depois disso, o matcher e o motor de decisão podem começar a lutar entre si.

### Correção recomendada

Criar um evento explícito de alteração de música:

```python
on_current_song_change(old_song, new_song, source)
```

O `source` pode ser:

```text
HOLYRICS_MANUAL
AUTOMATION
INITIAL_SYNC
```

Quando a mudança for externa/manual:

```python
reset_context_for_song_change()
song_decision_engine.set_active_song(new_song)
```

Também criar algo equivalente a:

```python
mark_song_command_sent(song_id)
```

para impedir que um `ShowLyrics` enviado pelo próprio AutoSlide seja interpretado depois como intervenção manual.

---

## 3.3. Busca local pode impedir que o refrão correto seja sequer avaliado

### Problema

O matcher atualmente pode retornar imediatamente quando algum candidato local alcança cerca de 75%.

Exemplo:

```text
Slide atual: 8
Cantor volta para refrão: slide 3

melhor local: slide 9 = 77%
refrão real: slide 3 = 97%
```

Se a função retornar nos 77%, o slide 3 nunca chega ao motor de decisão.

### Correção recomendada

A busca local deve ser uma **prioridade**, não um bloqueio.

Fluxo recomendado:

```text
1. calcular melhores candidatos locais
2. calcular candidato global
3. comparar local x global
4. aplicar prior temporal
5. mandar melhor hipótese ao motor de decisão
```

Uma regra possível:

```text
Se global_score >= local_score + 10
    considerar global
Senão
    manter local
```

Para saltos globais, o próprio `SlideDecisionEngine` já deve exigir score e confirmações maiores.

---

## 3.4. Processamento pesado dentro do callback de áudio

### Problema

O callback do `sounddevice` executa operações como:

- cópia de array;
- conversão para mono;
- cálculo de RMS e peak;
- reamostragem;
- callback de UI;
- escrita no ring buffer.

Se a interface estiver em 44,1 kHz ou 48 kHz, o código pode usar `scipy.signal.resample()` repetidamente dentro do callback de tempo real.

Isso é um ponto perigoso.

Callback de áudio deveria realizar o mínimo de trabalho possível.

### Consequências possíveis

- jitter;
- dropout;
- callback atrasado;
- pedaços de áudio perdidos;
- descontinuidades;
- pior entrada para o ASR;
- transcrição instável.

### Correção recomendada

Callback:

```text
capturar -> copiar para buffer raw -> retornar
```

Worker de áudio separado:

```text
raw buffer
    -> seleção de canais
    -> mono
    -> resampler streaming/stateful
    -> VAD
    -> ring buffer de ASR
```

Também não usar automaticamente todos os `max_input_channels`.

Uma interface com 8 canais não deveria automaticamente fazer média dos 8 canais.

Configurar explicitamente:

- canal 1;
- canal 2;
- estéreo 1+2;
- ou dispositivo/canal selecionado pelo usuário.

---

## 3.5. Prompt do Whisper pode prender a aplicação na música errada

### Problema

O prompt contextual é construído utilizando:

- título da música atual;
- palavras dos slides próximos.

Enquanto a música atual está correta, isso ajuda.

Durante a transição, porém, pode criar este loop:

```text
Música A está travada
        ↓
Começa música B
        ↓
Whisper recebe prompt da música A
        ↓
áudio ambíguo é interpretado como palavras de A
        ↓
matcher identifica A
        ↓
máquina conclui que A continua
        ↓
prompt de A continua sendo enviado
```

### Correção recomendada

Usar prompt diferente conforme estado.

#### `SONG_LOCKED` com alta confiança

Pode usar letra local da música atual.

#### confiança caindo

Reduzir o prompt.

#### `SONG_TRANSITION_CANDIDATE`

Remover o texto dos slides atuais.

Usar, no máximo:

- nomes das músicas da playlist;
- artistas;
- termos discriminativos.

#### `SEARCHING_SONG`

Não enviesar para uma música específica.

---

## 3.6. O `SongMatcher` usa o score discriminativo de forma que pode reduzir a música correta

### Problema

A ideia de valorizar palavras raras da playlist é excelente, porém a implementação atual combina o discriminador com o score base de maneira que termos comuns podem reduzir o score final.

Em repertório de igreja, palavras como:

```text
Deus
Senhor
Jesus
amor
graça
santo
glória
```

aparecem em muitas músicas.

O discriminador deveria ajudar quando existe informação rara, não punir quando ela não existe.

### Correção recomendada

Usar IDF.

Exemplo conceitual:

```python
idf = log((N + 1) / (df + 1)) + 1
```

Criar um bônus positivo limitado:

```text
base_score = similaridade textual
rare_word_bonus = 0..15
final = min(100, base_score + rare_word_bonus)
```

O discriminador nunca deveria derrubar um score textual excelente.

---

# P1 — Alta prioridade

## 3.7. `TranscriptMerger` depende de overlap exato

### Problema

Hoje a fusão encontra a maior igualdade exata entre:

```text
sufixo do histórico
prefixo da nova transcrição
```

Whisper nem sempre produz janelas perfeitamente iguais.

Exemplo:

```text
janela 1: aquele que acalma o vento
janela 2: é aquele que acalma os ventos e o mar
```

Existe correspondência semântica e temporal, mas não igualdade literal.

### Correção recomendada

Ordem de preferência:

1. timestamps de segmento;
2. timestamps de palavra;
3. alinhamento fuzzy de tokens.

Se timestamps estiverem disponíveis, cada palavra pode ser inserida na timeline pelo tempo do áudio e a deduplicação deixa de depender apenas do texto.

---

## 3.8. Bug no reset de `candidate_score`

### Problema

`AppState` possui:

```python
candidate_score
```

mas `reset_context_for_song_change()` escreve em:

```python
candidate_slide_score
```

Como o dataclass não utiliza `slots=True`, Python permite criar o atributo novo silenciosamente.

O valor verdadeiro de `candidate_score` pode permanecer antigo.

### Correção

Substituir por:

```python
self.state.candidate_score = 0.0
```

Idealmente considerar `slots=True` em dataclasses importantes para transformar erros desse tipo em falhas imediatas durante desenvolvimento.

---

## 3.9. Fallback local do Faster-Whisper está configurado com parâmetros da Groq

### Problema

Os defaults incluem valores como:

```text
model = whisper-large-v3-turbo
device = cloud
compute_type = api
```

Esses parâmetros pertencem ao fluxo de nuvem.

O `FasterWhisperTranscriber` espera parâmetros como:

```text
model = large-v3 / medium / small
device = cpu / cuda
compute_type = int8 / float16
```

### Correção

Separar configurações:

```text
transcription.provider

groq.model
groq.api_key

deepgram.model
deepgram.api_key

local.model
local.device
local.compute_type
```

---

## 3.10. Slides vazios podem quebrar indexação

### Problema

No carregamento do Holyrics, slides vazios podem ser descartados, mas o índice original é mantido.

Então pode ocorrer:

```text
posição da lista != índice do Holyrics
```

Posteriormente, códigos como:

```python
current_song.slides[target_idx]
```

assumem que posição e índice são iguais.

### Correção recomendada

Opção A — preservar todos os slides.

Ou opção B — criar APIs explícitas:

```python
song.get_slide_by_holyrics_index(index)
song.get_position_by_holyrics_index(index)
```

Nunca usar índice externo diretamente como posição de lista.

---

## 3.11. Configurações antigas não controlam mais o pipeline real

Existem configurações como:

- `chunk_duration`;
- `overlap_duration`;
- `rolling_window_duration`.

Porém o novo pipeline usa vários valores hardcoded.

Isso dificulta calibração e pode fazer a interface mostrar uma configuração que não altera o comportamento real.

### Correção

Centralizar todos os parâmetros temporais em configuração:

```text
audio.asr_window_ms
audio.asr_hop_ms
matching.slide_window_ms
matching.song_window_ms
transcript.history_ms
```

---

# P2 — Melhorias de consistência

## 3.12. README chama filtro passa-faixa de isolamento vocal

Um filtro de aproximadamente 300–3400 Hz não isola vocal de uma música.

Ele apenas restringe a banda de frequência.

Instrumentos como:

- guitarra;
- teclado;
- caixa;
- harmônicos de outros instrumentos;

continuam ocupando a mesma região.

Além disso, canto possui informação útil fora dessa faixa.

O README deveria utilizar termos como:

```text
filtro de banda de voz
pré-processamento espectral
```

em vez de afirmar isolamento vocal.

---

# 4. Por que a Groq não está entregando o comportamento necessário

A Groq não é necessariamente lenta no tempo de inferência do modelo. O problema é que o tipo de integração utilizado não é ideal para este caso.

A API atual utiliza requisições de transcrição de blocos/arquivos de áudio.

O fluxo fica semelhante a:

```text
capturar áudio
    ↓
esperar janela
    ↓
montar WAV
    ↓
POST HTTP
    ↓
processar Whisper
    ↓
receber transcrição completa
    ↓
merger
    ↓
matcher
    ↓
decision engine
    ↓
HTTP Holyrics
```

Mesmo que a inferência da Groq seja rápida, existe uma latência estrutural acumulada.

Além disso, `whisper-large-v3-turbo` prioriza velocidade/custo em relação ao `whisper-large-v3` completo.

A própria documentação da Groq atualmente posiciona:

- `whisper-large-v3` para aplicações sensíveis a erro;
- `whisper-large-v3-turbo` para melhor relação preço/desempenho.

Logo, para este projeto, utilizar o Turbo como mecanismo principal de decisão já representa um compromisso de precisão.

Porém simplesmente trocar para `whisper-large-v3` não resolve o problema arquitetural completo.

---

# 5. Problema fundamental: canto não é fala comum

O sistema está tentando resolver um problema de **lyric tracking** utilizando um modelo genérico de **speech-to-text**.

Isso funciona parcialmente, mas existe uma diferença importante.

ASR convencional normalmente espera:

```text
fala
voz dominante
ritmo de fala
pronúncia relativamente clara
```

No louvor ao vivo existe:

```text
voz cantada
notas sustentadas
melismas
repetição
mudança de ritmo
bateria
guitarras
teclado
backing vocals
reverb
retorno da igreja
congregação
```

Isso aumenta muito a probabilidade de erros de reconhecimento.

Portanto, não existe garantia de que trocar Groq por outro ASR genérico produzirá a melhoria “absurda” de precisão desejada.

A arquitetura precisa explorar uma vantagem que já existe:

> **O sistema conhece antecipadamente todas as letras possíveis.**

Esse é o ponto mais importante de toda a solução.

---

# 6. Arquitetura V2 recomendada — rastreador de letra conhecido

## 6.1. Princípio

Em vez de perguntar:

> “O que essa pessoa está cantando?”

perguntar:

> “Entre estas poucas linhas conhecidas, em qual delas o cantor provavelmente está agora?”

Isso transforma um problema aberto em um problema fechado.

---

## 6.2. Holyrics deve ser a fonte primária da música atual

Quando o Holyrics já está projetando uma música, não existe motivo para o ASR tentar redescobrir continuamente qual música está tocando.

Fluxo recomendado:

```text
Holyrics informa música atual
        ↓
AutoSlide trava essa música
        ↓
ASR/matcher procuram SOMENTE seus slides
        ↓
transição de música é tratada separadamente
```

Isso remove uma grande quantidade de falsos positivos.

### Identificação de nova música

A identificação automática da próxima música deve ser um subsistema independente e conservador.

Ela pode utilizar uma janela maior, por exemplo:

```text
5–10 s
```

E somente alterar a música após forte confirmação.

A troca de **slide** não deveria depender da redescoberta contínua da música.

---

# 7. Novo `LyricTracker`

Criar um componente responsável pela localização temporal dentro da letra.

Exemplo:

```text
LyricTracker
├── current_song
├── current_slide
├── candidate_slide
├── transition_graph
├── token_history
├── confidence
└── position_probability[]
```

Ele deve conhecer a estrutura completa da música.

---

## 7.1. Grafo de transições

Em vez de tratar os slides como uma lista simples:

```text
0 -> 1 -> 2 -> 3 -> 4 -> 5
```

criar um grafo probabilístico.

Exemplo:

```text
0 -> 1
1 -> 2
2 -> 3
3 -> 4
4 -> 5
5 -> 6
6 -> 3   # volta ao refrão
6 -> 7
```

Transições naturais recebem prioridade alta.

Saltos recebem prioridade baixa, mas continuam possíveis.

Isso é equivalente a aplicar uma lógica semelhante a HMM/Viterbi sobre os estados da letra.

---

## 7.2. Score de emissão

Para cada nova evidência do ASR:

```text
texto parcial
palavras estáveis
probabilidade/timestamp
```

calcular:

```text
P(evidência | slide)
```

O score pode combinar:

```text
similaridade textual
+ palavras distintivas
+ sequência de palavras
+ início da estrofe
+ proximidade temporal
+ estado anterior
```

---

## 7.3. Score final

Conceitualmente:

```text
score_final =
    emission_score
    + transition_prior
    + unique_words_bonus
    + sequence_bonus
    - jump_penalty
```

Assim, um slide próximo com 80% pode vencer um distante com 82%, mas um refrão distante com 98% ainda consegue vencer.

---

# 8. Não esperar uma frase completa para trocar o slide

O sistema atualmente depende de blocos relativamente grandes.

Para reduzir latência, a decisão deve utilizar **palavras parciais estáveis**.

Exemplo de slide:

```text
Tu és fiel Senhor
Meu Pai celeste
```

Se as primeiras palavras `tu és fiel` forem distintivas na música, não existe motivo para esperar toda a frase.

Pré-computar para cada slide:

```text
primeiras 2 palavras
primeiras 3 palavras
primeiras 4 palavras
ngrams distintivos
palavras exclusivas
```

Exemplo:

```python
slide.signature = {
    "starts": ["tu es", "tu es fiel", "tu es fiel senhor"],
    "rare_ngrams": [...],
    "keywords": [...]
}
```

Isso pode antecipar a decisão em centenas de milissegundos ou até mais de um segundo.

---

# 9. Alternativas à Groq que devem ser benchmarkadas

Nenhuma alternativa deve ser adotada apenas pela documentação. É necessário testar com áudio real de louvor.

---

## 9.1. Deepgram Nova-3 Streaming — primeira alternativa que eu testaria

### Motivo

Deepgram possui API de STT realmente orientada a streaming e suporta resultados intermediários.

Isso elimina a necessidade de criar milhares de pequenos WAVs e fazer um POST independente para cada janela.

Fluxo:

```text
captura contínua
        ↓
WebSocket persistente
        ↓
ASR streaming
        ↓
interim transcript
        ↓
LyricTracker
```

A documentação atual do Nova-3 também possui **Keyterm Prompting**, permitindo fornecer até 100 termos/frases importantes.

No Holyrics AutoSlide, esses keyterms podem ser gerados dinamicamente a partir:

- do slide atual;
- dos próximos slides;
- do refrão;
- das palavras raras da música.

Isso é muito mais alinhado ao problema do que um prompt genérico.

### Estratégia dinâmica

Se estiver no slide 4, enviar como contexto prioritário:

```text
slide 4
slide 5
slide 6
refrão principal
```

Não enviar a playlist inteira sem necessidade.

### Importante

Deepgram ainda é um ASR genérico. Precisa ser validado com **voz cantada e banda ao vivo**.

---

## 9.2. Groq `whisper-large-v3` completo — benchmark obrigatório antes de abandonar Groq

Antes de remover Groq completamente, testar o modelo completo:

```text
whisper-large-v3
```

em vez de:

```text
whisper-large-v3-turbo
```

A própria documentação da Groq indica o Large V3 para cenários sensíveis a erro.

Esse teste serve para medir quanto do problema vem:

- do modelo Turbo;
- e quanto vem da arquitetura de chunking.

Não considero, porém, que isso sozinho resolva a latência estrutural do POST por bloco.

---

## 9.3. Google Speech-to-Text com model adaptation

Google possui recursos de adaptação de vocabulário/frases.

Isso permite enviesar o reconhecedor para palavras e frases conhecidas.

Pode ser interessante como benchmark por causa do universo fechado das letras.

Novamente: precisa ser testado com canto, não apenas fala.

---

## 9.4. NVIDIA Canary 1B v2 local

O `Canary-1B-v2` suporta Português e timestamps.

Pode ser uma alternativa interessante se houver GPU NVIDIA disponível.

Benefícios:

- processamento local;
- nenhuma ida à nuvem;
- controle de pipeline;
- possibilidade de integração mais profunda.

Cuidado: a própria documentação/model card informa diferenças de variante do Português e que muito do treinamento em português é europeu, portanto é necessário testar especificamente PT-BR.

Sem GPU adequada, não considero essa a primeira opção para o desktop do operador.

---

## 9.5. Faster-Whisper local

Também pode ser benchmarkado, principalmente com GPU.

Porém executar `large-v3` localmente em CPU e esperar latência extremamente baixa provavelmente será inviável.

Modelos menores podem reduzir latência, mas tendem a perder precisão justamente no cenário difícil de canto + música.

---

# 10. Minha recomendação de tecnologia para a próxima versão

## Opção recomendada para protótipo V2

```text
Audio Capture
    ↓
Raw Audio Queue
    ↓
Streaming Resampler
    ↓
VAD leve
    ↓
Deepgram Nova-3 Streaming
    ↓
Partial Transcript / Stable Words
    ↓
LyricTracker
    ↓
Slide Decision FSM
    ↓
Holyrics API
```

Em paralelo:

```text
Holyrics Polling/Event
    ↓
Current Song Lock
    ↓
LyricTracker Context
```

A detecção de troca de música fica em um pipeline mais lento e conservador.

---

# 11. O áudio de entrada pode ser mais importante que o ASR

Se o sistema estiver ouvindo o **mix completo do culto**, existe um limite físico para a precisão do reconhecimento.

O melhor cenário seria receber do mixer uma saída dedicada contendo principalmente voz.

Por exemplo:

```text
mesa de som
    ↓
AUX / BUS de vocais
    ↓
interface USB
    ↓
Holyrics AutoSlide
```

Isso pode produzir uma melhoria maior que trocar de fornecedor de ASR.

Idealmente enviar:

- vocal principal;
- backing vocals em volume moderado;
- pouco ou nenhum instrumento.

Se existir acesso à mesa de som, essa é uma das primeiras coisas que eu testaria.

### Evitar acreditar que band-pass = separação vocal

Filtro 300–3400 Hz não consegue remover instrumentos que ocupam essa mesma faixa.

Separação neural estilo Demucs pode melhorar isolamento, mas geralmente adiciona custo e latência incompatíveis com a troca de slides ao vivo, salvo implementação especializada/GPU.

---

# 12. Estratégia de latência

O objetivo deve ser medir toda a cadeia.

Adicionar timestamps para:

```text
T0 = áudio capturado
T1 = áudio enviado ao ASR
T2 = resultado parcial recebido
T3 = match concluído
T4 = decisão autorizada
T5 = HTTP enviado ao Holyrics
T6 = polling confirma slide alterado
```

Calcular:

```text
capture_to_asr_ms
asr_latency_ms
matching_latency_ms
decision_latency_ms
holyrics_command_ms
end_to_end_ms
```

Sem isso, é fácil culpar o ASR quando o atraso real pode estar em outra etapa.

---

## 12.1. Meta sugerida

Meta inicial para experiência boa:

```text
ASR parcial utilizável: 200–500 ms
matching: < 20 ms
decisão: < 10 ms
Holyrics HTTP: < 100 ms na LAN
end-to-end típico: < 700–900 ms
```

Em trechos altamente distintivos, o sistema pode antecipar ainda mais utilizando início de frase.

---

# 13. Troca de slide não deve usar o mesmo rigor da troca de música

Separar claramente:

## Slide

Precisa ser rápido.

Pode aceitar:

- poucas palavras distintivas;
- forte prior de sequência;
- uma confirmação quando `N -> N+1` for muito evidente.

## Música

Precisa ser conservadora.

Deve exigir:

- janela maior;
- múltiplas confirmações;
- margem forte;
- ausência de correspondência convincente com a música atual.

Essa separação permite ter simultaneamente:

```text
slides rápidos
músicas seguras
```

---

# 14. Thresholds atuais estão baixos para algumas situações

Os defaults atuais incluem aproximadamente:

```text
song_threshold = 75
song_margin = 5
slide_strong = 78
slide_possible = 68
confirmations = 1
cooldown = 0.4s
```

Com uma confirmação, score 78 e texto ruidoso, ainda existe espaço para falsos positivos.

Porém simplesmente aumentar thresholds pode deixar a automação lenta.

A solução não é usar:

```text
threshold = 95 para tudo
```

A solução é aumentar a qualidade do **contexto**.

Exemplo:

```text
slide N -> N+1
+ primeiras 3 palavras exclusivas
+ partial transcript recente
```

pode ser autorizado rapidamente.

Já:

```text
slide N -> slide N-6
```

precisa de evidência muito maior.

---

# 15. Melhorar o matching com sequência, não apenas conjunto de palavras

`token_set_ratio` é útil, mas perde ordem.

Por exemplo:

```text
Jesus meu Senhor é santo
Senhor Jesus santo é meu
```

podem apresentar grande conjunto de tokens em comum.

Para letra cantada, a sequência é valiosa.

Adicionar scores como:

- n-gram de 2 palavras;
- n-gram de 3 palavras;
- longest common subsequence;
- alinhamento local tipo Smith-Waterman simplificado;
- distância de edição ponderada.

Um match de sequência exata de 3–4 palavras distintivas deve valer muito mais do que várias palavras soltas.

---

# 16. Refrões repetidos

Slides idênticos não podem ser resolvidos somente pelo texto.

Se dois slides possuem exatamente:

```text
O meu Deus é o Deus de escape
```

não existe informação acústica textual capaz de distinguir qual ocorrência está sendo cantada.

A decisão obrigatoriamente deve usar contexto estrutural:

```text
posição atual
histórico de slides
sequência provável
estrofe anterior
```

Portanto, para refrões repetidos:

```text
texto identifica o conteúdo
estado da música identifica a ocorrência
```

Esse comportamento deve ser explícito no `LyricTracker`.

---

# 17. Benchmark obrigatório com gravações reais

Não continuar calibrando “no feeling”.

Criar um dataset interno.

## 17.1. Conteúdo

Usar gravações reais de 5–10 músicas.

Incluir:

- banda completa;
- vocal;
- refrões;
- pontes;
- repetições;
- pausas;
- ministrações faladas;
- transições entre músicas;
- erros naturais do cantor;
- mudanças de estrutura.

---

## 17.2. Ground truth

Criar arquivo semelhante a:

```csv
timestamp,song_id,slide_index,event
0.000,123,0,START
8.420,123,1,SLIDE
15.310,123,2,SLIDE
35.870,123,5,CHORUS
...
```

---

## 17.3. Métricas

### Música

```text
song_accuracy
false_song_switches
song_detection_latency
```

### Slide

```text
slide_accuracy
false_slide_switches
missed_switches
```

### Latência

```text
latency_p50
latency_p95
latency_p99
```

### Estabilidade

```text
flapping_count
backward_wrong_jumps
large_wrong_jumps
```

### ASR

```text
WER aproximado
keyword recall
first_distinctive_phrase_latency
```

---

# 18. Benchmark de provedores/modelos

Executar exatamente o mesmo conjunto de áudios contra:

| Variante | Objetivo |
|---|---|
| Groq Whisper Large V3 Turbo | baseline atual |
| Groq Whisper Large V3 | medir ganho de precisão |
| Deepgram Nova-3 Streaming | medir streaming + keyterms |
| Google STT com adaptation | medir bias da letra conhecida |
| Faster-Whisper local | medir viabilidade local |
| NVIDIA Canary 1B v2 | benchmark local se houver GPU |

Não escolher fornecedor por WER publicado em fala comum.

Escolher pelo resultado do **dataset de louvor real**.

---

# 19. Estratégia de implementação em fases

## Fase 1 — Corrigir bugs estruturais atuais

Prioridade máxima:

- [ ] corrigir cursor do `ChunkScheduler`;
- [ ] sincronizar `current_song` com `SongStateMachine`;
- [ ] corrigir `candidate_score`;
- [ ] remover hard-stop prematuro da busca local;
- [ ] corrigir `SongMatcher` discriminativo;
- [ ] tirar resampling pesado do callback;
- [ ] separar canais de áudio explicitamente;
- [ ] corrigir prompt durante transições;
- [ ] criar testes de backlog;
- [ ] criar testes de troca manual de música.

---

## Fase 2 — Instrumentação

- [ ] adicionar timestamps T0–T6;
- [ ] medir latência ponta a ponta;
- [ ] exibir `dropped_chunks`;
- [ ] exibir ASR latency p50/p95;
- [ ] registrar decisão com todos os scores;
- [ ] registrar top 3 candidatos de slide;
- [ ] registrar top 3 candidatos de música;
- [ ] registrar motivo de bloqueio/troca.

---

## Fase 3 — Dataset de benchmark

- [ ] suporte a reprodução WAV determinística;
- [ ] formato ground truth;
- [ ] runner automatizado;
- [ ] relatório CSV/JSON;
- [ ] cálculo de acurácia;
- [ ] cálculo de latência;
- [ ] comparação entre configurações.

---

## Fase 4 — `LyricTracker`

- [ ] criar grafo de slides;
- [ ] gerar assinaturas de cada slide;
- [ ] calcular n-grams distintivos;
- [ ] calcular IDF por música;
- [ ] implementar transition prior;
- [ ] implementar jump penalty;
- [ ] tratar refrões repetidos por estado;
- [ ] usar partial transcript;
- [ ] separar song tracking de slide tracking.

---

## Fase 5 — Provider abstraction

Criar interface:

```python
class StreamingASRProvider:
    async def connect(self): ...
    async def send_audio(self, audio): ...
    async def events(self): ...
    async def update_context(self, context): ...
    async def close(self): ...
```

Implementações:

```text
GroqChunkedProvider
DeepgramStreamingProvider
GoogleStreamingProvider
LocalWhisperProvider
```

O resto da aplicação não deve depender diretamente de Groq.

---

## Fase 6 — Deepgram experimental

- [ ] conexão WebSocket persistente;
- [ ] áudio PCM contínuo;
- [ ] interim results;
- [ ] final results;
- [ ] keyterms dinâmicos;
- [ ] reconexão automática;
- [ ] watchdog;
- [ ] benchmark contra Groq.

Só substituir o provider padrão após o benchmark.

---

# 20. Mudança de arquitetura proposta

## Arquitetura atual simplificada

```text
AUDIO
  ↓
CHUNK 2.5 s
  ↓
GROQ / WHISPER
  ↓
TRANSCRIÇÃO
  ↓
FUZZY MATCH TODA LETRA
  ↓
DECISÃO
  ↓
HOLYRICS
```

## Arquitetura proposta

```text
                       ┌────────────────────┐
                       │      Holyrics       │
                       │ música/slide atual  │
                       └─────────┬──────────┘
                                 │
                                 ▼
                         ┌──────────────┐
                         │ LyricTracker │
                         │ grafo/estado │
                         └──────┬───────┘
                                ▲
                                │ evidência
                                │
┌─────────┐   ┌────────────┐   ┌──────────────┐
│  Áudio  │ → │ Audio Pipe │ → │ Streaming ASR│
└─────────┘   └────────────┘   └──────────────┘
                                │
                                │ partial words
                                ▼
                        ┌─────────────────┐
                        │ Evidence Matcher│
                        └────────┬────────┘
                                 │
                                 ▼
                         ┌──────────────┐
                         │ Decision FSM │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ Holyrics API │
                         └──────────────┘
```

---

# 21. Python ou Node.js?

Continuo recomendando manter Python.

Os problemas encontrados não são causados pelo GIL ou pela linguagem em si.

A maior parte do trabalho pesado ocorre em:

- bibliotecas nativas de áudio;
- NumPy/SciPy;
- rede;
- serviços externos de ASR;
- RapidFuzz;
- modelos nativos.

Trocar para Node.js obrigaria reescrever:

- captura;
- buffer;
- scheduler;
- matching;
- estado;
- integração;
- UI/backend;
- testes;

sem resolver automaticamente:

- ASR ruim em canto;
- prompt bias;
- contexto incorreto;
- transição de estado;
- decisão de refrão;
- áudio contaminado;
- arquitetura de chunking.

Python continua sendo uma escolha adequada.

---

# 22. Minha recomendação objetiva

Não investir mais tempo apenas ajustando thresholds da versão atual.

Executar nesta ordem:

1. **corrigir os P0 deste documento**;
2. **instrumentar a latência ponta a ponta**;
3. **usar o Holyrics como autoridade da música atual**;
4. **criar o `LyricTracker` orientado à letra conhecida**;
5. **testar Deepgram Nova-3 Streaming como primeiro provider alternativo**;
6. **benchmarkar Groq Large V3 completo**;
7. **criar dataset real de músicas da igreja**;
8. **escolher o ASR exclusivamente pelos números desse benchmark**;
9. **se possível, alimentar o AutoSlide com um AUX/BUS de vocais da mesa de som**.

Se essas mudanças forem implementadas corretamente, a aplicação deixa de ser apenas:

> “Whisper tentando adivinhar uma música e um slide”.

Ela passa a ser:

> **“um rastreador determinístico/probabilístico de uma letra conhecida, assistido por reconhecimento de áudio”.**

Essa segunda abordagem é muito mais adequada para atingir precisão alta e baixa latência.

---

# 23. Instrução pronta para o agente de desenvolvimento

Use esta seção como backlog técnico.

## Objetivo

Refatorar o Holyrics AutoSlide para reduzir drasticamente falsos positivos e latência, tornando o ASR um fornecedor de evidência e não a fonte primária de decisão.

## Requisitos obrigatórios

### Pipeline de áudio

- remover processamento pesado do callback do `sounddevice`;
- callback deve apenas copiar/enfileirar frames;
- criar worker de pré-processamento;
- utilizar resampler stateful/streaming;
- permitir seleção explícita de canais;
- medir dropped frames;
- impedir backlog de inferência.

### Scheduler

- corrigir política `latest wins`;
- após consumir a janela recente, cursor deve apontar para `current_total`;
- backlog antigo deve ser descartado;
- criar testes para 2, 3 e 5 hops de atraso.

### Estado de música

- Holyrics deve ser autoridade principal da música projetada;
- sincronizar `AppState.current_song` e `SongStateMachine.locked_song`;
- implementar callback de mudança de música;
- distinguir mudança manual de comando enviado pelo AutoSlide;
- limpar contexto textual na troca confirmada.

### Matching

- remover early-return local baseado apenas em 75%;
- comparar melhor candidato local e global;
- implementar IDF como bônus positivo;
- adicionar n-grams ordenados;
- adicionar score por início de frase;
- adicionar palavras exclusivas;
- adicionar penalidade proporcional ao salto;
- refrões repetidos devem ser desambiguados pelo estado/estrutura.

### `LyricTracker`

Criar novo componente que mantenha:

```text
current_song
current_slide
candidate_slide
slide_probabilities
transition_graph
stable_tokens
last_switch_at
```

O tracker deve receber evidência incremental e produzir candidatos baseados em emissão + transição.

### Prompt/contexto

- prompt específico somente quando a música estiver fortemente travada;
- reduzir prompt quando a confiança cair;
- remover letra da música atual durante `SONG_TRANSITION_CANDIDATE`;
- nunca deixar prompt antigo impedir descoberta da nova música.

### Provider ASR

Criar abstração para múltiplos providers.

Implementar ou preparar:

```text
GroqChunkedProvider
DeepgramStreamingProvider
LocalProvider
```

Deepgram experimental deve utilizar conexão streaming persistente e resultados intermediários.

### Telemetria

Registrar para cada decisão:

```text
audio_timestamp
transcript_partial
transcript_final
current_song
current_slide
top_candidates
scores
decision_reason
asr_latency_ms
end_to_end_latency_ms
```

### Benchmark

Criar runner de arquivos WAV com ground truth.

O runner deve calcular:

```text
song_accuracy
slide_accuracy
false_switches
missed_switches
latency_p50
latency_p95
latency_p99
```

Nenhuma alteração de provider ou threshold deve ser considerada melhor sem comparação pelo benchmark.

---

# 24. Critérios de aceite sugeridos

Antes de utilizar o modo automático em produção:

## Precisão de slide

Meta inicial:

```text
>= 97% das transições corretas no dataset interno
```

## Trocas erradas

Meta:

```text
0 saltos de música falsos em uma execução completa do repertório de teste
```

## Latência

Meta:

```text
p50 <= 700 ms
p95 <= 1200 ms
```

A meta exata pode ser recalibrada com músicos reais, pois antecipação excessiva também pode parecer errada visualmente.

## Backlog

Meta:

```text
nenhum resultado antigo pode provocar troca de slide
```

O sistema deve preferir descartar inferência a executar comando atrasado.

---

# 25. Referências externas consultadas

- Groq Speech-to-Text: https://console.groq.com/docs/speech-to-text
- Groq Whisper Large V3 Turbo: https://console.groq.com/docs/model/whisper-large-v3-turbo
- Groq Whisper Large V3: https://console.groq.com/docs/model/whisper-large-v3
- Deepgram Keyterm Prompting: https://developers.deepgram.com/docs/keyterm
- Deepgram Streaming Speech-to-Text: https://developers.deepgram.com/reference/speech-to-text/listen-streaming
- Google Cloud Speech-to-Text Model Adaptation: https://cloud.google.com/speech-to-text/docs/adaptation-model
- NVIDIA NeMo ASR: https://docs.nvidia.com/nemo/speech/nightly/asr/intro.html
- NVIDIA Canary 1B v2: https://huggingface.co/nvidia/canary-1b-v2

---

# 26. Conclusão

A refatoração atual foi um avanço real. O projeto agora possui componentes corretos para scheduler, merge, state machine e decisão contextual.

Porém, para alcançar o nível de precisão e velocidade desejado, não recomendo continuar apenas adicionando heurísticas em volta do `whisper-large-v3-turbo`.

A próxima evolução deve transformar o AutoSlide em um **sistema de rastreamento de letra conhecida**.

A combinação mais promissora para a próxima prova de conceito é:

```text
Holyrics como contexto autoritativo
+ áudio de voz o mais limpo possível
+ ASR streaming
+ partial transcripts
+ keyterms/phrases dinâmicos
+ LyricTracker probabilístico
+ grafo de transições
+ benchmark com gravações reais
```

O ganho esperado vem principalmente de reduzir a quantidade de possibilidades que o sistema precisa considerar. Em vez de confiar que um modelo genérico transcreva perfeitamente uma apresentação musical ao vivo, a aplicação usa o conhecimento prévio da letra e da posição atual para tomar uma decisão muito mais restrita, rápida e segura.
