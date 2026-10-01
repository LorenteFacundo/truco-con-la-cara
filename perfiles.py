"""Perfiles: una calibración por persona, para que cada uno juegue con sus propios gestos.

Cada perfil es un archivo perfiles/perfil-N.json con la calibración y, adentro,
{"perfil": {"nombre": "Perfil N", "creado": "2026-10-01T18:30"}}. Como sin manos no se
pueden escribir nombres, se numeran solos.
"""

import json
import re
import shutil
from datetime import datetime

from rutas import carpeta_datos

CARPETA = carpeta_datos() / "perfiles"


class Perfiles:
    def __init__(self, carpeta=CARPETA):
        self.carpeta = carpeta
        self.respaldos = carpeta / "respaldos"
        self.respaldos.mkdir(parents=True, exist_ok=True)
        self._migrar()

    def _migrar(self):
        """La calibración de antes de que existieran los perfiles pasa a ser el Perfil 1."""
        vieja = self.carpeta.parent / "calibracion.json"
        if vieja.exists() and not self.lista():
            try:
                datos = json.loads(vieja.read_text())
            except ValueError:
                return
            creado = datetime.fromtimestamp(vieja.stat().st_mtime)
            self.guardar("perfil-1", datos, "Perfil 1", creado)
            vieja.rename(self.respaldos / "calibracion-original.json")

    def _archivo(self, id):
        return self.carpeta / f"{id}.json"

    @staticmethod
    def _numero(id):
        m = re.fullmatch(r"perfil-(\d+)", id)
        return int(m.group(1)) if m else 0

    def lista(self):
        """[{"id", "nombre", "creado"}] ordenados por número."""
        perfiles = []
        for f in self.carpeta.glob("perfil-*.json"):
            try:
                info = json.loads(f.read_text()).get("perfil", {})
            except ValueError:
                continue
            perfiles.append({"id": f.stem, "nombre": info.get("nombre", f.stem),
                             "creado": info.get("creado", "")})
        return sorted(perfiles, key=lambda p: self._numero(p["id"]))

    def existe(self, id):
        return bool(id) and self._archivo(id).exists()

    def nombre(self, id):
        return next((p["nombre"] for p in self.lista() if p["id"] == id), "Sin perfil")

    def cargar(self, id):
        """La calibración del perfil, o None si no existe."""
        try:
            return json.loads(self._archivo(id).read_text())
        except (OSError, ValueError, TypeError):
            return None

    def nuevo(self):
        """Elige el id y el nombre del próximo perfil (todavía no lo crea)."""
        n = max((self._numero(p["id"]) for p in self.lista()), default=0) + 1
        return f"perfil-{n}", f"Perfil {n}"

    def guardar(self, id, datos, nombre=None, creado=None):
        """Guarda la calibración del perfil; la anterior queda en respaldos/."""
        archivo = self._archivo(id)
        info = dict((self.cargar(id) or {}).get("perfil", {}))
        if archivo.exists():
            shutil.copyfile(archivo, self.respaldos / f"{id}.anterior.json")
        if nombre:
            info["nombre"] = nombre
        info.setdefault("nombre", id)
        info.setdefault("creado", (creado or datetime.now()).isoformat(timespec="minutes"))
        datos = dict(datos, perfil=info)
        archivo.write_text(json.dumps(datos, ensure_ascii=False))
        return datos

    def borrar(self, id):
        archivo = self._archivo(id)
        if archivo.exists():
            archivo.rename(self.respaldos / f"{id}.borrado.json")


def fecha_corta(iso):
    """'2026-10-01T18:30' -> '01/10 18:30'."""
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except ValueError:
        return ""
