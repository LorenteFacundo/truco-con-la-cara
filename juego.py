"""Truco con la cara: jugá al truco contra la compu usando gestos faciales.

La primera vez el juego aprende tus gestos (calibración, ~1 minuto). Gestos por defecto
(se pueden cambiar en el menú de pausa):
  Girar la cabeza        elegir carta
  Abrir la boca          tirar la carta elegida
  Levantar las cejas     Truco / Retruco / Vale cuatro
  Trompita (beso)        Envido
  Guiño izquierdo        Real envido
  Guiño derecho          Falta envido
  Sonreír                Quiero
  Fruncir el ceño        No quiero
  Inflar los cachetes    Me voy al mazo
  Cerrar los ojos        menú de pausa (girar la cabeza para moverte, cejas para elegir)

Teclado de respaldo: ← → / a d, espacio, t, e, r, f, s (quiero), n (no quiero), m (mazo),
Esc / p (pausa), q salir.
Uso: .venv/bin/python juego.py
"""

import argparse
import random
import time
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw

from ajustes import GESTO_ELEGIR, GESTO_PAUSA, TECLA_DE, TECLAS, Ajustes
from caras import (GESTOS, NOMBRE_GESTO, Calibracion, Calibrado, Control, Lector, cargar_clasificador,
                   guardar_calibracion, sonar)
from dibujo import (DORADO, FONDO_OSCURO, H, W, camara_con_gesto, escribir, flecha, fuente,
                    pegar_camara)
from menu import Menu
from truco import CPU, NOMBRE_ENVIDO, NOMBRE_TRUCO, NOMBRES, VOS, Compu, Mano

PANEL_X = 880

PAUSA_CPU = 1.3     # la compu "piensa" este tiempo antes de actuar
PAUSA_MANOS = 4.0   # segundos entre manos

# ---------------------------------------------------------------- dibujo de cartas
COLOR_PALO = {"espada": (40, 80, 170), "basto": (40, 120, 50), "oro": (200, 150, 20), "copa": (180, 40, 40)}
ESCALA = 3  # se dibuja grande y se achica para que quede suave


