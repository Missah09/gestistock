"""Repartir propre avant la vraie utilisation (15/10/2026) : efface les données d'essai.

Utilisation :  python manage.py repartir_propre donnees\\stock_ankorondrano.csv
(outils\\repartir-propre-en-ligne.bat le fait sur la base en ligne Neon, après une sauvegarde.)

Efface : demandes, réquisitions (et téléchargements des bons), sorties, bons de retour, réceptions,
         historique des mouvements, exemplaires (n° de série) et répartition du stock par état.
Supprime : les articles absents du fichier d'inventaire (créés pendant les essais).
Remet : la quantité en stock et la quantité minimale de chaque article du fichier (tout au magasin, état par défaut).
Garde : comptes (et signatures enregistrées), départements, magasins, emplacements, catégories,
        fournisseurs, chantiers.
Les numéros DEM-, RM- et BR- repartent à 0001.

Rien n'est effacé sans la confirmation OUI. Option --essai : affiche ce qui serait fait, sans rien changer.
"""
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from stock.models import (Article, BonRetour, Demande, Entree, Exemplaire, LigneDemande, LigneEntree, LigneRetour,
                          LigneSortie, Magasin, MouvementEtat, Requisition, Sortie, StockEtat, TelechargementBon)


def lire_inventaire(fichier):
    """{(nom de l'article, nom du magasin): (stock, qte_minimale)} depuis le fichier d'inventaire."""
    try:
        with open(fichier, encoding="utf-8-sig", newline="") as f:
            lignes = list(csv.DictReader(f, delimiter=";"))
    except FileNotFoundError:
        raise CommandError(f"Fichier introuvable : {fichier}")
    inventaire = {}
    for n, l in enumerate(lignes, start=2):
        nom = (l.get("article") or "").strip()
        if not nom:
            continue
        valeurs = []
        for col in ("stock", "qte_minimale"):
            v = (l.get(col) or "").strip() or "0"
            if not v.isdigit():
                raise CommandError(f"Ligne {n} : « {col} » doit être un nombre entier (trouvé : « {v} »).")
            valeurs.append(int(v))
        inventaire[(nom, (l.get("magasin") or "").strip())] = tuple(valeurs)
    if not inventaire:
        raise CommandError("Le fichier d'inventaire ne contient aucun article : arrêt par sécurité.")
    return inventaire


class Command(BaseCommand):
    help = "Efface les données d'essai et remet le stock du fichier d'inventaire (confirmation OUI)."

    def add_arguments(self, parser):
        parser.add_argument("fichier", help="Fichier d'inventaire réel (CSV, séparateur ;)")
        parser.add_argument("--essai", action="store_true", help="Afficher sans rien changer")
        parser.add_argument("--oui", action="store_true", help="Ne pas demander la confirmation (tests)")

    def handle(self, fichier, essai=False, oui=False, **options):
        inventaire = lire_inventaire(fichier)

        magasins = set(Magasin.objects.values_list("nom", flat=True))
        inconnus = sorted({m for _, m in inventaire if m not in magasins})
        if inconnus:
            raise CommandError("Magasin(s) du fichier introuvable(s) dans la base : " + ", ".join(inconnus))

        a_garder, a_supprimer = [], []
        for a in Article.objects.select_related("emplacement__magasin").order_by("code"):
            cle = (a.nom.strip(), a.emplacement.magasin.nom)
            (a_garder if cle in inventaire else a_supprimer).append(a)
        trouves = {(a.nom.strip(), a.emplacement.magasin.nom) for a in a_garder}
        absents = [f"{nom} ({mag})" for (nom, mag) in inventaire if (nom, mag) not in trouves]

        w = self.stdout.write
        w("")
        w("=== Seront effacés ===")
        for libelle, qs in [
            ("demandes", Demande.objects), ("réquisitions (bons RM)", Requisition.objects),
            ("téléchargements de bons", TelechargementBon.objects), ("sorties", Sortie.objects),
            ("bons de retour", BonRetour.objects), ("réceptions (entrées en stock)", Entree.objects),
            ("lignes d'historique des mouvements", MouvementEtat.objects),
            ("exemplaires (n° de série)", Exemplaire.objects),
        ]:
            w(f"  {qs.count():>5}  {libelle}")
        w(f"  {len(a_supprimer):>5}  articles créés pendant les essais (absents du fichier) :")
        for a in a_supprimer:
            w(f"           - {a.code} – {a.nom} ({a.emplacement.magasin.nom})")
        w("")
        w(f"=== Stock remis selon l'inventaire : {len(a_garder)} articles ===")
        for a in a_garder:
            stock, mini = inventaire[(a.nom.strip(), a.emplacement.magasin.nom)]
            changement = "" if a.qte_stock == stock else f"   (aujourd'hui : {a.qte_stock})"
            w(f"  {a.code:<10} {a.nom[:45]:<45} → {stock}{changement}")
        if absents:
            w("")
            w("Attention : ces lignes du fichier n'ont pas d'article dans la base (ignorées) :")
            for x in absents:
                w(f"  - {x}")
        w("")
        w("Conservés : comptes, signatures enregistrées, départements, magasins, emplacements,")
        w("catégories, fournisseurs et chantiers. Les numéros DEM, RM et BR repartiront à 0001.")
        w("")

        if essai:
            w(self.style.WARNING("Mode essai : rien n'a été changé."))
            return
        if not oui and input("Tapez OUI pour tout effacer (définitif) : ").strip().upper() != "OUI":
            w(self.style.WARNING("Annulé : rien n'a été changé."))
            return

        with transaction.atomic():
            # Ordre imposé par les liens entre tables (du plus récent dans le circuit au plus ancien).
            LigneRetour.objects.all().delete()
            BonRetour.objects.all().delete()
            LigneSortie.objects.all().delete()
            Sortie.objects.all().delete()
            TelechargementBon.objects.all().delete()
            Requisition.objects.all().delete()
            LigneDemande.objects.all().delete()
            Demande.objects.all().delete()
            MouvementEtat.objects.all().delete()
            LigneEntree.objects.all().delete()
            Entree.objects.all().delete()
            Exemplaire.objects.all().delete()
            StockEtat.objects.all().delete()  # la répartition se refait seule à partir de la quantité
            Article.objects.filter(id__in=[a.id for a in a_supprimer]).delete()
            for a in a_garder:
                stock, mini = inventaire[(a.nom.strip(), a.emplacement.magasin.nom)]
                # suivi_serie remis à « non » : sans exemplaire, la quantité du fichier fait foi.
                Article.objects.filter(pk=a.pk).update(qte_stock=stock, qte_minimale=mini, suivi_serie=False)

        w(self.style.SUCCESS("Terminé : l'application repart propre, avec le stock de l'inventaire réel."))
