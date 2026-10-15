"""Signatures électroniques : contrôle et lecture.

11/10/2026 : signature dessinée au stylo électronique (souris, doigt ou stylet).
15/10/2026 : signature scannée (papier + stylo), nettoyée dans le navigateur (fond transparent, recadrée),
             enregistrée une fois dans le compte et réutilisée d'un clic ; mot de passe à retaper à chaque signature.

Le navigateur envoie l'image au format « data:image/png;base64,… ».
On ne garde que la partie base64, dans Requisition.signature_agent / signature_responsable, BonRetour.signature_agent
et Profil.signature (signature enregistrée).

Corps attendu pour signer (valider, viser, bon de retour) :
  {"source": "dessinee" | "importee" | "enregistree",
   "signature": "data:image/png;base64,…"   (sauf source « enregistree »),
   "enregistrer": true                      (source « importee » : garder la signature dans le compte),
   "mot_de_passe": "…"}
"""
import base64
import binascii
from dataclasses import dataclass

from django.core.cache import cache
from django.utils import timezone

PREFIXE = "data:image/png;base64,"
TAILLE_MAX = 500 * 1024  # octets


def lire_signature(valeur):
    """Renvoie la signature (base64) ou lève ValueError avec un message pour l'utilisateur."""
    if not valeur:
        raise ValueError("Signez dans le cadre avec la souris avant de valider.")
    if not isinstance(valeur, str) or not valeur.startswith(PREFIXE):
        raise ValueError("Signature illisible : effacez et signez à nouveau.")
    b64 = valeur[len(PREFIXE):]
    try:
        octets = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Signature illisible : effacez et signez à nouveau.")
    if not octets.startswith(b"\x89PNG") or len(octets) < 60:
        raise ValueError("Signature illisible : effacez et signez à nouveau.")
    if len(octets) > TAILLE_MAX:
        raise ValueError("Signature trop grande : effacez et signez à nouveau.")
    return b64


def image(b64):
    return base64.b64decode(b64)


def en_data_url(b64):
    return PREFIXE + b64 if b64 else None


# --- Signer : mot de passe retapé + signature (dessinée, importée ou enregistrée) -----------------------------------

ESSAIS_MAX = 5          # mots de passe ratés au moment de signer, avant blocage
BLOCAGE_SECONDES = 300  # 5 minutes


class ErreurSignature(Exception):
    """Erreur à montrer à l'utilisateur ; champ = « signature » ou « mot_de_passe » ; code HTTP."""

    def __init__(self, champ, message, code=400):
        super().__init__(message)
        self.champ, self.message, self.code = champ, message, code

    def reponse(self):
        from rest_framework.response import Response
        return Response({self.champ: [self.message]}, status=self.code)


@dataclass
class Signature:
    b64: str
    origine: str          # OrigineSignature (DESSINEE / IMPORTEE)
    a_enregistrer: bool   # garder cette signature scannée dans le compte après l'action


def profil_de(user):
    from .models import Profil
    return Profil.objects.get_or_create(user=user)[0]


def verifier_mot_de_passe(user, mot_de_passe):
    """Le mot de passe du compte connecté, retapé au moment de signer (quelqu'un qui trouve la session ouverte
    ne peut pas signer à la place de la personne). Blocage 5 minutes après 5 essais ratés."""
    cle = f"signature-ratee:{user.pk}"
    if cache.get(cle, 0) >= ESSAIS_MAX:
        raise ErreurSignature("mot_de_passe", "Trop d'essais ratés : patientez 5 minutes avant de signer.", 429)
    if not mot_de_passe:
        raise ErreurSignature("mot_de_passe", "Retapez votre mot de passe pour signer.")
    if not user.check_password(mot_de_passe):
        cache.set(cle, cache.get(cle, 0) + 1, BLOCAGE_SECONDES)
        raise ErreurSignature("mot_de_passe", "Mot de passe incorrect.")
    cache.delete(cle)


def signature_de_la_requete(request):
    """Lit et contrôle la signature envoyée puis le mot de passe ; lève ErreurSignature."""
    from .models import OrigineSignature
    donnees = request.data if isinstance(request.data, dict) else {}
    source = str(donnees.get("source") or "dessinee")
    if source == "enregistree":
        b64 = profil_de(request.user).signature
        if not b64:
            raise ErreurSignature("signature", "Aucune signature n'est enregistrée dans votre compte : importez-la.")
        sig = Signature(b64, OrigineSignature.IMPORTEE, False)
    elif source in ("dessinee", "importee"):
        try:
            b64 = lire_signature(donnees.get("signature"))
        except ValueError as exc:
            message = str(exc)
            if source == "importee":
                message = message.replace("Signez dans le cadre avec la souris", "Importez votre signature scannée") \
                                 .replace("effacez et signez à nouveau", "choisissez un autre fichier")
            raise ErreurSignature("signature", message)
        importee = source == "importee"
        sig = Signature(b64, OrigineSignature.IMPORTEE if importee else OrigineSignature.DESSINEE,
                        importee and bool(donnees.get("enregistrer")))
    else:
        raise ErreurSignature("signature", "Signature illisible : recommencez.")
    verifier_mot_de_passe(request.user, str(donnees.get("mot_de_passe") or ""))
    return sig


def enregistrer_si_demande(user, sig):
    """Après une signature réussie : garde la signature scannée dans le compte si la case était cochée."""
    if sig.a_enregistrer:
        p = profil_de(user)
        remplace = bool(p.signature)
        p.signature, p.signature_le = sig.b64, timezone.now()
        p.save(update_fields=["signature", "signature_le"])
        from . import journal  # (15/10/2026) l'image n'est jamais copiée dans le journal
        journal.compte("signature_enregistree", "Signature enregistrée dans le compte", user, user,
                       "Signature scannée " + ("remplacée" if remplace else "enregistrée") + " par la personne elle-même")
