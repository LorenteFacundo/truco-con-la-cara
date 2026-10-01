"""Arma el ejecutable con PyInstaller y lo empaqueta para compartir.

    Linux:   dist/truco-con-la-cara-linux-x86_64.tar.gz
    Windows: dist/truco-con-la-cara-windows-x64.zip

Se arma como carpeta (con el ejecutable adentro) y no como archivo único porque
arranca bastante más rápido.

Uso:
    pip install -r requirements.txt pyinstaller
    python build.py
"""

import os
import platform
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

AQUI = Path(__file__).parent
NOMBRE = "truco-con-la-cara"


def main():
    os.chdir(AQUI)
    PyInstaller.__main__.run([
        "--noconfirm", "--clean", "--onedir",
        "--name", NOMBRE,
        "--add-data", f"face_landmarker.task{os.pathsep}.",
        "--add-data", f"fuentes{os.pathsep}fuentes",
        "--collect-data", "mediapipe",
        "--collect-binaries", "mediapipe",
        "juego.py",
    ])

    maquina = platform.machine().lower()
    if sys.platform == "win32":
        arch = "x64" if maquina in ("amd64", "x86_64") else maquina
        paquete = shutil.make_archive(f"dist/{NOMBRE}-windows-{arch}", "zip", "dist", NOMBRE)
        ejecutable = f"dist/{NOMBRE}/{NOMBRE}.exe"
    else:
        sistema = "macos" if sys.platform == "darwin" else "linux"
        paquete = shutil.make_archive(f"dist/{NOMBRE}-{sistema}-{maquina}", "gztar", "dist", NOMBRE)
        ejecutable = f"dist/{NOMBRE}/{NOMBRE}"

    print()
    print(f"Listo: {ejecutable}")
    print(f"Paquete para compartir: {paquete}")
    print(f"Probalo con: {ejecutable} --diagnostico")


if __name__ == "__main__":
    main()
