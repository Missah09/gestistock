"""Envoie un email d'essai pour vérifier les réglages (outils\\configurer-email.bat le lance).

    python manage.py tester_email            → à l'adresse temporaire ou aux Responsables HBC
    python manage.py tester_email moi@x.com  → à cette adresse
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from stock.notifications import destinataires_responsable, email_actif


class Command(BaseCommand):
    help = "Envoie un email d'essai GestiStock."

    def add_arguments(self, parser):
        parser.add_argument("adresse", nargs="?")

    def handle(self, *args, **opts):
        a = [opts["adresse"]] if opts["adresse"] else destinataires_responsable()
        if not a:
            raise CommandError("Aucun destinataire : indiquez une adresse, ou réglez GESTISTOCK_EMAIL_TEMPORAIRE dans backend\\.env.")
        if not email_actif():
            self.stdout.write("Envoi pas encore configuré (pas de mot de passe d'application) : "
                              "le message sera enregistré dans backend\\emails-non-envoyes.")
        try:
            send_mail("GestiStock – email d'essai",
                      "Bonjour,\n\nCet email d'essai confirme que GestiStock peut envoyer des emails.\n\n— GestiStock, H.B.C",
                      settings.DEFAULT_FROM_EMAIL, a, fail_silently=False)
        except Exception as exc:
            raise CommandError(f"Échec de l'envoi ({type(exc).__name__}) : {exc}\n"
                               "Vérifiez l'adresse Gmail et le mot de passe d'application (16 lettres).")
        self.stdout.write(self.style.SUCCESS(f"OK : email d'essai {'envoyé' if email_actif() else 'enregistré'} pour {', '.join(a)}."))