def _simbolo(d, palo, cx, cy, s):
    col = COLOR_PALO[palo]
    if palo == "oro":
        d.ellipse((cx - s, cy - s, cx + s, cy + s), fill=(235, 185, 40), outline=(150, 100, 10), width=s // 6)
        d.ellipse((cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2), outline=(170, 110, 10), width=s // 8)
    elif palo == "copa":
        d.chord((cx - s, cy - s * 1.1, cx + s, cy + s * 0.5), 0, 180, fill=col)
        d.rectangle((cx - s, cy - s * 0.35 - s * 0.1, cx + s, cy - s * 0.3), fill=col)
        d.rectangle((cx - s * 0.15, cy + s * 0.4, cx + s * 0.15, cy + s * 0.9), fill=col)
        d.ellipse((cx - s * 0.6, cy + s * 0.8, cx + s * 0.6, cy + s * 1.1), fill=col)
        d.ellipse((cx - s * 0.75, cy - s * 0.5, cx + s * 0.75, cy - s * 0.2), fill=(240, 200, 60))
    elif palo == "espada":
        d.polygon([(cx, cy - s * 1.4), (cx + s * 0.22, cy - s * 1.1), (cx + s * 0.22, cy + s * 0.5),
                   (cx - s * 0.22, cy + s * 0.5), (cx - s * 0.22, cy - s * 1.1)], fill=(150, 170, 200), outline=col)
        d.rectangle((cx - s * 0.75, cy + s * 0.45, cx + s * 0.75, cy + s * 0.65), fill=(230, 180, 40), outline=col)
        d.rectangle((cx - s * 0.14, cy + s * 0.65, cx + s * 0.14, cy + s * 1.2), fill=col)
        d.ellipse((cx - s * 0.25, cy + s * 1.15, cx + s * 0.25, cy + s * 1.45), fill=(230, 180, 40))
    else:  # basto
        d.polygon([(cx - s * 0.25, cy + s * 1.3), (cx + s * 0.25, cy + s * 1.3),
                   (cx + s * 0.55, cy - s * 1.1), (cx - s * 0.55, cy - s * 1.1)], fill=(130, 85, 40))
        d.ellipse((cx - s * 0.6, cy - s * 1.4, cx + s * 0.6, cy - s * 0.8), fill=(130, 85, 40))
        for dy in (-0.6, -0.1, 0.4):
            d.ellipse((cx - s * 0.5, cy + s * dy - s * 0.12, cx - s * 0.2, cy + s * dy + s * 0.12), fill=(70, 140, 60))
            d.ellipse((cx + s * 0.2, cy + s * (dy + 0.25) - s * 0.12, cx + s * 0.5, cy + s * (dy + 0.25) + s * 0.12),
                      fill=(70, 140, 60))


@lru_cache(maxsize=256)
def imagen_carta(carta, w, h):
    W2, H2 = w * ESCALA, h * ESCALA
    img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = 12 * ESCALA
    if carta is None:  # dorso
        d.rounded_rectangle((0, 0, W2 - 1, H2 - 1), r, fill=(120, 25, 35), outline=(250, 240, 220), width=4 * ESCALA)
        m = 10 * ESCALA
        d.rounded_rectangle((m, m, W2 - m, H2 - m), r // 2, outline=(220, 170, 80), width=2 * ESCALA)
        for i in range(-H2, W2, 14 * ESCALA):
            d.line((m + i, m, m + i + H2, m + H2), fill=(150, 40, 50), width=3 * ESCALA)
        d.rounded_rectangle((0, 0, W2 - 1, H2 - 1), r, outline=(250, 240, 220), width=4 * ESCALA)
        d.ellipse((W2 / 2 - 14 * ESCALA, H2 / 2 - 14 * ESCALA, W2 / 2 + 14 * ESCALA, H2 / 2 + 14 * ESCALA),
                  fill=(220, 170, 80))
    else:
        col = COLOR_PALO[carta.palo]
        d.rounded_rectangle((0, 0, W2 - 1, H2 - 1), r, fill=(252, 248, 236), outline=(60, 60, 60), width=2 * ESCALA)
        d.rounded_rectangle((5 * ESCALA, 5 * ESCALA, W2 - 5 * ESCALA, H2 - 5 * ESCALA), r // 2, outline=col,
                            width=2 * ESCALA)
        f = fuente(int(h * 0.2) * ESCALA, True)
        d.text((10 * ESCALA, 6 * ESCALA), str(carta.numero), font=f, fill=col)
        d.text((W2 - 10 * ESCALA, H2 - 4 * ESCALA), str(carta.numero), font=f, fill=col, anchor="rd")
        _simbolo(d, carta.palo, W2 / 2, H2 / 2, int(min(w, h) * 0.22) * ESCALA)
    return img.resize((w, h), Image.LANCZOS)


@lru_cache(maxsize=1)
def fondo():
    """Paño verde con viñeta suave + panel lateral (se calcula una sola vez)."""
    yy, xx = np.mgrid[0:H, 0:PANEL_X].astype(np.float32)
    dist = np.sqrt(((xx - PANEL_X / 2) / (PANEL_X / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    luz = np.clip(1.15 - 0.45 * dist ** 2, 0.55, 1.15)[..., None]
    pano = np.clip(np.array([20, 95, 55], np.float32) * luz, 0, 255).astype(np.uint8)
    arr = np.empty((H, W, 3), np.uint8)
    arr[:, :PANEL_X] = pano
    arr[:, PANEL_X:] = (28, 30, 36)
    return Image.fromarray(arr)


# ---------------------------------------------------------------- juego
class Juego:
    def __init__(self, ajustes):
        self.ajustes = ajustes
        self.compu = Compu()
        self.nuevo_partido()

    def nuevo_partido(self):
        self.meta = self.ajustes.puntos
        self.puntaje = [0, 0]
        self.mano_de = random.choice((VOS, CPU))
        self.log = [f"Partido a {self.meta} puntos. ¡Suerte!"]
        self.nueva_mano()

    def nueva_mano(self):
        self.m = Mano.repartir(self.mano_de, self.puntaje, self.meta)
        self.mano_de = 1 - self.mano_de
        self.sel = 0
        self.t_accion = time.monotonic()
        self.t_fin = None
        self.burbujas = {}
        self.log.append(f"— Nueva mano. Es mano: {NOMBRES[self.m.mano]}")

    def reanudar(self, pausado):
        """Corre los relojes lo que duró la pausa, así la compu no juega apenas volvés."""
        self.t_accion += pausado
        if self.t_fin is not None:
            self.t_fin += pausado
        self.burbujas = {j: (txt, t + pausado) for j, (txt, t) in self.burbujas.items()}

    @property
    def partido_terminado(self):
        return max(self.puntaje) >= self.meta

    def consumir_eventos(self, ahora):
        for j, texto in self.m.eventos:
            if j is not None:
                self.burbujas[j] = (texto, ahora)
                self.log.append(f"{NOMBRES[j]}: {texto}")
            else:
                self.log.append(texto)
        self.m.eventos.clear()
        self.log = self.log[-8:]

    def accion_humano(self, accion, ahora):
        m = self.m
        if m.terminada:
            return
        if accion in ("izq", "der"):
            if m.cartas[VOS]:
                self.sel = (self.sel + (1 if accion == "der" else -1)) % len(m.cartas[VOS])
            return
        carta = None
        if accion == "jugar":
            if not m.cartas[VOS]:
                return
            self.sel = min(self.sel, len(m.cartas[VOS]) - 1)
            carta = m.cartas[VOS][self.sel]
        if m.hacer(VOS, accion, carta):
            self.t_accion = ahora
            if m.cartas[VOS]:
                self.sel = min(self.sel, len(m.cartas[VOS]) - 1)

    def paso(self, ahora):
        m = self.m
        if m.terminada:
            if self.t_fin is None:
                self.t_fin = ahora
            elif not self.partido_terminado and ahora - self.t_fin > PAUSA_MANOS:
                self.nueva_mano()
        elif m.quien_actua() == CPU and ahora - self.t_accion > PAUSA_CPU:
            accion, carta = self.compu.decidir(m)
            m.hacer(CPU, accion, carta)
            self.t_accion = ahora
        self.consumir_eventos(ahora)

    # ------------------------------------------------------------ dibujo
    def acciones_visibles(self):
        m = self.m
        acc = m.acciones(VOS)
        filas = []
        for a in acc:
            if a == "jugar":
                etiqueta = "Tirar la carta elegida"
            elif a == "truco":
                etiqueta = ("Quiero " if m.pendiente else "") + NOMBRE_TRUCO[m.proximo_truco()]
            elif a in NOMBRE_ENVIDO:
                etiqueta = NOMBRE_ENVIDO[a]
            else:
                etiqueta = {"quiero": "Quiero", "no_quiero": "No quiero", "mazo": "Irse al mazo"}[a]
            filas.append((a, etiqueta))
        return filas

    def dibujar(self, cam, control, ahora):
        img = fondo().copy()
        d = ImageDraw.Draw(img, "RGBA")
        m = self.m

        # info de la mano
        escribir(img, (24, 18), f"Es mano: {NOMBRES[m.mano]}", font=fuente(18), fill=(220, 240, 220))
        vale = NOMBRE_TRUCO.get(m.truco, "Sin truco")
        escribir(img, (24, 42), f"La mano vale {m.truco} ({vale})", font=fuente(18), fill=(220, 240, 220))

        # cartas de la compu
        n = len(m.cartas[CPU])
        for i, c in enumerate(m.cartas[CPU]):
            x = 440 - (n * 115) // 2 + i * 115 + 7
            img.paste(imagen_carta(c if m.terminada else None, 100, 150), (x, 20),
                      imagen_carta(c if m.terminada else None, 100, 150))

        # bazas jugadas
        for r, baza in enumerate(m.jugadas):
            cx = 260 + r * 180
            res = m.resultados[r] if r < len(m.resultados) else "?"
            for j, y in ((CPU, 195), (VOS, 290)):
                c = baza[j]
                if c is None:
                    continue
                ci = imagen_carta(c, 90, 135)
                img.paste(ci, (cx - 45, y), ci)
                if res != "?" and res is not None and res != j:
                    d.rounded_rectangle((cx - 45, y, cx + 45, y + 135), 12, fill=(0, 0, 0, 110))
            if res != "?":
                txt = "parda" if res is None else f"gana {NOMBRES[res]}"
                escribir(img, (cx, 438), txt, font=fuente(15, True), fill=(255, 230, 120), anchor="mt")

        # mis cartas
        n = len(m.cartas[VOS])
        mi_turno_jugar = "jugar" in m.acciones(VOS)
        for i, c in enumerate(m.cartas[VOS]):
            x = 440 - (n * 125) // 2 + i * 125 + 7
            y = 535
            if i == self.sel and mi_turno_jugar:
                y -= 28
                d.rounded_rectangle((x - 6, y - 6, x + 116, y + 171), 16, fill=(255, 215, 80, 200))
            ci = imagen_carta(c, 110, 165)
            img.paste(ci, (x, y), ci)

        # burbujas de diálogo
        for j, (bx, by) in ((CPU, (640, 50)), (VOS, (640, 480))):
            if j in self.burbujas:
                texto, t = self.burbujas[j]
                if ahora - t < 2.8:
                    f = fuente(26, True)
                    tw = d.textlength(texto, font=f)
                    bx = min(bx, PANEL_X - 16 - int(tw) - 36)  # que no se meta en el panel
                    d.rounded_rectangle((bx, by, bx + tw + 36, by + 54), 18, fill=(255, 255, 255, 235),
                                        outline=(30, 30, 30), width=2)
                    escribir(img, (bx + 18, by + 27), texto, font=f, fill=(25, 25, 25), anchor="lm")

        # cartel central
        cartel = None
        if self.partido_terminado:
            cartel = ("¡GANASTE EL PARTIDO!" if self.puntaje[VOS] >= self.meta else "Ganó la CPU…",
                      f"{NOMBRE_GESTO[self.ajustes.acciones['quiero']]} (o espacio) para jugar otra")
        elif m.terminada:
            g = m.ganador
            cartel = ("Ganaste la mano" if g == VOS else "La CPU ganó la mano", "Repartiendo…")
        elif m.quien_actua() == CPU:
            escribir(img, (440, 468), "La CPU está pensando…", font=fuente(17), fill=(230, 230, 200), anchor="mm")
        if cartel:
            d.rounded_rectangle((170, 300, 710, 420), 24, fill=(0, 0, 0, 190))
            escribir(img, (440, 340), cartel[0], font=fuente(34, True), fill=(255, 220, 90), anchor="mm")
            escribir(img, (440, 390), cartel[1], font=fuente(18), fill=(230, 230, 230), anchor="mm")

        self.dibujar_panel(img, d, cam, control, ahora)
        return img

    def dibujar_panel(self, img, d, cam, control, ahora):
        x0 = PANEL_X
        # puntaje
        for k, (j, col) in enumerate(((VOS, (110, 210, 130)), (CPU, (230, 120, 110)))):
            y = 16 + k * 30
            escribir(img, (x0 + 16, y), NOMBRES[j], font=fuente(20, True), fill=col)
            d.rounded_rectangle((x0 + 80, y + 6, x0 + 330, y + 22), 6, fill=(55, 58, 66))
            ancho = int(250 * self.puntaje[j] / self.meta)
            if ancho > 0:
                d.rounded_rectangle((x0 + 80, y + 6, x0 + 80 + ancho, y + 22), 6, fill=col)
            escribir(img, (x0 + 345, y), str(self.puntaje[j]), font=fuente(20, True), fill=(240, 240, 240))
        escribir(img, (W - 16, 78), f"a {self.meta}", font=fuente(13), fill=(150, 150, 160), anchor="rt")
        escribir(img, (x0 + 16, 78), f"Pausa: {NOMBRE_GESTO[GESTO_PAUSA].lower()} o Esc", font=fuente(13),
                 fill=(150, 150, 160))

        # cámara
        cx, cy, cw, ch = x0 + 40, 100, 320, 240
        camara_con_gesto(img, d, cam, control, cx, cy, cw, ch)

        # acciones disponibles
        y = cy + ch + 12
        filas = self.acciones_visibles()
        if self.partido_terminado:
            filas = []
            revancha = f"{NOMBRE_GESTO[self.ajustes.acciones['quiero']]} o espacio: revancha"
            escribir(img, (x0 + 16, y), revancha, font=fuente(15), fill=(220, 220, 220))
        elif not filas:
            escribir(img, (x0 + 16, y), "Esperando a la CPU…" if not self.m.terminada else "Fin de la mano",
                   font=fuente(16), fill=(170, 170, 180))
        else:
            escribir(img, (x0 + 16, y), "Lo que podés hacer:", font=fuente(14), fill=(160, 160, 170))
            y += 22
            if any(a == "jugar" for a, _ in filas):
                escribir(img, (x0 + 16, y), "Girar la cabeza", font=fuente(15, True), fill=(140, 200, 255))
                flecha(d, x0 + 150, y + 10, -1, 7, (140, 200, 255))
                flecha(d, x0 + 172, y + 10, 1, 7, (140, 200, 255))
                escribir(img, (x0 + 220, y), "elegir carta", font=fuente(15), fill=(220, 220, 220))
                y += 24
            for a, etiqueta in filas:
                gesto = self.ajustes.acciones[a]
                activo = control.gesto == gesto
                if activo:
                    d.rounded_rectangle((x0 + 10, y - 2, W - 10, y + 22), 6, fill=(80, 70, 30))
                    d.rounded_rectangle((x0 + 10, y - 2, x0 + 10 + int((W - x0 - 20) * control.progreso), y + 22),
                                        6, fill=(150, 120, 30))
                escribir(img, (x0 + 16, y), NOMBRE_GESTO[gesto], font=fuente(15, True), fill=(255, 215, 80))
                escribir(img, (x0 + 170, y), etiqueta, font=fuente(15), fill=(235, 235, 235))
                escribir(img, (W - 16, y + 2), f"[{TECLA_DE[a]}]", font=fuente(12), fill=(130, 130, 140), anchor="rt")
                y += 25

        # registro
        y = H - 5 * 19 - 8
        d.line((x0 + 16, y - 8, W - 16, y - 8), fill=(60, 62, 70), width=1)
        for linea in self.log[-5:]:
            escribir(img, (x0 + 16, y), linea, font=fuente(13), fill=(180, 180, 190))
            y += 19


# ---------------------------------------------------------------- pantallas de gestos
def a_bgr(img):
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def dibujar_calibracion(cal, cam, lectura, ahora):
    img = Image.new("RGB", (W, H), FONDO_OSCURO)
    d = ImageDraw.Draw(img, "RGBA")
    cx = W // 2
    camx, camy, camw, camh = cx - 320, 160, 640, 480

    if cal.fase == "intro":
        if cal.motivo == "nuevos":
            titulo = "Hay gestos nuevos para aprender"
            lineas = ("Ahora podés levantar cada ceja por separado y cerrar los ojos para pausar.",
                      f"Volvemos a calibrar todo: {len(cal.pasos)} caras de unos 2 segundos (alrededor de un minuto).",
                      "Hacé cada gesto como lo vas a hacer jugando y mantenelo mientras corre la barra roja.")
        else:
            titulo = "Vamos a aprender tus gestos"
            lineas = (f"Te voy a pedir {len(cal.pasos)} caras de unos 2 segundos cada una (alrededor de un minuto).",
                      "Hacé cada gesto como lo vas a hacer jugando: claro, pero sin exagerar.",
                      "Mantenelo mientras corre la barra roja. Suena un aviso al terminar cada uno.")
        escribir(img, (cx, 22), titulo, font=fuente(36, True), fill=DORADO, anchor="mt")
        for i, linea in enumerate(lineas):
            escribir(img, (cx, 80 + i * 24), linea, font=fuente(18), fill=(225, 225, 230), anchor="mt")
        pie = "Espacio: empezar   ·   S: saltar   ·   Q: salir"
    else:
        _, instruccion, _ = cal.paso
        escribir(img, (cx, 18), f"Paso {cal.i + 1} de {len(cal.pasos)}", font=fuente(16), fill=(160, 160, 170),
                 anchor="mt")
        escribir(img, (cx, 46), instruccion, font=fuente(36, True), fill=(255, 255, 255), anchor="mt")
        grabando = cal.fase == "grabar"
        estado = "Grabando: mantené el gesto" if grabando else "Preparate…"
        color = (255, 90, 90) if grabando else DORADO
        escribir(img, (cx, 108), estado, font=fuente(20, True), fill=color, anchor="mt")
        if grabando:
            px = cx - d.textlength(estado, font=fuente(20, True)) / 2 - 18
            d.ellipse((px - 7, 116, px + 7, 130), fill=color)
        pie = "Esc: cancelar"

    pegar_camara(img, d, cam, camx, camy, camw, camh)
    if lectura is not None and not lectura["cara"]:
        d.rectangle((camx, camy + camh // 2 - 30, camx + camw, camy + camh // 2 + 30), fill=(150, 30, 30, 200))
        escribir(img, (cx, camy + camh // 2), "No veo tu cara: acercate o poné más luz", font=fuente(22, True),
                 fill=(255, 255, 255), anchor="mm")
    if cal.fase != "intro":
        p = cal.progreso(ahora)
        color = (230, 70, 70) if cal.fase == "grabar" else DORADO
        d.rounded_rectangle((camx, camy + camh + 10, camx + camw, camy + camh + 24), 7, fill=(55, 58, 66))
        d.rounded_rectangle((camx, camy + camh + 10, camx + max(14, int(camw * p)), camy + camh + 24), 7, fill=color)
    escribir(img, (cx, H - 22), pie, font=fuente(16), fill=(170, 170, 180), anchor="mm")
    return img


def dibujar_prueba(clf, control, puntajes, cam, flash, sel, ahora):
    img = Image.new("RGB", (W, H), FONDO_OSCURO)
    d = ImageDraw.Draw(img, "RGBA")
    escribir(img, (40, 22), "Probá tus gestos", font=fuente(32, True), fill=DORADO)
    if clf.calibrado:
        sub = (f"Cada gesto se pone verde cuando lo mantenés {control.espera:.1f} s. "
               "Girá la cabeza para ver las flechas.")
    else:
        sub = "Sin calibrar: detección automática. Apretá C para calibrar (recomendado)."
    escribir(img, (40, 72), sub, font=fuente(16), fill=(200, 200, 210))

    camx, camy = 40, 116
    pegar_camara(img, d, cam, camx, camy, 640, 480)
    if flash and flash[0] in ("izq", "der") and ahora - flash[1] < 0.8:
        fx = camx + 50 if flash[0] == "izq" else camx + 590
        d.ellipse((fx - 38, camy + 202, fx + 38, camy + 278), fill=(0, 0, 0, 150))
        flecha(d, fx, camy + 240, -1 if flash[0] == "izq" else 1, 22, (140, 200, 255))

    x, y = 712, 116
    for n, g in enumerate(GESTOS):
        disparado = flash and flash[0] == g and ahora - flash[1] < 1.0
        d.rounded_rectangle((x, y, W - 40, y + 40), 9, fill=(40, 120, 65) if disparado else (40, 44, 52))
        if control.gesto == g and not disparado:
            d.rounded_rectangle((x, y, x + int((W - 40 - x) * control.progreso), y + 40), 9, fill=(110, 95, 35))
        if n == sel:
            d.rounded_rectangle((x - 2, y - 2, W - 38, y + 42), 10, outline=DORADO, width=2)
        escribir(img, (x + 14, y + 3), NOMBRE_GESTO[g], font=fuente(17, True), fill=(255, 255, 255))
        p = puntajes.get(g, 0.0)
        d.rounded_rectangle((x + 14, y + 29, x + 194, y + 34), 2, fill=(65, 68, 78))
        if p > 0.02:
            d.rounded_rectangle((x + 14, y + 29, x + 14 + int(180 * p), y + 34), 2, fill=DORADO)
        if g in clf.faltantes:
            escribir(img, (W - 54, y + 20), "sin grabar: elegilo y apretá R", font=fuente(14, True),
                     fill=(240, 170, 70), anchor="rm")
        elif clf.calibrado and g in clf.calidad:
            acierto, confusion = clf.calidad[g]
            color = (110, 210, 130) if acierto >= 0.85 else (240, 170, 70) if acierto >= 0.6 else (240, 90, 90)
            txt = f"{acierto:.0%}"
            if acierto < 0.85 and confusion:
                txt = f"se confunde con «{NOMBRE_GESTO[confusion].lower()}»  {txt}"
            escribir(img, (W - 54, y + 20), txt, font=fuente(14, True), fill=color, anchor="rm")
        y += 44

    if clf.calibrado and "neutro" in clf.calidad:
        acierto, confusion = clf.calidad["neutro"]
        if acierto >= 0.9 or not confusion:
            txt, color = "Cara normal: bien reconocida", (110, 210, 130)
        else:
            txt, color = f"Ojo: tu cara normal a veces parece «{NOMBRE_GESTO[confusion].lower()}»", (240, 170, 70)
        escribir(img, (x, y + 4), txt, font=fuente(15, True), fill=color)
    escribir(img, (x, y + 30), "Los % dicen qué tan bien distingo cada gesto.", font=fuente(14), fill=(160, 160, 170))

    pie = "Espacio: volver al juego   ·   flechas: elegir gesto   ·   R: regrabarlo   ·   C: calibrar todo   ·   Q: salir"
    escribir(img, (W // 2, H - 22), pie, font=fuente(16, True), fill=(220, 220, 230), anchor="mm")
    return img


IZQ, DER, ARRIBA, ABAJO = (65361, 81, ord("a")), (65363, 83, ord("d")), (65362, 82), (65364, 84)


def diagnostico(camara):
    """Revisa que todo esté en su lugar sin abrir la ventana (útil si el juego no arranca)."""
    from rutas import carpeta_datos

    print("Truco con la cara: diagnóstico")
    print(f"  datos del jugador: {carpeta_datos()}")
    print(f"  fuente: {getattr(fuente(20), 'path', 'la de Pillow (sin acentos lindos)')}")
    lector = Lector(camara)
    print("  modelo de MediaPipe: cargado")
    cam = lectura = None
    for _ in range(15):
        cam, lectura = lector.leer()
    if cam is None:
        print(f"  cámara {camara}: no disponible (se puede jugar con el teclado)")
    else:
        cara = "sí" if lectura and lectura["cara"] else "no (¿estás frente a la cámara?)"
        print(f"  cámara {camara}: ok, {cam.shape[1]}x{cam.shape[0]}; cara detectada: {cara}")
    clf = cargar_clasificador()
    print(f"  calibración: {'sí' if clf.calibrado else 'todavía no'}")
    ajustes, control = Ajustes.cargar(), Control()
    juego = Juego(ajustes)
    Menu(ajustes).dibujar(juego.dibujar(cam, control, 0.0), cam, control)
    dibujar_prueba(clf, control, {}, cam, None, 0, 0.0)
    dibujar_calibracion(Calibracion(), cam, lectura, 0.0)
    print("  pantallas: ok")
    lector.cerrar()
    print("Todo listo para jugar.")


def main():
    ap = argparse.ArgumentParser(description="Truco con gestos de la cara")
    ap.add_argument("--camara", type=int, default=0, help="número de cámara si tenés más de una")
    ap.add_argument("--diagnostico", action="store_true", help="revisar que todo funcione, sin abrir el juego")
    args = ap.parse_args()
    if args.diagnostico:
        diagnostico(args.camara)
        return

    ajustes = Ajustes.cargar()
    lector = Lector(args.camara)
    clf = cargar_clasificador()
    control = Control(ajustes.espera)
    juego = Juego(ajustes)
    ventana = "Truco con la cara"
    cv2.namedWindow(ventana, cv2.WINDOW_AUTOSIZE)

    cal = menu = flash = None
    sel = 0
    t_pausa = None
    mostrada = False
    if lector.ok and not clf.calibrado:
        modo, cal = "calibrar", Calibracion()
    elif lector.ok and clf.faltantes:
        modo, cal = "calibrar", Calibracion(motivo="nuevos")
    else:
        modo = "juego"
    if modo != "juego":
        t_pausa = time.monotonic()

    try:
        while True:
            ahora = time.monotonic()
            cam, lectura = lector.leer()
            cara = bool(lectura and lectura["cara"])
            gesto, puntajes = clf.predecir(lectura["b"]) if cara else (None, {})
            giro = lectura["giro"] - clf.giro_centro if cara else None
            control.espera = ajustes.espera

            tecla = cv2.waitKeyEx(1)
            letra = chr(tecla) if 0 <= tecla < 256 else ""
            # Se mira antes de volver a mostrar la imagen: si no, imshow reabre la ventana cerrada con la ✕.
            if letra == "q" or (mostrada and cv2.getWindowProperty(ventana, cv2.WND_PROP_VISIBLE) < 1):
                break
            anterior = modo

            if modo == "calibrar":
                if tecla == 27:
                    modo = "prueba"
                elif cal.fase == "intro" and letra == " ":
                    cal.empezar()
                elif cal.fase == "intro" and letra == "s":
                    modo = "prueba"
                cal.actualizar(lectura, ahora)
                if cal.terminada:
                    datos = cal.resultado(clf.datos if clf.calibrado else None)
                    guardar_calibracion(datos)
                    clf = Calibrado(datos)
                    modo = "prueba"
                imagen = dibujar_calibracion(cal, cam, lectura, ahora)

            elif modo == "prueba":
                for ev in control.actualizar(gesto, giro, ahora):
                    flash = (ev, ahora)
                if letra in (" ", "\r") or tecla == 27:
                    modo = "juego"
                elif tecla in ARRIBA:
                    sel = (sel - 1) % len(GESTOS)
                elif tecla in ABAJO:
                    sel = (sel + 1) % len(GESTOS)
                elif letra == "c" and lector.ok:
                    modo, cal = "calibrar", Calibracion()
                elif letra == "r" and lector.ok:
                    solo = [GESTOS[sel]] if clf.calibrado else None
                    modo, cal = "calibrar", Calibracion(solo=solo, intro=solo is None)
                imagen = dibujar_prueba(clf, control, puntajes, cam, flash, sel, ahora)

            elif modo == "menu":
                for ev in control.actualizar(gesto, giro, ahora):
                    if ev in ("izq", "der"):
                        menu.evento(ev)
                    elif ev == GESTO_ELEGIR:
                        menu.evento("elegir")
                    elif ev == GESTO_PAUSA:
                        menu.evento("volver")
                if tecla in IZQ:
                    menu.evento("izq")
                elif tecla in DER:
                    menu.evento("der")
                elif letra in (" ", "\r"):
                    menu.evento("elegir")
                elif tecla == 27 or letra == "p":
                    menu.evento("volver")
                if menu.salida == "salir":
                    break
                if menu.salida == "nuevo":
                    juego.nuevo_partido()
                if menu.salida:
                    modo = "prueba" if menu.salida == "prueba" else "juego"
                imagen = juego.dibujar(cam, control, ahora)
                menu.dibujar(imagen, cam, control)

            else:  # juego
                acciones = []
                for ev in control.actualizar(gesto, giro, ahora):
                    if ev == GESTO_PAUSA:
                        modo = "menu"
                    elif ev in ("izq", "der"):
                        acciones.append(ev)
                    elif ajustes.accion_de(ev):
                        acciones.append(ajustes.accion_de(ev))
                if tecla == 27 or letra == "p":
                    modo = "menu"
                elif tecla in IZQ:
                    acciones.append("izq")
                elif tecla in DER:
                    acciones.append("der")
                elif tecla in TECLAS:
                    acciones.append(TECLAS[tecla])

                if modo == "menu":
                    menu = Menu(ajustes)
                    sonar("bell")
                else:
                    for accion in acciones:
                        if juego.partido_terminado:
                            if accion in ("quiero", "jugar"):
                                juego.nuevo_partido()
                        else:
                            juego.accion_humano(accion, ahora)
                    juego.paso(ahora)
                imagen = juego.dibujar(cam, control, ahora)

            if modo != anterior:
                control.limpiar()
                flash = None
                if anterior == "juego":
                    t_pausa = ahora
                elif modo == "juego" and t_pausa is not None:
                    juego.reanudar(ahora - t_pausa)
                    t_pausa = None

            cv2.imshow(ventana, a_bgr(imagen))
            mostrada = True
    finally:
        lector.cerrar()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
