"""Núcleo de SuperRecopilatorios: busca los grandes éxitos de un artista y los descarga en MP3."""

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
    progreso: float = 0.0  # 0..100
    estado: str = "En cola"  # En cola | Preparando | Descargando | Convirtiendo | Listo | Error
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
        pistas += yt.search(nombre, filter="songs", limit=50)

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


def _descargar_una(cancion: Cancion, carpeta: str, avisar: Callable[[Cancion], None]) -> None:
    base = _nombre_archivo(f"{cancion.indice:02d} - {cancion.artista} - {cancion.titulo}")
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
            info["album_artists"] = artistas[:1]
            info["album_artist"] = artistas[0] if artistas else cancion.artista
            if cancion.album:
                info["album"] = cancion.album
            info["track_number"] = cancion.indice
            info["description"] = info["synopsis"] = None
            # La fecha de subida a YouTube no es la del disco: mejor no etiquetar.
            for campo in ("upload_date", "release_date", "release_year", "timestamp", "release_timestamp"):
                info[campo] = None
            ydl.process_ie_result(info, download=True)
        cancion.archivo = destino_mp3
        cancion.progreso, cancion.estado = 100.0, "Listo"
    except Exception as exc:  # noqa: BLE001 - queremos seguir con el resto
        cancion.estado = "Error"
        cancion.error = re.sub(r"^ERROR:\s*", "", str(exc)).splitlines()[0][:200]
    avisar(cancion)


def descargar_todas(
    canciones: list[Cancion],
    carpeta: str,
    avisar: Callable[[Cancion], None],
    simultaneas: int = DESCARGAS_SIMULTANEAS,
) -> None:
    """Descarga todas las canciones (varias a la vez) y bloquea hasta terminar."""
    os.makedirs(carpeta, exist_ok=True)
    with ThreadPoolExecutor(max_workers=simultaneas) as pool:
        for c in canciones:
            pool.submit(_descargar_una, c, carpeta, avisar)
