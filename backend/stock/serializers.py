from django.db import transaction
from rest_framework import serializers

from .models import (Article, Categorie, Chantier, Demande, Emplacement, Entree, Etat, Exemplaire, Fournisseur,
                     LigneDemande, LigneEntree, Magasin, etat_stock)


class ArticleListeSerializer(serializers.ModelSerializer):
    """Une ligne de la liste Articles (7 colonnes)."""

    categorie = serializers.CharField(source="categorie.nom")
    emplacement = serializers.CharField(source="emplacement.nom")
    magasin = serializers.CharField(source="emplacement.magasin.nom")
    qte_disponible = serializers.IntegerField()
    etat = serializers.SerializerMethodField()
    # État du produit (12/10/2026) : {"etats": {"NEUF": 3, …}, "disponible", "de_cote", "pretes", "par_serie"}
    repartition = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = ["id", "code", "nom", "categorie", "type", "unite",
                  "qte_disponible", "qte_minimale", "etat", "emplacement", "magasin", "repartition"]

    def get_etat(self, obj):
        return etat_stock(obj.qte_disponible, obj.qte_minimale)

    def get_repartition(self, obj):
        from . import etats
        reps = self.context.get("reps") or {}
        return etats.en_json(reps[obj.id] if obj.id in reps else etats.repartition(obj))


class ExemplaireSerializer(serializers.ModelSerializer):
    statut_libelle = serializers.CharField(source="get_statut_display")
    etat_libelle = serializers.CharField(source="get_etat_display")

    class Meta:
        model = Exemplaire
        fields = ["id", "numero_serie", "code_immo", "date_etalonnage",
                  "statut", "statut_libelle", "etat", "etat_libelle", "prete_a", "chantier"]


class ArticleFicheSerializer(ArticleListeSerializer):
    """Fiche complète d'un article (panneau « Détails »)."""

    type_libelle = serializers.CharField(source="get_type_display")
    fournisseur = serializers.CharField(source="fournisseur.nom", default="")
    prix_unitaire = serializers.DecimalField(max_digits=14, decimal_places=2, coerce_to_string=False)
    montant_stock = serializers.SerializerMethodField()
    exemplaires = ExemplaireSerializer(many=True, read_only=True)

    class Meta(ArticleListeSerializer.Meta):
        fields = ArticleListeSerializer.Meta.fields + [
            "type_libelle", "prix_unitaire", "montant_stock", "fournisseur",
            "ref_fournisseur", "ref_fabricant", "marque", "modele", "exemplaires", "suivi_serie",
        ]

    def get_montant_stock(self, obj):
        # Calculé : quantité disponible × prix unitaire
        return float(obj.qte_disponible * obj.prix_unitaire)


class ExemplaireModificationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    numero_serie = serializers.CharField(max_length=60, trim_whitespace=True,
                                         error_messages={"blank": "Le n° de série est obligatoire."})
    code_immo = serializers.CharField(max_length=40, allow_blank=True, required=False, trim_whitespace=True)
    date_etalonnage = serializers.DateField(allow_null=True, required=False)


def valeurs_fiche(article):
    """Valeurs de la fiche, lisibles, pour l'Historique (15/10/2026) : {libellé: texte}. Les exemplaires (n° de série)
    sont repérés par leur id : un n° corrigé apparaît « N° de série (FJK-0O1) : FJK-0O1 → FJK-001 »."""
    from . import journal
    from .exports import montant
    a = Article.objects.select_related("categorie", "emplacement__magasin", "fournisseur").get(pk=article.pk)
    v = {
        "Nom": journal.texte(a.nom), "Catégorie": journal.texte(a.categorie), "Unité": a.get_unite_display(),
        "Qté minimale": journal.texte(a.qte_minimale),
        "Emplacement": f"{a.emplacement.nom} – {a.emplacement.magasin.nom}",
        "Prix unitaire": montant(a.prix_unitaire) or journal.VIDE, "Fournisseur": journal.texte(a.fournisseur),
        "Réf. fournisseur": journal.texte(a.ref_fournisseur), "Réf. fabricant": journal.texte(a.ref_fabricant),
        "Marque": journal.texte(a.marque), "Modèle": journal.texte(a.modele),
    }
    for e in a.exemplaires.order_by("id"):
        v[f"#{e.id} N° de série"] = e.numero_serie
        v[f"#{e.id} Code immo"] = journal.texte(e.code_immo)
        v[f"#{e.id} Étalonnage"] = journal.texte(e.date_etalonnage)
    return v


