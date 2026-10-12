"""Modèles de l'écran Articles : catégories, emplacements, fournisseurs,
articles et exemplaires (matériel prêté)."""
from django.db import models, transaction
from django.db.models import Q


class Categorie(models.Model):
    nom = models.CharField(max_length=80, unique=True)
    prefixe = models.CharField(
        max_length=5, unique=True,
        help_text="Début du code article, ex. CAB pour Câbles → CAB-0012",
    )

    class Meta:
        ordering = ["nom"]
        verbose_name = "catégorie"

    def __str__(self):
        return self.nom


class Magasin(models.Model):
    """Lieu de stockage : les magasins permanents (Ankorondrano, Manandriana)
    et les magasins de chantier, créés le temps d'un chantier."""

    class Type(models.TextChoices):
        MAGASIN = "MAGASIN", "Magasin"
        CHANTIER = "CHANTIER", "Chantier"

    nom = models.CharField(max_length=80, unique=True)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.MAGASIN)
    actif = models.BooleanField(default=True, help_text="Décocher quand le chantier est terminé")

    class Meta:
        ordering = ["type", "nom"]  # les magasins permanents d'abord, puis les chantiers

    def __str__(self):
        return self.nom if self.type == self.Type.MAGASIN else f"{self.nom} (chantier)"


class Emplacement(models.Model):
    nom = models.CharField(max_length=80)
    magasin = models.ForeignKey(Magasin, on_delete=models.PROTECT, related_name="emplacements")

    class Meta:
        ordering = ["magasin__nom", "nom"]
        unique_together = [("magasin", "nom")]

    def __str__(self):
        return f"{self.nom} – {self.magasin.nom}"


class Fournisseur(models.Model):
    nom = models.CharField(max_length=120, unique=True)
    contact = models.CharField(max_length=120, blank=True)
    telephone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Article(models.Model):
    class Type(models.TextChoices):
        CONSOMMABLE = "CONSOMMABLE", "Consommable (ne revient pas)"
        PRETE = "PRETE", "Non consommable · à rendre"

    class Unite(models.TextChoices):
        PIECE = "piece", "pièce"
        METRE = "m", "m"
        PAIRE = "paire", "paire"

    code = models.CharField(max_length=20, unique=True, blank=True, help_text="Créé automatiquement")
    nom = models.CharField(max_length=150)
    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="articles")
    type = models.CharField(max_length=12, choices=Type.choices, default=Type.CONSOMMABLE)
    unite = models.CharField(max_length=10, choices=Unite.choices, default=Unite.PIECE)
    # Matériel prêté avec exemplaires (n° de série) : la quantité est calculée à partir des exemplaires.
    # Sinon (consommables, petit matériel sans n° de série) : cette quantité saisie fait foi.
    qte_stock = models.PositiveIntegerField("quantité en stock (consommables)", default=0)
    qte_minimale = models.PositiveIntegerField("quantité minimale", default=0)
    emplacement = models.ForeignKey(Emplacement, on_delete=models.PROTECT, related_name="articles")

    prix_unitaire = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    fournisseur = models.ForeignKey(
        Fournisseur, on_delete=models.SET_NULL, null=True, blank=True, related_name="articles"
    )
    ref_fournisseur = models.CharField("réf. fournisseur", max_length=60, blank=True)
    ref_fabricant = models.CharField("réf. fabricant", max_length=60, blank=True)
    marque = models.CharField(max_length=60, blank=True)
    modele = models.CharField("modèle", max_length=60, blank=True)

    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} – {self.nom}"

    @property
    def est_prete(self):
        return self.type == self.Type.PRETE

    def save(self, *args, **kwargs):
        if not self.code:
            with transaction.atomic():
                self.code = self._prochain_code()
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def _prochain_code(self):
        prefixe = self.categorie.prefixe
        derniers = (
            Article.objects.select_for_update()
            .filter(code__startswith=f"{prefixe}-")
            .values_list("code", flat=True)
        )
        numeros = [int(c.split("-")[1]) for c in derniers if c.split("-")[1].isdigit()]
        return f"{prefixe}-{(max(numeros, default=0) + 1):04d}"


