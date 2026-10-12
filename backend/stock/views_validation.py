"""Écran « Demandes à valider » de l'Agent Logistique (11/10/2026).

L'Agent Logistique voit toutes les demandes, modifie au besoin les quantités, puis :
  - valide  → la demande passe « Validée », la réquisition matière (RM-AAAA-0001) est créée en un clic ;
              cette validation vaut visa électronique de l'Agent Logistique ; elle attend ensuite le visa du Responsable HBC ;
  - refuse  → motif obligatoire, visible par le demandeur.
La quantité demandée d'origine est conservée (LigneDemande.quantite) ; la quantité retenue va dans qte_accordee.
Le stock ne change pas ici (il baissera à la confirmation de sortie).
"""
from django.conf import settings
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Demande, Requisition
from .notifications import email_actif, prevenir_responsable
from .signatures import lire_signature
from .permissions import EstAgentLogistique
from .views import ONGLETS, PAR_PAGE_DEMANDES, demandes_completes, en_json

MOTIF_MAX = 250


def _introuvable():
    return Response({"general": ["Demande introuvable."]}, status=status.HTTP_404_NOT_FOUND)


def _deja_traitee(d):
    return Response({"general": [f"Cette demande est déjà {d.get_statut_display().lower()} : "
                                 "seule une demande en attente peut être validée ou refusée."]},
                    status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def liste(request):
    """Toutes les demandes, par onglet (?onglet=attente|validees|refusees|toutes, ?page=).
    En attente : les urgentes d'abord, puis les plus anciennes (à traiter en premier)."""
    qs = demandes_completes()
    compteurs = {cle: (qs.filter(f).count() if f is not None else qs.count()) for cle, f in ONGLETS.items()}
    onglet = request.query_params.get("onglet", "attente")
    filtre = ONGLETS.get(onglet, ONGLETS["attente"])
    if filtre is not None:
        qs = qs.filter(filtre)
    if onglet == "attente" or onglet not in ONGLETS:
        qs = qs.annotate(rang=Case(When(urgent=True, then=Value(0)), default=Value(1), output_field=IntegerField())) \
               .order_by("rang", "cree_le", "id")
    total = qs.count()
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    morceau = list(qs[(page - 1) * PAR_PAGE_DEMANDES: page * PAR_PAGE_DEMANDES])
    return Response({"count": total, "par_page": PAR_PAGE_DEMANDES, "compteurs": compteurs, "results": en_json(morceau)})


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def detail(request, pk):
    d = demandes_completes().filter(pk=pk).first()
    return _introuvable() if d is None else Response(en_json([d])[0])


@api_view(["POST"])
@permission_classes([EstAgentLogistique])
def valider(request, pk):
    """Valide la demande avec les quantités accordées et crée la réquisition matière.
    Corps : {"lignes": [{"id": <ligne>, "qte_accordee": <entier ≥ 0>}, …]} ; une ligne absente garde la quantité demandée."""
    saisies = request.data.get("lignes", [])
    if not isinstance(saisies, list):
        return Response({"general": ["Données incorrectes."]}, status=status.HTTP_400_BAD_REQUEST)
    # La validation vaut visa : l'Agent Logistique signe au stylo électronique (case « Agent Logistique » du bon).
    try:
        signature = lire_signature(request.data.get("signature"))
    except ValueError as exc:
        return Response({"signature": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        d = Demande.objects.select_for_update().filter(pk=pk).first()
        if d is None:
            return _introuvable()
        if d.statut != Demande.Statut.EN_ATTENTE:  # déjà traitée, ou annulée entre-temps par le demandeur
            return _deja_traitee(d)
        lignes = {l.id: l for l in d.lignes.select_related("article")}
        accordees = {i: l.quantite for i, l in lignes.items()}  # par défaut : ce qui a été demandé
        erreurs = {}
        for s in saisies:
            if not isinstance(s, dict) or s.get("id") not in lignes:
                return Response({"general": ["Un article de la demande est introuvable : rechargez la page."]},
                                status=status.HTTP_400_BAD_REQUEST)
            valeur = s.get("qte_accordee")
            if valeur in (None, ""):
                erreurs[str(s["id"])] = ["Indiquez la quantité accordée (0 pour retirer l'article)."]
                continue
            if isinstance(valeur, int) and not isinstance(valeur, bool):
                n = valeur
            elif isinstance(valeur, str) and valeur.strip().lstrip("-").isdigit():
                n = int(valeur.strip())
            else:
                erreurs[str(s["id"])] = ["Indiquez un nombre entier."]
                continue
            if n < 0:
                erreurs[str(s["id"])] = ["La quantité ne peut pas être négative."]
                continue
            accordees[s["id"]] = n
        if erreurs:
            return Response({"lignes": erreurs}, status=status.HTTP_400_BAD_REQUEST)
        if not any(accordees.values()):
            return Response({"general": ["Toutes les quantités sont à 0 : accordez au moins un article, "
                                         "ou refusez la demande."]}, status=status.HTTP_400_BAD_REQUEST)

        maintenant = timezone.now()
        for i, l in lignes.items():
            l.qte_accordee = accordees[i]
            l.save(update_fields=["qte_accordee"])
        d.statut = Demande.Statut.VALIDEE
        d.traitee_le = maintenant
        d.traitee_par = request.user
        d.save(update_fields=["statut", "traitee_le", "traitee_par"])
        # Le n° attribué au clic sur « Valider » (celui imprimé sur le bon signé) devient le n° de la réquisition.
        numero = d.numero_requisition or _attribuer(d)
        r = Requisition.objects.create(demande=d, numero=numero, visa_agent=request.user, visa_agent_le=maintenant,
                                       signature_agent=signature)

    # Email au Responsable (désactivé pour l'instant : GESTISTOCK_EMAILS). Après l'enregistrement :
    # un souci d'email n'annule pas la validation.
    etat_email = prevenir_responsable(r) if settings.GESTISTOCK_EMAILS else None
    d = demandes_completes().get(pk=d.pk)
    return Response({"message": f"Demande {d.numero} validée. Réquisition {r.numero} créée : "
                                "elle attend maintenant le visa du Responsable HBC (menu « À viser »).",
                     "email": etat_email,
                     "email_ok": not settings.GESTISTOCK_EMAILS or (bool(d.requisition.email_envoye_le) and email_actif()),
                     "demande": en_json([d])[0]})


@api_view(["POST"])
@permission_classes([EstAgentLogistique])
def renvoyer_email(request, pk):
    """« Renvoyer l'email » au Responsable HBC (réquisition encore en attente du visa)."""
    d = demandes_completes().filter(pk=pk).first()
    r = getattr(d, "requisition", None) if d else None
    if r is None:
        return _introuvable()
    if not settings.GESTISTOCK_EMAILS:
        return Response({"general": ["Les emails sont désactivés pour l'instant."]}, status=status.HTTP_400_BAD_REQUEST)
    if r.statut != Requisition.Statut.ATTENTE_VISA:
        return Response({"general": ["Cette réquisition n'attend plus le visa : inutile de renvoyer l'email."]},
                        status=status.HTTP_400_BAD_REQUEST)
    etat = prevenir_responsable(r)
    d = demandes_completes().get(pk=d.pk)
    return Response({"message": etat, "email_ok": bool(r.email_envoye_le) and email_actif(), "demande": en_json([d])[0]})


@api_view(["POST"])
@permission_classes([EstAgentLogistique])
def refuser(request, pk):
    """Refuse la demande. Corps : {"motif": "…"} (obligatoire, 250 caractères au plus, montré au demandeur)."""
    motif = str(request.data.get("motif") or "").strip()
    if not motif:
        return Response({"motif": ["Indiquez le motif du refus : il sera montré au demandeur."]},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(motif) > MOTIF_MAX:
        return Response({"motif": [f"{MOTIF_MAX} caractères au maximum."]}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        d = Demande.objects.select_for_update().filter(pk=pk).first()
        if d is None:
            return _introuvable()
        if d.statut != Demande.Statut.EN_ATTENTE:
            return _deja_traitee(d)
        d.statut = Demande.Statut.REFUSEE
        d.motif_refus = motif
        d.traitee_le = timezone.now()
        d.traitee_par = request.user
        d.numero_requisition = ""  # n° éventuellement attribué : libéré
        d.save(update_fields=["statut", "motif_refus", "traitee_le", "traitee_par", "numero_requisition"])
    d = demandes_completes().get(pk=d.pk)
    return Response({"message": f"Demande {d.numero} refusée. Le demandeur verra le motif dans « Mes demandes ».",
                     "demande": en_json([d])[0]})


def _attribuer(d):
    """Attribue le prochain n° de réquisition à la demande `d` (verrouillée par l'appelant)."""
    from django.db import IntegrityError
    for _ in range(3):
        try:
            with transaction.atomic():
                d.numero_requisition = Requisition._prochain_numero()
                d.save(update_fields=["numero_requisition"])
            return d.numero_requisition
        except IntegrityError:  # deux validations au même instant : on reprend le suivant
            d.numero_requisition = ""
    raise RuntimeError("Impossible d'attribuer un n° de réquisition.")


@api_view(["POST"])
@permission_classes([EstAgentLogistique])
def attribuer_numero(request, pk):
    """Clic sur « Valider » (12/10/2026) : le n° de réquisition est attribué tout de suite et s'affiche sur le bon
    à signer. Le même n° est gardé si la fenêtre est fermée puis rouverte."""
    with transaction.atomic():
        d = Demande.objects.select_for_update().filter(pk=pk).first()
        if d is None:
            return _introuvable()
        if d.statut != Demande.Statut.EN_ATTENTE:
            return _deja_traitee(d)
        numero = d.numero_requisition or _attribuer(d)
    return Response({"numero": numero})
