"""Connexion / déconnexion et informations sur le compte connecté (11/10/2026)."""
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .permissions import MESSAGE_AUTRE_APPAREIL, session_remplacee
from .models import ROLE_AGENT, ROLE_RESPONSABLE, Demande, Requisition, departement_de, roles_de

ESSAIS_MAX = 5          # essais ratés avant blocage
BLOCAGE_SECONDES = 300  # 5 minutes


def compte_en_json(user):
    roles = roles_de(user)
    dep = departement_de(user)
    return {
        "connecte": True,
        "identifiant": user.username,
        "nom": user.get_full_name() or user.username,
        "departement": dep.nom if dep else "",
        "roles": roles,
        "agent_logistique": ROLE_AGENT in roles,
        "responsable": ROLE_RESPONSABLE in roles,
        "administrateur": user.is_superuser,
        "emails": settings.GESTISTOCK_EMAILS,
    }


@api_view(["GET"])
def compteurs(request):
    """Nombres affichés sur le menu (mis à jour toutes les 30 s) : ce qui attend l'utilisateur connecté."""
    roles = roles_de(request.user)
    reponse = {}
    if ROLE_AGENT in roles:
        reponse["a_valider"] = Demande.objects.filter(statut=Demande.Statut.EN_ATTENTE).count()
        # Bons signés pas encore imprimés (écran « Réquisitions »)
        reponse["a_imprimer"] = Requisition.objects.filter(statut=Requisition.Statut.VISEE, imprimee_le__isnull=True).count()
        # Bons imprimés dont la remise au magasin n'est pas encore confirmée (écran « Sorties », 12/10/2026)
        reponse["a_confirmer"] = Requisition.objects.filter(statut=Requisition.Statut.VISEE, imprimee_le__isnull=False,
                                                            sortie__isnull=True).count()
        # Matériel prêté pas rentré à la date prévue (écran « Retours de stock », 12/10/2026)
        from .views_retours import compter_retards
        reponse["retours_en_retard"] = compter_retards()
    if ROLE_RESPONSABLE in roles:
        reponse["a_viser"] = Requisition.objects.filter(statut=Requisition.Statut.ATTENTE_VISA).count()
    return Response(reponse)


@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([AllowAny])
def session(request):
    """Qui est connecté ? (pose aussi le cookie de protection CSRF)."""
    if request.user and request.user.is_authenticated:
        return Response(compte_en_json(request.user))
    if session_remplacee(request):  # l'application vérifie toutes les 30 s : message clair à l'écran de connexion
        return Response({"connecte": False, "raison": "autre_appareil", "message": MESSAGE_AUTRE_APPAREIL})
    return Response({"connecte": False})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def connexion(request):
    identifiant = str(request.data.get("identifiant", "")).strip()
    mot_de_passe = str(request.data.get("mot_de_passe", ""))
    erreurs = {}
    if not identifiant:
        erreurs["identifiant"] = ["Indiquez votre identifiant."]
    if not mot_de_passe:
        erreurs["mot_de_passe"] = ["Indiquez votre mot de passe."]
    if erreurs:
        return Response(erreurs, status=status.HTTP_400_BAD_REQUEST)

    cle = f"connexion-ratee:{identifiant.lower()}"
    if cache.get(cle, 0) >= ESSAIS_MAX:
        return Response({"general": ["Trop d'essais ratés : patientez 5 minutes avant de réessayer."]},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)

    user = authenticate(request, username=identifiant, password=mot_de_passe)
    if user is None:
        cache.set(cle, cache.get(cle, 0) + 1, BLOCAGE_SECONDES)
        return Response({"general": ["Identifiant ou mot de passe incorrect."]}, status=status.HTTP_400_BAD_REQUEST)
    cache.delete(cle)
    login(request, user)
    return Response(compte_en_json(user))


@api_view(["POST"])
@permission_classes([AllowAny])
def deconnexion(request):
    logout(request)
    return Response({"connecte": False})


@api_view(["GET", "DELETE"])
def ma_signature(request):
    """Signature scannée enregistrée dans le compte connecté (15/10/2026).
    GET : {"enregistree", "image" (data:image/png;base64,…), "le"} ; DELETE : la retire du compte.
    Elle s'enregistre au moment de signer (case « Enregistrer dans mon compte »), avec le mot de passe retapé."""
    from .serializers import heure_locale
    from .signatures import en_data_url, profil_de
    p = profil_de(request.user)
    if request.method == "DELETE":
        p.signature, p.signature_le = "", None
        p.save(update_fields=["signature", "signature_le"])
        return Response({"enregistree": False, "image": None, "le": None,
                         "message": "Signature enregistrée retirée de votre compte."})
    return Response({"enregistree": bool(p.signature), "image": en_data_url(p.signature), "le": heure_locale(p.signature_le)})
