# ClaudeFM — Design Spec

**Data:** 2026-05-25  
**Status:** Aprovado

---

## Visão Geral

ClaudeFM é um music player desktop offline para Windows (cross-platform por design). Fluxo central:

1. Buscar metadados via **Last.fm API** (`pylast`)
2. Baixar áudio via **YouTube** (`yt-dlp` + `ffmpeg`)
3. Reproduzir arquivos locais via **miniaudio**
4. Interface HTML/CSS/JS renderizada via **pywebview**

Distribuído como executável standalone via **PyInstaller** — usuário não instala dependências.

---

## Stack Técnico

| Componente | Tecnologia |
|---|---|
| Desktop/webview | `pywebview` |
| Áudio | `miniaudio` |
| Metadados | `pylast` (Last.fm API) |
| Download | `yt-dlp` (bundled) |
| Conversão de áudio | `ffmpeg` (bundled) |
| Banco de dados | SQLite |
| Validação de dados | `pydantic` (BaseModel) |
| Distribuição | PyInstaller (`--onedir`, Windows) |
| Interface | HTML/CSS/JS |

**Formato padrão de download:** m4a. Alternativa configurável: mp3. Configurado nas Settings.

**Query de busca no YouTube:** `"Artista - Música"` — minimiza resultados errados. MVP não oferece mecanismo de substituição de download incorreto.

---

## Estrutura de Arquivos

```
claudefm/
├── app.py                          # Ponto de entrada; startup check; janela pywebview
├── claudefm.spec                   # PyInstaller spec
│
├── services/
│   ├── lastfm_service.py           # Busca via pylast; integrado ao cache
│   ├── youtube_service.py          # Download via yt-dlp; query "Artista - Música"; sanitiza filename
│   └── player_service.py           # Reprodução via miniaudio; controla fila ativa em memória
│
├── models/
│   ├── track.py                    # Track — espelha tabela tracks; valida com Pydantic
│   ├── playlist.py                 # Playlist + PlaylistTrack
│   ├── artist.py                   # Artist — resultado de busca Last.fm (não persiste no DB)
│   └── album.py                    # Album — resultado de busca Last.fm (não persiste no DB)
│
├── api/
│   └── api.py                      # Classe exposta ao pywebview como js_api
│                                   # Métodos: search_lastfm, search_local, download_track,
│                                   #          play, pause, next, prev, get_library,
│                                   #          get_playlists, create_playlist, etc.
│
├── utils/
│   ├── logger.py                   # Logger global; INFO/WARN/ERROR; traceback completo; rotação por sessão
│   └── event_bus.py                # emit(event_type, payload) — centraliza evaluate_js calls
│
├── database/
│   ├── database.py                 # SQLite; schema e queries
│   └── file_manager.py             # Scan de pastas no startup; scan rápido + rescan em background
│
├── interface/
│   ├── pages/
│   │   ├── home.html
│   │   ├── search.html
│   │   ├── artist.html
│   │   ├── album.html
│   │   ├── playlists.html
│   │   ├── playlist_detail.html
│   │   ├── downloads.html
│   │   └── settings.html
│   ├── components/                 # player_bar, track_card, download_panel, context_menu
│   ├── styles/
│   │   ├── main.css
│   │   └── theme.css               # Variáveis de design inspiradas no Spotify
│   └── scripts/
│       ├── api.js                  # Wrapper de window.pywebview.api + handlers de eventos push
│       ├── player.js               # Controles do player; estado da fila
│       └── router.js               # Navegação entre páginas (SPA-like)
│
├── assets/
│   ├── placeholder.png             # Fallback universal para faixas e álbuns
│   ├── artist_placeholder.png      # Fallback específico para artistas
│   └── vendor/
│       ├── ffmpeg.exe              # Bundled — não requer instalação
│       └── yt-dlp.exe              # Bundled — não requer instalação
│
└── logs/
```

---

## Comunicação JS ↔ Python

### JS → Python (ações síncronas/assíncronas)

JS chama métodos via `window.pywebview.api.método(args)` — retorna Promise.

```javascript
api.search_lastfm(query, type)       // → resultados Last.fm
api.search_local(query, type)        // → resultados da biblioteca local
api.download_track(track_id)         // → inicia download (async)
api.play(track_id, context)          // → reproduz e define fila
api.pause()
api.next_track()
api.prev_track()
api.get_library(filter)              // → músicas locais
api.get_playlists()                  // → lista de playlists
api.create_playlist(name)
api.add_to_playlist(playlist_id, track_id)
api.remove_from_playlist(playlist_id, track_id)
api.delete_playlist(playlist_id)
```

