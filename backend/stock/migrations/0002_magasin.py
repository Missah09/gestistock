"""Les magasins deviennent une vraie table (avec le type Magasin / Chantier).

Les noms de magasins déjà saisis sur les emplacements sont repris tels quels.
"""
import django.db.models.deletion
from django.db import migrations, models


def reprendre_magasins(apps, schema_editor):
    Magasin = apps.get_model("stock", "Magasin")
    Emplacement = apps.get_model("stock", "Emplacement")
    for e in Emplacement.objects.all():
        e.magasin_ref = Magasin.objects.get_or_create(nom=e.magasin or "Ankorondrano")[0]
        e.save(update_fields=["magasin_ref"])


class Migration(migrations.Migration):
    dependencies = [("stock", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Magasin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nom", models.CharField(max_length=80, unique=True)),
                ("type", models.CharField(choices=[("MAGASIN", "Magasin"), ("CHANTIER", "Chantier")], default="MAGASIN", max_length=10)),
                ("actif", models.BooleanField(default=True, help_text="Décocher quand le chantier est terminé")),
            ],
            options={"ordering": ["type", "nom"]},
        ),
        migrations.AddField(
            model_name="emplacement",
            name="magasin_ref",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to="stock.magasin"),
        ),
        migrations.RunPython(reprendre_magasins, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(name="emplacement", unique_together=set()),
        migrations.RemoveField(model_name="emplacement", name="magasin"),
        migrations.RenameField(model_name="emplacement", old_name="magasin_ref", new_name="magasin"),
        migrations.AlterField(
            model_name="emplacement",
            name="magasin",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="emplacements", to="stock.magasin"),
        ),
        migrations.AlterModelOptions(name="emplacement", options={"ordering": ["magasin__nom", "nom"]}),
        migrations.AlterUniqueTogether(name="emplacement", unique_together={("magasin", "nom")}),
    ]
