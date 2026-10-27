"""Supprimer un article jamais utilisé dans l'administration (26/10/2026), même s'il a des lignes de correction
dans l'historique. Un article qui a servi reste protégé. Lancer : python manage.py test stock"""
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from stock.models import Article, Evenement, MouvementEtat


@override_settings(GESTISTOCK_EMAILS=False)
class SuppressionArticleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.chef = User.objects.create_superuser("chef", password="x")
        cls.agent = User.objects.create_user("agent", password="x")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.modele = Article.objects.filter(type="CONSOMMABLE").first()

    def setUp(self):
        self.client.force_login(self.chef)

    def article_test(self, nom="kkk"):
        a = Article.objects.create(nom=nom, categorie=self.modele.categorie, emplacement=self.modele.emplacement)
        MouvementEtat.objects.create(article=a, type="CORRECTION", quantite=3, variation=3, motif="Quantité corrigée")
        return a

    def test_article_jamais_utilise_supprime_avec_ses_corrections(self):
        a = self.article_test()
        page = self.client.get(f"/admin/stock/article/{a.id}/delete/").content.decode()
        self.assertNotIn("ne possède pas la permission", page)
        self.assertIn("Quantité corrigée", page)  # les corrections supprimées sont listées avant de confirmer
        rep = self.client.post(f"/admin/stock/article/{a.id}/delete/", {"post": "yes"})
        self.assertEqual(rep.status_code, 302)
        self.assertFalse(Article.objects.filter(id=a.id).exists())
        self.assertFalse(MouvementEtat.objects.filter(motif="Quantité corrigée").exists())
        self.assertTrue(Evenement.objects.filter(action="admin_suppr", objet__contains="kkk").exists())  # journal

    def test_suppression_groupee(self):
        a, b = self.article_test("t1"), self.article_test("t2")
        rep = self.client.post("/admin/stock/article/", {"action": "delete_selected", "_selected_action": [a.id, b.id],
                                                         "post": "yes"})
        self.assertEqual(rep.status_code, 302)
        self.assertFalse(Article.objects.filter(id__in=[a.id, b.id]).exists())

    def test_article_qui_a_servi_reste_protege(self):
        a = self.article_test()
        api = APIClient(); api.force_login(self.agent)
        rep = api.post("/api/entrees/", {"date_reception": timezone.localdate().isoformat(),
                                         "magasin": a.emplacement.magasin_id, "lignes": [{"article": a.id, "quantite": 2}]},
                       format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        page = self.client.get(f"/admin/stock/article/{a.id}/delete/").content.decode()
        self.assertIn("Impossible de supprimer", page)
        self.assertNotIn("pas autorisé", page)          # 27/10/2026 : la vraie raison (la réception) est montrée
        self.assertIn(str(a.lignes_entree.first()), page)
        self.client.post(f"/admin/stock/article/{a.id}/delete/", {"post": "yes"})
        self.assertTrue(Article.objects.filter(id=a.id).exists())
        self.assertEqual(MouvementEtat.objects.filter(article=a).count(), 2)

    def test_pas_administrateur_reste_bloque(self):
        a = self.article_test()
        u = User.objects.create_user("staff", password="x", is_staff=True)
        from django.contrib.auth.models import Permission
        u.user_permissions.add(*Permission.objects.filter(codename__in=["delete_article", "view_article"]))
        self.client.force_login(u)
        page = self.client.get(f"/admin/stock/article/{a.id}/delete/").content.decode()
        self.assertIn("ne possède pas la permission", page)
