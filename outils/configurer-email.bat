@echo off
rem Configure l'envoi des emails de GestiStock par Gmail (mot de passe d'application) puis envoie un email d'essai.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configurer-email.ps1"
echo.
pause
