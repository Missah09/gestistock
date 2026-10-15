"""Journal des événements (15/10/2026) : ce qui est modifié dans GestiStock, avec l'ancienne → nouvelle valeur.

Voir le modèle `Evenement`. Les mouvements du stock restent dans `MouvementEtat` ; les étapes du circuit des demandes
se lisent dans les demandes et réquisitions elles-mêmes. Ici : tout le reste (fiches, comptes, connexions).
Jamais de mot de passe ni d'image de signature dans le journal.
"""
import datetime
from decimal import Decimal

from django.db import models

from .models import Evenement

VIDE = "—"


def nom_de(user):
    return (user.get_full_name() or user.username) if user else ""


def adresse_ip(request):
    if request is None:
        return None
    transmise = request.META.get("HTTP_X_FORWARDED_FOR", "")  # en ligne (Render) : l'adresse réelle est transmise ici
    ip = (transmise.split(",")[0] if transmise else request.META.get("REMOTE_ADDR", "")).strip()
    return ip or None


def appareil(request):
    """« Windows · Chrome », « Android · Chrome », « iPhone · Safari »… (d'après le navigateur)."""
    if request is None:
        return ""
    ua = request.META.get("HTTP_USER_AGENT", "")
    systeme = next((nom for cle, nom in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"),
                                         ("Mac OS", "Mac"), ("Linux", "Linux")) if cle in ua), "")
    navigateur = next((nom for cle, nom in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"),
                                            ("Safari/", "Safari")) if cle in ua), "")
    return " · ".join(filter(None, [systeme, navigateur])) or ua[:120]


def noter(categorie, action, libelle, par=None, compte=None, identifiant="", article=None, objet="", reference="",
          detail="", request=None):
    par = par if par is not None and getattr(par, "is_authenticated", False) else None
    return Evenement.objects.create(
        categorie=categorie, action=action, libelle=libelle[:80], par=par, par_nom=nom_de(par)[:150],
        compte=compte, identifiant=(identifiant or (compte.username if compte else ""))[:150], article=article,
        objet=objet[:200], reference=reference[:60], detail=detail, adresse_ip=adresse_ip(request), appareil=appareil(request))


def modification(action, libelle, par, detail, article=None, objet="", reference="", request=None):
    return noter(Evenement.Categorie.MODIFICATION, action, libelle, par=par, article=article, objet=objet,
                 reference=reference, detail=detail, request=request)


def compte(action, libelle, par, cible, detail="", request=None):
    return noter(Evenement.Categorie.COMPTE, action, libelle, par=par, compte=cible, objet=nom_de(cible), detail=detail,
                 request=request)


# ---------------------------------------------------------------- Ancienne → nouvelle valeur
def texte(v):
    """Valeur lisible : vide → « — », 12500.00 → « 12 500 », date → 15/10/2026, oui / non."""
    if v is None or v == "":
        return VIDE
    if isinstance(v, bool):
        return "oui" if v else "non"
    if isinstance(v, Decimal):
        v = v.normalize()
        entier = v == v.to_integral()
        v = f"{int(v):,}".replace(",", " ") if entier else f"{v:,.2f}".replace(",", " ").replace(".", ",")
        return v
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    if isinstance(v, datetime.datetime):
        from django.utils import timezone
        return f"{timezone.localtime(v):%d/%m/%Y %H:%M}" if timezone.is_aware(v) else f"{v:%d/%m/%Y %H:%M}"
    if isinstance(v, datetime.date):
        return f"{v:%d/%m/%Y}"
    return str(v)


def differences(avant, apres):
    """{libellé: valeur} avant / après → « Prix unitaire : 12 500 Ar → 13 000 Ar · Qté minimale : 5 → 10 » (rien si égal).
    Clés « #<id> <champ> » (exemplaires d'un article) : « N° de série : FJK-0O1 → FJK-001 », « Code immo (FJK-001) : — → IM-22 »."""
    morceaux = []
    for cle in apres:
        a, b = avant.get(cle, VIDE), apres[cle]
        if a == b:
            continue
        if cle.startswith("#"):
            ident, champ = cle[1:].split(" ", 1)
            if champ == "N° de série":
                morceaux.append(f"N° de série : {a} → {b}")
            else:
                serie = apres.get(f"#{ident} N° de série", "")
                morceaux.append(f"{champ} ({serie}) : {a} → {b}")
        else:
            morceaux.append(f"{cle} : {a} → {b}")
    return " · ".join(morceaux)


# Champs jamais repris (mot de passe, sessions, images de signature, quantités déjà suivies dans les mouvements du stock).
EXCLUS = {"password", "last_login", "cle_session", "signature", "signature_agent", "signature_responsable", "qte_stock"}


def valeur_champ(obj, champ):
    if champ.choices:
        return texte(getattr(obj, f"get_{champ.name}_display")())
    if isinstance(champ, models.ForeignKey):
        return texte(getattr(obj, champ.name))
    return texte(getattr(obj, champ.attname))


def instantane(obj):
    """Toutes les valeurs modifiables d'un objet (administration) : {libellé: texte}."""
    if obj is None or obj.pk is None:
        return {}
    valeurs = {}
    for champ in obj._meta.fields:
        if not champ.editable or champ.primary_key or champ.name in EXCLUS or champ.auto_created:
            continue
        valeurs[str(champ.verbose_name).capitalize()] = valeur_champ(obj, champ)
    for champ in obj._meta.many_to_many:
        if champ.editable and champ.name not in EXCLUS:
            valeurs[str(champ.verbose_name).capitalize()] = ", ".join(sorted(str(x) for x in getattr(obj, champ.name).all())) or VIDE
    return valeurs
