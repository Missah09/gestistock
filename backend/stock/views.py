import unicodedata

from django.db.models import Case, Count, F, IntegerField, Q, When
from rest_framework import mixins, viewsets
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .permissions import EstAgentLogistique, LectureOuAgentLogistique
from .models import Article, Categorie, Chantier, Demande, Emplacement, Exemplaire, Fournisseur, Magasin
from .serializers import (ArticleFicheSerializer, ArticleListeSerializer, ArticleModificationSerializer,
                          EntreeSerializer, NouvelleDemandeSerializer, article_resume, demande_en_json)


def articles_avec_quantites():
    """Articles + quantité disponible calculée.

    - Consommable : la quantité saisie (qte_stock).
    - Matériel prêté suivi par n° de série : le nombre d'exemplaires « En stock ».
    - Matériel prêté sans n° de série (pelles, casques…) : la quantité saisie, comme un consommable.
    """
    return (
        Article.objects.select_related("categorie", "emplacement__magasin")
        .annotate(
            nb_exemplaires=Count("exemplaires"),
            nb_en_stock=Count("exemplaires", filter=Q(exemplaires__statut=Exemplaire.Statut.EN_STOCK)),
        )
        .annotate(qte_disponible=Case(
            # Matériel suivi par n° de série : on compte les exemplaires « En stock ».
            When(type=Article.Type.PRETE, nb_exemplaires__gt=0, then=F("nb_en_stock")),
            default=F("qte_stock"),
            output_field=IntegerField(),
        ))
        .order_by("code")
    )


