import { useEffect, useRef, useState } from "react";
import ListeDeroulante from "../ListeDeroulante.jsx";
import { passerSuiviSerie } from "../api.js";
import { ETATS_PRODUIT, ORDRE_ETATS, quantite, texteEtats } from "../format.js";

const premier = (x) => (Array.isArray(x) ? x[0] : x);
const OPTIONS_ETAT = ORDRE_ETATS.map((e) => ({ valeur: e, libelle: ETATS_PRODUIT[e].libelle }));

/** Fenêtre « Passer au suivi par n° de série » (15/10/2026) : ouverte depuis la fiche d'un article suivi par quantité
 *  (Agent Logistique et administrateur), ou depuis « Entrée en stock » (« Ce produit a des n° de série ? », depuisEntree).
 *  Depuis le 26/10/2026, aussi pour un consommable compté à la pièce (box ONT…) : sans code immo ni étalonnage. Une ligne par unité au magasin, l'état déjà rempli
 *  d'après le stock actuel ; on saisit le n° de série (obligatoire), le code immo et l'étalonnage (facultatifs).
 *  Le stock ne change pas ; le choix est définitif. Refusé par le serveur si des unités prêtées ne sont pas rendues. */
export default function PasserSuiviSerie({ article, onFermer, onPasse, depuisEntree = false }) {
  const prete = article.type === "PRETE";
  const [lignes, setLignes] = useState(() => ORDRE_ETATS.flatMap((e) =>
    Array.from({ length: article.repartition?.etats?.[e] ?? 0 }, () => ({ numero_serie: "", code_immo: "", date_etalonnage: "", etat: e }))));
  const [erreurs, setErreurs] = useState({});
  const [envoi, setEnvoi] = useState(false);
  const champs = useRef([]);
  const stock = article.qte_disponible;

  useEffect(() => {
    const touche = (e) => e.key === "Escape" && !envoi && onFermer();
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi]);
  useEffect(() => { champs.current[0]?.focus(); }, []);

  const changer = (i, cle, v) => {
    setLignes((ls) => ls.map((l, j) => (j === i ? { ...l, [cle]: v } : l)));
    setErreurs((e) => (e.exemplaires?.[i]?.[cle] ? { ...e, exemplaires: e.exemplaires.map((x, j) => (j === i ? { ...x, [cle]: undefined } : x)) } : e));
  };
  const errLigne = (i, cle) => premier(erreurs.exemplaires?.[i]?.[cle]);
  const general = premier(erreurs.general);
  const enErreur = general || erreurs.exemplaires?.some((x) => x && Object.values(x).some(Boolean));
  const parEtat = lignes.reduce((t, l) => ({ ...t, [l.etat]: (t[l.etat] ?? 0) + 1 }), {});

  async function confirmer(e) {
    e.preventDefault();
    setEnvoi(true); setErreurs({});
    try {
      const fiche = await passerSuiviSerie(article.id, {
        exemplaires: lignes.map((l) => ({ ...l, numero_serie: l.numero_serie.trim(), code_immo: l.code_immo.trim(), date_etalonnage: l.date_etalonnage || null })),
      });
      onPasse(fiche);
    } catch (x) {
      setErreurs(x.details ?? { general: ["L'enregistrement a échoué. Vérifiez que le serveur est démarré."] });
      setEnvoi(false);
    }
  }

  return (
    <>
      <div className="voile par-dessus" onClick={() => !envoi && onFermer()} />
      <form className="fenetre compte suivi-serie par-dessus" role="dialog" aria-modal="true" aria-label="Passer au suivi par n° de série"
        onSubmit={confirmer} noValidate>
        <div className="fenetre-tete">
          <h2>Passer au suivi par n° de série</h2>
          <span className="code titre-pill">{article.code}</span>
        </div>
        <div className="fenetre-corps">
          <p className="intro"><b>{article.nom}</b> : {stock > 0
            ? <>{quantite(stock, article.unite)} au magasin ({texteEtats(article.repartition?.etats, ORDRE_ETATS, article.unite)}). Saisissez le n° de série de chaque unité.</>
            : depuisEntree
              ? <>aucune unité au magasin. Confirmez, puis saisissez les n° des unités reçues dans l'entrée en stock.</>
              : <>stock à 0. Aucun n° à saisir maintenant : ils seront demandés à la prochaine entrée en stock.</>}
          </p>
          {general && <div className="alerte">{general}</div>}
          {!general && enErreur && <div className="alerte">Certains n° sont à corriger (en rouge ci-dessous).</div>}

          {lignes.length > 0 && (
            <table className="tableau table-serie">
              <thead>
                <tr><th style={{ width: 36 }}>N°</th><th>N° de série *</th>{prete && <><th>Code immo</th><th style={{ width: 150 }}>Prochain étalonnage</th></>}<th style={{ width: 130 }}>État</th></tr>
              </thead>
              <tbody>
                {lignes.map((l, i) => (
                  <tr key={i}>
                    <td className="discret">{i + 1}</td>
                    <td>
                      <input ref={(el) => { champs.current[i] = el; }} className={`saisie petite${errLigne(i, "numero_serie") ? " invalide" : ""}`}
                        value={l.numero_serie} onChange={(e) => changer(i, "numero_serie", e.target.value)} aria-label={`N° de série de l'unité ${i + 1}`}
                        onKeyDown={(e) => { if (e.key === "Enter" && i < lignes.length - 1) { e.preventDefault(); champs.current[i + 1]?.focus(); } }} />
                      {errLigne(i, "numero_serie") && <em className="msg-erreur">{errLigne(i, "numero_serie")}</em>}
                    </td>
                    {prete && <>
                    <td>
                      <input className={`saisie petite${errLigne(i, "code_immo") ? " invalide" : ""}`} placeholder="Facultatif"
                        value={l.code_immo} onChange={(e) => changer(i, "code_immo", e.target.value)} aria-label={`Code immo de l'unité ${i + 1}`} />
                      {errLigne(i, "code_immo") && <em className="msg-erreur">{errLigne(i, "code_immo")}</em>}
                    </td>
                    <td>
                      <input className="saisie petite" type="date" value={l.date_etalonnage} onChange={(e) => changer(i, "date_etalonnage", e.target.value)}
                        aria-label={`Prochain étalonnage de l'unité ${i + 1}`} />
                    </td>
                    </>}
                    <td>
                      <ListeDeroulante petite ariaLabel={`État de l'unité ${i + 1}`} valeur={l.etat} options={OPTIONS_ETAT}
                        onChange={(v) => changer(i, "etat", v)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {lignes.length > 0 && <p className="aide">Total : {lignes.length} ({texteEtats(parEtat)}). Le stock reste à {quantite(stock, article.unite)}. Astuce : Entrée passe au n° suivant.</p>}
          <p className="aide attention-definitif">Ce choix est définitif : ensuite, chaque entrée en stock de cet article demandera les n° de série, et chaque sortie, les n° des {prete ? "appareils remis" : "unités remises (elles passent « Sorti (consommé) »)"}.</p>
        </div>
        <div className="fiche-pied">
          <span className="sp" />
          <button key="annuler" className="btn" type="button" onClick={onFermer} disabled={envoi}>Annuler</button>
          <button key="confirmer" className="btn pri" type="submit" disabled={envoi}>{envoi ? "Enregistrement…" : "Confirmer le passage"}</button>
        </div>
      </form>
    </>
  );
}
