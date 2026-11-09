"""Portadas oficiales: las busca en Deezer (con iTunes de respaldo) y las incrusta en los MP3."""

from __future__ import annotations

import difflib
import json
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from mutagen.id3 import APIC, ID3, TCON, TDRC, TXXX, ID3NoHeaderError

MARCA = "SR_PORTADA"  # etiqueta que indica que ya tiene la portada oficial
# MusicBrainz pide identificar la app con una forma de contacto
_UA = {"User-Agent": "HeyMp3/1.0 ( https://github.com/heyteamsoftware/HeySuperRecopilatorios )",
       "Accept": "application/json"}
_VARIANTES = re.compile(r"\b(remix|slowed|reverb|sped up|live|en vivo|karaoke|instrumental|acoustic|8d)\b", re.I)

_cache_busquedas: dict[tuple, str | None] = {}  # búsquedas ya hechas
_cache_imagenes: dict[str, bytes | None] = {}
_cerrojo = threading.Lock()
_ultima_llamada = {"deezer": 0.0, "itunes": 0.0, "musicbrainz": 0.0}
_ESPERA = {"deezer": 0.15, "itunes": 3.1, "musicbrainz": 1.1}  # límites de uso de cada servicio


# ---------------------------------------------------------------- utilidades

def _normalizar(texto: str) -> str:
    texto = re.sub(r"[\(\[].*?[\)\]]", "", texto or "")
    texto = re.split(r"\s[-–—]\s|\bfeat\.?\s|\bft\.?\s", texto, flags=re.I)[0]
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def _artistas(texto: str) -> list[str]:
    partes = re.split(r",|&|\by\b|\band\b|\bfeat\.?|\bft\.?|\bcon\b|\bx\b", texto or "", flags=re.I)
    return [n for n in (_normalizar(p) for p in partes) if n]


def _parecido(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _pedir(servicio: str, url: str):
    """GET con pausa entre llamadas para no superar el límite del servicio."""
    for intento in range(3):
        with _cerrojo:
            espera = _ultima_llamada[servicio] + _ESPERA[servicio] - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            _ultima_llamada[servicio] = time.monotonic()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=15) as r:
                datos = json.load(r)
            if servicio == "deezer" and isinstance(datos, dict) and "error" in datos:
                time.sleep(3 * (intento + 1))  # cuota superada: espera y reintenta
                continue
            return datos
        except Exception:  # noqa: BLE001
            time.sleep(2 * (intento + 1))
    return None


def _descargar_imagen(url: str) -> bytes | None:
    if url in _cache_imagenes:
        return _cache_imagenes[url]
    datos = None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=20) as r:
            datos = r.read()
        if not (datos[:2] == b"\xff\xd8" or datos[:8] == b"\x89PNG\r\n\x1a\n") or len(datos) < 5000:
            datos = None
    except Exception:  # noqa: BLE001
        datos = None
    _cache_imagenes[url] = datos
    return datos


# ---------------------------------------------------------------- búsqueda

def _mismo_artista(suyo: str, mio: str) -> bool:
    mis, sus = set(_artistas(mio)), set(_artistas(suyo))
    return any(a in b or b in a for a in mis for b in sus)


def _mismo_album(suyo: str, mio: str) -> bool:
    a, b = _normalizar(suyo), _normalizar(mio)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a)) or _parecido(a, b) >= 0.8


def _elegir_cancion(candidatos: list[tuple[str, str, str, str]], artista: str, titulo: str, album: str,
                    exigir_album: bool) -> str | None:
    """candidatos: (artista, título, álbum, url_portada). Devuelve la url más fiable o None."""
    mi_titulo = _normalizar(titulo)
    quiero_variante = bool(_VARIANTES.search(titulo))
    mejor, mejor_puntos = None, 0.0
    for c_artista, c_titulo, c_album, url in candidatos:
        if not url or not _mismo_artista(c_artista, artista):
            continue
        t = _normalizar(c_titulo)
        parecido_titulo = 1.0 if t == mi_titulo else _parecido(t, mi_titulo)
        if parecido_titulo < 0.85:
            continue
        coincide_album = _mismo_album(c_album, album)
        if exigir_album and not coincide_album:
            continue
        puntos = parecido_titulo + (0.6 if coincide_album else 0)
        if not quiero_variante and _VARIANTES.search(f"{c_titulo} {c_album}"):
            puntos -= 0.5
        if puntos > mejor_puntos:
            mejor, mejor_puntos = url, puntos
    return mejor


def _principal(artista: str) -> str:
    return re.split(r",|&", artista)[0].strip()


def _sin_parentesis(texto: str) -> str:
    return re.sub(r"\s*[\(\[].*?[\)\]]", "", texto).strip() or texto


def _anio(fecha: str) -> str:
    anio = (fecha or "")[:4]
    return anio if anio.isdigit() and anio != "0000" else ""


