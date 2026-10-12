"""Tests du visa du Responsable HBC et de l'email (11/10/2026).  Lancer : python manage.py test stock"""
from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from stock.tests_outils import SIGNATURE
from stock.models import Article, Demande, Magasin, Requisition

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@override_settings(GESTISTOCK_EMAILS=True, GESTISTOCK_EMAIL_TEMPORAIRE="", GESTISTOCK_ADRESSE="http://127.0.0.1:3000")
class VisaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.saisisseur = User.objects.create_user("rabe", password="x", first_name="Jean", last_name="Rabe")
        cls.agent = User.objects.create_user("agent", password="x", first_name="Hery", last_name="Agent")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.resp = User.objects.create_user("resp", password="x", first_name="Lova", last_name="Resp", email="resp@hbc.test")
        cls.resp.groups.add(Group.objects.get(name="Responsable HBC"))
        cls.article = Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank).first()

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.saisisseur)
        self.a = APIClient(); self.a.force_login(self.agent)
        self.r = APIClient(); self.r.force_login(self.resp)

    def demande_validee(self, urgent=False):
        r = self.s.post("/api/demandes/", {"magasin": self.ank.id, "urgent": urgent,
                                           "lignes": [{"article": self.article.id, "quantite": 4}]}, format="json")
        d = Demande.objects.get(id=r.data["id"])
        l = d.lignes.first()
        r = self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "lignes": [{"id": l.id, "qte_accordee": 3}]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        return d, r

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_email_au_responsable_a_la_validation(self):
        d, r = self.demande_validee(urgent=True)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        rq = Requisition.objects.get(demande=d)
        self.assertEqual(m.to, ["resp@hbc.test"])
        self.assertIn(rq.numero, m.subject); self.assertIn("URGENT", m.subject)
        self.assertIn(f"http://127.0.0.1:3000/#a-viser/{d.id}", m.body)
        self.assertIn("Jean Rabe", m.body); self.assertIn(": 3", m.body)  # quantité accordée, pas demandée
        self.assertIn(rq.numero, m.alternatives[0][0])  # version HTML
        self.assertIsNotNone(rq.email_envoye_le)
        self.assertIn("email", r.data)

    @override_settings(EMAIL_BACKEND=LOCMEM, GESTISTOCK_EMAIL_TEMPORAIRE="temporaire@exemple.test")
    def test_adresse_temporaire(self):
        self.demande_validee()
        self.assertEqual(mail.outbox[0].to, ["temporaire@exemple.test"])

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_sans_adresse_la_validation_passe_quand_meme(self):
        self.resp.email = ""; self.resp.save()
        d, r = self.demande_validee()
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("aucun compte", r.data["email"])
        self.assertEqual(Demande.objects.get(id=d.id).statut, "VALIDEE")
        self.assertIsNone(Requisition.objects.get(demande=d).email_envoye_le)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="127.0.0.1",
                       EMAIL_PORT=9, EMAIL_TIMEOUT=2)
    def test_serveur_injoignable_ne_bloque_pas(self):
        d, r = self.demande_validee()
        self.assertIn("non envoyé", r.data["email"]); self.assertFalse(r.data["email_ok"])
        self.assertEqual(Requisition.objects.get(demande=d).statut, "ATTENTE_VISA")
        # Renvoyer l'email une fois le problème réglé
        with self.settings(EMAIL_BACKEND=LOCMEM):
            r = self.a.post(f"/api/a-valider/{d.id}/renvoyer-email/")
            self.assertEqual(r.status_code, 200, r.data); self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.s.post(f"/api/a-valider/{d.id}/renvoyer-email/").status_code, 403)

    def test_reserve_au_responsable(self):
        d, _ = self.demande_validee()
        for c in (self.s, self.a):
            self.assertEqual(c.get("/api/a-viser/").status_code, 403)
            self.assertEqual(c.post(f"/api/a-viser/{d.id}/viser/", {"signature": SIGNATURE}, format="json").status_code, 403)
        self.assertEqual(APIClient().get("/api/a-viser/").status_code, 401)

    def test_liste_et_visa(self):
        d1, _ = self.demande_validee(); d2, _ = self.demande_validee(urgent=True)
        # une demande encore en attente de la Logistique n'apparaît pas
        self.s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [{"article": self.article.id, "quantite": 1}]}, format="json")
        r = self.r.get("/api/a-viser/").data
        self.assertEqual([x["numero"] for x in r["results"]], [d2.numero, d1.numero])  # urgente d'abord
        self.assertEqual(r["compteurs"], {"attente": 2, "visees": 0, "refusees": 0, "toutes": 2})
        self.assertEqual(self.r.get(f"/api/a-viser/{d1.id}/").status_code, 200)
        r = self.r.post(f"/api/a-viser/{d1.id}/viser/", {"signature": SIGNATURE}, format="json")
        self.assertEqual(r.status_code, 200, r.data); self.assertIn("visée", r.data["message"])
        rq = Requisition.objects.get(demande=d1)
        self.assertEqual((rq.statut, rq.visa_responsable), ("VISEE", self.resp)); self.assertIsNotNone(rq.visa_responsable_le)
        self.assertEqual(self.r.post(f"/api/a-viser/{d1.id}/viser/", {"signature": SIGNATURE}, format="json").status_code, 400)  # déjà visée
        self.assertEqual(self.r.post(f"/api/a-viser/{d1.id}/refuser/", {"motif": "x"}, format="json").status_code, 400)
        self.assertEqual(self.r.get("/api/a-viser/?onglet=visees").data["count"], 1)
        # Le demandeur voit l'étape « Visée »
        self.assertEqual(self.s.get(f"/api/demandes/{d1.id}/").data["requisition"]["statut"], "VISEE")
        self.assertEqual(self.r.post("/api/a-viser/999999/viser/", {"signature": SIGNATURE}, format="json").status_code, 404)

    def test_refus_du_responsable(self):
        d, _ = self.demande_validee()
        self.assertEqual(self.r.post(f"/api/a-viser/{d.id}/refuser/", {"motif": " "}, format="json").status_code, 400)
        r = self.r.post(f"/api/a-viser/{d.id}/refuser/", {"motif": "Budget du mois dépassé"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        rq = Requisition.objects.get(demande=d)
        self.assertEqual((rq.statut, rq.motif_refus), ("REFUSEE", "Budget du mois dépassé"))
        # Rangée dans « Refusées » pour l'Agent Logistique et pour le demandeur
        self.assertEqual(self.a.get("/api/a-valider/?onglet=refusees").data["count"], 1)
        self.assertEqual(self.a.get("/api/a-valider/?onglet=validees").data["count"], 0)
        self.assertEqual(self.s.get("/api/demandes/?onglet=refusees").data["count"], 1)
        self.assertEqual(self.s.get(f"/api/demandes/{d.id}/").data["requisition"]["motif_refus"], "Budget du mois dépassé")
        self.assertEqual(self.a.post(f"/api/a-valider/{d.id}/renvoyer-email/").status_code, 400)


    @override_settings(GESTISTOCK_EMAILS=False, EMAIL_BACKEND=LOCMEM)
    def test_sans_email_et_compteurs(self):
        """Emails désactivés (réglage par défaut depuis le 11/10, 22 h 15) : rien ne part ; compteurs du menu."""
        self.assertEqual(self.r.get("/api/compteurs/").data, {"a_viser": 0})
        d, r = self.demande_validee()
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(r.data["email"]); self.assertTrue(r.data["email_ok"])
        self.assertEqual(self.r.get("/api/compteurs/").data, {"a_viser": 1})
        self.assertEqual(self.a.get("/api/compteurs/").data, {"a_valider": 0, "a_imprimer": 0, "a_confirmer": 0})  # a_imprimer, a_confirmer : 12/10/2026
        self.assertEqual(self.s.get("/api/compteurs/").data, {})
        self.assertEqual(self.a.post(f"/api/a-valider/{d.id}/renvoyer-email/").status_code, 400)
        self.r.post(f"/api/a-viser/{d.id}/viser/", {"signature": SIGNATURE}, format="json")
        self.assertEqual(self.r.get("/api/compteurs/").data, {"a_viser": 0})
        self.assertFalse(self.s.get("/api/session/").data["emails"])


class SignatureTests(TestCase):
    """Signature dessinée au stylo électronique : obligatoire pour valider (Agent) et viser (Responsable)."""
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.saisisseur = User.objects.create_user("rabe", password="x")
        cls.autre = User.objects.create_user("autre", password="x")
        cls.agent = User.objects.create_user("agent", password="x")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.resp = User.objects.create_user("resp", password="x")
        cls.resp.groups.add(Group.objects.get(name="Responsable HBC"))
        cls.article = Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank).first()

    def client_de(self, u):
        c = APIClient(); c.force_login(u); return c

    def test_signatures_obligatoires_et_images(self):
        s, a, r = self.client_de(self.saisisseur), self.client_de(self.agent), self.client_de(self.resp)
        d = s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [{"article": self.article.id, "quantite": 2}]}, format="json").data
        for mauvaise in [None, "", "bonjour", "data:image/png;base64,@@@", "data:image/png;base64,aGVsbG8gd29ybGQgaGVsbG8gd29ybGQgaGVsbG8gd29ybGQgaGVsbG8gd29ybGQgaGVsbG8gd29ybGQ="]:
            rep = a.post(f"/api/a-valider/{d['id']}/valider/", {"signature": mauvaise}, format="json")
            self.assertEqual(rep.status_code, 400, mauvaise); self.assertIn("signature", rep.data)
        self.assertEqual(Demande.objects.get(id=d["id"]).statut, "EN_ATTENTE")
        rep = a.post(f"/api/a-valider/{d['id']}/valider/", {"signature": SIGNATURE}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertTrue(rep.data["demande"]["requisition"]["signature_agent"])
        self.assertFalse(rep.data["demande"]["requisition"]["signature_responsable"])
        # Le Responsable doit signer aussi
        rep = r.post(f"/api/a-viser/{d['id']}/viser/", {}, format="json")
        self.assertEqual(rep.status_code, 400); self.assertIn("Signez", rep.data["signature"][0])
        rep = r.post(f"/api/a-viser/{d['id']}/viser/", {"signature": SIGNATURE}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data); self.assertTrue(rep.data["demande"]["requisition"]["signature_responsable"])
        # Images : Agent, Responsable et demandeur peuvent les voir ; un autre compte non
        for c in (a, r, s):
            img = c.get(f"/api/requisitions/{d['id']}/signature/agent/")
            self.assertEqual((img.status_code, img["Content-Type"]), (200, "image/png"))
            self.assertTrue(img.content.startswith(b"\x89PNG"))
        self.assertEqual(r.get(f"/api/requisitions/{d['id']}/signature/responsable/").status_code, 200)
        self.assertEqual(self.client_de(self.autre).get(f"/api/requisitions/{d['id']}/signature/agent/").status_code, 404)
        self.assertEqual(r.get(f"/api/requisitions/{d['id']}/signature/inconnu/").status_code, 404)
