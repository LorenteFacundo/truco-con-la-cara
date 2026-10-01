"""Menú de pausa manejado con la cara.

Girar la cabeza: moverse entre opciones · Levantar las cejas: elegir · Cerrar los ojos: volver.
Las opciones se muestran como un carrusel horizontal, así girar a la izquierda
muestra la opción que está a la izquierda.
"""

from dataclasses import dataclass, field
from typing import Callable

from PIL import ImageDraw

from ajustes import ACCIONES, ASIGNABLES, ESPERAS, GESTO_ELEGIR, GESTO_PAUSA, NOMBRE_ACCION, PUNTOS
from caras import NOMBRE_GESTO
from dibujo import DORADO, H, W, camara_con_gesto, escribir, flecha, fuente


@dataclass
class Opcion:
    id: object
    texto: str
    detalle: str = ""


@dataclass
class Pantalla:
    titulo: str
    opciones: list
    al_elegir: Callable
    i: int = 0
    nota: str = ""
    refrescar: Callable | None = field(default=None, repr=False)


class Menu:
    """Pila de pantallas. Cuando `salida` deja de ser None, el menú se cierra:
    "seguir", "prueba" (probar/calibrar gestos), "nuevo" (partido nuevo) o "salir"."""

    def __init__(self, ajustes):
        self.ajustes = ajustes
        self.pila = [self.principal()]
        self.salida = None

    # ------------------------------------------------------------ navegación
    def evento(self, ev):
        p = self.pila[-1]
        if ev == "izq":
            p.i = (p.i - 1) % len(p.opciones)
        elif ev == "der":
            p.i = (p.i + 1) % len(p.opciones)
        elif ev == "elegir":
            p.al_elegir(p.opciones[p.i].id)
        elif ev == "volver":
            self.volver()

    def volver(self):
        if len(self.pila) == 1:
            self.salida = "seguir"
            return
        self.pila.pop()
        p = self.pila[-1]
        if p.refrescar:
            self.pila[-1] = p.refrescar(p.i)

    def abrir(self, pantalla):
        self.pila.append(pantalla)

    # ------------------------------------------------------------ pantallas
    def principal(self, i=0):
        a = self.ajustes
        opciones = [
            Opcion("seguir", "Seguir jugando"),
            Opcion("espera", "Tiempo de gesto", f"{a.espera:.1f} s"),
            Opcion("asignar", "Gestos del juego", "qué gesto hace cada acción"),
            Opcion("prueba", "Probar / calibrar", "ver si te reconoce bien"),
            Opcion("puntos", "Partido a", f"{a.puntos} puntos"),
            Opcion("nuevo", "Nuevo partido"),
            Opcion("salir", "Salir del juego"),
        ]
        return Pantalla("Pausa", opciones, self._principal, i, refrescar=self.principal)

    def _principal(self, id):
        a = self.ajustes
        if id in ("seguir", "prueba"):
            self.salida = id
        elif id == "espera":
            ops = [Opcion(v, f"{v:.1f} s", "más rápido" if v < 0.5 else "más seguro" if v > 0.7 else "")
                   for v in ESPERAS]
            self.abrir(Pantalla("Tiempo de gesto", ops, self._espera, ESPERAS.index(a.espera),
                                "Cuánto hay que sostener un gesto para que cuente"))
        elif id == "puntos":
            ops = [Opcion(p, f"A {p} puntos") for p in PUNTOS]
            self.abrir(Pantalla("Largo del partido", ops, self._puntos, PUNTOS.index(a.puntos),
                                "Se aplica desde el próximo partido"))
        elif id == "asignar":
            self.abrir(self.acciones())
        elif id == "nuevo":
            self.abrir(self.confirmar("¿Empezar un partido nuevo?", "Sí, de nuevo", "nuevo"))
        elif id == "salir":
            self.abrir(self.confirmar("¿Salir del juego?", "Sí, salir", "salir"))

    def _espera(self, v):
        self.ajustes.espera = v
        self.ajustes.guardar()
        self.volver()

    def _puntos(self, p):
        self.ajustes.puntos = p
        self.ajustes.guardar()
        self.volver()

    def confirmar(self, titulo, si, salida):
        def elegir(ok):
            if ok:
                self.salida = salida
            else:
                self.volver()
        return Pantalla(titulo, [Opcion(False, "No, volver"), Opcion(True, si)], elegir)

    def acciones(self, i=0):
        ops = [Opcion(a, NOMBRE_ACCION[a], NOMBRE_GESTO[self.ajustes.acciones[a]]) for a in ACCIONES]
        ops.append(Opcion("listo", "Listo", "volver a la pausa"))
        return Pantalla("Gestos del juego", ops, self._accion, i,
                        "Elegí una acción para cambiarle el gesto", refrescar=self.acciones)

    def _accion(self, accion):
        if accion == "listo":
            self.volver()
            return
        actual = self.ajustes.acciones[accion]
        ops = []
        for g in ASIGNABLES:
            otra = self.ajustes.accion_de(g)
            detalle = "el actual" if g == actual else f"ahora: {NOMBRE_ACCION[otra]}" if otra else "libre"
            ops.append(Opcion(g, NOMBRE_GESTO[g], detalle))

        def elegir(g):
            self.ajustes.asignar(accion, g)
            self.ajustes.guardar()
            self.volver()

        nota = f"Gesto para «{NOMBRE_ACCION[accion]}» (si otra acción lo usaba, se intercambian)"
        self.abrir(Pantalla(NOMBRE_ACCION[accion], ops, elegir, ASIGNABLES.index(actual), nota))

    # ------------------------------------------------------------ dibujo
    def dibujar(self, img, cam, control):
        """Dibuja el menú encima de `img` (la pantalla del juego)."""
        d = ImageDraw.Draw(img, "RGBA")
        d.rectangle((0, 0, W, H), fill=(10, 12, 16, 220))
        p = self.pila[-1]
        cx, cy = W // 2, 290

        escribir(img, (cx, 50), p.titulo, font=fuente(40, True), fill=DORADO, anchor="mt")
        if p.nota:
            escribir(img, (cx, 112), p.nota, font=fuente(18), fill=(200, 200, 210), anchor="mt")

        n = len(p.opciones)
        if n > 1:
            for lado in (-1, 1):
                o = p.opciones[(p.i + lado) % n]
                x = cx + lado * 400
                d.rounded_rectangle((x - 150, cy - 55, x + 150, cy + 55), 16, fill=(45, 48, 56))
                escribir(img, (x, cy - (12 if o.detalle else 0)), o.texto, font=fuente(20, True),
                         fill=(150, 150, 160), anchor="mm")
                if o.detalle:
                    escribir(img, (x, cy + 20), o.detalle, font=fuente(14), fill=(115, 115, 125), anchor="mm")
                flecha(d, cx + lado * 585, cy, lado, 16, (140, 200, 255))

        o = p.opciones[p.i]
        d.rounded_rectangle((cx - 230, cy - 85, cx + 230, cy + 85), 22, fill=(62, 66, 78), outline=DORADO, width=3)
        escribir(img, (cx, cy - (18 if o.detalle else 0)), o.texto, font=fuente(32, True), fill=(255, 255, 255),
                 anchor="mm")
        if o.detalle:
            escribir(img, (cx, cy + 30), o.detalle, font=fuente(20), fill=DORADO, anchor="mm")

        x0 = cx - (n - 1) * 11
        for k in range(n):
            r = 6 if k == p.i else 4
            d.ellipse((x0 + k * 22 - r, cy + 118 - r, x0 + k * 22 + r, cy + 118 + r),
                      fill=DORADO if k == p.i else (90, 94, 104))

        ayudas = (("Girá la cabeza", "para moverte"),
                  (NOMBRE_GESTO[GESTO_ELEGIR], "para elegir"),
                  (NOMBRE_GESTO[GESTO_PAUSA], "para volver" if len(self.pila) > 1 else "para seguir jugando"))
        y = 470
        for gesto, que in ayudas:
            escribir(img, (cx - 10, y), gesto, font=fuente(19, True), fill=(140, 200, 255), anchor="ra")
            escribir(img, (cx + 10, y), que, font=fuente(19), fill=(225, 225, 230))
            y += 32
        escribir(img, (cx, y + 14), "Teclado: flechas para moverte  ·  Enter elegir  ·  Esc volver", font=fuente(14),
                 fill=(130, 130, 140), anchor="mt")

        camara_con_gesto(img, d, cam, control, W - 260, H - 200, 240, 180)
