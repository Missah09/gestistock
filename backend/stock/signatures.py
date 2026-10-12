"""Signatures dessinées au stylo électronique (souris, doigt ou stylet) : contrôle et lecture (11/10/2026).

Le navigateur envoie l'image du cadre de signature au format « data:image/png;base64,… ».
On ne garde que la partie base64, dans Requisition.signature_agent / signature_responsable.
"""
import base64
import binascii

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
