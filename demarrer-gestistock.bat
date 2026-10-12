@echo off
rem Demarre GestiStock : le serveur Django, l'interface React, puis ouvre le navigateur.
rem Double-cliquez sur ce fichier. Pour arreter : fermez les deux fenetres noires.
rem 12/10/2026 : installe d'abord les modules Python manquants (ReportLab pour le PDF du bon) ; sans Internet, on continue.
rem Les variables de certificats sont videes pour cette fenetre seulement (reglage PostgreSQL qui gene pip).
cd /d "%~dp0"
start "GestiStock - serveur (ne pas fermer)" cmd /k "set "REQUESTS_CA_BUNDLE=" && set "CURL_CA_BUNDLE=" && set "SSL_CERT_FILE=" && set "PIP_CERT=" && cd /d "%~dp0backend" && call venv\Scripts\activate && (python -m pip install -q --disable-pip-version-check -r requirements.txt || echo Modules Python non installes : lancez outils\installer-modules.bat.) && python manage.py migrate --noinput && python manage.py runserver"
start "GestiStock - interface (ne pas fermer)" cmd /k "cd /d "%~dp0frontend" && npm run dev"
echo Demarrage de GestiStock... le navigateur va s'ouvrir.
timeout /t 8 /nobreak >nul
start "" http://127.0.0.1:3000
