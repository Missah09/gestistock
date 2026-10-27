"""Tests de « Passer au suivi par n° de série » depuis la fiche article (15/10/2026).
Lancer : python manage.py test stock"""
import datetime

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.db.models import Count
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from stock import etats
from stock.models import Article, Exemplaire, Magasin, MouvementEtat
from stock.tests_outils import SIGNATURE
from stock import tests_retours  # (module importé, pas la classe : ses tests ne sont pas relancés ici)


@override_settings(GESTISTOCK_EMAILS=False)
class PassageSuiviSerieTests(TestCase):
    setUpTestData = classmethod(tests_retours.EtatEtRetoursTests.setUpTestData.__func__)
    sortie = tests_retours.EtatEtRetoursTests.sortie  # demande de casques jusqu'à la sortie confirmée

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.saisisseur)
        self.a = APIClient(); self.a.force_login(self.agent)
        self.r = APIClient(); self.r.force_login(self.resp)
        # Casques : 7 « Bon » et 3 « Moyen » au magasin
        etats.retirer(self.casque, "BON", 3)
        etats.ajouter(self.casque, "MOYEN", 3)

    def url(self, article):
        return f"/api/articles/{article.id}/suivi-serie/"

    def lignes(self, n, prefixe="CQ", etat="BON"):
        return [{"numero_serie": f"{prefixe}-{i:03d}", "etat": etat} for i in range(n)]

    def test_passage_garde_le_stock_et_les_etats(self):
        fiche = self.a.get(f"/api/articles/{self.casque.id}/").data
        self.assertFalse(fiche["suivi_serie"])
        self.assertEqual((fiche["qte_disponible"], fiche["repartition"]["etats"]["MOYEN"]), (10, 3))
        lignes = self.lignes(7) + self.lignes(3, "CQM", "MOYEN")
        lignes[0].update(code_immo="IMMO-CQ-1", date_etalonnage="2027-01-15")
        rep = self.a.post(self.url(self.casque), {"exemplaires": lignes}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertIn("désormais suivi par n° de série", rep.data["message"])
        self.assertTrue(rep.data["suivi_serie"])
        self.assertEqual(len(rep.data["exemplaires"]), 10)
        self.assertEqual(rep.data["qte_disponible"], 10)                       # le stock ne change pas
        self.assertEqual(rep.data["repartition"]["etats"]["MOYEN"], 3)
        self.assertTrue(rep.data["repartition"]["par_serie"])
        e = Exemplaire.objects.get(numero_serie="CQ-000")
        self.assertEqual((e.code_immo, str(e.date_etalonnage), e.statut), ("IMMO-CQ-1", "2027-01-15", "EN_STOCK"))
        # Historique : 10 mouvements sans effet sur le stock, regroupés en une ligne « 10 → 10 »
        m = MouvementEtat.objects.filter(article=self.casque, motif="Passage au suivi par n° de série")
        self.assertEqual((m.count(), sum(x.variation for x in m)), (10, 0))
        self.assertTrue(all(x.par_id == self.agent.id for x in m))
        h = [l for l in self.a.get("/api/historique/").data["lignes"] if "Passage au suivi" in l.get("detail", "")]
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["stock"], "10 → 10")
        self.assertIn("CQ-000", h[0]["detail"])
        # Définitif : une seconde fois est refusée ; l'entrée en stock demande désormais les n°
        self.assertEqual(self.a.post(self.url(self.casque), {"exemplaires": []}, format="json").status_code, 400)
        entree = {"date_reception": timezone.localdate().isoformat(), "magasin": self.ank.id,
                  "lignes": [{"article": self.casque.id, "quantite": 2}]}
        self.assertIn("numeros_serie", self.a.post("/api/entrees/", entree, format="json").data["lignes"][0])
        entree["lignes"][0]["numeros_serie"] = ["CQ-NOUV-1", "CQ-NOUV-2"]
        self.assertEqual(self.a.post("/api/entrees/", entree, format="json").status_code, 201)
        self.assertEqual(self.a.get(f"/api/articles/{self.casque.id}/").data["qte_disponible"], 12)

    def test_verifications(self):
        url = self.url(self.casque)
        # Pas le bon nombre
        rep = self.a.post(url, {"exemplaires": self.lignes(9)}, format="json")
        self.assertIn("Indiquez 10 n° de série", rep.data["general"][0])
        # N° vide, en double, déjà utilisé sur un autre article ; code immo déjà utilisé
        lignes = self.lignes(10)
        lignes[1]["numero_serie"] = ""
        lignes[2]["numero_serie"] = lignes[3]["numero_serie"] = "DOUBLE"
        lignes[4]["numero_serie"] = "RT-SN-0"
        lignes[5]["code_immo"] = "IMMO-1"
        rep = self.a.post(url, {"exemplaires": lignes}, format="json")
        self.assertEqual(rep.status_code, 400)
        err = rep.data["exemplaires"]
        self.assertIn("obligatoire", str(err[1]["numero_serie"][0]))
        self.assertIn("double", str(err[2]["numero_serie"][0]))
        self.assertIn("existe déjà", str(err[4]["numero_serie"][0]))
        self.assertIn("existe déjà", str(err[5]["code_immo"][0]))
        self.assertFalse(Article.objects.get(id=self.casque.id).suivi_serie)       # rien n'a changé
        self.assertEqual(Exemplaire.objects.filter(article=self.casque).count(), 0)

    def test_qui_et_quoi(self):
        lignes = {"exemplaires": self.lignes(10)}
        self.assertEqual(self.s.post(self.url(self.casque), lignes, format="json").status_code, 403)   # demandeur
        # Consommable à la pièce : accepté depuis le 26/10/2026 (ici : il faut un n° par unité au magasin)
        rep = self.a.post(self.url(self.conso), {"exemplaires": []}, format="json")
        self.assertIn("Indiquez 50 n° de série", rep.data["general"][0])
        metre = Article.objects.create(nom="Câble au mètre", categorie=self.conso.categorie, type="CONSOMMABLE",
                                       unite="m", emplacement=self.conso.emplacement)
        rep = self.a.post(self.url(metre), {"exemplaires": []}, format="json")                          # au mètre
        self.assertIn("comptés à la pièce", rep.data["general"][0])
        rep = self.a.post(self.url(self.serie), {"exemplaires": []}, format="json")                     # déjà suivi
        self.assertIn("déjà suivi", rep.data["general"][0])
        admin = APIClient(); admin.force_login(User.objects.create_superuser("chef", password="x"))
        self.assertEqual(admin.post(self.url(self.casque), lignes, format="json").status_code, 200)

    def test_refuse_tant_que_des_unites_pretees_ne_sont_pas_rendues(self):
        etats.retirer(self.casque, "MOYEN", 3)   # tout en « Bon » : la sortie n'a pas à préciser l'état
        etats.ajouter(self.casque, "BON", 3)
        d = self.sortie(casques=8, avec_serie=False)
        self.assertEqual(self.a.get(f"/api/articles/{self.casque.id}/").data["qte_disponible"], 2)
        rep = self.a.post(self.url(self.casque), {"exemplaires": self.lignes(2)}, format="json")
        self.assertEqual(rep.status_code, 400)
        self.assertIn("8 unités sont encore dehors", rep.data["general"][0])
        # Tout est rendu : le passage est possible, avec les 10 unités
        rep = self.a.post(f"/api/retours/{d.id}/bon/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
        bon = rep.data["demande"]["retour"]["bon_ouvert"]
        ligne = next(l for l in bon["lignes"] if l["article"]["id"] == self.casque.id)
        rep = self.a.post(f"/api/retours/bons/{bon['id']}/confirmer/", {
            "date_retour": timezone.localdate().isoformat(), "magasinier": "Koto", "rendu_par": "Jean Rabe",
            "lignes": [{"id": ligne["id"], "etats": {"BON": 8}}]}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        rep = self.a.post(self.url(self.casque), {"exemplaires": self.lignes(10)}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertEqual(rep.data["qte_disponible"], 10)

    def test_stock_a_zero(self):
        vide = Article.objects.create(nom="Soudeuse optique", categorie=self.conso.categorie, type="PRETE",
                                      emplacement=self.conso.emplacement, qte_stock=0)
        self.assertIn("aucun n° de série", self.a.post(self.url(vide), {"exemplaires": self.lignes(1)}, format="json").data["general"][0])
        rep = self.a.post(self.url(vide), {"exemplaires": []}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        self.assertIn("prochaine entrée en stock", rep.data["message"])
        self.assertTrue(Article.objects.get(id=vide.id).suivi_serie)
        self.assertTrue(MouvementEtat.objects.filter(article=vide, motif__startswith="Passage au suivi").exists())

    def test_correction_d_un_numero_inscrite_dans_l_historique(self):
        from stock.models import Evenement
        self.a.post(self.url(self.casque), {"exemplaires": self.lignes(10)}, format="json")
        fiche = self.a.get(f"/api/articles/{self.casque.id}/").data
        ex = [{"id": e["id"], "numero_serie": e["numero_serie"], "code_immo": e["code_immo"]} for e in fiche["exemplaires"]]
        ex[0]["numero_serie"] = "CQ-0O0-CORRIGE"                                    # faute de frappe corrigée
        ex[1]["numero_serie"], ex[2]["numero_serie"] = ex[2]["numero_serie"], ex[1]["numero_serie"]  # deux n° inversés
        ex[3]["code_immo"] = "IM-77"
        rep = self.a.patch(f"/api/articles/{self.casque.id}/", {"exemplaires": ex}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        e = Evenement.objects.get(article=self.casque, action="article_modifie")      # une ligne par enregistrement
        self.assertEqual((e.categorie, e.par_id, e.reference), ("MODIFICATION", self.agent.id, "Fiche article"))
        for morceau in ("N° de série : CQ-000 → CQ-0O0-CORRIGE", "N° de série : CQ-001 → CQ-002",
                        "N° de série : CQ-002 → CQ-001", "Code immo (CQ-003) : — → IM-77"):
            self.assertIn(morceau, e.detail)
        h = [l for l in self.a.get("/api/historique/").data["lignes"] if l["type"] == "modification"]
        self.assertEqual(len(h), 1)
        self.assertEqual((h[0]["quantite"], h[0]["stock"], h[0]["type_libelle"]), ("", "", "Modification"))
        self.assertIn("Rasoa", h[0]["par"])
        # Rien de changé : aucune ligne de plus
        self.a.patch(f"/api/articles/{self.casque.id}/", {"exemplaires": ex}, format="json")
        self.assertEqual(Evenement.objects.filter(article=self.casque, action="article_modifie").count(), 1)
