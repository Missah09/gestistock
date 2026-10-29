from django.urls import path
from rest_framework.routers import DefaultRouter

from .views_comptes import compteurs, connexion, deconnexion, ma_signature, session
from . import (views_gestion_comptes, views_rapports, views_requisitions, views_retours, views_sorties, views_tableau, views_validation,
               views_visa)

from .views import (ArticleViewSet, annuler_demande, choix, choix_demande, demandes, detail_demande, enregistrer_entree,
                    filtres)

router = DefaultRouter()
router.register("articles", ArticleViewSet, basename="article")

urlpatterns = [path("session/", session), path("compteurs/", compteurs),
               # Signature scannée enregistrée dans le compte connecté (15/10/2026)
               path("ma-signature/", ma_signature),
               # Écran « Tableau de bord » (Responsable Technique et Responsable Logistique, 12/10/2026)
               path("tableau-de-bord/", views_tableau.tableau_de_bord),
               # Écrans « Générer Rapports » et « Historique » (Responsable Technique, 15/10/2026)
               path("rapports/", views_rapports.liste), path("rapports/<str:cle>/", views_rapports.rapport),
               path("historique/", views_rapports.historique), path("historique/export/", views_rapports.historique_export),
               # Écran « Comptes » (administrateur)
               path("comptes/", views_gestion_comptes.comptes), path("comptes/<int:pk>/", views_gestion_comptes.modifier),
               # Historique des comptes et journal de connexion (administrateur, 15/10/2026)
               path("comptes/journal/", views_gestion_comptes.journal_comptes),
               path("comptes/<int:pk>/activer/", views_gestion_comptes.activer),
               path("comptes/<int:pk>/mot-de-passe/", views_gestion_comptes.mot_de_passe),
               path("comptes/<int:pk>/deconnecter/", views_gestion_comptes.deconnecter),
               path("comptes/<int:pk>/signature/", views_gestion_comptes.signature), path("connexion/", connexion), path("deconnexion/", deconnexion),
               path("filtres/", filtres), path("choix/", choix), path("entrees/", enregistrer_entree),
               path("demandes/", demandes), path("demandes/choix/", choix_demande),
               path("demandes/<int:pk>/", detail_demande), path("demandes/<int:pk>/annuler/", annuler_demande),
               # Écran « Demandes à valider » (Responsable Technique)
               path("a-valider/", views_validation.liste), path("a-valider/<int:pk>/", views_validation.detail),
               path("a-valider/<int:pk>/numero/", views_validation.attribuer_numero),
               path("a-valider/<int:pk>/valider/", views_validation.valider),
               path("a-valider/<int:pk>/refuser/", views_validation.refuser),
               path("a-valider/<int:pk>/renvoyer-email/", views_validation.renvoyer_email),
               # Écran « À viser » (Responsable Logistique)
               path("a-viser/", views_visa.liste), path("a-viser/<int:pk>/", views_visa.detail),
               path("a-viser/<int:pk>/viser/", views_visa.viser), path("a-viser/<int:pk>/refuser/", views_visa.refuser),
               path("requisitions/<int:pk>/signature/<str:qui>/", views_visa.signature),
               # Écran « Réquisitions » (Responsable Technique et Responsable Logistique) : bons signés, PDF (12/10/2026)
               path("requisitions/", views_requisitions.liste), path("requisitions/<int:pk>/", views_requisitions.detail),
               path("requisitions/<int:pk>/pdf/", views_requisitions.pdf),
               # Écran « Sorties » (Responsable Technique) : confirmation de la remise, le stock diminue (12/10/2026)
               path("sorties/", views_sorties.liste), path("sorties/<int:pk>/", views_sorties.detail),
               path("sorties/<int:pk>/confirmer/", views_sorties.confirmer),
               path("sorties/<int:pk>/pdf/", views_sorties.pdf_archive),
               # Écran « Retours de stock » (Responsable Technique) : bons de retour, le stock remonte (12/10/2026)
               path("retours/", views_retours.liste), path("retours/<int:pk>/", views_retours.detail),
               path("retours/<int:pk>/bon/", views_retours.creer_bon),
               path("retours/bons/<int:bon_id>/pdf/", views_retours.pdf),
               path("retours/bons/<int:bon_id>/confirmer/", views_retours.confirmer),
               path("retours/bons/<int:bon_id>/annuler/", views_retours.annuler_bon)] + router.urls
# L'écran « Matériel à réparer » a été retiré le 12/10/2026 (états simplifiés : Neuf · Bon · Moyen · Mauvais).
