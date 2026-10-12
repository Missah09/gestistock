"""Écran « Sorties » (Agent Logistique, 12/10/2026) : confirmation de la remise du matériel.

Circuit : le bon imprimé (écran « Réquisitions ») est porté au magasin ; le magasinier remet le matériel,
remplit la colonne « Qté livrée » et signe. Au retour du bon signé, l'Agent Logistique recopie ici les quantités
livrées (et coche les n° de série remis pour le matériel suivi par exemplaire) : **le stock diminue à ce moment**.
L'application garde une copie d'archive du bon avec la Qté livrée remplie (PDF).
"""
import datetime

from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Article, Exemplaire, LigneSortie, Requisition, Sortie
from .permissions import EstAgentLogistique
from .serializers import nom_de
from .views import PAR_PAGE_DEMANDES, demandes_completes, en_json

MAGASINIER_MAX = 120
OBSERVATION_MAX = 250

ONGLETS = {"a_confirmer": Q(requisition__sortie__isnull=True),
           "confirmees": Q(requisition__sortie__isnull=False),
           "toutes": Q()}


def _introuvable():
    return Response({"general": ["Bon introuvable."]}, status=status.HTTP_404_NOT_FOUND)


def _bons_imprimes():
    """Demandes dont le bon (visé) a été imprimé par l'Agent Logistique : il est parti au magasin."""
    return demandes_completes().filter(requisition__statut=Requisition.Statut.VISEE,
                                       requisition__imprimee_le__isnull=False)


def lignes_a_livrer(demande):
    """Lignes du bon : quantité accordée (sinon demandée) ; les articles retirés (0) n'y figurent pas."""
    return [l for l in demande.lignes.all() if (l.qte_accordee if l.qte_accordee is not None else l.quantite) > 0]


def qte_du_bon(l):
    return l.qte_accordee if l.qte_accordee is not None else l.quantite


def _avec_exemplaires(demandes):
    """Comme en_json ; pour le matériel suivi par n° de série, la liste des exemplaires « En stock » à cocher."""
    resultats = en_json(demandes)
    ids = {j["article"]["id"] for json in resultats for j in json["lignes"] if j["article"]["suivi_par_serie"]}
    dispo = {}
    for e in Exemplaire.objects.filter(article_id__in=ids, statut=Exemplaire.Statut.EN_STOCK).order_by("numero_serie"):
        dispo.setdefault(e.article_id, []).append({"id": e.id, "numero_serie": e.numero_serie, "code_immo": e.code_immo})
    for json in resultats:
        for j in json["lignes"]:
            if j["article"]["suivi_par_serie"]:
                j["exemplaires_en_stock"] = dispo.get(j["article"]["id"], [])
    return resultats


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def liste(request):
    """Bons imprimés par onglet (?onglet=a_confirmer|confirmees|toutes, ?page=).
    À confirmer : les urgents d'abord, puis les plus anciens ; sinon les plus récents d'abord."""
    qs = _bons_imprimes()
    compteurs = {cle: qs.filter(f).count() for cle, f in ONGLETS.items()}
    onglet = request.query_params.get("onglet", "a_confirmer")
    if onglet not in ONGLETS:
        onglet = "a_confirmer"
    qs = qs.filter(ONGLETS[onglet])
    if onglet == "a_confirmer":
        qs = qs.annotate(rang=Case(When(urgent=True, then=Value(0)), default=Value(1), output_field=IntegerField())) \
               .order_by("rang", "requisition__imprimee_le", "id")
    else:
        qs = qs.order_by(F("requisition__sortie__confirmee_le").desc(nulls_first=True), "-requisition__imprimee_le", "-id")
    total = qs.count()
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    morceau = list(qs[(page - 1) * PAR_PAGE_DEMANDES: page * PAR_PAGE_DEMANDES])
    return Response({"count": total, "par_page": PAR_PAGE_DEMANDES, "compteurs": compteurs,
                     "results": _avec_exemplaires(morceau)})


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def detail(request, pk):
    d = _bons_imprimes().filter(pk=pk).first()
    return _introuvable() if d is None else Response(_avec_exemplaires([d])[0])


def _entier(valeur):
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        return valeur
    if isinstance(valeur, str) and valeur.strip().isdigit():
        return int(valeur.strip())
    return None


