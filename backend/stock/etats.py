"""État du produit : Neuf · Bon · Moyen · Mauvais (simplifié le 12/10/2026 ; tous les états sont disponibles).

Deux façons de suivre un article :
- **par n° de série** (matériel prêté avec exemplaires) : chaque exemplaire porte son état ;
- **par quantité** (consommables, matériel prêté sans n° de série) : le stock est réparti par état (StockEtat).
  `Article.qte_stock` est la quantité disponible (somme des états), celle que tout le reste de l'application utilise.

(Le mécanisme « mis de côté » — DE_COTE, emplacements dédiés — est resté en place mais ne sert plus : liste vide.)

Si la répartition et `qte_stock` ne concordent pas (stock corrigé dans l'administration, articles anciens),
l'écart est compté dans l'état par défaut (Neuf pour un consommable, Bon état pour du matériel prêté) :
voir `_concilier`. Les mouvements (`ajouter`, `retirer`) remettent d'abord la table en accord.
"""
from django.db import transaction
from django.db.models import F

from .models import (ETATS_DE_COTE, ETATS_UTILISABLES, Article, Emplacement, Etat, Exemplaire, MouvementEtat,
                     StockEtat)

ORDRE = [Etat.NEUF, Etat.BON, Etat.MOYEN, Etat.MAUVAIS]
LIBELLES = dict(Etat.choices)
UTILISABLES = [str(e) for e in ETATS_UTILISABLES]
DE_COTE = [str(e) for e in ETATS_DE_COTE]
# Statut d'un exemplaire selon son état (quand il est au magasin).
STATUT_SELON_ETAT = {}  # plus d'état « mis de côté » : un exemplaire au magasin est toujours « En stock »
EMPLACEMENT_DE_COTE = {}
# Anciens emplacements « Atelier – À réparer » et « Rebut » : jamais proposés (s'ils existent encore).
NOMS_EMPLACEMENTS_DE_COTE = {"Atelier – À réparer", "Rebut"}


def etat_valide(valeur):
    return valeur in LIBELLES


def etat_par_defaut(article):
    return Etat.NEUF if article.type == Article.Type.CONSOMMABLE else Etat.BON


def suivi_par_serie(article, a_des_exemplaires=None):
    if article.type != Article.Type.PRETE:
        return False
    if article.suivi_serie:  # choisi à la création (12/10/2026), même sans exemplaire encore reçu
        return True
    if a_des_exemplaires is None:
        a_des_exemplaires = article.exemplaires.exists()
    return bool(a_des_exemplaires)


def statut_pour(etat):
    return STATUT_SELON_ETAT.get(etat, Exemplaire.Statut.EN_STOCK)


def texte(etats, unite=None):
    """{"NEUF": 3, "BON": 2} → « 3 Neuf · 2 Bon état » (ordre fixe, zéros omis)."""
    morceaux = [f"{etats[e]} {LIBELLES[e]}" for e in ORDRE if (etats or {}).get(e)]
    return " · ".join(morceaux)


def _concilier(qte_stock, par_etat, defaut):
    """Répartition dont la partie disponible est égale à qte_stock (voir l'en-tête du module)."""
    r = {e: max(0, int(par_etat.get(e, 0))) for e in ORDRE}
    ecart = qte_stock - sum(r[e] for e in UTILISABLES)
    if ecart > 0:
        r[defaut] += ecart
    elif ecart < 0:
        for e in (Etat.MAUVAIS, Etat.MOYEN, Etat.BON, Etat.NEUF):
            retire = min(r[e], -ecart)
            r[e] -= retire
            ecart += retire
            if not ecart:
                break
    return r


def repartitions(articles):
    """{id: {"etats": {état: qté au magasin}, "pretes": n, "par_serie": bool}} pour une liste d'articles.
    Au magasin : disponibles + mis de côté (les exemplaires prêtés et mis au rebut ne sont pas comptés)."""
    articles = list(articles)
    ids = [a.id for a in articles]
    tables = {}
    for s in StockEtat.objects.filter(article_id__in=ids):
        tables.setdefault(s.article_id, {})[s.etat] = s.quantite
    ex = {}
    for article_id, etat, statut in Exemplaire.objects.filter(article_id__in=ids).values_list("article_id", "etat", "statut"):
        ex.setdefault(article_id, []).append((etat, statut))
    resultat = {}
    for a in articles:
        if a.type == Article.Type.PRETE and a.id in ex:
            # Un exemplaire « En stock » compte dans son état.
            etats = {e: 0 for e in ORDRE}
            for e, st in ex[a.id]:
                if st == Exemplaire.Statut.EN_STOCK:
                    etats[e if e in UTILISABLES else Etat.BON] += 1
            resultat[a.id] = {"etats": etats, "pretes": sum(1 for _, st in ex[a.id] if st == Exemplaire.Statut.PRETE),
                              "par_serie": True}
        else:
            resultat[a.id] = {"etats": _concilier(a.qte_stock, tables.get(a.id, {}), etat_par_defaut(a)),
                              "pretes": None, "par_serie": False}
    return resultat


