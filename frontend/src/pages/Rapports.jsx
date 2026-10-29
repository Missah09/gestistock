import { useCallback, useEffect, useState } from "react";
import { lireCatalogueRapports, lireRapport, telechargerRapport } from "../api.js";
import { date, montant, quantite } from "../format.js";
import Icon from "../icons.jsx";
import ListeDeroulante from "../ListeDeroulante.jsx";
import FicheArticle from "./FicheArticle.jsx";

/** Écran « Générer Rapports » (Responsable Technique, 15/10/2026), d'après la maquette (écran 10).
 *  Six cartes : Voir (à l'écran, avec des filtres), PDF, Excel. Les lignes et totaux sont fabriqués par le serveur
 *  (stock/rapports.py) : l'écran, le PDF et le fichier Excel montrent exactement la même chose. */

// Couleurs (« ton ») envoyées par le serveur → classes de l'application.
const PILL = { rouge: "p-c", orange: "p-w", vert: "p-ok", bleu: "e-neuf", gris: "p-g", violet: "p-i" };
const TEXTE = { rouge: "rouge", orange: "texte-orange", vert: "vert", bleu: "texte-bleu", gris: "discret", violet: "texte-violet" };
const A_DROITE = new Set(["quantite", "nombre", "montant"]);

function dateHeureCourte(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const deux = (n) => String(n).padStart(2, "0");
  return `${deux(d.getDate())}/${deux(d.getMonth() + 1)}/${d.getFullYear()} ${deux(d.getHours())}:${deux(d.getMinutes())}`;
}

/** Une cellule, selon le type de la colonne (le même que dans le PDF et le fichier Excel). */
export function Cellule({ col, ligne, total }) {
  const v = ligne[col.cle];
  const ton = ligne[`_ton_${col.cle}`];
  const detail = ligne[`_detail_${col.cle}`];
  let contenu;
  if (v === null || v === undefined || v === "") contenu = col.type === "pill" || total ? "" : <span className="discret">—</span>;
  else if (col.type === "quantite") contenu = quantite(Number(v), ligne._unite);
  else if (col.type === "nombre") contenu = quantite(Number(v));
  else if (col.type === "montant") contenu = montant(v);
  else if (col.type === "date") contenu = date(v);
  else if (col.type === "dateheure") contenu = dateHeureCourte(v);
  else if (col.type === "pill") contenu = <span className={`pill ${PILL[ton] ?? "p-g"}`}>{v}</span>;
  else if (col.type === "code") contenu = <span className="code">{v}</span>;
  else contenu = v;
  const classes = [A_DROITE.has(col.type) ? "droite num" : "", col.cle === "article" ? "nom" : "",
    ton && col.type !== "pill" ? TEXTE[ton] : ""].filter(Boolean).join(" ");
  return (
    <td className={classes}>
      {contenu}
      {detail && <small className="detail-cellule">{detail}</small>}
    </td>
  );
}