### Python → JS (eventos push)

Todos os eventos passam por `event_bus.emit(event_type, payload)` — wrapper central que chama `window.evaluate_js(...)`. Nenhum módulo chama `evaluate_js` diretamente.

```python
# Tipos de evento
{ "type": "download_progress", "track_id": ..., "percent": 72 }
{ "type": "download_complete",  "track_id": ... }
{ "type": "download_error",     "track_id": ..., "message": "..." }
{ "type": "library_scan_complete", "added": 3, "missing": 1 }
{ "type": "playback_ended" }
```

`api.js` registra `onEvent` global e despacha para handlers específicos por tipo.

---

## Concorrência

Operações pesadas rodam em threads separadas via `ThreadPoolExecutor` — nunca bloqueiam a UI ou o event loop do pywebview.

| Operação | Threading |
|---|---|
| Download (`yt-dlp` + `ffmpeg`) | Thread por download; pool com limite de concorrência |
| Scan de biblioteca | Thread dedicada em background |
| Busca Last.fm | Thread por request |
| Playback (`miniaudio`) | Thread dedicada do player |

Downloads simultâneos: limite configurável (padrão: 2). Eventos de progresso emitidos via `event_bus` de dentro das threads.

---

## Fila de Reprodução e Playlists

### Fila Ativa

Fila = contexto de onde a música foi tocada. Clicar em qualquer faixa de um contexto define a fila e inicia naquela faixa.

| Contexto | Nome auto-gerado | Conteúdo |
|---|---|---|
| Busca local `"tame impala"` | `tame impala` | Todos os resultados da query |
| Álbum | Nome do álbum | Todas as faixas do álbum na biblioteca |
| Artista | Nome do artista | Todas as faixas do artista na biblioteca |
| Pasta configurada | Nome da pasta | Todas as músicas da pasta |
| Biblioteca inteira | `Todas as músicas` | Toda a biblioteca local |

- Navegação ⏮⏭ é linear dentro da fila ativa
- Última faixa toca → exibe "Fila acabou" no player bar
- Trocar contexto substitui fila ativa
- Shuffle: fora do escopo dessa versão
- Estado da fila: em memória durante a sessão

### Persistência mínima do player

Ao fechar o app, salva nas settings:
- `player_last_track_id` — ID da faixa que estava tocando
- `player_last_position` — posição em segundos
- `player_last_context` — contexto/fila ativa (serializado como JSON)

Ao reabrir, restaura automaticamente faixa e posição (não retoma reprodução — apenas posiciona).

### Auto-save de Filas como Playlists

Toda fila gerada por contexto é salva automaticamente como playlist com `type = 'auto'`. Se contexto idêntico já existe → atualiza faixas, não duplica.

Limite de retenção: máximo 15 playlists `auto`. Ao criar a 16ª, a mais antiga é deletada automaticamente. Playlists `manual` não são afetadas.

### Playlists Manuais

- Usuário cria playlist com nome livre
- Adiciona músicas via right-click em qualquer card → "Adicionar à playlist" / "Criar nova playlist"
- Pode remover faixas individuais na página de detalhe
- Pode renomear ou deletar qualquer playlist (auto ou manual)

---

## Interface

### Layout Global

```
┌──────────────────────────────────────────────────────────────────┐
│  TOPBAR: [≡][ClaudeFM]  [Home][Artists][Albums][Playlists][Downloads][Config] [⬇2]│
├───────────────────────┬──────────────────────────────────────────┤
│  SIDEBAR (colapsável) │  CONTEÚDO PRINCIPAL                      │
│                       │                                          │
│  [🔍 Buscar...  ][🔍] │  (varia conforme a página)               │
│  [ Last.fm | Local ]  │                                          │
│                       │                                          │
│  Buscar por:          │                                          │
│  ○ Artista            │                                          │
│  ○ Música             │                                          │
│  ○ Álbum              │                                          │
│                       │                                          │
│  [Resultados]         │                                          │
│                       │                                          │
├───────────────────────┴──────────────────────────────────────────┤
│  PLAYER BAR (fixa no rodapé)                                     │
│  [capa] Título · Artista      [⏮] [⏯] [⏭]    [────] 🔊         │
└──────────────────────────────────────────────────────────────────┘

Collapsed state:
┌──────────────────────────────────────────────────────────────────┐
│  TOPBAR: [≡][ClaudeFM]  [Home][Playlists][Downloads][Config] [⬇2]│
├──────────────────────────────────────────────────────────────────┤
│  CONTEÚDO PRINCIPAL (full width)                                 │
├──────────────────────────────────────────────────────────────────┤
│  PLAYER BAR                                                      │
└──────────────────────────────────────────────────────────────────┘
```

