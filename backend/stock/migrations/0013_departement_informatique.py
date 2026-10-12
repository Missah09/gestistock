"""Département « Informatique » (12/10/2026) ; le compte « admin » (service Informatique) y est rattaché."""
from django.db import migrations


def ajouter(apps, schema_editor):
    Departement = apps.get_model("stock", "Departement")
    Profil = apps.get_model("stock", "Profil")
    User = apps.get_model("auth", "User")
    info, _ = Departement.objects.get_or_create(nom="Informatique")
    for u in User.objects.filter(username__iexact="admin"):
        p, _ = Profil.objects.get_or_create(user=u)
        p.departement = info
        p.save(update_fields=["departement"])


def rien(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0012_signatures"),
    ]

    operations = [migrations.RunPython(ajouter, rien)]
