"""Écran « Retours de stock » (Agent Logistique, 12/10/2026) : le matériel prêté revient au magasin.

Circuit (le même que pour la sortie) :
1. Dans « Matériel attendu », l'Agent Logistique imprime un **bon de retour** (BR-AAAA-0001) rattaché à la
   réquisition, rempli d'office avec ce qui reste à rendre, et signé au stylo électronique.
2. Au magasin, le magasinier reçoit le matériel, remplit à la main « Qté rendue » et « État au retour » ;
   le demandeur et lui signent.
3. L'Agent Logistique **confirme le retour** en recopiant le bon : le stock remonte, l'état est mis à jour
   (Neuf · Bon · Moyen · Mauvais ; tous redeviennent disponibles).
Retour partiel : un bon par passage au magasin ; le suivant ne liste que ce qui reste à rendre.
Seul le matériel prêté (non consommable) revient ; jamais les consommables.
"""
import datetime

from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import etats
from .models import Article, BonRetour, Exemplaire, LigneRetour, LigneSortie, Requisition, Sortie
from .permissions import EstAgentLogistique
from .serializers import heure_locale, nom_de
from .signatures import ErreurSignature, enregistrer_si_demande, signature_de_la_requete
from .views import PAR_PAGE_DEMANDES, demandes_completes, en_json

TEXTE_MAX = 120
OBSERVATION_MAX = 250
ONGLETS = ("attendu", "en_retard", "soldes", "toutes")


def _introuvable(quoi="Retour introuvable."):
    return Response({"general": [quoi]}, status=status.HTTP_404_NOT_FOUND)


def _entier(valeur):
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int):
        return valeur
    if isinstance(valeur, str) and valeur.strip().isdigit():
        return int(valeur.strip())
    return None


# ---------------------------------------------------------------- Calcul de ce qui reste à rendre
def _sorties_avec_pret():
    """Sorties confirmées comprenant du matériel prêté effectivement remis."""
    lignes = LigneSortie.objects.select_related("article__categorie", "ligne_demande").prefetch_related(
        "exemplaires",
        Prefetch("lignes_retour", queryset=LigneRetour.objects.select_related("bon").prefetch_related("exemplaires")))
    return (Sortie.objects.filter(lignes__article__type=Article.Type.PRETE, lignes__qte_livree__gt=0).distinct()
            .select_related("requisition__demande", "confirmee_par")
            .prefetch_related(Prefetch("lignes", queryset=lignes),
                              Prefetch("bons_retour", queryset=BonRetour.objects.select_related("imprime_par", "confirme_par")
                                       .prefetch_related("lignes__exemplaires", "lignes__exemplaires_attendus",
                                                         "lignes__article"))))


def _exemplaire_json(e):
    return {"id": e.id, "numero_serie": e.numero_serie, "code_immo": e.code_immo, "etat": e.etat,
            "etat_libelle": e.get_etat_display(), "statut": e.statut}


def lignes_a_rendre(sortie):
    """Une entrée par ligne de matériel prêté de la sortie : sorti, déjà rendu, reste, n° de série."""
    aujourd_hui = timezone.localdate()
    resultat = []
    for ls in sortie.lignes.all():
        a = ls.article
        if a.type != Article.Type.PRETE or ls.qte_livree <= 0:
            continue
        confirmees = [lr for lr in ls.lignes_retour.all() if lr.bon.statut == BonRetour.Statut.CONFIRME]
        rendus = {e.id: lr.bon.numero for lr in confirmees for e in lr.exemplaires.all()}
        deja = sum(lr.qte_rendue for lr in confirmees)
        exemplaires = list(ls.exemplaires.all())
        reste = ls.qte_livree - deja
        prevue = ls.ligne_demande.date_retour_prevue
        resultat.append({
            "ligne_sortie": ls.id, "ligne_demande": ls.ligne_demande_id,
            "article": {"id": a.id, "code": a.code, "nom": a.nom, "unite": a.unite, "categorie": a.categorie.nom,
                        "suivi_par_serie": bool(exemplaires)},
            "date_retour_prevue": prevue.isoformat() if prevue else None,
            "qte_sortie": ls.qte_livree, "deja_rendu": deja, "reste": max(0, reste),
            "etats_sortie": ls.etats, "etats_sortie_texte": etats.texte(ls.etats),
            "en_retard": bool(reste > 0 and prevue and prevue < aujourd_hui),
            "exemplaires": [{**_exemplaire_json(e), "rendu": e.id in rendus, "bon": rendus.get(e.id, "")}
                            for e in exemplaires],
        })
    return resultat