`[≡]` toggle button na topbar — colapsa/expande sidebar. Estado salvo em `settings.sidebar_collapsed`. `⬇ N` na topbar: N = downloads ativos. Clica → painel dropdown com fila de downloads, barras de progresso individuais, ✓ nos concluídos.

### Páginas

| Página | Conteúdo |
|---|---|
| **Home** | Grid de tracks da biblioteca local · Sort/filter controls |
| **Artists** | Grid de artistas da biblioteca local · Clicar → grid de tracks do artista |
| **Albums** | Grid de álbuns da biblioteca local · Clicar → grid de tracks do álbum |
| **Last.fm Artist** | Top 10 tracks · Discografia completa · Álbuns clicáveis (navegação via sidebar search) |
| **Last.fm Album** | Lista de faixas · Botão "Download all" (navegação via sidebar search) |
| **Playlists** | Duas seções: "Recent contexts" (auto) · "Your playlists" (manuais) · Botão "New playlist" |
| **Playlist detail** | Faixas da playlist · Remove track · Rename · Delete playlist |
| **Downloads** | Active queue com barras de progresso · Histórico com ✓ |
| **Settings** | API key Last.fm · Download folder · Additional folders · Audio format (m4a/mp3) · Cache on/off · Theme (dark/light) · Search results limit (default 5) |

**Home — Sort/filter options:**

| Tipo | Opções |
|---|---|
| Sort by | Most recent (default) · Oldest · Title A–Z · Title Z–A · Artist A–Z · Duration |
| Filter by format | All (default) · m4a · mp3 |

Artists e Albums pages seguem mesmo padrão de sort/filter.

### Busca

Busca **nunca dispara automaticamente** (sem debounce, sem auto-complete). Dispara apenas ao clicar no botão de lupa ou pressionar Enter.

Limite de resultados configurável nas Settings (`search_results_limit`). Padrão: **5**. Aplica tanto a Last.fm quanto a busca local.

Search input, toggle (Last.fm | Local) e radio buttons ficam **fixos** no topo da sidebar. Resultados renderizam num container com `overflow-y: auto` abaixo — controls sempre visíveis independente da quantidade de resultados.

### Language

All interface text is in **English** — labels, buttons, messages, placeholders, toasts.

### Images

Not downloaded. Two placeholder assets:
- `assets/placeholder.png` — tracks and albums
- `assets/artist_placeholder.png` — artists

### Search Results in Sidebar

Results appear inline in the sidebar (compact list, up to `search_results_limit` items). Clicking a result opens the full page in the main content area:

| Result type | Action on click | Inline button (hover) |
|---|---|---|
| Artist | Opens Artist page | — |
| Album | Opens Album page | `⬇` downloads all tracks in album |
| Track (Last.fm) | Opens track detail | `⬇` downloads track |
| Track (local) | Plays immediately, sets queue context | — |

**Inline download button states:**

| Condition | Button state |
|---|---|
| Not downloaded | `⬇` — enabled |
| `download_status = 'completed'` AND `file_status = 'available'` | `✓` — disabled, no re-download |
| `file_status = 'missing'` or `'corrupted'` | `⬇` — enabled; on completion sets `file_status = 'available'` and `download_status = 'completed'` |
| `download_status = 'downloading'` | Spinner — disabled |

**On click:** button switches to spinner immediately (optimistic UI); `⬇ N` counter in topbar increments. No toast.
| `download_status = 'failed'` | `⬇` retry — enabled |

### Right-click em cards de música

Menu de contexto com:
- Reproduzir
- Download (se não baixada)
- Adicionar à playlist → submenu com playlists existentes + "Nova playlist..."
- Remover da biblioteca (se baixada)

---

## Banco de Dados

