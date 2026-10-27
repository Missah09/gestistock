"""Écran « Rapports » (Agent Logistique, 15/10/2026) : six rapports, à voir à l'écran, en PDF ou en Excel.

D'après la maquette (écran 10) : État du stock · À commander · Consommation par chantier · Matériel prêté ·
Valeur du stock · Étalonnages à prévoir. Chaque rapport est décrit une seule fois (voir exports.py) :
l'écran, le PDF et le fichier Excel montrent exactement les mêmes lignes et les mêmes totaux.

Les règles sont celles du reste de l'application :
- quantité disponible et état du stock : comme la Liste d'Articles (articles_avec_quantites, etat_stock) ;
- « sous le seuil » et valeur du stock : comme le Tableau de bord ;
- matériel prêté encore dehors : comme l'écran « Retours de stock ».
"""
import datetime
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from . import etats
from .models import (Article, BonRetour, Categorie, Exemplaire, LigneRetour, LigneSortie, Magasin, departement_de,
                     etat_stock)
from .serializers import nom_de

LIBELLES_ETAT_STOCK = {"OK": "OK", "BAS": "Stock bas", "CRITIQUE": "Critique", "EPUISE": "Épuisé"}
TON_ETAT_STOCK = {"OK": "vert", "BAS": "orange", "CRITIQUE": "rouge", "EPUISE": "rouge"}

# ---------------------------------------------------------------- Périodes (Rapports et Historique)
PERIODES = [("jour", "Aujourd'hui"), ("semaine", "Cette semaine"), ("mois", "Ce mois-ci"),
            ("mois_dernier", "Le mois dernier"), ("annee", "Cette année"), ("tout", "Depuis le début"),
            ("choisie", "Période choisie…")]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]


def _date(valeur):
    try:
        return datetime.date.fromisoformat(str(valeur or "").strip()[:10])
    except ValueError:
        return None


def periode_de(params, defaut="semaine"):
    """(du, au, libellé) : `du`/`au` inclus, None = sans limite. Période choisie : ?du=AAAA-MM-JJ&au=AAAA-MM-JJ."""
    auj = timezone.localdate()
    p = params.get("periode") or defaut
    if p == "jour":
        return auj, auj, f"aujourd'hui ({auj:%d/%m/%Y})"
    if p == "semaine":
        lundi = auj - datetime.timedelta(days=auj.weekday())
        return lundi, auj, f"cette semaine (depuis le lundi {lundi:%d/%m/%Y})"
    if p == "mois":
        return auj.replace(day=1), auj, f"{MOIS[auj.month - 1]} {auj.year}"
    if p == "mois_dernier":
        fin = auj.replace(day=1) - datetime.timedelta(days=1)
        return fin.replace(day=1), fin, f"{MOIS[fin.month - 1]} {fin.year}"
    if p == "annee":
        return auj.replace(month=1, day=1), auj, f"année {auj.year}"
    if p == "choisie":
        du, au = _date(params.get("du")), _date(params.get("au"))
        if du and au and du > au:
            du, au = au, du
        if du and au:
            return du, au, f"du {du:%d/%m/%Y} au {au:%d/%m/%Y}"
        if du:
            return du, None, f"depuis le {du:%d/%m/%Y}"
        if au:
            return None, au, f"jusqu'au {au:%d/%m/%Y}"
    return None, None, "depuis le début"


# ---------------------------------------------------------------- Outils
def _magasin(params):
    try:
        return Magasin.objects.get(pk=int(params.get("magasin")))
    except (TypeError, ValueError, Magasin.DoesNotExist):
        return None


def _categorie(params):
    try:
        return Categorie.objects.get(pk=int(params.get("categorie")))
    except (TypeError, ValueError, Categorie.DoesNotExist):
        return None


def _articles(params):
    from .views import articles_avec_quantites
    qs = articles_avec_quantites()
    m, c = _magasin(params), _categorie(params)
    if m:
        qs = qs.filter(emplacement__magasin=m)
    if c:
        qs = qs.filter(categorie=c)
    return qs, m, c


def _filtres_texte(m=None, c=None, extra=""):
    morceaux = [f"Magasin : {m.nom if m else 'tous'}"]
    if c is not None:
        morceaux.append(f"Catégorie : {c.nom}")
    if extra:
        morceaux.append(extra)
    return " · ".join(morceaux)