/** Les sections d'un rapport, avec leurs sous-totaux et le total général. */
function TableauRapport({ rapport, onArticle }) {
  const cols = rapport.colonnes;
  const plusieurs = rapport.sections.length > 1;
  if (!rapport.sections.length || rapport.sections.every((s) => !s.lignes.length && !s.titre)) {
    return <div className="card vide-rapport">{rapport.vide || "Rien à afficher."}</div>;
  }
  return (
    <div className="card rapport-carte">
      <table className="tableau rapport-table">
        <thead>
          <tr>{cols.map((c) => <th key={c.cle} className={A_DROITE.has(c.type) ? "droite" : ""}>{c.titre}</th>)}</tr>
        </thead>
        {rapport.sections.map((s, i) => (
          <tbody key={i}>
            {s.titre && <tr className="rapport-section"><td colSpan={cols.length}>{s.titre}</td></tr>}
            {s.lignes.map((l, j) => (
              <tr key={j} className={`${l._fond ? "ligne-alerte-fond" : ""} ${l._id && onArticle ? "cliquable" : ""}`}
                onClick={l._id && onArticle ? () => onArticle(l._id) : undefined}
                title={l._id && onArticle ? "Voir la fiche de l'article" : undefined}>
                {cols.map((c) => <Cellule key={c.cle} col={c} ligne={l} />)}
              </tr>
            ))}
            {!s.lignes.length && <tr><td colSpan={cols.length} className="vide">{s.vide || rapport.vide || "Rien à afficher."}</td></tr>}
            {s.total && <tr className="rapport-total">{cols.map((c) => <Cellule key={c.cle} col={c} ligne={s.total} total />)}</tr>}
          </tbody>
        ))}
        {rapport.total && (plusieurs || !rapport.sections[0]?.total) && (
          <tfoot>
            <tr className="rapport-total general">{cols.map((c) => <Cellule key={c.cle} col={c} ligne={rapport.total} total />)}</tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

/** Boutons PDF et Excel (téléchargement), avec un petit état « en cours ». */
function BoutonsFichier({ cle, reglages, onErreur, grands }) {
  const [enCours, setEnCours] = useState(null);
  async function telecharger(fichier) {
    setEnCours(fichier); onErreur(null);
    try { await telechargerRapport(cle, reglages, fichier); } catch (e) { onErreur(e.message); } finally { setEnCours(null); }
  }
  return (
    <>
      <button type="button" className={`btn ${grands ? "" : "rapport-btn"}`} disabled={!!enCours} onClick={() => telecharger("pdf")}
        title="Télécharger en PDF (pour imprimer ou envoyer)">
        <Icon name="doc" size={18} />{enCours === "pdf" ? "PDF…" : "PDF"}
      </button>
      <button type="button" className={`btn ${grands ? "" : "rapport-btn"}`} disabled={!!enCours} onClick={() => telecharger("xlsx")}
        title="Télécharger en Excel (pour retravailler les chiffres)">
        <Icon name="excel" size={18} />{enCours === "xlsx" ? "Excel…" : "Excel"}
      </button>
    </>
  );
}

/** Encadré « Notes » sous le tableau (16/10/2026) : définitions (terme : texte) puis points d'attention. */
export function NotesRapport({ notes }) {
  const liste = (notes ?? []).map((n) => (typeof n === "string" ? { texte: n } : n));
  if (!liste.length) return null;
  const definitions = liste.filter((n) => !n.alerte);
  const alertes = liste.filter((n) => n.alerte);
  return (
    <aside className="rapport-notes" aria-label="Notes">
      <div className="rapport-notes-titre">Notes</div>
      <dl>
        {definitions.map((n, i) => (
          <div key={i} className="rapport-notes-ligne">{n.terme && <dt>{n.terme}</dt>}<dd className={n.terme ? undefined : "seule"}>{n.texte}</dd></div>
        ))}
        {alertes.map((n, i) => (
          <div key={`a${i}`} className="rapport-notes-ligne alerte"><dt>À noter</dt><dd>{n.texte}</dd></div>
        ))}
      </dl>
    </aside>
  );
}

/** Fenêtre d'un rapport : les filtres, le résumé, le tableau, les notes. */
function FenetreRapport({ info, catalogue, onFermer }) {
  const [reglages, setReglages] = useState({});
  const [rapport, setRapport] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [fiche, setFiche] = useState(null);
  const filtres = info.filtres;
  const regler = (k, v) => setReglages((r) => ({ ...r, [k]: v }));

  useEffect(() => {
    let annule = false;
    setChargement(true);
    lireRapport(info.cle, reglages)
      .then((r) => { if (!annule) { setRapport(r); setErreur(null); } })
      .catch(() => !annule && setErreur("Impossible de joindre le serveur. Vérifiez que la fenêtre du backend (runserver) est ouverte."))
      .finally(() => !annule && setChargement(false));
    return () => { annule = true; };
  }, [info.cle, reglages]);

  useEffect(() => {
    const echap = (e) => { if (e.key === "Escape" && !fiche) onFermer(); };
    document.addEventListener("keydown", echap);
    return () => document.removeEventListener("keydown", echap);
  }, [onFermer, fiche]);

  const periode = reglages.periode ?? (info.cle === "consommation" ? "mois" : "");
  return (
    <>
      <div className="voile" onClick={onFermer} />
      <div className="fenetre fenetre-rapport" role="dialog" aria-modal="true" aria-label={rapport?.titre ?? info.titre}>
        <div className="fenetre-tete">
          <span className={`rapport-icone ${info.ton}`}><Icon name={info.icone} size={22} /></span>
          <h2>{rapport?.titre ?? info.titre}</h2>
          <span className="sp" />
          <div className="rapport-actions">
            <BoutonsFichier cle={info.cle} reglages={reglages} onErreur={setErreur} grands />
          </div>
          <button className="fermer" type="button" onClick={onFermer} aria-label="Fermer"><Icon name="x" /></button>
        </div>
        <div className="fenetre-corps">
          <div className="barre">
            {filtres.includes("magasin") && (
              <ListeDeroulante className="filtre" ariaLabel="Magasin" recherche={false} valeur={reglages.magasin ?? ""}
                onChange={(v) => regler("magasin", v)}
                options={[{ valeur: "", libelle: "Magasin : Tous" },
                  ...catalogue.magasins.map((m) => ({ valeur: String(m.id), libelle: m.nom, texte: `Magasin : ${m.nom}` }))]} />
            )}
            {filtres.includes("categorie") && (
              <ListeDeroulante className="filtre filtre-large" ariaLabel="Catégorie" valeur={reglages.categorie ?? ""}
                onChange={(v) => regler("categorie", v)}
                options={[{ valeur: "", libelle: "Catégorie : Toutes" },
                  ...catalogue.categories.map((c) => ({ valeur: String(c.id), libelle: c.nom, texte: `Catégorie : ${c.nom}` }))]} />
            )}
            {filtres.includes("periode") && (
              <ListeDeroulante className="filtre filtre-large" ariaLabel="Période" recherche={false} valeur={periode}
                onChange={(v) => regler("periode", v)}
                options={catalogue.periodes.map((p) => ({ valeur: p.valeur, libelle: p.libelle, texte: `Période : ${p.libelle}` }))} />
            )}
            {filtres.includes("periode") && periode === "choisie" && (
              <>
                <label className="date-filtre">Du <input type="date" className="saisie" value={reglages.du ?? ""}
                  onChange={(e) => regler("du", e.target.value)} /></label>
                <label className="date-filtre">au <input type="date" className="saisie" value={reglages.au ?? ""}
                  onChange={(e) => regler("au", e.target.value)} /></label>
              </>
            )}
            {filtres.includes("regrouper") && (
              <ListeDeroulante className="filtre filtre-large" ariaLabel="Regrouper par" recherche={false}
                valeur={reglages.regrouper ?? "chantier"} onChange={(v) => regler("regrouper", v)}
                options={[{ valeur: "chantier", libelle: "Par chantier", texte: "Regrouper : par chantier" },
                  { valeur: "service", libelle: "Par service demandeur", texte: "Regrouper : par service" }]} />
            )}
            {filtres.includes("horizon") && (
              <ListeDeroulante className="filtre filtre-large" ariaLabel="Échéance" recherche={false}
                valeur={reglages.horizon ?? "90"} onChange={(v) => regler("horizon", v)}
                options={catalogue.horizons.map((h) => ({ valeur: h.valeur, libelle: h.libelle }))} />
            )}
            {Object.values(reglages).some(Boolean) && (
              <button className="btn lien effacer" type="button" onClick={() => setReglages({})}>
                <Icon name="x" size={14} stroke={2.2} />Effacer
              </button>
            )}
          </div>

          {erreur && <div className="alerte">{erreur}</div>}
          {rapport && (
            <div className={`rapport-entete ${chargement ? "en-chargement" : ""}`}>
              <span className="rapport-sous-titre">{rapport.sous_titre}</span>
              <div className="rapport-resume">
                {rapport.resume.map(([libelle, valeur]) => <span key={libelle}>{libelle} <b>{valeur}</b></span>)}
              </div>
            </div>
          )}
          {!rapport && chargement && <div className="card vide-rapport">Chargement…</div>}
          {rapport && (
            <div className={chargement ? "en-chargement" : ""}>
              <TableauRapport rapport={rapport} onArticle={setFiche} />
              <NotesRapport notes={rapport.notes} />
            </div>
          )}
        </div>
      </div>
      {fiche && <div className="fiche-au-dessus"><FicheArticle id={fiche} modifiable={false} onFermer={() => setFiche(null)} onModifie={() => {}} /></div>}
    </>
  );
}

export default function Rapports() {
  const [catalogue, setCatalogue] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [ouvert, setOuvert] = useState(null);
  const fermer = useCallback(() => setOuvert(null), []);

  useEffect(() => {
    lireCatalogueRapports().then(setCatalogue)
      .catch(() => setErreur("Impossible de joindre le serveur. Vérifiez que la fenêtre du backend (runserver) est ouverte."));
  }, []);

  return (
    <>
      <header className="top"><h1>Générer Rapports</h1></header>
      <div className="body rapports">
        <p className="rapports-intro">Choisissez un rapport : <b>Voir</b> l'affiche à l'écran (avec des filtres),
          <b> PDF</b> le prépare pour l'imprimer ou l'envoyer, <b>Excel</b> pour retravailler les chiffres.</p>
        {erreur && <div className="alerte">{erreur}</div>}
        <div className="rapports-grille">
          {catalogue?.rapports.map((r) => (
            <section key={r.cle} className="card rapport-tuile">
              <span className={`rapport-icone ${r.ton}`}><Icon name={r.icone} size={24} /></span>
              <h2>{r.titre}</h2>
              <p>{r.description}</p>
              <div className="rapport-boutons">
                <button type="button" className="btn pri rapport-btn" onClick={() => setOuvert(r)}>
                  <Icon name="oeil" size={18} />Voir
                </button>
                <BoutonsFichier cle={r.cle} reglages={{}} onErreur={setErreur} />
              </div>
            </section>
          ))}
        </div>
      </div>
      {ouvert && catalogue && <FenetreRapport info={ouvert} catalogue={catalogue} onFermer={fermer} />}
    </>
  );
}