def bon_json(b):
    lignes = []
    for lr in b.lignes.all():
        a = lr.article
        attendus = list(lr.exemplaires_attendus.all())
        rendus = {e.id: e for e in lr.exemplaires.all()}
        if attendus:
            etats_retour = {str(k): v for k, v in (lr.etats or {}).items()}
            detail = [{**_exemplaire_json(e), "rendu": e.id in rendus,
                       "etat_retour": etats_retour.get(str(e.id), ""),
                       "etat_retour_libelle": etats.LIBELLES.get(etats_retour.get(str(e.id), ""), "")} for e in attendus]
            texte_retour = etats.texte({k: sum(1 for v in etats_retour.values() if v == k) for k in etats.LIBELLES})
        else:
            detail, texte_retour = [], etats.texte(lr.etats or {})
        lignes.append({"id": lr.id, "ligne_sortie": lr.ligne_sortie_id,
                       "article": {"id": a.id, "code": a.code, "nom": a.nom, "unite": a.unite,
                                   "suivi_par_serie": bool(attendus)},
                       "qte_attendue": lr.qte_attendue, "qte_rendue": lr.qte_rendue, "etats": lr.etats,
                       "etats_texte": texte_retour, "exemplaires": detail, "observation": lr.observation})
    return {"id": b.id, "numero": b.numero, "statut": b.statut, "statut_libelle": b.get_statut_display(),
            "imprime_le": heure_locale(b.imprime_le), "imprime_par": nom_de(b.imprime_par),
            "signature_agent": bool(b.signature_agent),
            "date_retour": b.date_retour.isoformat() if b.date_retour else None, "magasinier": b.magasinier,
            "rendu_par": b.rendu_par, "observation": b.observation,
            "confirme_le": heure_locale(b.confirme_le), "confirme_par": nom_de(b.confirme_par),
            "annule_le": heure_locale(b.annule_le), "lignes": lignes}


def retour_json(sortie):
    lignes = lignes_a_rendre(sortie)
    bons = list(sortie.bons_retour.all())
    ouvert = next((b for b in bons if b.statut == BonRetour.Statut.A_CONFIRMER), None)
    restantes = [l for l in lignes if l["reste"] > 0]
    dates = [l["date_retour_prevue"] for l in restantes if l["date_retour_prevue"]]
    return {"lignes": lignes,
            "sorti_total": sum(l["qte_sortie"] for l in lignes), "rendu_total": sum(l["deja_rendu"] for l in lignes),
            "reste_total": sum(l["reste"] for l in lignes), "solde": not restantes,
            "en_retard": any(l["en_retard"] for l in lignes), "prochaine_date": min(dates) if dates else None,
            "date_remise": sortie.date_remise.isoformat(),
            "bons": [bon_json(b) for b in bons if b.statut != BonRetour.Statut.ANNULE],
            "bon_ouvert": bon_json(ouvert) if ouvert else None}


def _avec_retour(sorties):
    """Demandes (comme les autres écrans) + la partie « retour » de chacune."""
    demandes = {d.id: d for d in demandes_completes().filter(id__in=[s.requisition.demande_id for s in sorties])}
    ordre = [demandes[s.requisition.demande_id] for s in sorties]
    resultats = en_json(ordre)
    for s, json in zip(sorties, resultats):
        json["retour"] = retour_json(s)
    return resultats


def compter_retards():
    """Réquisitions dont du matériel prêté n'est pas rentré à la date prévue (pastille du menu)."""
    aujourd_hui = timezone.localdate()
    n = 0
    for s in _sorties_avec_pret().filter(lignes__ligne_demande__date_retour_prevue__lt=aujourd_hui):
        if any(l["en_retard"] for l in lignes_a_rendre(s)):
            n += 1
    return n