class Exemplaire(models.Model):
    class Statut(models.TextChoices):
        EN_STOCK = "EN_STOCK", "En stock"
        PRETE = "PRETE", "Prêté"
        REPARATION = "REPARATION", "En réparation"
        HORS_SERVICE = "HORS_SERVICE", "Hors service"

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="exemplaires")
    numero_serie = models.CharField("n° de série", max_length=60, unique=True)
    code_immo = models.CharField(
        "code immo", max_length=40, blank=True, help_text="Renseigné par la Finance (facultatif)"
    )
    date_etalonnage = models.DateField("prochain étalonnage", null=True, blank=True)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_STOCK)
    # Provisoire : sera rempli automatiquement par les écrans Sorties / Retours.
    prete_a = models.CharField("prêté à", max_length=120, blank=True)
    chantier = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["numero_serie"]
        constraints = [
            models.UniqueConstraint(
                fields=["code_immo"], condition=~Q(code_immo=""), name="code_immo_unique_si_renseigne"
            )
        ]

    def __str__(self):
        return f"{self.article.nom} – {self.numero_serie}"


def etat_stock(qte_disponible, qte_minimale):
    """Règle d'état du stock (la même partout dans l'application).

    Épuisé  : plus rien en stock
    Critique: la moitié du minimum ou moins
    Stock bas: sous le minimum
    OK      : le reste
    """
    if qte_disponible <= 0:
        return "EPUISE"
    if qte_minimale and qte_disponible <= qte_minimale / 2:
        return "CRITIQUE"
    if qte_disponible < qte_minimale:
        return "BAS"
    return "OK"


class Entree(models.Model):
    """Une réception de produits (livraison d'un fournisseur)."""

    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.PROTECT, null=True, blank=True, related_name="entrees")
    numero_facture = models.CharField("n° de facture", max_length=60, blank=True)
    date_reception = models.DateField("date de réception")
    magasin = models.ForeignKey(Magasin, on_delete=models.PROTECT, related_name="entrees")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_reception", "-id"]
        verbose_name = "entrée (réception)"
        verbose_name_plural = "entrées (réceptions)"

    def __str__(self):
        return f"Réception du {self.date_reception:%d/%m/%Y} – {self.magasin.nom}"


class LigneEntree(models.Model):
    entree = models.ForeignKey(Entree, on_delete=models.CASCADE, related_name="lignes")
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name="lignes_entree")
    quantite = models.PositiveIntegerField("quantité")
    prix_unitaire = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    numeros_serie = models.TextField("n° de série reçus", blank=True, help_text="Un par ligne")

    class Meta:
        verbose_name = "ligne de réception"
        verbose_name_plural = "lignes de réception"

    def __str__(self):
        return f"{self.article.nom} × {self.quantite}"


class Chantier(models.Model):
    """Chantiers proposés dans la fenêtre « Nouvelle demande ». Ajoutés dans l'administration."""

    nom = models.CharField(max_length=150, unique=True)
    actif = models.BooleanField(default=True, help_text="Décocher quand le chantier est terminé : il n'est plus proposé")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Demande(models.Model):
    """Demande de matériel : une intention, validée ou refusée par l'Agent Logistique
    (la validation crée la réquisition matière, que le Responsable HBC vise ensuite).
    Le stock ne change pas ici ; il diminue à la confirmation de sortie."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        VALIDEE = "VALIDEE", "Validée"
        REFUSEE = "REFUSEE", "Refusée"
        ANNULEE = "ANNULEE", "Annulée"

    numero = models.CharField("n°", max_length=20, unique=True, blank=True, help_text="Créé automatiquement")
    # Provisoire : vide tant que les comptes ne sont pas en place.
    demandeur = models.ForeignKey("auth.User", on_delete=models.PROTECT, null=True, blank=True, related_name="demandes")
    magasin = models.ForeignKey(Magasin, on_delete=models.PROTECT, related_name="demandes")
    # Facultatif : une demande n'est pas forcément rattachée à un chantier.
    chantier = models.ForeignKey(Chantier, on_delete=models.PROTECT, null=True, blank=True, related_name="demandes")
    # Ancien champ (saisie libre, demandes d'avant le 11/10) : conservé pour ne pas perdre l'information.
    travail = models.CharField("travail (ancien champ)", max_length=150, blank=True)
    urgent = models.BooleanField(default=False)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    motif_refus = models.CharField("motif du refus", max_length=250, blank=True)
    # Date et heure de la demande : prises automatiquement sur le serveur à l'envoi.
    cree_le = models.DateTimeField("envoyée le", auto_now_add=True)
    traitee_le = models.DateTimeField("validée ou refusée le", null=True, blank=True)
    traitee_par = models.ForeignKey("auth.User", on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="demandes_traitees", verbose_name="validée ou refusée par")

    class Meta:
        ordering = ["-cree_le", "-id"]

    def __str__(self):
        return f"{self.numero} – {self.destination}"

    @property
    def destination(self):
        """Ce qui s'affiche : le nom du chantier, sinon le travail saisi."""
        return self.chantier.nom if self.chantier_id else self.travail  # vide si sans chantier

    def save(self, *args, **kwargs):
        if not self.numero:
            with transaction.atomic():
                self.numero = self._prochain_numero()
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    @staticmethod
    def _prochain_numero():
        """DEM-2026-0001, DEM-2026-0002… (la numérotation repart à 1 chaque année)."""
        from django.utils import timezone
        annee = timezone.localdate().year
        prefixe = f"DEM-{annee}-"
        numeros = Demande.objects.select_for_update().filter(numero__startswith=prefixe).values_list("numero", flat=True)
        dernier = max((int(n.rsplit("-", 1)[1]) for n in numeros if n.rsplit("-", 1)[1].isdigit()), default=0)
        return f"{prefixe}{dernier + 1:04d}"


