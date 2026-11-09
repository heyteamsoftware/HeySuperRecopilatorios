"""Núcleo de SuperRecopilatorios: busca éxitos de artistas o playlists de Spotify y los descarga en MP3."""

from __future__ import annotations

import os
import re
import shutil
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from ytmusicapi import YTMusic
import yt_dlp

import portadas

NUM_EXITOS = 20
DESCARGAS_SIMULTANEAS = 3
DURACION_MAX_SEG = 10 * 60  # descarta mezclas, directos larguísimos, etc.

# Versiones que normalmente no queremos en un recopilatorio de éxitos.
_PALABRAS_DESCARTE = re.compile(
    r"\b(live|en vivo|directo|remix|remezcla|karaoke|instrumental|acoustic|ac[uú]stic[oa]|"
    r"sped up|slowed|anniversary|demo|mix|medley|versi[oó]n japonesa|japanese)\b",
    re.IGNORECASE,
)


@dataclass
class Cancion:
    indice: int
    video_id: str
    titulo: str
    artista: str
    album: str = ""
    duracion: int = 0
    artista_album: str = ""  # artista del disco (para álbumes completos)
    anio: str = ""
    total: int = 0  # número de pistas, para etiquetar «3/10»
    progreso: float = 0.0  # 0..100
    estado: str = "En cola"  # En cola | Preparando | Descargando | Convirtiendo | Portada | Listo | Error
    archivo: str = ""
    error: str = ""

    @property
    def url(self) -> str:
        return f"https://music.youtube.com/watch?v={self.video_id}"


def _normalizar(texto: str) -> str:
    """Clave para detectar duplicados: sin acentos, sin paréntesis ni 'feat.'."""
    texto = re.sub(r"[\(\[].*?[\)\]]", "", texto)
    texto = re.split(r"\s[-–—]\s|\bfeat\.?|\bft\.?|\bcon\b", texto, flags=re.IGNORECASE)[0]
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def _nombre_archivo(texto: str) -> str:
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto).strip().rstrip(".")
    return re.sub(r"\s+", " ", texto)[:150] or "cancion"


def _es_descartable(titulo: str, album: str) -> bool:
    return bool(_PALABRAS_DESCARTE.search(titulo)) or bool(_PALABRAS_DESCARTE.search(album or ""))


def buscar_exitos(artista: str, cantidad: int = NUM_EXITOS) -> tuple[str, list[Cancion]]:
    """Devuelve (nombre oficial del artista, lista de sus canciones más populares)."""
    yt = YTMusic(language="es")
    artistas = yt.search(artista, filter="artists", limit=5)
    if not artistas:
        raise LookupError(f"No he encontrado ningún artista llamado «{artista}».")

    ficha = artistas[0]
    nombre = ficha.get("artist") or artista
    info = yt.get_artist(ficha["browseId"])

    pistas: list[dict] = []
    seccion = info.get("songs") or {}
    if seccion.get("browseId"):
        # Lista "Canciones" del artista: viene ordenada por popularidad.
        pistas = yt.get_playlist(seccion["browseId"], limit=150).get("tracks", [])
    if not pistas:
        pistas = seccion.get("results", [])
    if len(pistas) < cantidad:
        # ytmusicapi no sabe filtrar canciones con la interfaz en español
        pistas += YTMusic(language="en").search(nombre, filter="songs", limit=50)

    canciones: list[Cancion] = []
    vistos: set[str] = set()
    for p in pistas:
        vid = p.get("videoId")
        titulo = (p.get("title") or "").strip()
        if not vid or not titulo or p.get("isAvailable") is False:
            continue
        album = (p.get("album") or {}).get("name", "") if isinstance(p.get("album"), dict) else ""
        duracion = p.get("duration_seconds") or 0
        if duracion and duracion > DURACION_MAX_SEG:
            continue
        if _es_descartable(titulo, album):
            continue
        clave = _normalizar(titulo)
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        artistas_pista = ", ".join(a["name"] for a in p.get("artists") or [] if a.get("name")) or nombre
        canciones.append(
            Cancion(
                indice=len(canciones) + 1,
                video_id=vid,
                titulo=titulo,
                artista=artistas_pista,
                album=album,
                duracion=duracion,
            )
        )
        if len(canciones) >= cantidad:
            break

    if not canciones:
        raise LookupError(f"No he encontrado canciones de «{nombre}».")
    for c in canciones:
        c.total = len(canciones)
    return nombre, canciones


