import { useCallback, useEffect, useState } from "react";
import { exporterHistorique, lireHistorique } from "../api.js";
import Icon from "../icons.jsx";
import ListeDeroulante from "../ListeDeroulante.jsx";
import FicheArticle from "./FicheArticle.jsx";

/** Écran « Historique » (Responsable Technique, 15/10/2026), d'après la maquette (écran 11).
 *  Tous les mouvements, les plus récents d'abord : entrées, sorties, retours, corrections (avec le stock avant → après),
 *  les étapes du circuit (demande, validation, signature, impression du bon, annulations, bons de retour) et, depuis le
 *  15/10/2026, les modifications (fiches, articles créés, prix, administration : ancienne → nouvelle valeur).
 *  Les comptes et les connexions sont réservés à l'administrateur (écran « Comptes »). Personne ne peut les modifier.
 *  Filtres : recherche, type, utilisateur, période ; Excel et PDF reprennent les mêmes filtres. */

const PILL = { rouge: "p-c", orange: "p-w", vert: "p-ok", bleu: "e-neuf", gris: "p-g", violet: "p-i", sable: "e-moyen" };

/** « 15/10 08:42 » (l'année n'est ajoutée que si ce n'est pas l'année en cours). */
function quand(iso) {
  const d = new Date(iso);
  const deux = (n) => String(n).padStart(2, "0");
  const annee = d.getFullYear() !== new Date().getFullYear() ? `/${d.getFullYear()}` : "";
  return `${deux(d.getDate())}/${deux(d.getMonth() + 1)}${annee} ${deux(d.getHours())}:${deux(d.getMinutes())}`;
}

function complet(iso) {
  const d = new Date(iso);
  const deux = (n) => String(n).padStart(2, "0");
  return `${deux(d.getDate())}/${deux(d.getMonth() + 1)}/${d.getFullYear()} à ${d.getHours()} h ${deux(d.getMinutes())}`;
}