class LigneDemande(models.Model):
    demande = models.ForeignKey(Demande, on_delete=models.CASCADE, related_name="lignes")
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name="lignes_demande")
    quantite = models.PositiveIntegerField("quantité demandée")
    qte_accordee = models.PositiveIntegerField("quantité accordée", null=True, blank=True,
                                               help_text="Fixée par l'Agent Logistique à la validation (0 = article retiré). "
                                                         "La quantité demandée d'origine est conservée.")
    date_retour_prevue = models.DateField("retour prévu", null=True, blank=True,
                                          help_text="Matériel prêté seulement (obligatoire) ; vide pour un consommable")
    motif = models.CharField(max_length=250, blank=True, help_text="Pourquoi cet article est demandé (facultatif)")

    class Meta:
        ordering = ["id"]
        verbose_name = "ligne de demande"
        verbose_name_plural = "lignes de demande"

    def __str__(self):
        return f"{self.article.nom} × {self.quantite}"


class Requisition(models.Model):
    """Réquisition matière (bon de sortie), créée en un clic quand l'Agent Logistique valide une demande.
    Cette validation vaut visa électronique de l'Agent Logistique ; le Responsable HBC vise ensuite."""

    class Statut(models.TextChoices):
        ATTENTE_VISA = "ATTENTE_VISA", "En attente du visa"
        VISEE = "VISEE", "Visée"
        REFUSEE = "REFUSEE", "Refusée par le Responsable"

    numero = models.CharField("n°", max_length=20, unique=True, blank=True, help_text="Créé automatiquement")
    demande = models.OneToOneField(Demande, on_delete=models.PROTECT, related_name="requisition")
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.ATTENTE_VISA)
    # Visa électronique de l'Agent Logistique : posé à la validation de la demande.
    visa_agent = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="requisitions_validees",
                                   verbose_name="visa de l'Agent Logistique")
    visa_agent_le = models.DateTimeField("visée par l'Agent Logistique le")
    # Visa du Responsable HBC (étape suivante du circuit).
    visa_responsable = models.ForeignKey("auth.User", on_delete=models.PROTECT, null=True, blank=True,
                                         related_name="requisitions_visees", verbose_name="visa du Responsable HBC")
    visa_responsable_le = models.DateTimeField("visée par le Responsable le", null=True, blank=True)
    motif_refus = models.CharField("motif du refus (Responsable)", max_length=250, blank=True)
    creee_le = models.DateTimeField("créée le", auto_now_add=True)
    # Signatures dessinées au stylo électronique (image PNG en base64), imprimées dans les cases du bon (11/10/2026).
    signature_agent = models.TextField("signature de l'Agent Logistique", blank=True, editable=False)
    signature_responsable = models.TextField("signature du Responsable HBC", blank=True, editable=False)
    # Email au Responsable HBC (envoyé à la validation ; « Renvoyer l'email » possible)
    email_envoye_le = models.DateTimeField("email envoyé le", null=True, blank=True)
    email_etat = models.CharField("état de l'email", max_length=300, blank=True)
    # Impression du bon (12/10/2026) : premier téléchargement du PDF par l'Agent Logistique,
    # qui porte ensuite le bon au magasin. Les téléchargements du Responsable sont de simples consultations.
    imprimee_le = models.DateTimeField("bon imprimé le", null=True, blank=True)
    imprimee_par = models.ForeignKey("auth.User", on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="requisitions_imprimees", verbose_name="bon imprimé par")

    class Meta:
        ordering = ["-creee_le", "-id"]
        verbose_name = "réquisition matière"
        verbose_name_plural = "réquisitions matière"

    def __str__(self):
        return f"{self.numero} (demande {self.demande.numero})"

    def save(self, *args, **kwargs):
        if not self.numero:
            with transaction.atomic():
                self.numero = self._prochain_numero()
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    @staticmethod
    def _prochain_numero():
        """RM-2026-0001, RM-2026-0002… (la numérotation repart à 1 chaque année)."""
        from django.utils import timezone
        prefixe = f"RM-{timezone.localdate().year}-"
        numeros = (Requisition.objects.select_for_update().filter(numero__startswith=prefixe)
                   .values_list("numero", flat=True))
        dernier = max((int(n.rsplit("-", 1)[1]) for n in numeros if n.rsplit("-", 1)[1].isdigit()), default=0)
        return f"{prefixe}{dernier + 1:04d}"