```sql
tracks (
  id INTEGER PRIMARY KEY,
  title TEXT,
  artist TEXT,
  album TEXT,
  duration INTEGER,              -- segundos
  file_path TEXT,
  audio_format TEXT,             -- 'm4a' | 'mp3'
  youtube_url TEXT,              -- URL usada no download
  date_downloaded DATETIME,
  download_status TEXT,          -- 'pending' | 'downloading' | 'completed' | 'failed'
  download_error TEXT,           -- mensagem de erro se failed
  file_status TEXT DEFAULT 'available'
                                 -- 'available' | 'missing' | 'corrupted'
)

playlists (
  id INTEGER PRIMARY KEY,
  name TEXT,
  type TEXT,                     -- 'auto' | 'manual'
  created_at DATETIME,
  updated_at DATETIME
)

playlist_tracks (
  playlist_id INTEGER,
  track_id INTEGER,
  position INTEGER,
  PRIMARY KEY (playlist_id, track_id)
)

settings (
  key TEXT PRIMARY KEY,
  value TEXT
  -- keys: lastfm_api_key, download_folder, additional_folders (JSON),
  --       audio_format ('m4a'|'mp3'), cache_enabled ('true'|'false'),
  --       search_results_limit ('5' padrão),
  --       sidebar_collapsed ('false' padrão),
  --       player_last_track_id, player_last_position, player_last_context
)

cache (
  key TEXT PRIMARY KEY,
  response TEXT,
  cached_at DATETIME,
  expires_at DATETIME            -- 30 dias por padrão
)
```

### Modelos (Pydantic)

Todos os modelos usam `pydantic.BaseModel`. Tipos espelham exatamente o schema do DB — sem conversões implícitas entre camadas.

```python
# track.py
class Track(BaseModel):
    id: int | None = None
    title: str
    artist: str
    album: str | None = None
    duration: int | None = None          # segundos
    file_path: str | None = None
    audio_format: str | None = None      # 'm4a' | 'mp3'
    youtube_url: str | None = None
    date_downloaded: datetime | None = None
    download_status: str = 'pending'     # 'pending'|'downloading'|'completed'|'failed'
    download_error: str | None = None
    file_status: str = 'available'       # 'available'|'missing'|'corrupted'

# playlist.py
class Playlist(BaseModel):
    id: int | None = None
    name: str
    type: str                            # 'auto' | 'manual'
    created_at: datetime | None = None
    updated_at: datetime | None = None

class PlaylistTrack(BaseModel):
    playlist_id: int
    track_id: int
    position: int

# artist.py — Last.fm result, sem persistência
class Artist(BaseModel):
    name: str
    mbid: str | None = None
    listeners: int | None = None
    top_tracks: list[Track] = []

# album.py — Last.fm result, sem persistência
class Album(BaseModel):
    title: str
    artist: str
    mbid: str | None = None
    tracks: list[Track] = []
```

DB layer recebe e retorna modelos Pydantic. `api.py` serializa via `.model_dump()` antes de passar para o JS.

### file_manager.py — Scan no Startup

**Scan rápido (bloqueante, antes da UI carregar):** verifica apenas faixas já no DB — atualiza `file_status` para `missing` se não encontradas.

**Rescan completo (background thread):** varre todas as pastas configuradas, detecta arquivos novos e adiciona ao DB. Emite `library_scan_complete` ao terminar.

Ao encontrar arquivo novo não cadastrado: adiciona com metadados extraídos do arquivo (título, duração, formato); `download_status = 'completed'`.

---

## Tratamento de Erros

| Cenário | Comportamento |
|---|---|
| `yt-dlp` falha no download | `download_status = 'failed'`, `download_error` preenchido, evento `download_error` emitido, item marcado com ✗ no painel |
| Sem internet ao buscar (Last.fm) | Dialog de aviso antes de tentar a request; não dispara request |
| Sem internet ao clicar em download | Dialog de aviso; download não é enfileirado |
| Timeout da API Last.fm | Retorna erro para o JS; toast de aviso na UI; não quebra o app |
| `ffmpeg` falha na conversão | Mesmo fluxo do `yt-dlp` failure; log com traceback completo |
| Arquivo corrompido (miniaudio) | `file_status = 'corrupted'`; skip automático na fila; aviso na UI |
| DB locked/erro SQLite | Log de erro; retry com backoff (3x); se persistir, notifica usuário |
| Startup sem `ffmpeg`/`yt-dlp` | Erro fatal com dialog claro; app não inicializa |

