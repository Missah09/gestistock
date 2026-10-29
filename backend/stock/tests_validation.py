"""Tests de l'écran « Demandes à valider » (Responsable Technique, 11/10/2026).  Lancer : python manage.py test stock"""
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from stock.tests_outils import SIGNATURE
from stock.models import Article, Demande, Departement, Magasin, Requisition


class ValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.saisisseur = User.objects.create_user("rabe", password="x", first_name="Jean", last_name="Rabe")
        cls.saisisseur.profil.departement = Departement.objects.get(nom="Technique"); cls.saisisseur.profil.save()
        cls.agent = User.objects.create_user("agent", password="x", first_name="Hery", last_name="Agent")
        cls.agent.groups.add(Group.objects.get(name="Responsable Technique"))
        cls.resp = User.objects.create_user("resp", password="x")
        cls.resp.groups.add(Group.objects.get(name="Responsable Logistique"))
        cls.articles = list(Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank)[:2])

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.saisisseur)
        self.a = APIClient(); self.a.force_login(self.agent)

    def nouvelle(self, urgent=False):
        r = self.s.post("/api/demandes/", {"magasin": self.ank.id, "urgent": urgent, "lignes": [
            {"article": self.articles[0].id, "quantite": 5}, {"article": self.articles[1].id, "quantite": 3}]}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        return Demande.objects.get(id=r.data["id"])

    def test_reserve_a_l_agent_logistique(self):
        d = self.nouvelle()
        for c in (self.s, self.r()):
            self.assertEqual(c.get("/api/a-valider/").status_code, 403)
            self.assertEqual(c.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json").status_code, 403)
            self.assertEqual(c.post(f"/api/a-valider/{d.id}/refuser/", {"motif": "x"}, format="json").status_code, 403)
        self.assertEqual(APIClient().get("/api/a-valider/").status_code, 401)

    def r(self):
        c = APIClient(); c.force_login(self.resp); return c

    def test_agent_voit_toutes_les_demandes(self):
        d = self.nouvelle()
        r = self.a.get("/api/a-valider/").data
        self.assertEqual(r["compteurs"]["attente"], 1)
        ligne = r["results"][0]
        self.assertEqual(ligne["numero"], d.numero)
        self.assertEqual(ligne["demandeur"], "Jean Rabe")
        self.assertEqual(ligne["demandeur_departement"], "Technique")
        self.assertIsNone(ligne["requisition"])
        self.assertEqual(self.a.get(f"/api/a-valider/{d.id}/").status_code, 200)
        self.assertEqual(self.a.get("/api/a-valider/999999/").status_code, 404)
        # L'agent ne voit pas cette demande dans SES demandes à lui.
        self.assertEqual(self.a.get("/api/demandes/?onglet=toutes").data["count"], 0)

    def test_urgentes_puis_plus_anciennes(self):
        d1 = self.nouvelle(); d2 = self.nouvelle(); d3 = self.nouvelle(urgent=True)
        ordre = [x["numero"] for x in self.a.get("/api/a-valider/?onglet=attente").data["results"]]
        self.assertEqual(ordre, [d3.numero, d1.numero, d2.numero])

    def test_valider_avec_quantites_modifiees(self):
        d = self.nouvelle()
        l1, l2 = d.lignes.order_by("id")
        stock_avant = Article.objects.get(id=l1.article_id).qte_stock
        r = self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l1.id, "qte_accordee": 2},
                                                                        {"id": l2.id, "qte_accordee": 0}]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        annee = d.cree_le.year
        self.assertEqual(r.data["demande"]["requisition"]["numero"], f"RM-{annee}-0001")
        self.assertIn("RM-", r.data["message"])
        d.refresh_from_db(); l1.refresh_from_db(); l2.refresh_from_db()
        self.assertEqual(d.statut, "VALIDEE"); self.assertEqual(d.traitee_par, self.agent); self.assertIsNotNone(d.traitee_le)
        self.assertEqual((l1.quantite, l1.qte_accordee), (5, 2))  # la quantité demandée d'origine est conservée
        self.assertEqual((l2.quantite, l2.qte_accordee), (3, 0))
        rq = Requisition.objects.get(demande=d)
        self.assertEqual((rq.statut, rq.visa_agent), ("ATTENTE_VISA", self.agent))
        self.assertEqual(Article.objects.get(id=l1.article_id).qte_stock, stock_avant)  # stock inchangé
        # Le demandeur voit la validation et la réquisition
        vue = self.s.get(f"/api/demandes/{d.id}/").data
        self.assertEqual(vue["statut"], "VALIDEE"); self.assertEqual(vue["requisition"]["statut"], "ATTENTE_VISA")
        self.assertEqual(vue["traitee_par"], "Hery Agent")
        # Numérotation suivante
        d2 = self.nouvelle()
        r = self.a.post(f"/api/a-valider/{d2.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")  # sans modification
        self.assertEqual(r.data["demande"]["requisition"]["numero"], f"RM-{annee}-0002")
        self.assertEqual(sorted(d2.lignes.values_list("qte_accordee", flat=True)), [3, 5])

    def test_valider_controles(self):
        d = self.nouvelle()
        l1, l2 = d.lignes.order_by("id")
        r = self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l1.id, "qte_accordee": -1},
                                                                        {"id": l2.id, "qte_accordee": "abc"}]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn(str(l1.id), r.data["lignes"]); self.assertIn(str(l2.id), r.data["lignes"])
        r = self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l1.id, "qte_accordee": ""}]}, format="json")
        self.assertIn("0 pour retirer", r.data["lignes"][str(l1.id)][0])
        r = self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l1.id, "qte_accordee": 0},
                                                                        {"id": l2.id, "qte_accordee": "0"}]}, format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("refusez", r.data["general"][0])
        r = self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": 999999, "qte_accordee": 1}]}, format="json")
        self.assertEqual(r.status_code, 400)
        d.refresh_from_db(); self.assertEqual(d.statut, "EN_ATTENTE"); self.assertFalse(Requisition.objects.exists())
        # Plus que demandé : permis (l'agent corrige au besoin)
        r = self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l1.id, "qte_accordee": "8"}]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        # Déjà validée : ni revalidation ni refus
        self.assertEqual(self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json").status_code, 400)
        r = self.a.post(f"/api/a-valider/{d.id}/refuser/", {"motif": "x"}, format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("déjà validée", r.data["general"][0])
        self.assertEqual(Requisition.objects.count(), 1)
        # Le demandeur ne peut plus annuler
        self.assertEqual(self.s.post(f"/api/demandes/{d.id}/annuler/").status_code, 400)

    def test_demande_annulee_ne_peut_plus_etre_validee(self):
        d = self.nouvelle()
        self.s.post(f"/api/demandes/{d.id}/annuler/")
        r = self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("annulée", r.data["general"][0])

    def test_refuser(self):
        d = self.nouvelle()
        r = self.a.post(f"/api/a-valider/{d.id}/refuser/", {"motif": "  "}, format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("motif", r.data)
        r = self.a.post(f"/api/a-valider/{d.id}/refuser/", {"motif": "x" * 251}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.a.post(f"/api/a-valider/{d.id}/refuser/", {"motif": " Stock réservé au chantier Ivato "}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        d.refresh_from_db()
        self.assertEqual((d.statut, d.motif_refus, d.traitee_par), ("REFUSEE", "Stock réservé au chantier Ivato", self.agent))
        self.assertFalse(Requisition.objects.exists())
        self.assertEqual(self.a.get("/api/a-valider/?onglet=refusees").data["count"], 1)
        self.assertEqual(self.s.get(f"/api/demandes/{d.id}/").data["motif_refus"], "Stock réservé au chantier Ivato")
