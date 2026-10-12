"""Charge les données d'exemple de la maquette.

Utilisation :  python manage.py charger_exemples
On peut la relancer sans risque : elle met à jour au lieu de dupliquer.
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from stock.models import Article, Categorie, Emplacement, Exemplaire, Fournisseur, Magasin

CATEGORIES = [("Câbles", "CAB"), ("Raccordement", "RAC"), ("Boîtiers", "BOI"),
              ("Équipements", "ACT"), ("Outillage", "OUT")]

# Les deux magasins permanents de l'entreprise.
MAGASINS = ["Ankorondrano", "Manandriana"]
# Anciens noms d'exemple, renommés si on relance la commande sur une base existante.
ANCIENS_NOMS = {"Magasin principal": "Ankorondrano", "Parc extérieur": "Manandriana"}

EMPLACEMENTS = [("Parc à tourets", "Manandriana"), ("Bac C-04", "Ankorondrano"),
                ("Bac C-06", "Ankorondrano"), ("Rayon B1", "Ankorondrano"),
                ("Rayon B2", "Ankorondrano"), ("Armoire A1", "Ankorondrano"),
                ("Armoire fermée", "Ankorondrano")]

FOURNISSEURS = [("Fibre Équipement SARL", "M. Rabe", "034 00 000 01"),
                ("Optique Connect", "Mme Raso", "034 00 000 02"),
                ("Réseau Pro Fournitures", "M. Andry", "034 00 000 03")]

C, P = Article.Type.CONSOMMABLE, Article.Type.PRETE
# code, nom, catégorie, type, unité, qté stock, qté min, emplacement, prix, fournisseur, réf four., réf fab., marque, modèle
ARTICLES = [
    ("CAB-0012", "Câble 12 fibres", "Câbles", C, "m", 14600, 5000, "Parc à tourets", "2800", "Optique Connect", "OC-C12", "G652D-12", "OptiCâble", "ADSS 12FO"),
    ("CAB-0048", "Câble 48 fibres", "Câbles", C, "m", 3200, 5000, "Parc à tourets", "7500", "Optique Connect", "OC-C48", "G652D-48", "OptiCâble", "ADSS 48FO"),
    ("RAC-0110", "Connecteurs SC/APC", "Raccordement", C, "piece", 40, 200, "Bac C-04", "3500", "Réseau Pro Fournitures", "RP-SCAPC", "SC-APC-09", "ConnectPlus", "SC/APC 0,9"),
    ("RAC-0120", "Pigtails SC/APC 1,5 m", "Raccordement", C, "piece", 60, 100, "Bac C-06", "6000", "Réseau Pro Fournitures", "RP-PIG15", "PT-SCAPC-15", "ConnectPlus", "PT-15"),
    ("BOI-0301", "Prises PTO", "Boîtiers", C, "piece", 85, 150, "Rayon B2", "12000", "Réseau Pro Fournitures", "RP-PTO1", "PTO-1F", "BoxNet", "PTO 1 port"),
    ("BOI-0148", "Boîtiers d'épissure 48 FO", "Boîtiers", C, "piece", 22, 10, "Rayon B1", "185000", "Optique Connect", "OC-BE48", "BE-48-IP68", "BoxNet", "BE48"),
    ("ACT-0401", "Box ONT (clients)", "Équipements", C, "piece", 134, 50, "Armoire A1", "145000", "Fibre Équipement SARL", "FE-ONT-1", "ONT-G1", "NetHome", "G-1000"),
    ("OUT-0101", "Soudeuses", "Outillage", P, "piece", 0, 2, "Armoire fermée", "24500000", "Fibre Équipement SARL", "FE-SOU-70", "FS70-KIT-EU", "Fusiona", "FS-70"),
    ("OUT-0120", "Réflectomètres OTDR", "Outillage", P, "piece", 0, 2, "Armoire fermée", "18000000", "Fibre Équipement SARL", "FE-OTDR-3", "OT3-SM", "Fusiona", "OT-300"),
    ("OUT-0205", "Électrodes de soudeuse", "Outillage", C, "paire", 0, 4, "Armoire fermée", "95000", "Fibre Équipement SARL", "FE-ELEC-70", "EL-FS70", "Fusiona", "EL-70"),
]

E, PR = Exemplaire.Statut.EN_STOCK, Exemplaire.Statut.PRETE
# article, n° série, code immo, étalonnage, statut, prêté à, chantier
EXEMPLAIRES = [
    ("OUT-0101", "SN-11873", "IMMO-2024-015", date(2027, 3, 12), E, "", ""),
    ("OUT-0101", "SN-11874", "IMMO-2024-016", date(2027, 3, 12), PR, "J. Rakoto", "Ivato"),
    ("OUT-0101", "SN-11902", "IMMO-2024-021", date(2027, 6, 5), E, "", ""),
    ("OUT-0101", "SN-12040", "IMMO-2025-004", date(2026, 11, 20), PR, "H. Randria", "Ambohidratrimo"),
    ("OUT-0101", "SN-12041", "IMMO-2025-005", date(2026, 11, 20), E, "", ""),
    ("OUT-0101", "SN-12377", "", date(2027, 9, 8), E, "", ""),
    ("OUT-0120", "OT-5501", "IMMO-2023-031", date(2027, 1, 15), E, "", ""),
    ("OUT-0120", "OT-5502", "IMMO-2023-032", date(2027, 1, 15), E, "", ""),
    ("OUT-0120", "OT-5810", "IMMO-2025-011", date(2027, 4, 2), E, "", ""),
    ("OUT-0120", "OT-5811", "IMMO-2025-012", date(2027, 4, 2), PR, "F. Rasoa", "Talatamaty"),
]


class Command(BaseCommand):
    help = "Charge les articles et exemplaires d'exemple de la maquette."

    @transaction.atomic
    def handle(self, *args, **options):
        cats = {n: Categorie.objects.update_or_create(nom=n, defaults={"prefixe": p})[0] for n, p in CATEGORIES}
        for ancien, nouveau in ANCIENS_NOMS.items():
            if not Magasin.objects.filter(nom=nouveau).exists():
                Magasin.objects.filter(nom=ancien).update(nom=nouveau)
        mags = {n: Magasin.objects.update_or_create(nom=n, defaults={"type": Magasin.Type.MAGASIN, "actif": True})[0]
                for n in MAGASINS}
        emps = {}
        for n, m in EMPLACEMENTS:
            e = Emplacement.objects.filter(nom=n).first() or Emplacement(nom=n)
            e.magasin = mags[m]
            e.save()
            emps[n] = e
        fours = {n: Fournisseur.objects.update_or_create(nom=n, defaults={"contact": c, "telephone": t})[0]
                 for n, c, t in FOURNISSEURS}

        for (code, nom, cat, typ, unite, qte, qmin, emp, prix, four, rf, rfab, marque, modele) in ARTICLES:
            Article.objects.update_or_create(code=code, defaults=dict(
                nom=nom, categorie=cats[cat], type=typ, unite=unite, qte_stock=qte, qte_minimale=qmin,
                emplacement=emps[emp], prix_unitaire=Decimal(prix), fournisseur=fours[four],
                ref_fournisseur=rf, ref_fabricant=rfab, marque=marque, modele=modele))

        for (code, sn, immo, etal, statut, a, chantier) in EXEMPLAIRES:
            Exemplaire.objects.update_or_create(numero_serie=sn, defaults=dict(
                article=Article.objects.get(code=code), code_immo=immo, date_etalonnage=etal,
                statut=statut, prete_a=a, chantier=chantier))

        self.stdout.write(self.style.SUCCESS(
            f"OK : {Article.objects.count()} articles, {Exemplaire.objects.count()} exemplaires, "
            f"{Fournisseur.objects.count()} fournisseurs, {Categorie.objects.count()} catégories, "
            f"{Magasin.objects.count()} magasins."))
