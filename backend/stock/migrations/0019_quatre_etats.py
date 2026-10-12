"""États du produit simplifiés (12/10/2026, après-midi) : Neuf · Bon · Moyen · Mauvais, tous disponibles.

Anciennes valeurs : Usagé → Moyen ; À réparer et Hors service → Mauvais, remis dans le stock disponible
(décision de l'utilisateur). Ce qui a déjà été mis au rebut reste hors stock. L'écran « Matériel à réparer » est retiré.
"""

from django.db import migrations, models


CORRESPONDANCE = {"USAGE": "MOYEN", "A_REPARER": "MAUVAIS", "HORS_SERVICE": "MAUVAIS"}
ANCIENS_DE_COTE = {"A_REPARER": "À réparer", "HORS_SERVICE": "Hors service"}
MOTIF = "États simplifiés (Neuf · Bon · Moyen · Mauvais) : « {} » devient « Mauvais », remis en stock."


def nouveau(etat):
    return CORRESPONDANCE.get(etat, etat)


def convertir(apps, schema_editor):
    Article = apps.get_model("stock", "Article")
    StockEtat = apps.get_model("stock", "StockEtat")
    Exemplaire = apps.get_model("stock", "Exemplaire")
    LigneEntree = apps.get_model("stock", "LigneEntree")
    LigneSortie = apps.get_model("stock", "LigneSortie")
    LigneRetour = apps.get_model("stock", "LigneRetour")
    MouvementEtat = apps.get_model("stock", "MouvementEtat")
    Emplacement = apps.get_model("stock", "Emplacement")

    # 1. Historique et lignes déjà enregistrées : simple changement de nom d'état.
    for ancien, neuf in CORRESPONDANCE.items():
        MouvementEtat.objects.filter(etat_avant=ancien).update(etat_avant=neuf)
        MouvementEtat.objects.filter(etat_apres=ancien).update(etat_apres=neuf)
        LigneEntree.objects.filter(etat=ancien).update(etat=neuf)

    def remap_quantites(d):
        r = {}
        for k, v in (d or {}).items():
            r[nouveau(k)] = r.get(nouveau(k), 0) + v
        return r

    for ls in LigneSortie.objects.exclude(etats={}):
        r = remap_quantites(ls.etats)
        if r != ls.etats:
            ls.etats = r
            ls.save(update_fields=["etats"])
    for lr in LigneRetour.objects.exclude(etats={}):
        d = lr.etats or {}
        if all(isinstance(v, str) for v in d.values()):  # n° de série : {"<id exemplaire>": "BON"}
            r = {k: nouveau(v) for k, v in d.items()}
        else:
            r = remap_quantites(d)
        if r != d:
            lr.etats = r
            lr.save(update_fields=["etats"])

    # 2. Stock suivi par quantité : Usagé → Moyen ; À réparer / Hors service → Mauvais, remis dans le disponible.
    for article_id in set(StockEtat.objects.filter(etat__in=CORRESPONDANCE).values_list("article_id", flat=True)):
        lignes = {s.etat: s for s in StockEtat.objects.filter(article_id=article_id)}
        total = {}
        remis = {}
        for etat, s in lignes.items():
            total[nouveau(etat)] = total.get(nouveau(etat), 0) + s.quantite
            if etat in ANCIENS_DE_COTE and s.quantite:
                remis[etat] = s.quantite
        StockEtat.objects.filter(article_id=article_id, etat__in=CORRESPONDANCE).delete()
        for etat, q in total.items():
            StockEtat.objects.update_or_create(article_id=article_id, etat=etat, defaults={"quantite": q})
        if remis:
            a = Article.objects.get(pk=article_id)
            a.qte_stock += sum(remis.values())
            a.save(update_fields=["qte_stock"])
            for etat, q in remis.items():
                MouvementEtat.objects.create(article_id=article_id, type="CORRECTION", quantite=q, etat_avant="",
                                             etat_apres="MAUVAIS", motif=MOTIF.format(ANCIENS_DE_COTE[etat]))

    # 3. Exemplaires (n° de série) : état renommé ; ceux mis de côté reviennent « En stock » en « Mauvais ».
    for ancien, neuf in CORRESPONDANCE.items():
        Exemplaire.objects.filter(etat=ancien).update(etat=neuf)
    for e in Exemplaire.objects.filter(statut__in=["REPARATION", "HORS_SERVICE"]):
        libelle = "À réparer" if e.statut == "REPARATION" else "Hors service"
        e.statut, e.etat = "EN_STOCK", "MAUVAIS"
        e.save(update_fields=["statut", "etat"])
        MouvementEtat.objects.create(article_id=e.article_id, exemplaire_id=e.id, type="CORRECTION", quantite=1,
                                     etat_avant="", etat_apres="MAUVAIS", motif=MOTIF.format(libelle))

    # 4. Emplacements « Atelier – À réparer » et « Rebut » : supprimés s'ils sont vides.
    for emp in Emplacement.objects.filter(nom__in=["Atelier – À réparer", "Rebut"]):
        if not Article.objects.filter(emplacement=emp).exists():
            emp.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0018_article_suivi_serie'),
    ]

    operations = [
        migrations.RunPython(convertir, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='exemplaire',
            name='etat',
            field=models.CharField(choices=[('NEUF', 'Neuf'), ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('MAUVAIS', 'Mauvais')], default='NEUF', max_length=12, verbose_name='état'),
        ),
        migrations.AlterField(
            model_name='exemplaire',
            name='statut',
            field=models.CharField(choices=[('EN_STOCK', 'En stock'), ('PRETE', 'Prêté'), ('REBUT', 'Mis au rebut')], default='EN_STOCK', max_length=12),
        ),
        migrations.AlterField(
            model_name='ligneentree',
            name='etat',
            field=models.CharField(choices=[('NEUF', 'Neuf'), ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('MAUVAIS', 'Mauvais')], default='NEUF', max_length=12, verbose_name='état à la réception'),
        ),
        migrations.AlterField(
            model_name='mouvementetat',
            name='etat_apres',
            field=models.CharField(blank=True, choices=[('NEUF', 'Neuf'), ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('MAUVAIS', 'Mauvais')], max_length=12, verbose_name='état après'),
        ),
        migrations.AlterField(
            model_name='mouvementetat',
            name='etat_avant',
            field=models.CharField(blank=True, choices=[('NEUF', 'Neuf'), ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('MAUVAIS', 'Mauvais')], max_length=12, verbose_name='état avant'),
        ),
        migrations.AlterField(
            model_name='stocketat',
            name='etat',
            field=models.CharField(choices=[('NEUF', 'Neuf'), ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('MAUVAIS', 'Mauvais')], max_length=12, verbose_name='état'),
        ),
    ]