def _au_jour():
    return f"au {timezone.localdate():%d/%m/%Y}"


def _etats_texte(par_etat, unite):
    """{"NEUF": 14600, "BON": 2} → « 14 600 m Neuf · 2 m Bon » (zéros omis, ordre fixe)."""
    from .exports import quantite
    return " · ".join(f"{quantite(par_etat[e], unite)} {etats.LIBELLES[e]}" for e in etats.ORDRE if par_etat.get(e))


def note(terme, texte):
    """Une ligne du bloc « Notes » en bas du rapport : un terme et sa définition (16/10/2026)."""
    return {"terme": terme, "texte": texte[:1].upper() + texte[1:]}


def alerte(texte):
    """Un point d'attention en bas du rapport (ex. articles sans prix) : affiché à part, en orange."""
    return {"alerte": True, "texte": texte}


def _pluriel(n, mot, pluriel=None):
    return f"{n} {mot if n == 1 else (pluriel or mot + 's')}"


def prete_dehors():
    """{article_id: quantité prêtée encore dehors} (matériel non consommable sorti et pas encore rendu)."""
    sortis = dict(LigneSortie.objects.filter(article__type=Article.Type.PRETE).values("article_id")
                  .annotate(n=Sum("qte_livree")).values_list("article_id", "n"))
    rendus = dict(LigneRetour.objects.filter(bon__statut=BonRetour.Statut.CONFIRME, article__type=Article.Type.PRETE)
                  .values("article_id").annotate(n=Sum("qte_rendue")).values_list("article_id", "n"))
    par_serie = dict(Exemplaire.objects.filter(statut=Exemplaire.Statut.PRETE).values("article_id")
                     .annotate(n=Count("id")).values_list("article_id", "n"))
    resultat = {}
    for aid in set(sortis) | set(par_serie):
        dehors = max(0, (sortis.get(aid) or 0) - (rendus.get(aid) or 0))
        resultat[aid] = max(dehors, par_serie.get(aid, 0))
    return resultat


# ---------------------------------------------------------------- 1. État du stock
def etat_du_stock(params):
    qs, m, c = _articles(params)
    articles = list(qs.order_by("emplacement__magasin__type", "emplacement__magasin__nom", "categorie__nom", "nom"))
    reps = etats.repartitions(articles)
    dehors = prete_dehors()
    sections, compte = {}, {"EPUISE": 0, "CRITIQUE": 0, "BAS": 0, "OK": 0}
    for a in articles:
        e = etat_stock(a.qte_disponible, a.qte_minimale)
        compte[e] += 1
        prete = a.type == Article.Type.PRETE
        ligne = {"code": a.code, "article": a.nom, "categorie": a.categorie.nom, "emplacement": a.emplacement.nom,
                 "type": "À rendre" if prete else "Consommable", "_ton_type": "violet" if prete else None,
                 "qte": a.qte_disponible, "minimum": a.qte_minimale, "etat": LIBELLES_ETAT_STOCK[e],
                 "_ton_etat": TON_ETAT_STOCK[e], "etat_produit": _etats_texte(reps[a.id]["etats"], a.unite),
                 "dehors": dehors.get(a.id, 0) if prete else None, "_unite": a.unite, "_id": a.id}
        if e in ("EPUISE", "CRITIQUE"):
            ligne["_ton_qte"] = "rouge"
        sections.setdefault(a.emplacement.magasin.nom, []).append(ligne)
    sous_seuil = compte["EPUISE"] + compte["CRITIQUE"] + compte["BAS"]
    return {
        "titre": "État du stock",
        "sous_titre": _filtres_texte(m, c, _au_jour()),
        "colonnes": [
            {"cle": "code", "titre": "Code", "type": "code", "largeur": 15},
            {"cle": "article", "titre": "Article", "largeur": 38},
            {"cle": "categorie", "titre": "Catégorie", "largeur": 20},
            {"cle": "emplacement", "titre": "Emplacement", "largeur": 20},
            {"cle": "type", "titre": "Type", "largeur": 15},
            {"cle": "qte", "titre": "Qté disponible", "type": "quantite", "largeur": 15},
            {"cle": "minimum", "titre": "Minimum", "type": "quantite", "largeur": 13},
            {"cle": "etat", "titre": "État du stock", "type": "pill", "largeur": 14},
            {"cle": "etat_produit", "titre": "État du produit", "largeur": 22},
            {"cle": "dehors", "titre": "Prêté (dehors)", "type": "quantite", "largeur": 13},
        ],
        "sections": [{"titre": f"Magasin {nom}" if len(sections) > 1 or not m else None, "lignes": lignes}
                     for nom, lignes in sections.items()],
        "resume": [["Articles", str(len(articles))], ["Sous le seuil", str(sous_seuil)],
                   ["dont épuisés", str(compte["EPUISE"])]],
        "notes": [note("Qté disponible", "quantité présente au magasin ; le matériel prêté à l'extérieur n'est pas compté."),
                  note("État du stock", "Épuisé : quantité nulle · Critique : moitié du minimum ou moins · "
                                        "Stock bas : sous la quantité minimale.")],
        "vide": "Aucun article.",
    }


