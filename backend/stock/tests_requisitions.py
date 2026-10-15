"""Tests de l'écran « Réquisitions » et du PDF du bon (12/10/2026).  Lancer : python manage.py test stock"""
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from stock.models import Article, Demande, Magasin, Requisition, TelechargementBon
from stock.pdf_bon import lignes_du_bon
from stock.tests_outils import SIGNATURE


@override_settings(GESTISTOCK_EMAILS=False)
class RequisitionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.saisisseur = User.objects.create_user("rabe", password="x", first_name="Jean", last_name="Rabe")
        cls.agent = User.objects.create_user("agent", password="x", first_name="Hery", last_name="Rasoa")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.resp = User.objects.create_user("resp", password="x", first_name="Paul", last_name="Randria")
        cls.resp.groups.add(Group.objects.get(name="Responsable HBC"))
        cls.articles = list(Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank)[:2])

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.saisisseur)
        self.a = APIClient(); self.a.force_login(self.agent)
        self.r = APIClient(); self.r.force_login(self.resp)

    def demande(self, viser=True, urgent=False):
        """Demande de 2 articles ; la Logistique retire le 2e (0) ; le Responsable signe si `viser`."""
        rep = self.s.post("/api/demandes/", {"magasin": self.ank.id, "urgent": urgent, "lignes": [
            {"article": self.articles[0].id, "quantite": 4}, {"article": self.articles[1].id, "quantite": 2}]}, format="json")
        d = Demande.objects.get(id=rep.data["id"])
        l1, l2 = d.lignes.all()
        rep = self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x", "lignes": [
            {"id": l1.id, "qte_accordee": 3}, {"id": l2.id, "qte_accordee": 0}]}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        if viser:
            rep = self.r.post(f"/api/a-viser/{d.id}/viser/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
            self.assertEqual(rep.status_code, 200, rep.data)
        return d

    # ---------------------------------------------------------------- Droits
    def test_droits_de_l_ecran(self):
        self.assertEqual(self.a.get("/api/requisitions/").status_code, 200)
        self.assertEqual(self.r.get("/api/requisitions/").status_code, 200)
        self.assertEqual(self.s.get("/api/requisitions/").status_code, 403)
        d = self.demande()
        self.assertEqual(self.s.get(f"/api/requisitions/{d.id}/pdf/").status_code, 403)
        self.assertEqual(APIClient().get(f"/api/requisitions/{d.id}/pdf/").status_code, 401)

    # ---------------------------------------------------------------- Liste
    def test_seules_les_requisitions_signees_par_le_responsable(self):
        visee = self.demande()
        self.demande(viser=False)
        rep = self.a.get("/api/requisitions/?onglet=toutes")
        self.assertEqual([x["id"] for x in rep.data["results"]], [visee.id])
        self.assertEqual(rep.data["compteurs"], {"a_imprimer": 1, "imprimees": 0, "toutes": 1})

    def test_urgentes_d_abord_dans_a_imprimer(self):
        normale = self.demande()
        urgente = self.demande(urgent=True)
        rep = self.a.get("/api/requisitions/")
        self.assertEqual([x["id"] for x in rep.data["results"]], [urgente.id, normale.id])

    def test_pdf_refuse_avant_la_signature_du_responsable(self):
        d = self.demande(viser=False)
        rep = self.a.get(f"/api/requisitions/{d.id}/pdf/")
        self.assertEqual(rep.status_code, 400)
        self.assertFalse(TelechargementBon.objects.exists())

    # ---------------------------------------------------------------- PDF et trace d'impression
    def test_pdf_par_l_agent_marque_le_bon_imprime(self):
        d = self.demande()
        rep = self.a.get(f"/api/requisitions/{d.id}/pdf/")
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep["Content-Type"], "application/pdf")
        rq = Requisition.objects.get(demande=d)
        self.assertIn(f'filename="{rq.numero}.pdf"', rep["Content-Disposition"])
        self.assertTrue(rep.content.startswith(b"%PDF"))
        self.assertEqual(rq.imprimee_par, self.agent)
        self.assertIsNotNone(rq.imprimee_le)
        premiere = rq.imprimee_le
        # Un 2e téléchargement est noté mais ne change pas la date d'impression
        self.a.get(f"/api/requisitions/{d.id}/pdf/")
        rq.refresh_from_db()
        self.assertEqual(rq.imprimee_le, premiere)
        self.assertEqual(rq.telechargements.count(), 2)
        rep = self.a.get("/api/requisitions/?onglet=imprimees")
        self.assertEqual(rep.data["results"][0]["requisition"]["imprimee_par"], "Hery Rasoa")
        self.assertEqual(rep.data["results"][0]["requisition"]["nb_telechargements"], 2)

    def test_pdf_par_le_responsable_est_une_consultation(self):
        d = self.demande()
        rep = self.r.get(f"/api/requisitions/{d.id}/pdf/")
        self.assertEqual(rep.status_code, 200)
        rq = Requisition.objects.get(demande=d)
        self.assertIsNone(rq.imprimee_le)
        t = rq.telechargements.get()
        self.assertEqual((t.par, t.role), (self.resp, "Responsable HBC"))
        self.assertEqual(self.a.get("/api/compteurs/").data["a_imprimer"], 1)

    def test_compteur_du_menu(self):
        d = self.demande()
        self.assertEqual(self.a.get("/api/compteurs/").data["a_imprimer"], 1)
        self.assertNotIn("a_imprimer", self.r.get("/api/compteurs/").data)
        self.a.get(f"/api/requisitions/{d.id}/pdf/")
        self.assertEqual(self.a.get("/api/compteurs/").data["a_imprimer"], 0)

    def test_les_articles_retires_ne_sont_pas_sur_le_bon(self):
        d = self.demande()
        lignes = lignes_du_bon(d)
        self.assertEqual([(l.article_id, q) for l, q in lignes], [(self.articles[0].id, 3)])

    def test_le_demandeur_voit_l_impression_dans_son_suivi(self):
        d = self.demande()
        self.a.get(f"/api/requisitions/{d.id}/pdf/")
        rep = self.s.get(f"/api/demandes/{d.id}/")
        self.assertEqual(rep.data["requisition"]["imprimee_par"], "Hery Rasoa")
