@echo off
rem Change le nom (message) du DERNIER envoi, meme s'il est deja sur GitHub (12/10/2026).
rem Le code ne change pas : seul le nom affiche sur GitHub est corrige.
setlocal
cd /d "%~dp0.."
where git >nul 2>nul
if errorlevel 1 (
  echo Git n'est pas installe sur ce PC.
  pause
  exit /b 1
)
git fetch origin main >nul 2>nul
for /f %%i in ('git rev-parse HEAD') do set ICI=%%i
for /f %%i in ('git rev-parse origin/main') do set GITHUB=%%i
if not "%ICI%"=="%GITHUB%" (
  echo Le dernier envoi du PC n'est pas le meme que celui de GitHub : rien n'a ete change.
  echo Lancez d'abord outils\publier-sur-github.bat, puis relancez ce fichier.
  pause
  exit /b 1
)
echo.
git log -1 --format="Nom actuel du dernier envoi : %%s"
echo.
powershell -NoProfile -Command "$m = Read-Host 'Nouveau nom (Entree seule pour annuler)'; [IO.File]::WriteAllText($env:TEMP + '\gestistock-message.txt', $m.Trim(), (New-Object Text.UTF8Encoding $false))"
for %%f in ("%TEMP%\gestistock-message.txt") do if %%~zf==0 (
  echo Annule : rien n'a ete change.
  del "%TEMP%\gestistock-message.txt" >nul 2>nul
  pause
  exit /b 0
)
rem --only : seul le nom change, meme si d'autres modifications sont en cours sur le PC.
git commit --amend --only -F "%TEMP%\gestistock-message.txt"
del "%TEMP%\gestistock-message.txt" >nul 2>nul
echo.
echo Envoi du nouveau nom vers GitHub...
git push --force-with-lease origin main
if errorlevel 1 (
  echo.
  echo ECHEC de l'envoi : copiez le message ci-dessus et envoyez-le.
) else (
  echo.
  git log -1 --format="Termine : le dernier envoi s'appelle maintenant : %%s"
)
endlocal
pause
