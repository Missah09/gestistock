"""Écran « Historique » (Agent Logistique, 15/10/2026) : tous les mouvements, avec le stock avant et après.

D'après la maquette (écran 11). Personne ne peut modifier l'historique : il est fabriqué à partir de ce que
GestiStock a enregistré.

Deux sortes de lignes :
- **les mouvements du stock** (MouvementEtat) : entrées en stock, sorties confirmées, retours confirmés et corrections
  (administration, import du fichier de stock). Quantité signée (+ / −) et stock disponible « avant → après ».
- **les étapes du circuit** (sans effet sur le stock) : demande envoyée, validation ou refus de la Logistique,
  signature ou refus du Responsable HBC, impression du bon.

Stock avant → après : on part du stock disponible actuel de chaque article et on remonte le temps, mouvement par
mouvement (`variation`). Les lignes d'un même passage (une sortie en plusieurs états, plusieurs n° de série reçus
ensemble) sont regroupées en une seule ligne.
"""
import datetime

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from . import etats
from .exports import quantite as quantite_texte
from .models import Demande, MouvementEtat, Requisition
from .rapports import periode_de
from .serializers import heure_locale, nom_de
from .views import articles_avec_quantites, sans_accents

# Types affichés (filtre « Type ») : clé, libellé, couleur de la pastille.
TYPES = [
    ("entree", "Entrée", "vert"), ("sortie", "Sortie", "orange"), ("retour", "Retour", "bleu"),
    ("correction", "Correction", "gris"), ("demande", "Demande", "gris"), ("validation", "Validation", "violet"),
    ("visa", "Signature", "violet"), ("refus", "Refus", "rouge"), ("impression", "Bon imprimé", "gris"),
]
LIBELLE = {k: l for k, l, _ in TYPES}
TON = {k: t for k, _, t in TYPES}
TYPE_MOUVEMENT = {"RECEPTION": "entree", "SORTIE": "sortie", "RETOUR": "retour", "CORRECTION": "correction",
                  "REPARATION": "correction", "REBUT": "correction"}
REGROUPEMENT = datetime.timedelta(seconds=10)  # mouvements d'un même passage (même article, même bon, même personne)


def stocks_avant_apres():
    """{id du mouvement: (stock avant, stock après)} : on remonte le temps depuis le stock disponible actuel."""
    courant = dict(articles_avec_quantites().values_list("id", "qte_disponible"))
    resultat = {}
    for mid, aid, variation in MouvementEtat.objects.order_by("-le", "-id").values_list("id", "article_id", "variation"):
        apres = courant.get(aid, 0)
        avant = apres - (variation or 0)
        resultat[mid] = (avant, apres)
        courant[aid] = avant
    return resultat


def _articles_texte(lignes):
    noms = [l.article.nom for l in lignes]
    if len(noms) <= 2:
        return " · ".join(noms)
    return f"{noms[0]} · {noms[1]} et {len(noms) - 2} autre{'s' if len(noms) > 3 else ''}"


def _dans(champ, du, au):
    f = {}
    if du:
        f[f"{champ}__date__gte"] = du
    if au:
        f[f"{champ}__date__lte"] = au
    return f