# ---------------------------------------------------------------- 2. À commander
def a_commander(params):
    from .views_tableau import ORDRE_URGENCE, sous_le_seuil
    m = _magasin(params)
    qs = sous_le_seuil().select_related("fournisseur")
    if m:
        qs = qs.filter(emplacement__magasin=m)
    articles = list(qs)
    for a in articles:
        a.etat = etat_stock(a.qte_disponible, a.qte_minimale)
    articles.sort(key=lambda a: (ORDRE_URGENCE.get(a.etat, 3),
                                 a.qte_disponible / a.qte_minimale if a.qte_minimale else 0, a.nom.lower()))
    groupes, sans_minimum, sans_prix = {}, 0, 0
    total = Decimal(0)
    for a in articles:
        qte = max(0, a.qte_minimale - a.qte_disponible) if a.qte_minimale else None
        prix = a.prix_unitaire or Decimal(0)
        valeur = (Decimal(qte) * prix) if qte and prix else None
        if qte is None:
            sans_minimum += 1
        if not prix:
            sans_prix += 1
        if valeur:
            total += valeur
        f = a.fournisseur.nom if a.fournisseur_id else "Fournisseur non renseigné"
        groupes.setdefault(f, []).append({
            "code": a.code, "article": a.nom, "magasin": a.emplacement.magasin.nom, "qte": a.qte_disponible,
            "minimum": a.qte_minimale, "etat": LIBELLES_ETAT_STOCK[a.etat], "_ton_etat": TON_ETAT_STOCK[a.etat],
            "a_commander": qte, "_ton_a_commander": "bleu" if qte else None,
            "_detail_a_commander": "minimum à fixer" if qte is None else "",
            "ref": a.ref_fournisseur, "prix": prix or None, "valeur": valeur, "_unite": a.unite, "_id": a.id})
    # Les fournisseurs connus d'abord (par ordre alphabétique), puis « non renseigné ».
    ordre = sorted(groupes, key=lambda f: (f == "Fournisseur non renseigné", f.lower()))
    sections = []
    for f in ordre:
        lignes = groupes[f]
        st = sum((l["valeur"] or 0 for l in lignes), Decimal(0))
        sections.append({"titre": f"{f} – {_pluriel(len(lignes), 'article')}", "lignes": lignes,
                         "total": {"article": "Sous-total", "valeur": st} if len(ordre) > 1 else None})
    notes = [note("Qté à commander", "quantité nécessaire pour revenir au minimum, à arrondir selon le "
                                     "conditionnement du fournisseur."),
             note("Prix unitaire", "dernier prix d'achat connu.")]
    if sans_minimum:
        notes.append(alerte(f"{_pluriel(sans_minimum, 'article épuisé')} sans quantité minimale : la renseigner dans "
                            "la fiche article pour calculer la quantité à commander."))
    if sans_prix:
        notes.append(alerte(f"{_pluriel(sans_prix, 'article')} sans prix unitaire : non compté(s) dans le montant."))
    return {
        "titre": "À commander",
        "sous_titre": _filtres_texte(m, extra=_au_jour()),
        "colonnes": [
            {"cle": "code", "titre": "Code", "type": "code", "largeur": 15},
            {"cle": "article", "titre": "Article", "largeur": 38},
            {"cle": "magasin", "titre": "Magasin", "largeur": 16},
            {"cle": "qte", "titre": "Stock", "type": "quantite", "largeur": 12},
            {"cle": "minimum", "titre": "Minimum", "type": "quantite", "largeur": 12},
            {"cle": "etat", "titre": "État", "type": "pill", "largeur": 12},
            {"cle": "a_commander", "titre": "Qté à commander", "type": "quantite", "largeur": 15},
            {"cle": "ref", "titre": "Réf. fournisseur", "largeur": 16},
            {"cle": "prix", "titre": "Prix unitaire", "type": "montant", "largeur": 15},
            {"cle": "valeur", "titre": "Montant estimé", "type": "montant", "largeur": 17},
        ],
        "sections": sections,
        "total": {"article": "Total estimé", "valeur": total},
        "resume": [["Articles à commander", str(len(articles))], ["Montant estimé", f"{_fmt_montant(total)}"]],
        "notes": notes,
        "vide": "Rien à commander : tous les articles sont au-dessus de leur minimum.",
    }