class ArticleModificationSerializer(serializers.ModelSerializer):
    """Ce qui peut être modifié depuis la fiche.

    Non modifiables ici : le code (automatique), le type (fixé à la création)
    et la quantité en stock (elle change par les entrées, sorties et l'inventaire).
    """

    nom = serializers.CharField(max_length=150, trim_whitespace=True,
                                error_messages={"blank": "Le nom de l'article est obligatoire."})
    prix_unitaire = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=0,
        error_messages={"min_value": "Le prix ne peut pas être négatif.", "invalid": "Indiquez un nombre."})
    qte_minimale = serializers.IntegerField(
        min_value=0, error_messages={"min_value": "La quantité minimale ne peut pas être négative.",
                                     "invalid": "Indiquez un nombre entier."})
    exemplaires = ExemplaireModificationSerializer(many=True, required=False)

    class Meta:
        model = Article
        fields = ["nom", "categorie", "unite", "qte_minimale", "emplacement", "prix_unitaire",
                  "fournisseur", "ref_fournisseur", "ref_fabricant", "marque", "modele", "exemplaires"]

    def validate_exemplaires(self, lignes):
        article = self.instance
        ids_article = set(article.exemplaires.values_list("id", flat=True))
        # Les exemplaires de cet article sont vérifiés entre eux (dans la liste) ;
        # la base ne sert qu'à vérifier les exemplaires des AUTRES articles.
        autres = Exemplaire.objects.exclude(article=article)
        erreurs, vus_serie, vus_immo = [], {}, {}
        for i, ligne in enumerate(lignes):
            err = {}
            if ligne["id"] not in ids_article:
                err["id"] = ["Cet exemplaire n'appartient pas à cet article."]
            serie = ligne["numero_serie"]
            immo = ligne.get("code_immo", "")
            if serie in vus_serie:
                err["numero_serie"] = ["Ce n° de série est en double dans la liste."]
            elif autres.filter(numero_serie=serie).exists():
                err["numero_serie"] = ["Ce n° de série existe déjà sur un autre article."]
            if immo:
                if immo in vus_immo:
                    err["code_immo"] = ["Ce code immo est en double dans la liste."]
                elif autres.filter(code_immo=immo).exists():
                    err["code_immo"] = ["Ce code immo existe déjà sur un autre article."]
            vus_serie[serie] = i
            if immo:
                vus_immo[immo] = i
            erreurs.append(err)
        if any(erreurs):
            raise serializers.ValidationError(erreurs)
        return lignes

    def update(self, article, donnees):
        from . import journal
        lignes = donnees.pop("exemplaires", None)
        requete = self.context.get("request")
        avant = valeurs_fiche(article)
        with transaction.atomic():
            for champ, valeur in donnees.items():
                setattr(article, champ, valeur)
            article.save()
            if lignes:
                # Deux passes pour permettre d'échanger deux n° de série sans conflit.
                par_id = {e.id: e for e in article.exemplaires.all()}
                for ligne in lignes:
                    e = par_id[ligne["id"]]
                    e.numero_serie = f"__tmp__{e.id}"
                    e.code_immo = ""
                    e.save(update_fields=["numero_serie", "code_immo"])
                for ligne in lignes:
                    e = par_id[ligne["id"]]
                    e.numero_serie = ligne["numero_serie"]
                    e.code_immo = ligne.get("code_immo", "")
                    if "date_etalonnage" in ligne:
                        e.date_etalonnage = ligne["date_etalonnage"]
                    e.save()
            # Historique (15/10/2026) : une ligne « Modification » par enregistrement, avec ce qui a changé
            # (ancienne → nouvelle valeur), la personne et l'heure. Rien de changé : aucune ligne.
            article.refresh_from_db()
            detail = journal.differences(avant, valeurs_fiche(article))
            if detail:
                journal.modification("article_modifie", "Fiche article modifiée", getattr(requete, "user", None), detail,
                                     article=article, reference="Fiche article", request=requete)
        return article


