"""Actualización automática desde GitHub.

Al arrancar, la app compara su versión con el último commit de la rama main del
repositorio. Si hay uno nuevo, ofrece actualizar: descarga los archivos (o hace
`git pull` si la carpeta es un clon de git), actualiza las librerías y reinicia.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

REPO = "heyteamsoftware/HeySuperRecopilatorios"
RAMA = "main"
CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_VERSION = os.path.join(CARPETA, "version.txt")
_UA = {"User-Agent": "SuperRecopilatorios-actualizador"}
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _es_git() -> bool:
    return os.path.isdir(os.path.join(CARPETA, ".git")) and shutil.which("git") is not None


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", CARPETA, *args], capture_output=True, text=True,
                          timeout=120, creationflags=_SIN_VENTANA)


def version_remota() -> str | None:
    """SHA del último commit publicado en GitHub (None si no hay conexión)."""
    peticion = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/commits/{RAMA}",
        headers={**_UA, "Accept": "application/vnd.github.sha"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=8) as r:
            sha = r.read().decode().strip()
        return sha if len(sha) == 40 else None
    except Exception:  # noqa: BLE001
        return None


def version_local() -> str | None:
    if _es_git():
        r = _git("rev-parse", "HEAD")
        return r.stdout.strip() if r.returncode == 0 else None
    try:
        with open(ARCHIVO_VERSION, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def hay_actualizacion() -> str | None:
    """Devuelve el SHA nuevo si en GitHub hay una versión que aquí no está; si no, None."""
    remota = version_remota()
    if not remota:
        return None
    if _es_git():
        # En un clon de git: hay novedad si ese commit no existe aquí todavía.
        return remota if _git("cat-file", "-e", f"{remota}^{{commit}}").returncode != 0 else None
    return remota if remota != version_local() else None


def _python_consola() -> str:
    """python.exe del entorno (pythonw no sirve para pip)."""
    exe = sys.executable
    candidato = os.path.join(os.path.dirname(exe), "python.exe")
    return candidato if os.path.exists(candidato) else exe


def actualizar(sha: str) -> None:
    """Descarga la versión nueva sobre esta carpeta. Lanza una excepción si algo falla."""
    if _es_git():
        r = _git("pull", "--ff-only", "origin", RAMA)
        if r.returncode != 0:
            raise RuntimeError("git pull ha fallado: " + (r.stderr or r.stdout).strip()[:200])
    else:
        url = f"https://codeload.github.com/{REPO}/zip/{sha}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=60) as r:
            datos = r.read()
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(io.BytesIO(datos)) as z:
                z.extractall(tmp)
            raiz = os.path.join(tmp, os.listdir(tmp)[0])  # «HeySuperRecopilatorios-<sha>/»
            for actual, dirs, archivos in os.walk(raiz):
                dirs[:] = [d for d in dirs if d not in (".venv", ".git", "__pycache__")]
                destino = os.path.join(CARPETA, os.path.relpath(actual, raiz))
                os.makedirs(destino, exist_ok=True)
                for nombre in archivos:
                    shutil.copy2(os.path.join(actual, nombre), os.path.join(destino, nombre))
        with open(ARCHIVO_VERSION, "w", encoding="utf-8") as f:
            f.write(sha)

    # Por si la versión nueva necesita librerías nuevas
    requisitos = os.path.join(CARPETA, "requirements.txt")
    if os.path.exists(requisitos):
        subprocess.run([_python_consola(), "-m", "pip", "install", "-q", "--disable-pip-version-check",
                        "--upgrade", "-r", requisitos], capture_output=True, timeout=600,
                       creationflags=_SIN_VENTANA)


def reiniciar() -> None:
    """Abre de nuevo la app (la ventana actual debe cerrarse después)."""
    exe = sys.executable
    sin_consola = os.path.join(os.path.dirname(exe), "pythonw.exe")
    subprocess.Popen([sin_consola if os.path.exists(sin_consola) else exe,
                      os.path.join(CARPETA, "app.pyw")], cwd=CARPETA)
