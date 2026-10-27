"""Tests de l'écran « Tableau de bord » (12/10/2026).
Lancer : python manage.py test stock"""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from stock.models import Article, Magasin
from stock.tests_outils import SIGNATURE
from stock.views import articles_avec_quantites


@override_settings(GESTISTOCK_EMAILS=False)
class TableauDeBordTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.saisisseur = User.objects.create_user("rabe", password="x", first_name="Jean", last_name="Rabe")
        cls.agent = User.objects.create_user("agent", password="x", first_name="Hery", last_name="Rasoa")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.resp = User.objects.create_user("resp", password="x", first_name="Paul", last_name="Randria")
        cls.resp.groups.add(Group.objects.get(name="Responsable HBC"))
        conso = list(Article.objects.filter(type="CONSOMMABLE", emplacement__magasin=cls.ank).order_by("code"))
        cls.epuise, cls.critique, cls.bas, cls.ok = conso[:4]
        Article.objects.filter(id=cls.epuise.id).update(qte_stock=0, qte_minimale=4)
        Article.objects.filter(id=cls.critique.id).update(qte_stock=40, qte_minimale=200)
        Article.objects.filter(id=cls.bas.id).update(qte_stock=85, qte_minimale=150)
        Article.objects.filter(id=cls.ok.id).update(qte_stock=500, qte_minimale=10)

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.saisisseur)
        self.a = APIClient(); self.a.force_login(self.agent)
        self.r = APIClient(); self.r.force_login(self.resp)

    def test_droits(self):
        self.assertEqual(self.a.get("/api/tableau-de-bord/").status_code, 200)
        self.assertEqual(self.r.get("/api/tableau-de-bord/").status_code, 200)
        self.assertEqual(self.s.get("/api/tableau-de-bord/").status_code, 403)
        self.assertEqual(APIClient().get("/api/tableau-de-bord/").status_code, 401)

    def test_cartes_selon_le_role(self):
        a = self.a.get("/api/tableau-de-bord/").data["cartes"]
        r = self.r.get("/api/tableau-de-bord/").data["cartes"]
        self.assertIn("a_valider", a); self.assertNotIn("a_viser", a)
        self.assertIn("a_viser", r); self.assertNotIn("a_valider", r)

    def test_sous_le_seuil_comme_la_liste_articles(self):
        d = self.a.get("/api/tableau-de-bord/").data
        liste = self.a.get("/api/articles/?sous_seuil=1").data["count"]
        self.assertEqual(d["cartes"]["sous_seuil"], liste)
        ids = [x["id"] for x in d["a_reapprovisionner"]]
        self.assertNotIn(self.ok.id, ids)
        # Les plus urgents d'abord : épuisé, puis critique, puis stock bas
        etats = [x["etat"] for x in d["a_reapprovisionner"]]
        self.assertEqual(etats, sorted(etats, key=["EPUISE", "CRITIQUE", "BAS"].index))
        self.assertLessEqual(ids.index(self.epuise.id) if self.epuise.id in ids else 0,
                             ids.index(self.critique.id) if self.critique.id in ids else 99)
        self.assertLessEqual(len(ids), 6)

    def test_valeur_du_stock(self):
        attendu = sum(Decimal(a.qte_disponible) * a.prix_unitaire for a in articles_avec_quantites())
        d = self.a.get("/api/tableau-de-bord/").data
        self.assertEqual(Decimal(d["cartes"]["valeur_stock"]), attendu.quantize(Decimal("1")))

    def test_activite_du_jour(self):
        rep = self.s.post("/api/demandes/", {"magasin": self.ank.id, "urgent": True,
                                             "lignes": [{"article": self.ok.id, "quantite": 3}]}, format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        did = rep.data["id"]
        lignes = self.a.get(f"/api/a-valider/{did}/").data["lignes"]
        self.assertEqual(self.a.post(f"/api/a-valider/{did}/valider/", {
            "signature": SIGNATURE, "mot_de_passe": "x", "lignes": [{"id": l["id"], "qte_accordee": l["quantite"]} for l in lignes]},
            format="json").status_code, 200)
        self.assertEqual(self.r.post(f"/api/a-viser/{did}/viser/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json").status_code, 200)
        d = self.a.get("/api/tableau-de-bord/").data
        types = [x["type"] for x in d["activite"]]
        self.assertEqual(set(types), {"demande", "validation", "visa"})
        textes = " | ".join(x["texte"] for x in d["activite"])
        self.assertIn("validée par H. Rasoa", textes)
        self.assertIn("signé par P. Randria", textes)
        self.assertIn("urgente", textes)
        # Les plus récents d'abord
        heures = [x["le"] for x in d["activite"]]
        self.assertEqual(heures, sorted(heures, reverse=True))
        self.assertTrue(heures[0].startswith(timezone.localdate().isoformat()))

    def test_graphiques(self):
        """Graphiques (16/10/2026) : top des sorties, entrées et sorties par jour, valeur par catégorie."""
        rep = self.s.post("/api/demandes/", {"magasin": self.ank.id,
                                             "lignes": [{"article": self.ok.id, "quantite": 7}]}, format="json")
        did = rep.data["id"]
        lignes = self.a.get(f"/api/a-valider/{did}/").data["lignes"]
        self.a.post(f"/api/a-valider/{did}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x",
                    "lignes": [{"id": l["id"], "qte_accordee": l["quantite"]} for l in lignes]}, format="json")
        self.r.post(f"/api/a-viser/{did}/viser/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
        self.assertEqual(self.a.get(f"/api/requisitions/{did}/pdf/").status_code, 200)
        rep = self.a.post(f"/api/sorties/{did}/confirmer/", {"date_remise": timezone.localdate().isoformat(),
                          "lignes": [{"id": lignes[0]["id"], "qte_livree": 5}]}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)

        g = self.a.get("/api/tableau-de-bord/").data["graphiques"]
        self.assertEqual(g["top_sorties"][0]["id"], self.ok.id)
        self.assertEqual(g["top_sorties"][0]["qte"], 5)
        self.assertEqual(len(g["mouvements"]), 14)
        self.assertEqual(g["mouvements"][-1]["jour"], timezone.localdate().isoformat())
        self.assertEqual(g["mouvements"][-1]["sorties"], 1)
        # La somme des catégories = la carte « Valeur du stock »
        d = self.a.get("/api/tableau-de-bord/").data
        self.assertEqual(sum(Decimal(c["valeur"]) for c in g["categories"]), Decimal(d["cartes"]["valeur_stock"]))

    def test_categories_sans_valeur_affichees_a_zero(self):
        """27/10/2026 : toutes les catégories figurent dans « Valeur du stock par catégorie », même à 0 Ar."""
        from stock.models import Categorie
        Categorie.objects.create(nom="Catégorie vide de test", prefixe="ZZV")
        g = self.a.get("/api/tableau-de-bord/").data["graphiques"]
        vide = [c for c in g["categories"] if c["nom"] == "Catégorie vide de test"]
        if Categorie.objects.count() <= 8:
            self.assertEqual(vide, [{"nom": "Catégorie vide de test", "valeur": "0"}])
            self.assertEqual(len(g["categories"]), Categorie.objects.count())
        valeurs = [Decimal(c["valeur"]) for c in g["categories"] if not c.get("autres")]
        self.assertEqual(valeurs, sorted(valeurs, reverse=True))   # les plus grosses valeurs d'abord, les 0 Ar à la fin
