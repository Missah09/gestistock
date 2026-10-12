"""PDF du bon de réquisition de matières (12/10/2026).

Même mise en page que l'aperçu à l'écran (maquette validée le 11/10/2026) :
en-tête HBC, informations générales, liste des articles accordés (les lignes à 0 sont retirées),
puis les quatre cases de visas : Demandeur et Magasinier à signer à la main, Agent Logistique et
Responsable HBC avec leur signature au stylo électronique, leur nom, la date et l'heure.
Format A4, prêt à imprimer. Fabriqué avec ReportLab.
"""
from io import BytesIO
from pathlib import Path

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .signatures import image as image_signature

LOGO = Path(__file__).resolve().parent / "ressources" / "logo-hbc.png"

BLEU = colors.HexColor("#2f4763")
BLEU_CLAIR = colors.HexColor("#e8eef5")
GRIS = colors.HexColor("#626262")
TRAIT = colors.HexColor("#9aa6b5")

POLICE, GRAS, ITALIQUE = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"

S_TITRE = ParagraphStyle("titre", fontName=GRAS, fontSize=13.5, leading=17, textColor=BLEU, alignment=TA_CENTER)
S_NUMERO = ParagraphStyle("numero", fontName=POLICE, fontSize=10.5, leading=14, alignment=TA_RIGHT)
S_SECTION = ParagraphStyle("section", fontName=GRAS, fontSize=11, leading=14, textColor=BLEU, spaceBefore=9, spaceAfter=4)
S_TEXTE = ParagraphStyle("texte", fontName=POLICE, fontSize=9.5, leading=13)
S_CELLULE = ParagraphStyle("cellule", fontName=POLICE, fontSize=9, leading=11)
S_ENTETE = ParagraphStyle("entete", fontName=GRAS, fontSize=9, leading=11, textColor=BLEU)
S_NOTE = ParagraphStyle("note", fontName=ITALIQUE, fontSize=8, leading=10, textColor=GRIS)
S_CASE_TITRE = ParagraphStyle("case_titre", fontName=GRAS, fontSize=9.5, leading=12, textColor=BLEU, alignment=TA_CENTER)
S_CASE = ParagraphStyle("case", fontName=POLICE, fontSize=8.5, leading=11)
S_ARCHIVE = ParagraphStyle("archive", fontName=GRAS, fontSize=9, leading=12, textColor=colors.HexColor("#a3332b"),
                           alignment=TA_CENTER)
S_CASE_PETIT = ParagraphStyle("case_petit", fontName=POLICE, fontSize=7.5, leading=9.5, textColor=GRIS)


