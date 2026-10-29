"""Écran « Comptes » de l'administrateur (11/10/2026) : créer, modifier, désactiver les comptes GestiStock.

Rôles : cases « Responsable Technique » et « Responsable Logistique » (groupes Django). Tout compte actif est Saisisseur.
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

from . import journal
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
        # Signature scannée enregistrée par la personne (15/10/2026) ; l'image se lit à part (comptes/<id>/signature/)
        "signature_enregistree": bool(p.signature), "signature_le": heure_locale(p.signature_le),
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


def valeurs_compte(u):
    """Ce qui se modifie dans l'écran « Comptes », lisible, pour l'historique des comptes (15/10/2026)."""
    p, _ = Profil.objects.get_or_create(user=u)
    return {"Identifiant": u.username, "Prénom": journal.texte(u.first_name), "Nom": journal.texte(u.last_name),
            "Email": journal.texte(u.email), "Département": journal.texte(p.departement),
            "Rôles": ", ".join(r for r in roles_de(u) if r != "Saisisseur") or "Saisisseur"}


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
        journal.compte("compte_cree", "Compte créé", request.user, u,
                       " · ".join(f"{k} : {x}" for k, x in valeurs_compte(u).items() if x != journal.VIDE)
                       + " · Mot de passe provisoire donné", request=request)
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
    avant = valeurs_compte(u)
    _appliquer(u, v)
    detail = journal.differences(avant, valeurs_compte(u))
    if detail:
        journal.compte("compte_modifie", "Compte modifié", request.user, u, detail, request=request)
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
    change = u.is_active != actif
    u.is_active = actif
    u.save(update_fields=["is_active"])
    if not actif:
        fermer_session(u.profil.cle_session)
    if change:
        journal.compte("compte_reactive" if actif else "compte_desactive", "Compte réactivé" if actif else "Compte désactivé",
                       request.user, u, "Il peut de nouveau se connecter" if actif
                       else "Il ne peut plus se connecter (déconnecté s'il était connecté)", request=request)
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
    # Jamais le mot de passe lui-même dans le journal.
    journal.compte("mot_de_passe", "Mot de passe changé", request.user, u,
                   "Nouveau mot de passe donné par l'administrateur" + ("" if u == request.user else " (déconnecté de son appareil)"),
                   request=request)
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
    etait = session_ouverte(u.profil)
    fermer_session(u.profil.cle_session)
    journal.compte("deconnexion_forcee", "Déconnecté par l'administrateur", request.user, u,
                   "Session de son appareil fermée" if etait else "Il n'était pas connecté", request=request)
    return Response({"message": f"« {u.username} » a été déconnecté.", "compte": compte_json(u)})


@api_view(["GET", "DELETE"])
@permission_classes([EstAdministrateur])
def signature(request, pk):
    """Signature scannée enregistrée dans un compte (15/10/2026).
    GET : l'image (PNG), pour la vérifier ; DELETE : la retire du compte (ex. départ de la personne, signature
    qui ne convient pas). Les bons déjà signés gardent leur signature."""
    from django.http import HttpResponse
    from .signatures import image
    u = _compte(pk)
    if u is None:
        return _introuvable()
    p, _ = Profil.objects.get_or_create(user=u)
    if request.method == "GET":
        if not p.signature:
            return Response({"general": ["Aucune signature enregistrée dans ce compte."]}, status=status.HTTP_404_NOT_FOUND)
        reponse = HttpResponse(image(p.signature), content_type="image/png")
        reponse["Cache-Control"] = "no-store"
        return reponse
    if not p.signature:
        return Response({"general": ["Aucune signature enregistrée dans ce compte."]}, status=status.HTTP_400_BAD_REQUEST)
    p.signature, p.signature_le = "", None
    p.save(update_fields=["signature", "signature_le"])
    journal.compte("signature_retiree", "Signature enregistrée retirée", request.user, u,
                   "Retirée par l'administrateur ; les bons déjà signés ne changent pas", request=request)
    return Response({"message": f"Signature enregistrée de « {u.username} » retirée. Les bons déjà signés ne changent pas.",
                     "compte": compte_json(u)})


# ---------------------------------------------------------------- Historique des comptes et journal de connexion (15/10/2026)
TONS_JOURNAL = {"compte_cree": "vert", "compte_reactive": "vert", "compte_desactive": "rouge", "admin_suppr": "rouge",
                "connexion": "vert", "connexion_ratee": "rouge", "connexion_bloquee": "rouge", "session_remplacee": "orange",
                "deconnexion_forcee": "orange", "deconnexion": "gris"}
PAR_PAGE_JOURNAL = 50


@api_view(["GET"])
@permission_classes([EstAdministrateur])
def journal_comptes(request):
    """Écran « Comptes » de l'administrateur, onglets « Historique des comptes » (?vue=comptes) et
    « Journal de connexion » (?vue=connexions). Filtres : compte, periode (du, au), q, resultat=echecs, page."""
    from .models import Evenement
    from .rapports import PERIODES, periode_de
    from .views import sans_accents
    p = request.query_params
    vue = Evenement.Categorie.CONNEXION if p.get("vue") == "connexions" else Evenement.Categorie.COMPTE
    du, au, libelle = periode_de(p, defaut="mois")
    qs = Evenement.objects.filter(categorie=vue).select_related("compte", "par")
    if du:
        qs = qs.filter(le__date__gte=du)
    if au:
        qs = qs.filter(le__date__lte=au)
    if str(p.get("compte") or "").isdigit():
        qs = qs.filter(compte_id=int(p["compte"]))
    if vue == Evenement.Categorie.CONNEXION and p.get("resultat") == "echecs":
        qs = qs.filter(action__in=["connexion_ratee", "connexion_bloquee"])
    lignes = list(qs)
    q = sans_accents(p.get("q") or "").split()
    if q:
        lignes = [e for e in lignes if all(m in sans_accents(" ".join(
            [e.libelle, e.objet, e.identifiant, e.detail, e.par_nom, e.adresse_ip or "", e.appareil])) for m in q)]
    try:
        page = max(1, int(p.get("page") or 1))
    except ValueError:
        page = 1
    pages = max(1, -(-len(lignes) // PAR_PAGE_JOURNAL))
    page = min(page, pages)
    morceau = lignes[(page - 1) * PAR_PAGE_JOURNAL: page * PAR_PAGE_JOURNAL]
    return Response({
        "lignes": [{"id": e.id, "le": heure_locale(e.le), "evenement": e.libelle, "ton": TONS_JOURNAL.get(e.action, "violet"),
                    "compte": journal.nom_de(e.compte) if e.compte else (e.objet or e.identifiant),
                    "identifiant": e.compte.username if e.compte else e.identifiant,
                    "par": journal.nom_de(e.par) if e.par else e.par_nom, "detail": e.detail,
                    "adresse_ip": e.adresse_ip or "", "appareil": e.appareil} for e in morceau],
        "count": len(lignes), "page": page, "pages": pages, "par_page": PAR_PAGE_JOURNAL,
        "periode": {"libelle": libelle}, "periodes": [{"valeur": v, "libelle": l} for v, l in PERIODES],
        "comptes": [{"id": u.id, "nom": journal.nom_de(u)} for u in User.objects.order_by("first_name", "last_name", "username")],
    })
