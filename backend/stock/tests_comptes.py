"""Tests des comptes, rôles et départements (11/10/2026).  Lancer : python manage.py test stock"""
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from stock.models import Article, Demande, Departement, Magasin


class ComptesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("charger_exemples", verbosity=0)
        cls.tech = Departement.objects.get(nom="Technique")
        cls.saisisseur = User.objects.create_user("rabe", password="Mdp-rabe-2026", first_name="Jean", last_name="Rabe")
        cls.saisisseur.profil.departement = cls.tech; cls.saisisseur.profil.save()
        cls.autre = User.objects.create_user("rasoa", password="Mdp-rasoa-2026")
        cls.agent = User.objects.create_user("agent", password="Mdp-agent-2026")
        cls.agent.groups.add(Group.objects.get(name="Responsable Technique"))
        cls.resp = User.objects.create_user("resp", password="Mdp-resp-2026")
        cls.resp.groups.add(Group.objects.get(name="Responsable Logistique"))
        cls.ank = Magasin.objects.get(nom="Ankorondrano")

    def setUp(self):
        cache.clear()
        self.c = APIClient()

    def demande(self, client):
        a = Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=self.ank).first()
        return client.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [{"article": a.id, "quantite": 1}]}, format="json")

    def test_donnees_initiales(self):
        self.assertEqual(sorted(Departement.objects.values_list("nom", flat=True)), ["Finance", "Informatique", "Logistique", "Technique"])
        self.assertTrue(Group.objects.filter(name="Responsable Technique").exists())
        self.assertTrue(Group.objects.filter(name="Responsable Logistique").exists())
        self.assertTrue(hasattr(User.objects.create_user("nouveau"), "profil"))  # profil créé automatiquement

    def test_tout_est_ferme_sans_connexion(self):
        for url in ["/api/articles/", "/api/demandes/", "/api/demandes/choix/", "/api/filtres/"]:
            r = self.c.get(url); self.assertEqual(r.status_code, 401, url)
        self.assertEqual(self.c.get("/api/session/").data, {"connecte": False})

    def test_connexion_et_deconnexion(self):
        r = self.c.post("/api/connexion/", {"identifiant": "rabe", "mot_de_passe": "faux"}, format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("incorrect", r.data["general"][0])
        r = self.c.post("/api/connexion/", {"identifiant": "", "mot_de_passe": ""}, format="json")
        self.assertIn("identifiant", r.data); self.assertIn("mot_de_passe", r.data)
        r = self.c.post("/api/connexion/", {"identifiant": "rabe", "mot_de_passe": "Mdp-rabe-2026"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["nom"], "Jean Rabe"); self.assertEqual(r.data["departement"], "Technique")
        self.assertEqual(r.data["roles"], ["Saisisseur"]); self.assertFalse(r.data["agent_logistique"])
        self.assertTrue(self.c.get("/api/session/").data["connecte"])
        self.assertEqual(self.c.get("/api/demandes/").status_code, 200)
        self.c.post("/api/deconnexion/")
        self.assertEqual(self.c.get("/api/demandes/").status_code, 401)

    def test_compte_desactive(self):
        u = User.objects.create_user("parti", password="Mdp-parti-2026", is_active=False)
        r = self.c.post("/api/connexion/", {"identifiant": "parti", "mot_de_passe": "Mdp-parti-2026"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_blocage_apres_5_essais(self):
        for _ in range(5):
            self.c.post("/api/connexion/", {"identifiant": "rabe", "mot_de_passe": "faux"}, format="json")
        r = self.c.post("/api/connexion/", {"identifiant": "rabe", "mot_de_passe": "Mdp-rabe-2026"}, format="json")
        self.assertEqual(r.status_code, 429)

    def test_roles(self):
        self.c.force_login(self.agent)
        d = self.c.get("/api/session/").data
        self.assertEqual(d["roles"], ["Saisisseur", "Responsable Technique"]); self.assertTrue(d["agent_logistique"]); self.assertFalse(d["responsable"])
        self.c.force_login(self.resp)
        self.assertEqual(self.c.get("/api/session/").data["roles"], ["Saisisseur", "Responsable Logistique"])
        admin = User.objects.create_superuser("admin2", password="Mdp-admin-2026")
        self.c.force_login(admin)
        d = self.c.get("/api/session/").data
        self.assertTrue(d["administrateur"] and d["agent_logistique"] and d["responsable"])

    def test_droits_articles_et_receptions(self):
        a = Article.objects.first()
        self.c.force_login(self.saisisseur)
        self.assertEqual(self.c.get("/api/articles/").status_code, 200)  # lecture permise
        self.assertEqual(self.c.patch(f"/api/articles/{a.id}/", {"nom": "X"}, format="json").status_code, 403)
        self.assertEqual(self.c.post("/api/entrees/", {}, format="json").status_code, 403)
        self.assertEqual(self.c.get("/api/choix/").status_code, 403)
        self.c.force_login(self.agent)
        self.assertEqual(self.c.patch(f"/api/articles/{a.id}/", {"nom": "Nouveau nom"}, format="json").status_code, 200)
        self.assertEqual(self.c.get("/api/choix/").status_code, 200)

    def test_chacun_ne_voit_que_ses_demandes(self):
        self.c.force_login(self.saisisseur)
        r = self.demande(self.c); self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("envoyée au Responsable Technique", r.data["message"])
        d = Demande.objects.get(id=r.data["id"]); self.assertEqual(d.demandeur, self.saisisseur)
        self.assertEqual(self.c.get("/api/demandes/?onglet=toutes").data["count"], 1)
        autre = APIClient(); autre.force_login(self.autre)
        self.assertEqual(autre.get("/api/demandes/?onglet=toutes").data["count"], 0)
        self.assertEqual(autre.get(f"/api/demandes/{d.id}/").status_code, 404)
        self.assertEqual(autre.post(f"/api/demandes/{d.id}/annuler/").status_code, 404)
        self.assertEqual(Demande.objects.get(id=d.id).statut, "EN_ATTENTE")

    def test_csrf_exige_pour_les_envois(self):
        c = APIClient(enforce_csrf_checks=True)
        c.login(username="rabe", password="Mdp-rabe-2026")
        self.assertEqual(self.demande(c).status_code, 403)  # sans jeton CSRF : refusé
        c.get("/api/session/")
        jeton = c.cookies["csrftoken"].value
        c.credentials(HTTP_X_CSRFTOKEN=jeton)
        self.assertEqual(self.demande(c).status_code, 201)