class TelechargementBon(models.Model):
    """Trace de chaque téléchargement du PDF d'un bon de réquisition (qui, quand, en quelle qualité)."""

    requisition = models.ForeignKey(Requisition, on_delete=models.CASCADE, related_name="telechargements")
    par = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="bons_telecharges", verbose_name="par")
    le = models.DateTimeField("le", auto_now_add=True)
    role = models.CharField("en tant que", max_length=30)

    class Meta:
        ordering = ["-le", "-id"]
        verbose_name = "téléchargement du bon"
        verbose_name_plural = "téléchargements des bons"

    def __str__(self):
        return f"{self.requisition.numero} – {self.par.username} – {self.le:%d/%m/%Y %H:%M}"


# ---------------------------------------------------------------- Comptes (11/10/2026)

ROLE_AGENT = "Agent Logistique"   # valide les demandes, crée et télécharge les réquisitions, réceptions, sorties, retours
ROLE_RESPONSABLE = "Responsable HBC"  # vise les réquisitions (prévenu par email)
ROLES = [ROLE_AGENT, ROLE_RESPONSABLE]
# « Saisisseur » = tout compte actif (pas de groupe). « Administrateur » = super-utilisateur (crée les comptes).


class Departement(models.Model):
    """Département (service) de HBC. Sert de « Service demandeur » sur le bon de réquisition."""

    nom = models.CharField(max_length=80, unique=True)
    actif = models.BooleanField(default=True, help_text="Décocher pour ne plus le proposer sur les comptes")

    class Meta:
        ordering = ["nom"]
        verbose_name = "département"

    def __str__(self):
        return self.nom


class Profil(models.Model):
    """Informations GestiStock d'un compte utilisateur (département)."""

    user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="profil")
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="profils", verbose_name="département",
                                    limit_choices_to={"actif": True})
    # Une seule connexion à la fois (11/10/2026) : la session de l'appareil connecté en dernier.
    cle_session = models.CharField("session en cours", max_length=40, blank=True, editable=False)

    class Meta:
        verbose_name = "profil GestiStock"
        verbose_name_plural = "profil GestiStock"

    def __str__(self):
        return f"Profil de {self.user.username}"


def roles_de(user):
    """Rôles d'un compte, dans l'ordre du circuit. Le super-utilisateur a tous les rôles."""
    if not user or not user.is_authenticated:
        return []
    if user.is_superuser:
        return ["Saisisseur", *ROLES, "Administrateur"]
    groupes = set(user.groups.values_list("name", flat=True))
    return ["Saisisseur"] + [r for r in ROLES if r in groupes]


def a_le_role(user, role):
    return role in roles_de(user)