class ArticleCreationSerializer(serializers.ModelSerializer):
    """Création d'un article (12/10/2026), depuis « Entrée en stock » : Agent Logistique (et administrateur).

    Le code est créé automatiquement (préfixe de la catégorie + n°). Le stock part de 0 :
    l'article est aussitôt placé sur la ligne de la livraison en cours (fenêtre « Entrée en stock »).
    """

    nom = serializers.CharField(max_length=150, trim_whitespace=True, error_messages={
        "blank": "Le nom de l'article est obligatoire.", "required": "Le nom de l'article est obligatoire."})
    categorie = serializers.PrimaryKeyRelatedField(queryset=Categorie.objects.all(), error_messages={
        "required": "Choisissez la catégorie.", "null": "Choisissez la catégorie.",
        "does_not_exist": "Catégorie inconnue.", "incorrect_type": "Choisissez la catégorie."})
    type = serializers.ChoiceField(choices=Article.Type.choices, error_messages={
        "required": "Choisissez le type d'article.", "null": "Choisissez le type d'article.",
        "invalid_choice": "Choisissez le type d'article."})
    unite = serializers.ChoiceField(choices=Article.Unite.choices, error_messages={
        "required": "Choisissez l'unité.", "null": "Choisissez l'unité.", "invalid_choice": "Choisissez l'unité."})
    emplacement = serializers.PrimaryKeyRelatedField(
        queryset=Emplacement.objects.filter(magasin__actif=True), error_messages={
            "required": "Choisissez l'emplacement.", "null": "Choisissez l'emplacement.",
            "does_not_exist": "Emplacement inconnu.", "incorrect_type": "Choisissez l'emplacement."})
    qte_minimale = serializers.IntegerField(min_value=0, required=False, default=0, error_messages={
        "min_value": "La quantité minimale ne peut pas être négative.", "invalid": "Indiquez un nombre entier."})
    prix_unitaire = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, default=0,
                                             error_messages={"min_value": "Le prix ne peut pas être négatif.",
                                                             "invalid": "Indiquez un nombre."})
    suivi_serie = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = Article
        fields = ["nom", "categorie", "type", "suivi_serie", "unite", "qte_minimale", "emplacement", "prix_unitaire",
                  "fournisseur", "ref_fournisseur", "ref_fabricant", "marque", "modele"]
        extra_kwargs = {"fournisseur": {"required": False, "allow_null": True}}

    def validate_emplacement(self, e):
        from . import etats
        if e.nom in etats.NOMS_EMPLACEMENTS_DE_COTE:
            raise serializers.ValidationError("Cet emplacement est réservé au matériel mis de côté.")
        return e

    def validate(self, data):
        from .views import sans_accents
        if data["type"] != Article.Type.PRETE:
            data["suivi_serie"] = False  # un consommable n'a pas de n° de série
        # Même nom dans le même magasin : sans doute un doublon (accents et majuscules ignorés).
        cle = " ".join(sans_accents(data["nom"]).split())
        magasin = data["emplacement"].magasin
        for code, nom in Article.objects.filter(emplacement__magasin=magasin).values_list("code", "nom"):
            if " ".join(sans_accents(nom).split()) == cle:
                raise serializers.ValidationError(
                    {"nom": [f"Cet article existe déjà à {magasin.nom} : {code} – {nom}."]})
        return data


class LigneEntreeSerializer(serializers.Serializer):
    article = serializers.PrimaryKeyRelatedField(queryset=Article.objects.all(),
                                                 error_messages={"does_not_exist": "Article introuvable.",
                                                                 "null": "Choisissez un article.",
                                                                 "incorrect_type": "Choisissez un article."})
    quantite = serializers.IntegerField(min_value=1, error_messages={
        "min_value": "La quantité doit être au moins 1.", "invalid": "Indiquez un nombre entier.",
        "null": "Indiquez la quantité.", "required": "Indiquez la quantité."})
    prix_unitaire = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False,
                                             allow_null=True, error_messages={
                                                 "min_value": "Le prix ne peut pas être négatif.",
                                                 "invalid": "Indiquez un nombre."})
    numeros_serie = serializers.ListField(child=serializers.CharField(max_length=60, trim_whitespace=True,
                                                                      allow_blank=True),
                                          required=False)
    # État du produit reçu (12/10/2026) : « Neuf » par défaut.
    etat = serializers.ChoiceField(choices=Etat.choices, required=False, default=Etat.NEUF,
                                   error_messages={"invalid_choice": "État inconnu."})


