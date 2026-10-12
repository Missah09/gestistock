"""Écran « Comptes » de l'administrateur (11/10/2026) : créer, modifier, désactiver les comptes GestiStock.

Rôles : cases « Agent Logistique » et « Responsable HBC » (groupes Django). Tout compte actif est Saisisseur.
Le super-utilisateur (Administrateur) se gère toujours dans l'administration Django.
"""
import re

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import ROLE_AGENT, ROLE_RESPONSABLE, Departement, Profil, fermer_session, roles_de, session_ouverte
from .permissions import EstAdministrateur
from .serializers import heure_locale

IDENTIFIANT = re.compile(r"^[A-Za-z0-9._-]{3,30}$")


def compte_json(u):
    p, _ = Profil.objects.get_or_create(user=u)
    roles = roles_de(u)
    return {
        "id": u.id, "identifiant": u.username, "prenom": u.first_name, "nom": u.last_name,
        "nom_complet": u.get_full_name() or u.username, "email": u.email,
        "departement": p.departement_id, "departement_nom": p.departement.nom if p.departement_id else "",
        "agent": ROLE_AGENT in roles, "responsable": ROLE_RESPONSABLE in roles, "administrateur": u.is_superuser,
        "actif": u.is_active, "connecte": u.is_active and session_ouverte(p),
        "derniere_connexion": heure_locale(u.last_login), "cree_le": heure_locale(u.date_joined),
    }


def _texte(data, cle, maxi):
    return str(data.get(cle) or "").strip()[:maxi]


def _verifier(data, u=None):
    """Contrôle les champs communs. Renvoie (valeurs, erreurs)."""
    e, v = {}, {}
    v["prenom"] = _texte(data, "prenom", 150)
    v["nom"] = _texte(data, "nom", 150)
    v["email"] = _texte(data, "email", 254)
    if not v["prenom"]:
        e["prenom"] = ["Indiquez le prénom (il est imprimé sur le bon de réquisition)."]
    if not v["nom"]:
        e["nom"] = ["Indiquez le nom (il est imprimé sur le bon de réquisition)."]
    if v["email"]:
        try:
            validate_email(v["email"])
        except ValidationError:
            e["email"] = ["Adresse email incorrecte."]
    dep = data.get("departement")
    v["departement"] = Departement.objects.filter(pk=dep, actif=True).first() if str(dep or "").isdigit() else None
    if v["departement"] is None and not (u and u.is_superuser):
        e["departement"] = ["Choisissez le département (il sert de « Service demandeur » sur le bon)."]
    v["agent"] = bool(data.get("agent"))
    v["responsable"] = bool(data.get("responsable"))
    return v, e


def _appliquer(u, v):
    u.first_name, u.last_name, u.email = v["prenom"], v["nom"], v["email"]
    u.save()
    p, _ = Profil.objects.get_or_create(user=u)
    p.departement = v["departement"]
    p.save(update_fields=["departement"])
    for role, oui in ((ROLE_AGENT, v["agent"]), (ROLE_RESPONSABLE, v["responsable"])):
        g = Group.objects.get(name=role)
        (u.groups.add if oui else u.groups.remove)(g)


def _erreurs_mdp(mdp, u):
    if not mdp:
        return ["Indiquez un mot de passe provisoire."]
    try:
        validate_password(mdp, user=u)
    except ValidationError as exc:
        return list(exc.messages)
    return None


