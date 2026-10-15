"""Tests de l'écran « Sorties » : confirmation de la remise, stock diminué, copie d'archive (12/10/2026).
Lancer : python manage.py test stock"""
import datetime

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.db.models import Count
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from stock.models import Article, Demande, Exemplaire, Magasin, Requisition, Sortie
from stock.tests_outils import SIGNATURE


@override_settings(GESTISTOCK_EMAILS=False)
class SortiesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.saisisseur = User.objects.create_user("rabe", password="x", first_name="Jean", last_name="Rabe")
        cls.agent = User.objects.create_user("agent", password="x", first_name="Hery", last_name="Rasoa")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.resp = User.objects.create_user("resp", password="x", first_name="Paul", last_name="Randria")
        cls.resp.groups.add(Group.objects.get(name="Responsable HBC"))
        conso = Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank).order_by("code")
        cls.c1, cls.c2 = list(conso[:2])
        Article.objects.filter(id__in=[cls.c1.id, cls.c2.id]).update(qte_stock=50)
        # Matériel suivi par n° de série, avec au moins 2 exemplaires en stock
        cls.serie = (Article.objects.filter(type="PRETE", emplacement__magasin=cls.ank)
                     .annotate(n=Count("exemplaires")).filter(n__gt=0).first())
        for i in range(2):
            Exemplaire.objects.create(article=cls.serie, numero_serie=f"TEST-SN-{i}")

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.saisisseur)
        self.a = APIClient(); self.a.force_login(self.agent)
        self.r = APIClient(); self.r.force_login(self.resp)

    def bon(self, imprimer=True, avec_serie=False):
        """Demande validée (c2 retiré à 0), visée et, si `imprimer`, téléchargée par l'Agent Logistique."""
        lignes = [{"article": self.c1.id, "quantite": 10}, {"article": self.c2.id, "quantite": 2}]
        if avec_serie:
            lignes.append({"article": self.serie.id, "quantite": 2,
                           "date_retour_prevue": (timezone.localdate() + datetime.timedelta(days=5)).isoformat()})
        rep = self.s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": lignes}, format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        d = Demande.objects.get(id=rep.data["id"])
        ls = list(d.lignes.all())
        accord = [{"id": ls[0].id, "qte_accordee": 8}, {"id": ls[1].id, "qte_accordee": 0}]
        accord += [{"id": l.id, "qte_accordee": l.quantite} for l in ls[2:]]
        self.assertEqual(self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": accord},
                                     format="json").status_code, 200)
        self.assertEqual(self.r.post(f"/api/a-viser/{d.id}/viser/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json").status_code, 200)
        if imprimer:
            self.assertEqual(self.a.get(f"/api/requisitions/{d.id}/pdf/").status_code, 200)
        return d

    def confirmer(self, d, lignes, date=None, **extra):
        return self.a.post(f"/api/sorties/{d.id}/confirmer/", {
            "date_remise": (date or timezone.localdate()).isoformat(), "lignes": lignes, **extra}, format="json")

    def stock(self, article):
        return Article.objects.get(id=article.id).qte_stock

    # ---------------------------------------------------------------- Droits et liste
    def test_droits(self):
        d = self.bon()
        self.assertEqual(self.a.get("/api/sorties/").status_code, 200)
        self.assertEqual(self.r.get("/api/sorties/").status_code, 403)
        self.assertEqual(self.s.get("/api/sorties/").status_code, 403)
        self.assertEqual(APIClient().get("/api/sorties/").status_code, 401)
        self.assertEqual(self.r.post(f"/api/sorties/{d.id}/confirmer/", {}, format="json").status_code, 403)

    def test_seuls_les_bons_imprimes_et_compteurs(self):
        imprime = self.bon()
        pas_imprime = self.bon(imprimer=False)
        rep = self.a.get("/api/sorties/?onglet=a_confirmer")
        self.assertEqual([x["id"] for x in rep.data["results"]], [imprime.id])
        self.assertEqual(rep.data["compteurs"], {"a_confirmer": 1, "confirmees": 0, "toutes": 1})
        self.assertEqual(self.a.get("/api/compteurs/").data["a_confirmer"], 1)
        rep = self.confirmer(pas_imprime, [])
        self.assertEqual(rep.status_code, 400)
        self.assertIn("pas encore imprimé", rep.data["general"][0])

    # ---------------------------------------------------------------- Confirmation
    def test_confirmation_diminue_le_stock(self):
        d = self.bon()
        l1 = d.lignes.order_by("id").first()
        rep = self.confirmer(d, [{"id": l1.id, "qte_livree": 6}], magasinier="Rakoto", observation="2 en rupture")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertIn("livraison partielle", rep.data["message"])
        self.assertEqual(self.stock(self.c1), 44)
        self.assertEqual(self.stock(self.c2), 50)  # retiré du bon : pas touché
        s = Sortie.objects.get(requisition__demande=d)
        self.assertEqual((s.magasinier, s.confirmee_par, s.lignes.get().qte_livree, s.lignes.get().qte_bon),
                         ("Rakoto", self.agent, 6, 8))
        sortie = rep.data["demande"]["requisition"]["sortie"]
        self.assertEqual(sortie["lignes"][str(l1.id)]["qte_livree"], 6)
        # Onglets et compteurs
        self.assertEqual(self.a.get("/api/sorties/").data["compteurs"], {"a_confirmer": 0, "confirmees": 1, "toutes": 1})
        self.assertEqual(self.a.get("/api/compteurs/").data["a_confirmer"], 0)
        # Pas deux fois
        rep = self.confirmer(d, [{"id": l1.id, "qte_livree": 6}])
        self.assertEqual(rep.status_code, 400)
        self.assertIn("déjà été confirmée", rep.data["general"][0])
        self.assertEqual(self.stock(self.c1), 44)
        # Le demandeur voit la remise dans « Mes demandes »
        self.assertIsNotNone(self.s.get(f"/api/demandes/{d.id}/").data["requisition"]["sortie"])

    def test_controles(self):
        d = self.bon()
        l1 = d.lignes.order_by("id").first()
        # Ligne manquante, plus que le bon, pas un nombre
        self.assertIn(str(l1.id), self.confirmer(d, []).data["lignes"])
        rep = self.confirmer(d, [{"id": l1.id, "qte_livree": 9}])
        self.assertIn("Plus que la quantité du bon", rep.data["lignes"][str(l1.id)][0])
        rep = self.confirmer(d, [{"id": l1.id, "qte_livree": "-1"}])
        self.assertEqual(rep.status_code, 400)
        # Tout à 0
        rep = self.confirmer(d, [{"id": l1.id, "qte_livree": 0}])
        self.assertIn("Toutes les quantités livrées sont à 0", rep.data["general"][0])
        # Dates : futur, avant le visa, absente
        demain = timezone.localdate() + datetime.timedelta(days=1)
        self.assertIn("futur", self.confirmer(d, [{"id": l1.id, "qte_livree": 1}], date=demain).data["date_remise"][0])
        hier = timezone.localdate() - datetime.timedelta(days=1)
        self.assertIn("visé le", self.confirmer(d, [{"id": l1.id, "qte_livree": 1}], date=hier).data["date_remise"][0])
        rep = self.a.post(f"/api/sorties/{d.id}/confirmer/", {"lignes": [{"id": l1.id, "qte_livree": 1}]}, format="json")
        self.assertIn("date_remise", rep.data)
        # Stock insuffisant dans l'application
        Article.objects.filter(id=self.c1.id).update(qte_stock=3)
        rep = self.confirmer(d, [{"id": l1.id, "qte_livree": 5}])
        self.assertIn("n'indique que 3", rep.data["lignes"][str(l1.id)][0])
        # Rien n'a changé
        self.assertFalse(Sortie.objects.exists())
        self.assertEqual(self.stock(self.c1), 3)

    def test_materiel_suivi_par_numero_de_serie(self):
        d = self.bon(avec_serie=True)
        l1, _, l3 = d.lignes.order_by("id")
        rep = self.a.get(f"/api/sorties/{d.id}/")
        ligne = [x for x in rep.data["lignes"] if x["id"] == l3.id][0]
        self.assertTrue(ligne["article"]["suivi_par_serie"])
        dispo = {e["numero_serie"]: e["id"] for e in ligne["exemplaires_en_stock"]}
        self.assertIn("TEST-SN-0", dispo)
        # Un exemplaire déjà prêté est refusé
        deja = Exemplaire.objects.filter(article=self.serie, statut="PRETE").first() or \
            Exemplaire.objects.create(article=self.serie, numero_serie="TEST-PRETE", statut="PRETE")
        rep = self.confirmer(d, [{"id": l1.id, "qte_livree": 8}, {"id": l3.id, "exemplaires": [deja.id]}])
        self.assertIn("n'est plus en stock", rep.data["lignes"][str(l3.id)][0])
        # Trois cochés pour deux sur le bon
        Exemplaire.objects.create(article=self.serie, numero_serie="TEST-SN-2")
        trois = list(Exemplaire.objects.filter(numero_serie__startswith="TEST-SN-").values_list("id", flat=True))
        rep = self.confirmer(d, [{"id": l1.id, "qte_livree": 8}, {"id": l3.id, "exemplaires": trois}])
        self.assertIn("ne peut pas remettre plus", rep.data["lignes"][str(l3.id)][0])
        # Un seul remis
        rep = self.confirmer(d, [{"id": l1.id, "qte_livree": 8}, {"id": l3.id, "exemplaires": [dispo["TEST-SN-0"]]}])
        self.assertEqual(rep.status_code, 200, rep.data)
        e = Exemplaire.objects.get(numero_serie="TEST-SN-0")
        self.assertEqual((e.statut, e.prete_a), ("PRETE", "Jean Rabe"))
        self.assertEqual(Exemplaire.objects.get(numero_serie="TEST-SN-1").statut, "EN_STOCK")
        self.assertEqual(rep.data["demande"]["requisition"]["sortie"]["lignes"][str(l3.id)]["exemplaires"], ["TEST-SN-0"])

    def test_copie_d_archive(self):
        d = self.bon()
        self.assertEqual(self.a.get(f"/api/sorties/{d.id}/pdf/").status_code, 404)
        l1 = d.lignes.order_by("id").first()
        self.assertEqual(self.confirmer(d, [{"id": l1.id, "qte_livree": 8}], magasinier="Rakoto").status_code, 200)
        rep = self.a.get(f"/api/sorties/{d.id}/pdf/")
        self.assertEqual(rep.status_code, 200)
        self.assertTrue(rep.content.startswith(b"%PDF"))
        self.assertIn("-archive.pdf", rep["Content-Disposition"])
        self.assertEqual(Requisition.objects.get(demande=d).telechargements.count(), 1)  # l'archive ne compte pas