def _ficha_deezer(artista: str, album: str) -> dict | None:
    q = urllib.parse.quote(f"{_principal(artista)} {_sin_parentesis(album)}")
    datos = _pedir("deezer", f"https://api.deezer.com/search/album?limit=10&q={q}") or {}
    for d in datos.get("data", []):
        su_artista = (d.get("artist") or {}).get("name", "")
        if d.get("cover_xl") and _mismo_artista(su_artista, artista) and _mismo_album(d.get("title", ""), album):
            detalle = _pedir("deezer", f"https://api.deezer.com/album/{d['id']}") or {}
            generos = (detalle.get("genres") or {}).get("data") or []
            return {
                "titulo": d.get("title", album), "artista": su_artista,
                "anio": _anio(detalle.get("release_date", "")),
                "genero": generos[0].get("name", "") if generos else "",
                "pistas": detalle.get("nb_tracks") or d.get("nb_tracks") or 0,
                "portada": d["cover_xl"],
            }
    return None


def _ficha_itunes(artista: str, album: str) -> dict | None:
    q = urllib.parse.quote(f"{_principal(artista)} {_sin_parentesis(album)}")
    datos = _pedir("itunes", f"https://itunes.apple.com/search?entity=album&limit=10&country=ES&term={q}") or {}
    for d in datos.get("results", []):
        portada = (d.get("artworkUrl100") or "").replace("100x100bb", "1000x1000bb")
        if portada and _mismo_artista(d.get("artistName", ""), artista) and _mismo_album(d.get("collectionName", ""), album):
            return {
                "titulo": d.get("collectionName", album), "artista": d.get("artistName", ""),
                "anio": _anio(d.get("releaseDate", "")), "genero": d.get("primaryGenreName", ""),
                "pistas": d.get("trackCount") or 0, "portada": portada,
            }
    return None


def _anio_original(artista: str, album: str) -> str:
    """Año de la PRIMERA edición del disco según MusicBrainz ("" si no se sabe).

    Deezer e iTunes suelen dar el año de la reedición o remasterización que tienen.
    """
    titulo = _sin_parentesis(album).replace('"', "").replace("\\", "")
    autor = _principal(artista).replace('"', "").replace("\\", "")
    q = urllib.parse.quote(f'releasegroup:"{titulo}" AND artist:"{autor}"')
    datos = _pedir("musicbrainz", f"https://musicbrainz.org/ws/2/release-group/?fmt=json&limit=5&query={q}") or {}
    for g in datos.get("release-groups", []):
        if (g.get("score") or 0) < 90:
            continue
        credito = " ".join(a.get("name", "") for a in g.get("artist-credit", []) if isinstance(a, dict))
        if _mismo_artista(credito, artista) and _mismo_album(g.get("title", ""), album):
            return _anio(g.get("first-release-date", ""))
    return ""


def info_album(artista: str, album: str) -> dict | None:
    """Ficha oficial de un disco: titulo, artista, anio, genero, pistas y portada (url).

    Busca en Deezer y, si no aparece, en iTunes. None si no hay coincidencia segura.
    """
    if not artista or not album:
        return None
    clave = ("ficha", _normalizar(_principal(artista)), _normalizar(album))
    if clave not in _cache_busquedas:
        ficha = _ficha_deezer(artista, album) or _ficha_itunes(artista, album)
        if ficha:
            ficha["anio"] = _anio_original(artista, album) or ficha["anio"]
        _cache_busquedas[clave] = ficha
    return _cache_busquedas[clave]


def _cancion_deezer(artista: str, titulo: str, album: str, exigir_album: bool) -> str | None:
    q = urllib.parse.quote(f"{_principal(artista)} {_sin_parentesis(titulo)}")
    datos = _pedir("deezer", f"https://api.deezer.com/search/track?limit=10&q={q}") or {}
    candidatos = [
        (d["artist"]["name"], d["title"], d["album"]["title"], d["album"].get("cover_xl") or d["album"].get("cover_big"))
        for d in datos.get("data", [])
        if d.get("artist") and d.get("album")
    ]
    return _elegir_cancion(candidatos, artista, titulo, album, exigir_album)


def _cancion_itunes(artista: str, titulo: str, album: str, exigir_album: bool) -> str | None:
    q = urllib.parse.quote(f"{_principal(artista)} {_sin_parentesis(titulo)}")
    datos = _pedir("itunes", f"https://itunes.apple.com/search?entity=song&limit=10&country=ES&term={q}") or {}
    candidatos = [
        (d.get("artistName", ""), d.get("trackName", ""), d.get("collectionName", ""),
         (d.get("artworkUrl100") or "").replace("100x100bb", "1000x1000bb"))
        for d in datos.get("results", [])
    ]
    return _elegir_cancion(candidatos, artista, titulo, album, exigir_album)


def _buscar_url(artista: str, titulo: str, album: str, exigir_album: bool) -> str | None:
    if album:
        # 1) El disco exacto que figura en la etiqueta (una búsqueda por álbum, se reutiliza)
        ficha = info_album(artista, album)
        if ficha:
            return ficha["portada"]
    # 2) La canción, y de ahí su disco
    clave = ("cancion", _normalizar(artista), _normalizar(titulo), _normalizar(album), exigir_album)
    if clave not in _cache_busquedas:
        _cache_busquedas[clave] = (_cancion_deezer(artista, titulo, album, exigir_album)
                                   or _cancion_itunes(artista, titulo, album, exigir_album))
    return _cache_busquedas[clave]


