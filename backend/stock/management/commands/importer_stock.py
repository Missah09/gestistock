"""Importe (ou met à jour) des articles depuis un fichier CSV.

Utilisation :  python manage.py importer_stock donnees\\stock_ankorondrano.csv

Le fichier (séparateur « ; », ouvrable dans Excel) contient les colonnes :
  magasin ; emplacement ; article ; categorie ; prefixe ; type ; unite ; stock ; qte_minimale ; sortie ; observation

- Le magasin doit déjà exister (Ankorondrano, Manandriana…).
- Catégories et emplacements manquants sont créés automatiquement.
- Un article est reconnu par son nom ET son magasin : relancer l'import met à jour au lieu de dupliquer.
- Option --synchroniser : supprime aussi les articles des magasins du fichier qui n'y figurent plus
  (utile après avoir retiré ou renommé une ligne).
- Les colonnes « sortie » et « observation » sont conservées dans le fichier pour l'écran Sorties
  (pas encore développé) : elles ne sont pas importées pour l'instant.
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from stock.models import Article, Categorie, Emplacement, Magasin

TYPES = {"CONSOMMABLE": Article.Type.CONSOMMABLE, "PRETE": Article.Type.PRETE}
UNITES = {"piece": "piece", "pièce": "piece", "m": "m", "paire": "paire"}


def entier(valeur, ligne, colonne):
    valeur = (valeur or "").strip()
    if valeur == "":
        return 0
    if not valeur.isdigit():
        raise CommandError(f"Ligne {ligne} : « {colonne} » doit être un nombre entier (trouvé : « {valeur} »).")
    return int(valeur)


class Command(BaseCommand):
    help = "Importe des articles depuis un fichier CSV (séparateur ;)."

    def add_arguments(self, parser):
        parser.add_argument("fichier")
        parser.add_argument("--synchroniser", action="store_true",
                            help="Supprimer les articles des magasins du fichier qui n'y figurent plus.")

    @transaction.atomic
    def handle(self, fichier, synchroniser=False, **options):
        try:
            with open(fichier, encoding="utf-8-sig", newline="") as f:
                lignes = list(csv.DictReader(f, delimiter=";"))
        except FileNotFoundError:
            raise CommandError(f"Fichier introuvable : {fichier}")

        crees = maj = 0
        vus = set()  # ids des articles présents dans le fichier
        magasins_du_fichier = set()
        for n, l in enumerate(lignes, start=2):  # ligne 1 = en-têtes
            nom = (l.get("article") or "").strip()
            if not nom:
                continue
            try:
                magasin = Magasin.objects.get(nom=l["magasin"].strip())
            except Magasin.DoesNotExist:
                raise CommandError(f"Ligne {n} : le magasin « {l['magasin']} » n'existe pas.")
            type_ = TYPES.get((l.get("type") or "").strip().upper())
            if not type_:
                raise CommandError(f"Ligne {n} : type « {l.get('type')} » inconnu (CONSOMMABLE ou PRETE).")
            unite = UNITES.get((l.get("unite") or "piece").strip().lower())
            if not unite:
                raise CommandError(f"Ligne {n} : unité « {l.get('unite')} » inconnue (piece, m ou paire).")

            categorie, _ = Categorie.objects.get_or_create(
                nom=l["categorie"].strip(), defaults={"prefixe": l["prefixe"].strip().upper()})
            emplacement, _ = Emplacement.objects.get_or_create(nom=l["emplacement"].strip(), magasin=magasin)

            valeurs = dict(categorie=categorie, type=type_, unite=unite, emplacement=emplacement,
                           qte_stock=entier(l.get("stock"), n, "stock"),
                           qte_minimale=entier(l.get("qte_minimale"), n, "qte_minimale"))
            magasins_du_fichier.add(magasin.id)
            article = Article.objects.filter(nom=nom, emplacement__magasin=magasin).first()
            if article:
                for k, v in valeurs.items():
                    setattr(article, k, v)
                article.save()
                maj += 1
            else:
                article = Article.objects.create(nom=nom, **valeurs)
                crees += 1
            vus.add(article.id)

        if synchroniser:
            absents = Article.objects.filter(emplacement__magasin_id__in=magasins_du_fichier).exclude(id__in=vus)
            for a in absents:
                self.stdout.write(f"Supprimé (absent du fichier) : {a.code} – {a.nom}")
            absents.delete()

        self.stdout.write(self.style.SUCCESS(f"OK : {crees} articles créés, {maj} mis à jour."))
