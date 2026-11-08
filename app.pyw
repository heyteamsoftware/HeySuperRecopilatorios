"""SuperRecopilatorios — escribe un artista y descarga sus 20 grandes éxitos en MP3."""

from __future__ import annotations

import json
import os
import threading
import tkinter as tk
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


class App:
    def __init__(self, raiz: tk.Tk):
        self.raiz = raiz
        self.config = _cargar_config()
        self.carpeta_base = self.config.get("carpeta") or str(Path.home() / "Music" / APP)
        self.canciones: list[rc.Cancion] = []
        self.filas: list[FilaCancion] = []
        self.trabajando = False
        self.carpeta_actual = ""
        self.mensaje_fase = ""

        raiz.title(APP)
        raiz.configure(bg=FONDO)
        try:
            raiz.iconbitmap(default=str(Path(__file__).with_name("icono.ico")))
        except Exception:
            pass
        escala = raiz.winfo_fpixels("1i") / 96  # respeta el escalado de Windows
        raiz.geometry(f"{int(720 * escala)}x{int(820 * escala)}")
        raiz.minsize(int(560 * escala), int(480 * escala))
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
        tk.Label(cab, text="Escribe un artista y descarga sus 20 grandes éxitos en MP3.",
                 bg=FONDO, fg=SUAVE, font=(FUENTE, 10)).pack(anchor="w")

        # Buscador
        caja = tk.Frame(r, bg=FONDO)
        caja.pack(fill="x", padx=28, pady=(14, 6))
        marco_entrada = tk.Frame(caja, bg=TARJETA, highlightthickness=1,
                                 highlightbackground=PISTA, highlightcolor=ACENTO)
        marco_entrada.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entrada = tk.Entry(marco_entrada, bd=0, bg=TARJETA, fg=TEXTO, insertbackground=TEXTO,
                                disabledbackground=TARJETA, disabledforeground=SUAVE,
                                font=(FUENTE, 12), relief="flat")
        self.entrada.pack(fill="x", padx=12, pady=8)
        self.entrada.bind("<Return>", lambda e: self.empezar())
        self.entrada.focus_set()
        self.btn = self._boton(caja, "Descargar éxitos", self.empezar)
        self.btn.pack(side="right")

        # Estado general
        estado = tk.Frame(r, bg=FONDO)
        estado.pack(fill="x", padx=28, pady=(10, 4))
        self.lbl_estado = tk.Label(estado, text="", bg=FONDO, fg=SUAVE, font=(FUENTE, 10), anchor="w")
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
        ruta = self.carpeta_actual or self.carpeta_base
        self.lbl_carpeta.configure(text=f"Guardando en:  {ruta}")

    # ---------- acciones ----------
    def cambiar_carpeta(self) -> None:
        if self.trabajando:
            return
        elegida = filedialog.askdirectory(initialdir=self.carpeta_base, title="Carpeta para los recopilatorios")
        if elegida:
            self.carpeta_base = os.path.normpath(elegida)
            self.carpeta_actual = ""
            self.config["carpeta"] = self.carpeta_base
            _guardar_config(self.config)
            self._pintar_carpeta()

    def abrir_carpeta(self) -> None:
        ruta = self.carpeta_actual if self.carpeta_actual and os.path.isdir(self.carpeta_actual) else self.carpeta_base
        os.makedirs(ruta, exist_ok=True)
        os.startfile(ruta)

    def empezar(self) -> None:
        artista = self.entrada.get().strip()
        if self.trabajando or not artista or not rc.ffmpeg_disponible():
            return
        self.trabajando = True
        self._activar(self.btn, False)
        self._activar(self.btn_cambiar, False)
        self.entrada.configure(state="disabled")
        for f in self.filas:
            f.marco.destroy()
        self.filas, self.canciones = [], []
        self.vacio.grid()
        self.vacio.configure(text="Buscando los grandes éxitos…")
        self.barra_total["value"] = 0
        self.barra_total.configure(style="Total.Horizontal.TProgressbar")
        self.lbl_total.configure(text="")
        self.mensaje_fase = f"Buscando éxitos de «{artista}»…"
        threading.Thread(target=self._trabajo, args=(artista,), daemon=True).start()

    def _trabajo(self, artista: str) -> None:
        try:
            nombre, canciones = rc.buscar_exitos(artista)
        except Exception as exc:  # noqa: BLE001
            texto = str(exc) if isinstance(exc, LookupError) else "No he podido buscar. ¿Hay conexión a Internet?"
            self.raiz.after(0, self._fin, texto, True)
            return
        carpeta = os.path.join(self.carpeta_base, rc._nombre_archivo(f"{nombre} - Grandes éxitos"))
        self.raiz.after(0, self._mostrar_lista, nombre, canciones, carpeta)
        rc.descargar_todas(canciones, carpeta, avisar=lambda c: None)
        hechas = sum(c.estado == "Listo" for c in canciones)
        fallos = len(canciones) - hechas
        texto = f"¡Listo! {hechas} canciones de {nombre} descargadas."
        if fallos:
            texto += f"  ({fallos} no se pudieron descargar)"
        self.raiz.after(0, self._fin, texto, False)

    def _mostrar_lista(self, nombre: str, canciones: list[rc.Cancion], carpeta: str) -> None:
        self.canciones = canciones
        self.carpeta_actual = carpeta
        self._pintar_carpeta()
        self.vacio.grid_remove()
        self.filas = [FilaCancion(self.lista, c, i) for i, c in enumerate(canciones)]
        self.lienzo.yview_moveto(0)
        self.mensaje_fase = f"Descargando {len(canciones)} éxitos de {nombre}…"

    def _fin(self, texto: str, es_error: bool) -> None:
        self.trabajando = False
        self.mensaje_fase = ""
        self._activar(self.btn, True)
        self._activar(self.btn_cambiar, True)
        self.entrada.configure(state="normal")
        self._refrescar()
        self.lbl_estado.configure(text=texto, fg=MAL if es_error else OK)
        if not es_error:
            self.barra_total.configure(style="TotalOk.Horizontal.TProgressbar")
        if es_error:
            self.vacio.configure(text="♪\n\nAquí aparecerán las canciones")
        self.entrada.focus_set()
        self.entrada.select_range(0, "end")

    # ---------- refresco periódico (hilo de la interfaz) ----------
    def _refrescar(self) -> None:
        for f in self.filas:
            f.refrescar()
        if self.canciones:
            total = sum(c.progreso if c.estado != "Error" else 100 for c in self.canciones) / len(self.canciones)
            self.barra_total["value"] = total
            listas = sum(c.estado == "Listo" for c in self.canciones)
            self.lbl_total.configure(text=f"{listas}/{len(self.canciones)} · {int(total)} %")
        if self.mensaje_fase:
            self.lbl_estado.configure(text=self.mensaje_fase, fg=SUAVE)

    def _tic(self) -> None:
        if self.trabajando:
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