def departement_de(user):
    profil = getattr(user, "profil", None) if user and user.is_authenticated else None
    return profil.departement if profil else None


from django.db.models.signals import post_save  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_save, sender="auth.User")
def creer_profil(sender, instance, created, **kwargs):
    """Chaque nouveau compte reçoit son profil (département à choisir dans l'administration)."""
    if created and not kwargs.get("raw"):
        Profil.objects.get_or_create(user=instance)


# ---------------------------------------------------------------- Une seule connexion par compte (11/10/2026)
SESSION_REMPLACEE = "session-remplacee:"  # clé du cache : session fermée parce que le compte s'est connecté ailleurs


def fermer_session(cle, remplacee=False):
    """Ferme une session (l'appareil concerné revient à l'écran de connexion)."""
    from django.contrib.sessions.models import Session
    from django.core.cache import cache
    if not cle:
        return
    Session.objects.filter(session_key=cle).delete()
    if remplacee:
        cache.set(SESSION_REMPLACEE + cle, True, 24 * 3600)


def session_ouverte(profil):
    """Vrai si l'appareil connecté en dernier a encore une session valide."""
    from django.contrib.sessions.models import Session
    from django.utils import timezone
    return bool(profil.cle_session) and Session.objects.filter(
        session_key=profil.cle_session, expire_date__gt=timezone.now()).exists()


from django.contrib.auth.signals import user_logged_in, user_logged_out  # noqa: E402


@receiver(user_logged_in)
def une_seule_connexion(sender, request, user, **kwargs):
    """Nouvelle connexion (application ou administration) : l'autre appareil est déconnecté."""
    profil, _ = Profil.objects.get_or_create(user=user)
    if not request.session.session_key:
        request.session.save()
    cle = request.session.session_key
    if profil.cle_session and profil.cle_session != cle:
        fermer_session(profil.cle_session, remplacee=True)
    Profil.objects.filter(pk=profil.pk).update(cle_session=cle)


@receiver(user_logged_out)
def oublier_session(sender, request, user, **kwargs):
    if user is not None:
        Profil.objects.filter(user=user, cle_session=getattr(request.session, "session_key", None) or "").update(cle_session="")


# ---------------------------------------------------------------- Sorties (12/10/2026)
class Sortie(models.Model):
    """Confirmation de sortie : le magasinier a remis le matériel et signé le bon ; l'Agent Logistique recopie
    les quantités livrées. C'est à ce moment que le stock de l'application diminue."""

    requisition = models.OneToOneField(Requisition, on_delete=models.PROTECT, related_name="sortie",
                                       verbose_name="réquisition matière")
    date_remise = models.DateField("matériel remis le")
    magasinier = models.CharField("magasinier", max_length=120, blank=True, help_text="Nom du magasinier qui a signé le bon")
    observation = models.CharField(max_length=250, blank=True)
    confirmee_le = models.DateTimeField("sortie confirmée le", auto_now_add=True)
    confirmee_par = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="sorties_confirmees",
                                      verbose_name="sortie confirmée par")

    class Meta:
        ordering = ["-confirmee_le", "-id"]
        verbose_name = "sortie (matériel remis)"
        verbose_name_plural = "sorties (matériel remis)"

    def __str__(self):
        return f"Sortie {self.requisition.numero} du {self.date_remise:%d/%m/%Y}"


class LigneSortie(models.Model):
    sortie = models.ForeignKey(Sortie, on_delete=models.CASCADE, related_name="lignes")
    ligne_demande = models.OneToOneField(LigneDemande, on_delete=models.PROTECT, related_name="ligne_sortie")
    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name="lignes_sortie")
    qte_bon = models.PositiveIntegerField("qté sur le bon")
    qte_livree = models.PositiveIntegerField("qté livrée")
    # Matériel suivi par n° de série : les exemplaires remis (ils passent au statut « Prêté »).
    exemplaires = models.ManyToManyField(Exemplaire, blank=True, related_name="sorties", verbose_name="exemplaires remis")

    class Meta:
        ordering = ["id"]
        verbose_name = "ligne de sortie"
        verbose_name_plural = "lignes de sortie"

    def __str__(self):
        return f"{self.article.nom} : {self.qte_livree} / {self.qte_bon}"