def sans_accents(texte):
    """« Jarretière » → « jarretiere » : recherche sans tenir compte des accents ni des majuscules."""
    t = unicodedata.normalize("NFD", str(texte or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def articles_trouves(q):
    """Articles dont le nom, le code, un n° de série ou un code immo contient TOUS les mots tapés,
    sans tenir compte des accents ni des majuscules (« tete optique » trouve « ODF (Tête optique) »).
    Fait en Python : quelques centaines d'articles, et aucun réglage spécial de PostgreSQL n'est nécessaire."""
    mots = sans_accents(q).split()
    textes = {a["id"]: f'{a["code"]} {a["nom"]}' for a in Article.objects.values("id", "code", "nom")}
    for e in Exemplaire.objects.values("article_id", "numero_serie", "code_immo"):
        if e["article_id"] in textes:
            textes[e["article_id"]] += f' {e["numero_serie"] or ""} {e["code_immo"] or ""}'
    return [i for i, t in textes.items() if all(m in sans_accents(t) for m in mots)]


class ArticleViewSet(mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Liste des articles.

    Paramètres possibles :
      q          – recherche : nom, code article, n° de série ou code immo
      categorie  – id de la catégorie
      magasin    – id du magasin
      sous_seuil – « 1 » pour ne garder que les articles sous le minimum ou épuisés
    """

    http_method_names = ["get", "patch", "head", "options"]
    permission_classes = [LectureOuAgentLogistique]

    def get_serializer_class(self):
        if self.action == "partial_update":
            return ArticleModificationSerializer
        return ArticleFicheSerializer if self.action == "retrieve" else ArticleListeSerializer

    def update(self, request, *args, **kwargs):
        # Enregistre, puis renvoie la fiche complète à jour.
        super().update(request, *args, **kwargs)
        fiche = self.get_queryset().get(pk=kwargs["pk"])
        return Response(ArticleFicheSerializer(fiche).data)

    def get_queryset(self):
        qs = articles_avec_quantites()
        if self.action in ("retrieve", "partial_update"):
            return qs.select_related("fournisseur").prefetch_related("exemplaires")
        p = self.request.query_params

        q = p.get("q", "").strip()
        if q:
            qs = qs.filter(id__in=articles_trouves(q))

        if p.get("categorie"):
            qs = qs.filter(categorie_id=p["categorie"])
        if p.get("magasin"):
            qs = qs.filter(emplacement__magasin_id=p["magasin"])
        if p.get("sous_seuil") == "1":
            # Sous le minimum, ou épuisé (même si aucun minimum n'est encore fixé).
            qs = qs.filter(Q(qte_disponible__lt=F("qte_minimale")) | Q(qte_disponible__lte=0))
        return qs


@api_view(["GET"])
def filtres(request):
    """Valeurs proposées dans les listes déroulantes de la page Articles."""
    return Response({
        "categories": list(Categorie.objects.values("id", "nom")),
        # Magasins permanents puis chantiers en cours (les chantiers terminés ne sont plus proposés).
        "magasins": [{"id": m.id, "nom": m.nom, "type": m.type} for m in Magasin.objects.filter(actif=True)],
    })


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def choix(request):
    """Listes proposées dans le formulaire « Modifier »."""
    return Response({
        "categories": list(Categorie.objects.values("id", "nom")),
        "emplacements": [{"id": e.id, "nom": e.nom, "magasin": e.magasin.nom}
                         for e in Emplacement.objects.select_related("magasin").filter(magasin__actif=True)],
        "fournisseurs": list(Fournisseur.objects.values("id", "nom")),
        "unites": [{"valeur": v, "libelle": l} for v, l in Article.Unite.choices],
        "magasins": [{"id": m.id, "nom": m.nom, "type": m.type} for m in Magasin.objects.filter(actif=True)],
        # Pour la fenêtre « Enregistrer des produits »
        "articles": [{"id": a.id, "code": a.code, "nom": a.nom, "type": a.type, "unite": a.unite, "magasin": a.emplacement.magasin_id,
                      "prix_unitaire": float(a.prix_unitaire), "suivi_serie": a.nb_ex > 0}
                     for a in Article.objects.select_related("emplacement").annotate(nb_ex=Count("exemplaires"))
                     .order_by("nom")],
    })


@api_view(["POST"])
@permission_classes([EstAgentLogistique])
def enregistrer_entree(request):
    """Enregistre une réception de produits et met le stock à jour."""
    s = EntreeSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    entree = s.save()
    nb = entree.lignes.count()
    return Response({"id": entree.id, "message": f"Réception enregistrée : {nb} article{'s' if nb > 1 else ''}, stock mis à jour."},
                    status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------- Demandes

# Onglets « Mes demandes » et « Demandes à valider ». Une réquisition refusée par le Responsable HBC
# range la demande dans « Refusées » (la demande elle-même reste « validée » par la Logistique).
ONGLETS = {"attente": Q(statut=Demande.Statut.EN_ATTENTE),
           "validees": Q(statut=Demande.Statut.VALIDEE) & ~Q(requisition__statut="REFUSEE"),
           "refusees": Q(statut=Demande.Statut.REFUSEE) | Q(requisition__statut="REFUSEE"),
           "toutes": None}
PAR_PAGE_DEMANDES = 10


def mes_demandes(request):
    """« Mes demandes » : chaque compte ne voit que ses propres demandes.
    (L'Agent Logistique voit toutes les demandes dans son écran « Demandes à valider » : views_validation.py.)"""
    return demandes_completes().filter(demandeur=request.user)


def demandes_completes():
    """Demandes avec tout ce que le tableau et le panneau affichent (sans requêtes en plus)."""
    return (Demande.objects.select_related("magasin", "demandeur__profil__departement", "chantier", "traitee_par",
                                           "requisition__visa_agent", "requisition__visa_responsable",
                                           "requisition__imprimee_par", "requisition__sortie__confirmee_par")
            .prefetch_related("lignes"))


def en_json(demandes):
    ids = {l.article_id for d in demandes for l in d.lignes.all()}
    articles = {a.id: a for a in articles_avec_quantites().filter(id__in=ids)}
    return [demande_en_json(d, articles) for d in demandes]


@api_view(["GET", "POST"])
def demandes(request):
    """GET : liste par onglet (?onglet=attente|validees|refusees|toutes, ?page=)
    POST : nouvelle demande (fenêtre « Nouvelle demande »)."""
    if request.method == "POST":
        s = NouvelleDemandeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.save(demandeur=request.user)
        nb = d.lignes.count()
        return Response({"id": d.id, "numero": d.numero,
                         "message": f"Demande {d.numero} envoyée à la Logistique ({nb} article{'s' if nb > 1 else ''})."},
                        status=status.HTTP_201_CREATED)

    qs = mes_demandes(request)
    compteurs = {cle: (qs.filter(f).count() if f is not None else qs.count()) for cle, f in ONGLETS.items()}
    onglet = request.query_params.get("onglet", "attente")
    filtre = ONGLETS.get(onglet, ONGLETS["attente"])
    if filtre is not None:
        qs = qs.filter(filtre)
    total = qs.count()
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    morceau = list(qs[(page - 1) * PAR_PAGE_DEMANDES: page * PAR_PAGE_DEMANDES])
    return Response({"count": total, "par_page": PAR_PAGE_DEMANDES, "compteurs": compteurs, "results": en_json(morceau)})


@api_view(["GET"])
def detail_demande(request, pk):
    """Une demande (pour garder le panneau à jour même si elle a changé d'onglet)."""
    d = mes_demandes(request).filter(pk=pk).first()
    if d is None:
        return Response({"general": ["Demande introuvable."]}, status=status.HTTP_404_NOT_FOUND)
    return Response(en_json([d])[0])


@api_view(["POST"])
def annuler_demande(request, pk):
    """« Annuler ma demande » : possible tant qu'elle est en attente."""
    d = mes_demandes(request).filter(pk=pk).first()
    if d is None:
        return Response({"general": ["Demande introuvable."]}, status=status.HTTP_404_NOT_FOUND)
    if d.statut != Demande.Statut.EN_ATTENTE:
        return Response({"general": [f"Cette demande est {d.get_statut_display().lower()} : seule une demande en attente peut être annulée."]},
                        status=status.HTTP_400_BAD_REQUEST)
    d.statut = Demande.Statut.ANNULEE
    d.save(update_fields=["statut"])
    return Response({"message": f"Demande {d.numero} annulée."})


@api_view(["GET"])
def choix_demande(request):
    """Listes de la fenêtre « Nouvelle demande » : magasins et articles avec leur stock actuel."""
    from django.utils import timezone
    return Response({
        # Heure du serveur : la fenêtre affiche la date et l'heure de la demande d'après elle (pas l'horloge du PC).
        "maintenant": timezone.localtime().isoformat(),
        "magasins": [{"id": m.id, "nom": m.nom, "type": m.type} for m in Magasin.objects.filter(actif=True)],
        # Chantiers en cours (ajoutés dans l'administration ; les chantiers terminés ne sont plus proposés).
        "chantiers": list(Chantier.objects.filter(actif=True).values("id", "nom")),
        "articles": [article_resume(a) for a in articles_avec_quantites().order_by("nom")],
    })
