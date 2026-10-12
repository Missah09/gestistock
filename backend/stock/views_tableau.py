"""Écran « Tableau de bord » (Agent Logistique et Responsable HBC, 12/10/2026).

Une seule lecture pour tout l'écran :
- les 4 cartes chiffrées (articles sous le seuil, demandes à valider ou bons à viser, retours en retard, valeur du stock) ;
- « À réapprovisionner » : les articles épuisés, critiques puis en stock bas (les plus urgents d'abord) ;
- « Activité du jour » : ce qui s'est passé aujourd'hui (entrées, demandes, validations, signatures, sorties, retours).
"""
from decimal import Decimal

from django.db.models import F, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import (ROLE_AGENT, ROLE_RESPONSABLE, Article, BonRetour, Demande, Entree, Requisition, Sortie,
                     etat_stock, roles_de)
from .permissions import EstAgentOuResponsable
from .serializers import heure_locale, nom_de
from .views import articles_avec_quantites

NB_A_REAPPROVISIONNER = 6   # lignes affichées (le lien « Voir tout » ouvre la liste complète)
NB_ACTIVITES = 12           # événements du jour affichés, les plus récents d'abord
ORDRE_URGENCE = {"EPUISE": 0, "CRITIQUE": 1, "BAS": 2}


def nombre(n):
    """6000 → « 6 000 » (espace fine insécable, comme à l'écran)."""
    return f"{n:,}".replace(",", " ")


def quantite(n, unite):
    if unite == Article.Unite.METRE:
        return f"{nombre(n)} m"
    if unite == Article.Unite.PAIRE:
        return f"{nombre(n)} paire{'s' if n > 1 else ''}"
    return nombre(n)


def initiale(user):
    """« Paul Randria » → « P. Randria » (comme sur la maquette)."""
    if not user:
        return ""
    if user.first_name and user.last_name:
        return f"{user.first_name[0]}. {user.last_name}"
    return nom_de(user)


def sous_le_seuil():
    """Même règle que le filtre « Sous le seuil » de la Liste d'Articles : sous le minimum, ou épuisé."""
    return articles_avec_quantites().filter(Q(qte_disponible__lt=F("qte_minimale")) | Q(qte_disponible__lte=0))


def valeur_du_stock():
    """Valeur de ce qui est au magasin : quantité disponible × prix unitaire (le matériel prêté dehors n'est pas compté)."""
    total = Decimal(0)
    for qte, prix in articles_avec_quantites().values_list("qte_disponible", "prix_unitaire"):
        total += Decimal(qte or 0) * (prix or 0)
    return total


def a_reapprovisionner():
    articles = list(sous_le_seuil())
    for a in articles:
        a.etat = etat_stock(a.qte_disponible, a.qte_minimale)
    # Les plus urgents d'abord ; à urgence égale, le stock le plus bas par rapport au minimum.
    articles.sort(key=lambda a: (ORDRE_URGENCE.get(a.etat, 3),
                                 a.qte_disponible / a.qte_minimale if a.qte_minimale else 0, a.nom.lower()))
    return len(articles), [{"id": a.id, "code": a.code, "nom": a.nom, "unite": a.unite, "qte_disponible": a.qte_disponible,
                            "qte_minimale": a.qte_minimale, "etat": a.etat} for a in articles[:NB_A_REAPPROVISIONNER]]


