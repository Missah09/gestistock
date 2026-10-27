"""Tests du 26/10/2026 : n° de série à l'entrée en stock (une case et un état par unité) et consommables
comptés à la pièce suivis par n° de série (« Sorti (consommé) » à la sortie).
Lancer : python manage.py test stock"""
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from stock.models import Article, Demande, Exemplaire, LigneEntree, MouvementEtat
from stock.rapports import prete_dehors
from stock.tests_outils import SIGNATURE
from stock import tests_retours  # (module importé, pas la classe : ses tests ne sont pas relancés ici)


@override_settings(GESTISTOCK_EMAILS=False)
class SeriesConsommablesTests(TestCase):
    setUpTestData = classmethod(tests_retours.EtatEtRetoursTests.setUpTestData.__func__)

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.saisisseur)
        self.a = APIClient(); self.a.force_login(self.agent)
        self.r = APIClient(); self.r.force_login(self.resp)

    def entree(self, *lignes):
        return self.a.post("/api/entrees/", {"date_reception": timezone.localdate().isoformat(), "magasin": self.ank.id,
                                             "lignes": list(lignes)}, format="json")

    def box_ont(self):
        rep = self.a.post("/api/articles/", {"nom": "Box ONT test", "categorie": self.conso.categorie_id, "type": "CONSOMMABLE",
                                             "unite": "piece", "emplacement": self.conso.emplacement_id}, format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        return Article.objects.get(id=rep.data["id"])

    # ---------------------------------------------------------------- Entrée en stock : un état par unité
    def test_entree_un_etat_par_exemplaire(self):
        rep = self.entree({"article": self.serie.id, "quantite": 3, "etat": "NEUF", "exemplaires": [
            {"numero_serie": "SD-1", "etat": "NEUF"}, {"numero_serie": " SD-2 ", "etat": "MAUVAIS"},
            {"numero_serie": "SD-3", "etat": "NEUF"}]})
        self.assertEqual(rep.status_code, 201, rep.data)
        etats = dict(Exemplaire.objects.filter(numero_serie__startswith="SD-").values_list("numero_serie", "etat"))
        self.assertEqual(etats, {"SD-1": "NEUF", "SD-2": "MAUVAIS", "SD-3": "NEUF"})
        ligne = LigneEntree.objects.get(article=self.serie)
        self.assertEqual((ligne.quantite, ligne.etat, ligne.numeros_serie), (3, "NEUF", "SD-1\nSD-2\nSD-3"))
        m = MouvementEtat.objects.get(type="RECEPTION", exemplaire__numero_serie="SD-2")
        self.assertEqual(m.etat_apres, "MAUVAIS")

    def test_entree_erreurs_par_case(self):
        rep = self.entree({"article": self.serie.id, "quantite": 4, "exemplaires": [
            {"numero_serie": "X-1"}, {"numero_serie": ""}, {"numero_serie": "X-1"}, {"numero_serie": "RT-SN-0"}]})
        self.assertEqual(rep.status_code, 400)
        err = rep.data["lignes"][0]
        self.assertIn("Il manque 1", err["numeros_serie"][0])
        cases = err["exemplaires"]
        self.assertIn("à saisir", cases[1]["numero_serie"][0])
        self.assertIn("double", cases[2]["numero_serie"][0])
        self.assertIn("Déjà enregistré", cases[3]["numero_serie"][0])
        self.assertFalse(Exemplaire.objects.filter(numero_serie="X-1").exists())
        # Moins de cases que la quantité : il manque des n°
        rep = self.entree({"article": self.serie.id, "quantite": 3, "exemplaires": [{"numero_serie": "X-9"}]})
        self.assertIn("Il manque 2", rep.data["lignes"][0]["numeros_serie"][0])

    # ---------------------------------------------------------------- Consommable suivi par n° de série
    def test_consommable_suivi_par_serie_de_bout_en_bout(self):
        box = self.box_ont()
        choix = {a["id"]: a for a in self.a.get("/api/choix/").data["articles"]}
        self.assertEqual((choix[box.id]["suivi_serie"], choix[box.id]["serie_possible"]), (False, True))
        # « Ce produit a des n° de série ? » : stock à 0, aucun n° à saisir maintenant
        rep = self.a.post(f"/api/articles/{box.id}/suivi-serie/", {"exemplaires": []}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertTrue(self.a.get("/api/choix/").data["articles"] and Article.objects.get(id=box.id).suivi_serie)
        # Réception : les n° sont maintenant obligatoires
        self.assertEqual(self.entree({"article": box.id, "quantite": 2}).status_code, 400)
        rep = self.entree({"article": box.id, "quantite": 2, "exemplaires": [
            {"numero_serie": "ONT-A", "etat": "NEUF"}, {"numero_serie": "ONT-B", "etat": "BON"}]})
        self.assertEqual(rep.status_code, 201, rep.data)
        fiche = self.a.get(f"/api/articles/{box.id}/").data
        self.assertEqual(fiche["qte_disponible"], 2)
        self.assertTrue(fiche["repartition"]["par_serie"])
        # Demande (sans date de retour : consommable) → validation → visa → sortie en cochant ONT-A
        rep = self.s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [{"article": box.id, "quantite": 1}]},
                          format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        d = Demande.objects.get(id=rep.data["id"])
        l = d.lignes.get()
        self.assertEqual(self.a.post(f"/api/a-valider/{d.id}/valider/", {"signature": SIGNATURE, "mot_de_passe": "x",
                         "lignes": [{"id": l.id, "qte_accordee": 1}]}, format="json").status_code, 200)
        self.assertEqual(self.r.post(f"/api/a-viser/{d.id}/viser/", {"signature": SIGNATURE, "mot_de_passe": "x"},
                                     format="json").status_code, 200)
        self.assertEqual(self.a.get(f"/api/requisitions/{d.id}/pdf/").status_code, 200)
        a_cocher = self.a.get(f"/api/sorties/{d.id}/").data["lignes"][0]
        self.assertTrue(a_cocher["article"]["suivi_par_serie"])
        self.assertEqual([e["numero_serie"] for e in a_cocher["exemplaires_en_stock"]], ["ONT-A", "ONT-B"])
        ont_a = Exemplaire.objects.get(numero_serie="ONT-A")
        rep = self.a.post(f"/api/sorties/{d.id}/confirmer/", {"date_remise": timezone.localdate().isoformat(),
                          "lignes": [{"id": l.id, "exemplaires": [ont_a.id]}]}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        ont_a.refresh_from_db()
        self.assertEqual(ont_a.statut, "CONSOMME")
        self.assertEqual(ont_a.get_statut_display(), "Sorti (consommé)")
        self.assertEqual(ont_a.prete_a, "Jean Rabe")
        self.assertEqual(self.a.get(f"/api/articles/{box.id}/").data["qte_disponible"], 1)
        self.assertNotIn(box.id, prete_dehors())  # aucun retour attendu
        self.assertEqual(MouvementEtat.objects.filter(type="SORTIE", exemplaire=ont_a).count(), 1)

    def test_consommable_unite_verrouillee(self):
        box = self.box_ont()
        Article.objects.filter(id=box.id).update(suivi_serie=True)
        rep = self.a.patch(f"/api/articles/{box.id}/", {"unite": "m"}, format="json")
        self.assertEqual(rep.status_code, 400)
        self.assertIn("pièce", rep.data["unite"][0])
        # Un consommable sans n° de série peut toujours changer d'unité
        self.assertEqual(self.a.patch(f"/api/articles/{self.conso.id}/", {"unite": "m"}, format="json").status_code, 200)
