# Impression du bon de réquisition (12/10/2026)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0013_departement_informatique"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="requisition",
            name="imprimee_le",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="bon imprimé le"
            ),
        ),
        migrations.AddField(
            model_name="requisition",
            name="imprimee_par",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="requisitions_imprimees",
                to=settings.AUTH_USER_MODEL,
                verbose_name="bon imprimé par",
            ),
        ),
        migrations.CreateModel(
            name="TelechargementBon",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("le", models.DateTimeField(auto_now_add=True, verbose_name="le")),
                ("role", models.CharField(max_length=30, verbose_name="en tant que")),
                (
                    "par",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bons_telecharges",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="par",
                    ),
                ),
                (
                    "requisition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="telechargements",
                        to="stock.requisition",
                    ),
                ),
            ],
            options={
                "verbose_name": "téléchargement du bon",
                "verbose_name_plural": "téléchargements des bons",
                "ordering": ["-le", "-id"],
            },
        ),
    ]