class EntreeSerializer(serializers.Serializer):
    """Réception de produits : en-tête + lignes. L'enregistrement met le stock à jour."""

    fournisseur = serializers.PrimaryKeyRelatedField(queryset=Fournisseur.objects.all(), required=False, allow_null=True)
    numero_facture = serializers.CharField(max_length=60, required=False, allow_blank=True, trim_whitespace=True)
    date_reception = serializers.DateField(error_messages={"invalid": "Date invalide.", "null": "Indiquez la date.",
                                                           "required": "Indiquez la date."})
    magasin = serializers.PrimaryKeyRelatedField(queryset=Magasin.objects.filter(actif=True), error_messages={
        "null": "Choisissez le magasin.", "required": "Choisissez le magasin.", "does_not_exist": "Magasin inconnu."})
    lignes = LigneEntreeSerializer(many=True)

    def validate(self, data):
        lignes = data["lignes"]
        if not lignes:
            raise serializers.ValidationError({"general": ["Ajoutez au moins un article."]})
        erreurs, vus, series_vues = [], set(), set()
        for ligne in lignes:
            err = {}
            a = ligne["article"]
            if a.emplacement.magasin_id != data["magasin"].id:
                err["article"] = [f"Cet article est rangé à {a.emplacement.magasin.nom}, pas dans ce magasin."]
            elif a.id in vus:
                err["article"] = ["Cet article est déjà sur une autre ligne."]
            vus.add(a.id)
            series = [s for s in ligne.get("numeros_serie", []) if s]
            ligne["numeros_serie"] = series
            if a.exemplaires.exists() or (a.type == Article.Type.PRETE and a.suivi_serie):  # suivi par n° de série
                if len(series) != ligne["quantite"]:
                    err["numeros_serie"] = [f"Indiquez {ligne['quantite']} n° de série (un par exemplaire reçu)."]
                else:
                    doublons = [s for s in series if s in series_vues or series.count(s) > 1]
                    existants = list(Exemplaire.objects.filter(numero_serie__in=series).values_list("numero_serie", flat=True))
                    if doublons:
                        err["numeros_serie"] = [f"N° de série en double : {', '.join(sorted(set(doublons)))}."]
                    elif existants:
                        err["numeros_serie"] = [f"Déjà enregistré : {', '.join(existants)}."]
                series_vues.update(series)
            elif series:
                ligne["numeros_serie"] = []  # article suivi par quantité : les n° éventuels sont ignorés
            erreurs.append(err)
        if any(erreurs):
            raise serializers.ValidationError({"lignes": erreurs})
        return data

    def create(self, data):
        from . import etats
        lignes = data.pop("lignes")
        par = data.pop("par", None)
        with transaction.atomic():
            entree = Entree.objects.create(**data)
            reference = f"Réception du {entree.date_reception:%d/%m/%Y}"
            for l in lignes:
                a = Article.objects.select_for_update().get(pk=l["article"].pk)
                etat = l.get("etat") or Etat.NEUF
                LigneEntree.objects.create(entree=entree, article=a, quantite=l["quantite"],
                                           prix_unitaire=l.get("prix_unitaire"),
                                           numeros_serie="\n".join(l["numeros_serie"]), etat=etat)
                if l["numeros_serie"]:
                    nouveaux = Exemplaire.objects.bulk_create([
                        Exemplaire(article=a, numero_serie=s, etat=etat, statut=etats.statut_pour(etat))
                        for s in l["numeros_serie"]])
                    for e in nouveaux:
                        etats.noter(a, "RECEPTION", 1, etat_apres=etat, reference=reference, par=par, exemplaire=e)
                else:
                    etats.ajouter(a, etat, l["quantite"])
                    etats.noter(a, "RECEPTION", l["quantite"], etat_apres=etat, reference=reference, par=par)
                if l.get("prix_unitaire") is not None:  # dernier prix d'achat connu
                    Article.objects.filter(pk=a.pk).update(prix_unitaire=l["prix_unitaire"])
                    if l["prix_unitaire"] != a.prix_unitaire:  # Historique (15/10/2026) : ancien → nouveau prix
                        from . import journal
                        from .exports import montant
                        journal.modification("prix_entree", "Prix mis à jour par l'entrée en stock", par,
                                             f"Prix unitaire : {montant(a.prix_unitaire) or journal.VIDE} → {montant(l['prix_unitaire'])}"
                                             " (dernier prix d'achat)", article=a, reference=reference)
        return entree


