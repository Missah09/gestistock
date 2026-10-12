@echo off
rem Change le mot de passe d'un compte GestiStock (par exemple "admin" si vous l'avez oublie).
cd /d "%~dp0..\backend"
call venv\Scripts\activate
set /p IDENT=Identifiant du compte (par exemple admin) : 
python manage.py changepassword %IDENT%
echo.
pause