def mouvements(du, au):
    """Lignes des mouvements du stock (regroupées par passage)."""
    stocks = stocks_avant_apres()
    qs = (MouvementEtat.objects.filter(**_dans("le", du, au)).select_related("article", "exemplaire", "par")
          .order_by("-le", "-id"))
    lignes = []
    for m in qs:
        avant, apres = stocks.get(m.id, (None, None))
        type_ = TYPE_MOUVEMENT.get(m.type, "correction")
        etat = m.etat_avant if m.type == "SORTIE" else (m.etat_apres or m.etat_avant)
        precedent = lignes[-1] if lignes else None
        if (precedent and precedent["_article_id"] == m.article_id and precedent["_type_m"] == m.type
                and precedent["reference"] == m.reference and precedent["_par_id"] == m.par_id
                and precedent["_motif"] == m.motif and precedent["_dernier"] - m.le <= REGROUPEMENT):
            precedent["_variation"] += m.variation or 0
            precedent["_avant"] = avant
            precedent["_dernier"] = m.le
            if etat:
                precedent["_etats"][etat] = precedent["_etats"].get(etat, 0) + m.quantite
            if m.exemplaire_id:
                precedent["_series"].append(m.exemplaire.numero_serie)
            continue
        lignes.append({
            "_le": m.le, "_dernier": m.le, "type": type_, "_type_m": m.type, "_article_id": m.article_id,
            "article": m.article.nom, "code": m.article.code, "_unite": m.article.unite,
            "_variation": m.variation or 0, "_avant": avant, "_apres": apres,
            "_etats": {etat: m.quantite} if etat else {},
            "_series": [m.exemplaire.numero_serie] if m.exemplaire_id else [],
            "reference": m.reference, "_motif": m.motif, "_par_id": m.par_id, "par": nom_de(m.par) if m.par else "",
        })
    for l in lignes:
        v, unite = l.pop("_variation"), l["_unite"]
        l["quantite"] = ("+" if v > 0 else "−" if v < 0 else "") + quantite_texte(abs(v), unite)
        l["_ton_quantite"] = "vert" if v > 0 else "rouge" if v < 0 else None
        l["_n"] = v
        avant, apres = l.pop("_avant"), l.pop("_apres")
        l["stock"] = (f"{quantite_texte(avant, unite)} → {quantite_texte(apres, unite)}"
                      if avant is not None and apres is not None else "")
        detail = []
        if l["_etats"]:
            detail.append(" · ".join(f"{quantite_texte(n, unite)} {etats.LIBELLES[e]}"
                                     for e, n in sorted(l["_etats"].items(), key=lambda x: etats.ORDRE.index(x[0]))
                                     if n and e in etats.LIBELLES))
        if l["_series"]:
            detail.append("N° " + ", ".join(sorted(l["_series"])))
        if l["_motif"]:
            detail.append(l["_motif"])
        l["detail"] = " · ".join(detail)
        if l["_type_m"] in ("REPARATION", "REBUT"):
            l["detail"] = " · ".join(filter(None, [dict(MouvementEtat.Type.choices)[l["_type_m"]], l["detail"]]))
    return lignes


def _origine(origine):
    """« (signature importée) » / « (signature dessinée) » ; rien pour les visas d'avant la signature électronique."""
    return {"DESSINEE": " (signature dessinée)", "IMPORTEE": " (signature importée)"}.get(origine or "", "")


def evenements_du_circuit(du, au):
    """Lignes des étapes du circuit des demandes (sans effet sur le stock)."""
    lignes = []

    def ajouter(le, type_, demande, par, reference, detail=""):
        lignes.append({"_le": le, "type": type_, "article": _articles_texte(list(demande.lignes.all())), "code": "",
                       "_article_id": None, "_unite": None, "quantite": "", "stock": "", "_n": 0,
                       "reference": reference, "detail": detail, "_par_id": par.id if par else None,
                       "par": nom_de(par) if par else ""})

    base = Demande.objects.select_related("demandeur", "traitee_par", "chantier").prefetch_related("lignes__article")
    for d in base.filter(**_dans("cree_le", du, au)):
        ajouter(d.cree_le, "demande", d, d.demandeur, d.numero,
                " · ".join(filter(None, ["Urgente" if d.urgent else "", d.destination])))
    for d in base.select_related("requisition").filter(traitee_le__isnull=False, **_dans("traitee_le", du, au)):
        r = getattr(d, "requisition", None)
        if d.statut == Demande.Statut.REFUSEE and r is None:
            ajouter(d.traitee_le, "refus", d, d.traitee_par, d.numero, f"Refusée par la Logistique : {d.motif_refus}")
        elif r is not None:
            ajouter(d.traitee_le, "validation", d, d.traitee_par, r.numero, f"Demande {d.numero} validée et signée{_origine(r.origine_signature_agent)}")
    reqs = Requisition.objects.select_related("demande", "visa_responsable", "imprimee_par").prefetch_related(
        "demande__lignes__article")
    for r in reqs.filter(visa_responsable_le__isnull=False, **_dans("visa_responsable_le", du, au)):
        if r.statut == Requisition.Statut.REFUSEE:
            ajouter(r.visa_responsable_le, "refus", r.demande, r.visa_responsable, r.numero,
                    f"Refusé par le Responsable : {r.motif_refus}")
        else:
            ajouter(r.visa_responsable_le, "visa", r.demande, r.visa_responsable, r.numero,
                    f"Demande {r.demande.numero} signée par le Responsable HBC{_origine(r.origine_signature_responsable)}")
    for r in reqs.filter(imprimee_le__isnull=False, **_dans("imprimee_le", du, au)):
        ajouter(r.imprimee_le, "impression", r.demande, r.imprimee_par, r.numero,
                f"Demande {r.demande.numero} : bon imprimé pour le magasin")
    return lignes


