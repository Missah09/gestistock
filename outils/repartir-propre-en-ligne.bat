@echo off
rem Repartir propre (15/10/2026) : efface les donnees d'essai de GestiStock EN LIGNE (base Neon).
rem 1) sauvegarde complete de la base Neon dans backend\donnees
rem 2) affiche ce qui sera efface, puis demande OUI
rem Garde : comptes, departements, magasins, emplacements, categories, fournisseurs, chantiers.
rem Efface : demandes, requisitions, sorties, retours, receptions, historique, articles d'essai.
rem Remet le stock du fichier backend\donnees\stock_ankorondrano.csv.
setlocal
chcp 65001 >nul
set "REQUESTS_CA_BUNDLE="
set "CURL_CA_BUNDLE="
set "SSL_CERT_FILE="
set "PIP_CERT="
set "PYTHONUTF8=1"
cd /d "%~dp0..\backend"
call venv\Scripts\activate
python -m pip install -q --disable-pip-version-check -r requirements.txt
echo.
echo Collez l'adresse de connexion Neon ^(commence par postgresql://...^)
set /p "DATABASE_URL=Adresse Neon : "
if "%DATABASE_URL%"=="" goto annule
for /f %%d in ('python -c "import datetime;print(datetime.datetime.now().strftime('%%Y-%%m-%%d-%%H%%M'))"') do set "HORO=%%d"
set "SAUVEGARDE=donnees\sauvegarde-neon-avant-remise-a-zero-%HORO%.json"
echo.
echo 1/2 - Sauvegarde de la base en ligne...
python manage.py dumpdata --natural-foreign -e contenttypes -e auth.permission -e sessions -e admin.logentry --indent 1 -o "%SAUVEGARDE%"
if errorlevel 1 goto echec
if not exist "%SAUVEGARDE%" goto echec
echo Sauvegarde faite : backend\%SAUVEGARDE%
echo.
echo 2/2 - Remise a zero des donnees d'essai
python manage.py repartir_propre donnees\stock_ankorondrano.csv
if errorlevel 1 goto echec
echo.
echo Si vous avez tape OUI : rechargez le site Render, l'application repart propre.
goto fin
:annule
echo.
echo Annule : la base en ligne n'a pas ete modifiee.
goto fin
:echec
echo.
echo ECHEC : rien n'a ete efface. Copiez le message ci-dessus et envoyez-le.
:fin
endlocal
pause
