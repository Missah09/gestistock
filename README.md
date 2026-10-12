# GestiStock

Application de gestion de stock (fibre optique).
Backend : Django + Django REST Framework + PostgreSQL. Frontend : React (Vite).

## Installation sur Windows (une seule fois)

### 1. Logiciels à installer (s'ils manquent)
- **Python 3.13** : https://www.python.org/downloads/ (cocher « Add python.exe to PATH »)
- **Node.js LTS** : https://nodejs.org/

La base de données est **PostgreSQL** (depuis le 12/10/2026, SQLite n'est plus utilisé, même en développement).
Les réglages de connexion sont dans `backend/.env` (modèle : `backend/.env.exemple`).
**Ne jamais remplacer `backend/.env` par `.env.exemple`** : le mot de passe de la base serait perdu.

### 2. Backend (première fenêtre d'Invite de commandes)
```
cd "%USERPROFILE%\Desktop\Gestion de Stock\backend"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py charger_exemples
python manage.py createsuperuser
python manage.py runserver
```
Laissez cette fenêtre ouverte.

### 3. Frontend (deuxième fenêtre d'Invite de commandes)
```
cd "%USERPROFILE%\Desktop\Gestion de Stock\frontend"
npm install
npm run dev
```
Ouvrez ensuite http://127.0.0.1:3000 dans le navigateur.

## Démarrer les jours suivants
**Le plus simple :** double-cliquez sur `demarrer-gestistock.bat` (dans le dossier Gestion de Stock).
Deux fenêtres noires s'ouvrent (ne pas les fermer), puis le navigateur sur http://127.0.0.1:3000.
Pour arrêter : fermez les deux fenêtres noires.

À la main, si besoin :
- Fenêtre 1 : `cd "%USERPROFILE%\Desktop\Gestion de Stock\backend"`, puis `venv\Scripts\activate`, puis `python manage.py runserver`
- Fenêtre 2 : `cd "%USERPROFILE%\Desktop\Gestion de Stock\frontend"`, puis `npm run dev`

## Adresses utiles
- Application : http://127.0.0.1:3000
- Administration Django : http://127.0.0.1:8000/admin

## Base de données PostgreSQL (12/10/2026)
- Passage définitif fait le 12/10/2026 (toutes les données de SQLite copiées et vérifiées). Copie des données gardée dans `backend/donnees/`.
- Les tests automatiques tournent aussi sur PostgreSQL : `python manage.py test stock`
  (l'utilisateur `gestistock` a le droit de créer la base de test).

## Comptes utilisateurs (depuis le 11/10/2026)
- Il faut se connecter (identifiant + mot de passe) pour utiliser GestiStock.
- **Créer un compte (depuis le 11/10/2026, 22 h 40)** : connecté en **admin**, menu **« Comptes »** › **« Nouveau compte »** :
  identifiant, prénom, nom, département, mot de passe provisoire, et les rôles à cocher (« Agent Logistique », « Responsable HBC »).
  Rien à cocher pour « Saisisseur » : tout compte actif peut faire des demandes.
  Depuis la même fenêtre : changer le mot de passe, déconnecter l'appareil, désactiver ou réactiver le compte.
- **Un compte = un seul appareil connecté à la fois** : se connecter ailleurs déconnecte l'autre appareil (message à l'écran).
- L'administration Django (lien « Administration » du menu) reste disponible, notamment pour les super-utilisateurs.
- Départements : administration › « Départements » (Logistique, Technique, Finance, Direction, Informatique).
- Identifiant : les majuscules ne comptent pas à la connexion (« haja » = « Haja »).
- Aide : lien « Aide » en bas du menu = tutoriel pas à pas, selon le rôle de la personne.
- Mot de passe oublié : `outils\changer-mot-de-passe.bat`.

## Réquisitions et PDF du bon (depuis le 12/10/2026)
- Menu **« Réquisitions »** (Agent Logistique et Responsable HBC) : les bons signés par la Logistique et le Responsable,
  en onglets « À imprimer », « Imprimées », « Toutes ».
- **« Télécharger le PDF »** : bon au format A4 (`RM-2026-0001.pdf`), avec les deux signatures ; les articles retirés (0) n'y figurent pas.
- Chaque téléchargement est noté (qui, quand). Le **premier téléchargement par l'Agent Logistique** fait passer le bon en « Imprimée » ;
  un téléchargement du Responsable est une simple consultation. Historique visible dans l'administration (fiche de la réquisition).
- Le PDF est fabriqué avec **ReportLab** (ajouté à `requirements.txt`) : `demarrer-gestistock.bat` l'installe tout seul au démarrage
  (Internet nécessaire la première fois). Sinon : double-cliquer sur `outils\installer-modules.bat`.
  Sans ReportLab, GestiStock fonctionne mais « Télécharger le PDF » affiche un message.
- Erreur pip « Could not find a suitable TLS CA certificate bundle … PostgreSQL\17\ssl\certs\ca-bundle.crt » : un réglage du PC
  (installé avec PostgreSQL) envoie pip vers un fichier absent. Les deux .bat l'ignorent pour leur fenêtre (rien n'est changé sur le PC).

## Sorties : confirmation de la remise du matériel (depuis le 12/10/2026)
- Menu **« Sorties »** (Agent Logistique) : les bons **imprimés** (écran « Réquisitions ») et portés au magasin,
  en onglets « À confirmer », « Confirmées », « Toutes ». La pastille rouge compte les bons à confirmer.
- Au retour du bon signé par le magasinier : **« Confirmer la sortie »**, recopier la colonne « Qté livrée »
  (0 si rien n'a été remis ; lien « Tout a été livré comme sur le bon »), cocher les **n° de série remis** pour le matériel suivi
  par exemplaire, date de remise, nom du magasinier et observation (facultatifs), puis confirmer.
- **C'est à ce moment que le stock de GestiStock diminue** (les exemplaires cochés passent « Prêté », au nom du demandeur).
  Pas plus que la quantité du bon ni que le stock enregistré ; une sortie ne se confirme qu'une fois et ne s'annule pas.
- **« Copie d'archive (PDF) »** : le bon avec la Qté livrée remplie (`RM-2026-0001-archive.pdf`).
- Le demandeur voit l'étape « Remise » cochée dans « Mes demandes ». Administration › « Sorties » : consultation seulement.

## Mise en ligne : GitHub + Render + Neon (depuis le 12/10/2026)
- **Un seul service Render** : Django sert l'API, l'administration et l'interface React (construite par `build.sh`).
  Réglages dans `render.yaml`. La base est chez **Neon** (variable `DATABASE_URL` sur Render).
- Ne partent jamais sur GitHub : `backend/.env`, `backend/donnees/`, les sauvegardes (voir `.gitignore`).
- **Envoyer le code sur GitHub** : double-cliquer sur `outils\publier-sur-github.bat` (Git pour Windows nécessaire).
  Après chaque modification, relancer ce fichier : Render remet le site à jour tout seul.
- **Copier les données du PC vers Neon** (une fois) : `outils\copier-donnees-vers-neon.bat` (remplace tout le contenu de Neon).
- Sur le PC, rien ne change : `demarrer-gestistock.bat` utilise toujours la base PostgreSQL locale.
- Offre gratuite Render : le site s'endort après 15 min sans visite ; la première ouverture suivante prend ~1 minute.
