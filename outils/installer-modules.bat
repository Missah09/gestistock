@echo off
rem Installe les modules Python de GestiStock (dont ReportLab, pour le PDF du bon de requisition).
rem Double-cliquez sur ce fichier (Internet necessaire). GestiStock peut rester ferme pendant l'installation.
rem 12/10/2026 : un reglage du PC (installe avec PostgreSQL) envoyait pip vers un fichier de certificats
rem inexistant (C:\Program Files\PostgreSQL\17\ssl\certs\ca-bundle.crt). On l'ignore ici, pour cette fenetre seulement :
rem rien n'est change sur le PC.
setlocal
set "REQUESTS_CA_BUNDLE="
set "CURL_CA_BUNDLE="
set "SSL_CERT_FILE="
set "PIP_CERT="
cd /d "%~dp0..\backend"
call venv\Scripts\activate
echo Installation des modules Python de GestiStock...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo ECHEC : copiez le message ci-dessus et envoyez-le.
) else (
  echo.
  echo Termine : les modules sont installes. Vous pouvez demarrer GestiStock.
)
endlocal
pause
