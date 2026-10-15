@echo off
rem Envoie GestiStock sur GitHub (12/10/2026).
rem Avant : creer un depot VIDE sur https://github.com/new (sans README, sans .gitignore), puis copier son adresse.
rem Les fichiers secrets (backend\.env, backend\donnees, sauvegardes) ne partent PAS (voir .gitignore).
setlocal
cd /d "%~dp0.."
where git >nul 2>nul
if errorlevel 1 (
  echo Git n'est pas installe sur ce PC.
  echo Installez-le depuis https://git-scm.com/download/win ^(options par defaut^), puis relancez ce fichier.
  pause
  exit /b 1
)
if not exist ".git" (
  git init -b main
)
git config user.name >nul 2>nul || git config user.name "GestiStock HBC"
git config user.email >nul 2>nul || git config user.email "razafymisandratra@gmail.com"
git add -A
rem Nom de l'envoi demande a chaque fois (12/10/2026) : avant, tous les envois s'appelaient
rem "GestiStock : preparation de la mise en ligne (Render + Neon)". PowerShell garde les accents.
echo.
echo Decrivez en quelques mots ce qui a change ^(ex. : Ajout de Tableau de bord^).
powershell -NoProfile -Command "$m = Read-Host 'Nom de l''envoi'; if (-not $m.Trim()) { $m = 'Mise a jour de GestiStock' }; [IO.File]::WriteAllText($env:TEMP + '\gestistock-message.txt', $m.Trim(), (New-Object Text.UTF8Encoding $false))"
git commit -F "%TEMP%\gestistock-message.txt"
del "%TEMP%\gestistock-message.txt" >nul 2>nul
git remote get-url origin >nul 2>nul
if errorlevel 1 (
  set /p DEPOT=Collez l'adresse du depot GitHub ^(ex. https://github.com/votre-nom/gestistock.git^) : 
  call git remote add origin %%DEPOT%%
)
git branch -M main
echo.
echo Envoi vers GitHub... ^(une fenetre de connexion GitHub peut s'ouvrir la premiere fois^)
git push -u origin main
if errorlevel 1 (
  echo.
  echo ECHEC de l'envoi : copiez le message ci-dessus et envoyez-le.
) else (
  echo.
  echo Termine : le code est sur GitHub.
)
endlocal
pause
