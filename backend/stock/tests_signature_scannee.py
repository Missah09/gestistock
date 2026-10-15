"""Signature scannée enregistrée dans le compte + mot de passe retapé pour signer (15/10/2026).
Lancer : python manage.py test stock"""
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from stock.models import Article, Demande, Magasin, Profil, Requisition
from stock.tests_outils import SIGNATURE


class SignatureScanneeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.saisisseur = User.objects.create_user("rabe", password="x")
        cls.agent = User.objects.create_user("agent", password="Mdp-agent")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.resp = User.objects.create_user("resp", password="Mdp-resp")
        cls.resp.groups.add(Group.objects.get(name="Responsable HBC"))
        cls.article = Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank).first()

    def setUp(self):
        cache.clear()
        self.s, self.a, self.r = (self.client_de(u) for u in (self.saisisseur, self.agent, self.resp))

    def client_de(self, u):
        c = APIClient(); c.force_login(u); return c

    def demande(self):
        return self.s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [{"article": self.article.id, "quantite": 2}]},
                           format="json").data["id"]

    def valider(self, did, **corps):
        return self.a.post(f"/api/a-valider/{did}/valider/", corps, format="json")

    def test_mot_de_passe_obligatoire_et_blocage(self):
        did = self.demande()
        rep = self.valider(did, signature=SIGNATURE)
        self.assertEqual(rep.status_code, 400); self.assertIn("Retapez", rep.data["mot_de_passe"][0])
        rep = self.valider(did, signature=SIGNATURE, mot_de_passe="faux")
        self.assertEqual(rep.status_code, 400); self.assertEqual(rep.data["mot_de_passe"], ["Mot de passe incorrect."])
        self.assertEqual(Demande.objects.get(id=did).statut, "EN_ATTENTE")
        for _ in range(4):
            self.valider(did, signature=SIGNATURE, mot_de_passe="faux")
        # 5 essais ratés : bloqué 5 minutes, même avec le bon mot de passe
        rep = self.valider(did, signature=SIGNATURE, mot_de_passe="Mdp-agent")
        self.assertEqual(rep.status_code, 429); self.assertIn("5 minutes", rep.data["mot_de_passe"][0])
        cache.clear()
        rep = self.valider(did, signature=SIGNATURE, mot_de_passe="Mdp-agent")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertEqual(Requisition.objects.get(demande_id=did).origine_signature_agent, "DESSINEE")
        # Le mot de passe d'un autre compte ne sert pas
        rep = self.r.post(f"/api/a-viser/{did}/viser/", {"signature": SIGNATURE, "mot_de_passe": "Mdp-agent"}, format="json")
        self.assertEqual(rep.status_code, 400); self.assertIn("mot_de_passe", rep.data)

    def test_import_enregistre_puis_reutilise(self):
        self.assertEqual(self.a.get("/api/ma-signature/").data, {"enregistree": False, "image": None, "le": None})
        did = self.demande()
        # Signature enregistrée demandée alors qu'il n'y en a pas
        rep = self.valider(did, source="enregistree", mot_de_passe="Mdp-agent")
        self.assertEqual(rep.status_code, 400); self.assertIn("importez", rep.data["signature"][0])
        # Fichier importé illisible : message adapté
        rep = self.valider(did, source="importee", signature="data:image/png;base64,@@", mot_de_passe="Mdp-agent")
        self.assertEqual(rep.status_code, 400); self.assertIn("autre fichier", rep.data["signature"][0])
        # Import + « Enregistrer dans mon compte »
        rep = self.valider(did, source="importee", signature=SIGNATURE, enregistrer=True, mot_de_passe="Mdp-agent")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertEqual(Requisition.objects.get(demande_id=did).origine_signature_agent, "IMPORTEE")
        m = self.a.get("/api/ma-signature/").data
        self.assertTrue(m["enregistree"]); self.assertEqual(m["image"], SIGNATURE); self.assertTrue(m["le"])
        # Le Responsable n'a pas de signature enregistrée ; il importe sans l'enregistrer
        rep = self.r.post(f"/api/a-viser/{did}/viser/", {"source": "importee", "signature": SIGNATURE, "mot_de_passe": "Mdp-resp"},
                          format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertFalse(Profil.objects.filter(user=self.resp).exclude(signature="").exists())
        self.assertEqual(Requisition.objects.get(demande_id=did).origine_signature_responsable, "IMPORTEE")
        # Demande suivante : signature enregistrée réutilisée d'un clic (+ mot de passe)
        d2 = self.demande()
        rep = self.valider(d2, source="enregistree", mot_de_passe="Mdp-agent")
        self.assertEqual(rep.status_code, 200, rep.data)
        r2 = Requisition.objects.get(demande_id=d2)
        self.assertEqual((r2.origine_signature_agent, "data:image/png;base64," + r2.signature_agent), ("IMPORTEE", SIGNATURE))
        # Image servie comme les autres signatures ; origine dans l'Historique
        self.assertEqual(self.a.get(f"/api/requisitions/{d2}/signature/agent/")["Content-Type"], "image/png")
        details = [l["detail"] for l in self.a.get("/api/historique/?type=validation").data["lignes"]]
        self.assertTrue(any("(signature importée)" in x for x in details), details)
        # Retirer la signature du compte
        self.assertFalse(self.a.delete("/api/ma-signature/").data["enregistree"])
        self.assertFalse(self.a.get("/api/ma-signature/").data["enregistree"])
        rep = self.valider(self.demande(), source="enregistree", mot_de_passe="Mdp-agent")
        self.assertEqual(rep.status_code, 400)

    def test_ma_signature_reservee_au_compte_connecte(self):
        self.assertIn(APIClient().get("/api/ma-signature/").status_code, (401, 403))


class RetraitParAdministrateurTests(TestCase):
    """L'administrateur peut retirer la signature enregistrée d'un compte (15/10/2026)."""

    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.admin = User.objects.create_superuser("admin", password="Mdp-admin")
        cls.agent = User.objects.create_user("agent", password="Mdp-agent")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))

    def setUp(self):
        p, _ = Profil.objects.get_or_create(user=self.agent)
        p.signature = SIGNATURE.split(",", 1)[1]
        from django.utils import timezone
        p.signature_le = timezone.now()
        p.save()

    def client_de(self, u):
        c = APIClient(); c.force_login(u); return c

    def test_retrait(self):
        ad, ag = self.client_de(self.admin), self.client_de(self.agent)
        url = f"/api/comptes/{self.agent.id}/signature/"
        fiche = next(c for c in ad.get("/api/comptes/").data["comptes"] if c["id"] == self.agent.id)
        self.assertTrue(fiche["signature_enregistree"]); self.assertTrue(fiche["signature_le"])
        img = ad.get(url)
        self.assertEqual((img.status_code, img["Content-Type"]), (200, "image/png"))
        # Réservé à l'administrateur
        self.assertEqual(ag.get(url).status_code, 403)
        self.assertEqual(ag.delete(url).status_code, 403)
        rep = ad.delete(url)
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertFalse(rep.data["compte"]["signature_enregistree"])
        self.assertFalse(ag.get("/api/ma-signature/").data["enregistree"])
        self.assertEqual(ad.get(url).status_code, 404)
        self.assertEqual(ad.delete(url).status_code, 400)
        self.assertEqual(ad.delete("/api/comptes/999999/signature/").status_code, 404)

    def test_action_administration_django(self):
        c = APIClient(); c.force_login(self.admin)
        rep = c.post("/admin/auth/user/", {"action": "retirer_signature", "_selected_action": [self.agent.id]})
        self.assertEqual(rep.status_code, 302)
        self.assertEqual(Profil.objects.get(user=self.agent).signature, "")