def historique(params):
    """Toutes les lignes correspondant aux filtres, les plus récentes d'abord, + la description de la période."""
    du, au, libelle = periode_de(params, defaut="semaine")
    type_ = params.get("type") or ""
    lignes = []
    if type_ in ("", "entree", "sortie", "retour", "correction"):
        lignes += mouvements(du, au)
    if type_ in ("", "demande", "validation", "visa", "refus", "impression"):
        lignes += evenements_du_circuit(du, au)
    if type_:
        lignes = [l for l in lignes if l["type"] == type_]
    try:
        par = int(params.get("utilisateur") or 0)
    except ValueError:
        par = 0
    if par:
        lignes = [l for l in lignes if l["_par_id"] == par]
    q = sans_accents(params.get("q") or "").strip()
    if q:
        mots = q.split()
        lignes = [l for l in lignes if all(m in sans_accents(" ".join(
            [l["article"], l["code"], l["reference"], l["detail"], l["par"]])) for m in mots)]
    lignes.sort(key=lambda l: l["_le"], reverse=True)
    for l in lignes:
        l["le"] = heure_locale(l["_le"])
        l["type_libelle"] = LIBELLE[l["type"]]
        l["_ton_type_libelle"] = TON[l["type"]]
    return lignes, du, au, libelle


def utilisateurs():
    """Comptes proposés dans le filtre « Utilisateur » (ceux qui ont déjà agi dans GestiStock, et les comptes actifs)."""
    ids = set(MouvementEtat.objects.exclude(par=None).values_list("par_id", flat=True))
    ids |= set(Demande.objects.exclude(demandeur=None).values_list("demandeur_id", flat=True))
    ids |= set(Demande.objects.exclude(traitee_par=None).values_list("traitee_par_id", flat=True))
    ids |= set(Requisition.objects.exclude(visa_responsable=None).values_list("visa_responsable_id", flat=True))
    comptes = User.objects.filter(Q(id__in=ids) | Q(is_active=True)).order_by("first_name", "last_name", "username")
    return [{"id": u.id, "nom": nom_de(u)} for u in comptes]


COLONNES = [
    {"cle": "le", "titre": "Date", "type": "dateheure", "largeur": 15},
    {"cle": "type_libelle", "titre": "Type", "type": "pill", "largeur": 12},
    {"cle": "article", "titre": "Article", "largeur": 40},
    {"cle": "quantite", "titre": "Quantité", "largeur": 13},
    {"cle": "stock", "titre": "Stock avant → après", "largeur": 20},
    {"cle": "reference", "titre": "Référence", "largeur": 22},
    {"cle": "par", "titre": "Par", "largeur": 18},
]


def rapport(params):
    """L'historique filtré, sous la forme commune des exports (PDF, Excel)."""
    lignes, du, au, libelle = historique(params)
    filtres = [f"Période : {libelle}"]
    if params.get("type") in LIBELLE:
        filtres.append(f"Type : {LIBELLE[params['type']]}")
    if params.get("utilisateur"):
        u = User.objects.filter(pk=params.get("utilisateur")).first() if str(params.get("utilisateur")).isdigit() else None
        if u:
            filtres.append(f"Utilisateur : {nom_de(u)}")
    if (params.get("q") or "").strip():
        filtres.append(f"Recherche : « {params['q'].strip()} »")
    for l in lignes:
        l["_detail_article"] = l["detail"]
    entrees = sum(1 for l in lignes if l["type"] == "entree")
    sorties = sum(1 for l in lignes if l["type"] == "sortie")
    return {
        "titre": "Historique des mouvements",
        "sous_titre": " · ".join(filtres),
        "colonnes": COLONNES,
        "sections": [{"titre": None, "lignes": lignes, "vide": "Aucun mouvement pour ces filtres."}],
        "resume": [["Lignes", str(len(lignes))], ["Entrées", str(entrees)], ["Sorties", str(sorties)]],
        "notes": ["Stock avant → après : quantité disponible au magasin de l'article. Les étapes du circuit "
                  "(demande, validation, signature, impression) ne changent pas le stock."],
    }