def _fmt_montant(v):
    from .exports import montant
    return montant(v)


# ---------------------------------------------------------------- 3. Consommation par chantier (ou par service)
def consommation(params):
    du, au, libelle = periode_de(params, defaut="mois")
    m = _magasin(params)
    par_service = params.get("regrouper") == "service"
    qs = (LigneSortie.objects.filter(qte_livree__gt=0, article__type=Article.Type.CONSOMMABLE)
          .select_related("article", "sortie__requisition__demande__chantier",
                          "sortie__requisition__demande__demandeur__profil__departement"))
    if du:
        qs = qs.filter(sortie__date_remise__gte=du)
    if au:
        qs = qs.filter(sortie__date_remise__lte=au)
    if m:
        qs = qs.filter(sortie__requisition__demande__magasin=m)
    groupes = {}
    for ls in qs.order_by("sortie__date_remise", "id"):
        d = ls.sortie.requisition.demande
        if par_service:
            dep = departement_de(d.demandeur) if d.demandeur else None
            cle = dep.nom if dep else "Service non renseigné"
        else:
            cle = d.destination or "Hors chantier"
        a = ls.article
        g = groupes.setdefault(cle, {})
        x = g.setdefault(a.id, {"code": a.code, "article": a.nom, "qte": 0, "prix": a.prix_unitaire or None,
                                "valeur": Decimal(0), "bons": [], "_unite": a.unite, "_id": a.id})
        x["qte"] += ls.qte_livree
        x["valeur"] += Decimal(ls.qte_livree) * (a.prix_unitaire or 0)
        numero = ls.sortie.requisition.numero
        if numero not in x["bons"]:
            x["bons"].append(numero)
    sections, total, nb = [], Decimal(0), 0
    hors = "Service non renseigné" if par_service else "Hors chantier"
    for cle in sorted(groupes, key=lambda k: (k == hors, -sum(v["valeur"] for v in groupes[k].values()), k.lower())):
        lignes = sorted(groupes[cle].values(), key=lambda v: (-v["valeur"], v["article"].lower()))
        st = sum((l["valeur"] for l in lignes), Decimal(0))
        total += st
        nb += len(lignes)
        for l in lignes:
            l["bons"] = ", ".join(l["bons"])
            l["valeur"] = l["valeur"] or None
        sections.append({"titre": cle, "lignes": lignes, "total": {"article": "Sous-total", "valeur": st}})
    quoi = "service demandeur" if par_service else "chantier"
    return {
        "titre": f"Consommation par {quoi}",
        "sous_titre": _filtres_texte(m, extra=f"Période : {libelle}"),
        "colonnes": [
            {"cle": "code", "titre": "Code", "type": "code", "largeur": 15},
            {"cle": "article", "titre": "Article", "largeur": 40},
            {"cle": "qte", "titre": "Qté sortie", "type": "quantite", "largeur": 14},
            {"cle": "prix", "titre": "Prix unitaire", "type": "montant", "largeur": 15},
            {"cle": "valeur", "titre": "Valeur", "type": "montant", "largeur": 17},
            {"cle": "bons", "titre": "Bons de réquisition", "largeur": 30},
        ],
        "sections": sections,
        "total": {"article": "Total de la période", "valeur": total},
        "resume": [[f"{quoi.capitalize()}s" if not par_service else "Services", str(len(sections))],
                   ["Lignes", str(nb)], ["Valeur consommée", _fmt_montant(total)]],
        "notes": [note("Périmètre", "consommables remis par le magasin (sorties confirmées dont la date de remise "
                                    "est comprise dans la période)."),
                  note("Matériel à rendre", "voir le rapport « Matériel prêté »."),
                  note("Valeur", "calculée au prix unitaire actuel.")],
        "vide": "Aucune sortie de consommables sur cette période.",
    }