def repartition(article):
    return repartitions([article])[article.id]


def en_json(rep):
    """Pour l'écran : {"NEUF": 3, …} (les 5 états), disponible, de côté."""
    e = rep["etats"]
    return {"etats": {k: e.get(k, 0) for k in ORDRE},
            "disponible": sum(e.get(k, 0) for k in UTILISABLES),
            "de_cote": sum(e.get(k, 0) for k in DE_COTE),
            "pretes": rep["pretes"], "par_serie": rep["par_serie"]}


# ---------------------------------------------------------------- Mouvements (article suivi par quantité)
def _materialiser(article):
    """Met StockEtat en accord avec qte_stock (article verrouillé par l'appelant, valeurs à jour)."""
    article.refresh_from_db(fields=["qte_stock"])
    lignes = {s.etat: s for s in StockEtat.objects.select_for_update().filter(article=article)}
    voulu = _concilier(article.qte_stock, {e: s.quantite for e, s in lignes.items()}, etat_par_defaut(article))
    for e in ORDRE:
        actuel = lignes[e].quantite if e in lignes else 0
        if voulu[e] != actuel:
            StockEtat.objects.update_or_create(article=article, etat=e, defaults={"quantite": voulu[e]})
    return voulu


@transaction.atomic
def disponibles_par_etat(article):
    """Quantités au magasin par état (article suivi par quantité), après mise en accord."""
    return _materialiser(article)


@transaction.atomic
def ajouter(article, etat, qte):
    """Entrée en stock (réception, retour, réparation) de `qte` dans l'état `etat`."""
    if qte <= 0:
        return
    _materialiser(article)
    s, _ = StockEtat.objects.get_or_create(article=article, etat=etat)
    StockEtat.objects.filter(pk=s.pk).update(quantite=F("quantite") + qte)
    if etat in UTILISABLES:
        Article.objects.filter(pk=article.pk).update(qte_stock=F("qte_stock") + qte)


@transaction.atomic
def retirer(article, etat, qte):
    """Sortie du stock (sortie, réparation, rebut). ValueError si l'état n'a pas assez de quantité."""
    if qte <= 0:
        return
    voulu = _materialiser(article)
    if voulu[etat] < qte:
        raise ValueError(f"{voulu[etat]} seulement en « {LIBELLES[etat]} »")
    StockEtat.objects.filter(article=article, etat=etat).update(quantite=F("quantite") - qte)
    if etat in UTILISABLES:
        Article.objects.filter(pk=article.pk).update(qte_stock=F("qte_stock") - qte)


# Sens de chaque mouvement sur le stock disponible (15/10/2026, écran « Historique »).
SENS = {"RECEPTION": 1, "RETOUR": 1, "REPARATION": 1, "CORRECTION": 1, "SORTIE": -1, "REBUT": 0}


def noter(article, type_, quantite, etat_avant="", etat_apres="", reference="", motif="", par=None, exemplaire=None,
          variation=None):
    """Historique : chaque mouvement (et changement d'état) est conservé, avec sa variation du stock disponible.
    `variation` : à donner pour une correction en moins (sinon déduite du type : +quantité, ou −quantité pour une sortie)."""
    if quantite <= 0:
        return None
    if variation is None:
        variation = SENS.get(str(type_), 1) * quantite
    return MouvementEtat.objects.create(article=article, exemplaire=exemplaire, type=type_, quantite=quantite,
                                        variation=variation,
                                        etat_avant=etat_avant or "", etat_apres=etat_apres or "",
                                        reference=reference[:60], motif=motif[:250],
                                        par=par if par and par.is_authenticated else None)


def emplacement_de_cote(magasin, etat):
    """« Atelier – À réparer » ou « Rebut » du magasin (créé au besoin)."""
    nom = EMPLACEMENT_DE_COTE.get(etat)
    if not nom:
        return None
    return Emplacement.objects.get_or_create(magasin=magasin, nom=nom)[0]
