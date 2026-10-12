"""Écran « Réquisitions » (12/10/2026) : les bons signés par l'Agent Logistique et le Responsable HBC.

- Visible par l'Agent Logistique et le Responsable HBC.
- « Télécharger le PDF » fabrique le bon (pdf_bon.py) et note chaque téléchargement (qui, quand).
- Le premier téléchargement par l'Agent Logistique marque le bon « imprimé » : c'est lui qui le porte au magasin.
  Un téléchargement du Responsable est une simple consultation.
"""
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import ROLE_AGENT, ROLE_RESPONSABLE, Requisition, TelechargementBon, a_le_role
from .permissions import EstAgentOuResponsable
from .views import PAR_PAGE_DEMANDES, demandes_completes, en_json

ONGLETS = {"a_imprimer": Q(requisition__imprimee_le__isnull=True),
           "imprimees": Q(requisition__imprimee_le__isnull=False),
           "toutes": Q()}


def _introuvable():
    return Response({"general": ["Réquisition introuvable."]}, status=status.HTTP_404_NOT_FOUND)


def _signees():
    """Demandes dont la réquisition est signée par l'Agent Logistique et le Responsable HBC."""
    return demandes_completes().select_related("requisition__imprimee_par") \
        .filter(requisition__statut=Requisition.Statut.VISEE) \
        .annotate(nb_telechargements=Count("requisition__telechargements"),
                  nb_impressions=Count("requisition__telechargements", filter=Q(requisition__telechargements__impression=True)))


@api_view(["GET"])
@permission_classes([EstAgentOuResponsable])
def liste(request):
    """Réquisitions signées par onglet (?onglet=a_imprimer|imprimees|toutes, ?page=).
    À imprimer : les urgentes d'abord, puis les plus anciennes ; sinon les plus récentes d'abord."""
    qs = _signees()
    compteurs = {cle: qs.filter(f).count() for cle, f in ONGLETS.items()}
    onglet = request.query_params.get("onglet", "a_imprimer")
    if onglet not in ONGLETS:
        onglet = "a_imprimer"
    qs = qs.filter(ONGLETS[onglet])
    if onglet == "a_imprimer":
        qs = qs.annotate(rang=Case(When(urgent=True, then=Value(0)), default=Value(1), output_field=IntegerField())) \
               .order_by("rang", "requisition__visa_responsable_le", "id")
    else:
        qs = qs.order_by("-requisition__visa_responsable_le", "-id")
    total = qs.count()
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    morceau = list(qs[(page - 1) * PAR_PAGE_DEMANDES: page * PAR_PAGE_DEMANDES])
    return Response({"count": total, "par_page": PAR_PAGE_DEMANDES, "compteurs": compteurs,
                     "results": _avec_telechargements(morceau)})


def _avec_telechargements(demandes):
    """Comme en_json, avec le nombre de téléchargements du bon."""
    resultats = en_json(demandes)
    for d, json in zip(demandes, resultats):
        json["requisition"]["nb_telechargements"] = getattr(d, "nb_telechargements", 0)
        json["requisition"]["nb_impressions"] = getattr(d, "nb_impressions", 0)
    return resultats


@api_view(["GET"])
@permission_classes([EstAgentOuResponsable])
def detail(request, pk):
    """Une réquisition signée (pk = id de la demande), avec l'historique de ses téléchargements."""
    d = _signees().filter(pk=pk).first()
    if d is None:
        return _introuvable()
    json = _avec_telechargements([d])[0]
    json["requisition"]["telechargements"] = [
        {"par": t.par.get_full_name() or t.par.username, "le": timezone.localtime(t.le).isoformat(), "role": t.role,
         "impression": t.impression}
        for t in d.requisition.telechargements.select_related("par")[:20]]
    return Response(json)


@api_view(["GET"])
@permission_classes([EstAgentOuResponsable])
def pdf(request, pk):
    """Télécharge le bon de réquisition en PDF (pk = id de la demande). Chaque téléchargement est noté.
    ?impression=1 (12/10/2026) : bouton « Imprimer » de l'application (le PDF s'ouvre dans l'aperçu d'impression).
    Le premier téléchargement ou la première impression par l'Agent Logistique marque le bon « Imprimée »."""
    impression = request.query_params.get("impression") == "1"
    # ReportLab est chargé ici seulement : s'il manque, le reste de GestiStock fonctionne quand même (12/10/2026).
    try:
        from .pdf_bon import fabriquer_pdf
    except ImportError:
        return Response({"general": ["Le PDF ne peut pas être fabriqué : le module ReportLab n'est pas installé sur ce PC. "
                                     "Double-cliquez sur outils\\installer-modules.bat (Internet nécessaire), "
                                     "puis redémarrez GestiStock."]}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    agent = a_le_role(request.user, ROLE_AGENT)
    with transaction.atomic():
        # select_for_update(of=("self",)) : PostgreSQL ne verrouille pas les tables jointes (demandeur facultatif).
        r = (Requisition.objects.select_for_update(of=("self",))
             .select_related("demande__demandeur", "visa_agent", "visa_responsable").filter(demande_id=pk).first())
        if r is None or r.statut != Requisition.Statut.VISEE:
            return Response({"general": ["Ce bon n'est pas encore signé par le Responsable HBC : il ne peut pas être imprimé."]},
                            status=status.HTTP_404_NOT_FOUND if r is None else status.HTTP_400_BAD_REQUEST)
        maintenant = timezone.now()
        TelechargementBon.objects.create(requisition=r, par=request.user, impression=impression,
                                         role=ROLE_AGENT if agent else ROLE_RESPONSABLE)
        if agent and r.imprimee_le is None:
            r.imprimee_le, r.imprimee_par = maintenant, request.user
            r.save(update_fields=["imprimee_le", "imprimee_par"])
    contenu = fabriquer_pdf(r, imprime_par=request.user, imprime_le=maintenant)
    reponse = HttpResponse(contenu, content_type="application/pdf")
    # Impression : affiché dans le navigateur (aperçu d'impression) au lieu d'être enregistré comme fichier.
    reponse["Content-Disposition"] = f'{"inline" if impression else "attachment"}; filename="{r.numero}.pdf"'
    reponse["Cache-Control"] = "no-store"
    return reponse
