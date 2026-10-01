"""Gestos de la cara: webcam + MediaPipe, calibración personal y control por gestos sostenidos.

En vez de umbrales fijos, se graba cómo hace cada gesto la persona que juega
(los 52 "blendshapes" de MediaPipe) y se reconoce con vecinos más cercanos (kNN).
"""

import json
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from rutas import dato, recurso

MODELO = recurso("face_landmarker.task")
ARCHIVO_CALIBRACION = dato("calibracion.json")

GESTOS = ("sonrisa", "boca", "cejas", "ceja_izq", "ceja_der", "ceño", "beso", "cachetes",
          "guiño_izq", "guiño_der", "ojos")
NOMBRE_GESTO = {
    "sonrisa": "Sonreír", "boca": "Abrir la boca", "beso": "Trompita",
    "cejas": "Levantar cejas", "ceja_izq": "Ceja izquierda", "ceja_der": "Ceja derecha",
    "ceño": "Fruncir el ceño", "cachetes": "Inflar cachetes",
    "guiño_izq": "Guiño izquierdo", "guiño_der": "Guiño derecho", "ojos": "Cerrar los ojos",
    "neutro": "Cara normal",
}
# Hacia dónde mirás cambia al recorrer la pantalla con la vista: no sirve para gestos.
IGNORAR = {"_neutral", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight",
           "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight"}
GIRO_ON, GIRO_OFF = 0.10, 0.05

SONIDOS = Path("/usr/share/sounds/freedesktop/stereo")
_REPRODUCTOR = shutil.which("paplay") or shutil.which("pw-play")


