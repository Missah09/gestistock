"""PDF du bon de retour de matériel (12/10/2026).

Même présentation que le bon de réquisition (pdf_bon.py), en A4 paysage (10 colonnes) :
en-tête HBC, rattachement à la réquisition RM-… et à la demande DEM-…, puis la liste de ce qui reste à rendre.
« Qté rendue » et « État au retour » se remplissent à la main au magasin ; sur la copie d'archive (après
confirmation du retour), ces colonnes sont remplies d'après la saisie du Responsable Technique.
Signatures : Rendu par (demandeur) · Reçu par (magasinier) à la main ; Responsable Technique au stylo électronique.
"""
from io import BytesIO

from django.utils import timezone
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import etats
from .models import BonRetour
from .pdf_bon import (BLEU, BLEU_CLAIR, GRAS, GRIS, LOGO, POLICE, S_ARCHIVE, S_CELLULE, S_ENTETE, S_NOTE, S_NUMERO,
                      S_SECTION, S_TEXTE, S_TITRE, TRAIT, _case_main, _case_visa, _date_heure, _jour, _nom, _x,
                      quantite_texte)


def _texte_etats(dico):
    return etats.texte(dico or {}) or "—"


def fabriquer_pdf_retour(bon, imprime_par=None, imprime_le=None):
    sortie = bon.sortie
    r = sortie.requisition
    d = r.demande
    archive = bon.statut == BonRetour.Statut.CONFIRME
    page = landscape(A4)
    tampon = BytesIO()
    marges = 12 * mm
    doc = SimpleDocTemplate(tampon, pagesize=page, leftMargin=marges, rightMargin=marges, topMargin=11 * mm,
                            bottomMargin=15 * mm, title=f"Bon de retour {bon.numero}", author="HBC – GestiStock",
                            subject=f"Réquisition {r.numero}")
    largeur = page[0] - 2 * marges
    elements = []

    logo = Image(str(LOGO), width=40 * mm, height=40 * mm * 232 / 746) if LOGO.exists() else Spacer(1, 1)
    tete = Table([[logo, Paragraph("BON DE RETOUR DE MATÉRIEL", S_TITRE),
                   Paragraph(f"N° <b>{_x(bon.numero)}</b>", S_NUMERO)]],
                 colWidths=[44 * mm, largeur - 88 * mm, 44 * mm])
    tete.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("LINEBELOW", (0, 0), (-1, 0), 1.2, BLEU),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    elements.append(tete)
    if archive:
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(
            f"COPIE D'ARCHIVE – retour confirmé le {_date_heure(bon.confirme_le)} par {_x(_nom(bon.confirme_par))}",
            S_ARCHIVE))

    from .models import departement_de
    dep = departement_de(d.demandeur) if d.demandeur else None
    elements.append(Paragraph("1. Informations générales", S_SECTION))
    infos = Table([
        [Paragraph(f"Réquisition : <b>{_x(r.numero)}</b> (demande {_x(d.numero)})", S_TEXTE),
         Paragraph(f"Projet (ou chantier) : <b>{_x(d.destination or '—')}</b>", S_TEXTE),
         Paragraph(f"Bon préparé le : <b>{_jour(bon.imprime_le)}</b>", S_TEXTE)],
        [Paragraph(f"Demandeur : <b>{_x(_nom(d.demandeur) or '—')}</b> – {_x(dep.nom if dep else '—')}", S_TEXTE),
         Paragraph(f"Matériel sorti le : <b>{sortie.date_remise:%d/%m/%Y}</b> – magasin {_x(d.magasin.nom)}", S_TEXTE),
         Paragraph(f"Rendu le : <b>{bon.date_retour:%d/%m/%Y}</b>" if archive and bon.date_retour
                   else "Rendu le : ......../......../............", S_TEXTE)],
    ], colWidths=[largeur * 0.36, largeur * 0.38, largeur * 0.26])
    infos.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    elements.append(infos)

    elements.append(Paragraph("2. Matériel à rendre", S_SECTION))
    entetes = ["N°", "Code article", "Désignation", "N° de série / code immo", "Qté sortie", "Déjà rendu",
               "Qté rendue", "État à la sortie", "État au retour", "Observation"]
    donnees = [[Paragraph(e, S_ENTETE) for e in entetes]]
    n = 0
    for lr in bon.lignes.select_related("article", "ligne_sortie").prefetch_related("exemplaires_attendus", "exemplaires"):
        a, ls = lr.article, lr.ligne_sortie
        deja = ls.qte_livree - lr.qte_attendue
        attendus = list(lr.exemplaires_attendus.all())
        if attendus:
            rendus = {e.id for e in lr.exemplaires.all()}
            retour = {str(k): v for k, v in (lr.etats or {}).items()}
            for e in attendus:
                n += 1
                serie = _x(e.numero_serie) + (f"<br/><font size='7.5' color='#626262'>immo {_x(e.code_immo)}</font>"
                                              if e.code_immo else "")
                donnees.append([str(n), a.code, Paragraph(_x(a.nom), S_CELLULE), Paragraph(serie, S_CELLULE), "1",
                                "", ("1" if e.id in rendus else "0") if archive else "",
                                Paragraph(_x(_etat_sortie_exemplaire(e)), S_CELLULE),
                                Paragraph(_x(etats.LIBELLES.get(retour.get(str(e.id)), "")) if archive else "", S_CELLULE),
                                Paragraph(_x(lr.observation) if archive else "", S_CELLULE)])
        else:
            n += 1
            donnees.append([str(n), a.code, Paragraph(_x(a.nom), S_CELLULE), "—",
                            quantite_texte(ls.qte_livree, a.unite), quantite_texte(deja, a.unite) if deja else "0",
                            quantite_texte(lr.qte_rendue, a.unite) if archive else "",
                            Paragraph(_x(_texte_etats(ls.etats)), S_CELLULE),
                            Paragraph(_x(etats.texte(lr.etats or {})) if archive else "", S_CELLULE),
                            Paragraph(_x(lr.observation) if archive else "", S_CELLULE)])
    larg = [9 * mm, 22 * mm, None, 34 * mm, 18 * mm, 18 * mm, 19 * mm, 30 * mm, 34 * mm, 40 * mm]
    larg[2] = largeur - sum(x for x in larg if x)
    table = Table(donnees, colWidths=larg, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, TRAIT), ("BACKGROUND", (0, 0), (-1, 0), BLEU_CLAIR),
        ("FONTNAME", (0, 1), (-1, -1), POLICE), ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("FONTNAME", (4, 1), (4, -1), GRAS), ("ALIGN", (0, 1), (0, -1), "CENTER"), ("ALIGN", (4, 1), (6, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Bon à remplir à la main : des lignes plus hautes pour écrire
        ("TOPPADDING", (0, 1), (-1, -1), 6 if archive else 11), ("BOTTOMPADDING", (0, 1), (-1, -1), 6 if archive else 11),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 3))
    if archive:
        note = (f"Qté rendue et état au retour : recopiés du bon signé au magasin. Rendu le {bon.date_retour:%d/%m/%Y}"
                f"{' par ' + _x(bon.rendu_par) if bon.rendu_par else ''}"
                f"{', reçu par ' + _x(bon.magasinier) if bon.magasinier else ''}.")
        if bon.observation:
            note += f" Observation : {_x(bon.observation)}"
        elements.append(Paragraph(note, S_NOTE))
    else:
        elements.append(Paragraph(
            "À remplir à la main par le magasinier : « Qté rendue » et « État au retour » (Neuf · Bon · Moyen · Mauvais). "
            "Pour une quantité, indiquez le nombre par état (ex. « 6 Bon, 2 Mauvais »).", S_NOTE))

    case = largeur / 3
    visas = Table([[
        _case_main("Rendu par (demandeur)", bon.rendu_par if archive and bon.rendu_par else _nom(d.demandeur),
                   f"{bon.date_retour:%d/%m/%Y}" if archive and bon.date_retour else ""),
        _case_main("Reçu par (magasinier)", bon.magasinier if archive else "",
                   f"{bon.date_retour:%d/%m/%Y}" if archive and bon.date_retour else ""),
        _case_visa("Responsable Technique", _nom(bon.imprime_par), bon.signature_agent, bon.imprime_le, case),
    ]], colWidths=[case] * 3, rowHeights=[38 * mm])
    visas.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, TRAIT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    elements.append(KeepTogether([Paragraph("3. Signatures", S_SECTION), visas]))

    pied = f"GestiStock – Bon de retour {bon.numero} (réquisition {r.numero}, demande {d.numero})"
    if archive:
        pied += " – copie d'archive"
    if imprime_par:
        pied += f" – imprimé le {_date_heure(imprime_le or timezone.now())} par {_nom(imprime_par)}"

    def numeroter(canvas, document):
        canvas.saveState()
        canvas.setFont(POLICE, 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawString(marges, 8 * mm, pied)
        canvas.drawRightString(page[0] - marges, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=numeroter, onLaterPages=numeroter)
    return tampon.getvalue()


def _etat_sortie_exemplaire(e):
    """État de l'exemplaire à la sortie : il ne change pas tant qu'il est prêté (dernier mouvement « Sortie » sinon)."""
    m = e.mouvements_etat.filter(type="SORTIE").order_by("-le", "-id").first()
    return etats.LIBELLES.get(m.etat_avant if m and m.etat_avant else e.etat, "")
