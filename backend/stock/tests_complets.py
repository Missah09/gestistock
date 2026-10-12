"""Tests des écrans Articles et Demandes.
Lancer :  python manage.py test stock
(base de test temporaire : vos données ne sont pas touchées)"""
from datetime import date, timedelta
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from stock.models import Article, Chantier, Demande, Exemplaire, Magasin, LigneDemande, etat_stock

class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("charger_exemples", verbosity=0)
        cls.ank = Magasin.objects.get(nom="Ankorondrano")
        cls.man = Magasin.objects.get(nom="Manandriana")
        cls.ch = Chantier.objects.create(nom="Chantier Ivato")
        cls.ch_fini = Chantier.objects.create(nom="Chantier fini", actif=False)
        from django.contrib.auth.models import Group, User
        cls.agent = User.objects.create_user("agent", password="Mdp-agent-2026")
        cls.agent.groups.add(Group.objects.get(name="Agent Logistique"))
    def setUp(self):
        # Depuis le 11/10/2026 il faut être connecté : les tests agissent en Agent Logistique.
        self.c = APIClient(); self.c.force_login(self.agent)
    def art(self, code): return Article.objects.get(code=code)

class ArticlesTests(Base):
    def test_liste(self):
        r = self.c.get("/api/articles/"); self.assertEqual(r.status_code, 200)
        self.assertIn("results", r.data); self.assertGreater(r.data["count"], 0)
        l = r.data["results"][0]
        for k in ["id","code","nom","categorie","type","unite","qte_disponible","qte_minimale","etat","emplacement","magasin"]:
            self.assertIn(k, l)
    def test_pagination(self):
        r = self.c.get("/api/articles/?page=1"); self.assertEqual(r.status_code, 200)
        r = self.c.get("/api/articles/?page=99"); self.assertEqual(r.status_code, 404)
    def test_recherche_nom_code_serie_immo(self):
        for q, code in [("soudeuse","OUT-0101"),("CAB-0012","CAB-0012"),("SN-11873","OUT-0101"),("IMMO-2023-031","OUT-0120")]:
            codes = [a["code"] for a in self.c.get("/api/articles/", {"q": q}).data["results"]]
            self.assertIn(code, codes, q)
        self.assertEqual(self.c.get("/api/articles/", {"q": "zzzz"}).data["count"], 0)
    def test_filtres(self):
        r = self.c.get("/api/filtres/").data
        self.assertTrue(r["categories"]); self.assertEqual({m["nom"] for m in r["magasins"]} >= {"Ankorondrano","Manandriana"}, True)
        res = self.c.get("/api/articles/", {"magasin": self.man.id, "page_size": 100}).data["results"]
        self.assertTrue(res and all(a["magasin"] == "Manandriana" for a in res))
        cat = self.art("CAB-0012").categorie_id
        res = self.c.get("/api/articles/", {"categorie": cat}).data["results"]
        self.assertTrue(all(a["categorie"] == "Câbles" for a in res))
    def test_sous_seuil(self):
        res = self.c.get("/api/articles/", {"sous_seuil": "1"}).data
        allres = res["results"]
        self.assertTrue(all(a["etat"] != "OK" for a in allres), allres)
        codes = [a["code"] for a in allres]; self.assertIn("RAC-0110", codes); self.assertNotIn("CAB-0012", codes)
    def test_quantite_pretee_calculee(self):
        a = [x for x in self.c.get("/api/articles/", {"q": "OUT-0101"}).data["results"]][0]
        self.assertEqual(a["qte_disponible"], 4)  # 6 exemplaires dont 2 prêtés
    def test_etat_stock(self):
        self.assertEqual(etat_stock(0, 5), "EPUISE"); self.assertEqual(etat_stock(2, 5), "CRITIQUE")
        self.assertEqual(etat_stock(4, 5), "BAS"); self.assertEqual(etat_stock(5, 5), "OK"); self.assertEqual(etat_stock(3, 0), "OK")
    def test_fiche(self):
        a = self.art("OUT-0101"); r = self.c.get(f"/api/articles/{a.id}/")
        self.assertEqual(r.status_code, 200); self.assertEqual(len(r.data["exemplaires"]), 6)
        self.assertEqual(r.data["montant_stock"], 4 * 24500000.0)
        self.assertEqual(self.c.get("/api/articles/999999/").status_code, 404)
    def test_modification_ok(self):
        a = self.art("RAC-0110")
        r = self.c.patch(f"/api/articles/{a.id}/", {"nom": "  Connecteurs SC/APC v2 ", "qte_minimale": 150, "prix_unitaire": "3600.50"}, format="json")
        self.assertEqual(r.status_code, 200, r.data); self.assertEqual(r.data["nom"], "Connecteurs SC/APC v2")
        a.refresh_from_db(); self.assertEqual(a.qte_minimale, 150); self.assertEqual(a.code, "RAC-0110")
    def test_champs_non_modifiables(self):
        a = self.art("RAC-0110")
        self.c.patch(f"/api/articles/{a.id}/", {"code": "XXX-1", "type": "PRETE", "qte_stock": 9999}, format="json")
        a.refresh_from_db(); self.assertEqual((a.code, a.type, a.qte_stock), ("RAC-0110", "CONSOMMABLE", 40))
    def test_modification_erreurs(self):
        a = self.art("RAC-0110")
        r = self.c.patch(f"/api/articles/{a.id}/", {"nom": "", "qte_minimale": -1, "prix_unitaire": "-5"}, format="json")
        self.assertEqual(r.status_code, 400); self.assertEqual(set(r.data), {"nom","qte_minimale","prix_unitaire"})
        self.assertEqual(self.c.put(f"/api/articles/{a.id}/", {}, format="json").status_code, 405)
        self.assertEqual(self.c.delete(f"/api/articles/{a.id}/").status_code, 405)
    def test_exemplaires_echange_et_doublons(self):
        a = self.art("OUT-0120"); ex = list(a.exemplaires.order_by("numero_serie"))
        # échange de 2 n° de série
        r = self.c.patch(f"/api/articles/{a.id}/", {"exemplaires": [
            {"id": ex[0].id, "numero_serie": ex[1].numero_serie, "code_immo": ex[1].code_immo},
            {"id": ex[1].id, "numero_serie": ex[0].numero_serie, "code_immo": ex[0].code_immo}]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        ex[0].refresh_from_db(); self.assertEqual(ex[0].numero_serie, "OT-5502")
        # n° déjà utilisé sur un autre article
        r = self.c.patch(f"/api/articles/{a.id}/", {"exemplaires": [{"id": ex[0].id, "numero_serie": "SN-11873"}]}, format="json")
        self.assertEqual(r.status_code, 400)
        # doublon dans la liste
        r = self.c.patch(f"/api/articles/{a.id}/", {"exemplaires": [{"id": ex[0].id, "numero_serie": "X1"},{"id": ex[1].id, "numero_serie": "X1"}]}, format="json")
        self.assertEqual(r.status_code, 400)
        # exemplaire d'un autre article
        autre = self.art("OUT-0101").exemplaires.first()
        r = self.c.patch(f"/api/articles/{a.id}/", {"exemplaires": [{"id": autre.id, "numero_serie": "Y"}]}, format="json")
        self.assertEqual(r.status_code, 400)
        # n° vide
        r = self.c.patch(f"/api/articles/{a.id}/", {"exemplaires": [{"id": ex[0].id, "numero_serie": ""}]}, format="json")
        self.assertEqual(r.status_code, 400)
    def test_code_auto(self):
        a = self.art("RAC-0110"); n = Article.objects.create(nom="Test", categorie=a.categorie, emplacement=a.emplacement)
        self.assertEqual(n.code, "RAC-0121")
    def test_choix(self):
        r = self.c.get("/api/choix/").data
        for k in ["categories","emplacements","fournisseurs","unites","magasins","articles"]: self.assertTrue(r[k], k)
    def test_entree_met_a_jour_stock(self):
        a = self.art("RAC-0110")
        r = self.c.post("/api/entrees/", {"date_reception": str(date.today()), "magasin": self.ank.id,
             "lignes": [{"article": a.id, "quantite": 10, "prix_unitaire": "3700"}]}, format="json")
        self.assertEqual(r.status_code, 201, r.data); a.refresh_from_db(); self.assertEqual(a.qte_stock, 50)

class DemandesTests(Base):
    def payload(self, **kw):
        d = {"magasin": self.ank.id, "chantier": self.ch.id, "urgent": False,
             "lignes": [{"article": self.art("RAC-0110").id, "quantite": 5, "motif": "raccordement"}]}
        d.update(kw); return d
    def test_creation_consommable(self):
        stock_avant = self.art("RAC-0110").qte_stock
        r = self.c.post("/api/demandes/", self.payload(), format="json")
        self.assertEqual(r.status_code, 201, r.data)
        an = timezone.localdate().year
        self.assertEqual(r.data["numero"], f"DEM-{an}-0001")
        d = Demande.objects.get(id=r.data["id"]); self.assertEqual(d.statut, "EN_ATTENTE")
        self.assertEqual(self.art("RAC-0110").qte_stock, stock_avant)  # stock inchangé
        r2 = self.c.post("/api/demandes/", self.payload(), format="json"); self.assertEqual(r2.data["numero"], f"DEM-{an}-0002")
    def test_sans_chantier(self):
        r = self.c.post("/api/demandes/", self.payload(chantier=None), format="json"); self.assertEqual(r.status_code, 201, r.data)
        p = self.payload(); p.pop("chantier"); self.assertEqual(self.c.post("/api/demandes/", p, format="json").status_code, 201)
    def test_chantier_inactif(self):
        r = self.c.post("/api/demandes/", self.payload(chantier=self.ch_fini.id), format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("chantier", r.data)
    def test_consommable_date_retour_ignoree(self):
        p = self.payload(); p["lignes"][0]["date_retour_prevue"] = "2020-01-01"
        r = self.c.post("/api/demandes/", p, format="json"); self.assertEqual(r.status_code, 201, r.data)
        self.assertIsNone(LigneDemande.objects.get(demande_id=r.data["id"]).date_retour_prevue)
    def test_prete_date_obligatoire(self):
        a = self.art("OUT-0101")
        r = self.c.post("/api/demandes/", self.payload(lignes=[{"article": a.id, "quantite": 1}]), format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("date_retour_prevue", r.data["lignes"][0])
        r = self.c.post("/api/demandes/", self.payload(lignes=[{"article": a.id, "quantite": 1, "date_retour_prevue": str(date.today()-timedelta(days=1))}]), format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("passée", str(r.data))
        r = self.c.post("/api/demandes/", self.payload(lignes=[{"article": a.id, "quantite": 1, "date_retour_prevue": str(date.today()+timedelta(days=7))}]), format="json")
        self.assertEqual(r.status_code, 201, r.data)
    def test_erreurs_groupees(self):
        a = self.art("OUT-0101")
        r = self.c.post("/api/demandes/", {"magasin": None, "lignes": [{"article": a.id, "quantite": 0}]}, format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("magasin", r.data)
        self.assertIn("date_retour_prevue", r.data["lignes"][0]); self.assertIn("quantite", r.data["lignes"][0])
    def test_erreurs_lignes(self):
        r = self.c.post("/api/demandes/", self.payload(lignes=[]), format="json"); self.assertEqual(r.status_code, 400)
        cab = self.art("CAB-0012")  # rangé à Manandriana
        r = self.c.post("/api/demandes/", self.payload(lignes=[{"article": cab.id, "quantite": 1}]), format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("Manandriana", str(r.data))
        rac = self.art("RAC-0110").id
        r = self.c.post("/api/demandes/", self.payload(lignes=[{"article": rac, "quantite": 1},{"article": rac, "quantite": 2}]), format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("autre ligne", str(r.data))
        r = self.c.post("/api/demandes/", self.payload(lignes=[{"article": 999999, "quantite": 1}]), format="json")
        self.assertEqual(r.status_code, 400)
        r = self.c.post("/api/demandes/", self.payload(lignes=[{"article": rac, "quantite": 1, "motif": "x"*251}]), format="json")
        self.assertEqual(r.status_code, 400)
    def test_liste_onglets_compteurs_pagination(self):
        for i in range(12): self.c.post("/api/demandes/", self.payload(), format="json")
        d = Demande.objects.first(); d.statut = "VALIDEE"; d.save()
        d2 = Demande.objects.last(); d2.statut = "REFUSEE"; d2.motif_refus = "stock"; d2.save()
        r = self.c.get("/api/demandes/").data
        self.assertEqual(r["compteurs"], {"attente": 10, "validees": 1, "refusees": 1, "toutes": 12})
        self.assertEqual(len(r["results"]), 10)
        self.assertEqual(len(self.c.get("/api/demandes/?onglet=toutes&page=2").data["results"]), 2)
        self.assertEqual(self.c.get("/api/demandes/?page=abc").status_code, 200)
        self.assertEqual(self.c.get("/api/demandes/?onglet=inconnu").data["count"], 10)
        res = self.c.get("/api/demandes/?onglet=refusees").data["results"][0]
        self.assertEqual(res["motif_refus"], "stock"); self.assertEqual(res["destination"], "Chantier Ivato")
        self.assertIn("qte_disponible", res["lignes"][0]["article"])
        # ordre : plus récente d'abord
        nums = [x["numero"] for x in self.c.get("/api/demandes/?onglet=toutes").data["results"]]
        self.assertEqual(nums, sorted(nums, reverse=True))
    def test_detail_et_annulation(self):
        id_ = self.c.post("/api/demandes/", self.payload(), format="json").data["id"]
        self.assertEqual(self.c.get(f"/api/demandes/{id_}/").status_code, 200)
        self.assertEqual(self.c.get("/api/demandes/999999/").status_code, 404)
        r = self.c.post(f"/api/demandes/{id_}/annuler/"); self.assertEqual(r.status_code, 200)
        self.assertEqual(Demande.objects.get(id=id_).statut, "ANNULEE")
        r = self.c.post(f"/api/demandes/{id_}/annuler/"); self.assertEqual(r.status_code, 400)
        cpt = self.c.get("/api/demandes/").data["compteurs"]; self.assertEqual(cpt["toutes"], 1); self.assertEqual(cpt["attente"], 0)
    def test_choix_demande(self):
        r = self.c.get("/api/demandes/choix/").data
        self.assertIn("maintenant", r); self.assertTrue(r["articles"])
        self.assertEqual([c["nom"] for c in r["chantiers"]], ["Chantier Ivato"])
    def test_ancien_champ_travail(self):
        d = Demande.objects.create(magasin=self.ank, travail="Ancien travail", demandeur=self.agent)
        res = self.c.get("/api/demandes/").data["results"][0]; self.assertEqual(res["destination"], "Ancien travail")
