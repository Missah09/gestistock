"""Connexion sans tenir compte des majuscules (12/10/2026).

« haja », « HAJA » et « Haja » ouvrent le même compte. L'écran « Comptes » refuse déjà deux
identifiants qui ne diffèrent que par les majuscules, il n'y a donc jamais d'ambiguïté.
Sert pour GestiStock et pour l'administration Django (réglage AUTHENTICATION_BACKENDS).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class IdentifiantSansMajuscules(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        username = str(username).strip()
        trouves = list(User._default_manager.filter(**{f"{User.USERNAME_FIELD}__iexact": username})[:2])
        # Identifiant exact en priorité (anciens comptes éventuels ne différant que par les majuscules).
        exact = [u for u in trouves if u.get_username() == username]
        user = exact[0] if exact else (trouves[0] if len(trouves) == 1 else None)
        if user is None:
            User().set_password(password)  # même durée de calcul qu'un vrai essai
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
