# ClaudeFM — Especificação do Projeto

## Visão Geral

**ClaudeFM** é um music player desktop focado em reprodução offline. O fluxo central é:

1. Buscar metadados (músicas, artistas, álbuns) via **Last.fm API** (`pylast`)
2. Baixar áudio localmente via **YouTube** (`yt-dlp`, apenas áudio — sem vídeo)
3. Reproduzir os arquivos baixados localmente

A interface é construída em **HTML/CSS/JS** e renderizada pela lib **webview** do Python — é uma aplicação desktop, não um site.

---

## Estrutura de Arquivos

```
claudefm/
├── app.py                      # Ponto de entrada da aplicação
│
├── services/
│   ├── lastfm_service.py       # Buscas de metadados via pylast
│   ├── youtube_service.py      # Downloads de áudio via yt-dlp
│   └── player_service.py       # Reprodução local (lib leve de áudio)
│
├── models/                     # Objetos de dados para organizar chamadas entre módulos
│
├── utils/
│   └── logger.py               # Logger global; salva logs em /logs
│
├── database/
│   ├── database.py             # SQLite com metadados das músicas baixadas
│   └── file_manager.py        # Sincronização entre arquivos locais e banco de dados
│
├── interface/
│   ├── pages/
│   │   ├── home.html           # Biblioteca local do usuário
│   │   ├── search.html         # Página de pesquisa
│   │   └── downloads.html      # Fila e histórico de downloads
│   ├── components/             # Componentes reutilizáveis (player bar, cards, modais)
│   ├── styles/
│   │   ├── main.css
│   │   └── theme.css           # Variáveis de design (inspirado no Spotify — ver design.md)
│   └── scripts/
│       ├── api.js              # Comunicação JS <-> backend Python
│       └── player.js           # Controles do player
│
├── assets/
│   └── placeholder.png         # Template de capa para artistas/álbuns (sem download de imagens)
│
└── logs/
```

---

## Funcionalidades por Módulo

### `services/lastfm_service.py`
- Busca por artista, música ou álbum (tipo definido pelo usuário via checkbox — sem detecção automática)
- Retorna: top tracks do artista, discografia completa, faixas do álbum, metadados gerais
- Integrado ao sistema de cache (ver seção Banco de Dados)

### `services/youtube_service.py`
- Recebe metadados da Last.fm (nome da música + artista) e realiza busca no YouTube
- Baixa apenas o áudio do primeiro resultado encontrado via `yt-dlp`
- Suporta download de músicas individuais e de álbuns completos

### `services/player_service.py`
- Reproduz arquivos de áudio locais
- Utilizar uma lib leve de áudio (sugestão: `pygame.mixer` ou `miniaudio`)

### `utils/logger.py`
- Objeto logger global disponível em todos os módulos
- Salva logs na pasta `/logs` com rotação por data/sessão

---

## Banco de Dados (`database/`)

### `database.py` — SQLite

**Tabela: músicas baixadas**
- Metadados: título, artista, álbum, duração, caminho do arquivo, data de download
- Coluna `missing`: `true` se o arquivo foi baixado mas não é mais encontrado na pasta

**Tabela: configurações**
- Chaves de API (Last.fm, etc.)
- Pasta principal de download
- Pastas adicionais no escopo de busca do app
- Preferências gerais do usuário

**Cache**
- Respostas da Last.fm API ficam em cache por **30 dias**
- Deve ser fácil desativar o cache (flag de configuração) para facilitar desenvolvimento e debug

### `database/file_manager.py`
- Ao iniciar o app, varre todas as pastas configuradas
- Se um arquivo de música não consta no banco: **adiciona com metadados básicos** extraídos do próprio arquivo (nome, duração, formato — sem chamada de API)
- Se um arquivo consta no banco mas não é encontrado: marca `missing = true`

---

## Interface

### Layout Global (todas as páginas)

```
┌──────────────────────────────────────────────────────────┐
│  TOPBAR: [ClaudeFM]         [Home]  [Downloads]  [Config]│
├─────────────────────┬────────────────────────────────────┤
│  SIDEBAR (fixa)     │  CONTEÚDO PRINCIPAL                │
│                     │                                    │
│  [🔍 Buscar...  ]   │  (varia conforme a página)         │
│                     │                                    │
│  Buscar por:        │                                    │
│  ○ Artista          │                                    │
│  ○ Música           │                                    │
│  ○ Álbum            │                                    │
│                     │                                    │
│  [Resultados da     │                                    │
│   pesquisa]         │                                    │
│                     │                                    │
├─────────────────────┴────────────────────────────────────┤
│  PLAYER BAR (fixa no rodapé)                             │
│  [capa] Título · Artista    [⏮] [⏯] [⏭]   [────] 🔊   │
└──────────────────────────────────────────────────────────┘
```

### Páginas

| Página | Conteúdo |
|---|---|
| **Home** | Grid de músicas e álbuns baixados pelo usuário |
| **Artista** | Top 10 tracks · Discografia completa · Álbuns clicáveis |
| **Álbum** | Lista de faixas · Botão "Baixar álbum completo" |
| **Search** | Resultados expandidos no centro ao clicar em um item da sidebar |
| **Downloads** | Fila de downloads em andamento + histórico |
| **Configurações** | Chaves de API · Pasta de download · Pastas adicionais · Opção de cache |

### Navegação entre páginas
- Clicar em um **artista** nos resultados abre a página do artista (centro)
- Clicar em um **álbum** abre a página do álbum (centro)
- Download de música individual: botão na faixa
- Download de álbum: botão na página do álbum

---

## Requisitos Gerais

- **Imagens**: não são baixadas. Usar `assets/placeholder.png` como fallback universal
- **Design**: inspirado no Spotify — detalhes em `design.md`
- **Banco de dados**: é a fonte da verdade para tudo que foi baixado; sincronizado com o sistema de arquivos ao iniciar
- **APIs**: chamadas minimizadas pelo sistema de cache (30 dias); desativável por flag