# ---------------------------------------------------------------- 4. Matériel prêté
def materiel_prete(params):
    from .views_retours import _sorties_avec_pret, lignes_a_rendre
    m = _magasin(params)
    auj = timezone.localdate()
    lignes, vus = [], set()
    sorties = _sorties_avec_pret().select_related("requisition__demande__demandeur__profil__departement",
                                                  "requisition__demande__chantier", "requisition__demande__magasin")
    if m:
        sorties = sorties.filter(requisition__demande__magasin=m)
    for s in sorties:
        d = s.requisition.demande
        dep = departement_de(d.demandeur) if d.demandeur else None
        commun = {"prete_a": nom_de(d.demandeur), "service": dep.nom if dep else "", "chantier": d.destination or "",
                  "sorti_le": s.date_remise.isoformat(), "bon": s.requisition.numero}
        for l in lignes_a_rendre(s):
            if l["reste"] <= 0:
                continue
            a = l["article"]
            prevue = l["date_retour_prevue"]
            retard = (auj - datetime.date.fromisoformat(prevue)).days if prevue else 0
            base = {**commun, "code": a["code"], "article": a["nom"], "retour_prevu": prevue, "_unite": a["unite"],
                    "_id": a["id"]}
            if retard > 0:
                base.update({"retard": f"{retard} j", "_ton_retard": "rouge", "_ton_retour_prevu": "rouge",
                             "_fond": "rouge", "_jours": retard})
            else:
                base["_jours"] = retard
            if a["suivi_par_serie"]:
                for e in l["exemplaires"]:
                    if not e["rendu"]:
                        vus.add(e["id"])
                        lignes.append({**base, "serie": e["numero_serie"], "qte": 1})
            else:
                lignes.append({**base, "serie": "", "qte": l["reste"]})
    # Exemplaires marqués « Prêté » sans sortie enregistrée (saisis avant les écrans Sorties et Retours).
    autres = Exemplaire.objects.filter(statut=Exemplaire.Statut.PRETE).exclude(id__in=vus).select_related("article__emplacement")
    if m:
        autres = autres.filter(article__emplacement__magasin=m)
    for e in autres:
        a = e.article
        lignes.append({"code": a.code, "article": a.nom, "serie": e.numero_serie, "qte": 1, "prete_a": e.prete_a,
                       "service": "", "chantier": e.chantier, "sorti_le": None, "retour_prevu": None,
                       "bon": "Sans bon", "_ton_bon": "gris", "_unite": a.unite, "_id": a.id, "_jours": -10 ** 6})
    lignes.sort(key=lambda l: (-l["_jours"], l["retour_prevu"] or "9999", l["article"].lower(), l["serie"]))
    en_retard = sum(1 for l in lignes if l["_jours"] > 0)
    return {
        "titre": "Matériel prêté",
        "sous_titre": _filtres_texte(m, extra=_au_jour()),
        "colonnes": [
            {"cle": "code", "titre": "Code", "type": "code", "largeur": 14},
            {"cle": "article", "titre": "Article", "largeur": 30},
            {"cle": "serie", "titre": "N° de série", "largeur": 17},
            {"cle": "qte", "titre": "Qté", "type": "quantite", "largeur": 9},
            {"cle": "prete_a", "titre": "Prêté à", "largeur": 20},
            {"cle": "service", "titre": "Service", "largeur": 14},
            {"cle": "chantier", "titre": "Chantier", "largeur": 18},
            {"cle": "sorti_le", "titre": "Sorti le", "type": "date", "largeur": 13},
            {"cle": "retour_prevu", "titre": "Retour prévu", "type": "date", "largeur": 13},
            {"cle": "retard", "titre": "Retard", "type": "pill", "largeur": 10},
            {"cle": "bon", "titre": "Bon", "largeur": 15},
        ],
        "sections": [{"titre": None, "lignes": lignes}],
        "resume": [["Lignes", str(len(lignes))], ["En retard", str(en_retard)]],
        "notes": [note("Périmètre", "matériel non consommable sorti du magasin et non encore rendu "
                                    "(retours confirmés déduits)."),
                  note("Retards", "date de retour prévue dépassée ; lignes affichées en premier, en rouge.")],
        "vide": "Aucun matériel prêté dehors : tout est rentré.",
    }


