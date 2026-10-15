"""Tests de l'état du produit (Neuf · Bon · Moyen · Mauvais) et de l'écran « Retours » (12/10/2026).
Lancer : python manage.py test stock"""
import datetime

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.db.models import Count
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from stock import etats
from stock.models import Article, BonRetour, Demande, Exemplaire, LigneSortie, Magasin, MouvementEtat, StockEtat
from stock.tests_outils import SIGNATURE


@override_settings(GESTISTOCK_EMAILS=False)
class EtatEtRetoursTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.saisisseur = User.objects.create_user("rabe", password="x", first_name="Jean", last_name="Rabe")
        cls.agent = User.objects.create_user("agent", password="x", first_name="Hery", last_name="Rasoa")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.resp = User.objects.create_user("resp", password="x", first_name="Paul", last_name="Randria")
        cls.resp.groups.add(Group.objects.get(name="Responsable HBC"))
        cls.conso = Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank).order_by("code").first()
        Article.objects.filter(id=cls.conso.id).update(qte_stock=50)
        # Matériel prêté suivi par quantité (casques) : 10 en « Bon état »
        cls.casque = Article.objects.create(nom="Casque de chantier", categorie=cls.conso.categorie, type="PRETE",
                                            emplacement=cls.conso.emplacement, qte_stock=10)
        cls.serie = (Article.objects.filter(type="PRETE", emplacement__magasin=cls.ank)
                     .annotate(n=Count("exemplaires")).filter(n__gt=0).first())
        for i in range(2):
            Exemplaire.objects.create(article=cls.serie, numero_serie=f"RT-SN-{i}", etat="BON", code_immo=f"IMMO-{i}")

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.saisisseur)
        self.a = APIClient(); self.a.force_login(self.agent)
        self.r = APIClient(); self.r.force_login(self.resp)

    def stock(self, article):
        return Article.objects.get(id=article.id).qte_stock

    def par_etat(self, article):
        return etats.repartition(Article.objects.get(id=article.id))["etats"]

    def sortie(self, retour=None, casques=8, avec_serie=True):
        """Demande de casques (et de 2 n° de série) jusqu'à la sortie confirmée."""
        retour = retour or (timezone.localdate() + datetime.timedelta(days=5))
        lignes = [{"article": self.casque.id, "quantite": casques, "date_retour_prevue": retour.isoformat()}]
        if avec_serie:
            lignes.append({"article": self.serie.id, "quantite": 2, "date_retour_prevue": retour.isoformat()})
        lignes.append({"article": self.conso.id, "quantite": 3})
        rep = self.s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": lignes}, format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        d = Demande.objects.get(id=rep.data["id"])
        accord = [{"id": l.id, "qte_accordee": l.quantite} for l in d.lignes.all()]
        self.assertEqual(self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": accord},
                                     format="json").status_code, 200)
        self.assertEqual(self.r.post(f"/api/a-viser/{d.id}/viser/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json").status_code, 200)
        self.assertEqual(self.a.get(f"/api/requisitions/{d.id}/pdf/").status_code, 200)
        ls = {l.article_id: l for l in d.lignes.all()}
        envoi = [{"id": ls[self.casque.id].id, "qte_livree": casques}, {"id": ls[self.conso.id].id, "qte_livree": 3}]
        if avec_serie:
            ids = list(Exemplaire.objects.filter(numero_serie__startswith="RT-SN-").values_list("id", flat=True))
            envoi.append({"id": ls[self.serie.id].id, "exemplaires": ids})
        rep = self.a.post(f"/api/sorties/{d.id}/confirmer/", {"date_remise": timezone.localdate().isoformat(),
                                                               "lignes": envoi}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        return d

    # ---------------------------------------------------------------- État du produit
    def test_reception_avec_etat(self):
        rep = self.a.post("/api/entrees/", {"date_reception": timezone.localdate().isoformat(), "magasin": self.ank.id,
                                            "lignes": [{"article": self.casque.id, "quantite": 4, "etat": "MOYEN"},
                                                       {"article": self.conso.id, "quantite": 2, "etat": "MAUVAIS"}]},
                          format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        self.assertEqual(self.stock(self.casque), 14)
        self.assertEqual(self.par_etat(self.casque)["MOYEN"], 4)
        self.assertEqual(self.par_etat(self.casque)["BON"], 10)  # stock d'avant : « Bon » (matériel prêté)
        self.assertEqual(self.stock(self.conso), 52)  # « Mauvais » : disponible comme les autres états
        self.assertEqual(self.par_etat(self.conso)["MAUVAIS"], 2)
        self.assertEqual(MouvementEtat.objects.filter(type="RECEPTION").count(), 2)
        # Anciens états refusés
        rep = self.a.post("/api/entrees/", {"date_reception": timezone.localdate().isoformat(), "magasin": self.ank.id,
                                            "lignes": [{"article": self.conso.id, "quantite": 1, "etat": "A_REPARER"}]},
                          format="json")
        self.assertEqual(rep.status_code, 400)
        # Liste Articles : répartition et filtre « État »
        rep = self.a.get("/api/articles/?etat=MAUVAIS")
        self.assertEqual([x["id"] for x in rep.data["results"]], [self.conso.id])
        self.assertEqual(rep.data["results"][0]["repartition"]["de_cote"], 0)

    def test_sortie_avec_plusieurs_etats(self):
        etats.ajouter(Article.objects.get(id=self.casque.id), "MOYEN", 3)
        retour = (timezone.localdate() + datetime.timedelta(days=5)).isoformat()
        rep = self.s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [
            {"article": self.casque.id, "quantite": 5, "date_retour_prevue": retour}]}, format="json")
        d = Demande.objects.get(id=rep.data["id"])
        l = d.lignes.get()
        self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l.id, "qte_accordee": 5}]},
                    format="json")
        self.r.post(f"/api/a-viser/{d.id}/viser/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
        self.a.get(f"/api/requisitions/{d.id}/pdf/")
        base = {"date_remise": timezone.localdate().isoformat()}
        # Deux états en stock : il faut dire lesquels sont sortis
        rep = self.a.post(f"/api/sorties/{d.id}/confirmer/", {**base, "lignes": [{"id": l.id, "qte_livree": 5}]}, format="json")
        self.assertEqual(rep.status_code, 400)
        self.assertIn("état", rep.data["lignes"][str(l.id)][0])
        rep = self.a.post(f"/api/sorties/{d.id}/confirmer/", {**base, "lignes": [
            {"id": l.id, "qte_livree": 5, "etats": {"BON": 2, "MOYEN": 2}}]}, format="json")
        self.assertEqual(rep.status_code, 400)  # 4 ≠ 5
        rep = self.a.post(f"/api/sorties/{d.id}/confirmer/", {**base, "lignes": [
            {"id": l.id, "qte_livree": 5, "etats": {"BON": 2, "MOYEN": 3}}]}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertEqual(self.par_etat(self.casque), {"NEUF": 0, "BON": 8, "MOYEN": 0, "MAUVAIS": 0})
        self.assertEqual(self.stock(self.casque), 8)
        self.assertEqual(LigneSortie.objects.get(ligne_demande=l).etats, {"BON": 2, "MOYEN": 3})
        # Copie d'archive avec la colonne État
        self.assertEqual(self.a.get(f"/api/sorties/{d.id}/pdf/").status_code, 200)

    # ---------------------------------------------------------------- Retours
    def test_circuit_du_retour_partiel(self):
        d = self.sortie()
        self.assertEqual(self.stock(self.casque), 2)
        self.assertEqual(self.r.get("/api/retours/").status_code, 403)
        rep = self.a.get("/api/retours/")
        self.assertEqual(rep.data["compteurs"]["attendu"], 1)
        retour = rep.data["results"][0]["retour"]
        self.assertEqual(retour["reste_total"], 10)  # 8 casques + 2 n° de série ; jamais le consommable
        self.assertEqual({l["article"]["id"] for l in retour["lignes"]}, {self.casque.id, self.serie.id})

        # Bon de retour : signature obligatoire, un seul à la fois
        self.assertEqual(self.a.post(f"/api/retours/{d.id}/bon/", {}, format="json").status_code, 400)
        rep = self.a.post(f"/api/retours/{d.id}/bon/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        b = BonRetour.objects.get(id=rep.data["bon"])
        self.assertTrue(b.numero.startswith(f"BR-{timezone.localdate().year}-"))
        self.assertEqual(self.a.post(f"/api/retours/{d.id}/bon/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json").status_code, 400)
        pdf = self.a.get(f"/api/retours/bons/{b.id}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        bon = rep.data["demande"]["retour"]["bon_ouvert"]
        ligne_casque = next(l for l in bon["lignes"] if l["article"]["id"] == self.casque.id)
        ligne_serie = next(l for l in bon["lignes"] if l["article"]["id"] == self.serie.id)
        ex = [e["id"] for e in ligne_serie["exemplaires"]]
        url = f"/api/retours/bons/{b.id}/confirmer/"
        base = {"date_retour": timezone.localdate().isoformat(), "magasinier": "Koto", "rendu_par": "Jean Rabe"}
        # Plus que le reste : refusé ; date future : refusée ; rien rendu : refusé
        rep = self.a.post(url, {**base, "lignes": [{"id": ligne_casque["id"], "etats": {"BON": 9}},
                                                   {"id": ligne_serie["id"], "exemplaires": {}}]}, format="json")
        self.assertEqual(rep.status_code, 400)
        rep = self.a.post(url, {**base, "date_retour": (timezone.localdate() + datetime.timedelta(days=1)).isoformat(),
                                "lignes": [{"id": ligne_casque["id"], "etats": {"BON": 1}},
                                           {"id": ligne_serie["id"], "exemplaires": {}}]}, format="json")
        self.assertIn("date_retour", rep.data)
        rep = self.a.post(url, {**base, "lignes": [{"id": ligne_casque["id"], "etats": {}},
                                                   {"id": ligne_serie["id"], "exemplaires": {}}]}, format="json")
        self.assertEqual(rep.status_code, 400)

        # Retour partiel : 6 casques (4 bon, 2 mauvais) et 1 n° de série en mauvais état : tout redevient disponible
        rep = self.a.post(url, {**base, "lignes": [
            {"id": ligne_casque["id"], "etats": {"BON": 4, "MAUVAIS": 2}, "observation": "2 fêlés"},
            {"id": ligne_serie["id"], "exemplaires": {str(ex[0]): "MAUVAIS"}}]}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertIn("Reste à rendre : 3", rep.data["message"])
        self.assertEqual(self.stock(self.casque), 8)
        self.assertEqual(self.par_etat(self.casque)["MAUVAIS"], 2)
        e0 = Exemplaire.objects.get(id=ex[0])
        self.assertEqual((e0.statut, e0.etat, e0.prete_a), ("EN_STOCK", "MAUVAIS", ""))
        self.assertEqual(self.a.get(f"/api/retours/bons/{b.id}/pdf/").status_code, 200)  # copie d'archive

        # Second bon : seulement ce qui reste
        rep = self.a.post(f"/api/retours/{d.id}/bon/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
        bon2 = rep.data["demande"]["retour"]["bon_ouvert"]
        self.assertEqual(sorted(l["qte_attendue"] for l in bon2["lignes"]), [1, 2])
        l2c = next(l for l in bon2["lignes"] if l["article"]["id"] == self.casque.id)
        l2s = next(l for l in bon2["lignes"] if l["article"]["id"] == self.serie.id)
        self.assertEqual([e["id"] for e in l2s["exemplaires"]], [ex[1]])
        rep = self.a.post(f"/api/retours/bons/{bon2['id']}/confirmer/", {**base, "lignes": [
            {"id": l2c["id"], "etats": {"MOYEN": 2}}, {"id": l2s["id"], "exemplaires": {str(ex[1]): "BON"}}]}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertIn("est rentré", rep.data["message"])
        self.assertTrue(rep.data["demande"]["retour"]["solde"])
        self.assertEqual(self.a.get("/api/retours/?onglet=soldes").data["count"], 1)
        self.assertEqual(Exemplaire.objects.get(id=ex[1]).statut, "EN_STOCK")
        self.assertEqual(self.a.post(f"/api/retours/{d.id}/bon/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json").status_code, 400)

    def test_annuler_un_bon_et_retards(self):
        d = self.sortie(avec_serie=False)
        # Retour prévu dépassé : compté en retard
        d.lignes.filter(article=self.casque).update(date_retour_prevue=timezone.localdate() - datetime.timedelta(days=1))
        self.assertEqual(self.a.get("/api/compteurs/").data["retours_en_retard"], 1)
        self.assertEqual(self.a.get("/api/retours/?onglet=en_retard").data["count"], 1)
        rep = self.a.post(f"/api/retours/{d.id}/bon/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
        b = rep.data["bon"]
        rep = self.a.post(f"/api/retours/bons/{b}/annuler/")
        self.assertEqual(rep.status_code, 200)
        self.assertIsNone(rep.data["demande"]["retour"]["bon_ouvert"])
        self.assertEqual(self.a.post(f"/api/retours/{d.id}/bon/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json").status_code, 201)

    # ---------------------------------------------------------------- « Matériel à réparer » retiré
    def test_ecran_materiel_a_reparer_retire(self):
        self.assertEqual(self.a.get("/api/a-reparer/").status_code, 404)

    def test_conversion_des_anciens_etats(self):
        """Migration 0019 : Usagé → Moyen ; À réparer / Hors service → Mauvais, remis dans le stock disponible."""
        from importlib import import_module
        from django.apps import apps
        migration = import_module("stock.migrations.0019_quatre_etats")
        casque = Article.objects.get(id=self.casque.id)  # 10 disponibles
        StockEtat.objects.update_or_create(article=casque, etat="BON", defaults={"quantite": 7})
        StockEtat.objects.create(article=casque, etat="USAGE", quantite=3)
        StockEtat.objects.create(article=casque, etat="A_REPARER", quantite=2)
        StockEtat.objects.create(article=casque, etat="HORS_SERVICE", quantite=1)
        e = Exemplaire.objects.get(numero_serie="RT-SN-0")
        Exemplaire.objects.filter(id=e.id).update(statut="REPARATION", etat="A_REPARER")
        avant = self.a.get(f"/api/articles/{self.serie.id}/").data["qte_disponible"]  # l'exemplaire « À réparer » n'y est pas
        migration.convertir(apps, None)
        self.assertEqual(self.stock(casque), 13)
        self.assertEqual(self.par_etat(casque), {"NEUF": 0, "BON": 7, "MOYEN": 3, "MAUVAIS": 3})
        self.assertFalse(StockEtat.objects.filter(etat__in=["USAGE", "A_REPARER", "HORS_SERVICE"]).exists())
        e.refresh_from_db()
        self.assertEqual((e.statut, e.etat), ("EN_STOCK", "MAUVAIS"))
        self.assertEqual(self.a.get(f"/api/articles/{self.serie.id}/").data["qte_disponible"], avant + 1)
        self.assertEqual(MouvementEtat.objects.filter(type="CORRECTION").count(), 3)


@override_settings(GESTISTOCK_EMAILS=False)
class NumeroEtImpressionTests(TestCase):
    """N° de réquisition attribué au clic sur « Valider » ; « Imprimer » marque le bon « Imprimée » (12/10/2026)."""

    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.s_user = User.objects.create_user("rabe", password="x")
        cls.agent = User.objects.create_user("agent", password="x")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.resp = User.objects.create_user("resp", password="x")
        cls.resp.groups.add(Group.objects.get(name="Responsable HBC"))
        cls.conso = Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank).first()
        Article.objects.filter(id=cls.conso.id).update(qte_stock=50)

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.s_user)
        self.a = APIClient(); self.a.force_login(self.agent)
        self.r = APIClient(); self.r.force_login(self.resp)

    def demande(self):
        rep = self.s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [{"article": self.conso.id, "quantite": 2}]},
                          format="json")
        return Demande.objects.get(id=rep.data["id"])

    def test_numero_attribue_au_clic_sur_valider(self):
        annee = timezone.localdate().year
        d1, d2 = self.demande(), self.demande()
        rep = self.a.post(f"/api/a-valider/{d1.id}/numero/")
        self.assertEqual(rep.data["numero"], f"RM-{annee}-0001")
        self.assertEqual(self.a.post(f"/api/a-valider/{d1.id}/numero/").data["numero"], f"RM-{annee}-0001")  # gardé
        self.assertEqual(self.a.post(f"/api/a-valider/{d2.id}/numero/").data["numero"], f"RM-{annee}-0002")
        self.assertEqual(self.s.post(f"/api/a-valider/{d1.id}/numero/").status_code, 403)
        # d2 validée d'abord : elle garde son n°
        l2 = d2.lignes.get()
        rep = self.a.post(f"/api/a-valider/{d2.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l2.id, "qte_accordee": 2}]},
                          format="json")
        self.assertEqual(rep.data["demande"]["requisition"]["numero"], f"RM-{annee}-0002")
        # d1 refusée : son n° est libéré ; une nouvelle demande validée sans clic préalable prend le suivant libre
        self.a.post(f"/api/a-valider/{d1.id}/refuser/", {"motif": "non"}, format="json")
        d3 = self.demande()
        l3 = d3.lignes.get()
        rep = self.a.post(f"/api/a-valider/{d3.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l3.id, "qte_accordee": 1}]},
                          format="json")
        self.assertEqual(rep.data["demande"]["requisition"]["numero"], f"RM-{annee}-0003")

    def test_imprimer_marque_le_bon(self):
        d = self.demande()
        l = d.lignes.get()
        self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l.id, "qte_accordee": 2}]},
                    format="json")
        self.r.post(f"/api/a-viser/{d.id}/viser/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
        rep = self.r.get(f"/api/requisitions/{d.id}/pdf/?impression=1")  # Responsable : consultation
        self.assertTrue(rep["Content-Disposition"].startswith("inline"))
        self.assertEqual(self.a.get("/api/requisitions/?onglet=imprimees").data["count"], 0)
        self.a.get(f"/api/requisitions/{d.id}/pdf/?impression=1")
        rep = self.a.get("/api/requisitions/?onglet=imprimees")
        self.assertEqual(rep.data["count"], 1)
        self.assertEqual(rep.data["results"][0]["requisition"]["nb_impressions"], 2)
