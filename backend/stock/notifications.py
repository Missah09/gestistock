"""Emails de GestiStock (11/10/2026) : prévenir le Responsable Logistique qu'une réquisition attend son visa."""
from html import escape

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils import timezone

from .models import ROLE_RESPONSABLE, departement_de


def email_actif():
    """Vrai si les emails partent réellement (Gmail configuré) ; sinon ils sont enregistrés comme fichiers."""
    return settings.EMAIL_BACKEND.endswith("smtp.EmailBackend")


def destinataires_responsable():
    """Adresse temporaire si elle est réglée (.env), sinon les adresses des comptes Responsable Logistique actifs."""
    if settings.GESTISTOCK_EMAIL_TEMPORAIRE:
        return [settings.GESTISTOCK_EMAIL_TEMPORAIRE]
    comptes = User.objects.filter(is_active=True).filter(Q(groups__name=ROLE_RESPONSABLE) | Q(is_superuser=True))
    # Le super-utilisateur a tous les rôles, mais on ne l'écrit que s'il n'y a aucun vrai Responsable.
    vrais = [u.email for u in comptes.filter(groups__name=ROLE_RESPONSABLE).distinct() if u.email]
    return vrais or [u.email for u in comptes.distinct() if u.email]


def _nom(user):
    return (user.get_full_name() or user.username) if user else "—"


def _quantite(n, unite):
    if unite == "m":
        return f"{n} m"
    if unite == "paire":
        return f"{n} paire{'s' if n > 1 else ''}"
    return str(n)


def message_visa(r):
    """Sujet, texte et HTML de l'email « réquisition à viser »."""
    d = r.demande
    lien = f"{settings.GESTISTOCK_ADRESSE}/#a-viser/{d.id}"
    dep = departement_de(d.demandeur) if d.demandeur else None
    quand = timezone.localtime(r.visa_agent_le)
    lignes = [l for l in d.lignes.select_related("article") if (l.qte_accordee if l.qte_accordee is not None else l.quantite) > 0]
    infos = [("N° de réquisition", r.numero), ("Demande", d.numero), ("Demandeur", _nom(d.demandeur)),
             ("Service demandeur", dep.nom if dep else "—"), ("Magasin", d.magasin.nom),
             ("Chantier", d.chantier.nom if d.chantier_id else "—"),
             ("Validée par", f"{_nom(r.visa_agent)}, le {quand:%d/%m/%Y} à {quand:%H} h {quand:%M}")]
    if d.urgent:
        infos.insert(0, ("Priorité", "URGENT"))

    sujet = f"GestiStock – Réquisition {r.numero} à viser{' (URGENT)' if d.urgent else ''}"
    texte = "\n".join([
        "Bonjour,", "",
        f"La réquisition matière {r.numero} attend votre visa.", "",
        *[f"{k} : {v}" for k, v in infos], "",
        "Articles :",
        *[f"  - {l.article.code} {l.article.nom} : {_quantite(l.qte_accordee if l.qte_accordee is not None else l.quantite, l.article.unite)}"
          for l in lignes], "",
        f"Pour la viser ou la refuser, ouvrez GestiStock : {lien}",
        "(connectez-vous avec votre identifiant ; la réquisition s'ouvre directement).", "",
        "— GestiStock, H.B.C (message automatique, ne pas répondre)",
    ])

    td = 'style="padding:6px 10px;border-bottom:1px solid #e3e7ee;"'
    html = f"""<div style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;color:#383838;max-width:640px">
<div style="background:#415F83;color:#fff;padding:14px 18px;border-radius:8px 8px 0 0;font-size:18px;font-weight:700">
GestiStock · Réquisition {escape(r.numero)} à viser</div>
<div style="border:1px solid #d3dbe4;border-top:0;padding:16px 18px;border-radius:0 0 8px 8px">
<p>Bonjour,</p><p>La réquisition matière <b>{escape(r.numero)}</b> attend votre visa.</p>
<table style="border-collapse:collapse;width:100%;margin:8px 0 14px">{''.join(
        f'<tr><td {td} width="40%"><span style="color:#626262">{escape(k)}</span></td><td {td}><b>{escape(v)}</b></td></tr>'
        for k, v in infos)}</table>
<p style="margin:0 0 6px;font-weight:700;color:#2F4763">Articles</p>
<table style="border-collapse:collapse;width:100%;margin-bottom:18px">
<tr style="background:#eef2f6"><th {td} align="left">Code</th><th {td} align="left">Désignation</th><th {td} align="right">Quantité</th></tr>
{''.join(f'<tr><td {td}>{escape(l.article.code)}</td><td {td}>{escape(l.article.nom)}</td>'
         f'<td {td} align="right"><b>{escape(_quantite(l.qte_accordee if l.qte_accordee is not None else l.quantite, l.article.unite))}</b></td></tr>'
         for l in lignes)}
</table>
<p><a href="{escape(lien)}" style="display:inline-block;background:#415F83;color:#fff;text-decoration:none;font-weight:700;padding:12px 22px;border-radius:8px">Ouvrir la réquisition dans GestiStock</a></p>
<p style="color:#626262;font-size:13px">Connectez-vous avec votre identifiant : la réquisition s'ouvre directement.<br>
Message automatique de GestiStock (H.B.C), merci de ne pas répondre.</p></div></div>"""
    return sujet, texte, html


def prevenir_responsable(r):
    """Envoie l'email « à viser ». Ne bloque jamais la validation : le résultat est noté sur la réquisition
    (email_envoye_le, email_etat) et renvoyé sous forme de phrase."""
    a = destinataires_responsable()
    if not a:
        r.email_etat = ("Email non envoyé : aucun compte « Responsable Logistique » n'a d'adresse email "
                        "(administration › Utilisateurs).")
        r.save(update_fields=["email_etat"])
        return r.email_etat
    sujet, texte, html = message_visa(r)
    try:
        m = EmailMultiAlternatives(sujet, texte, settings.DEFAULT_FROM_EMAIL, a)
        m.attach_alternative(html, "text/html")
        m.send(fail_silently=False)
    except Exception as exc:  # serveur injoignable, mot de passe refusé…
        r.email_etat = f"Email non envoyé ({type(exc).__name__}) : {exc}"[:300]
        r.save(update_fields=["email_etat"])
        return r.email_etat
    r.email_envoye_le = timezone.now()
    if email_actif():
        r.email_etat = f"Email envoyé à {', '.join(a)}."[:300]
    else:
        r.email_etat = ("Envoi des emails pas encore configuré : le message a été enregistré dans le dossier "
                        "backend\\emails-non-envoyes (lancez outils\\configurer-email.bat).")
    r.save(update_fields=["email_envoye_le", "email_etat"])
    return r.email_etat
