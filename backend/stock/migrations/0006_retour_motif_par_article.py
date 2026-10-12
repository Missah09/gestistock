"""Retour prévu et motif par article ; plus de « date souhaitée » (la date de la demande est celle de l'envoi)."""
from django.db import migrations, models


def reprendre_retours(apps, schema_editor):
    # L'ancienne date de retour (une par demande) est recopiée sur ses articles prêtés.
    Demande = apps.get_model("stock", "Demande")
    for d in Demande.objects.exclude(date_retour_prevue=None):
        d.lignes.filter(article__type="PRETE").update(date_retour_prevue=d.date_retour_prevue)


def remettre_retours(apps, schema_editor):
    Demande = apps.get_model("stock", "Demande")
    for d in Demande.objects.all():
        l = d.lignes.exclude(date_retour_prevue=None).order_by("date_retour_prevue").last()
        if l:
            d.date_retour_prevue = l.date_retour_prevue
            d.save(update_fields=["date_retour_prevue"])


class Migration(migrations.Migration):

    dependencies = [("stock", "0005_chantiers")]

    operations = [
        migrations.AddField(
            model_name="lignedemande", name="date_retour_prevue",
            field=models.DateField(blank=True, null=True, verbose_name="retour prévu",
                                   help_text="Matériel prêté seulement (obligatoire) ; vide pour un consommable"),
        ),
        migrations.AddField(
            model_name="lignedemande", name="motif",
            field=models.CharField(blank=True, max_length=250, help_text="Pourquoi cet article est demandé (facultatif)"),
        ),
        migrations.RunPython(reprendre_retours, remettre_retours),
        migrations.RemoveField(model_name="demande", name="date_retour_prevue"),
        migrations.RemoveField(model_name="demande", name="date_souhaitee"),
        migrations.AlterField(
            model_name="demande", name="travail",
            field=models.CharField(blank=True, max_length=150, verbose_name="travail (ancien champ)"),
        ),
    ]
