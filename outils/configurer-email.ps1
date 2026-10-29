# Configuration de l'envoi des emails de GestiStock par Gmail (11/10/2026).
# Lancé par configurer-email.bat. Le mot de passe d'application est saisi ici, sur votre PC, et écrit dans backend\.env.
$ErrorActionPreference = "Stop"
$racine  = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $racine "backend"
$python  = Join-Path $backend "venv\Scripts\python.exe"
$envFich = Join-Path $backend ".env"
$env:PYTHONUTF8 = "1"
$utf8 = New-Object System.Text.UTF8Encoding $false

function Regler([string]$texte, [string]$cle, [string]$valeur) {
  # Remplace la ligne « CLE=… » si elle existe, sinon l'ajoute à la fin.
  $motif = "(?m)^\s*" + [regex]::Escape($cle) + "\s*=.*$"
  if ($texte -match $motif) { return [regex]::Replace($texte, $motif, ($cle + "=" + $valeur).Replace('$', '$$')) }
  if ($texte.Length -gt 0 -and -not $texte.EndsWith("`n")) { $texte += "`r`n" }
  return $texte + $cle + "=" + $valeur + "`r`n"
}
function Lire([string]$texte, [string]$cle) {
  $m = [regex]::Match($texte, "(?m)^\s*" + [regex]::Escape($cle) + "\s*=(.*)$")
  if ($m.Success) { return $m.Groups[1].Value.Trim() } else { return "" }
}

try {
  if (-not (Test-Path $python)) { throw "Python du projet introuvable : $python" }
  if (-not (Test-Path $envFich)) { throw "Fichier backend\.env introuvable." }
  $texte = [IO.File]::ReadAllText($envFich)

  Write-Host ""
  Write-Host "=== Envoi des emails de GestiStock par Gmail ===" -ForegroundColor Cyan
  Write-Host "Il faut un « mot de passe d'application » Google (16 lettres), PAS le mot de passe habituel du compte."
  Write-Host "Pour le créer : https://myaccount.google.com/apppasswords"
  Write-Host "(la validation en deux étapes doit être activée sur le compte Google). Nom proposé : GestiStock."
  Write-Host ""

  $actuel = Lire $texte "EMAIL_HOST_USER"
  $adresse = Read-Host "Adresse Gmail qui envoie les emails [$actuel]"
  if (-not $adresse) { $adresse = $actuel }
  if ($adresse -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { throw "Adresse email incorrecte : '$adresse'." }

  $secret = Read-Host "Mot de passe d'application (16 lettres, rien ne s'affiche)" -AsSecureString
  $mdp = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret))
  $mdp = ($mdp -replace '\s', '')
  if ($mdp.Length -lt 16) { throw "Le mot de passe d'application doit faire 16 lettres (vous en avez saisi $($mdp.Length)). Rien n'a été modifié." }

  $tempo = Lire $texte "GESTISTOCK_EMAIL_TEMPORAIRE"
  $dest = Read-Host "Destinataire temporaire des emails (vide = les comptes Responsable Logistique) [$tempo]"
  if (-not $dest) { $dest = $tempo }

  Copy-Item $envFich ($envFich + ".avant-email") -Force
  $texte = Regler $texte "EMAIL_HOST_USER" $adresse
  $texte = Regler $texte "EMAIL_HOST_PASSWORD" $mdp
  $texte = Regler $texte "GESTISTOCK_EMAIL_TEMPORAIRE" $dest
  [IO.File]::WriteAllText($envFich, $texte, $utf8)
  Write-Host "   OK : réglages enregistrés dans backend\.env (ancienne version : backend\.env.avant-email)." -ForegroundColor Green

  Write-Host ""
  Write-Host "Envoi d'un email d'essai..." -ForegroundColor Cyan
  Push-Location $backend
  try { & $python manage.py tester_email; $code = $LASTEXITCODE } finally { Pop-Location }
  if ($code -ne 0) { throw "L'email d'essai n'est pas parti : vérifiez l'adresse et le mot de passe d'application, puis relancez." }
  Write-Host ""
  Write-Host "Terminé. Fermez puis relancez GestiStock (demarrer-gestistock.bat) pour que le serveur prenne les réglages." -ForegroundColor Green
} catch {
  Write-Host ""
  Write-Host "ERREUR : $($_.Exception.Message)" -ForegroundColor Red
}