def buscar_portada(artista: str, titulo: str, album: str = "",
                   exigir_album: bool = False) -> tuple[bytes, str] | None:
    """Devuelve (imagen, fuente) con la portada oficial, o None si no hay certeza.

    Con exigir_album=True solo vale la portada del mismo disco que figura en la etiqueta
    (se usa cuando la canción ya tiene una portada, para no cambiarla por la de otro disco).
    """
    if exigir_album and not album:
        return None
    url = _buscar_url(artista, titulo, album, exigir_album)
    if not url:
        return None
    datos = _descargar_imagen(url)
    if not datos:
        return None
    return datos, ("deezer" if "dzcdn" in url else "itunes")


# ---------------------------------------------------------------- MP3

def _leer(mp3: str) -> ID3:
    try:
        return ID3(mp3)
    except ID3NoHeaderError:
        return ID3()


def tiene_portada_oficial(mp3: str) -> bool:
    try:
        return bool(_leer(mp3).getall(f"TXXX:{MARCA}"))
    except Exception:  # noqa: BLE001
        return False


def incrustar(mp3: str, imagen: bytes, fuente: str) -> None:
    tags = _leer(mp3)
    tags.delall("APIC")
    mime = "image/png" if imagen[:4] == b"\x89PNG" else "image/jpeg"
    tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=imagen))
    tags.delall(f"TXXX:{MARCA}")
    tags.add(TXXX(encoding=3, desc=MARCA, text=[fuente]))
    tags.save(mp3)


def completar_datos(mp3: str, artista: str, album: str) -> bool:
    """Añade año y género del disco si faltan. Devuelve True si cambió algo."""
    ficha = info_album(artista, album)
    if not ficha:
        return False
    tags = _leer(mp3)
    cambios = False
    if ficha["anio"] and not tags.getall("TDRC"):
        tags.add(TDRC(encoding=3, text=[ficha["anio"]]))
        cambios = True
    genero = tags.get("TCON")
    if ficha["genero"] and (not genero or str(genero.text[0]).lower() in ("music", "música", "")):
        tags.delall("TCON")
        tags.add(TCON(encoding=3, text=[ficha["genero"]]))
        cambios = True
    if cambios:
        tags.save(mp3)
    return cambios


def poner_portada(mp3: str, artista: str | None = None, titulo: str | None = None,
                  album: str | None = None, forzar: bool = False) -> str:
    """Pone la portada oficial a un MP3 y completa año y género del disco.

    Devuelve "ya_tenia", "nueva", "no_encontrada" o "error".
    """
    try:
        tags = _leer(mp3)

        def texto(frame: str) -> str:
            f = tags.get(frame)
            return str(f.text[0]) if f and f.text else ""

        artista = artista or texto("TPE2") or texto("TPE1")
        titulo = titulo or texto("TIT2")
        album = album if album is not None else texto("TALB")
        if not forzar and tiene_portada_oficial(mp3):
            if album and not tags.getall("TDRC"):
                completar_datos(mp3, artista, album)  # las antiguas no tenían año
            return "ya_tenia"
        if not artista or not titulo:
            return "no_encontrada"
        # Si ya tiene una portada, solo se cambia por la del mismo disco (nunca por la de otro).
        ya_tiene = bool(tags.getall("APIC"))
        encontrada = buscar_portada(artista, titulo, album, exigir_album=ya_tiene)
        if not encontrada:
            return "no_encontrada"
        incrustar(mp3, *encontrada)
        if album:
            completar_datos(mp3, artista, album)
        return "nueva"
    except Exception:  # noqa: BLE001
        return "error"


def listar_mp3(carpeta: str) -> list[str]:
    archivos = []
    for raiz, _dirs, nombres in os.walk(carpeta):
        archivos += [os.path.join(raiz, n) for n in sorted(nombres) if n.lower().endswith(".mp3")]
    return archivos


def revisar_carpeta(carpeta: str, avisar: Callable[[int, int, dict], None] | None = None,
                    forzar: bool = False, hilos: int = 4) -> dict:
    """Pone la portada oficial a todos los MP3 de la carpeta (y subcarpetas)."""
    archivos = listar_mp3(carpeta)
    cuenta = {"nueva": 0, "ya_tenia": 0, "no_encontrada": 0, "error": 0}
    hechos = 0
    cerrojo = threading.Lock()

    def uno(ruta: str) -> None:
        nonlocal hechos
        r = poner_portada(ruta, forzar=forzar)
        with cerrojo:
            cuenta[r] += 1
            hechos += 1
            if avisar:
                avisar(hechos, len(archivos), dict(cuenta))

    with ThreadPoolExecutor(max_workers=hilos) as pool:
        list(pool.map(uno, archivos))
    return cuenta
