# SuperRecopilatorios

Escribe el nombre de un artista o pega una playlist de Spotify y la app descarga las canciones en **MP3 con su portada oficial**. Solo ves la lista de canciones y el % de progreso de cada una.

## Uso

1. Abre **SuperRecopilatorios** (el acceso directo del Escritorio o de esta carpeta).
2. Escribe un artista y pulsa **Intro**: descarga sus **20 grandes éxitos**.
3. Puedes seguir escribiendo artistas mientras descarga: se ponen **en cola** y se descargan uno detrás de otro.
4. También puedes pegar un enlace de **Spotify** (playlist, álbum o canción).
5. Al terminar, pulsa **Abrir carpeta**.

Debajo de la caja aparece una etiqueta por cada artista o playlist: gris si espera (✕ para quitarla), morada con su % si se está descargando, verde al terminar y roja si falla. Pulsa una etiqueta para ver sus canciones.

Las canciones se guardan en `Música\SuperRecopilatorios\<Artista> - Grandes éxitos\` (o en una carpeta con el nombre de la playlist), con nombres tipo `01 - Queen - Bohemian Rhapsody.mp3`. Puedes cambiar la carpeta con **Cambiar…** y la app la recuerda.

## Portadas

- Cada canción nueva lleva la **portada oficial del disco** (1000 × 1000 px), buscada en Deezer y, si no aparece, en iTunes. Solo se pone si el artista y el título coinciden; si no hay coincidencia segura, se queda la carátula de YouTube.
- El botón **Revisar portadas** repasa todo lo que ya tienes descargado y pone la portada oficial a las canciones que aún no la tienen. Las que ya la tienen se saltan, así que puedes pulsarlo cuando quieras.

## Cómo funciona

- **Qué canciones elige:** pide a YouTube Music la lista «Canciones» del artista, que viene ordenada por popularidad. Descarta directos, remixes, karaokes y versiones repetidas, y se queda con las 20 primeras.
- **Spotify:** lee la lista desde el reproductor público de Spotify (solo las 100 primeras canciones de cada playlist, y tiene que ser pública) y busca cada canción en YouTube Music, usando la duración para acertar con la versión.
- **De dónde y a qué calidad:** el audio sale de YouTube Music con `yt-dlp`, a la mejor calidad disponible sin Premium (Opus a ~130 kbps), y se convierte a MP3 a 320 kbps con FFmpeg. Descarga 3 canciones a la vez.
- **Etiquetas:** cada MP3 lleva título, artista, álbum, número de pista y portada.
- Si vuelves a pedir el mismo artista, las canciones que ya tienes no se descargan otra vez.

## Instalar en otro PC

Copia la carpeta (sin `.venv`) y haz doble clic en **`instalar.bat`**. Instala lo que falte, sin preguntar nada:

1. **Python 3.13**, si no hay un Python 3.10 o posterior.
2. **FFmpeg**, que convierte a MP3 y pone la carátula.
3. **Deno**, el motor de JavaScript que YouTube exige para descargar. Si ya hay Node.js, no instala nada.
4. Las librerías de Python `yt-dlp` y `ytmusicapi`, en un entorno propio dentro de la carpeta.
5. Los accesos directos, en la carpeta y en el Escritorio.

Al terminar abre la app. Solo necesita Windows 10/11 con winget, que viene de serie, e Internet.

## Actualizaciones

Al abrirse, la app comprueba si hay una versión nueva en [GitHub](https://github.com/heyteamsoftware/HeySuperRecopilatorios). Si la hay, aparece arriba a la derecha el botón **⬆ Actualizar app**: descarga los archivos nuevos, actualiza las librerías y se reinicia sola. Si hay descargas en marcha, espera a que termine la cola.

## Si un día deja de descargar

YouTube cambia a menudo y `yt-dlp` se actualiza para seguirle el ritmo. Vuelve a ejecutar `instalar.bat`, que actualiza las dependencias.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `app.pyw` | Ventana de la app |
| `recopilador.py` | Búsqueda de éxitos, playlists de Spotify y descarga a MP3 |
| `portadas.py` | Búsqueda de portadas oficiales y su incrustación en los MP3 |
| `actualizar.py` | Comprobación y descarga de versiones nuevas desde GitHub |
| `instalar.bat` | Instalación y actualización |
| `icono.ico` | Icono |

Úsala para tu uso personal y respeta los derechos de autor y las condiciones de YouTube.
