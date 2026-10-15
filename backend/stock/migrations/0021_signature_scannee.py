"""Signature scannée enregistrée dans le compte + origine des signatures (dessinée / importée), 15/10/2026."""
from django.db import migrations, models

CHOIX = [("DESSINEE", "dessinée à la souris"), ("IMPORTEE", "importée (signature scannée)")]


def anciennes_dessinees(apps, schema_editor):
    """Avant le 15/10/2026, toutes les signatures étaient dessinées à la souris."""
    Requisition = apps.get_model("stock", "Requisition")
    BonRetour = apps.get_model("stock", "BonRetour")
    Requisition.objects.exclude(signature_agent="").update(origine_signature_agent="DESSINEE")
    Requisition.objects.exclude(signature_responsable="").update(origine_signature_responsable="DESSINEE")
    BonRetour.objects.exclude(signature_agent="").update(origine_signature_agent="DESSINEE")


class Migration(migrations.Migration):
    dependencies = [("stock", "0020_mouvement_variation")]

    operations = [
        migrations.AddField("profil", "signature", models.TextField("signature enregistrée", blank=True, editable=False)),
        migrations.AddField("profil", "signature_le", models.DateTimeField("signature enregistrée le", null=True, blank=True,
                                                                           editable=False)),
        migrations.AddField("requisition", "origine_signature_agent", models.CharField(
            "signature de l'Agent", max_length=10, choices=CHOIX, blank=True, editable=False)),
        migrations.AddField("requisition", "origine_signature_responsable", models.CharField(
            "signature du Responsable", max_length=10, choices=CHOIX, blank=True, editable=False)),
        migrations.AddField("bonretour", "origine_signature_agent", models.CharField(
            "signature de l'Agent", max_length=10, choices=CHOIX, blank=True, editable=False)),
        migrations.RunPython(anciennes_dessinees, migrations.RunPython.noop),
    ]
