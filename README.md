# SuperRecopilatorios

Escribe el nombre de un artista y la app descarga sus **20 grandes éxitos en MP3**. Solo ves la lista de canciones y el % de progreso de cada una.

## Uso

1. Abre **SuperRecopilatorios** (el acceso directo de esta carpeta).
2. Escribe el artista y pulsa **Descargar éxitos** (o Intro).
3. Al terminar, pulsa **Abrir carpeta**.

Las canciones se guardan en `Música\SuperRecopilatorios\<Artista> - Grandes éxitos\`, con nombres tipo `01 - Queen - Bohemian Rhapsody.mp3`. Puedes cambiar la carpeta con **Cambiar…** y la app la recuerda.

## Cómo funciona

- **Qué canciones elige:** pide a YouTube Music la lista «Canciones» del artista, que viene ordenada por popularidad. Descarta directos, remixes, karaokes y versiones repetidas, y se queda con las 20 primeras.
- **Cómo las descarga:** con `yt-dlp`, la mejor pista de audio disponible, convertida a MP3 a 320 kbps con FFmpeg. Descarga 3 canciones a la vez.
- **Etiquetas:** cada MP3 lleva título, artista, álbum, número de pista y la carátula (recortada a cuadrado).
- Si vuelves a pedir el mismo artista, las canciones que ya tienes no se descargan otra vez.

## Instalar en otro PC

Copia la carpeta (sin `.venv`) y haz doble clic en **`instalar.bat`**. Instala lo que falte, sin preguntar nada:

1. **Python 3.13**, si no hay un Python 3.10 o posterior.
2. **FFmpeg**, que convierte a MP3 y pone la carátula.
3. **Deno**, el motor de JavaScript que YouTube exige para descargar. Si ya hay Node.js, no instala nada.
4. Las librerías de Python `yt-dlp` y `ytmusicapi`, en un entorno propio dentro de la carpeta.
5. Los accesos directos, en la carpeta y en el Escritorio.

Al terminar abre la app. Solo necesita Windows 10/11 con winget, que viene de serie, e Internet.

## Si un día deja de descargar

YouTube cambia a menudo y `yt-dlp` se actualiza para seguirle el ritmo. Vuelve a ejecutar `instalar.bat`, que actualiza las dependencias.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `app.pyw` | Ventana de la app |
| `recopilador.py` | Búsqueda de éxitos y descarga a MP3 |
| `instalar.bat` | Instalación y actualización |
| `icono.ico` | Icono |

Úsala para tu uso personal y respeta los derechos de autor y las condiciones de YouTube.
