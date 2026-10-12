from django.contrib import admin

from .models import Article, Categorie, Emplacement, Entree, Exemplaire, Fournisseur, LigneEntree, Magasin


class ExemplaireInline(admin.TabularInline):
    model = Exemplaire
    extra = 0


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "categorie", "type", "qte_stock", "qte_minimale", "emplacement")
    list_filter = ("type", "categorie", "emplacement__magasin")
    search_fields = ("code", "nom", "exemplaires__numero_serie", "exemplaires__code_immo")
    readonly_fields = ("code",)
    inlines = [ExemplaireInline]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["qte_stock"].label = "Quantité en stock"
        form.base_fields["qte_stock"].help_text = (
            "Pour le matériel avec n° de série, laissez 0 : la quantité se calcule à partir des exemplaires « En stock »."
        )
        return form


@admin.register(Exemplaire)
class ExemplaireAdmin(admin.ModelAdmin):
    list_display = ("numero_serie", "article", "code_immo", "statut", "prete_a", "date_etalonnage")
    list_filter = ("statut",)
    search_fields = ("numero_serie", "code_immo", "article__nom")


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
    readonly_fields = ("par", "le", "role")
    fields = ("par", "le", "role")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Requisition)
class RequisitionAdmin(admin.ModelAdmin):
    """Réquisitions matière : créées automatiquement quand l'Agent Logistique valide une demande."""
    list_display = ("numero", "demande", "statut", "visa_agent", "visa_agent_le", "visa_responsable", "visa_responsable_le")
    list_filter = ("statut",)
    search_fields = ("numero", "demande__numero")
    readonly_fields = ("numero", "demande", "visa_agent", "visa_agent_le", "creee_le", "email_envoye_le", "email_etat",
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
    verbose_name_plural = "Département"


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
