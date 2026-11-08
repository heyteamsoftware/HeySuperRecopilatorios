"""SuperRecopilatorios — descarga en MP3 los éxitos de artistas o playlists de Spotify, en cola."""

from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, ttk

import recopilador as rc

APP = "SuperRecopilatorios"
CONFIG = Path(os.environ.get("APPDATA", Path.home())) / APP / "config.json"

# Paleta
FONDO = "#F6F7FB"
TARJETA = "#FFFFFF"
TEXTO = "#1E2230"
SUAVE = "#7A8194"
ACENTO = "#5B5BF0"
ACENTO_HOVER = "#4848D8"
OK = "#1FAA6B"
MAL = "#E0475B"
PISTA = "#E7E9F2"
FUENTE = "Segoe UI"


def _cargar_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar_config(datos: dict) -> None:
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


class FilaCancion:
    """Una línea de la lista: número, título, barra y porcentaje."""

    def __init__(self, padre: tk.Widget, cancion: rc.Cancion, fila: int):
        self.cancion = cancion
        fondo = TARJETA
        self.marco = tk.Frame(padre, bg=fondo)
        self.marco.grid(row=fila, column=0, sticky="ew", pady=(0, 2))
        self.marco.columnconfigure(1, weight=1)

        tk.Label(self.marco, text=f"{cancion.indice:02d}", bg=fondo, fg=SUAVE,
                 font=(FUENTE, 10), width=3, anchor="w").grid(row=0, column=0, rowspan=2, sticky="w", padx=(14, 6))

        self.titulo = tk.Label(self.marco, text=cancion.titulo, bg=fondo, fg=TEXTO,
                               font=(FUENTE, 10, "bold"), anchor="w", width=1)
        self.titulo.grid(row=0, column=1, sticky="ew", pady=(7, 0))
        self.sub = tk.Label(self.marco, text=cancion.artista, bg=fondo, fg=SUAVE,
                            font=(FUENTE, 9), anchor="w", width=1)
        self.sub.grid(row=1, column=1, sticky="ew", pady=(0, 7))

        self.barra = ttk.Progressbar(self.marco, style="Fila.Horizontal.TProgressbar",
                                     length=int(150 * padre.winfo_fpixels("1i") / 96), maximum=100)
        self.barra.grid(row=0, column=2, rowspan=2, padx=(12, 10))

        self.pct = tk.Label(self.marco, text="", bg=fondo, fg=SUAVE, font=(FUENTE, 10),
                            width=6, anchor="e")
        self.pct.grid(row=0, column=3, rowspan=2, padx=(0, 14))
        self._ultimo = None
        self.refrescar()

    def refrescar(self) -> None:
        c = self.cancion
        clave = (c.estado, int(c.progreso))
        if clave == self._ultimo:
            return
        self._ultimo = clave
        self.barra["value"] = c.progreso
        if c.estado == "Listo":
            self.barra.configure(style="Ok.Horizontal.TProgressbar")
            self.pct.configure(text="100 %", fg=OK)
        elif c.estado == "Error":
            self.barra.configure(style="Mal.Horizontal.TProgressbar")
            self.barra["value"] = 100
            self.pct.configure(text="Error", fg=MAL)
            self.sub.configure(text=f"{c.artista} · {c.error}"[:110], fg=MAL)
        elif c.estado == "En cola":
            self.pct.configure(text="—", fg=SUAVE)
        else:
            self.pct.configure(text=f"{int(c.progreso)} %", fg=TEXTO)


@dataclass
class Trabajo:
    """Un artista o una lista de Spotify en la cola."""

    consulta: str
    spotify: bool = False
    nombre: str = ""
    canciones: list = field(default_factory=list)
    carpeta: str = ""
    estado: str = "pendiente"  # pendiente | buscando | descargando | listo | error
    mensaje: str = ""
    chip: tk.Frame | None = None
    chip_texto: tk.Label | None = None
    chip_quitar: tk.Label | None = None

    @property
    def etiqueta(self) -> str:
        if self.nombre:
            return self.nombre
        return "Playlist de Spotify" if self.spotify else self.consulta

    def progreso(self) -> float:
        if not self.canciones:
            return 0.0
        return sum(c.progreso if c.estado != "Error" else 100 for c in self.canciones) / len(self.canciones)