export default function Historique({ parametres }) {
  // Ouvert depuis le Tableau de bord (« Activité du jour » › Historique) : la période « Aujourd'hui ».
  const [filtres, setFiltres] = useState({ periode: parametres?.periode ?? "semaine" });
  const [recherche, setRecherche] = useState("");
  const [page, setPage] = useState(1);
  const [donnees, setDonnees] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState(null);
  const [enCours, setEnCours] = useState(null);
  const [fiche, setFiche] = useState(null);
  const regler = (k, v) => { setPage(1); setFiltres((f) => ({ ...f, [k]: v })); };

  // La recherche part 0,3 s après la dernière touche.
  const [q, setQ] = useState("");
  useEffect(() => {
    const minuteur = setTimeout(() => { setPage(1); setQ(recherche.trim()); }, 300);
    return () => clearTimeout(minuteur);
  }, [recherche]);

  useEffect(() => {
    let annule = false;
    const charger = (discret) => {
      if (document.hidden) return;
      if (!discret) setChargement(true);
      lireHistorique({ ...filtres, q, page })
        .then((d) => { if (!annule) { setDonnees(d); setErreur(null); } })
        .catch(() => !annule && setErreur("Impossible de joindre le serveur. Vérifiez que la fenêtre du backend (runserver) est ouverte."))
        .finally(() => !annule && setChargement(false));
    };
    charger(false);
    // Mis à jour toutes les 30 s (première page seulement : on ne déplace pas les lignes de celui qui lit plus loin).
    const minuteur = setInterval(() => page === 1 && charger(true), 30_000);
    return () => { annule = true; clearInterval(minuteur); };
  }, [filtres, q, page]);

  async function exporter(fichier) {
    setEnCours(fichier); setErreur(null);
    try { await exporterHistorique({ ...filtres, q }, fichier); } catch (e) { setErreur(e.message); } finally { setEnCours(null); }
  }

  const fermerFiche = useCallback(() => setFiche(null), []);
  const filtreActif = q || filtres.type || filtres.utilisateur || filtres.periode !== "semaine";
  const lignes = donnees?.lignes ?? [];
  const debut = donnees ? (donnees.page - 1) * donnees.par_page + 1 : 0;
  const fin = donnees ? debut + lignes.length - 1 : 0;

  return (
    <>
      <header className="top">
        <h1>Historique</h1>
        <button type="button" className="btn" disabled={!!enCours || !donnees?.count} onClick={() => exporter("xlsx")}
          title="Toutes les lignes affichées par ces filtres, dans un fichier Excel">
          <Icon name="excel" size={18} />{enCours === "xlsx" ? "Excel…" : "Excel"}
        </button>
        <button type="button" className="btn" disabled={!!enCours || !donnees?.count} onClick={() => exporter("pdf")}
          title="Toutes les lignes affichées par ces filtres, en PDF">
          <Icon name="doc" size={18} />{enCours === "pdf" ? "PDF…" : "PDF"}
        </button>
      </header>
      <div className="body">
        <div className="barre barre-historique">
          <label className="recherche">
            <Icon name="search" size={18} />
            <input type="search" placeholder="Article, n° de bon, personne…" value={recherche}
              onChange={(e) => setRecherche(e.target.value)} aria-label="Rechercher dans l'historique" />
          </label>
          <ListeDeroulante className="filtre" ariaLabel="Type" recherche={false} valeur={filtres.type ?? ""}
            onChange={(v) => regler("type", v)}
            options={[{ valeur: "", libelle: "Type : Tous" },
              ...(donnees?.types ?? []).map((t) => ({ valeur: t.valeur, libelle: t.libelle, texte: `Type : ${t.libelle}` }))]} />
          <ListeDeroulante className="filtre filtre-large" ariaLabel="Utilisateur" valeur={filtres.utilisateur ?? ""}
            onChange={(v) => regler("utilisateur", v)}
            options={[{ valeur: "", libelle: "Utilisateur : Tous" },
              ...(donnees?.utilisateurs ?? []).map((u) => ({ valeur: String(u.id), libelle: u.nom, texte: `Utilisateur : ${u.nom}` }))]} />
          <ListeDeroulante className="filtre filtre-large" ariaLabel="Période" recherche={false} valeur={filtres.periode}
            onChange={(v) => regler("periode", v)}
            options={(donnees?.periodes ?? [{ valeur: "semaine", libelle: "Cette semaine" }])
              .map((p) => ({ valeur: p.valeur, libelle: p.libelle }))} />
          {filtres.periode === "choisie" && (
            <>
              <label className="date-filtre">Du <input type="date" className="saisie" value={filtres.du ?? ""}
                onChange={(e) => regler("du", e.target.value)} /></label>
              <label className="date-filtre">au <input type="date" className="saisie" value={filtres.au ?? ""}
                onChange={(e) => regler("au", e.target.value)} /></label>
            </>
          )}
          {filtreActif && (
            <button className="btn lien effacer" type="button"
              onClick={() => { setRecherche(""); setQ(""); setPage(1); setFiltres({ periode: "semaine" }); }}>
              <Icon name="x" size={14} stroke={2.2} />Effacer
            </button>
          )}
        </div>

        {erreur && <div className="alerte">{erreur}</div>}

        <div className="card">
          <table className="tableau historique">
            <thead>
              <tr>
                <th style={{ width: 112 }}>Date</th>
                <th style={{ width: 128 }}>Type</th>
                <th>Article</th>
                <th className="droite" style={{ width: 100 }}>Quantité</th>
                <th style={{ width: 160 }}>Stock avant → après</th>
                <th style={{ width: 150 }}>Référence</th>
                <th style={{ width: 140 }}>Par</th>
              </tr>
            </thead>
            <tbody className={chargement && donnees ? "en-chargement" : ""}>
              {lignes.map((l, i) => (
                <tr key={`${l.le}-${i}`} className={l.article_id ? "cliquable" : ""}
                  onClick={l.article_id ? () => setFiche(l.article_id) : undefined}
                  title={l.article_id ? "Voir la fiche de l'article" : undefined}>
                  <td className="quand" title={complet(l.le)}>{quand(l.le)}</td>
                  <td><span className={`pill ${PILL[l._ton_type_libelle] ?? "p-g"}`}>{l.type_libelle}</span></td>
                  <td>
                    <span className="nom">{l.article}</span>
                    {l.code && <span className="code code-hist">{l.code}</span>}
                    {l.detail && <small className="detail-cellule">{l.detail}</small>}
                  </td>
                  <td className={`droite num ${l._ton_quantite === "vert" ? "vert" : l._ton_quantite === "rouge" ? "rouge" : ""}`}>
                    {l.quantite || <span className="discret">—</span>}
                  </td>
                  <td className="stock-hist">{l.stock || <span className="discret">—</span>}</td>
                  <td className="reference">{l.reference}</td>
                  <td>{l.par || <span className="discret">—</span>}</td>
                </tr>
              ))}
              {!chargement && donnees && lignes.length === 0 && (
                <tr><td colSpan={7} className="vide">
                  Aucun mouvement {donnees.periode.libelle ? `(${donnees.periode.libelle})` : ""}
                  {filtreActif ? " pour ces filtres." : "."} Choisissez une période plus longue, par exemple « Ce mois-ci ».
                </td></tr>
              )}
              {chargement && !donnees && <tr><td colSpan={7} className="vide">Chargement…</td></tr>}
            </tbody>
          </table>
          <div className="pied">
            <span>
              {donnees ? (donnees.count ? `${debut} à ${fin} sur ${donnees.count} ligne${donnees.count > 1 ? "s" : ""}` : "0 ligne")
                + ` · ${donnees.periode.libelle}` : "Chargement…"}
            </span>
            <div className="pages">
              <button className="btn" type="button" disabled={!donnees || donnees.page <= 1 || chargement}
                onClick={() => setPage(donnees.page - 1)}>← Page précédente</button>
              <button className="btn" type="button" disabled={!donnees || donnees.page >= donnees.pages || chargement}
                onClick={() => setPage(donnees.page + 1)}>Page suivante →</button>
            </div>
          </div>
        </div>
      </div>
      {fiche && <FicheArticle id={fiche} modifiable={false} onFermer={fermerFiche} onModifie={() => {}} />}
    </>
  );
}