class _LoggerSilencioso:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def _completar_path() -> None:
    """Añade al PATH lo recién instalado (registro de Windows y carpetas de winget).

    Así la app encuentra FFmpeg y Deno aunque se instalaran después de iniciar sesión.
    """
    rutas: list[str] = []
    try:
        import winreg

        for raiz, clave in (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(raiz, clave) as k:
                    valor = winreg.QueryValueEx(k, "Path")[0]
                rutas += [os.path.expandvars(p) for p in valor.split(";") if p]
            except OSError:
                pass
    except ImportError:
        pass

    winget = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet")
    rutas.append(os.path.join(winget, "Links"))
    paquetes = os.path.join(winget, "Packages")
    if os.path.isdir(paquetes):
        for raiz_dir, _dirs, archivos in os.walk(paquetes):
            if raiz_dir.count(os.sep) - paquetes.count(os.sep) > 3:
                _dirs.clear()
            elif "ffmpeg.exe" in archivos or "deno.exe" in archivos:
                rutas.append(raiz_dir)

    actuales = os.environ.get("PATH", "").split(os.pathsep)
    nuevas = [p for p in dict.fromkeys(rutas) if p and p not in actuales and os.path.isdir(p)]
    if nuevas:
        os.environ["PATH"] = os.pathsep.join(actuales + nuevas)


_completar_path()


def ffmpeg_disponible() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _descargar_una(cancion: Cancion, carpeta: str, avisar: Callable[[Cancion], None], digitos: int = 2) -> None:
    if cancion.estado == "Error":  # p. ej. no se encontró en YouTube Music
        avisar(cancion)
        return
    base = _nombre_archivo(f"{cancion.indice:0{digitos}d} - {cancion.artista} - {cancion.titulo}")
    destino_mp3 = os.path.join(carpeta, base + ".mp3")

    if os.path.exists(destino_mp3):
        cancion.progreso, cancion.estado, cancion.archivo = 100.0, "Listo", destino_mp3
        avisar(cancion)
        return

    cancion.estado = "Preparando"
    avisar(cancion)

    def gancho_descarga(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                # La descarga ocupa el 0-90 %; la conversión a MP3 el resto.
                cancion.progreso = min(90.0, d.get("downloaded_bytes", 0) / total * 90)
            cancion.estado = "Descargando"
            avisar(cancion)
        elif d["status"] == "finished":
            cancion.progreso, cancion.estado = 90.0, "Convirtiendo"
            avisar(cancion)

    def gancho_postproceso(d):
        if d["status"] == "started" and d.get("postprocessor") == "ExtractAudio":
            cancion.progreso, cancion.estado = 92.0, "Convirtiendo"
            avisar(cancion)
        elif d["status"] == "finished" and d.get("postprocessor") == "EmbedThumbnail":
            cancion.progreso = 99.0
            avisar(cancion)

    opciones = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(carpeta, base + ".%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _LoggerSilencioso(),
        "writethumbnail": True,
        "retries": 5,
        "fragment_retries": 5,
        "progress_hooks": [gancho_descarga],
        "postprocessor_hooks": [gancho_postproceso],
        # YouTube exige resolver un reto JavaScript; vale Deno o Node.
        "js_runtimes": {"deno": {}, "node": {}},
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"},
        ],
        # Carátula cuadrada (recorta el marco 16:9 de la miniatura de YouTube).
        "postprocessor_args": {"thumbnailsconvertor": ["-vf", "crop='min(iw,ih)':'min(iw,ih)'"]},
    }

    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(cancion.url, download=False)
            # Etiquetas ID3 limpias con los datos de YouTube Music.
            artistas = [a.strip() for a in cancion.artista.split(",") if a.strip()]
            info["title"] = info["track"] = cancion.titulo
            info["artists"] = artistas
            info["artist"] = cancion.artista
            artista_album = cancion.artista_album or (artistas[0] if artistas else cancion.artista)
            info["album_artists"] = [artista_album]
            info["album_artist"] = artista_album
            if cancion.album:
                info["album"] = cancion.album
            info["track_number"] = cancion.indice
            info["description"] = info["synopsis"] = None
            # La fecha de subida a YouTube no es la del disco: mejor no etiquetar.
            for campo in ("upload_date", "release_date", "release_year", "timestamp", "release_timestamp"):
                info[campo] = None
            ydl.process_ie_result(info, download=True)
        cancion.archivo = destino_mp3
        # Cambia la miniatura de YouTube por la portada oficial del disco (si la encuentra).
        cancion.estado = "Portada"
        avisar(cancion)
        _etiquetar(destino_mp3, cancion)
        portadas.poner_portada(destino_mp3, cancion.artista_album or cancion.artista, cancion.titulo,
                               cancion.album, forzar=True)
        cancion.progreso, cancion.estado = 100.0, "Listo"
    except Exception as exc:  # noqa: BLE001 - queremos seguir con el resto
        cancion.estado = "Error"
        cancion.error = re.sub(r"^ERROR:\s*", "", str(exc)).splitlines()[0][:200]
    avisar(cancion)


def _etiquetar(mp3: str, cancion: Cancion) -> None:
    """Número de pista «n/total» y año del disco (si se conoce)."""
    from mutagen.id3 import TDRC, TRCK

    try:
        tags = portadas._leer(mp3)
        tags.delall("TRCK")
        tags.add(TRCK(encoding=3, text=[f"{cancion.indice}/{cancion.total}" if cancion.total else str(cancion.indice)]))
        if cancion.anio:
            tags.delall("TDRC")
            tags.add(TDRC(encoding=3, text=[cancion.anio]))
        tags.save(mp3)
    except Exception:  # noqa: BLE001
        pass


def descargar_todas(
    canciones: list[Cancion],
    carpeta: str,
    avisar: Callable[[Cancion], None],
    simultaneas: int = DESCARGAS_SIMULTANEAS,
) -> None:
    """Descarga todas las canciones (varias a la vez) y bloquea hasta terminar."""
    os.makedirs(carpeta, exist_ok=True)
    digitos = max(2, len(str(len(canciones))))
    with ThreadPoolExecutor(max_workers=simultaneas) as pool:
        for c in canciones:
            pool.submit(_descargar_una, c, carpeta, avisar, digitos)


# ---------------------------------------------------------------- Spotify

_RE_SPOTIFY = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z-]+/)?(?:embed/)?|spotify:)(playlist|album|track)[/:]([A-Za-z0-9]{10,})"
)
_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)