CHIP = {  # estado -> (fondo, texto)
    "pendiente": (PISTA, TEXTO),
    "buscando": (ACENTO, "white"),
    "descargando": (ACENTO, "white"),
    "listo": ("#DDF3E8", "#137A4B"),
    "error": ("#FBE1E5", "#B8283B"),
}


class App:
    def __init__(self, raiz: tk.Tk):
        self.raiz = raiz
        self.config = _cargar_config()
        self.carpeta_base = self.config.get("carpeta") or str(Path.home() / "Music" / APP)
        self.trabajos: list[Trabajo] = []
        self.activo: Trabajo | None = None  # el que se está descargando
        self.vista: Trabajo | None = None  # el que se muestra en la lista
        self.filas: list[FilaCancion] = []
        self._filas_de: Trabajo | None = None

        raiz.title(APP)
        raiz.configure(bg=FONDO)
        try:
            raiz.iconbitmap(default=str(Path(__file__).with_name("icono.ico")))
        except Exception:
            pass
        escala = raiz.winfo_fpixels("1i") / 96  # respeta el escalado de Windows
        raiz.geometry(f"{int(720 * escala)}x{int(860 * escala)}")
        raiz.minsize(int(560 * escala), int(520 * escala))
        self.escala = escala
        self._estilos()
        self._construir()
        self._tic()

    # ---------- aspecto ----------
    def _estilos(self) -> None:
        s = ttk.Style()
        s.theme_use("clam")
        comun = dict(troughcolor=PISTA, borderwidth=0, thickness=8, lightcolor=ACENTO, darkcolor=ACENTO,
                     bordercolor=PISTA, relief="flat")
        s.configure("Fila.Horizontal.TProgressbar", background=ACENTO, **comun)
        s.configure("Ok.Horizontal.TProgressbar", **{**comun, "background": OK, "lightcolor": OK, "darkcolor": OK})
        s.configure("Mal.Horizontal.TProgressbar", **{**comun, "background": MAL, "lightcolor": MAL, "darkcolor": MAL})
        s.configure("Total.Horizontal.TProgressbar", background=ACENTO, **{**comun, "thickness": 10})
        s.configure("TotalOk.Horizontal.TProgressbar",
                    **{**comun, "thickness": 10, "background": OK, "lightcolor": OK, "darkcolor": OK})
        s.configure("Vertical.TScrollbar", background=PISTA, troughcolor=FONDO, borderwidth=0,
                    arrowcolor=SUAVE, lightcolor=PISTA, darkcolor=PISTA, bordercolor=FONDO, arrowsize=12)
        s.map("Vertical.TScrollbar", background=[("active", "#D3D6E4")])

    def _boton(self, padre, texto, comando, primario=True) -> tk.Label:
        if primario:
            b = tk.Label(padre, text=texto, bg=ACENTO, fg="white", cursor="hand2",
                         font=(FUENTE, 10, "bold"), padx=18, pady=9)
            b._estilo = {True: dict(bg=ACENTO, fg="white"), False: dict(bg="#B9BCD0", fg="white")}
            hover = dict(bg=ACENTO_HOVER)
        else:
            b = tk.Label(padre, text=texto, bg=FONDO, fg=ACENTO, cursor="hand2",
                         font=(FUENTE, 9, "bold"), padx=8, pady=2)
            b._estilo = {True: dict(bg=FONDO, fg=ACENTO), False: dict(bg=FONDO, fg="#B6BBCB")}
            hover = dict(bg=PISTA)
        b._activo = True
        b.bind("<Enter>", lambda e: b._activo and b.configure(**hover))
        b.bind("<Leave>", lambda e: b.configure(**b._estilo[b._activo]))
        b.bind("<Button-1>", lambda e: b._activo and comando())
        return b

    def _activar(self, boton: tk.Label, activo: bool) -> None:
        boton._activo = activo
        boton.configure(cursor="hand2" if activo else "arrow", **boton._estilo[activo])

    def _construir(self) -> None:
        r = self.raiz
        cab = tk.Frame(r, bg=FONDO)
        cab.pack(fill="x", padx=28, pady=(24, 6))
        tk.Label(cab, text="SuperRecopilatorios", bg=FONDO, fg=TEXTO,
                 font=(FUENTE, 20, "bold")).pack(anchor="w")
        tk.Label(cab, text="Escribe un artista o pega una playlist de Spotify. Puedes añadir varios: se descargan en cola.",
                 bg=FONDO, fg=SUAVE, font=(FUENTE, 10), anchor="w", justify="left",
                 wraplength=int(640 * self.escala)).pack(anchor="w", fill="x")

        # Buscador: siempre activo, cada Intro añade a la cola
        caja = tk.Frame(r, bg=FONDO)
        caja.pack(fill="x", padx=28, pady=(14, 4))
        marco_entrada = tk.Frame(caja, bg=TARJETA, highlightthickness=1,
                                 highlightbackground=PISTA, highlightcolor=ACENTO)
        marco_entrada.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entrada = tk.Entry(marco_entrada, bd=0, bg=TARJETA, fg=TEXTO, insertbackground=TEXTO,
                                font=(FUENTE, 12), relief="flat")
        self.entrada.pack(fill="x", padx=12, pady=8)
        self.entrada.bind("<Return>", lambda e: self.anadir())
        self.entrada.focus_set()
        self.btn = self._boton(caja, "Descargar", self.anadir)
        self.btn.pack(side="right")

        # Cola: una etiqueta por artista / playlist
        self.cola = tk.Frame(r, bg=FONDO, height=1)
        self.cola.pack(fill="x", padx=28, pady=(6, 0))
        self.cola.bind("<Configure>", lambda e: self._maquetar_cola())

        # Estado general
        estado = tk.Frame(r, bg=FONDO)
        estado.pack(fill="x", padx=28, pady=(10, 4))
        self.lbl_estado = tk.Label(estado, text="", bg=FONDO, fg=SUAVE, font=(FUENTE, 10), anchor="w", width=1)
        self.lbl_estado.pack(side="left", fill="x", expand=True)
        self.lbl_total = tk.Label(estado, text="", bg=FONDO, fg=TEXTO, font=(FUENTE, 10, "bold"))
        self.lbl_total.pack(side="right")
        self.barra_total = ttk.Progressbar(r, style="Total.Horizontal.TProgressbar", maximum=100)
        self.barra_total.pack(fill="x", padx=28, pady=(0, 12))

        # Lista desplazable
        contenedor = tk.Frame(r, bg=FONDO)
        contenedor.pack(fill="both", expand=True, padx=28)
        self.lienzo = tk.Canvas(contenedor, bg=FONDO, highlightthickness=0, bd=0)
        barra = ttk.Scrollbar(contenedor, orient="vertical", command=self.lienzo.yview)
        self.lista = tk.Frame(self.lienzo, bg=FONDO)
        self.lista.columnconfigure(0, weight=1)
        ventana = self.lienzo.create_window((0, 0), window=self.lista, anchor="nw")
        self.lista.bind("<Configure>", lambda e: self.lienzo.configure(scrollregion=self.lienzo.bbox("all")))
        self.lienzo.bind("<Configure>", lambda e: self.lienzo.itemconfigure(ventana, width=e.width))
        self.lienzo.configure(yscrollcommand=barra.set)
        self.lienzo.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.raiz.bind_all("<MouseWheel>", lambda e: self.lienzo.yview_scroll(int(-e.delta / 120), "units"))

        self.vacio = tk.Label(self.lista, text="♪\n\nAquí aparecerán las canciones",
                              bg=FONDO, fg="#B6BBCB", font=(FUENTE, 12), pady=120)
        self.vacio.grid(row=0, column=0, sticky="ew")

        # Pie: carpeta de destino
        pie = tk.Frame(r, bg=FONDO)
        pie.pack(fill="x", padx=28, pady=(10, 18))
        self.lbl_carpeta = tk.Label(pie, text="", bg=FONDO, fg=SUAVE, font=(FUENTE, 9), anchor="w", width=1)
        self.lbl_carpeta.pack(side="left", fill="x", expand=True)
        self.btn_abrir = self._boton(pie, "Abrir carpeta", self.abrir_carpeta, primario=False)
        self.btn_abrir.pack(side="right")
        self.btn_cambiar = self._boton(pie, "Cambiar…", self.cambiar_carpeta, primario=False)
        self.btn_cambiar.pack(side="right", padx=(0, 4))
        self._pintar_carpeta()

        if not rc.ffmpeg_disponible():
            self._activar(self.btn, False)
            self.lbl_estado.configure(
                text="Falta FFmpeg. Ejecuta «instalar.bat» y vuelve a abrir la app.", fg=MAL)

    def _pintar_carpeta(self) -> None:
        ruta = self.vista.carpeta if self.vista and self.vista.carpeta else self.carpeta_base
        self.lbl_carpeta.configure(text=f"Guardando en:  {ruta}")

    # ---------- cola ----------
    def anadir(self) -> None:
        texto = self.entrada.get().strip()
        if not texto or not rc.ffmpeg_disponible():
            return
        self.entrada.delete(0, "end")
        spotify = rc.es_spotify(texto)
        clave = texto.lower()
        if any(t.consulta.lower() == clave and t.estado in ("pendiente", "buscando", "descargando")
               for t in self.trabajos):
            return  # ya está en la cola
        t = Trabajo(consulta=texto, spotify=spotify)
        self.trabajos.append(t)
        self._crear_chip(t)
        if self.activo is None:
            self._siguiente()

    def _crear_chip(self, t: Trabajo) -> None:
        chip = tk.Frame(self.cola, bg=PISTA, highlightthickness=2, highlightbackground=FONDO, cursor="hand2")
        texto = tk.Label(chip, text="", bg=PISTA, fg=TEXTO, font=(FUENTE, 9, "bold"), padx=10, pady=4, cursor="hand2")
        texto.pack(side="left")
        quitar = tk.Label(chip, text="✕", bg=PISTA, fg=SUAVE, font=(FUENTE, 9), padx=6, cursor="hand2")
        quitar.pack(side="left")
        for w in (chip, texto):
            w.bind("<Button-1>", lambda e, t=t: self._ver(t))
        quitar.bind("<Button-1>", lambda e, t=t: self._quitar(t))
        t.chip, t.chip_texto, t.chip_quitar = chip, texto, quitar
        self._pintar_chip(t)
        self._maquetar_cola()

    def _pintar_chip(self, t: Trabajo) -> None:
        if not t.chip:
            return
        fondo, color = CHIP[t.estado]
        icono = "♫ " if t.spotify else ""
        if t.estado == "buscando":
            texto = f"{icono}{t.etiqueta} · buscando…"
        elif t.estado == "descargando":
            texto = f"{icono}{t.etiqueta} · {int(t.progreso())} %"
        elif t.estado == "listo":
            hechas = sum(c.estado == "Listo" for c in t.canciones)
            texto = f"{icono}{t.etiqueta} · {hechas}/{len(t.canciones)}"
        else:
            texto = f"{icono}{t.etiqueta}"
        if len(texto) > 48:
            texto = texto[:46] + "…"
        borde = TEXTO if t is self.vista else FONDO
        if t.chip_texto.cget("text") != texto or t.chip.cget("bg") != fondo:
            t.chip_texto.configure(text=texto, bg=fondo, fg=color)
            t.chip.configure(bg=fondo)
            t.chip_quitar.configure(bg=fondo, fg=color)
        t.chip.configure(highlightbackground=borde)
        # Solo se pueden quitar los que aún esperan o ya terminaron
        if t.estado in ("buscando", "descargando"):
            t.chip_quitar.pack_forget()
        elif not t.chip_quitar.winfo_ismapped():
            t.chip_quitar.pack(side="left")

    def _maquetar_cola(self) -> None:
        """Coloca las etiquetas en filas, saltando de línea cuando no caben."""
        self.cola.update_idletasks()
        ancho = max(self.cola.winfo_width(), 100)
        x = y = alto_fila = 0
        hueco = 6
        for t in self.trabajos:
            w, h = t.chip.winfo_reqwidth(), t.chip.winfo_reqheight()
            if x and x + w > ancho:
                x, y, alto_fila = 0, y + alto_fila + hueco, 0
            t.chip.place(x=x, y=y)
            x += w + hueco
            alto_fila = max(alto_fila, h)
        alto = y + alto_fila if self.trabajos else 1
        if int(self.cola.cget("height")) != alto:
            self.cola.configure(height=alto)

    def _quitar(self, t: Trabajo) -> None:
        if t.estado in ("buscando", "descargando"):
            return
        self.trabajos.remove(t)
        t.chip.destroy()
        if self.vista is t:
            self._ver(self.activo or (self.trabajos[-1] if self.trabajos else None))
        self._maquetar_cola()

    def _siguiente(self, mostrar: bool = True) -> None:
        t = next((t for t in self.trabajos if t.estado == "pendiente"), None)
        self.activo = t
        if t is None:
            return
        t.estado = "buscando"
        self._pintar_chip(t)
        if mostrar or self.vista is None:
            self._ver(t)
        threading.Thread(target=self._trabajo, args=(t,), daemon=True).start()

    def _trabajo(self, t: Trabajo) -> None:
        try:
            if t.spotify:
                nombre, canciones = rc.buscar_spotify(
                    t.consulta, avisar=lambda n, total: setattr(t, "mensaje", f"Buscando canciones en YouTube… {n}/{total}"))
                carpeta_nombre = nombre
            else:
                nombre, canciones = rc.buscar_exitos(t.consulta)
                carpeta_nombre = f"{nombre} - Grandes éxitos"
        except Exception as exc:  # noqa: BLE001
            t.estado = "error"
            t.mensaje = str(exc) if isinstance(exc, LookupError) else "No he podido buscar. ¿Hay conexión a Internet?"
            self.raiz.after(0, self._terminado, t)
            return
        t.nombre, t.canciones = nombre, canciones
        t.carpeta = os.path.join(self.carpeta_base, rc._nombre_archivo(carpeta_nombre))
        t.estado = "descargando"
        t.mensaje = ""
        self.raiz.after(0, self._ver_si_toca, t)
        rc.descargar_todas(canciones, t.carpeta, avisar=lambda c: None)
        hechas = sum(c.estado == "Listo" for c in canciones)
        fallos = len(canciones) - hechas
        de = f"de la playlist «{nombre}»" if t.spotify else f"de {nombre}"
        t.mensaje = f"¡Listo! {hechas} canciones {de} descargadas."
        if fallos:
            t.mensaje += f"  ({fallos} no se pudieron descargar)"
        t.estado = "listo"
        self.raiz.after(0, self._terminado, t)

    def _ver_si_toca(self, t: Trabajo) -> None:
        if self.vista is t:
            self._ver(t)

    def _terminado(self, t: Trabajo) -> None:
        self._pintar_chip(t)
        seguia = self.vista is t  # si estabas mirando este, pasa al siguiente
        self._siguiente(mostrar=seguia)
        if self.vista is t:
            self._ver(t)
        self._maquetar_cola()

    # ---------- lista de canciones ----------
    def _ver(self, t: Trabajo | None) -> None:
        anterior, self.vista = self.vista, t
        for x in (anterior, t):
            if x and x.chip and x in self.trabajos:
                self._pintar_chip(x)
        if t is not self._filas_de or (t and len(self.filas) != len(t.canciones)):
            for f in self.filas:
                f.marco.destroy()
            self.filas = [FilaCancion(self.lista, c, i) for i, c in enumerate(t.canciones)] if t else []
            self._filas_de = t
            self.lienzo.yview_moveto(0)
        if self.filas:
            self.vacio.grid_remove()
        else:
            self.vacio.grid()
            if t is None:
                self.vacio.configure(text="♪\n\nAquí aparecerán las canciones")
            elif t.estado == "pendiente":
                self.vacio.configure(text="En cola…\n\nEmpezará cuando terminen los anteriores")
            elif t.estado == "buscando":
                self.vacio.configure(text="Leyendo la playlist…" if t.spotify else "Buscando los grandes éxitos…")
            else:
                self.vacio.configure(text="♪\n\nNo hay canciones")
        self._pintar_carpeta()
        self._refrescar()

    # ---------- acciones ----------
    def cambiar_carpeta(self) -> None:
        elegida = filedialog.askdirectory(initialdir=self.carpeta_base, title="Carpeta para los recopilatorios")
        if elegida:
            self.carpeta_base = os.path.normpath(elegida)
            self.config["carpeta"] = self.carpeta_base
            _guardar_config(self.config)
            self._pintar_carpeta()

    def abrir_carpeta(self) -> None:
        ruta = self.vista.carpeta if self.vista and os.path.isdir(self.vista.carpeta or "") else self.carpeta_base
        os.makedirs(ruta, exist_ok=True)
        os.startfile(ruta)

    # ---------- refresco periódico (hilo de la interfaz) ----------
    def _refrescar(self) -> None:
        for f in self.filas:
            f.refrescar()
        t = self.vista
        if self.activo:
            self._pintar_chip(self.activo)
            self._maquetar_cola()  # el % cambia el ancho de la etiqueta

        if t and t.canciones:
            total = t.progreso()
            self.barra_total["value"] = total
            listas = sum(c.estado == "Listo" for c in t.canciones)
            self.lbl_total.configure(text=f"{listas}/{len(t.canciones)} · {int(total)} %")
        else:
            self.barra_total["value"] = 0
            self.lbl_total.configure(text="")
        self.barra_total.configure(
            style="TotalOk.Horizontal.TProgressbar" if t and t.estado == "listo" else "Total.Horizontal.TProgressbar")

        if t is None:
            texto, color = "", SUAVE
        elif t.estado == "pendiente":
            texto, color = f"«{t.etiqueta}» está en cola.", SUAVE
        elif t.estado == "buscando":
            texto = t.mensaje or ("Leyendo la playlist de Spotify…" if t.spotify else f"Buscando éxitos de «{t.consulta}»…")
            color = SUAVE
        elif t.estado == "descargando":
            texto, color = f"Descargando {len(t.canciones)} canciones de {t.etiqueta}…", SUAVE
        else:
            texto, color = t.mensaje, (MAL if t.estado == "error" else OK)
        en_cola = sum(x.estado == "pendiente" for x in self.trabajos)
        if en_cola and t and t.estado != "pendiente":
            texto += f"   ·   {en_cola} más en cola"
        if rc.ffmpeg_disponible():
            self.lbl_estado.configure(text=texto, fg=color)

    def _tic(self) -> None:
        if self.activo or self.vista:
            self._refrescar()
        self.raiz.after(150, self._tic)


def main() -> None:
    try:  # textos nítidos en pantallas con escalado
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    raiz = tk.Tk()
    App(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
