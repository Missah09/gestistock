"""Tests du journal (15/10/2026) : modifications dans l'Historique (ancienne → nouvelle valeur), historique des comptes
et journal de connexion (administrateur seulement). Lancer : python manage.py test stock"""
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from stock import tests_retours  # (module importé, pas la classe : ses tests ne sont pas relancés ici)
from stock.models import Article, Categorie, Demande, Evenement
from stock.tests_outils import SIGNATURE


def lignes_historique(client, **filtres):
    return client.get("/api/historique/", {"periode": "tout", **filtres}).data["lignes"]


@override_settings(GESTISTOCK_EMAILS=False)
class JournalTests(TestCase):
    setUpTestData = classmethod(tests_retours.EtatEtRetoursTests.setUpTestData.__func__)
    sortie = tests_retours.EtatEtRetoursTests.sortie

    def setUp(self):
        self.s = APIClient(); self.s.force_login(self.saisisseur)
        self.a = APIClient(); self.a.force_login(self.agent)
        self.r = APIClient(); self.r.force_login(self.resp)
        self.chef = User.objects.create_superuser("chef", password="Chef-2026!x", first_name="Haja", last_name="Admin")
        self.adm = APIClient(); self.adm.force_login(self.chef)
        from django.core.cache import cache
        cache.clear()                       # compteurs d'essais ratés
        Evenement.objects.all().delete()    # les connexions ci-dessus (force_login) ne comptent pas

    # ---------------------------------------------------------------- Historique : modifications
    def test_fiche_article_modifiee(self):
        a = self.conso
        rep = self.a.patch(f"/api/articles/{a.id}/", {"prix_unitaire": "13000", "qte_minimale": 12, "marque": "Corning"}, format="json")
        self.assertEqual(rep.status_code, 200, rep.data)
        e = Evenement.objects.get(article=a, action="article_modifie")
        self.assertIn("Qté minimale :", e.detail)
        self.assertIn("→ 12", e.detail)
        self.assertIn("→ 13 000 Ar", e.detail)
        self.assertRegex(e.detail, r"Marque : [^·]+ → Corning")
        self.assertNotIn("Nom :", e.detail)                                    # seulement ce qui a changé
        h = [l for l in lignes_historique(self.a, type="modification")]
        self.assertEqual(len(h), 1)
        self.assertEqual((h[0]["article_id"], h[0]["code"], h[0]["reference"]), (a.id, a.code, "Fiche article"))
        self.assertTrue(h[0]["detail"].startswith("Fiche article modifiée · "))
        # Même chose une deuxième fois : rien de nouveau
        self.a.patch(f"/api/articles/{a.id}/", {"prix_unitaire": "13000", "qte_minimale": 12, "marque": "Corning"}, format="json")
        self.assertEqual(Evenement.objects.filter(action="article_modifie").count(), 1)
        # La recherche et le filtre « Utilisateur » trouvent la ligne
        self.assertEqual(len(lignes_historique(self.a, q="Corning")), 1)
        self.assertTrue(any(u["id"] == self.agent.id for u in self.a.get("/api/historique/").data["utilisateurs"]))

    def test_article_cree_et_prix_mis_a_jour_par_une_entree(self):
        rep = self.a.post("/api/articles/", {"nom": "Pince à dénuder", "categorie": self.conso.categorie_id, "type": "CONSOMMABLE",
                                             "unite": "piece", "emplacement": self.conso.emplacement_id, "qte_minimale": 2,
                                             "prix_unitaire": "8000"}, format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        cree = Evenement.objects.get(action="article_cree")
        self.assertEqual(cree.article_id, rep.data["id"])
        self.assertIn("Prix unitaire : 8 000 Ar", cree.detail)
        base = {"date_reception": timezone.localdate().isoformat(), "magasin": self.ank.id}
        self.a.post("/api/entrees/", {**base, "lignes": [{"article": rep.data["id"], "quantite": 5, "prix_unitaire": "8000"}]}, format="json")
        self.assertFalse(Evenement.objects.filter(action="prix_entree").exists())  # même prix : rien
        self.a.post("/api/entrees/", {**base, "lignes": [{"article": rep.data["id"], "quantite": 5, "prix_unitaire": "9500"}]}, format="json")
        p = Evenement.objects.get(action="prix_entree")
        self.assertEqual(p.detail, "Prix unitaire : 8 000 Ar → 9 500 Ar (dernier prix d'achat)")
        self.assertTrue(p.reference.startswith("Réception du"))

    def test_demande_annulee_et_bons_de_retour(self):
        rep = self.s.post("/api/demandes/", {"magasin": self.ank.id, "lignes": [{"article": self.conso.id, "quantite": 1}]}, format="json")
        d = Demande.objects.get(id=rep.data["id"])
        self.assertEqual(self.s.post(f"/api/demandes/{d.id}/annuler/").status_code, 200)
        h = [l for l in lignes_historique(self.a, type="demande") if l["detail"] == "Demande annulée par le demandeur"]
        self.assertEqual((len(h), h[0]["reference"]), (1, d.numero))
        # Bon de retour imprimé puis annulé
        d2 = self.sortie(avec_serie=False)
        rep = self.a.post(f"/api/retours/{d2.id}/bon/", {"signature": SIGNATURE, "mot_de_passe": "x"}, format="json")
        bon = rep.data["demande"]["retour"]["bon_ouvert"]
        self.assertEqual(self.a.post(f"/api/retours/bons/{bon['id']}/annuler/").status_code, 200)
        retours = [l for l in lignes_historique(self.a, type="retour") if l["reference"] == bon["numero"]]
        self.assertEqual(sorted(l["detail"].split(" (")[0].split(" :")[0] for l in retours),
                         ["Bon de retour annulé", "Bon de retour imprimé"])
        self.assertTrue(all("Rasoa" in l["par"] for l in retours))

    def test_administration_django(self):
        c = Client(); c.force_login(self.chef)
        cat = Categorie.objects.first()
        rep = c.post(f"/admin/stock/categorie/{cat.id}/change/", {"nom": "Câbles et fibres", "prefixe": cat.prefixe})
        self.assertEqual(rep.status_code, 302)
        e = Evenement.objects.get(action="admin_modif")
        self.assertEqual((e.categorie, e.reference, e.par_id), ("MODIFICATION", "Administration", self.chef.id))
        self.assertEqual(e.detail, f"Nom : {cat.nom} → Câbles et fibres")
        self.assertTrue(any(l["detail"].startswith("Modifié dans l'administration") for l in lignes_historique(self.a)))
        # Le journal lui-même ne se modifie pas dans l'administration
        self.assertEqual(c.post(f"/admin/stock/evenement/{e.id}/delete/", {"post": "yes"}).status_code, 403)
        # Rôle donné dans l'administration : historique des comptes, pas l'Historique
        u = self.saisisseur
        rep = c.post(f"/admin/auth/user/{u.id}/change/", {
            "username": u.username, "first_name": u.first_name, "last_name": u.last_name, "email": "", "is_active": "on",
            "groups": [Group.objects.get(name="Agent Logistique").id], "last_login_0": "", "last_login_1": "",
            "date_joined_0": "15/10/2026", "date_joined_1": "08:00:00",
            "profil-TOTAL_FORMS": "1", "profil-INITIAL_FORMS": "1", "profil-MIN_NUM_FORMS": "1", "profil-MAX_NUM_FORMS": "1",
            "profil-0-id": u.profil.id, "profil-0-user": u.id, "profil-0-departement": ""})
        self.assertEqual(rep.status_code, 302, rep.content[:3000])
        e = Evenement.objects.get(action="admin_modif", categorie="COMPTE")
        self.assertIn("→ Agent Logistique", e.detail)
        self.assertFalse(any("Agent Logistique" in l["detail"] for l in lignes_historique(self.a, type="modification")))

    # ---------------------------------------------------------------- Comptes (administrateur)
    def test_historique_des_comptes(self):
        from stock.models import Departement
        dep = Departement.objects.filter(actif=True).first()
        rep = self.adm.post("/api/comptes/", {"identifiant": "koto", "prenom": "Koto", "nom": "Rabe", "departement": dep.id,
                                              "mot_de_passe": "Koto-2026!long"}, format="json")
        self.assertEqual(rep.status_code, 201, rep.data)
        k = User.objects.get(username="koto")
        self.adm.patch(f"/api/comptes/{k.id}/", {"prenom": "Koto", "nom": "Rabearisoa", "departement": dep.id, "agent": True}, format="json")
        self.adm.post(f"/api/comptes/{k.id}/mot-de-passe/", {"mot_de_passe": "Autre-2026!long"}, format="json")
        self.adm.post(f"/api/comptes/{k.id}/activer/", {"actif": False}, format="json")
        self.adm.post(f"/api/comptes/{k.id}/deconnecter/", {}, format="json")
        actions = list(Evenement.objects.filter(categorie="COMPTE", compte=k).order_by("id").values_list("action", flat=True))
        self.assertEqual(actions, ["compte_cree", "compte_modifie", "mot_de_passe", "compte_desactive", "deconnexion_forcee"])
        modif = Evenement.objects.get(action="compte_modifie")
        self.assertIn("Nom : Rabe → Rabearisoa", modif.detail)
        self.assertIn("Rôles : Saisisseur → Agent Logistique", modif.detail)
        self.assertFalse(Evenement.objects.filter(detail__contains="Autre-2026").exists())   # jamais le mot de passe
        # Écran : administrateur seulement ; jamais dans l'Historique de l'Agent Logistique
        rep = self.adm.get("/api/comptes/journal/", {"vue": "comptes", "compte": k.id})
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.data["count"], 5)
        self.assertEqual(rep.data["lignes"][0]["evenement"], "Déconnecté par l'administrateur")
        self.assertIn("Haja", rep.data["lignes"][0]["par"])
        self.assertEqual(self.a.get("/api/comptes/journal/").status_code, 403)
        self.assertFalse(any("Koto" in l["article"] + l["detail"] for l in lignes_historique(self.a)))

    def test_journal_de_connexion(self):
        c = APIClient(REMOTE_ADDR="10.0.0.7", HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0) Chrome/120.0 Safari/537.36")
        self.assertEqual(c.post("/api/connexion/", {"identifiant": "rabe", "mot_de_passe": "faux"}, format="json").status_code, 400)
        c.post("/api/connexion/", {"identifiant": "inconnu", "mot_de_passe": "x"}, format="json")
        # « Rabe » (majuscule acceptée) alors que self.s est connecté ailleurs : l'autre appareil est déconnecté
        self.assertEqual(c.post("/api/connexion/", {"identifiant": "Rabe", "mot_de_passe": "x"}, format="json").status_code, 200)
        c.post("/api/deconnexion/")
        ev = list(Evenement.objects.filter(categorie="CONNEXION").order_by("id"))
        self.assertEqual([e.action for e in ev], ["connexion_ratee", "connexion_ratee", "connexion", "session_remplacee", "deconnexion"])
        self.assertIn("Mot de passe incorrect", ev[0].detail)
        self.assertEqual((ev[0].compte_id, ev[1].compte_id, ev[1].identifiant), (self.saisisseur.id, None, "inconnu"))
        self.assertIn("Identifiant inconnu", ev[1].detail)
        self.assertEqual((ev[2].adresse_ip, ev[2].appareil, ev[2].detail), ("10.0.0.7", "Windows · Chrome", "Application"))
        self.assertFalse(Evenement.objects.filter(detail__contains="faux").exists())
        # 5 essais ratés : blocage noté
        for _ in range(5):
            c.post("/api/connexion/", {"identifiant": "resp", "mot_de_passe": "mauvais"}, format="json")
        c.post("/api/connexion/", {"identifiant": "resp", "mot_de_passe": "x"}, format="json")
        self.assertTrue(Evenement.objects.filter(action="connexion_bloquee", compte=self.resp).exists())
        # Écran de l'administrateur : filtre « Échecs seulement », filtre « Compte »
        rep = self.adm.get("/api/comptes/journal/", {"vue": "connexions", "resultat": "echecs"})
        self.assertEqual(rep.data["count"], 8)
        rep = self.adm.get("/api/comptes/journal/", {"vue": "connexions", "compte": self.saisisseur.id})
        self.assertEqual([l["evenement"] for l in rep.data["lignes"]],
                         ["Déconnexion", "Déconnecté de l'autre appareil", "Connexion", "Connexion refusée"])
        self.assertEqual(rep.data["lignes"][2]["adresse_ip"], "10.0.0.7")
        self.assertEqual(self.a.get("/api/comptes/journal/", {"vue": "connexions"}).status_code, 403)
