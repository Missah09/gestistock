"""Tests des corrections du 12/10/2026.  Lancer : python manage.py test stock"""
import datetime
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from stock.tests_outils import SIGNATURE
from stock.models import Article, Demande, Departement, Exemplaire, Magasin, Requisition


class CorrectionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.saisisseur = User.objects.create_user("Rasoa", password="Mot-de-passe-1", first_name="Rasoa", last_name="R")
        cls.agent = User.objects.create_user("Haja", password="Mot-de-passe-1", first_name="Haja", last_name="Rakoto")
        cls.agent.groups.add(Group.objects.get(name="Responsable Technique"))
        cls.resp = User.objects.create_user("resp", password="x")
        cls.resp.groups.add(Group.objects.get(name="Responsable Logistique"))
        cls.conso = Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank).first()
        cls.prete = Article.objects.filter(type="PRETE", emplacement__magasin=cls.ank).first()

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # compteurs d'essais de connexion ratés remis à zéro entre les tests

    def client_de(self, user):
        c = APIClient(); c.force_login(user); return c

    # ---- Point 2 : dates à l'heure de Madagascar ----
    def test_dates_a_l_heure_de_madagascar(self):
        s = self.client_de(self.saisisseur)
        minuit_et_demi = datetime.datetime(2026, 10, 11, 21, 30, tzinfo=datetime.timezone.utc)  # 12/10 à 0 h 30 à Tana
        with mock.patch("django.utils.timezone.now", return_value=minuit_et_demi):
            r = s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [{"article": self.conso.id, "quantite": 1}]},
                       format="json")
        self.assertEqual(r.status_code, 201, r.data)
        ligne = s.get("/api/demandes/?onglet=toutes").data["results"][0]
        self.assertTrue(ligne["cree_le"].startswith("2026-10-12T00:30"), ligne["cree_le"])
        self.assertTrue(ligne["cree_le"].endswith("+03:00"))

    # ---- Point 3 : toutes les erreurs ensemble ----
    def test_quantite_et_date_passee_signalees_ensemble(self):
        s = self.client_de(self.saisisseur)
        hier = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
        r = s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [
            {"article": self.conso.id, "quantite": 0},
            {"article": self.prete.id, "quantite": 1, "date_retour_prevue": hier},
            {"article": self.prete.id, "quantite": 1},
        ]}, format="json")
        self.assertEqual(r.status_code, 400)
        lignes = r.data["lignes"]
        self.assertIn("quantite", lignes[0])
        self.assertEqual(str(lignes[1]["date_retour_prevue"][0]), "Cette date est déjà passée.")
        self.assertIn("article", lignes[2])  # doublon
        self.assertIn("date_retour_prevue", lignes[2])  # retour manquant

    def test_lignes_absentes_message_inchange(self):
        r = self.client_de(self.saisisseur).post("/api/demandes/", {"magasin": self.ank.id}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("lignes", r.data)

    # ---- Point 5 : recherche sans accents ----
    def test_recherche_articles_sans_accents(self):
        a = Article.objects.filter(emplacement__magasin=self.ank).first()
        a.nom = "Jarretière optique (Tête)"; a.save()
        c = self.client_de(self.saisisseur)
        for q in ["jarretiere", "JARRETIÈRE", "tete optique", "optique JARRET", a.code.lower()]:
            noms = [x["nom"] for x in c.get("/api/articles/", {"q": q}).data["results"]]
            self.assertIn(a.nom, noms, q)
        self.assertEqual(c.get("/api/articles/", {"q": "zzz-introuvable"}).data["count"], 0)

    def test_recherche_par_numero_de_serie(self):
        e = Exemplaire.objects.exclude(numero_serie="").first()
        if e is None:
            self.skipTest("pas d'exemplaire dans les données d'exemple")
        r = self.client_de(self.saisisseur).get("/api/articles/", {"q": e.numero_serie.lower()})
        self.assertIn(e.article_id, [x["id"] for x in r.data["results"]])

    # ---- Point 6 : identifiant sans majuscules ----
    def test_connexion_sans_tenir_compte_des_majuscules(self):
        for ident in ["haja", "HAJA", " Haja "]:
            c = APIClient()
            r = c.post("/api/connexion/", {"identifiant": ident, "mot_de_passe": "Mot-de-passe-1"}, format="json")
            self.assertEqual(r.status_code, 200, (ident, r.data))
            self.assertEqual(r.data["identifiant"], "Haja")
        r = APIClient().post("/api/connexion/", {"identifiant": "haja", "mot_de_passe": "faux"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_blocage_compte_aussi_sans_majuscules(self):
        c = APIClient()
        for i in range(5):
            c.post("/api/connexion/", {"identifiant": "HAJA" if i % 2 else "haja", "mot_de_passe": "faux"}, format="json")
        r = c.post("/api/connexion/", {"identifiant": "Haja", "mot_de_passe": "Mot-de-passe-1"}, format="json")
        self.assertEqual(r.status_code, 429)

    # ---- Point 7 : le Responsable Technique valide sa propre demande → elle va au Responsable Logistique ----
    def test_agent_valide_sa_propre_demande_qui_va_au_responsable(self):
        a = self.client_de(self.agent)
        r = a.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [{"article": self.conso.id, "quantite": 2}]},
                   format="json")
        d = Demande.objects.get(id=r.data["id"])
        self.assertEqual(d.demandeur, self.agent)
        self.assertIn(d.id, [x["id"] for x in a.get("/api/a-valider/").data["results"]])
        l = d.lignes.first()
        r = a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "Mot-de-passe-1", "lignes": [{"id": l.id, "qte_accordee": 2}]},
                   format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Requisition.objects.get(demande=d).statut, Requisition.Statut.ATTENTE_VISA)
        self.assertIn(d.id, [x["id"] for x in self.client_de(self.resp).get("/api/a-viser/").data["results"]])

    # ---- Département Informatique ----
    def test_departement_informatique(self):
        self.assertTrue(Departement.objects.filter(nom="Informatique").exists())

    def test_admin_rattache_a_informatique(self):
        import importlib
        from django.apps import apps
        migration = importlib.import_module("stock.migrations.0013_departement_informatique")
        admin = User.objects.create_superuser("admin", password="x")
        admin.profil.departement = Departement.objects.get(nom="Technique"); admin.profil.save()
        migration.ajouter(apps, None)
        admin.profil.refresh_from_db()
        self.assertEqual(admin.profil.departement.nom, "Informatique")
        self.assertEqual(Departement.objects.filter(nom="Informatique").count(), 1)
