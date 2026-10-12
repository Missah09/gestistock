import { useEffect, useMemo, useState } from "react";
import ListeDeroulante from "../ListeDeroulante.jsx";
import { envoyerDemande, lireChoixDemande } from "../api.js";
import { manque, quantite, LIBELLE_PRETE, ETATS_UTILISABLES, texteEtats } from "../format.js";
import Icon from "../icons.jsx";
import ChoixArticle from "./ChoixArticle.jsx";

const premier = (x) => (Array.isArray(x) ? x[0] : x);
const ligneVide = () => ({ cle: Math.random(), article: "", quantite: "", date_retour_prevue: "", motif: "" });
const UNITES = { m: "m", paire: "paire(s)", piece: "pièce(s)" };
const deux = (n) => String(n).padStart(2, "0");
const isoJour = (d) => `${d.getFullYear()}-${deux(d.getMonth() + 1)}-${deux(d.getDate())}`;

/** Fenêtre « Nouvelle demande ». Tous les champs sont vides à l'ouverture.
 *  La date et l'heure de la demande viennent du serveur (pas de l'horloge du PC) et s'affichent près du titre. */
export default function NouvelleDemande({ onFermer, onEnvoyee }) {
  const [choix, setChoix] = useState(null);
  const [entete, setEntete] = useState({ magasin: "", chantier: "", urgent: false });
  const [lignes, setLignes] = useState([ligneVide()]);
  const [erreurs, setErreurs] = useState({});
  const [envoi, setEnvoi] = useState(false);
  const [decalage, setDecalage] = useState(null); // heure du serveur − heure du PC, en millisecondes
  const [, setTic] = useState(0);

  useEffect(() => {
    lireChoixDemande()
      .then((c) => { setChoix(c); setDecalage(new Date(c.maintenant).getTime() - Date.now()); })
      .catch(() => setErreurs({ general: ["Impossible de charger les listes. Vérifiez que le serveur est démarré."] }));
  }, []);

  // L'heure affichée avance toute seule (rafraîchie toutes les 15 s).
  useEffect(() => {
    const minuteur = setInterval(() => setTic((x) => x + 1), 15_000);
    return () => clearInterval(minuteur);
  }, []);
  const maintenant = decalage === null ? null : new Date(Date.now() + decalage);

  useEffect(() => {
    const touche = (e) => e.key === "Escape" && !envoi && onFermer();
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi]);

  const articlesDuMagasin = useMemo(
    () => (choix && entete.magasin ? choix.articles.filter((a) => String(a.magasin) === String(entete.magasin)) : []),
    [choix, entete.magasin]
  );
  const article = (id) => choix?.articles.find((a) => String(a.id) === String(id));
  const estPrete = (id) => article(id)?.type === "PRETE";
  // « Retour prévu » n'existe que pour le matériel prêté : la colonne n'apparaît que s'il y en a sur la demande.
  const colonneRetour = lignes.some((l) => estPrete(l.article));

  function changerEntete(champ, valeur) {
    if (erreurs[champ] || erreurs.general) setErreurs({ ...erreurs, [champ]: undefined, general: undefined });
    setEntete({ ...entete, [champ]: valeur });
  }
  function changerMagasin(valeur) {
    // Les articles dépendent du magasin : on repart d'une liste vide.
    changerEntete("magasin", valeur);
    setLignes([ligneVide()]);
  }
  function changerLigne(i, champ, valeur) {
    if (erreurs.general || erreurs.lignes?.[i]?.[champ] || (champ === "article" && erreurs.lignes?.[i])) {
      const lignesErr = erreurs.lignes ? [...erreurs.lignes] : undefined;
      if (lignesErr?.[i]) lignesErr[i] = champ === "article" ? {} : { ...lignesErr[i], [champ]: undefined };
      setErreurs({ ...erreurs, general: undefined, lignes: lignesErr });
    }
    setLignes(lignes.map((l, j) => {
      if (j !== i) return l;
      const n = { ...l, [champ]: valeur };
      if (champ === "article" && !estPrete(valeur)) n.date_retour_prevue = ""; // consommable : pas de retour
      return n;
    }));
  }
  function retirer(i) {
    if (erreurs.lignes) setErreurs({ ...erreurs, lignes: undefined }); // les n° de ligne des erreurs ne correspondent plus
    setLignes(lignes.length > 1 ? lignes.filter((_, j) => j !== i) : [ligneVide()]);
  }

  async function envoyer(e) {
    e.preventDefault();
    setEnvoi(true); setErreurs({});
    const donnees = {
      magasin: entete.magasin ? Number(entete.magasin) : null,
      chantier: entete.chantier ? Number(entete.chantier) : null,
      urgent: entete.urgent,
      lignes: lignes
        .filter((l) => l.article || l.quantite || l.date_retour_prevue || l.motif.trim())
        .map((l) => ({
          article: l.article ? Number(l.article) : null,
          quantite: l.quantite === "" ? null : Number(l.quantite),
          date_retour_prevue: estPrete(l.article) && l.date_retour_prevue ? l.date_retour_prevue : null,
          motif: l.motif,
        })),
    };
    try {
      const r = await envoyerDemande(donnees);
      onEnvoyee(r.message);
    } catch (err) {
      const details = err.details ?? { general: ["L'envoi a échoué. Vérifiez que le serveur est démarré."] };
      // Le serveur peut renvoyer les erreurs de lignes sous forme { "0": {...} } : on en fait une liste.
      if (details.lignes && !Array.isArray(details.lignes)) {
        details.lignes = Array.from({ length: donnees.lignes.length }, (_, i) => details.lignes[i] ?? {});
      }
      setErreurs(details);
    } finally {
      setEnvoi(false);
    }
  }

  const err = (champ) => premier(erreurs[champ]);
  const errLigne = (i, champ) => premier(erreurs.lignes?.[i]?.[champ]);
  const aCorriger = Boolean(err("general") || err("magasin") || err("chantier")
    || (erreurs.lignes ?? []).some((x) => x && Object.values(x).some(Boolean)));

  return (
    <>
      <div className="voile" onClick={() => !envoi && onFermer()} />
      <form className="fenetre large" role="dialog" aria-modal="true" aria-label="Nouvelle demande" onSubmit={envoyer} noValidate>
        <div className="fenetre-tete">
          <h2>Nouvelle demande</h2>
          {maintenant && (
            <span className="horodatage" title="Date et heure du serveur. La demande est datée au moment de l'envoi.">
              <Icon name="clock" size={17} stroke={2} />
              {deux(maintenant.getDate())}/{deux(maintenant.getMonth() + 1)}/{maintenant.getFullYear()} à {maintenant.getHours()} h {deux(maintenant.getMinutes())}
            </span>
          )}
          <button className="fermer" type="button" onClick={onFermer} aria-label="Fermer"><Icon name="x" size={22} stroke={2.2} /></button>
        </div>

        <div className="fenetre-corps">
          {aCorriger && (
            <div className="alerte">{err("general") ?? "Certaines informations sont à compléter ou à corriger (en rouge ci-dessous)."}</div>
          )}

          {!choix ? <p className="vide">{erreurs.general ? "" : "Chargement…"}</p> : (
            <>
              <div className="entete-grille">
                <label className={err("magasin") ? "en-erreur" : ""}>
                  <span>Magasin</span>
                  <ListeDeroulante ariaLabel="Magasin" placeholder="— Choisir le magasin —" valeur={entete.magasin} onChange={changerMagasin}
                    invalide={Boolean(err("magasin"))}
                    options={choix.magasins.map((m) => ({ valeur: String(m.id), libelle: m.type === "CHANTIER" ? `Chantier : ${m.nom}` : m.nom }))} />
                  {err("magasin") && <em className="msg-erreur">{err("magasin")}</em>}
                </label>
                <label className={err("chantier") ? "en-erreur" : ""}>
                  <span>Chantier <i className="facultatif">(facultatif)</i></span>
                  <ListeDeroulante ariaLabel="Chantier" placeholder="— Choisir le chantier —" valeur={entete.chantier}
                    onChange={(v) => changerEntete("chantier", v)} invalide={Boolean(err("chantier"))} texteAucun="Aucun chantier"
                    options={[{ valeur: "", libelle: "— Aucun chantier —", texte: "" },
                      ...choix.chantiers.map((c) => ({ valeur: String(c.id), libelle: c.nom }))]} />
                  {err("chantier") && <em className="msg-erreur">{err("chantier")}</em>}
                </label>
              </div>

              <div className="lignes">
                <table className="tableau">
                  <thead>
                    <tr>
                      <th style={{ width: "29%" }}>Article demandé</th>
                      <th style={{ width: "14%" }}>Qté disponible</th>
                      <th style={{ width: "13%" }}>Qté demandée</th>
                      {colonneRetour && <th style={{ width: "15%" }}>Retour prévu</th>}
                      <th>Motif <i className="facultatif">(facultatif)</i></th>
                      <th style={{ width: 52 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {lignes.map((l, i) => {
                      const a = article(l.article);
                      const prete = a?.type === "PRETE";
                      const q = Number(l.quantite) || 0;
                      const insuffisant = a ? manque(q, a.qte_disponible) : null;
                      return (
                        <tr key={l.cle}>
                          <td>
                            <ChoixArticle articles={articlesDuMagasin} valeur={l.article} desactive={!entete.magasin}
                              invalide={Boolean(errLigne(i, "article"))} dejaPris={lignes.map((x) => x.article).filter(Boolean)}
                              texteVide={entete.magasin ? "Taper un nom ou un code, ou choisir…" : "Choisissez d'abord le magasin"}
                              onChoisir={(v) => changerLigne(i, "article", v)} />
                            {errLigne(i, "article") && <em className="msg-erreur">{errLigne(i, "article")}</em>}
                            {prete && !errLigne(i, "article") && <span className="pill p-i petite-pill">{LIBELLE_PRETE}</span>}
                          </td>
                          <td className="dispo">
                            {!a ? <span className="discret">—</span> : (
                              <>
                                <b className={insuffisant ? "rouge" : "vert"}>{quantite(a.qte_disponible, a.unite)}</b>
                                {insuffisant && <span className="pill p-c">{insuffisant}</span>}
                                {texteEtats(a.etats, ETATS_UTILISABLES) && <small className="etat-ligne">{texteEtats(a.etats, ETATS_UTILISABLES, a.unite)}</small>}
                              </>
                            )}
                          </td>
                          <td>
                            <div className="avec-unite">
                              <input className={`saisie petite${errLigne(i, "quantite") ? " invalide" : ""}`} type="number" min="1" step="1"
                                value={l.quantite} disabled={!entete.magasin} aria-label="Qté demandée"
                                onChange={(e) => changerLigne(i, "quantite", e.target.value)} />
                              {a && <small>{UNITES[a.unite] ?? a.unite}</small>}
                            </div>
                            {errLigne(i, "quantite") && <em className="msg-erreur">{errLigne(i, "quantite")}</em>}
                          </td>
                          {colonneRetour && (
                            <td>
                              {prete && (
                                <>
                                  <input className={`saisie petite${errLigne(i, "date_retour_prevue") ? " invalide" : ""}`} type="date"
                                    min={maintenant ? isoJour(maintenant) : undefined} value={l.date_retour_prevue}
                                    aria-label="Retour prévu" aria-required="true"
                                    onChange={(e) => changerLigne(i, "date_retour_prevue", e.target.value)} />
                                  {errLigne(i, "date_retour_prevue") && <em className="msg-erreur">{errLigne(i, "date_retour_prevue")}</em>}
                                </>
                              )}
                            </td>
                          )}
                          <td>
                            <input className={`saisie petite motif${errLigne(i, "motif") ? " invalide" : ""}`} maxLength={250}
                              value={l.motif} disabled={!a} aria-label="Motif"
                              onChange={(e) => changerLigne(i, "motif", e.target.value)} />
                            {errLigne(i, "motif") && <em className="msg-erreur">{errLigne(i, "motif")}</em>}
                          </td>
                          <td>
                            <button type="button" className="btn-icone" onClick={() => retirer(i)} aria-label="Retirer cette ligne" title="Retirer cette ligne">
                              <Icon name="x" size={16} stroke={2.2} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <button type="button" className="btn lien ajouter" disabled={!entete.magasin}
                  onClick={() => { setErreurs({ ...erreurs, general: undefined, lignes: undefined }); setLignes([...lignes, ligneVide()]); }}>
                  <Icon name="plus" size={18} stroke={2.4} />Ajouter un article
                </button>
              </div>
            </>
          )}
        </div>

        <div className="fiche-pied">
          <label className="btn case urgent">
            <input type="checkbox" checked={entete.urgent} onChange={(e) => changerEntete("urgent", e.target.checked)} />
            Urgent
          </label>
          <span className="sp" />
          <button key="annuler" className="btn" type="button" onClick={onFermer} disabled={envoi}>Annuler</button>
          <button key="envoyer" className="btn pri" type="submit" disabled={envoi || !choix}>
            {envoi ? "Envoi…" : "Envoyer la demande"}
          </button>
        </div>
      </form>
    </>
  );
}
