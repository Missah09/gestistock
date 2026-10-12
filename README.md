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

## État du produit et Retours (depuis le 12/10/2026)
- **État du produit** partout : **Neuf · Bon · Moyen · Mauvais** (simplifié le 12/10/2026 après-midi). Choisi à l'entrée en stock
  (« Neuf » par défaut), indiqué à la sortie et au retour, visible dans la liste Articles (filtre « État ») et dans les fiches.
  **Tous les états sont disponibles** (comptés dans le stock, proposés dans les demandes). Le bon de réquisition a une colonne « État ».
- Anciennes valeurs converties par la migration 0019 : Usagé → Moyen ; À réparer et Hors service → Mauvais, **remis dans le stock
  disponible** (une ligne « Correction » est ajoutée à l'historique). Ce qui avait été mis au rebut reste hors stock.
  Les emplacements vides « Atelier – À réparer » et « Rebut » sont supprimés. **À lancer : `python manage.py migrate`.**
- L'écran **« Matériel à réparer » a été retiré** (sauvegarde : `sauvegarde-avant-4-etats-12-10`).
- Menu **« Retours de stock »** (Agent Logistique) : le matériel prêté attendu (retards en rouge, pastille du menu).
  « Préparer le bon de retour » (signature au stylo) → BON DE RETOUR BR-AAAA-0001 en PDF, rempli à la main au magasin →
  « Confirmer le retour » : le stock remonte. Retour partiel : un bon par passage, le suivant ne liste que le reste.
- Historique de chaque changement d'état : Administration › « Historique des états ».

## Entrée en stock et création d'articles (depuis le 12/10/2026)
- L'ancien bouton « Enregistrer des produits » s'appelle désormais **« Entrée en stock »** (écran Liste d'Articles, en haut à droite).
  Il n'y a **pas de bouton séparé** pour créer un article : un produit nouveau arrive toujours avec une livraison.
- **Créer un article** : dans « Entrée en stock », taper le nom dans « Article reçu » ; en bas de la liste, **« ＋ Créer l'article « … » »**.
  La fenêtre « Nouvel article » s'ouvre par-dessus (nom repris, magasin de la livraison). Après « Créer l'article », il est placé
  sur la ligne : il ne reste qu'à saisir la quantité. Si la livraison est ensuite annulée, l'article reste créé (stock 0).
- **Depuis une fiche article** : bouton **« Entrée en stock »** à côté de « Modifier » ; la fenêtre s'ouvre avec cet article déjà choisi,
  et la fiche se rouvre ensuite avec le stock à jour.
- Agent Logistique et administrateur seulement.
- Création : code automatique (aperçu affiché), catégorie, unité, type, emplacement, seuil d'alerte ; prix, fournisseur, références facultatifs.
  Matériel « Non consommable · à rendre » : case **« Suivi par n° de série »** (OTDR, soudeuse…) : n° exigés dès la 1re entrée en stock.
  Type et suivi par n° de série fixés à la création. Doublon refusé : même nom (accents/majuscules ignorés) dans le même magasin.
- **Mise à jour de la base nécessaire** (colonne `suivi_serie`) : `python manage.py migrate` (migration 0018 ; le matériel qui a déjà
  des exemplaires est marqué « suivi par n° de série » automatiquement).
- Sauvegardes : `sauvegarde-avant-nouvel-article-12-10`, `sauvegarde-avant-entree-en-stock-12-10`. Tests : `stock/tests_nouvel_article.py`.

## Mise en ligne : GitHub + Render + Neon (depuis le 12/10/2026)
- **Un seul service Render** : Django sert l'API, l'administration et l'interface React (construite par `build.sh`).
  Réglages dans `render.yaml`. La base est chez **Neon** (variable `DATABASE_URL` sur Render).
- Ne partent jamais sur GitHub : `backend/.env`, `backend/donnees/`, les sauvegardes (voir `.gitignore`).
- **Envoyer le code sur GitHub** : double-cliquer sur `outils\publier-sur-github.bat` (Git pour Windows nécessaire).
  Après chaque modification, relancer ce fichier : Render remet le site à jour tout seul.
- **Copier les données du PC vers Neon** (une fois) : `outils\copier-donnees-vers-neon.bat` (remplace tout le contenu de Neon).
- Sur le PC, rien ne change : `demarrer-gestistock.bat` utilise toujours la base PostgreSQL locale.
- Offre gratuite Render : le site s'endort après 15 min sans visite ; la première ouverture suivante prend ~1 minute.