Todos os erros logados com traceback completo via `logger.py`.

---

## Sanitização de Filenames

Aplicada em `youtube_service.py` antes de salvar qualquer arquivo:

- Remove caracteres inválidos no Windows: `< > : " / \ | ? *`
- Substitui por `_` (underscore)
- Limita path total a 200 caracteres (margem segura abaixo do limite de 260 do Windows)
- Evita nomes reservados: `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`
- Append de sufixo numérico em caso de colisão de nome

---

## Logging

`utils/logger.py` — logger global disponível em todos os módulos.

- Níveis: `INFO`, `WARN`, `ERROR`
- Arquivo por sessão: `logs/YYYY-MM-DD_HH-MM-SS.log`
- `ERROR` inclui traceback completo
- stdout e stderr de subprocessos (`yt-dlp`, `ffmpeg`) redirecionados e logados em `DEBUG`
- Rotação automática: mantém últimas 10 sessões

---

## Build e Distribuição

### Estrutura

```
claudefm/
├── build/            # PyInstaller output (gitignored)
├── dist/             # Executável final (gitignored)
├── assets/vendor/    # ffmpeg.exe + yt-dlp.exe (committed)
└── claudefm.spec     # PyInstaller spec
```

### PyInstaller

- Modo `--onedir` — inicialização mais rápida que `--onefile`
- `ffmpeg.exe` e `yt-dlp.exe` incluídos via `--add-binary`
- Em runtime, app localiza binários via `sys._MEIPASS` (bundle path)

### Startup Check (app.py)

Na inicialização, em ordem:

1. `ffmpeg` acessível → ok | erro fatal com dialog claro
2. `yt-dlp` acessível → ok | erro fatal com dialog claro
3. Banco de dados inicializado
4. Scan rápido de biblioteca (file_manager — bloqueante)
5. API key configurada? → não: abre Settings automaticamente
6. Pasta de download configurada? → não: abre Settings automaticamente
7. Rescan completo em background thread

---

## Sistema de Temas

Dois temas inclusos: **dark** (padrão) e **light**. Tema salvo nas settings do usuário.

### Arquivos

```
src/interface/assets/themes/
├── dark.json          # Tema escuro (Spotify-inspired)
├── light.json         # Tema claro
├── base.css           # Tokens compartilhados (tipografia, espaçamento, raios) — não muda por tema
src/interface/scripts/
└── theme-loader.js    # Lê JSON do tema, aplica como CSS custom properties no :root
```

### Criar novo tema

Copiar `dark.json` ou `light.json`, alterar os valores de cor, salvar com nome novo (ex: `sepia.json`). O `ThemeLoader.load('sepia')` aplica automaticamente.

### Estrutura do JSON de tema

Cada arquivo define:
- `name` / `displayName`
- `colors` — todos os tokens de cor (`bg_base`, `accent`, `text_primary`, `shadow_heavy`, etc.)
- `typography` — `font_family` e `font_family_title` (stack de fallback — sem fontes proprietárias)

`theme-loader.js` mapeia cada token para uma CSS custom property (`--color-bg-base`, `--color-accent`, etc.) e seta no `:root`. Todo o CSS da interface usa apenas as variáveis CSS — nunca valores hardcoded.

### Font

`SpotifyMixUI` é proprietária da Spotify. ClaudeFM usa stack de fallback:
`'Helvetica Neue', helvetica, arial, 'Hiragino Sans', 'Meiryo', sans-serif`

### Album art e cromaticidade

Imagens não são baixadas — `placeholder.png` universal. A UI é intencionalmente acromática, com identidade visual sustentada pelos tokens de cor do tema ativo (accent, superfícies, tipografia). O DESIGN.md foi adaptado ao projeto; não o contrário.

---

## Requisitos Gerais

- **Offline-first:** reprodução não depende de internet; downloads requerem conexão
- **Cache Last.fm:** 30 dias; desativável por flag nas Settings (facilita debug)
- **Busca YouTube:** query `"Artista - Música"`, primeiro resultado, sem seleção manual no MVP
- **Plataforma:** Windows. Design não introduz dependências Windows-only; portabilidade futura possível
- **Imagens:** não baixadas em nenhum contexto; placeholder universal
- **Temas:** dark (padrão) e light; configurável nas Settings; fácil adicionar novos via JSON