# ---------------------------------------------------------------- 5. Valeur du stock
def valeur_du_stock(params):
    qs, m, c = _articles(params)
    groupes, total, sans_prix = {}, Decimal(0), 0
    for a in qs.order_by("categorie__nom", "nom"):
        prix = a.prix_unitaire or Decimal(0)
        valeur = Decimal(a.qte_disponible or 0) * prix
        if not prix and a.qte_disponible:
            sans_prix += 1
        total += valeur
        groupes.setdefault(a.categorie.nom, []).append({
            "code": a.code, "article": a.nom, "magasin": a.emplacement.magasin.nom, "qte": a.qte_disponible,
            "prix": prix or None, "_detail_prix": "" if prix else "non renseigné", "valeur": valeur,
            "_unite": a.unite, "_id": a.id})
    sections = []
    for cat, lignes in groupes.items():
        st = sum((l["valeur"] for l in lignes), Decimal(0))
        sections.append({"titre": f"{cat} – {_fmt_montant(st)}", "lignes": lignes,
                         "total": {"article": f"Sous-total {cat}", "valeur": st}, "_valeur": st})
    sections.sort(key=lambda s: -s.pop("_valeur"))
    notes = [note("Valeur", "quantité disponible au magasin × prix unitaire (dernier prix d'achat)."),
             note("Périmètre", "le matériel prêté à l'extérieur n'est pas compté (même total que la carte "
                               "« Valeur du stock » du tableau de bord).")]
    if sans_prix:
        notes.append(alerte(f"{_pluriel(sans_prix, 'article')} en stock sans prix unitaire : compté(s) pour 0 Ar."))
    return {
        "titre": "Valeur du stock",
        "sous_titre": _filtres_texte(m, c, _au_jour()),
        "colonnes": [
            {"cle": "code", "titre": "Code", "type": "code", "largeur": 15},
            {"cle": "article", "titre": "Article", "largeur": 42},
            {"cle": "magasin", "titre": "Magasin", "largeur": 16},
            {"cle": "qte", "titre": "Qté disponible", "type": "quantite", "largeur": 15},
            {"cle": "prix", "titre": "Prix unitaire", "type": "montant", "largeur": 16},
            {"cle": "valeur", "titre": "Valeur", "type": "montant", "largeur": 18},
        ],
        "sections": sections,
        "total": {"article": "Valeur totale du stock", "valeur": total},
        "resume": [["Valeur totale", _fmt_montant(total)], ["Catégories", str(len(sections))]],
        "notes": notes,
        "vide": "Aucun article.",
    }


# ---------------------------------------------------------------- 6. Étalonnages à prévoir
HORIZONS = [("30", "Dans les 30 jours"), ("90", "Dans les 3 mois"), ("180", "Dans les 6 mois"), ("365", "Dans l'année"),
            ("tout", "Toutes les dates")]


