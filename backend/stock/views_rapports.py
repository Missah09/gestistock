"""Écrans « Générer Rapports » et « Historique » (Responsable Technique, 15/10/2026).

- GET /api/rapports/                      : les six rapports (cartes de l'écran) et les listes des filtres
- GET /api/rapports/<rapport>/            : le rapport à l'écran ; ?fichier=pdf ou ?fichier=xlsx : le fichier
- GET /api/historique/                    : l'historique filtré, 50 lignes par page (?page=)
- GET /api/historique/export/?fichier=…    : tout l'historique filtré, en PDF ou Excel
Filtres : ?magasin=, ?categorie=, ?periode=jour|semaine|mois|mois_dernier|annee|tout|choisie (&du=&au=),
?regrouper=chantier|service, ?horizon=30|90|180|365|tout ; historique : ?type=, ?utilisateur=, ?q=.
"""
from decimal import Decimal

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import historique as hist
from .exports import reponse_fichier
from .permissions import EstAgentLogistique
from .rapports import PERIODES, RAPPORTS, catalogue, construire

PAR_PAGE = 50
MAX_EXPORT = 10_000
GARDER = ("_ton_", "_detail_", "_unite", "_fond", "_id")


def _propre(valeur):
    if isinstance(valeur, Decimal):
        return str(valeur.quantize(Decimal("1")) if valeur == valeur.to_integral_value() else valeur)
    return valeur


def _ligne_json(ligne):
    """Les clés internes (« _… ») ne partent pas à l'écran, sauf la mise en forme (couleur, détail, unité)."""
    if not ligne:
        return ligne
    return {k: _propre(v) for k, v in ligne.items() if not k.startswith("_") or k.startswith(GARDER)}


def rapport_json(r):
    return {**{k: v for k, v in r.items() if k not in ("sections", "total")},
            "total": _ligne_json(r.get("total")),
            "sections": [{"titre": s.get("titre"), "vide": s.get("vide"), "total": _ligne_json(s.get("total")),
                          "lignes": [_ligne_json(l) for l in s["lignes"]]} for s in r["sections"]]}


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def liste(request):
    return Response(catalogue())


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def rapport(request, cle):
    if cle not in RAPPORTS:
        return Response({"general": ["Rapport inconnu."]}, status=status.HTTP_404_NOT_FOUND)
    r = construire(cle, request.query_params)
    format_ = request.query_params.get("fichier")
    if format_:
        return reponse_fichier(r, format_, request.user)
    return Response(rapport_json(r))


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def historique(request):
    lignes, du, au, libelle = hist.historique(request.query_params)
    try:
        page = max(1, int(request.query_params.get("page") or 1))
    except ValueError:
        page = 1
    pages = max(1, -(-len(lignes) // PAR_PAGE))
    page = min(page, pages)
    morceau = lignes[(page - 1) * PAR_PAGE: page * PAR_PAGE]
    return Response({
        "lignes": [{**_ligne_json(l), "article_id": l["_article_id"]} for l in morceau],
        "count": len(lignes), "page": page, "pages": pages, "par_page": PAR_PAGE,
        "periode": {"du": du.isoformat() if du else None, "au": au.isoformat() if au else None, "libelle": libelle},
        "types": [{"valeur": k, "libelle": l, "ton": t} for k, l, t in hist.TYPES],
        "periodes": [{"valeur": v, "libelle": l} for v, l in PERIODES],
        "utilisateurs": hist.utilisateurs(),
    })


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def historique_export(request):
    r = hist.rapport(request.query_params)
    lignes = r["sections"][0]["lignes"]
    if len(lignes) > MAX_EXPORT:
        return Response({"general": [f"{len(lignes)} lignes : c'est trop pour un fichier. Choisissez une période plus "
                                     f"courte (au plus {MAX_EXPORT} lignes)."]}, status=status.HTTP_400_BAD_REQUEST)
    return reponse_fichier(r, request.query_params.get("fichier"), request.user)
