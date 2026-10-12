#!/usr/bin/env bash
# Construction de GestiStock sur Render (12/10/2026) : interface React, puis Django.
set -o errexit

echo "== Interface React =="
cd frontend
npm ci
npm run build
cd ..

echo "== Django =="
cd backend
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
# Met à jour les tables de la base Neon (sans effet si elles sont déjà à jour).
python manage.py migrate --noinput
