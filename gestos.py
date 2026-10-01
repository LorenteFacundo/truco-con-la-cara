"""Detector de gestos faciales en tiempo real con la webcam.

Usa MediaPipe FaceLandmarker (478 puntos + 52 "blendshapes") y OpenCV.
Teclas: q / Esc = salir, m = mostrar/ocultar malla, b = mostrar/ocultar barras.
"""

import math
import time
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

MODELO = Path(__file__).with_name("face_landmarker.task")
CAMARA = 0

# Gesto -> (función que recibe el dict de blendshapes, umbral)
# La imagen se muestra espejada, así que "izquierdo" es tu ojo izquierdo tal como lo ves.
GESTOS = {
    "Sonrisa":          (lambda b: (b["mouthSmileLeft"] + b["mouthSmileRight"]) / 2, 0.55),
    "Boca abierta":     (lambda b: b["jawOpen"], 0.45),
    "Beso / trompita":  (lambda b: b["mouthPucker"], 0.6),
    "Cejas arriba":     (lambda b: b["browInnerUp"], 0.5),
    "Ceño fruncido":    (lambda b: (b["browDownLeft"] + b["browDownRight"]) / 2, 0.4),
    "Mejillas infladas": (lambda b: b["cheekPuff"], 0.4),
    "Guiño izquierdo":  (lambda b: b["eyeBlinkLeft"] - b["eyeBlinkRight"], 0.35),
    "Guiño derecho":    (lambda b: b["eyeBlinkRight"] - b["eyeBlinkLeft"], 0.35),
    "Ojos cerrados":    (lambda b: min(b["eyeBlinkLeft"], b["eyeBlinkRight"]), 0.5),
}

VERDE = (80, 220, 100)
GRIS = (150, 150, 150)
BLANCO = (255, 255, 255)
CIAN = (255, 200, 0)


def angulos_cabeza(matriz):
    """Devuelve (yaw, pitch, roll) en grados desde la matriz de transformación 4x4."""
    r = np.array(matriz)[:3, :3]
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    yaw = math.degrees(math.asin(-max(-1.0, min(1.0, r[2, 0]))))
    roll = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    return yaw, pitch, roll


def describir_cabeza(yaw, pitch, roll):
    partes = []
    if yaw > 18:
        partes.append("mirando a la izquierda")
    elif yaw < -18:
        partes.append("mirando a la derecha")
    if pitch > 15:
        partes.append("mirando abajo")
    elif pitch < -15:
        partes.append("mirando arriba")
    if roll > 15:
        partes.append("cabeza inclinada")
    elif roll < -15:
        partes.append("cabeza inclinada")
    return ", ".join(partes) or "mirando al frente"


def texto(img, s, pos, color=BLANCO, escala=0.6, grosor=1):
    cv2.putText(img, s, pos, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), grosor + 3, cv2.LINE_AA)
    cv2.putText(img, s, pos, cv2.FONT_HERSHEY_SIMPLEX, escala, color, grosor, cv2.LINE_AA)


def dibujar_panel(img, valores):
    x, y = 12, 30
    for nombre, (valor, umbral) in valores.items():
        activo = valor >= umbral
        color = VERDE if activo else GRIS
        ancho = int(150 * max(0.0, min(1.0, valor)))
        cv2.rectangle(img, (x, y - 12), (x + 150, y + 2), (40, 40, 40), -1)
        cv2.rectangle(img, (x, y - 12), (x + ancho, y + 2), color, -1)
        marca = x + int(150 * umbral)
        cv2.line(img, (marca, y - 14), (marca, y + 4), BLANCO, 1)
        texto(img, nombre, (x + 160, y), color, 0.5)
        y += 24


def main():
    if not MODELO.exists():
        raise SystemExit(f"Falta el modelo: {MODELO}")

    opciones = vision.FaceLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=str(MODELO)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
    )

    cap = cv2.VideoCapture(CAMARA, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        raise SystemExit("No pude abrir la cámara (¿la está usando otra app?)")

    ver_malla, ver_barras = True, True
    t0 = time.monotonic()
    fps, ultimo = 0.0, time.monotonic()

    with vision.FaceLandmarker.create_from_options(opciones) as detector:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("No llegan imágenes de la cámara")
                break
            frame = cv2.flip(frame, 1)  # efecto espejo
            h, w = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts = int((time.monotonic() - t0) * 1000)
            res = detector.detect_for_video(imagen, ts)

            if res.face_landmarks:
                puntos = res.face_landmarks[0]
                if ver_malla:
                    for p in puntos:
                        cv2.circle(frame, (int(p.x * w), int(p.y * h)), 1, CIAN, -1)

                b = {c.category_name: c.score for c in res.face_blendshapes[0]}
                valores = {n: (f(b), u) for n, (f, u) in GESTOS.items()}
                activos = [n for n, (v, u) in valores.items() if v >= u]
                if "Ojos cerrados" in activos:
                    activos = [a for a in activos if not a.startswith("Guiño")]

                if ver_barras:
                    dibujar_panel(frame, valores)

                cabeza = describir_cabeza(*angulos_cabeza(res.facial_transformation_matrixes[0]))
                texto(frame, cabeza.capitalize(), (12, h - 50), CIAN, 0.7, 2)
                texto(frame, "  |  ".join(activos) if activos else "Cara neutra",
                      (12, h - 18), VERDE if activos else BLANCO, 0.9, 2)
            else:
                texto(frame, "No veo ninguna cara", (12, h - 18), (80, 80, 255), 0.9, 2)

            ahora = time.monotonic()
            fps = 0.9 * fps + 0.1 * (1 / max(ahora - ultimo, 1e-6))
            ultimo = ahora
            texto(frame, f"{fps:4.1f} FPS", (w - 110, 25), BLANCO, 0.6)

            cv2.imshow("Gestos de la cara  (q = salir)", frame)
            tecla = cv2.waitKey(1) & 0xFF
            if tecla in (ord("q"), 27):
                break
            if tecla == ord("m"):
                ver_malla = not ver_malla
            if tecla == ord("b"):
                ver_barras = not ver_barras

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
