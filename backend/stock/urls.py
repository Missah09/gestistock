from django.urls import path
from rest_framework.routers import DefaultRouter

from .views_comptes import compteurs, connexion, deconnexion, session
from . import views_gestion_comptes, views_requisitions, views_sorties, views_validation, views_visa

from .views import (ArticleViewSet, annuler_demande, choix, choix_demande, demandes, detail_demande, enregistrer_entree,
                    filtres)

router = DefaultRouter()
router.register("articles", ArticleViewSet, basename="article")

urlpatterns = [path("session/", session), path("compteurs/", compteurs),
               # Écran « Comptes » (administrateur)
               path("comptes/", views_gestion_comptes.comptes), path("comptes/<int:pk>/", views_gestion_comptes.modifier),
               path("comptes/<int:pk>/activer/", views_gestion_comptes.activer),
               path("comptes/<int:pk>/mot-de-passe/", views_gestion_comptes.mot_de_passe),
               path("comptes/<int:pk>/deconnecter/", views_gestion_comptes.deconnecter), path("connexion/", connexion), path("deconnexion/", deconnexion),
               path("filtres/", filtres), path("choix/", choix), path("entrees/", enregistrer_entree),
               path("demandes/", demandes), path("demandes/choix/", choix_demande),
               path("demandes/<int:pk>/", detail_demande), path("demandes/<int:pk>/annuler/", annuler_demande),
               # Écran « Demandes à valider » (Agent Logistique)
               path("a-valider/", views_validation.liste), path("a-valider/<int:pk>/", views_validation.detail),
               path("a-valider/<int:pk>/valider/", views_validation.valider),
               path("a-valider/<int:pk>/refuser/", views_validation.refuser),
               path("a-valider/<int:pk>/renvoyer-email/", views_validation.renvoyer_email),
               # Écran « À viser » (Responsable HBC)
               path("a-viser/", views_visa.liste), path("a-viser/<int:pk>/", views_visa.detail),
               path("a-viser/<int:pk>/viser/", views_visa.viser), path("a-viser/<int:pk>/refuser/", views_visa.refuser),
               path("requisitions/<int:pk>/signature/<str:qui>/", views_visa.signature),
               # Écran « Réquisitions » (Agent Logistique et Responsable HBC) : bons signés, PDF (12/10/2026)
               path("requisitions/", views_requisitions.liste), path("requisitions/<int:pk>/", views_requisitions.detail),
               path("requisitions/<int:pk>/pdf/", views_requisitions.pdf),
               # Écran « Sorties » (Agent Logistique) : confirmation de la remise, le stock diminue (12/10/2026)
               path("sorties/", views_sorties.liste), path("sorties/<int:pk>/", views_sorties.detail),
               path("sorties/<int:pk>/confirmer/", views_sorties.confirmer),
               path("sorties/<int:pk>/pdf/", views_sorties.pdf_archive)] + router.urls