def etalonnages(params):
    m = _magasin(params)
    auj = timezone.localdate()
    horizon = params.get("horizon") or "90"
    qs = (Exemplaire.objects.filter(date_etalonnage__isnull=False).exclude(statut=Exemplaire.Statut.REBUT)
          .select_related("article__emplacement__magasin").order_by("date_etalonnage", "article__nom", "numero_serie"))
    if horizon.isdigit():
        qs = qs.filter(date_etalonnage__lte=auj + datetime.timedelta(days=int(horizon)))
    if m:
        qs = qs.filter(article__emplacement__magasin=m)
    lignes, depasses = [], 0
    for e in qs:
        jours = (e.date_etalonnage - auj).days
        if jours < 0:
            depasses += 1
            echeance, ton = f"Dépassé de {-jours} j", "rouge"
        elif jours == 0:
            echeance, ton = "Aujourd'hui", "rouge"
        else:
            echeance, ton = f"Dans {jours} j", "orange" if jours <= 30 else "vert"
        prete = e.statut == Exemplaire.Statut.PRETE
        lignes.append({"code": e.article.code, "article": e.article.nom, "serie": e.numero_serie,
                       "immo": e.code_immo, "date": e.date_etalonnage.isoformat(), "echeance": echeance,
                       "_ton_echeance": ton, "_ton_date": "rouge" if jours <= 0 else None,
                       "ou": f"Prêté à {e.prete_a}" if prete and e.prete_a else "Prêté" if prete else
                       f"En stock – {e.article.emplacement.magasin.nom}", "_ton_ou": "violet" if prete else None,
                       "_fond": "rouge" if jours < 0 else None, "_id": e.article_id})
    libelle = dict(HORIZONS).get(horizon, "Dans les 3 mois")
    return {
        "titre": "Étalonnages à prévoir",
        "sous_titre": _filtres_texte(m, extra=f"{libelle} (et dates dépassées) · {_au_jour()}"),
        "colonnes": [
            {"cle": "code", "titre": "Code", "type": "code", "largeur": 15},
            {"cle": "article", "titre": "Appareil", "largeur": 34},
            {"cle": "serie", "titre": "N° de série", "largeur": 18},
            {"cle": "immo", "titre": "Code immo", "largeur": 14},
            {"cle": "date", "titre": "Prochain étalonnage", "type": "date", "largeur": 16},
            {"cle": "echeance", "titre": "Échéance", "type": "pill", "largeur": 15},
            {"cle": "ou", "titre": "Où est-il ?", "largeur": 28},
        ],
        "sections": [{"titre": None, "lignes": lignes}],
        "resume": [["Appareils", str(len(lignes))], ["Dates dépassées", str(depasses)]],
        "notes": [note("Périmètre", "appareils suivis par n° de série dont la date du prochain étalonnage est renseignée."),
                  note("Mise à jour", "fiche article › Modifier › Exemplaires, ou Administration › Exemplaires.")],
        "vide": "Aucun étalonnage à prévoir sur cette période.",
    }


# ---------------------------------------------------------------- Catalogue (l'ordre est celui des cartes de l'écran)
RAPPORTS = {
    "etat-stock": {"fonction": etat_du_stock, "titre": "État du stock", "icone": "box", "ton": "bleu",
                   "description": "Tous les articles : quantité disponible, minimum, état du stock et du produit.",
                   "filtres": ["magasin", "categorie"]},
    "a-commander": {"fonction": a_commander, "titre": "À commander", "icone": "panier", "ton": "vert",
                    "description": "Les articles sous le seuil, par fournisseur, avec la quantité et le montant à prévoir.",
                    "filtres": ["magasin"]},
    "consommation": {"fonction": consommation, "titre": "Consommation par chantier", "icone": "chantier", "ton": "orange",
                     "description": "Les consommables remis sur une période, par chantier ou par service demandeur.",
                     "filtres": ["magasin", "periode", "regrouper"]},
    "materiel-prete": {"fonction": materiel_prete, "titre": "Matériel prêté", "icone": "out", "ton": "bleu-clair",
                       "description": "Le matériel à rendre encore dehors : à qui, depuis quand, les retards.",
                       "filtres": ["magasin"]},
    "valeur-stock": {"fonction": valeur_du_stock, "titre": "Valeur du stock", "icone": "billet", "ton": "violet",
                     "description": "La valeur du stock au magasin, par catégorie (quantité × prix unitaire).",
                     "filtres": ["magasin", "categorie"]},
    "etalonnages": {"fonction": etalonnages, "titre": "Étalonnages à prévoir", "icone": "clock", "ton": "rouge",
                    "description": "Les appareils (OTDR, soudeuses…) dont l'étalonnage arrive à échéance.",
                    "filtres": ["magasin", "horizon"]},
}


def construire(cle, params):
    return RAPPORTS[cle]["fonction"](params)


def catalogue():
    """Ce que l'écran affiche : les six cartes et les listes des filtres."""
    return {
        "rapports": [{"cle": k, **{c: v for c, v in r.items() if c != "fonction"}} for k, r in RAPPORTS.items()],
        "magasins": [{"id": m.id, "nom": m.nom} for m in Magasin.objects.filter(Q(actif=True) | Q(entrees__isnull=False)).distinct()],
        "categories": [{"id": c.id, "nom": c.nom} for c in Categorie.objects.all()],
        "periodes": [{"valeur": v, "libelle": l} for v, l in PERIODES],
        "horizons": [{"valeur": v, "libelle": l} for v, l in HORIZONS],
    }
