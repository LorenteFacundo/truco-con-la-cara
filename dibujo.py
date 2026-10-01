"""Utilidades de dibujo compartidas (Pillow): fuentes, texto rápido, flechas y la cámara."""

from functools import lru_cache
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFont

from caras import NOMBRE_GESTO
from rutas import recurso

W, H = 1280, 720
FONDO_OSCURO = (24, 26, 32)
DORADO = (255, 215, 80)
FUENTES = (recurso("fuentes"), Path("/usr/share/fonts/google-noto"))


@lru_cache(maxsize=None)
def fuente(tam, negrita=False):
    nombre = "NotoSans-Bold.ttf" if negrita else "NotoSans-Regular.ttf"
    for carpeta in FUENTES:
        try:
            return ImageFont.truetype(str(carpeta / nombre), tam, layout_engine=ImageFont.Layout.BASIC)
        except OSError:
            pass
    return ImageFont.load_default(tam)


@lru_cache(maxsize=2048)
def _mascara(s, f, anchor):
    l, t, r, b = f.getbbox(s, anchor=anchor)
    m = Image.new("L", (max(1, r - l), max(1, b - t)))
    ImageDraw.Draw(m).text((-l, -t), s, font=f, fill=255, anchor=anchor)
    return m, l, t


def escribir(img, xy, s, font, fill, anchor="la"):
    """Como ImageDraw.text pero cacheando cada texto ya dibujado."""
    m, ox, oy = _mascara(s, font, anchor)
    x, y = int(xy[0] + ox), int(xy[1] + oy)
    img.paste(fill[:3], (x, y, x + m.width, y + m.height), m)


def flecha(d, cx, cy, sentido, t, color):
    """Triángulo apuntando a la izquierda (sentido=-1) o a la derecha (1)."""
    d.polygon([(cx + sentido * t, cy), (cx - sentido * t, cy - t), (cx - sentido * t, cy + t)], fill=color)


def pegar_camara(img, d, cam, x, y, w, h):
    if cam is not None:
        img.paste(Image.fromarray(cv2.cvtColor(cv2.resize(cam, (w, h)), cv2.COLOR_BGR2RGB)), (x, y))
    else:
        d.rectangle((x, y, x + w, y + h), fill=(50, 50, 55))
        escribir(img, (x + w // 2, y + h // 2), "No hay cámara", font=fuente(16), fill=(200, 200, 200), anchor="mm")


def camara_con_gesto(img, d, cam, control, x, y, w, h):
    """La cámara con una franja abajo que dice qué gesto se está cargando."""
    pegar_camara(img, d, cam, x, y, w, h)
    if control.gesto:
        d.rectangle((x, y + h - 30, x + w, y + h), fill=(0, 0, 0, 160))
        d.rectangle((x, y + h - 4, x + int(w * control.progreso), y + h), fill=DORADO)
        escribir(img, (x + 10, y + h - 15), NOMBRE_GESTO[control.gesto], font=fuente(16, True),
                 fill=(255, 255, 255), anchor="lm")