def activite_du_jour():
    """Les événements d'aujourd'hui (heure de Madagascar), les plus récents d'abord."""
    aujourd_hui = timezone.localdate()
    ev = []

    def ajouter(quand, type_, texte):
        if quand:
            ev.append({"le": quand, "type": type_, "texte": texte})

    # Entrées en stock (livraisons)
    for e in Entree.objects.filter(cree_le__date=aujourd_hui).select_related("fournisseur").prefetch_related("lignes__article"):
        lignes = list(e.lignes.all())
        if len(lignes) == 1:
            l = lignes[0]
            texte = f"Entrée : {l.article.nom} ({quantite(l.quantite, l.article.unite)})"
        else:
            texte = f"Entrée : {len(lignes)} articles reçus" + (f" de {e.fournisseur.nom}" if e.fournisseur else "")
        ajouter(e.cree_le, "entree", texte)

    # Nouvelles demandes
    for d in Demande.objects.filter(cree_le__date=aujourd_hui).select_related("demandeur"):
        de = f" de {nom_de(d.demandeur)}" if d.demandeur else ""
        ajouter(d.cree_le, "demande", f"Nouvelle demande{' urgente' if d.urgent else ''} {d.numero}{de}")

    # Validations et refus de l'Agent Logistique
    for d in Demande.objects.filter(traitee_le__date=aujourd_hui).select_related("traitee_par"):
        par = f" par {initiale(d.traitee_par)}" if d.traitee_par else ""
        if d.statut == Demande.Statut.VALIDEE or hasattr(d, "requisition"):
            ajouter(d.traitee_le, "validation", f"Demande{' urgente' if d.urgent else ''} {d.numero} validée{par}")
        elif d.statut == Demande.Statut.REFUSEE:
            ajouter(d.traitee_le, "refus", f"Demande {d.numero} refusée{par}")

    # Signature (ou refus) du Responsable HBC
    for r in Requisition.objects.filter(visa_responsable_le__date=aujourd_hui).select_related("visa_responsable"):
        par = f" par {initiale(r.visa_responsable)}" if r.visa_responsable else ""
        if r.statut == Requisition.Statut.REFUSEE:
            ajouter(r.visa_responsable_le, "refus", f"Bon {r.numero} refusé{par}")
        else:
            ajouter(r.visa_responsable_le, "visa", f"Bon {r.numero} signé{par}")

    # Sorties confirmées (le stock a baissé)
    for s in Sortie.objects.filter(confirmee_le__date=aujourd_hui).select_related("requisition__demande__demandeur"):
        demandeur = s.requisition.demande.demandeur
        ajouter(s.confirmee_le, "sortie",
                f"Sortie : {s.requisition.numero}" + (f" remis à {nom_de(demandeur)}" if demandeur else ""))

    # Retours confirmés (le stock est remonté)
    for b in (BonRetour.objects.filter(statut=BonRetour.Statut.CONFIRME, confirme_le__date=aujourd_hui)
              .select_related("sortie__requisition__demande__demandeur")):
        qui = b.rendu_par or nom_de(b.sortie.requisition.demande.demandeur)
        ajouter(b.confirme_le, "retour", f"Retour : {b.numero}" + (f" rendu par {qui}" if qui else ""))

    ev.sort(key=lambda x: x["le"], reverse=True)
    return [{**x, "le": heure_locale(x["le"])} for x in ev[:NB_ACTIVITES]], len(ev)


@api_view(["GET"])
@permission_classes([EstAgentOuResponsable])
def tableau_de_bord(request):
    from .views_retours import compter_retards
    roles = roles_de(request.user)
    nb_sous_seuil, liste = a_reapprovisionner()
    activites, nb_activites = activite_du_jour()
    cartes = {"sous_seuil": nb_sous_seuil, "retours_en_retard": compter_retards(),
              "valeur_stock": str(valeur_du_stock().quantize(Decimal("1")))}
    if ROLE_AGENT in roles:
        cartes["a_valider"] = Demande.objects.filter(statut=Demande.Statut.EN_ATTENTE).count()
    if ROLE_RESPONSABLE in roles:
        cartes["a_viser"] = Requisition.objects.filter(statut=Requisition.Statut.ATTENTE_VISA).count()
    return Response({"maintenant": heure_locale(timezone.now()), "cartes": cartes, "a_reapprovisionner": liste,
                     "activite": activites, "nb_activites": nb_activites})
