#!/usr/bin/env bash
# Arma el ejecutable y lo empaqueta para compartir:
#   dist/truco-con-la-cara/truco-con-la-cara        (el ejecutable, con sus bibliotecas al lado)
#   dist/truco-con-la-cara-linux-x86_64.tar.gz      (para subir a GitHub Releases)
# Se arma como carpeta y no como archivo único porque arranca bastante más rápido.
# Uso: ./build.sh   (crea .venv e instala lo necesario si hace falta)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt pyinstaller

.venv/bin/pyinstaller --noconfirm --clean --onedir \
    --name truco-con-la-cara \
    --add-data "face_landmarker.task:." \
    --add-data "fuentes:fuentes" \
    --collect-data mediapipe \
    --collect-binaries mediapipe \
    juego.py

paquete="truco-con-la-cara-linux-$(uname -m).tar.gz"
tar -C dist -czf "dist/$paquete" truco-con-la-cara

echo
echo "Listo: dist/truco-con-la-cara/truco-con-la-cara"
echo "Paquete para compartir: dist/$paquete"
echo "Probalo con: ./dist/truco-con-la-cara/truco-con-la-cara --diagnostico"