# ---------------------------------------------------------------- API
@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def liste(request):
    """Matériel attendu (?onglet=attendu|en_retard|soldes|toutes, ?page=).
    Attendu : les retards d'abord, puis le retour prévu le plus proche ; sinon les sorties les plus récentes."""
    infos = []
    for s in _sorties_avec_pret():
        lignes = lignes_a_rendre(s)
        if not lignes:
            continue
        reste = sum(l["reste"] for l in lignes)
        retard = any(l["en_retard"] for l in lignes)
        dates = [l["date_retour_prevue"] for l in lignes if l["reste"] > 0 and l["date_retour_prevue"]]
        infos.append((s, reste, retard, min(dates) if dates else "9999-12-31"))
    filtres = {"attendu": lambda i: i[1] > 0, "en_retard": lambda i: i[1] > 0 and i[2],
               "soldes": lambda i: i[1] == 0, "toutes": lambda i: True}
    compteurs = {cle: sum(1 for i in infos if f(i)) for cle, f in filtres.items()}
    onglet = request.query_params.get("onglet", "attendu")
    if onglet not in ONGLETS:
        onglet = "attendu"
    choisis = [i for i in infos if filtres[onglet](i)]
    if onglet in ("attendu", "en_retard"):
        choisis.sort(key=lambda i: (not i[2], i[3], i[0].confirmee_le))
    else:
        choisis.sort(key=lambda i: i[0].confirmee_le, reverse=True)
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    morceau = [i[0] for i in choisis[(page - 1) * PAR_PAGE_DEMANDES: page * PAR_PAGE_DEMANDES]]
    return Response({"count": len(choisis), "par_page": PAR_PAGE_DEMANDES, "compteurs": compteurs,
                     "results": _avec_retour(morceau)})


def _sortie_de(pk):
    return _sorties_avec_pret().filter(requisition__demande_id=pk).first()


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def detail(request, pk):
    s = _sortie_de(pk)
    return _introuvable() if s is None else Response(_avec_retour([s])[0])