def es_spotify(texto: str) -> bool:
    return bool(_RE_SPOTIFY.search(texto or ""))


def id_spotify(texto: str) -> tuple[str, str]:
    """(tipo, identificador) de un enlace de Spotify, o ("", "")."""
    m = _RE_SPOTIFY.search(texto or "")
    return (m.group(1), m.group(2)) if m else ("", "")


def tipo_spotify(texto: str) -> str:
    """«playlist», «album» o «track» (o "" si no es un enlace de Spotify)."""
    m = _RE_SPOTIFY.search(texto or "")
    return m.group(1) if m else ""


def _leer_spotify(texto: str) -> tuple[str, str, str, list[dict]]:
    """Lee una playlist, álbum o canción de Spotify desde su reproductor público.

    Devuelve (tipo, nombre, artista, [{titulo, artista, duracion}]). Spotify solo muestra ahí
    las 100 primeras canciones de cada lista.
    """
    import json
    import urllib.request

    m = _RE_SPOTIFY.search(texto)
    if not m:
        raise LookupError("Eso no parece un enlace de Spotify.")
    tipo, ident = m.groups()
    peticion = urllib.request.Request(
        f"https://open.spotify.com/embed/{tipo}/{ident}",
        headers={"User-Agent": _NAVEGADOR, "Accept-Language": "es-ES,es;q=0.9"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "code", None) in (400, 404):
            raise LookupError("No encuentro esa lista en Spotify. ¿Es pública?") from exc
        raise
    datos = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not datos:
        raise LookupError("Spotify no ha devuelto la lista. ¿Es pública?")
    entidad = json.loads(datos.group(1))["props"]["pageProps"]["state"]["data"]["entity"]

    nombre = entidad.get("name") or entidad.get("title") or "Spotify"
    artista = (entidad.get("subtitle") or "").replace(" ", " ") if tipo == "album" else ""
    pistas = []
    if tipo == "track":
        artistas = ", ".join(a.get("name", "") for a in entidad.get("artists") or []) or entidad.get("subtitle", "")
        pistas.append({"titulo": _limpiar_titulo(nombre), "artista": artistas, "duracion": (entidad.get("duration") or 0) // 1000})
        nombre = f"{artistas} - {nombre}"
    else:
        for t in entidad.get("trackList") or []:
            if t.get("title"):
                pistas.append({
                    "titulo": _limpiar_titulo(t["title"]),
                    "artista": (t.get("subtitle") or "").replace(" ", " "),
                    "duracion": (t.get("duration") or 0) // 1000,
                })
    if not pistas:
        raise LookupError("La lista de Spotify está vacía o no es pública.")
    return tipo, nombre, artista, pistas


_COLETILLA = re.compile(
    r"\s+-\s+[^-]*\b(remaster(ed)?|version|versi[oó]n|from|edit|mono|stereo|single|radio)\b.*$", re.IGNORECASE
)


def _limpiar_titulo(titulo: str) -> str:
    """«Bohemian Rhapsody - Remastered 2011» -> «Bohemian Rhapsody»."""
    return _COLETILLA.sub("", titulo).strip() or titulo


def _emparejar(pista: dict, album: str = "") -> dict | None:
    """Busca en YouTube Music la canción de Spotify (con la duración y el disco para acertar)."""
    yt = YTMusic(language="en")  # con "es" la búsqueda de canciones no devuelve nada
    consulta = f"{pista['artista'].split(',')[0]} {pista['titulo']}"
    try:
        resultados = [r for r in yt.search(consulta, filter="songs", limit=5) if r.get("videoId")]
    except Exception:  # noqa: BLE001
        resultados = []
    if not resultados:
        return None
    if pista["duracion"]:
        cercanos = [r for r in resultados if abs((r.get("duration_seconds") or 0) - pista["duracion"]) <= 15]
        if cercanos:
            resultados = cercanos
    if album:  # en un álbum, mejor la versión de ese disco que la de un recopilatorio
        clave = _normalizar(album)
        del_disco = [r for r in resultados
                     if isinstance(r.get("album"), dict) and _normalizar(r["album"].get("name", "")) == clave]
        if del_disco:
            return del_disco[0]
    return resultados[0]


def buscar_spotify(texto: str, avisar: Callable[[int, int], None] | None = None) -> tuple[str, list[Cancion]]:
    """Convierte una playlist de Spotify en canciones de YouTube Music listas para bajar."""
    tipo, nombre, artista_disco, pistas = _leer_spotify(texto)
    album, anio = "", ""
    if tipo == "album":
        # Álbum completo: mismo disco, artista y año en todas las pistas
        album = nombre
        ficha = portadas.info_album(artista_disco, album)
        anio = ficha["anio"] if ficha else ""
        nombre = f"{artista_disco} - {album}" + (f" ({anio})" if anio else "")
    canciones = [
        Cancion(indice=i, video_id="", titulo=p["titulo"], artista=p["artista"], duracion=p["duracion"],
                album=album, artista_album=artista_disco, anio=anio, total=len(pistas))
        for i, p in enumerate(pistas, 1)
    ]
    hechas = 0

    def resolver(c: Cancion, p: dict) -> None:
        nonlocal hechas
        r = _emparejar(p, album)
        if r:
            c.video_id = r["videoId"]
            if not album:  # en playlists, cada canción con su propio disco
                su_album = r.get("album")
                c.album = su_album.get("name", "") if isinstance(su_album, dict) else ""
        else:
            c.estado, c.error = "Error", "No está en YouTube Music"
        hechas += 1
        if avisar:
            avisar(hechas, len(canciones))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(resolver, canciones, pistas))
    return nombre, canciones