class LigneSuiviSerieSerializer(serializers.Serializer):
    numero_serie = serializers.CharField(max_length=60, trim_whitespace=True, allow_blank=True)
    code_immo = serializers.CharField(max_length=40, allow_blank=True, required=False, trim_whitespace=True)
    date_etalonnage = serializers.DateField(allow_null=True, required=False,
                                            error_messages={"invalid": "Date invalide."})
    etat = serializers.ChoiceField(choices=Etat.choices, error_messages={"invalid_choice": "État inconnu."})


class PassageSuiviSerieSerializer(serializers.Serializer):
    """« Passer au suivi par n° de série » (fiche article, 15/10/2026).

    Un article non consommable suivi par quantité devient suivi par n° de série : un n° pour chaque unité au magasin
    (autant de n° que de stock disponible). Le stock ne change pas. Refusé tant que des unités prêtées ne sont pas rendues.
    Contexte : « article » (verrouillé par l'appelant)."""

    exemplaires = LigneSuiviSerieSerializer(many=True)

    def validate(self, data):
        from . import etats
        from .rapports import prete_dehors
        article = self.context["article"]
        if article.type != Article.Type.PRETE:
            raise serializers.ValidationError({"general": ["Seul le matériel non consommable peut être suivi par n° de série."]})
        if etats.suivi_par_serie(article):
            raise serializers.ValidationError({"general": ["Cet article est déjà suivi par n° de série."]})
        dehors = prete_dehors().get(article.id, 0)
        if dehors:
            u = "unité est encore dehors" if dehors == 1 else "unités sont encore dehors"
            raise serializers.ValidationError({"general": [
                f"{dehors} {u} (prêtée{'s' if dehors > 1 else ''}, pas encore rendue{'s' if dehors > 1 else ''}) : "
                f"attendez {'son' if dehors == 1 else 'leur'} retour avant de passer au suivi par n° de série."]})
        lignes = data["exemplaires"]
        stock = article.qte_stock
        if len(lignes) != stock:
            raise serializers.ValidationError({"general": [
                f"Indiquez {stock} n° de série (un par unité au magasin) : {len(lignes)} saisi{'s' if len(lignes) > 1 else ''}."
                if stock else "Le stock est à 0 : aucun n° de série à saisir."]})
        series = [l["numero_serie"] for l in lignes]
        immos = [l.get("code_immo", "") for l in lignes]
        existants_serie = set(Exemplaire.objects.filter(numero_serie__in=[x for x in series if x])
                              .values_list("numero_serie", flat=True))
        existants_immo = set(Exemplaire.objects.filter(code_immo__in=[x for x in immos if x])
                             .values_list("code_immo", flat=True))
        erreurs = []
        for l in lignes:
            err = {}
            serie, immo = l["numero_serie"], l.get("code_immo", "")
            if not serie:
                err["numero_serie"] = ["Le n° de série est obligatoire."]
            elif series.count(serie) > 1:
                err["numero_serie"] = ["Ce n° de série est en double dans la liste."]
            elif serie in existants_serie:
                err["numero_serie"] = ["Ce n° de série existe déjà (sur un autre article)."]
            if immo:
                if immos.count(immo) > 1:
                    err["code_immo"] = ["Ce code immo est en double dans la liste."]
                elif immo in existants_immo:
                    err["code_immo"] = ["Ce code immo existe déjà (sur un autre article)."]
            erreurs.append(err)
        if any(erreurs):
            raise serializers.ValidationError({"exemplaires": erreurs})
        return data

    def save(self, par=None):
        from . import etats
        from .models import MouvementEtat, StockEtat
        article = self.context["article"]
        lignes = self.validated_data["exemplaires"]
        motif = "Passage au suivi par n° de série"
        with transaction.atomic():
            nouveaux = Exemplaire.objects.bulk_create([
                Exemplaire(article=article, numero_serie=l["numero_serie"], code_immo=l.get("code_immo", ""),
                           date_etalonnage=l.get("date_etalonnage"), etat=l["etat"], statut=etats.statut_pour(l["etat"]))
                for l in lignes])
            # Le stock est désormais compté par les exemplaires « En stock » : la quantité saisie n'a plus cours.
            Article.objects.filter(pk=article.pk).update(suivi_serie=True, qte_stock=0)
            StockEtat.objects.filter(article=article).update(quantite=0)
            # Historique : une ligne par exemplaire, sans effet sur le stock (variation 0), regroupées à l'écran.
            if nouveaux:
                for e in Exemplaire.objects.filter(article=article, numero_serie__in=[x.numero_serie for x in nouveaux]):
                    etats.noter(article, "CORRECTION", 1, etat_apres=e.etat, reference="Suivi par n° de série",
                                motif=motif, par=par, exemplaire=e, variation=0)
            else:
                MouvementEtat.objects.create(article=article, type="CORRECTION", quantite=0, variation=0,
                                             reference="Suivi par n° de série", motif=f"{motif} (stock à 0)",
                                             par=par if par and par.is_authenticated else None)
        return article