def _x(texte):
    """Texte à insérer dans un Paragraph (caractères spéciaux échappés)."""
    return (str(texte or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _nombre(n):
    return f"{n:,}".replace(",", " ")


def quantite_texte(n, unite):
    if unite == "m":
        return f"{_nombre(n)} m"
    if unite == "paire":
        return f"{_nombre(n)} {'paires' if n > 1 else 'paire'}"
    return _nombre(n)


def _jour(dt):
    return timezone.localtime(dt).strftime("%d/%m/%Y") if dt else ""


def _date_heure(dt):
    if not dt:
        return ""
    t = timezone.localtime(dt)
    return f"{t:%d/%m/%Y} à {t.hour} h {t.minute:02d}"


def _nom(user):
    return (user.get_full_name() or user.username) if user else ""


def lignes_du_bon(demande):
    """Lignes imprimées : quantité accordée (sinon demandée) ; les articles retirés (0) n'y figurent pas."""
    lignes = []
    for l in demande.lignes.select_related("article__categorie").all():
        qte = l.qte_accordee if l.qte_accordee is not None else l.quantite
        if qte > 0:
            lignes.append((l, qte))
    return lignes


def _case_visa(titre, nom, b64, le, largeur):
    """Case Agent Logistique / Responsable HBC : nom, signature dessinée, date et heure du visa."""
    contenu = [Paragraph(titre, S_CASE_TITRE), Spacer(1, 3), Paragraph(f"Nom : <b>{_x(nom)}</b>", S_CASE)]
    if b64:
        lecteur = ImageReader(BytesIO(image_signature(b64)))
        l, h = lecteur.getSize()
        haut_max, large_max = 19 * mm, largeur - 8 * mm
        echelle = min(haut_max / h, large_max / l)
        img = Image(BytesIO(image_signature(b64)), width=l * echelle, height=h * echelle)
        img.hAlign = "CENTER"
        contenu.append(img)
    else:
        contenu.append(Spacer(1, 19 * mm))
    contenu.append(Paragraph(f"Visé électroniquement le {_date_heure(le)}" if le else "", S_CASE_PETIT))
    return contenu


def _case_main(titre, nom="", date=""):
    """Case à signer à la main (Demandeur, Magasinier)."""
    return [Paragraph(titre, S_CASE_TITRE), Spacer(1, 3), Paragraph(f"Nom : <b>{_x(nom)}</b>", S_CASE),
            Paragraph("Signature :", S_CASE), Spacer(1, 13 * mm), Paragraph(f"Date : {_x(date)}", S_CASE)]


def fabriquer_pdf(requisition, imprime_par=None, imprime_le=None, sortie=None):
    """Renvoie le PDF (octets) du bon de réquisition `requisition` (déjà visé par le Responsable).
    `sortie` (12/10/2026) : copie d'archive après confirmation de la sortie, avec la colonne « Qté livrée » remplie,
    les n° de série remis et le nom du magasinier."""
    d = requisition.demande
    livrees = {}
    if sortie is not None:
        livrees = {ls.ligne_demande_id: ls for ls in sortie.lignes.prefetch_related("exemplaires")}
    tampon = BytesIO()
    marges = 15 * mm
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=marges, rightMargin=marges, topMargin=13 * mm,
                            bottomMargin=16 * mm, title=f"Bon de réquisition {requisition.numero}",
                            author="HBC – GestiStock", subject=f"Demande {d.numero}")
    largeur = A4[0] - 2 * marges
    elements = []

    # En-tête : logo, titre, numéro
    logo = Image(str(LOGO), width=40 * mm, height=40 * mm * 232 / 746) if LOGO.exists() else Spacer(1, 1)
    tete = Table([[logo, Paragraph("BON DE RÉQUISITION DE MATIÈRES", S_TITRE),
                   Paragraph(f"N° <b>{_x(requisition.numero)}</b>", S_NUMERO)]],
                 colWidths=[44 * mm, largeur - 84 * mm, 40 * mm])
    tete.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("LINEBELOW", (0, 0), (-1, 0), 1.2, BLEU),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    elements.append(tete)
    if sortie is not None:
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(
            f"COPIE D'ARCHIVE – sortie confirmée le {_date_heure(sortie.confirmee_le)} par {_x(_nom(sortie.confirmee_par))}",
            S_ARCHIVE))

    # 1. Informations générales
    from .models import departement_de
    dep = departement_de(d.demandeur) if d.demandeur else None
    elements.append(Paragraph("1. Informations générales", S_SECTION))
    infos = Table([
        [Paragraph(f"Date : <b>{_jour(requisition.visa_agent_le)}</b>", S_TEXTE),
         Paragraph(f"Projet (ou chantier) : <b>{_x(d.destination or '—')}</b>", S_TEXTE)],
        [Paragraph(f"Service demandeur : <b>{_x(dep.nom if dep else '—')}</b>", S_TEXTE),
         Paragraph("Nature des travaux : ....................................................", S_TEXTE)],
    ], colWidths=[largeur / 2, largeur / 2])
    infos.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    elements.append(infos)

    # 2. Liste des articles
    elements.append(Paragraph("2. Liste des articles", S_SECTION))
    entetes = ["N°", "Code article", "Désignation", "Catégorie", "Qté demandée", "Qté livrée", "Motif"]
    donnees = [[Paragraph(e, S_ENTETE) for e in entetes]]
    for i, (l, qte) in enumerate(lignes_du_bon(d), start=1):
        a = l.article
        designation = _x(a.nom)
        livree = ""
        ls = livrees.get(l.id)
        if ls is not None:
            livree = quantite_texte(ls.qte_livree, a.unite)
            series = [e.numero_serie for e in ls.exemplaires.all()]
            if series:
                designation += f"<br/><font size='7.5' color='#626262'>N° de série : {_x(', '.join(series))}</font>"
        elif sortie is not None:
            livree = "0"
        donnees.append([str(i), a.code, Paragraph(designation, S_CELLULE), Paragraph(_x(a.categorie.nom), S_CELLULE),
                        quantite_texte(qte, a.unite), livree, Paragraph(_x(l.motif), S_CELLULE)])
    larg = [9 * mm, 23 * mm, None, 33 * mm, 22 * mm, 19 * mm, 33 * mm]
    larg[2] = largeur - sum(x for x in larg if x)
    table = Table(donnees, colWidths=larg, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, TRAIT), ("BACKGROUND", (0, 0), (-1, 0), BLEU_CLAIR),
        ("FONTNAME", (0, 1), (-1, -1), POLICE), ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("FONTNAME", (4, 1), (4, -1), GRAS), ("ALIGN", (0, 1), (0, -1), "CENTER"), ("ALIGN", (4, 1), (5, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 1), (-1, -1), 5), ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 3))
    if sortie is None:
        elements.append(Paragraph("Qté livrée : à remplir à la main par le magasinier lors de la remise du matériel.", S_NOTE))
    else:
        note = (f"Qté livrée : recopiée du bon signé par le magasinier. Matériel remis le {sortie.date_remise:%d/%m/%Y}"
                f"{' par ' + _x(sortie.magasinier) if sortie.magasinier else ''}.")
        if sortie.observation:
            note += f" Observation : {_x(sortie.observation)}"
        elements.append(Paragraph(note, S_NOTE))

    # 3. Visas et signatures
    case = largeur / 4
    visas = Table([[
        _case_main("Demandeur", _nom(d.demandeur), _jour(d.cree_le)),
        _case_visa("Agent Logistique", _nom(requisition.visa_agent), requisition.signature_agent,
                   requisition.visa_agent_le, case),
        _case_visa("Responsable HBC", _nom(requisition.visa_responsable), requisition.signature_responsable,
                   requisition.visa_responsable_le, case),
        _case_main("Magasinier", sortie.magasinier if sortie else "",
                   f"{sortie.date_remise:%d/%m/%Y}" if sortie else ""),
    ]], colWidths=[case] * 4, rowHeights=[40 * mm])
    visas.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, TRAIT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    elements.append(KeepTogether([Paragraph("3. Visas et signatures", S_SECTION), visas]))

    pied = f"GestiStock – Réquisition {requisition.numero} (demande {d.numero})"
    if sortie is not None:
        pied += " – copie d'archive"
    if imprime_par:
        pied += f" – imprimé le {_date_heure(imprime_le or timezone.now())} par {_nom(imprime_par)}"

    def numeroter(canvas, document):
        canvas.saveState()
        canvas.setFont(POLICE, 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawString(marges, 9 * mm, pied)
        canvas.drawRightString(A4[0] - marges, 9 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=numeroter, onLaterPages=numeroter)
    return tampon.getvalue()
