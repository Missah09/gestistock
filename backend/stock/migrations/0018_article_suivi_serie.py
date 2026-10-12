"""Création d'un article dans l'application (12/10/2026) : « suivi par n° de série » choisi à la création."""
from django.db import migrations, models


def marquer_existants(apps, schema_editor):
    # Le matériel prêté qui a déjà des exemplaires est, par définition, suivi par n° de série.
    Article = apps.get_model("stock", "Article")
    Article.objects.filter(type="PRETE", exemplaires__isnull=False).distinct().update(suivi_serie=True)


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0017_numero_attribue_et_impression"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="suivi_serie",
            field=models.BooleanField(default=False, help_text="Matériel prêté seulement : chaque exemplaire reçu porte un n° de série.",
                                      verbose_name="suivi par n° de série"),
        ),
        migrations.RunPython(marquer_existants, migrations.RunPython.noop),
    ]
