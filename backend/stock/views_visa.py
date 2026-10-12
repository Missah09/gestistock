"""Écran « À viser » du Responsable HBC (11/10/2026).

Le Responsable reçoit un email avec un lien, se connecte, puis vise la réquisition matière
(son visa électronique sera imprimé sur le bon) ou la refuse avec un motif.
Après le visa, l'Agent Logistique pourra télécharger le bon en PDF (étape suivante).
"""
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Requisition
from .permissions import EstResponsable
from .signatures import image, lire_signature
from .views import PAR_PAGE_DEMANDES, demandes_completes, en_json

MOTIF_MAX = 250
ONGLETS_VISA = {"attente": Q(requisition__statut=Requisition.Statut.ATTENTE_VISA),
                "visees": Q(requisition__statut=Requisition.Statut.VISEE),
                "refusees": Q(requisition__statut=Requisition.Statut.REFUSEE),
                "toutes": Q(requisition__isnull=False)}


def _introuvable():
    return Response({"general": ["Réquisition introuvable."]}, status=status.HTTP_404_NOT_FOUND)


def _a_viser():
    """Demandes validées par la Logistique (elles ont une réquisition)."""
    return demandes_completes().filter(requisition__isnull=False)


@api_view(["GET"])
@permission_classes([EstResponsable])
def liste(request):
    """Réquisitions par onglet (?onglet=attente|visees|refusees|toutes, ?page=).
    À viser : les urgentes d'abord, puis les plus anciennes."""
    qs = _a_viser()
    compteurs = {cle: qs.filter(f).count() for cle, f in ONGLETS_VISA.items()}
    onglet = request.query_params.get("onglet", "attente")
    if onglet not in ONGLETS_VISA:
        onglet = "attente"
    qs = qs.filter(ONGLETS_VISA[onglet])
    if onglet == "attente":
        qs = qs.annotate(rang=Case(When(urgent=True, then=Value(0)), default=Value(1), output_field=IntegerField())) \
               .order_by("rang", "requisition__visa_agent_le", "id")
    else:
        qs = qs.order_by("-requisition__visa_agent_le", "-id")
    total = qs.count()
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    morceau = list(qs[(page - 1) * PAR_PAGE_DEMANDES: page * PAR_PAGE_DEMANDES])
    return Response({"count": total, "par_page": PAR_PAGE_DEMANDES, "compteurs": compteurs, "results": en_json(morceau)})


@api_view(["GET"])
@permission_classes([EstResponsable])
def detail(request, pk):
    """Une demande validée et sa réquisition (pk = id de la demande, comme dans le lien de l'email)."""
    d = _a_viser().filter(pk=pk).first()
    return _introuvable() if d is None else Response(en_json([d])[0])


def _verrouiller(pk):
    """La réquisition de la demande pk, verrouillée ; ou une réponse d'erreur."""
    r = Requisition.objects.select_for_update().filter(demande_id=pk).first()
    if r is None:
        return None, _introuvable()
    if r.statut != Requisition.Statut.ATTENTE_VISA:
        return None, Response({"general": [f"Cette réquisition est déjà {r.get_statut_display().lower()}."]},
                              status=status.HTTP_400_BAD_REQUEST)
    return r, None


@api_view(["POST"])
@permission_classes([EstResponsable])
def viser(request, pk):
    """Vise la réquisition : signature dessinée au stylo électronique + nom (du compte) + date et heure."""
    try:
        signature = lire_signature(request.data.get("signature"))
    except ValueError as exc:
        return Response({"signature": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        r, erreur = _verrouiller(pk)
        if erreur:
            return erreur
        r.statut = Requisition.Statut.VISEE
        r.visa_responsable = request.user
        r.visa_responsable_le = timezone.now()
        r.signature_responsable = signature
        r.save(update_fields=["statut", "visa_responsable", "visa_responsable_le", "signature_responsable"])
    d = _a_viser().get(pk=pk)
    return Response({"message": f"Réquisition {r.numero} signée et visée. L'Agent Logistique peut maintenant imprimer le bon.",
                     "demande": en_json([d])[0]})


@api_view(["POST"])
@permission_classes([EstResponsable])
def refuser(request, pk):
    """Refuse la réquisition. Corps : {"motif": "…"} (obligatoire, montré à l'Agent Logistique et au demandeur)."""
    motif = str(request.data.get("motif") or "").strip()
    if not motif:
        return Response({"motif": ["Indiquez le motif du refus : il sera montré à la Logistique et au demandeur."]},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(motif) > MOTIF_MAX:
        return Response({"motif": [f"{MOTIF_MAX} caractères au maximum."]}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        r, erreur = _verrouiller(pk)
        if erreur:
            return erreur
        r.statut = Requisition.Statut.REFUSEE
        r.motif_refus = motif
        r.visa_responsable = request.user  # qui a refusé
        r.visa_responsable_le = timezone.now()
        r.save(update_fields=["statut", "motif_refus", "visa_responsable", "visa_responsable_le"])
    d = _a_viser().get(pk=pk)
    return Response({"message": f"Réquisition {r.numero} refusée. Le motif est visible par la Logistique et le demandeur.",
                     "demande": en_json([d])[0]})


@api_view(["GET"])
def signature(request, pk, qui):
    """Image d'une signature (qui = agent | responsable) pour l'aperçu du bon. pk = id de la demande.
    Visible par l'Agent Logistique, le Responsable HBC et le demandeur."""
    from django.http import HttpResponse
    from .models import ROLE_AGENT, ROLE_RESPONSABLE, roles_de
    r = Requisition.objects.select_related("demande").filter(demande_id=pk).first()
    roles = roles_de(request.user)
    if r is None or not (ROLE_AGENT in roles or ROLE_RESPONSABLE in roles or r.demande.demandeur_id == request.user.id):
        return _introuvable()
    b64 = r.signature_agent if qui == "agent" else r.signature_responsable if qui == "responsable" else ""
    if not b64:
        return _introuvable()
    reponse = HttpResponse(image(b64), content_type="image/png")
    reponse["Cache-Control"] = "private, max-age=3600"
    return reponse
