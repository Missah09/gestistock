@echo off
rem Copie les donnees de GestiStock (PostgreSQL du PC) vers la base en ligne Neon (12/10/2026).
rem A lancer UNE SEULE FOIS, apres le premier deploiement reussi sur Render.
rem Le PC garde ses donnees : rien n'est efface ici.
setlocal
set "REQUESTS_CA_BUNDLE="
set "CURL_CA_BUNDLE="
set "SSL_CERT_FILE="
set "PIP_CERT="
set "PYTHONUTF8=1"
cd /d "%~dp0..\backend"
call venv\Scripts\activate
python -m pip install -q --disable-pip-version-check -r requirements.txt
echo.
echo 1/3 - Export des donnees du PC...
python manage.py dumpdata --natural-foreign -e contenttypes -e auth.permission -e sessions -e admin.logentry --indent 1 -o donnees\export-pour-neon.json
if errorlevel 1 goto echec
echo.
echo Collez l'adresse de connexion Neon ^(commence par postgresql://...^)
set /p "DATABASE_URL=Adresse Neon : "
echo.
echo 2/3 - Creation des tables sur Neon...
python manage.py migrate --noinput
if errorlevel 1 goto echec
echo.
echo ATTENTION : tout ce qui est deja dans la base Neon va etre remplace par les donnees du PC.
set /p "OK=Tapez OUI pour continuer : "
if /i not "%OK%"=="OUI" goto annule
python manage.py flush --noinput
if errorlevel 1 goto echec
echo 3/3 - Copie des donnees vers Neon...
python manage.py loaddata donnees\export-pour-neon.json
if errorlevel 1 goto echec
echo.
echo Termine : les donnees sont en ligne. Connectez-vous sur le site Render avec vos identifiants habituels.
goto fin
:annule
echo.
echo Annule : la base Neon n'a pas ete modifiee par la copie.
goto fin
:echec
echo.
echo ECHEC : copiez le message ci-dessus et envoyez-le.
:fin
endlocal
pause
