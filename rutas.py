"""Dónde están los archivos.

- Recursos del juego (modelo de MediaPipe, fuentes): al lado del código, o dentro del
  ejecutable cuando se arma con PyInstaller.
- Datos de cada jugador (calibración, ajustes): en la carpeta de configuración del
  usuario, así sobreviven a actualizaciones y nunca se mezclan con el código.
"""

import os
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).parent
NOMBRE_APP = "truco-con-la-cara"


def recurso(nombre):
    return Path(getattr(sys, "_MEIPASS", AQUI)) / nombre


def carpeta_datos():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    carpeta = base / NOMBRE_APP
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def dato(nombre):
    """Archivo del jugador. Si quedó uno de una versión anterior al lado del código, lo muda."""
    destino = carpeta_datos() / nombre
    viejo = AQUI / nombre
    if not destino.exists() and viejo.exists() and not getattr(sys, "frozen", False):
        shutil.move(viejo, destino)
    return destino
