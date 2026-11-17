# Cliente Multimedia (NUC)

Cliente multimedia tipo "Steam Big Picture" optimizado para TV, con navegacion
por raton o pantalla tactil. Funciona con YouTube como si fuera un canal de
television.

## Arranque

1. Ejecutar `launch.bat`.
2. El script instala/sincroniza **UV** si no esta presente.
3. Ejecuta `uv sync` para instalar las dependencias declaradas en `pyproject.toml`.
4. Inicia el programa Python (`src/main.py`).

## Requisito del sistema: VLC

El reproductor usa **VLC** (binding `python-vlc`), que debe estar instalado en
el NUC. VLC NO se instala por pip. Opciones:

- **A (recomendada):** el `launch.bat` detecta si VLC esta instalado y, si no,
  lo instala silenciosamente o muestra instrucciones.
- **B:** empaquetar VLC portable junto a la app (~150 MB, independiente del SO).

La ruta de VLC se autodetecta (Program Files, variable de entorno) o se
configura en `config/settings.toml` bajo `[vlc] install_path`.

## Decisiones de arquitectura

| Decision | Elegida | Motivo |
|----------|---------|--------|
| Reproductor | VLC (incrustado en Qt) | Soporta todos los streams de yt-dlp, control total |
| Metadatos YouTube | yt-dlp (sin API key) | Sin dependencia de API key; mas simple |
| Pantalla completa | Opcional (F11 / boton), OFF por defecto | Barra de tareas visible por defecto |
| Inicio con Windows | Disponible, OFF por defecto | Carpeta Startup (facil de gestionar) |
| Anuncios YouTube | Bloqueados automaticamente | Stream directo de yt-dlp no incluye ads de plataforma |
| Patrocinios en video | SponsorBlock (API publica) | Salta segmentos "sponsor"/"selfpromo"/etc. via seek |
| Login YouTube | Cookies (navegador o archivo) | yt-dlp `--cookies-from-browser` / `--cookies file` |

## Login de YouTube (via cookies)

Sin API oficial. Para usar tu cuenta (suscripciones, videos restringidos):

1. Abrir Configuracion -> YouTube -> activar "Login".
2. Elegir metodo:
   - **browser:** lee cookies de Chrome/Edge/Firefox del NUC (debes tener la
     sesion iniciada en ese navegador).
   - **file:** exportar cookies con una extension del navegador a `cookies.txt`
     e indicar la ruta (caduca en ~2-4 semanas).

Las cookies se leen al momento; la app no guarda copias.

## Estado de implementacion

Implementado y probado (smoke test en `smoke_test.py`):
- Arranque completo: UV sync + ventana PyQt6 + 4 pantallas
- Home con visor grande tipo Steam Big Picture: una miniatura por seccion
  (~60% del ancho, centrada, alta resolucion). Secciones: Tendencias,
  Suscripciones, Historial, Favoritos
- Navegacion: flechas arriba/abajo cambian de seccion, izquierda/derecha
  cambian de video, Enter reproduce. Tambien flechas en pantalla y rueda del
  raton. La seccion activa se resalta con borde rojo
- Tamano de la miniatura configurable: ui.big_thumb_scale en settings.toml
- Busqueda de YouTube con teclado virtual opcional
- Modo feed estilo TikTok: al abrir la app se reproduce automaticamente el
  primer video de tendencias (feed.autostart) y se pre-cargan los streams de
  los videos vecinos (feed.preload_radius) hacia adelante y atras, asi al
  pulsar flecha abajo/arriba (o la rueda del raton) el siguiente video
  arranca casi al instante. Flechas izquierda/derecha saltan +/- 10 s
- Reproductor VLC incrustado con controles grandes (play, seek, volumen)
- SponsorBlock: omision automatica de segmentos patrocinados
- Audio mono opcional: mezcla L/R en un solo canal (playback.mono_audio),
  util si el NUC va a un altavoz unico y el stereo suena irregular
- Historial y favoritos persistentes en JSON
- Login de YouTube via cookies del navegador (suscripciones + videos restringidos)
- F11 / boton para pantalla completa; cursor se oculta tras inactividad
- Inicio automatico con Windows (toggle en Ajustes, OFF por defecto)
- Deteccion silenciosa de VLC en launch.bat (winget o descarga directa)

Nota sobre tendencias: el feed oficial de YouTube exige login en muchas
regiones; la app lo intenta y, si falla, muestra contenido popular via busqueda.

Nota sobre el error "Sign in to confirm you're not a bot": YouTube lo exige
segun IP/configuracion/video. La app lo resuelve en cascada:
1. Intenta con cookies del navegador (si el login esta activo).
2. Reintenta sin cookies con el cliente normal.
3. Reintenta con el cliente 'android' de yt-dlp, que evita el chequeo.
Un ~5-10% de los videos puede seguir pidiendo verificacion; en ese caso la
app muestra instrucciones para activar el login con cookies.
El login tambien es necesario para suscripciones y videos restringidos.

## Estructura

```
cliente-multimedia/
├── launch.bat              # UV + VLC silencioso + sync + run
├── smoke_test.py           # Prueba de humo (arranque offscreen)
├── pyproject.toml
├── config/
│   └── settings.toml
├── src/
│   ├── main.py             # Entry point
│   ├── domain/
│   │   └── models.py       # Video, format_duration
│   ├── infra/
│   │   ├── settings.py     # load/save TOML con defaults
│   │   ├── storage.py      # historial y favoritos JSON
│   │   ├── vlc_setup.py    # localizacion de libvlc.dll
│   │   ├── youtube_service.py  # yt-dlp: tendencias, busqueda, streams
│   │   ├── sponsorblock.py # API SponsorBlock
│   │   └── autostart.py    # acceso directo en Startup
│   ├── app/
│   │   ├── workers.py      # QThreadPool + Worker
│   │   └── controllers.py  # NavigationController, PlaybackController
│   └── ui/
│       ├── main_window.py  # stack de pantallas, top bar, F11, cursor
│       ├── home_screen.py  # launcher + shelves
│       ├── search_screen.py
│       ├── player_screen.py # VLC incrustado
│       ├── settings_screen.py
│       ├── widgets.py      # VideoCard, ShelfWidget, VirtualKeyboard
│       └── styles.qss      # tema 10-foot oscuro
└── assets/
```
