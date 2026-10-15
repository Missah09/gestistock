"""Écran « Historique » (15/10/2026) : chaque mouvement porte sa variation du stock disponible (+ entrée, − sortie).

Les mouvements déjà enregistrés reçoivent la leur d'après leur type : réception, retour, réparation et correction
ont augmenté le stock disponible ; une sortie l'a diminué ; une mise au rebut (ancien écran) ne le changeait pas
(le matériel était déjà « à réparer », hors du disponible)."""
from django.db import migrations, models

SENS = {"RECEPTION": 1, "RETOUR": 1, "REPARATION": 1, "CORRECTION": 1, "SORTIE": -1, "REBUT": 0}


def remplir(apps, schema_editor):
    MouvementEtat = apps.get_model("stock", "MouvementEtat")
    for type_, sens in SENS.items():
        for m in MouvementEtat.objects.filter(type=type_, variation__isnull=True).only("id", "quantite"):
            MouvementEtat.objects.filter(pk=m.pk).update(variation=sens * m.quantite)


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0019_quatre_etats"),
    ]

    operations = [
        migrations.AddField(
            model_name="mouvementetat",
            name="variation",
            field=models.IntegerField(blank=True, null=True, verbose_name="variation du stock"),
        ),
        migrations.RunPython(remplir, migrations.RunPython.noop),
    ]
