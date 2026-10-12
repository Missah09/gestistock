"""Tests de l'écran « Comptes » et de la règle « un seul appareil connecté par compte » (11/10/2026)."""
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from stock.models import Departement

MDP = "Gesti-Stock-2026!"


class UnSeulAppareilTests(TestCase):
    def setUp(self):
        cache.clear()
        self.u = User.objects.create_user("rabe", password=MDP)

    def connecter(self):
        c = APIClient()
        r = c.post("/api/connexion/", {"identifiant": "rabe", "mot_de_passe": MDP}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        return c

    def test_nouvelle_connexion_deconnecte_l_autre_appareil(self):
        pc_bureau = self.connecter()
        self.assertEqual(pc_bureau.get("/api/demandes/").status_code, 200)
        telephone = self.connecter()
        self.assertEqual(telephone.get("/api/demandes/").status_code, 200)
        # L'application vérifie la session toutes les 30 s : le message dit pourquoi on est déconnecté.
        s = pc_bureau.get("/api/session/").data
        self.assertEqual((s["connecte"], s["raison"]), (False, "autre_appareil"))
        self.assertEqual(pc_bureau.get("/api/demandes/").status_code, 401)
        # Se reconnecter au bureau déconnecte le téléphone (message aussi sur un appel ordinaire)
        pc_bureau = self.connecter()
        r = telephone.get("/api/demandes/")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data["raison"], "autre_appareil"); self.assertIn("autre appareil", r.data["general"][0])
        self.assertEqual(pc_bureau.get("/api/demandes/").status_code, 200)

    def test_deconnexion_normale_sans_message(self):
        c = self.connecter()
        c.post("/api/deconnexion/")
        self.assertEqual(c.get("/api/session/").data, {"connecte": False})
        self.u.profil.refresh_from_db(); self.assertEqual(self.u.profil.cle_session, "")


class GestionComptesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("admin", password=MDP)
        cls.agent = User.objects.create_user("agent", password=MDP)
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.tech = Departement.objects.get(nom="Technique")

    def setUp(self):
        cache.clear()
        self.a = APIClient(); self.a.force_login(self.admin)

    def nouveau(self, **k):
        d = {"identifiant": "lova", "prenom": "Lova", "nom": "Randria", "email": "", "departement": self.tech.id,
             "responsable": True, "agent": False, "mot_de_passe": MDP}
        d.update(k)
        return self.a.post("/api/comptes/", d, format="json")

    def test_reserve_a_l_administrateur(self):
        c = APIClient(); c.force_login(self.agent)
        self.assertEqual(c.get("/api/comptes/").status_code, 403)
        self.assertEqual(c.post("/api/comptes/", {}, format="json").status_code, 403)
        self.assertEqual(APIClient().get("/api/comptes/").status_code, 401)

    def test_creer_un_compte(self):
        r = self.nouveau()
        self.assertEqual(r.status_code, 201, r.data)
        u = User.objects.get(username="lova")
        self.assertEqual((u.first_name, u.last_name, u.profil.departement), ("Lova", "Randria", self.tech))
        self.assertEqual(list(u.groups.values_list("name", flat=True)), ["Responsable HBC"])
        self.assertFalse(u.is_superuser); self.assertTrue(u.check_password(MDP))
        liste = self.a.get("/api/comptes/").data
        lova = next(x for x in liste["comptes"] if x["identifiant"] == "lova")
        self.assertTrue(lova["responsable"]); self.assertFalse(lova["agent"]); self.assertFalse(lova["connecte"])
        self.assertEqual(len(liste["departements"]), 4)  # + Informatique (12/10/2026)
        c = APIClient()
        self.assertEqual(c.post("/api/connexion/", {"identifiant": "lova", "mot_de_passe": MDP}, format="json").status_code, 200)
        self.assertTrue(next(x for x in self.a.get("/api/comptes/").data["comptes"] if x["identifiant"] == "lova")["connecte"])

    def test_controles_a_la_creation(self):
        self.nouveau()
        r = self.nouveau(identifiant="LOVA", prenom="", nom=" ", departement=None, email="pas-un-email", mot_de_passe="123")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(set(r.data), {"identifiant", "prenom", "nom", "departement", "email", "mot_de_passe"})
        self.assertIn("déjà pris", r.data["identifiant"][0])
        self.assertIn("espace", self.nouveau(identifiant="jean rabe").data["identifiant"][0])
        self.assertEqual(self.nouveau(identifiant="x2", mot_de_passe="").data["mot_de_passe"][0], "Indiquez un mot de passe provisoire.")

    def test_modifier_roles_et_departement(self):
        u = User.objects.get(id=self.nouveau().data["compte"]["id"])
        fin = Departement.objects.get(nom="Finance")
        r = self.a.patch(f"/api/comptes/{u.id}/", {"prenom": "Lova", "nom": "Rakoto", "departement": fin.id,
                                                    "agent": True, "responsable": False}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        u.refresh_from_db()
        self.assertEqual((u.last_name, u.profil.departement), ("Rakoto", fin))
        self.assertEqual(list(u.groups.values_list("name", flat=True)), ["Agent Logistique"])
        self.assertEqual(self.a.patch("/api/comptes/999999/", {}, format="json").status_code, 404)

    def test_desactiver_mot_de_passe_deconnecter(self):
        u = User.objects.get(id=self.nouveau().data["compte"]["id"])
        c = APIClient(); c.post("/api/connexion/", {"identifiant": "lova", "mot_de_passe": MDP}, format="json")
        self.assertEqual(c.get("/api/demandes/").status_code, 200)
        # Déconnecter
        self.assertEqual(self.a.post(f"/api/comptes/{u.id}/deconnecter/").status_code, 200)
        self.assertEqual(c.get("/api/demandes/").status_code, 401)
        # Nouveau mot de passe : l'ancien ne marche plus
        self.assertEqual(self.a.post(f"/api/comptes/{u.id}/mot-de-passe/", {"mot_de_passe": "abc"}, format="json").status_code, 400)
        self.assertEqual(self.a.post(f"/api/comptes/{u.id}/mot-de-passe/", {"mot_de_passe": "Nouveau-Mdp-2026"}, format="json").status_code, 200)
        self.assertEqual(c.post("/api/connexion/", {"identifiant": "lova", "mot_de_passe": MDP}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/connexion/", {"identifiant": "lova", "mot_de_passe": "Nouveau-Mdp-2026"}, format="json").status_code, 200)
        # Désactiver : déconnecté et plus de connexion possible
        self.assertEqual(self.a.post(f"/api/comptes/{u.id}/activer/", {"actif": False}, format="json").status_code, 200)
        self.assertEqual(c.get("/api/demandes/").status_code, 401)
        self.assertEqual(c.post("/api/connexion/", {"identifiant": "lova", "mot_de_passe": "Nouveau-Mdp-2026"}, format="json").status_code, 400)
        self.a.post(f"/api/comptes/{u.id}/activer/", {"actif": True}, format="json")
        self.assertEqual(c.post("/api/connexion/", {"identifiant": "lova", "mot_de_passe": "Nouveau-Mdp-2026"}, format="json").status_code, 200)

    def test_l_administrateur_ne_se_bloque_pas_lui_meme(self):
        self.assertEqual(self.a.post(f"/api/comptes/{self.admin.id}/activer/", {"actif": False}, format="json").status_code, 400)
        self.assertEqual(self.a.post(f"/api/comptes/{self.admin.id}/deconnecter/").status_code, 400)
        r = self.a.post(f"/api/comptes/{self.admin.id}/mot-de-passe/", {"mot_de_passe": "Autre-Mdp-2026"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.a.get("/api/comptes/").status_code, 200)  # toujours connecté après son propre changement
        # Super-utilisateur : département facultatif
        r = self.a.patch(f"/api/comptes/{self.admin.id}/", {"prenom": "Admin", "nom": "HBC", "departement": None}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
