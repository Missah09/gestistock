from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Écran « Sorties » (12/10/2026) : confirmation de la remise du matériel, le stock diminue."""

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("stock", "0014_impression_du_bon"),
    ]

    operations = [
        migrations.CreateModel(
            name="Sortie",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date_remise", models.DateField(verbose_name="matériel remis le")),
                ("magasinier", models.CharField(blank=True, help_text="Nom du magasinier qui a signé le bon", max_length=120, verbose_name="magasinier")),
                ("observation", models.CharField(blank=True, max_length=250)),
                ("confirmee_le", models.DateTimeField(auto_now_add=True, verbose_name="sortie confirmée le")),
                ("confirmee_par", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sorties_confirmees", to=settings.AUTH_USER_MODEL, verbose_name="sortie confirmée par")),
                ("requisition", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="sortie", to="stock.requisition", verbose_name="réquisition matière")),
            ],
            options={"verbose_name": "sortie (matériel remis)", "verbose_name_plural": "sorties (matériel remis)", "ordering": ["-confirmee_le", "-id"]},
        ),
        migrations.CreateModel(
            name="LigneSortie",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("qte_bon", models.PositiveIntegerField(verbose_name="qté sur le bon")),
                ("qte_livree", models.PositiveIntegerField(verbose_name="qté livrée")),
                ("article", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lignes_sortie", to="stock.article")),
                ("exemplaires", models.ManyToManyField(blank=True, related_name="sorties", to="stock.exemplaire", verbose_name="exemplaires remis")),
                ("ligne_demande", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="ligne_sortie", to="stock.lignedemande")),
                ("sortie", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lignes", to="stock.sortie")),
            ],
            options={"verbose_name": "ligne de sortie", "verbose_name_plural": "lignes de sortie", "ordering": ["id"]},
        ),
    ]