class LigneDemandeSaisieSerializer(serializers.Serializer):
    article = serializers.PrimaryKeyRelatedField(queryset=Article.objects.all(),
                                                 error_messages={"does_not_exist": "Article introuvable.",
                                                                 "null": "Choisissez un article.",
                                                                 "required": "Choisissez un article.",
                                                                 "incorrect_type": "Choisissez un article."})
    quantite = serializers.IntegerField(min_value=1, error_messages={
        "min_value": "La quantité doit être au moins 1.", "invalid": "Indiquez un nombre entier.",
        "null": "Indiquez la quantité.", "required": "Indiquez la quantité."})
    # Matériel prêté seulement (obligatoire, contrôlé dans NouvelleDemandeSerializer.validate) ; ignoré pour un consommable.
    date_retour_prevue = serializers.DateField(required=False, allow_null=True,
                                               error_messages={"invalid": "Date invalide."})
    motif = serializers.CharField(max_length=250, required=False, allow_blank=True, allow_null=True,
                                  trim_whitespace=True,
                                  error_messages={"max_length": "250 caractères au maximum."})


class NouvelleDemandeSerializer(serializers.Serializer):
    """Fenêtre « Nouvelle demande ». Le stock ne change pas : la demande attend la validation du Responsable."""

    magasin = serializers.PrimaryKeyRelatedField(queryset=Magasin.objects.filter(actif=True), error_messages={
        "null": "Choisissez le magasin.", "required": "Choisissez le magasin.",
        "does_not_exist": "Magasin inconnu.", "incorrect_type": "Choisissez le magasin."})
    # Facultatif : une demande n'est pas forcément rattachée à un chantier.
    chantier = serializers.PrimaryKeyRelatedField(queryset=Chantier.objects.filter(actif=True), required=False,
                                                  allow_null=True, error_messages={
                                                      "does_not_exist": "Ce chantier n'est plus proposé.",
                                                      "incorrect_type": "Chantier inconnu."})
    urgent = serializers.BooleanField(required=False, default=False)
    lignes = LigneDemandeSaisieSerializer(many=True)

    def to_internal_value(self, data):
        # Si d'autres champs sont en erreur (ex. quantité à 0), on signale AUSSI les erreurs de chaque ligne
        # contrôlées d'habitude plus loin (retour manquant ou passé, doublon, autre magasin) : toutes d'un coup.
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError as exc:
            erreurs = dict(exc.detail)
            lignes = data.get("lignes") if isinstance(data.get("lignes"), list) else []
            err_lignes = erreurs.get("lignes")
            par_ligne = {}
            if isinstance(err_lignes, list) and all(isinstance(e, dict) for e in err_lignes):
                par_ligne = {i: dict(e) for i, e in enumerate(err_lignes)}
            elif isinstance(err_lignes, dict):
                par_ligne = {int(k): dict(v) for k, v in err_lignes.items()}
            elif err_lignes is not None:
                raise  # ex. « Ce champ est obligatoire. » : rien à compléter ligne par ligne
            for i, msgs in self._erreurs_supplementaires(data, lignes).items():
                for champ, m in msgs.items():
                    par_ligne.setdefault(i, {}).setdefault(champ, m)
            if par_ligne:
                erreurs["lignes"] = [par_ligne.get(i, {}) for i in range(len(lignes))]
            raise serializers.ValidationError(erreurs)

    @staticmethod
    def _erreurs_supplementaires(data, lignes):
        """Contrôles de validate(), refaits sur les données brutes quand la saisie a d'autres erreurs."""
        import datetime
        from django.utils import timezone
        aujourdhui = timezone.localdate()
        ids = [l.get("article") for l in lignes if isinstance(l, dict)]
        articles = Article.objects.select_related("emplacement__magasin").in_bulk(
            [i for i in ids if isinstance(i, int)])
        try:
            magasin = int(data.get("magasin")) if data.get("magasin") not in (None, "") else None
        except (TypeError, ValueError):
            magasin = None
        res, vus = {}, set()
        for i, l in enumerate(lignes):
            if not isinstance(l, dict) or l.get("article") not in articles:
                continue
            a, err = articles[l["article"]], {}
            if magasin and a.emplacement.magasin_id != magasin:
                err["article"] = [f"Cet article est rangé à {a.emplacement.magasin.nom}, pas dans ce magasin."]
            elif a.id in vus:
                err["article"] = ["Cet article est déjà sur une autre ligne."]
            vus.add(a.id)
            if a.type == Article.Type.PRETE:
                retour = l.get("date_retour_prevue")
                if not retour:
                    err["date_retour_prevue"] = ["Indiquez la date de retour (article non consommable, à rendre)."]
                else:
                    try:
                        if datetime.date.fromisoformat(str(retour)) < aujourdhui:
                            err["date_retour_prevue"] = ["Cette date est déjà passée."]
                    except ValueError:
                        pass  # format incorrect : déjà signalé par le champ lui-même
            if err:
                res[i] = err
        return res

    def validate(self, data):
        from django.utils import timezone
        aujourdhui = timezone.localdate()
        lignes = data["lignes"]
        if not lignes:
            raise serializers.ValidationError({"general": ["Ajoutez au moins un article."]})
        erreurs, vus = [], set()
        for ligne in lignes:
            err, a = {}, ligne["article"]
            if a.emplacement.magasin_id != data["magasin"].id:
                err["article"] = [f"Cet article est rangé à {a.emplacement.magasin.nom}, pas dans ce magasin."]
            elif a.id in vus:
                err["article"] = ["Cet article est déjà sur une autre ligne."]
            vus.add(a.id)
            # Retour prévu : obligatoire pour le matériel prêté, facultatif pour un consommable.
            retour = ligne.get("date_retour_prevue")
            if a.type != Article.Type.PRETE:
                ligne["date_retour_prevue"] = retour = None  # consommable : pas de date de retour
            elif not retour:
                err["date_retour_prevue"] = ["Indiquez la date de retour (article non consommable, à rendre)."]
            elif retour and retour < aujourdhui:
                err["date_retour_prevue"] = ["Cette date est déjà passée."]
            ligne["motif"] = ligne.get("motif") or ""
            erreurs.append(err)
        if any(erreurs):
            raise serializers.ValidationError({"lignes": erreurs})
        return data

    def create(self, data):
        lignes = data.pop("lignes")
        with transaction.atomic():
            demande = Demande.objects.create(**data)
            LigneDemande.objects.bulk_create(
                [LigneDemande(demande=demande, article=l["article"], quantite=l["quantite"],
                              date_retour_prevue=l.get("date_retour_prevue"), motif=l["motif"]) for l in lignes])
        return demande