@api_view(["POST"])
@permission_classes([EstAgentLogistique])
def creer_bon(request, pk):
    """Prépare le bon de retour (ce qui reste à rendre) ; signature de l'Agent Logistique au stylo."""
    try:
        sig = signature_de_la_requete(request)  # signature + mot de passe retapé (15/10/2026)
    except ErreurSignature as exc:
        return exc.reponse()
    with transaction.atomic():
        r = Requisition.objects.select_for_update(of=("self",)).filter(demande_id=pk).first()
        s = _sortie_de(pk)
        if r is None or s is None:
            return _introuvable("Aucun matériel prêté n'est sorti pour cette demande.")
        ouvert = s.bons_retour.filter(statut=BonRetour.Statut.A_CONFIRMER).first()
        if ouvert:
            return Response({"general": [f"Le bon de retour {ouvert.numero} n'est pas encore confirmé : confirmez-le "
                                         f"(ou annulez-le) avant d'en imprimer un autre."]},
                            status=status.HTTP_400_BAD_REQUEST)
        restantes = [l for l in lignes_a_rendre(s) if l["reste"] > 0]
        if not restantes:
            return Response({"general": ["Tout le matériel de ce bon est déjà rentré."]}, status=status.HTTP_400_BAD_REQUEST)
        b = BonRetour.objects.create(sortie=s, imprime_par=request.user, signature_agent=sig.b64,
                                     origine_signature_agent=sig.origine)
        enregistrer_si_demande(request.user, sig)
        for l in restantes:
            lr = LigneRetour.objects.create(bon=b, ligne_sortie_id=l["ligne_sortie"], article_id=l["article"]["id"],
                                            qte_attendue=l["reste"])
            if l["article"]["suivi_par_serie"]:
                lr.exemplaires_attendus.set([e["id"] for e in l["exemplaires"] if not e["rendu"]])
    s = _sortie_de(pk)
    return Response({"message": f"Bon de retour {b.numero} prêt : téléchargez-le et portez-le au magasin.",
                     "bon": b.id, "numero": b.numero, "demande": _avec_retour([s])[0]}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([EstAgentLogistique])
def annuler_bon(request, bon_id):
    """Bon imprimé mais le matériel n'est pas venu : on l'annule (le numéro reste utilisé)."""
    with transaction.atomic():
        b = BonRetour.objects.select_for_update().select_related("sortie__requisition").filter(pk=bon_id).first()
        if b is None:
            return _introuvable("Bon de retour introuvable.")
        if b.statut != BonRetour.Statut.A_CONFIRMER:
            return Response({"general": [f"Ce bon est déjà {b.get_statut_display().lower()} : il ne peut plus être annulé."]},
                            status=status.HTTP_400_BAD_REQUEST)
        b.statut, b.annule_le, b.annule_par = BonRetour.Statut.ANNULE, timezone.now(), request.user
        b.save(update_fields=["statut", "annule_le", "annule_par"])
    s = _sortie_de(b.sortie.requisition.demande_id)
    return Response({"message": f"Bon de retour {b.numero} annulé.", "demande": _avec_retour([s])[0]})


@api_view(["POST"])
@permission_classes([EstAgentLogistique])
def confirmer(request, bon_id):
    """Recopie du bon de retour rempli au magasin → le stock remonte, l'état est mis à jour.

    Données : {date_retour: "AAAA-MM-JJ", magasinier, rendu_par, observation,
               lignes: [{id (ligne du bon), etats: {"BON": 6, "MAUVAIS": 2}, observation}
                        | {id, exemplaires: {"<id exemplaire>": "BON"}, observation}]}
    """
    donnees = request.data if isinstance(request.data, dict) else {}
    erreurs, erreurs_lignes = {}, {}
    textes = {}
    for champ, maxi in (("magasinier", TEXTE_MAX), ("rendu_par", TEXTE_MAX), ("observation", OBSERVATION_MAX)):
        textes[champ] = str(donnees.get(champ) or "").strip()
        if len(textes[champ]) > maxi:
            erreurs[champ] = [f"{maxi} caractères au plus."]

    with transaction.atomic():
        b = (BonRetour.objects.select_for_update(of=("self",)).select_related("sortie__requisition").filter(pk=bon_id).first())
        if b is None:
            return _introuvable("Bon de retour introuvable.")
        if b.statut != BonRetour.Statut.A_CONFIRMER:
            return Response({"general": [f"Ce bon de retour est déjà {b.get_statut_display().lower()}."]},
                            status=status.HTTP_400_BAD_REQUEST)
        sortie = b.sortie
        aujourd_hui = timezone.localdate()
        try:
            date_retour = datetime.date.fromisoformat(str(donnees.get("date_retour") or ""))
        except ValueError:
            date_retour = None
            erreurs["date_retour"] = ["Indiquez la date à laquelle le matériel a été rendu au magasin."]
        if date_retour:
            if date_retour > aujourd_hui:
                erreurs["date_retour"] = ["Cette date est dans le futur : indiquez le jour où le matériel a été rendu."]
            elif date_retour < sortie.date_remise:
                erreurs["date_retour"] = [f"Le matériel est sorti le {sortie.date_remise:%d/%m/%Y} : il n'a pas pu être rendu avant."]

        recues = {}
        for x in donnees.get("lignes") or []:
            if isinstance(x, dict) and _entier(x.get("id")) is not None:
                recues[_entier(x["id"])] = x
        reste_actuel = {l["ligne_sortie"]: l["reste"] for l in lignes_a_rendre(_sorties_avec_pret().get(pk=sortie.pk))}
        a_faire = []  # (ligne du bon, article, {état: qté} ou {exemplaire: état}, exemplaires, observation)
        for lr in b.lignes.select_related("article").prefetch_related("exemplaires_attendus"):
            a = Article.objects.select_for_update().get(pk=lr.article_id)
            x = recues.get(lr.id)
            if x is None:
                erreurs_lignes[lr.id] = ["Recopiez la quantité rendue (0 si rien n'a été rendu)."]
                continue
            obs = str(x.get("observation") or "").strip()
            if len(obs) > OBSERVATION_MAX:
                erreurs_lignes[lr.id] = [f"Observation : {OBSERVATION_MAX} caractères au plus."]
                continue
            attendus = {e.id: e for e in lr.exemplaires_attendus.all()}
            if attendus:
                choix = x.get("exemplaires") or {}
                if not isinstance(choix, dict):
                    erreurs_lignes[lr.id] = ["Liste de n° de série incorrecte."]
                    continue
                parse, probleme = {}, None
                for cle, etat in choix.items():
                    i = _entier(cle)
                    if i not in attendus:
                        probleme = "Un n° de série coché n'est pas sur ce bon de retour."
                    elif not etats.etat_valide(etat):
                        probleme = f"Choisissez l'état au retour du n° {attendus[i].numero_serie}."
                    elif attendus[i].statut != Exemplaire.Statut.PRETE:
                        probleme = f"Le n° {attendus[i].numero_serie} n'est plus noté « prêté »."
                    else:
                        parse[i] = etat
                if probleme:
                    erreurs_lignes[lr.id] = [probleme]
                    continue
                a_faire.append((lr, a, parse, [attendus[i] for i in parse], obs))
            else:
                saisie = x.get("etats") or {}
                if not isinstance(saisie, dict):
                    erreurs_lignes[lr.id] = ["État au retour incorrect."]
                    continue
                parse, probleme = {}, None
                for etat, n in saisie.items():
                    n = _entier(n)
                    if not etats.etat_valide(etat) or n is None:
                        probleme = "Indiquez des nombres entiers, 0 ou plus, pour chaque état."
                    elif n:
                        parse[etat] = n
                total = sum(parse.values())
                reste = min(lr.qte_attendue, reste_actuel.get(lr.ligne_sortie_id, 0))
                if probleme:
                    erreurs_lignes[lr.id] = [probleme]
                elif total > reste:
                    erreurs_lignes[lr.id] = [f"{total} rendus pour {reste} à rendre : vérifiez la quantité rendue."]
                else:
                    a_faire.append((lr, a, parse, [], obs))

        nb_rendus = sum(len(e) if e else sum(p.values()) for _, _, p, e, _ in a_faire)
        if not erreurs and not erreurs_lignes and nb_rendus == 0:
            erreurs["general"] = ["Rien n'est rendu sur ce bon : si le matériel n'est pas venu, annulez le bon de retour "
                                  "(ou attendez son retour)."]
        if erreurs or erreurs_lignes:
            if erreurs_lignes:
                erreurs["lignes"] = {str(k): v for k, v in erreurs_lignes.items()}
                erreurs.setdefault("general", ["Vérifiez les lignes signalées en rouge."])
            transaction.set_rollback(True)
            return Response(erreurs, status=status.HTTP_400_BAD_REQUEST)

        de_cote = {}
        for lr, a, parse, exemplaires, obs in a_faire:
            if exemplaires:
                for e in exemplaires:
                    etat = parse[e.id]
                    avant = e.etat
                    Exemplaire.objects.filter(pk=e.pk).update(etat=etat, statut=etats.statut_pour(etat),
                                                              prete_a="", chantier="")
                    etats.noter(a, "RETOUR", 1, etat_avant=avant, etat_apres=etat, reference=b.numero,
                                motif=obs, par=request.user, exemplaire=e)
                    if etat in etats.DE_COTE:
                        de_cote[etat] = de_cote.get(etat, 0) + 1
                lr.exemplaires.set(exemplaires)
                lr.etats = {str(k): v for k, v in parse.items()}
                lr.qte_rendue = len(exemplaires)
            else:
                avant = next(iter(lr.ligne_sortie.etats)) if len(lr.ligne_sortie.etats or {}) == 1 else ""
                for etat, n in parse.items():
                    etats.ajouter(a, etat, n)
                    etats.noter(a, "RETOUR", n, etat_avant=avant, etat_apres=etat, reference=b.numero, motif=obs,
                                par=request.user)
                    if etat in etats.DE_COTE:
                        de_cote[etat] = de_cote.get(etat, 0) + n
                lr.etats = parse
                lr.qte_rendue = sum(parse.values())
            lr.observation = obs
            lr.save(update_fields=["etats", "qte_rendue", "observation"])
        b.statut, b.date_retour = BonRetour.Statut.CONFIRME, date_retour
        b.magasinier, b.rendu_par, b.observation = textes["magasinier"], textes["rendu_par"], textes["observation"]
        b.confirme_le, b.confirme_par = timezone.now(), request.user
        b.save()

    s = _sortie_de(sortie.requisition.demande_id)
    json = _avec_retour([s])[0]
    reste = json["retour"]["reste_total"]
    message = f"Retour {b.numero} confirmé : le stock a été mis à jour."
    if de_cote:
        message += " Mis de côté : " + ", ".join(
            f"{n} {etats.LIBELLES[e].lower()} ({etats.EMPLACEMENT_DE_COTE[e]})" for e, n in de_cote.items()) + "."
    message += f" Reste à rendre : {reste}." if reste else f" Tout le matériel du bon {sortie.requisition.numero} est rentré."
    return Response({"message": message, "demande": json})


@api_view(["GET"])
@permission_classes([EstAgentLogistique])
def pdf(request, bon_id):
    """Bon de retour à imprimer ; après confirmation, copie d'archive avec les colonnes remplies."""
    try:
        from .pdf_retour import fabriquer_pdf_retour
    except ImportError:
        return Response({"general": ["Le PDF ne peut pas être fabriqué : le module ReportLab n'est pas installé sur ce PC. "
                                     "Double-cliquez sur outils\\installer-modules.bat (Internet nécessaire), "
                                     "puis redémarrez GestiStock."]}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    b = (BonRetour.objects.select_related("sortie__requisition__demande__demandeur", "sortie__requisition__demande__chantier",
                                          "imprime_par", "confirme_par").filter(pk=bon_id).first())
    if b is None or b.statut == BonRetour.Statut.ANNULE:
        return _introuvable("Bon de retour introuvable (ou annulé).")
    contenu = fabriquer_pdf_retour(b, imprime_par=request.user, imprime_le=timezone.now())
    reponse = HttpResponse(contenu, content_type="application/pdf")
    nom = f"{b.numero}{'-archive' if b.statut == BonRetour.Statut.CONFIRME else ''}.pdf"
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    reponse["Cache-Control"] = "no-store"
    return reponse
