import { useEffect, useState } from "react";
import { lireJournalComptes } from "../api.js";
import Icon from "../icons.jsx";
import ListeDeroulante from "../ListeDeroulante.jsx";

const PILL = { rouge: "p-c", orange: "p-w", vert: "p-ok", gris: "p-g", violet: "p-i" };

function quand(iso) {
  const d = new Date(iso);
  const deux = (n) => String(n).padStart(2, "0");
  const annee = d.getFullYear() !== new Date().getFullYear() ? `/${d.getFullYear()}` : "";
  return `${deux(d.getDate())}/${deux(d.getMonth() + 1)}${annee} ${deux(d.getHours())}:${deux(d.getMinutes())}`;
}

/** Onglets « Historique des comptes » et « Journal de connexion » de l'écran « Comptes » (administrateur, 15/10/2026).
 *  Lecture seule : personne ne peut modifier ni effacer ces lignes. */
export default function JournalComptes({ vue }) {
  const connexions = vue === "connexions";
  const [filtres, setFiltres] = useState({ periode: "mois" });
  const [recherche, setRecherche] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [donnees, setDonnees] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState(null);
  const regler = (k, v) => { setPage(1); setFiltres((f) => ({ ...f, [k]: v })); };

  useEffect(() => {
    const minuteur = setTimeout(() => { setPage(1); setQ(recherche.trim()); }, 300);
    return () => clearTimeout(minuteur);
  }, [recherche]);

  useEffect(() => {
    let annule = false;
    setChargement(true);
    lireJournalComptes({ ...filtres, q, page, vue })
      .then((d) => { if (!annule) { setDonnees(d); setErreur(null); } })
      .catch(() => !annule && setErreur("Impossible de joindre le serveur. Vérifiez que la fenêtre du backend (runserver) est ouverte."))
      .finally(() => !annule && setChargement(false));
    return () => { annule = true; };
  }, [filtres, q, page, vue]);

  const lignes = donnees?.lignes ?? [];
  const debut = donnees ? (donnees.page - 1) * donnees.par_page + 1 : 0;
  const fin = donnees ? debut + lignes.length - 1 : 0;
  const filtreActif = q || filtres.compte || filtres.resultat || filtres.periode !== "mois";

  return (
    <>
      <div className="barre barre-historique">
        <label className="recherche">
          <Icon name="search" size={18} />
          <input type="search" placeholder={connexions ? "Nom, identifiant, adresse IP…" : "Nom, identifiant, détail…"} value={recherche}
            onChange={(e) => setRecherche(e.target.value)} aria-label="Rechercher" />
        </label>
        <ListeDeroulante className="filtre filtre-large" ariaLabel="Compte" valeur={filtres.compte ?? ""} onChange={(v) => regler("compte", v)}
          options={[{ valeur: "", libelle: "Compte : Tous" },
            ...(donnees?.comptes ?? []).map((c) => ({ valeur: String(c.id), libelle: c.nom, texte: `Compte : ${c.nom}` }))]} />
        {connexions && (
          <ListeDeroulante className="filtre" ariaLabel="Résultat" recherche={false} valeur={filtres.resultat ?? ""}
            onChange={(v) => regler("resultat", v)}
            options={[{ valeur: "", libelle: "Tout" }, { valeur: "echecs", libelle: "Échecs seulement" }]} />
        )}
        <ListeDeroulante className="filtre filtre-large" ariaLabel="Période" recherche={false} valeur={filtres.periode}
          onChange={(v) => regler("periode", v)}
          options={(donnees?.periodes ?? [{ valeur: "mois", libelle: "Ce mois-ci" }]).map((p) => ({ valeur: p.valeur, libelle: p.libelle }))} />
        {filtres.periode === "choisie" && (
          <>
            <label className="date-filtre">Du <input type="date" className="saisie" value={filtres.du ?? ""} onChange={(e) => regler("du", e.target.value)} /></label>
            <label className="date-filtre">au <input type="date" className="saisie" value={filtres.au ?? ""} onChange={(e) => regler("au", e.target.value)} /></label>
          </>
        )}
        {filtreActif && (
          <button className="btn lien effacer" type="button" onClick={() => { setRecherche(""); setQ(""); setPage(1); setFiltres({ periode: "mois" }); }}>
            <Icon name="x" size={14} stroke={2.2} />Effacer
          </button>
        )}
      </div>

      {erreur && <div className="alerte">{erreur}</div>}

      <div className="card">
        <table className="tableau historique journal-comptes">
          <thead>
            <tr>
              <th style={{ width: 112 }}>Date</th>
              <th style={{ width: 200 }}>Événement</th>
              <th>Compte</th>
              {connexions ? <><th style={{ width: 140 }}>Adresse IP</th><th style={{ width: 150 }}>Appareil</th></>
                : <th style={{ width: 160 }}>Par</th>}
            </tr>
          </thead>
          <tbody className={chargement && donnees ? "en-chargement" : ""}>
            {lignes.map((l) => (
              <tr key={l.id}>
                <td className="quand">{quand(l.le)}</td>
                <td><span className={`pill ${PILL[l.ton] ?? "p-i"}`}>{l.evenement}</span></td>
                <td>
                  <span className="nom">{l.compte || <span className="discret">—</span>}</span>
                  {l.identifiant && <span className="code code-hist">{l.identifiant}</span>}
                  {l.detail && <small className="detail-cellule">{l.detail}</small>}
                </td>
                {connexions ? (
                  <><td className="code">{l.adresse_ip || <span className="discret">—</span>}</td>
                    <td>{l.appareil || <span className="discret">—</span>}</td></>
                ) : <td>{l.par || <span className="discret">—</span>}</td>}
              </tr>
            ))}
            {!chargement && donnees && lignes.length === 0 && (
              <tr><td colSpan={connexions ? 5 : 4} className="vide">Rien ({donnees.periode.libelle}){filtreActif ? " pour ces filtres" : ""}. Choisissez une période plus longue.</td></tr>
            )}
            {chargement && !donnees && <tr><td colSpan={5} className="vide">Chargement…</td></tr>}
          </tbody>
        </table>
        <div className="pied">
          <span>
            {donnees ? (donnees.count ? `${debut} à ${fin} sur ${donnees.count} ligne${donnees.count > 1 ? "s" : ""}` : "0 ligne")
              + ` · ${donnees.periode.libelle}` : "Chargement…"}
          </span>
          <div className="pages">
            <button className="btn" type="button" disabled={!donnees || donnees.page <= 1 || chargement} onClick={() => setPage(donnees.page - 1)}>← Page précédente</button>
            <button className="btn" type="button" disabled={!donnees || donnees.page >= donnees.pages || chargement} onClick={() => setPage(donnees.page + 1)}>Page suivante →</button>
          </div>
        </div>
      </div>
    </>
  );
}