def article_resume(a, rep=None):
    """Ce que la demande montre d'un article (tableau et panneau). `a` vient de articles_avec_quantites().
    `rep` (12/10/2026) : répartition par état (etats.repartitions) ; Neuf, Bon, Moyen, Mauvais (tous disponibles)."""
    from . import etats as module_etats
    resume = {
        "id": a.id, "code": a.code, "nom": a.nom, "categorie": a.categorie.nom, "type": a.type,
        "unite": a.unite, "emplacement": a.emplacement.nom, "magasin": a.emplacement.magasin_id,
        "modele": a.modele, "marque": a.marque, "qte_disponible": a.qte_disponible,
        "qte_minimale": a.qte_minimale, "etat": etat_stock(a.qte_disponible, a.qte_minimale),
        # Matériel suivi par n° de série : à la sortie, on coche les exemplaires remis (12/10/2026).
        "suivi_par_serie": a.type == "PRETE" and (getattr(a, "nb_exemplaires", 0) > 0 or a.suivi_serie),
    }
    if rep is not None:
        resume["etats"] = module_etats.en_json(rep)["etats"]
    return resume


def heure_locale(dt):
    """Date-heure envoyée à l'écran à l'heure de Madagascar (« 2026-10-12T00:00:10+03:00 »), jamais en UTC :
    sinon une demande faite entre minuit et 3 h s'affichait avec la date de la veille (corrigé le 12/10/2026)."""
    from django.utils import timezone
    return timezone.localtime(dt).isoformat() if dt else None


