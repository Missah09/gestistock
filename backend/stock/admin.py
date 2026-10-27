from django.contrib import admin

from .models import Article, Categorie, Emplacement, Entree, Exemplaire, Fournisseur, LigneEntree, Magasin


class ExemplaireInline(admin.TabularInline):
    model = Exemplaire
    extra = 0


class StockEtatInline(admin.TabularInline):
    """Répartition par état (12/10/2026) : mise à jour par GestiStock (entrées en stock, sorties, retours)."""
    from .models import StockEtat
    model = StockEtat
    extra = 0
    can_delete = False
    fields = ("etat", "quantite")
    readonly_fields = fields
    verbose_name_plural = "Stock par état (Neuf, Bon, Moyen, Mauvais)"

    def has_add_permission(self, request, obj=None):
        return False


def article_supprimable(article):
    """Article de test ou créé par erreur (27/10/2026) : il peut avoir été reçu (Entrée en stock), mais jamais demandé,
    sorti ni rendu. L'administrateur peut alors le supprimer avec ses lignes de réception et son historique ;
    une réception qui ne contenait que lui est supprimée aussi. Les autres articles de la réception ne changent pas."""
    return not (article.lignes_demande.exists() or article.lignes_sortie.exists() or article.lignes_retour.exists())


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "categorie", "type", "qte_stock", "qte_minimale", "emplacement")
    list_filter = ("type", "categorie", "emplacement__magasin")
    search_fields = ("code", "nom", "exemplaires__numero_serie", "exemplaires__code_immo")
    readonly_fields = ("code",)
    inlines = [StockEtatInline, ExemplaireInline]

    # Corrections faites ici (15/10/2026) : notées dans l'Historique, pour que le « stock avant → après » reste juste.
    def save_model(self, request, obj, form, change):
        from . import etats
        avant = Article.objects.filter(pk=obj.pk).values_list("qte_stock", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        if avant is not None and avant != obj.qte_stock and not etats.suivi_par_serie(obj):
            ecart = obj.qte_stock - avant
            etats.noter(obj, "CORRECTION", abs(ecart), variation=ecart, par=request.user,
                        motif=f"Quantité corrigée dans l'administration ({avant} → {obj.qte_stock})")

    def save_formset(self, request, form, formset, change):
        if formset.model is not Exemplaire:
            return super().save_formset(request, form, formset, change)
        avant = dict(Exemplaire.objects.filter(article=form.instance).values_list("id", "statut"))
        supprimes = [o for o in formset.deleted_forms if o.instance.pk]
        super().save_formset(request, form, formset, change)
        for f in supprimes:
            noter_exemplaire_admin(request, f.instance, avant.get(f.instance.pk), None)
        for f in formset.forms:
            e = f.instance
            if e.pk and f not in formset.deleted_forms and f.has_changed():
                noter_exemplaire_admin(request, e, avant.get(e.pk), e.statut)

    # Supprimer un article jamais utilisé (26/10/2026), ou seulement reçu (27/10/2026) : l'historique des mouvements et
    # les réceptions ne se suppriment jamais à la main, sauf ici, pour un administrateur (voir article_supprimable).
    # Un article demandé, sorti ou rendu reste bloqué : ces lignes sont listées comme protégées.
    def get_deleted_objects(self, objs, request):
        a_supprimer, compte, permissions, proteges = super().get_deleted_objects(objs, request)
        if request.user.is_superuser and all(article_supprimable(a) for a in objs):
            # Ce qui part avec l'article est montré dans « seront aussi supprimés », pour être vu avant de confirmer.
            articles = list(objs)
            permissions, proteges = set(), []
            lignes = list(LigneEntree.objects.filter(article__in=articles).select_related("entree__magasin", "article"))
            if lignes:
                nom = str(LigneEntree._meta.verbose_name)
                a_supprimer = [*a_supprimer, [f"{nom.capitalize()} : {l} — {l.entree}" for l in lignes]]
                compte = {**compte, str(LigneEntree._meta.verbose_name_plural): len(lignes)}
                videes = [e for e in Entree.objects.filter(lignes__in=lignes).distinct()
                          if not e.lignes.exclude(article__in=articles).exists()]
                if videes:
                    a_supprimer = [*a_supprimer, [f"Réception entière (ne contenait que cet article) : {e}" for e in videes]]
                    compte = {**compte, str(Entree._meta.verbose_name_plural): len(videes)}
            nom = str(MouvementEtat._meta.verbose_name)
            mouvements = list(MouvementEtat.objects.filter(article__in=articles))
            if mouvements:
                a_supprimer = [*a_supprimer, [f"{nom.capitalize()} : {m} ({m.motif or m.get_type_display()})"
                                              for m in mouvements]]
                compte = {**compte, str(MouvementEtat._meta.verbose_name_plural): len(mouvements)}
        elif request.user.is_superuser:
            # L'article a servi (27/10/2026) : la vraie raison du blocage est ce qui l'utilise (demandes, sorties,
            # retours). Sans cela, Django affichait « votre compte n'est pas autorisé à supprimer… mouvement »
            # et masquait la liste des objets protégés. On retire aussi de cette liste l'historique de l'article lui-même.
            nom = str(MouvementEtat._meta.verbose_name)
            permissions = set()
            proteges = [p for p in proteges if not str(p).lower().startswith(nom.lower())] or proteges
        return a_supprimer, compte, permissions, proteges

    def delete_model(self, request, obj):
        from django.db import transaction

        from . import journal
        with transaction.atomic():
            if request.user.is_superuser and article_supprimable(obj):
                lignes = list(obj.lignes_entree.select_related("entree__magasin"))
                entrees = {l.entree for l in lignes}
                MouvementEtat.objects.filter(article=obj).delete()
                for l in lignes:
                    journal.modification("admin_suppr", "Réception supprimée avec l'article", request.user,
                                         f"{l} — {l.entree} (article de test ou créé par erreur)",
                                         objet=f"{obj.code} – {obj.nom}", reference="Administration", request=request)
                    l.delete()
                for e in entrees:
                    if not e.lignes.exists():
                        e.delete()
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in list(queryset):
            self.delete_model(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["qte_stock"].label = "Quantité en stock"
        form.base_fields["qte_stock"].help_text = (
            "Quantité disponible (Neuf + Bon + Moyen + Mauvais). Pour le matériel avec n° de série, laissez 0 : la quantité se "
            "calcule à partir des exemplaires « En stock ». Si vous la corrigez ici, l'écart est compté en « Neuf » "
            "(consommable) ou « Bon » (matériel prêté)."
        )
        return form


def noter_exemplaire_admin(request, e, statut_avant, statut_apres):
    """Exemplaire ajouté, supprimé, ou dont le statut change dans l'administration : +1 / −1 dans l'Historique."""
    from . import etats
    en_stock = Exemplaire.Statut.EN_STOCK
    variation = int(statut_apres == en_stock) - int(statut_avant == en_stock)
    if not variation:
        return
    quoi = ("ajouté" if statut_avant is None else "supprimé" if statut_apres is None
            else f"passé de « {Exemplaire.Statut(statut_avant).label} » à « {Exemplaire.Statut(statut_apres).label} »")
    etats.noter(e.article, "CORRECTION", 1, variation=variation, par=request.user,
                exemplaire=e if statut_apres is not None else None,
                motif=f"N° de série {e.numero_serie} {quoi} dans l'administration")


@admin.register(Exemplaire)
class ExemplaireAdmin(admin.ModelAdmin):
    list_display = ("numero_serie", "article", "code_immo", "statut", "etat", "prete_a", "date_etalonnage")
    list_filter = ("statut", "etat")
    search_fields = ("numero_serie", "code_immo", "article__nom")

    def save_model(self, request, obj, form, change):
        avant = Exemplaire.objects.filter(pk=obj.pk).values_list("statut", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        noter_exemplaire_admin(request, obj, avant, obj.statut)

    def delete_model(self, request, obj):
        noter_exemplaire_admin(request, obj, obj.statut, None)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for e in queryset.select_related("article"):
            noter_exemplaire_admin(request, e, e.statut, None)
        super().delete_queryset(request, queryset)


admin.site.register(Categorie)


@admin.register(Magasin)
class MagasinAdmin(admin.ModelAdmin):
    list_display = ("nom", "type", "actif")
    list_filter = ("type", "actif")


@admin.register(Emplacement)
class EmplacementAdmin(admin.ModelAdmin):
    list_display = ("nom", "magasin")
    list_filter = ("magasin",)
admin.site.register(Fournisseur)
admin.site.site_header = "GestiStock – administration"


class LigneEntreeInline(admin.TabularInline):
    model = LigneEntree
    extra = 0
    readonly_fields = ("article", "quantite", "prix_unitaire", "numeros_serie")
    can_delete = False


@admin.register(Entree)
class EntreeAdmin(admin.ModelAdmin):
    """Consultation des réceptions (elles se saisissent dans l'application, qui met le stock à jour)."""
    list_display = ("date_reception", "magasin", "fournisseur", "numero_facture", "cree_le")
    list_filter = ("magasin", "fournisseur")
    inlines = [LigneEntreeInline]

    def has_add_permission(self, request):
        return False


from .models import Chantier, Demande, LigneDemande, Requisition, TelechargementBon  # noqa: E402


class LigneDemandeInline(admin.TabularInline):
    model = LigneDemande
    extra = 0


@admin.register(Demande)
class DemandeAdmin(admin.ModelAdmin):
    list_display = ("numero", "cree_le", "demandeur", "magasin", "chantier", "travail", "urgent", "statut")
    list_filter = ("statut", "magasin", "urgent")
    search_fields = ("numero", "chantier__nom", "travail")
    readonly_fields = ("numero", "cree_le", "traitee_le", "traitee_par")
    inlines = [LigneDemandeInline]


class TelechargementBonInline(admin.TabularInline):
    """Qui a téléchargé le PDF du bon, et quand (lecture seule)."""
    model = TelechargementBon
    extra = 0
    can_delete = False
    readonly_fields = ("par", "le", "role", "impression")
    fields = ("par", "le", "role", "impression")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Requisition)
class RequisitionAdmin(admin.ModelAdmin):
    """Réquisitions matière : créées automatiquement quand l'Agent Logistique valide une demande."""
    list_display = ("numero", "demande", "statut", "visa_agent", "visa_agent_le", "visa_responsable", "visa_responsable_le")
    list_filter = ("statut",)
    search_fields = ("numero", "demande__numero")
    readonly_fields = ("numero", "demande", "visa_agent", "visa_agent_le", "origine_signature_agent",
                       "origine_signature_responsable", "creee_le", "email_envoye_le", "email_etat",
                       "imprimee_le", "imprimee_par")
    inlines = [TelechargementBonInline]


@admin.register(Chantier)
class ChantierAdmin(admin.ModelAdmin):
    """Les chantiers ajoutés ici apparaissent dans la liste « Chantier » de la fenêtre « Nouvelle demande »."""
    list_display = ("nom", "actif", "cree_le")
    list_filter = ("actif",)
    search_fields = ("nom",)


# ---------------------------------------------------------------- Comptes (11/10/2026)
from django.contrib.auth.admin import UserAdmin  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402

from .models import Departement, Profil, ROLES, roles_de  # noqa: E402


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    """Départements de HBC : « Service demandeur » sur le bon de réquisition."""
    list_display = ("nom", "actif")
    list_filter = ("actif",)


class ProfilInline(admin.StackedInline):
    model = Profil
    can_delete = False
    min_num = 1
    max_num = 1
    verbose_name_plural = "Département et signature"
    fields = ("departement", "signature_enregistree")
    readonly_fields = ("signature_enregistree",)

    @admin.display(description="signature scannée enregistrée")
    def signature_enregistree(self, obj):
        # Enregistrée par la personne elle-même au moment de signer (15/10/2026) ; elle peut la retirer depuis la fenêtre de signature.
        if not obj or not obj.signature:
            return "non"
        from django.utils import timezone
        return f"oui, depuis le {timezone.localtime(obj.signature_le):%d/%m/%Y à %H:%M}" if obj.signature_le else "oui"


class CompteAdmin(UserAdmin):
    """Comptes GestiStock. Rôles : cochez les groupes « Agent Logistique » et/ou « Responsable HBC »
    (tout compte actif peut faire des demandes). « Statut super-utilisateur » = Administrateur."""
    inlines = [ProfilInline]
    list_display = ("username", "first_name", "last_name", "departement", "roles", "email", "is_active")
    list_filter = ("is_active", "groups", "profil__departement", "is_superuser")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personne", {"fields": ("first_name", "last_name", "email")}),
        ("Rôles et accès", {"fields": ("is_active", "groups", "is_staff", "is_superuser"),
                            "description": "Rôles : « Agent Logistique », « Responsable HBC » (cumulables). "
                                           "Tout compte actif peut faire des demandes. "
                                           "« Équipe » = accès à cette administration ; « Super-utilisateur » = Administrateur. "
                                           "Prénom et nom : ils sont imprimés sur le bon de réquisition (visas)."}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    filter_horizontal = ("groups",)

    @admin.display(description="département", ordering="profil__departement__nom")
    def departement(self, obj):
        p = getattr(obj, "profil", None)
        return p.departement if p and p.departement else "—"

    @admin.display(description="rôles")
    def roles(self, obj):
        return ", ".join(r for r in roles_de(obj) if r != "Saisisseur") or "Saisisseur"

    actions = ["retirer_signature"]

    @admin.action(description="Retirer la signature scannée enregistrée")
    def retirer_signature(self, request, queryset):
        # 15/10/2026 : les bons déjà signés gardent leur signature.
        n = Profil.objects.filter(user__in=queryset).exclude(signature="").update(signature="", signature_le=None)
        self.message_user(request, f"Signature enregistrée retirée de {n} compte(s)." if n
                          else "Aucun de ces comptes n'avait de signature enregistrée.")

    def get_inline_instances(self, request, obj=None):
        # Le département se choisit après la première étape (identifiant + mot de passe).
        return super().get_inline_instances(request, obj) if obj else []


admin.site.unregister(User)
admin.site.register(User, CompteAdmin)


# ---------------------------------------------------------------- Sorties (12/10/2026) : consultation seulement
from .models import LigneSortie, Sortie  # noqa: E402


class LigneSortieInline(admin.TabularInline):
    model = LigneSortie
    extra = 0
    can_delete = False
    fields = ("article", "qte_bon", "qte_livree", "exemplaires")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sortie)
class SortieAdmin(admin.ModelAdmin):
    """Les sorties se confirment dans GestiStock (écran « Sorties ») : le stock y est mis à jour.
    Ici, consultation seulement (une modification ne corrigerait pas le stock)."""
    list_display = ("requisition", "date_remise", "magasinier", "confirmee_le", "confirmee_par")
    search_fields = ("requisition__numero", "requisition__demande__numero", "magasinier")
    readonly_fields = ("requisition", "date_remise", "magasinier", "observation", "confirmee_le", "confirmee_par")
    inlines = [LigneSortieInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------- État du produit et retours (12/10/2026)
from .models import BonRetour, LigneRetour, MouvementEtat  # noqa: E402


@admin.register(MouvementEtat)
class MouvementEtatAdmin(admin.ModelAdmin):
    """Historique des états : chaque réception, sortie, retour, réparation et mise au rebut (consultation)."""
    list_display = ("le", "type", "article", "exemplaire", "quantite", "variation", "etat_avant", "etat_apres", "reference", "par")
    list_filter = ("type", "etat_apres")
    search_fields = ("article__code", "article__nom", "exemplaire__numero_serie", "reference", "motif")
    readonly_fields = [f.name for f in MouvementEtat._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class LigneRetourInline(admin.TabularInline):
    model = LigneRetour
    extra = 0
    can_delete = False
    fields = ("article", "qte_attendue", "qte_rendue", "etats", "exemplaires", "observation")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BonRetour)
class BonRetourAdmin(admin.ModelAdmin):
    """Les retours se confirment dans GestiStock (écran « Retours de stock ») : consultation seulement."""
    list_display = ("numero", "sortie", "statut", "imprime_le", "date_retour", "confirme_par")
    list_filter = ("statut",)
    search_fields = ("numero", "sortie__requisition__numero")
    readonly_fields = ("numero", "sortie", "statut", "imprime_le", "imprime_par", "date_retour", "magasinier", "rendu_par",
                       "observation", "confirme_le", "confirme_par", "annule_le", "origine_signature_agent")
    inlines = [LigneRetourInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------- Journal (15/10/2026)
# Tout ce qui est ajouté, modifié ou supprimé dans l'administration est noté (ancienne → nouvelle valeur) :
# comptes → historique des comptes (administrateur) ; le reste → « Modification » dans l'écran Historique.
from django.contrib.auth.models import User as _User  # noqa: E402

from . import journal as _journal  # noqa: E402
from .models import Evenement  # noqa: E402


@admin.register(Evenement)
class EvenementAdmin(admin.ModelAdmin):
    """Journal des événements : consultation seulement (personne ne peut le modifier ni l'effacer)."""
    list_display = ("le", "categorie", "libelle", "objet", "par_nom", "adresse_ip")
    list_filter = ("categorie", "action")
    search_fields = ("libelle", "objet", "detail", "identifiant", "par_nom", "reference")
    readonly_fields = [f.name for f in Evenement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def _cible(obj):
    """(catégorie, compte, article, objet) d'une ligne du journal pour cet objet."""
    from .models import Profil
    compte = obj if isinstance(obj, _User) else obj.user if isinstance(obj, Profil) else None
    if compte is not None:
        return Evenement.Categorie.COMPTE, compte, None, _journal.nom_de(compte)
    article = obj if isinstance(obj, Article) else getattr(obj, "article", None) if hasattr(obj, "article_id") else None
    return Evenement.Categorie.MODIFICATION, None, article, f"{str(obj._meta.verbose_name).capitalize()} « {obj} »"


def _noter_admin(request, obj, quoi, detail):
    categorie, compte, article, objet = _cible(obj)
    _journal.noter(categorie, f"admin_{quoi}", {"ajout": "Ajouté dans l'administration",
                                                "modif": "Modifié dans l'administration",
                                                "suppr": "Supprimé dans l'administration"}[quoi],
                   par=request.user, compte=compte, article=article, objet=objet, reference="Administration",
                   detail=detail, request=request)


class JournalAdminMixin:
    """Ajouté devant chaque page de l'administration (voir la boucle ci-dessous)."""

    def save_model(self, request, obj, form, change):
        ancien = type(obj).objects.filter(pk=obj.pk).first() if change and obj.pk else None
        request._journal_avant = _journal.instantane(ancien)
        request._journal_lignes = []
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        avant = {f.instance.pk: _journal.instantane(type(f.instance).objects.filter(pk=f.instance.pk).first())
                 for f in formset.forms if f.instance.pk}
        supprimes = [f.instance for f in formset.deleted_forms if f.instance.pk]
        noms_supprimes = {o.pk: str(o) for o in supprimes}
        super().save_formset(request, form, formset, change)
        lignes = getattr(request, "_journal_lignes", None)
        if lignes is None:
            return
        for f in formset.forms:
            o = f.instance
            nom = str(o._meta.verbose_name).capitalize()
            if o.pk in noms_supprimes:
                lignes.append(f"{nom} « {noms_supprimes[o.pk]} » supprimé")
            elif o.pk and o.pk not in avant and f.has_changed():
                lignes.append(f"{nom} « {o} » ajouté")
            elif o.pk in avant:
                d = _journal.differences(avant[o.pk], _journal.instantane(type(o).objects.filter(pk=o.pk).first()))
                if d:
                    lignes.append(f"{nom} « {o} » : {d}")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        apres = _journal.instantane(type(obj).objects.filter(pk=obj.pk).first())
        lignes = getattr(request, "_journal_lignes", [])
        if change:
            d = _journal.differences(getattr(request, "_journal_avant", {}), apres)
            detail = " · ".join(filter(None, [d, *lignes]))
            if detail:
                _noter_admin(request, obj, "modif", detail)
        else:
            detail = " · ".join([f"{k} : {v}" for k, v in apres.items() if v != _journal.VIDE] + lignes)
            _noter_admin(request, obj, "ajout", detail)

    def delete_model(self, request, obj):
        detail = " · ".join(f"{k} : {v}" for k, v in _journal.instantane(obj).items() if v != _journal.VIDE)
        categorie, compte, article, objet = _cible(obj)
        super().delete_model(request, obj)
        _journal.noter(categorie, "admin_suppr", "Supprimé dans l'administration", par=request.user,
                       compte=None if compte is obj else compte, identifiant=getattr(compte, "username", ""),
                       article=None if article is obj else article, objet=objet, reference="Administration",
                       detail=detail, request=request)

    def delete_queryset(self, request, queryset):
        for obj in list(queryset):
            self.delete_model(request, obj)


class CompteJournalAdmin(JournalAdminMixin, CompteAdmin):
    def user_change_password(self, request, id, form_url=""):
        reponse = super().user_change_password(request, id, form_url)
        if request.method == "POST" and reponse.status_code == 302:  # mot de passe enregistré (jamais noté lui-même)
            u = _User.objects.filter(pk=id).first()
            if u:
                _journal.compte("mot_de_passe", "Mot de passe changé", request.user, u,
                                "Changé dans l'administration", request=request)
        return reponse

    def retirer_signature(self, request, queryset):
        avec = list(queryset.filter(profil__signature__gt=""))
        super().retirer_signature(request, queryset)
        for u in avec:
            _journal.compte("signature_retiree", "Signature enregistrée retirée", request.user, u,
                            "Retirée dans l'administration ; les bons déjà signés ne changent pas", request=request)
    retirer_signature.short_description = "Retirer la signature scannée enregistrée"


for _modele, _page in list(admin.site._registry.items()):
    if _modele is Evenement:
        continue
    admin.site.unregister(_modele)
    if _modele is _User:
        admin.site.register(_modele, CompteJournalAdmin)
    else:
        admin.site.register(_modele, type(type(_page).__name__, (JournalAdminMixin, type(_page)), {}))
