"""Ajustes del juego que se guardan entre partidas: tiempo de gesto, puntos y qué gesto hace cada acción."""

import json

from caras import GESTOS
from rutas import dato

ARCHIVO = dato("ajustes.json")

ACCIONES = ("jugar", "truco", "envido", "real", "falta", "quiero", "no_quiero", "mazo")
NOMBRE_ACCION = {
    "jugar": "Tirar carta", "truco": "Truco / Retruco / Vale 4", "envido": "Envido",
    "real": "Real envido", "falta": "Falta envido", "quiero": "Quiero", "no_quiero": "No quiero",
    "mazo": "Irse al mazo",
}
POR_DEFECTO = {
    "jugar": "boca", "truco": "cejas", "envido": "beso", "real": "guiño_izq",
    "falta": "guiño_der", "quiero": "sonrisa", "no_quiero": "ceño", "mazo": "cachetes",
}
GESTO_PAUSA = "ojos"      # siempre abre / cierra el menú
GESTO_ELEGIR = "cejas"    # en el menú: elegir la opción
ASIGNABLES = tuple(g for g in GESTOS if g != GESTO_PAUSA)
ESPERAS = tuple(round(0.3 + 0.1 * i, 1) for i in range(10))   # 0.3 … 1.2 s
PUNTOS = (15, 30)

TECLAS = {
    ord(" "): "jugar", 13: "jugar", ord("t"): "truco", ord("e"): "envido", ord("r"): "real",
    ord("f"): "falta", ord("s"): "quiero", ord("n"): "no_quiero", ord("m"): "mazo",
}
TECLA_DE = {"jugar": "espacio", "truco": "T", "envido": "E", "real": "R", "falta": "F",
            "quiero": "S", "no_quiero": "N", "mazo": "M"}


class Ajustes:
    def __init__(self, espera=0.5, puntos=30, acciones=None):
        self.espera = espera
        self.puntos = puntos
        self.acciones = dict(acciones or POR_DEFECTO)

    @classmethod
    def cargar(cls):
        try:
            d = json.loads(ARCHIVO.read_text())
        except (OSError, ValueError):
            return cls()
        a = cls()
        if d.get("espera") in ESPERAS:
            a.espera = d["espera"]
        if d.get("puntos") in PUNTOS:
            a.puntos = d["puntos"]
        acc = d.get("acciones", {})
        valido = (set(acc) == set(ACCIONES) and all(g in ASIGNABLES for g in acc.values())
                  and len(set(acc.values())) == len(acc))
        if valido:
            a.acciones = acc
        return a

    def guardar(self):
        ARCHIVO.write_text(json.dumps({"espera": self.espera, "puntos": self.puntos,
                                       "acciones": self.acciones}, ensure_ascii=False, indent=2))

    def accion_de(self, gesto):
        """Qué acción hace un gesto en el juego (o None)."""
        for a, g in self.acciones.items():
            if g == gesto:
                return a
        return None

    def asignar(self, accion, gesto):
        """Le da `gesto` a `accion`; si otra acción lo usaba, se intercambian."""
        otra = self.accion_de(gesto)
        if otra and otra != accion:
            self.acciones[otra] = self.acciones[accion]
        self.acciones[accion] = gesto