def nom_de(user):
    return (user.get_full_name() or user.username) if user else ""


def requisition_en_json(d):
    """La réquisition matière créée à la validation (ou None)."""
    try:
        r = d.requisition
    except Exception:  # pas encore de réquisition (RelatedObjectDoesNotExist)
        return None
    return {"numero": r.numero, "statut": r.statut, "statut_libelle": r.get_statut_display(),
            "visa_agent": nom_de(r.visa_agent), "visa_agent_le": heure_locale(r.visa_agent_le),
            "visa_responsable": nom_de(r.visa_responsable), "visa_responsable_le": heure_locale(r.visa_responsable_le),
            "motif_refus": r.motif_refus, "email_envoye_le": heure_locale(r.email_envoye_le), "email_etat": r.email_etat,
            # Signatures dessinées : l'image se lit à part (/api/requisitions/<demande>/signature/agent|responsable/)
            "signature_agent": bool(r.signature_agent), "signature_responsable": bool(r.signature_responsable),
            # Impression du bon (12/10/2026) : premier téléchargement du PDF par l'Agent Logistique
            "imprimee_le": heure_locale(r.imprimee_le), "imprimee_par": nom_de(r.imprimee_par),
            # Sortie confirmée par l'Agent Logistique (12/10/2026) : matériel remis, stock diminué
            "sortie": sortie_en_json(r)}


def sortie_en_json(r):
    """La sortie confirmée (ou None) ; `lignes` : {id de la ligne de demande: qté livrée, n° de série remis}."""
    try:
        s = r.sortie
    except Exception:  # pas encore de sortie
        return None
    return {"date_remise": s.date_remise.isoformat(), "magasinier": s.magasinier, "observation": s.observation,
            "confirmee_le": heure_locale(s.confirmee_le), "confirmee_par": nom_de(s.confirmee_par),
            "lignes": {str(ls.ligne_demande_id): {"qte_bon": ls.qte_bon, "qte_livree": ls.qte_livree, "etats": ls.etats,
                                                  "exemplaires": [e.numero_serie for e in ls.exemplaires.all()]}
                       for ls in s.lignes.prefetch_related("exemplaires")}}


def demande_en_json(d, articles, reps=None):
    """`articles` : {id: article annoté} pour les quantités disponibles actuelles ; `reps` : répartitions par état."""
    reps = reps or {}
    from .models import departement_de
    dep = departement_de(d.demandeur) if d.demandeur else None
    return {
        "id": d.id, "numero": d.numero, "cree_le": heure_locale(d.cree_le), "statut": d.statut,
        "statut_libelle": d.get_statut_display(),
        "demandeur": nom_de(d.demandeur),
        "demandeur_departement": dep.nom if dep else "",
        "traitee_par": nom_de(d.traitee_par),
        "requisition": requisition_en_json(d),
        "numero_requisition": d.numero_requisition,  # attribué au clic sur « Valider » (12/10/2026)
        "magasin": d.magasin.nom, "chantier": d.chantier.nom if d.chantier_id else "", "travail": d.travail,
        "destination": d.destination, "urgent": d.urgent, "motif_refus": d.motif_refus,
        "traitee_le": heure_locale(d.traitee_le),
        "lignes": [{"id": l.id, "quantite": l.quantite, "qte_accordee": l.qte_accordee,
                    "date_retour_prevue": l.date_retour_prevue, "motif": l.motif,
                    "article": article_resume(articles[l.article_id], reps.get(l.article_id))} for l in d.lignes.all()],
    }