def sonar(nombre):
    """Reproduce un sonido del sistema sin frenar el juego (si no se puede, no pasa nada)."""
    if sys.platform == "win32":
        import winsound
        winsound.MessageBeep()
        return
    archivo = SONIDOS / f"{nombre}.oga"
    if _REPRODUCTOR and archivo.exists():
        subprocess.Popen([_REPRODUCTOR, str(archivo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Lector:
    """Lee la webcam y devuelve los blendshapes de la cara y el giro de la cabeza."""

    def __init__(self, camara=0):
        if sys.platform.startswith("linux"):
            backend = cv2.CAP_V4L2
        elif sys.platform == "win32":
            backend = cv2.CAP_DSHOW   # abre mucho más rápido que el predeterminado en Windows
        else:
            backend = cv2.CAP_ANY
        self.cap = cv2.VideoCapture(camara, backend)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.ok = self.cap.isOpened()
        opciones = vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(MODELO)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
        )
        self.detector = vision.FaceLandmarker.create_from_options(opciones)
        self.t0 = time.monotonic()
        self.ultimo_ts = -1

    def leer(self):
        """Devuelve (frame, lectura). lectura = {"cara": bool, "b": blendshapes, "giro": float}."""
        if not self.ok:
            return None, None
        ok, frame = self.cap.read()
        if not ok:
            return None, None
        frame = cv2.flip(frame, 1)
        ts = max(self.ultimo_ts + 1, int((time.monotonic() - self.t0) * 1000))
        self.ultimo_ts = ts
        imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        res = self.detector.detect_for_video(imagen, ts)
        if not res.face_landmarks:
            return frame, {"cara": False}

        puntos = res.face_landmarks[0]
        h, w = frame.shape[:2]
        for i in (1, 33, 263, 61, 291, 10, 152, 234, 454):
            cv2.circle(frame, (int(puntos[i].x * w), int(puntos[i].y * h)), 3, (0, 220, 255), -1)

        # Giro: posición de la nariz respecto al centro de la cara (imagen espejada).
        izq, der, nariz = puntos[234].x, puntos[454].x, puntos[1].x
        giro = (nariz - (izq + der) / 2) / max(abs(der - izq), 1e-6)
        b = {c.category_name: c.score for c in res.face_blendshapes[0]}
        return frame, {"cara": True, "b": b, "giro": giro}

    def cerrar(self):
        self.detector.close()
        self.cap.release()


# ---------------------------------------------------------------- clasificadores
class PorUmbrales:
    """Detección sin calibrar: umbrales fijos, en orden de prioridad."""

    calibrado = False
    giro_centro = 0.0
    calidad = {}
    faltantes = ()
    REGLAS = (
        ("ojos", lambda b: min(b["eyeBlinkLeft"], b["eyeBlinkRight"]), 0.5),
        ("guiño_izq", lambda b: b["eyeBlinkLeft"] - b["eyeBlinkRight"], 0.2),
        ("guiño_der", lambda b: b["eyeBlinkRight"] - b["eyeBlinkLeft"], 0.2),
        ("cachetes", lambda b: b["cheekPuff"], 0.15),
        ("boca", lambda b: b["jawOpen"], 0.3),
        ("beso", lambda b: b["mouthPucker"], 0.5),
        ("sonrisa", lambda b: (b["mouthSmileLeft"] + b["mouthSmileRight"]) / 2, 0.45),
        ("ceño", lambda b: (b["browDownLeft"] + b["browDownRight"]) / 2, 0.35),
        ("ceja_izq", lambda b: b["browOuterUpLeft"] - b["browOuterUpRight"], 0.25),
        ("ceja_der", lambda b: b["browOuterUpRight"] - b["browOuterUpLeft"], 0.25),
        ("cejas", lambda b: b["browInnerUp"], 0.45),
    )

    def predecir(self, b):
        valores = {g: f(b) / u for g, f, u in self.REGLAS}
        puntajes = {g: min(1.0, max(0.0, v)) for g, v in valores.items()}
        for g, _, _ in self.REGLAS:
            if valores[g] >= 1.0:
                return g, puntajes
        return None, puntajes


K = 7          # vecinos que votan
MINIMO = 0.6   # parte de los votos que necesita un gesto para ganarle a la cara normal


def _matriz(pasos, escala):
    filas = [(v, p["clase"]) for p in pasos for v in p["vectores"]]
    X = np.array([f for f, _ in filas], np.float32) / escala
    y = np.array([c for _, c in filas])
    return X, y


def _escala(pasos):
    """Cada rasgo se divide por cuánto varía en la calibración (así pesan parecido)."""
    X = np.concatenate([np.array(p["vectores"], np.float32) for p in pasos])
    return X.std(0) + 0.02


def _votar(X, y, Q):
    """kNN con votos pesados por distancia. Devuelve una lista de {clase: proporción}."""
    d2 = (Q ** 2).sum(1)[:, None] + (X ** 2).sum(1)[None, :] - 2 * Q @ X.T
    d = np.sqrt(np.maximum(d2, 0))
    k = min(K, len(X))
    idx = np.argpartition(d, k - 1, axis=1)[:, :k]
    salida = []
    for fila, ids in zip(d, idx):
        votos = {}
        for c, peso in zip(y[ids], 1.0 / (fila[ids] + 0.05)):
            votos[c] = votos.get(c, 0.0) + peso
        total = sum(votos.values())
        salida.append({c: v / total for c, v in votos.items()})
    return salida


def _elegir(votos):
    c = max(votos, key=votos.get)
    return c if c != "neutro" and votos[c] >= MINIMO else None


def evaluar(pasos):
    """Parte cada grabación a la mitad, entrena con una mitad y prueba con la otra.
    Devuelve {clase: (acierto 0..1, con qué se confunde más o None)}."""
    escala = _escala(pasos)
    mitades = ([], [])
    for p in pasos:
        m = len(p["vectores"]) // 2
        mitades[0].append({"clase": p["clase"], "vectores": p["vectores"][:m]})
        mitades[1].append({"clase": p["clase"], "vectores": p["vectores"][m:]})
    predicciones = {}
    for entrena, prueba in ((mitades[0], mitades[1]), (mitades[1], mitades[0])):
        X, y = _matriz(entrena, escala)
        for p in prueba:
            if not p["vectores"]:
                continue
            Q = np.array(p["vectores"], np.float32) / escala
            predicciones.setdefault(p["clase"], []).extend(
                _elegir(v) or "neutro" for v in _votar(X, y, Q))
    calidad = {}
    for c, preds in predicciones.items():
        otros = [p for p in preds if p != c]
        calidad[c] = (1 - len(otros) / len(preds), max(set(otros), key=otros.count) if otros else None)
    return calidad


class Calibrado:
    """Reconoce los gestos comparando con las grabaciones de la calibración."""

    calibrado = True

    def __init__(self, datos):
        self.datos = datos
        self.nombres = datos["nombres"]
        self.giro_centro = datos.get("giro_centro", 0.0)
        self.escala = _escala(datos["pasos"])
        self.X, self.y = _matriz(datos["pasos"], self.escala)
        self.calidad = evaluar(datos["pasos"])
        grabadas = {p["clase"] for p in datos["pasos"]}
        self.faltantes = tuple(g for g in GESTOS if g not in grabadas)

    def predecir(self, b):
        v = np.array([[b.get(n, 0.0) for n in self.nombres]], np.float32) / self.escala
        votos = _votar(self.X, self.y, v)[0]
        return _elegir(votos), {g: votos.get(g, 0.0) for g in GESTOS}


def cargar_clasificador():
    try:
        return Calibrado(json.loads(ARCHIVO_CALIBRACION.read_text()))
    except (OSError, ValueError, KeyError):
        return PorUmbrales()


def guardar_calibracion(datos):
    """Guarda la calibración; la anterior queda como respaldo en calibracion_anterior.json."""
    if ARCHIVO_CALIBRACION.exists():
        shutil.copyfile(ARCHIVO_CALIBRACION, ARCHIVO_CALIBRACION.with_name("calibracion_anterior.json"))
    ARCHIVO_CALIBRACION.write_text(json.dumps(datos, ensure_ascii=False))


# ---------------------------------------------------------------- calibración guiada
PASOS = (
    ("neutro", "Poné cara normal y mirá la pantalla", 3.0),
    ("neutro", "Cara normal: girá la cabeza despacio a los costados", 3.0),
    ("neutro", "Relajado: mirá distintas partes de la pantalla", 3.0),
    ("sonrisa", "Sonreí", 2.5),
    ("boca", "Abrí la boca (no hace falta mucho)", 2.5),
    ("cejas", "Levantá las dos cejas", 2.5),
    ("ceja_izq", "Levantá solo la ceja IZQUIERDA", 2.5),
    ("ceja_der", "Levantá solo la ceja DERECHA", 2.5),
    ("ceño", "Fruncí el ceño", 2.5),
    ("beso", "Hacé trompita, como para dar un beso", 2.5),
    ("cachetes", "Inflá los cachetes", 2.5),
    ("guiño_izq", "Guiñá el ojo IZQUIERDO", 2.5),
    ("guiño_der", "Guiñá el ojo DERECHO", 2.5),
    ("ojos", "Cerrá los dos ojos hasta que suene el aviso", 2.5),
)
PREPARAR = 2.0
MIN_MUESTRAS = 15


def _recortar_ojos(vectores, nombres):
    """Con los ojos cerrados no se ve la pantalla: si se abrieron antes o después de
    tiempo, se descartan esos cuadros (los que tienen los ojos bastante más abiertos)."""
    iz, de = nombres.index("eyeBlinkLeft"), nombres.index("eyeBlinkRight")
    cierre = np.array([min(v[iz], v[de]) for v in vectores])
    quedan = [v for v, c in zip(vectores, cierre) if c >= 0.6 * cierre.max()]
    return quedan if len(quedan) >= 5 else vectores


class Calibracion:
    """Va pidiendo cada gesto: unos segundos para prepararse y otros grabando.
    `solo` = lista de gestos a regrabar (None = todo)."""

    def __init__(self, solo=None, intro=True, motivo=None):
        self.solo = set(solo) if solo else None
        self.pasos = [p for p in PASOS if self.solo is None or p[0] in self.solo]
        self.fase = "intro" if intro else "preparar"
        self.motivo = motivo
        self.i = 0
        self.t = None
        self.grabaciones = []
        self.actual, self.giros = [], []
        self.nombres = None
        self.terminada = False

    @property
    def paso(self):
        return self.pasos[min(self.i, len(self.pasos) - 1)]

    def progreso(self, ahora):
        if self.t is None:
            return 0.0
        dur = PREPARAR if self.fase == "preparar" else self.paso[2]
        return min(1.0, (ahora - self.t) / dur)

    def empezar(self):
        if self.fase == "intro":
            self.fase, self.t = "preparar", None

    def actualizar(self, lectura, ahora):
        if self.fase == "intro" or self.terminada:
            return
        if self.t is None:
            self.t = ahora
        if self.fase == "preparar":
            if ahora - self.t >= PREPARAR:
                self.fase, self.t = "grabar", ahora
                self.actual, self.giros = [], []
            return
        if lectura and lectura["cara"]:
            if self.nombres is None:
                self.nombres = [n for n in lectura["b"] if n not in IGNORAR]
            self.actual.append([round(lectura["b"][n], 3) for n in self.nombres])
            self.giros.append(lectura["giro"])
        if ahora - self.t >= self.paso[2] and len(self.actual) >= MIN_MUESTRAS:
            clase = self.paso[0]
            vectores = _recortar_ojos(self.actual, self.nombres) if clase == "ojos" else self.actual
            self.grabaciones.append({"clase": clase, "vectores": vectores, "giro": float(np.median(self.giros))})
            self.i += 1
            if self.i >= len(self.pasos):
                self.terminada = True
                sonar("complete")
            else:
                self.fase, self.t = "preparar", ahora
                sonar("message")

    def resultado(self, previos=None):
        """Arma los datos de calibración; si se regrabaron algunos gestos, reemplaza esos en los previos."""
        if self.solo and previos and previos["nombres"] == self.nombres:
            pasos = [p for p in previos["pasos"] if p["clase"] not in self.solo] + self.grabaciones
            centro = previos.get("giro_centro", 0.0)
        else:
            pasos = self.grabaciones
            centro = self.grabaciones[0]["giro"]
        return {"version": 2, "nombres": self.nombres, "giro_centro": centro, "pasos": pasos}


# ---------------------------------------------------------------- control
class Control:
    """Convierte el gesto de cada cuadro en eventos.

    Un gesto se dispara cuando estuvo presente `espera` segundos dentro de una ventana
    un poco más larga (espera / PRESENCIA): así tolera algún cuadro perdido, pero un
    gesto que aparece de a ratos por error (menos de ~2/3 del tiempo) nunca llega.
    Después de dispararse hay que soltarlo un momento antes de que vuelva a contar."""

    SOLTAR = 0.25
    PRESENCIA = 0.65

    def __init__(self, espera=0.5):
        self.espera = espera
        self.reiniciar()

    def reiniciar(self):
        self.limpiar()
        self.bloqueado, self.libre = None, 0.0
        self.centrado = True
        self.t = None

    def limpiar(self):
        """Olvida los gestos a medio cargar (al cambiar de pantalla), pero mantiene el
        bloqueo: si cerraste los ojos para pausar, no vuelve a contar hasta que los abras."""
        self.historia = deque()
        self.gesto, self.progreso = None, 0.0

    def actualizar(self, gesto, giro, ahora):
        dt = 0.0 if self.t is None else min(ahora - self.t, 0.1)
        self.t = ahora
        eventos = []

        if giro is not None:
            if self.centrado and abs(giro) > GIRO_ON:
                eventos.append("izq" if giro < 0 else "der")
                self.centrado = False
            elif abs(giro) < GIRO_OFF:
                self.centrado = True

        if self.bloqueado:
            self.libre = 0.0 if gesto == self.bloqueado else self.libre + dt
            if self.libre >= self.SOLTAR:
                self.bloqueado = None

        self.historia.append((ahora, dt, gesto))
        while ahora - self.historia[0][0] > self.espera / self.PRESENCIA:
            self.historia.popleft()
        presente = {}
        for _, d, g in self.historia:
            if g and g != self.bloqueado:
                presente[g] = presente.get(g, 0.0) + d

        if gesto and presente.get(gesto, 0.0) >= self.espera:
            eventos.append(gesto)
            self.bloqueado, self.libre = gesto, 0.0
            self.historia.clear()
            presente = {}

        if gesto and gesto == self.bloqueado:
            self.gesto, self.progreso = gesto, 1.0
        else:
            activo = max(presente, key=presente.get, default=None)
            if activo and presente[activo] > 0.05 * self.espera:
                self.gesto, self.progreso = activo, min(1.0, presente[activo] / self.espera)
            else:
                self.gesto, self.progreso = None, 0.0
        return eventos