@api_view(["POST"])
@permission_classes([EstAgentLogistique])
def confirmer(request, pk):
    """Confirme la sortie d'un bon imprimé : quantités livrées (ou n° de série remis) → le stock diminue.

    Données : {date_remise: "AAAA-MM-JJ", magasinier, observation,
               lignes: [{id (ligne de demande), qte_livree, exemplaires: [id…] (matériel suivi par n° de série)}]}
    """
    donnees = request.data if isinstance(request.data, dict) else {}
    erreurs, erreurs_lignes = {}, {}

    magasinier = str(donnees.get("magasinier") or "").strip()
    observation = str(donnees.get("observation") or "").strip()
    if len(magasinier) > MAGASINIER_MAX:
        erreurs["magasinier"] = [f"{MAGASINIER_MAX} caractères au plus."]
    if len(observation) > OBSERVATION_MAX:
        erreurs["observation"] = [f"{OBSERVATION_MAX} caractères au plus."]

    with transaction.atomic():
        r = (Requisition.objects.select_for_update(of=("self",))
             .select_related("demande__demandeur", "demande__chantier").filter(demande_id=pk).first())
        if r is None:
            return _introuvable()
        if r.statut != Requisition.Statut.VISEE or r.imprimee_le is None:
            return Response({"general": ["Ce bon n'est pas encore imprimé : téléchargez-le d'abord dans l'écran « Réquisitions »."]},
                            status=status.HTTP_400_BAD_REQUEST)
        if hasattr(r, "sortie"):
            s = r.sortie
            return Response({"general": [f"La sortie de ce bon a déjà été confirmée le "
                                         f"{timezone.localtime(s.confirmee_le):%d/%m/%Y} par {nom_de(s.confirmee_par)}."]},
                            status=status.HTTP_400_BAD_REQUEST)
        d = r.demande

        # Date de remise : obligatoire, ni dans le futur, ni avant le visa du Responsable.
        aujourd_hui = timezone.localdate()
        try:
            date_remise = datetime.date.fromisoformat(str(donnees.get("date_remise") or ""))
        except ValueError:
            date_remise = None
            erreurs["date_remise"] = ["Indiquez la date à laquelle le magasinier a remis le matériel."]
        if date_remise:
            visa = timezone.localtime(r.visa_responsable_le).date() if r.visa_responsable_le else None
            if date_remise > aujourd_hui:
                erreurs["date_remise"] = ["Cette date est dans le futur : indiquez le jour où le matériel a été remis."]
            elif visa and date_remise < visa:
                erreurs["date_remise"] = [f"Le bon a été visé le {visa:%d/%m/%Y} : le matériel n'a pas pu être remis avant."]

        lignes = lignes_a_livrer(d)
        recues = {}
        for x in donnees.get("lignes") or []:
            if isinstance(x, dict) and _entier(x.get("id")) is not None:
                recues[_entier(x["id"])] = x
        articles = {a.id: a for a in Article.objects.select_for_update().filter(id__in=[l.article_id for l in lignes])}
        avec_serie = set(Exemplaire.objects.filter(article_id__in=articles).values_list("article_id", flat=True))

        a_faire = []   # (ligne, article, quantité, exemplaires)
        for l in lignes:
            a = articles[l.article_id]
            x = recues.get(l.id)
            bon = qte_du_bon(l)
            if x is None:
                erreurs_lignes[l.id] = ["Indiquez la quantité livrée (0 si le magasin n'a rien remis)."]
                continue
            if a.type == Article.Type.PRETE and a.id in avec_serie:
                ids = x.get("exemplaires") or []
                ids = [_entier(i) for i in ids] if isinstance(ids, list) else [None]
                if None in ids or len(set(ids)) != len(ids):
                    erreurs_lignes[l.id] = ["Liste de n° de série incorrecte."]
                    continue
                exemplaires = list(Exemplaire.objects.select_for_update().filter(id__in=ids, article=a))
                if len(exemplaires) != len(ids):
                    erreurs_lignes[l.id] = ["Un n° de série coché n'appartient pas à cet article."]
                    continue
                pris = [e.numero_serie for e in exemplaires if e.statut != Exemplaire.Statut.EN_STOCK]
                if pris:
                    erreurs_lignes[l.id] = [f"N° de série qui n'est plus en stock : {', '.join(pris)}."]
                    continue
                if len(exemplaires) > bon:
                    erreurs_lignes[l.id] = [f"{len(exemplaires)} n° de série cochés pour {bon} sur le bon : "
                                            f"le magasinier ne peut pas remettre plus que le bon."]
                    continue
                a_faire.append((l, a, len(exemplaires), exemplaires))
            else:
                qte = _entier(x.get("qte_livree"))
                if qte is None:
                    erreurs_lignes[l.id] = ["Indiquez un nombre entier, 0 ou plus (0 si rien n'a été remis)."]
                elif qte > bon:
                    erreurs_lignes[l.id] = [f"Plus que la quantité du bon ({bon}) : le magasinier ne peut pas remettre plus."]
                elif qte > a.qte_stock:
                    erreurs_lignes[l.id] = [f"Le stock de l'application n'indique que {a.qte_stock} : vérifiez la quantité "
                                            f"livrée, ou enregistrez d'abord la réception manquante."]
                else:
                    a_faire.append((l, a, qte, []))

        if not erreurs and not erreurs_lignes and not any(q for _, _, q, _ in a_faire):
            erreurs["general"] = ["Toutes les quantités livrées sont à 0 : si le magasin n'a rien remis, "
                                  "ne confirmez pas la sortie (le bon reste « à confirmer »)."]
        if erreurs or erreurs_lignes:
            if erreurs_lignes:
                erreurs["lignes"] = {str(k): v for k, v in erreurs_lignes.items()}
                erreurs.setdefault("general", ["Vérifiez les quantités signalées en rouge."])
            transaction.set_rollback(True)
            return Response(erreurs, status=status.HTTP_400_BAD_REQUEST)

        s = Sortie.objects.create(requisition=r, date_remise=date_remise, magasinier=magasinier,
                                  observation=observation, confirmee_par=request.user)
        destinataire = nom_de(d.demandeur)
        for l, a, qte, exemplaires in a_faire:
            ls = LigneSortie.objects.create(sortie=s, ligne_demande=l, article=a, qte_bon=qte_du_bon(l), qte_livree=qte)
            if exemplaires:
                ls.exemplaires.set(exemplaires)
                Exemplaire.objects.filter(id__in=[e.id for e in exemplaires]).update(
                    statut=Exemplaire.Statut.PRETE, prete_a=destinataire[:120], chantier=(d.destination or "")[:120])
            elif qte:
                Article.objects.filter(id=a.id).update(qte_stock=F("qte_stock") - qte)

    livres = sum(q for _, _, q, _ in a_faire)
    partiel = any(q < qte_du_bon(l) for l, _, q, _ in a_faire)
    message = (f"Sortie du bon {r.numero} confirmée : le stock a été mis à jour"
               f"{' (livraison partielle)' if partiel else ''}.")
    d = _bons_imprimes().get(pk=pk)
    return Response({"message": message, "livres": livres, "demande": _avec_exemplaires([d])[0]})


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def pdf_archive(request, pk):
    """Copie d'archive du bon, avec la colonne « Qté livrée » remplie (après confirmation de la sortie)."""
    try:
        from .pdf_bon import fabriquer_pdf
    except ImportError:
        return Response({"general": ["Le PDF ne peut pas être fabriqué : le module ReportLab n'est pas installé sur ce PC. "
                                     "Double-cliquez sur outils\\installer-modules.bat (Internet nécessaire), "
                                     "puis redémarrez GestiStock."]}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    r = (Requisition.objects.select_related("demande__demandeur", "visa_agent", "visa_responsable",
                                            "sortie__confirmee_par").filter(demande_id=pk).first())
    if r is None or not hasattr(r, "sortie"):
        return Response({"general": ["La sortie de ce bon n'est pas encore confirmée : pas de copie d'archive."]},
                        status=status.HTTP_404_NOT_FOUND)
    contenu = fabriquer_pdf(r, imprime_par=request.user, imprime_le=timezone.now(), sortie=r.sortie)
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="{r.numero}-archive.pdf"'
    reponse["Cache-Control"] = "no-store"
    return reponse
