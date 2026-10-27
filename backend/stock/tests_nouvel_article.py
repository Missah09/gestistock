"""Tests de la fenêtre « Nouvel article » (12/10/2026) : création réservée à l'Agent Logistique et à l'administrateur,
code automatique, stock à 0, doublons, suivi par n° de série dès la première réception.
Lancer : python manage.py test stock"""
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from stock.models import Article, Categorie, Emplacement, Exemplaire, Magasin


@override_settings(GESTISTOCK_EMAILS=False)
class NouvelArticleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.emp = Emplacement.objects.filter(magasin=cls.ank).exclude(nom__in=["Atelier – À réparer", "Rebut"]).first()
        cls.cat = Categorie.objects.first()
        cls.saisisseur = User.objects.create_user("rabe", password="x")
        cls.agent = User.objects.create_user("agent", password="x")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
        cls.admin = User.objects.create_superuser("chef", password="x")

    def client_de(self, user):
        c = APIClient(); c.force_login(user); return c

    def donnees(self, **autres):
        d = {"nom": "Testeur de continuité XT-9", "categorie": self.cat.id, "type": "CONSOMMABLE", "unite": "piece",
             "emplacement": self.emp.id, "qte_minimale": 3, "prix_unitaire": "12500"}
        d.update(autres)
        return d

    def test_agent_cree_un_article(self):
        a = self.client_de(self.agent)
        attendu = a.get("/api/choix/").data["categories"]
        prochain = next(c["prochain_code"] for c in attendu if c["id"] == self.cat.id)
        rep = a.post("/api/articles/", self.donnees(), format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        art = Article.objects.get(id=rep.data["id"])
        self.assertEqual(art.code, prochain)                      # l'aperçu annonçait le bon code
        self.assertTrue(art.code.startswith(self.cat.prefixe + "-"))
        self.assertEqual((art.qte_stock, art.qte_minimale, art.suivi_serie), (0, 3, False))
        self.assertEqual(rep.data["qte_disponible"], 0)
        self.assertIn(art.code, rep.data["message"])
        # Il apparaît dans la liste de la fenêtre « Entrée en stock »
        self.assertTrue(any(x["id"] == art.id for x in a.get("/api/choix/").data["articles"]))

    def test_administrateur_peut_creer(self):
        rep = self.client_de(self.admin).post("/api/articles/", self.donnees(nom="Article admin"), format="json")
        self.assertEqual(rep.status_code, 201, rep.data)

    def test_saisisseur_ne_peut_pas_creer(self):
        rep = self.client_de(self.saisisseur).post("/api/articles/", self.donnees(), format="json")
        self.assertEqual(rep.status_code, 403)
        self.assertFalse(Article.objects.filter(nom="Testeur de continuité XT-9").exists())

    def test_champs_obligatoires(self):
        rep = self.client_de(self.agent).post("/api/articles/", {"nom": " "}, format="json")
        self.assertEqual(rep.status_code, 400)
        for champ in ["nom", "categorie", "type", "unite", "emplacement"]:
            self.assertIn(champ, rep.data)

    def test_doublon_dans_le_meme_magasin_refuse(self):
        a = self.client_de(self.agent)
        existant = Article.objects.filter(emplacement__magasin=self.ank).first()
        nom = existant.nom.upper().replace("E", "É")  # majuscules et accents ignorés
        rep = a.post("/api/articles/", self.donnees(nom=f"  {nom} "), format="json")
        self.assertEqual(rep.status_code, 400)
        self.assertIn(existant.code, rep.data["nom"][0])

    def test_emplacement_mis_de_cote_refuse(self):
        rebut = Emplacement.objects.get_or_create(magasin=self.ank, nom="Rebut")[0]
        rep = self.client_de(self.agent).post("/api/articles/", self.donnees(emplacement=rebut.id), format="json")
        self.assertEqual(rep.status_code, 400)
        self.assertIn("emplacement", rep.data)

    def test_consommable_suivi_par_serie_seulement_a_la_piece(self):
        # Depuis le 26/10/2026 : un consommable compté à la pièce (box ONT…) peut être suivi par n° de série.
        a = self.client_de(self.agent)
        rep = a.post("/api/articles/", self.donnees(suivi_serie=True), format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        self.assertTrue(Article.objects.get(id=rep.data["id"]).suivi_serie)
        # … mais pas un consommable mesuré (mètres) : « un n° = une unité » n'a pas de sens.
        rep = a.post("/api/articles/", self.donnees(nom="Câble test", unite="m", suivi_serie=True), format="json")
        self.assertEqual(rep.status_code, 400)
        self.assertIn("pièce", rep.data["suivi_serie"][0])
        rep = a.post("/api/articles/", self.donnees(nom="Câble test", unite="m"), format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        self.assertFalse(Article.objects.get(id=rep.data["id"]).suivi_serie)

    def test_materiel_suivi_par_serie_des_la_premiere_reception(self):
        a = self.client_de(self.agent)
        rep = a.post("/api/articles/", self.donnees(nom="OTDR test", type="PRETE", suivi_serie=True), format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        art_id = rep.data["id"]
        self.assertTrue(rep.data["suivi_serie"])
        ligne = next(x for x in a.get("/api/choix/").data["articles"] if x["id"] == art_id)
        self.assertTrue(ligne["suivi_serie"])  # la colonne « N° de série » s'affiche à la réception
        entree = {"date_reception": "2026-10-12", "magasin": self.ank.id,
                  "lignes": [{"article": art_id, "quantite": 2, "numeros_serie": []}]}
        rep = a.post("/api/entrees/", entree, format="json")
        self.assertEqual(rep.status_code, 400)  # n° de série exigés
        entree["lignes"][0]["numeros_serie"] = ["NA-001", "NA-002"]
        self.assertEqual(a.post("/api/entrees/", entree, format="json").status_code, 201)
        self.assertEqual(Exemplaire.objects.filter(article_id=art_id).count(), 2)
        self.assertEqual(a.get(f"/api/articles/{art_id}/").data["qte_disponible"], 2)

    def test_materiel_sans_serie_suivi_par_quantite(self):
        a = self.client_de(self.agent)
        rep = a.post("/api/articles/", self.donnees(nom="Pelle test", type="PRETE"), format="json")
        art_id = rep.data["id"]
        entree = {"date_reception": "2026-10-12", "magasin": self.ank.id,
                  "lignes": [{"article": art_id, "quantite": 5}]}
        self.assertEqual(a.post("/api/entrees/", entree, format="json").status_code, 201)
        self.assertEqual(a.get(f"/api/articles/{art_id}/").data["qte_disponible"], 5)
