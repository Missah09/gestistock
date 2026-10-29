"""Droits d'accès selon le rôle (11/10/2026)."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import ROLE_AGENT, ROLE_RESPONSABLE, a_le_role


class EstAgentLogistique(BasePermission):
    message = "Réservé au Responsable Technique."

    def has_permission(self, request, view):
        return a_le_role(request.user, ROLE_AGENT)


class EstResponsable(BasePermission):
    message = "Réservé au Responsable Logistique."

    def has_permission(self, request, view):
        return a_le_role(request.user, ROLE_RESPONSABLE)


class EstAgentOuResponsable(BasePermission):
    """Écran « Réquisitions » : le Responsable Technique et le Responsable Logistique (12/10/2026)."""
    message = "Réservé au Responsable Technique et au Responsable Logistique."

    def has_permission(self, request, view):
        return a_le_role(request.user, ROLE_AGENT) or a_le_role(request.user, ROLE_RESPONSABLE)


class EstAdministrateur(BasePermission):
    message = "Réservé à l'administrateur."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class LectureOuAgentLogistique(BasePermission):
    """Lecture pour tout compte connecté ; modification pour le Responsable Technique."""
    message = "Seul le Responsable Technique peut modifier les articles."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or a_le_role(request.user, ROLE_AGENT)


MESSAGE_AUTRE_APPAREIL = ("Votre compte vient d'être ouvert sur un autre appareil : vous avez été déconnecté ici. "
                          "Un compte ne peut être connecté que sur un seul appareil à la fois.")


def session_remplacee(request):
    """Vrai si le cookie de session de cet appareil a été fermé par une connexion ailleurs."""
    from django.conf import settings
    from django.core.cache import cache
    from .models import SESSION_REMPLACEE
    cle = request.COOKIES.get(settings.SESSION_COOKIE_NAME) if request is not None else None
    return bool(cle) and bool(cache.get(SESSION_REMPLACEE + cle))


def gestion_erreurs(exc, context):
    """Comme DRF, mais « non connecté » renvoie 401 (l'écran de connexion s'affiche alors)."""
    from rest_framework.exceptions import NotAuthenticated
    from rest_framework.views import exception_handler
    reponse = exception_handler(exc, context)
    if isinstance(exc, NotAuthenticated) and reponse is not None:
        reponse.status_code = 401
        if session_remplacee(context.get("request")):
            reponse.data = {"general": [MESSAGE_AUTRE_APPAREIL], "raison": "autre_appareil"}
        else:
            reponse.data = {"general": ["Votre session est terminée : reconnectez-vous."]}
    return reponse
