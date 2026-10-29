"""Nouveaux noms des rôles (29/10/2026) : « Agent Logistique » devient « Responsable Technique »,
« Responsable HBC » devient « Responsable Logistique ». Les rôles et le circuit ne changent pas.

Les membres des groupes sont conservés. Si le nouveau nom existe déjà (groupe renommé à la main dans
l'administration), les membres de l'ancien groupe y sont ajoutés et l'ancien groupe est supprimé."""

from django.db import migrations

RENOMMAGES = [("Agent Logistique", "Responsable Technique"), ("Responsable HBC", "Responsable Logistique")]


def renommer(apps, schema_editor, sens=1):
    Group = apps.get_model("auth", "Group")
    for ancien, nouveau in RENOMMAGES:
        if sens < 0:
            ancien, nouveau = nouveau, ancien
        vieux = Group.objects.filter(name=ancien).first()
        neuf = Group.objects.filter(name=nouveau).first()
        if vieux and not neuf:
            vieux.name = nouveau
            vieux.save(update_fields=["name"])
        elif vieux and neuf:
            neuf.user_set.add(*vieux.user_set.all())
            neuf.permissions.add(*vieux.permissions.all())
            vieux.delete()
        elif not neuf:
            Group.objects.create(name=nouveau)


def retour(apps, schema_editor):
    renommer(apps, schema_editor, sens=-1)


class Migration(migrations.Migration):
    dependencies = [("stock", "0023_numeros_serie_consommables"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(renommer, retour)]
