from django.db import transaction
from rest_framework import serializers

from .models import (Article, Chantier, Demande, Entree, Exemplaire, Fournisseur, LigneDemande, LigneEntree, Magasin,
                     etat_stock)


class ArticleListeSerializer(serializers.ModelSerializer):
    """Une ligne de la liste Articles (7 colonnes)."""

    categorie = serializers.CharField(source="categorie.nom")
    emplacement = serializers.CharField(source="emplacement.nom")
    magasin = serializers.CharField(source="emplacement.magasin.nom")
    qte_disponible = serializers.IntegerField()
    etat = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = ["id", "code", "nom", "categorie", "type", "unite",
                  "qte_disponible", "qte_minimale", "etat", "emplacement", "magasin"]

    def get_etat(self, obj):
        return etat_stock(obj.qte_disponible, obj.qte_minimale)


class ExemplaireSerializer(serializers.ModelSerializer):
    statut_libelle = serializers.CharField(source="get_statut_display")

    class Meta:
        model = Exemplaire
        fields = ["id", "numero_serie", "code_immo", "date_etalonnage",
                  "statut", "statut_libelle", "prete_a", "chantier"]


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
            "ref_fournisseur", "ref_fabricant", "marque", "modele", "exemplaires",
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
        lignes = donnees.pop("exemplaires", None)
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
        return article


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
            if a.exemplaires.exists():  # matériel suivi par n° de série
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
        from django.db.models import F
        lignes = data.pop("lignes")
        with transaction.atomic():
            entree = Entree.objects.create(**data)
            for l in lignes:
                a = l["article"]
                LigneEntree.objects.create(entree=entree, article=a, quantite=l["quantite"],
                                           prix_unitaire=l.get("prix_unitaire"),
                                           numeros_serie="\n".join(l["numeros_serie"]))
                if l["numeros_serie"]:
                    Exemplaire.objects.bulk_create([Exemplaire(article=a, numero_serie=s) for s in l["numeros_serie"]])
                else:
                    Article.objects.filter(pk=a.pk).update(qte_stock=F("qte_stock") + l["quantite"])
                if l.get("prix_unitaire") is not None:  # dernier prix d'achat connu
                    Article.objects.filter(pk=a.pk).update(prix_unitaire=l["prix_unitaire"])
        return entree


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


def article_resume(a):
    """Ce que la demande montre d'un article (tableau et panneau). `a` vient de articles_avec_quantites()."""
    return {
        "id": a.id, "code": a.code, "nom": a.nom, "categorie": a.categorie.nom, "type": a.type,
        "unite": a.unite, "emplacement": a.emplacement.nom, "magasin": a.emplacement.magasin_id,
        "modele": a.modele, "marque": a.marque, "qte_disponible": a.qte_disponible,
        "qte_minimale": a.qte_minimale, "etat": etat_stock(a.qte_disponible, a.qte_minimale),
        # Matériel suivi par n° de série : à la sortie, on coche les exemplaires remis (12/10/2026).
        "suivi_par_serie": a.type == "PRETE" and getattr(a, "nb_exemplaires", 0) > 0,
    }


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
            "lignes": {str(ls.ligne_demande_id): {"qte_bon": ls.qte_bon, "qte_livree": ls.qte_livree,
                                                  "exemplaires": [e.numero_serie for e in ls.exemplaires.all()]}
                       for ls in s.lignes.prefetch_related("exemplaires")}}


def demande_en_json(d, articles):
    """`articles` : {id: article annoté} pour les quantités disponibles actuelles."""
    from .models import departement_de
    dep = departement_de(d.demandeur) if d.demandeur else None
    return {
        "id": d.id, "numero": d.numero, "cree_le": heure_locale(d.cree_le), "statut": d.statut,
        "statut_libelle": d.get_statut_display(),
        "demandeur": nom_de(d.demandeur),
        "demandeur_departement": dep.nom if dep else "",
        "traitee_par": nom_de(d.traitee_par),
        "requisition": requisition_en_json(d),
        "magasin": d.magasin.nom, "chantier": d.chantier.nom if d.chantier_id else "", "travail": d.travail,
        "destination": d.destination, "urgent": d.urgent, "motif_refus": d.motif_refus,
        "traitee_le": heure_locale(d.traitee_le),
        "lignes": [{"id": l.id, "quantite": l.quantite, "qte_accordee": l.qte_accordee,
                    "date_retour_prevue": l.date_retour_prevue, "motif": l.motif,
                    "article": article_resume(articles[l.article_id])} for l in d.lignes.all()],
    }