@api_view(["GET", "POST"])
@permission_classes([EstAdministrateur])
def comptes(request):
    """GET : tous les comptes (+ départements proposés). POST : nouveau compte."""
    if request.method == "GET":
        qs = User.objects.select_related("profil__departement").prefetch_related("groups").order_by("-is_active", "first_name", "last_name", "username")
        return Response({"comptes": [compte_json(u) for u in qs],
                         "departements": list(Departement.objects.filter(actif=True).values("id", "nom"))})

    d = request.data
    v, e = _verifier(d)
    ident = _texte(d, "identifiant", 30)
    if not ident:
        e["identifiant"] = ["Indiquez l'identifiant (le nom utilisé pour se connecter)."]
    elif not IDENTIFIANT.match(ident):
        e["identifiant"] = ["3 à 30 caractères : lettres sans accent, chiffres, point, tiret ou souligné (pas d'espace)."]
    elif User.objects.filter(username__iexact=ident).exists():
        e["identifiant"] = ["Cet identifiant est déjà pris."]
    mdp = str(d.get("mot_de_passe") or "")
    err = _erreurs_mdp(mdp, User(username=ident, first_name=v["prenom"], last_name=v["nom"], email=v["email"]))
    if err:
        e["mot_de_passe"] = err
    if e:
        return Response(e, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        u = User.objects.create_user(ident, password=mdp)
        _appliquer(u, v)
    return Response({"message": f"Compte « {ident} » créé. Donnez-lui son identifiant et son mot de passe provisoire.",
                     "compte": compte_json(u)}, status=status.HTTP_201_CREATED)


def _compte(pk):
    return User.objects.filter(pk=pk).first()


def _introuvable():
    return Response({"general": ["Compte introuvable."]}, status=status.HTTP_404_NOT_FOUND)


@api_view(["PATCH"])
@permission_classes([EstAdministrateur])
def modifier(request, pk):
    """Prénom, nom, email, département, rôles."""
    u = _compte(pk)
    if u is None:
        return _introuvable()
    v, e = _verifier(request.data, u)
    if e:
        return Response(e, status=status.HTTP_400_BAD_REQUEST)
    _appliquer(u, v)
    return Response({"message": f"Compte « {u.username} » enregistré.", "compte": compte_json(u)})


@api_view(["POST"])
@permission_classes([EstAdministrateur])
def activer(request, pk):
    """{"actif": false} : désactive (le compte ne peut plus se connecter, il est déconnecté) ; true : réactive."""
    u = _compte(pk)
    if u is None:
        return _introuvable()
    actif = bool(request.data.get("actif"))
    if not actif and u == request.user:
        return Response({"general": ["Vous ne pouvez pas désactiver votre propre compte."]}, status=status.HTTP_400_BAD_REQUEST)
    u.is_active = actif
    u.save(update_fields=["is_active"])
    if not actif:
        fermer_session(u.profil.cle_session)
    return Response({"message": f"Compte « {u.username} » {'réactivé' if actif else 'désactivé : il ne peut plus se connecter'}.",
                     "compte": compte_json(u)})


@api_view(["POST"])
@permission_classes([EstAdministrateur])
def mot_de_passe(request, pk):
    """Nouveau mot de passe (oublié, ou compte à remettre à zéro). L'appareil connecté est déconnecté."""
    u = _compte(pk)
    if u is None:
        return _introuvable()
    mdp = str(request.data.get("mot_de_passe") or "")
    err = _erreurs_mdp(mdp, u)
    if err:
        return Response({"mot_de_passe": err}, status=status.HTTP_400_BAD_REQUEST)
    u.set_password(mdp)
    u.save(update_fields=["password"])
    if u == request.user:
        update_session_auth_hash(request, u)  # l'administrateur qui change son propre mot de passe reste connecté
    else:
        fermer_session(u.profil.cle_session)
    return Response({"message": f"Mot de passe de « {u.username} » changé.", "compte": compte_json(u)})


@api_view(["POST"])
@permission_classes([EstAdministrateur])
def deconnecter(request, pk):
    """Ferme la session de l'appareil où le compte est connecté (ex. PC resté ouvert)."""
    u = _compte(pk)
    if u is None:
        return _introuvable()
    if u == request.user:
        return Response({"general": ["Pour vous déconnecter vous-même, utilisez « Se déconnecter »."]},
                        status=status.HTTP_400_BAD_REQUEST)
    fermer_session(u.profil.cle_session)
    return Response({"message": f"« {u.username} » a été déconnecté.", "compte": compte_json(u)})
