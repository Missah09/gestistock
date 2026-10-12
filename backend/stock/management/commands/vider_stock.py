"""Supprime les articles et leurs listes, pour repartir d'une base vide.

Utilisation :  python manage.py vider_stock

Supprime : articles, exemplaires, catégories, emplacements, fournisseurs.
Conserve : les magasins (Ankorondrano, Manandriana…) et les comptes utilisateurs.
Une confirmation est demandée avant de supprimer.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from stock.models import Article, Categorie, Emplacement, Exemplaire, Fournisseur


class Command(BaseCommand):
    help = "Supprime articles, exemplaires, catégories, emplacements et fournisseurs (garde les magasins)."

    def handle(self, *args, **options):
        comptes = {
            "articles": Article.objects.count(),
            "exemplaires": Exemplaire.objects.count(),
            "catégories": Categorie.objects.count(),
            "emplacements": Emplacement.objects.count(),
            "fournisseurs": Fournisseur.objects.count(),
        }
        self.stdout.write("Seront supprimés : " + ", ".join(f"{n} {k}" for k, n in comptes.items()))
        self.stdout.write("Les magasins et les comptes utilisateurs sont conservés.")
        if input("Tapez OUI pour confirmer : ").strip().upper() != "OUI":
            self.stdout.write(self.style.WARNING("Annulé : rien n'a été supprimé."))
            return
        with transaction.atomic():
            Exemplaire.objects.all().delete()
            Article.objects.all().delete()   # d'abord les articles (ils utilisent les listes ci-dessous)
            Categorie.objects.all().delete()
            Emplacement.objects.all().delete()
            Fournisseur.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("Terminé : la base est vide, prête pour vos vrais articles."))
