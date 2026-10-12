import { useEffect, useMemo, useState } from "react";
import ListeDeroulante from "../ListeDeroulante.jsx";
import ChoixArticle from "./ChoixArticle.jsx";
import NouvelArticle from "./NouvelArticle.jsx";
import { enregistrerEntree, lireChoix } from "../api.js";
import { montant } from "../format.js";
import Icon from "../icons.jsx";

// Date du jour en heure locale (toISOString donnerait la date UTC, fausse avant 3 h à Madagascar).
const aujourdhui = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const premier = (x) => (Array.isArray(x) ? x[0] : x);
// État du produit reçu (12/10/2026) : « Neuf » par défaut.
const ligneVide = () => ({ cle: Math.random(), article: "", quantite: "", prix_unitaire: "", series: "", etat: "NEUF" });
const UNITES = { m: "m", paire: "paire(s)", piece: "pièce(s)" };

/** Fenêtre « Entrée en stock » (anciennement « Enregistrer des produits », renommée le 12/10/2026) :
 *  réception d'une livraison, qui augmente le stock.
 *  - articleInitial : ouverte depuis la fiche d'un article, avec cet article déjà sur la 1re ligne.
 *  - Un article absent se crée depuis la liste des articles (« ＋ Créer l'article… ») : il est aussitôt placé sur la ligne. */
export default function EntreeStock({ onFermer, onEnregistre, articleInitial = null, onArticleCree }) {
  const [choix, setChoix] = useState(null);
  const [entete, setEntete] = useState({ fournisseur: "", numero_facture: "", date_reception: aujourdhui(), magasin: "" });
  const [lignes, setLignes] = useState([ligneVide()]);
  const [erreurs, setErreurs] = useState({});
  const [envoi, setEnvoi] = useState(false);
  const [creation, setCreation] = useState(null); // { ligne, nom } : fenêtre « Nouvel article » ouverte par-dessus
  const [info, setInfo] = useState(null);         // ex. « Article CAB-0049 créé et ajouté à la livraison. »

  useEffect(() => {
    lireChoix()
      .then((c) => {
        setChoix(c);
        const a = articleInitial && c.articles.find((x) => String(x.id) === String(articleInitial));
        if (a) {
          // Depuis la fiche : le magasin de l'article, et l'article sur la 1re ligne.
          setEntete((e) => ({ ...e, magasin: a.magasin }));
          setLignes([{ ...ligneVide(), article: String(a.id), prix_unitaire: a.prix_unitaire > 0 ? String(a.prix_unitaire) : "" }]);
        } else {
          setEntete((e) => ({ ...e, magasin: e.magasin || c.magasins[0]?.id || "" }));
        }
      })
      .catch(() => setErreurs({ general: ["Impossible de charger les listes. Vérifiez que le serveur est démarré."] }));
  }, []);

  useEffect(() => {
    const touche = (e) => e.key === "Escape" && !envoi && !creation && onFermer();
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi, creation]);

  /** Article créé depuis la ligne `creation.ligne` : on recharge les listes et on le place sur cette ligne. */
  async function articleCree(fiche) {
    const ligne = creation.ligne;
    setCreation(null);
    try { setChoix(await lireChoix()); } catch { /* la ligne garde l'id : l'enregistrement fonctionnera quand même */ }
    setLignes((ls) => ls.map((l, j) => (j === ligne
      ? { ...l, article: String(fiche.id), prix_unitaire: fiche.prix_unitaire > 0 ? String(fiche.prix_unitaire) : "" } : l)));
    setErreurs({});
    setInfo(`Article ${fiche.code} – ${fiche.nom} créé et ajouté à la livraison. Indiquez la quantité reçue.`);
    onArticleCree?.();
  }

  const articlesDuMagasin = useMemo(
    () => (choix ? choix.articles.filter((a) => String(a.magasin) === String(entete.magasin)) : []),
    [choix, entete.magasin]
  );
  const article = (id) => choix?.articles.find((a) => String(a.id) === String(id));
  // La colonne « N° de série » n'apparaît que si une ligne concerne un appareil suivi un par un.
  const colonneSerie = lignes.some((l) => article(l.article)?.suivi_serie);

  function changerMagasin(valeur) {
    // Les articles dépendent du magasin : on repart d'une liste vide.
    setEntete({ ...entete, magasin: valeur });
    setLignes([ligneVide()]);
  }
  function changerLigne(i, champ, valeur) {
    if (erreurs.general) setErreurs({}); // le message général ne correspond plus à la saisie en cours
    setLignes(lignes.map((l, j) => {
      if (j !== i) return l;
      const n = { ...l, [champ]: valeur };
      if (champ === "article") {
        const a = article(valeur);
        n.prix_unitaire = a && a.prix_unitaire > 0 ? String(a.prix_unitaire) : "";
      }
      if (champ === "series" && article(l.article)?.suivi_serie) {
        n.quantite = String(valeur.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean).length || "");
      }
      return n;
    }));
  }
  const retirer = (i) => setLignes(lignes.length > 1 ? lignes.filter((_, j) => j !== i) : [ligneVide()]);

  const total = lignes.reduce((t, l) => t + (Number(l.quantite) || 0) * (Number(l.prix_unitaire) || 0), 0);

  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true); setErreurs({});
    const donnees = {
      fournisseur: entete.fournisseur ? Number(entete.fournisseur) : null,
      numero_facture: entete.numero_facture,
      date_reception: entete.date_reception || null,
      magasin: entete.magasin ? Number(entete.magasin) : null,
      lignes: lignes
        .filter((l) => l.article || l.quantite)
        .map((l) => ({
          article: l.article ? Number(l.article) : null,
          quantite: l.quantite === "" ? null : Number(l.quantite),
          prix_unitaire: l.prix_unitaire === "" ? null : l.prix_unitaire,
          numeros_serie: l.series.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean),
          etat: l.etat,
        })),
    };
    try {
      const r = await enregistrerEntree(donnees);
      onEnregistre(r.message);
    } catch (err) {
      setErreurs(err.details ?? { general: ["L'enregistrement a échoué. Vérifiez que le serveur est démarré."] });
    } finally {
      setEnvoi(false);
    }
  }

  const errLigne = (i, champ) => premier(erreurs.lignes?.[i]?.[champ]);
  const err = (champ) => premier(erreurs[champ]);

  return (
    <>
      <div className="voile" onClick={() => !envoi && !creation && onFermer()} />
      <form className="fenetre" role="dialog" aria-modal="true" aria-label="Entrée en stock" onSubmit={enregistrer}>
        <div className="fenetre-tete">
          <h2>Entrée en stock</h2>
          <button className="fermer" type="button" onClick={onFermer} aria-label="Fermer"><Icon name="x" size={22} stroke={2.2} /></button>
        </div>

        <div className="fenetre-corps">
          {(err("general") || Object.keys(erreurs).length > 0) && (
            <div className="alerte">{err("general") ?? "Certaines informations sont à corriger (en rouge ci-dessous)."}</div>
          )}
          {info && Object.keys(erreurs).length === 0 && <div className="succes">{info}</div>}

          {!choix ? <p className="vide">Chargement…</p> : (
            <>
              <div className="entete-grille">
                <label className={err("fournisseur") ? "en-erreur" : ""}>
                  <span>Fournisseur</span>
                  <ListeDeroulante ariaLabel="Fournisseur" placeholder="— Non précisé —" valeur={entete.fournisseur}
                    onChange={(v) => setEntete({ ...entete, fournisseur: v })}
                    options={[{ valeur: "", libelle: "— Non précisé —" }, ...choix.fournisseurs.map((f) => ({ valeur: String(f.id), libelle: f.nom }))]} />
                </label>
                <label>
                  <span>N° de facture ou de bon de livraison</span>
                  <input className="saisie" value={entete.numero_facture} placeholder="Ex. FA-2026-0918"
                    onChange={(e) => setEntete({ ...entete, numero_facture: e.target.value })} />
                </label>
                <label className={err("date_reception") ? "en-erreur" : ""}>
                  <span>Date de réception</span>
                  <input className="saisie" type="date" value={entete.date_reception}
                    onChange={(e) => setEntete({ ...entete, date_reception: e.target.value })} />
                  {err("date_reception") && <em className="msg-erreur">{err("date_reception")}</em>}
                </label>
                <label className={err("magasin") ? "en-erreur" : ""}>
                  <span>Magasin</span>
                  <ListeDeroulante ariaLabel="Magasin" valeur={entete.magasin} onChange={changerMagasin} invalide={Boolean(err("magasin"))}
                    options={choix.magasins.map((m) => ({ valeur: String(m.id), libelle: m.type === "CHANTIER" ? `Chantier : ${m.nom}` : m.nom }))} />
                  {err("magasin") && <em className="msg-erreur">{err("magasin")}</em>}
                </label>
              </div>

              <div className="lignes">
                <table className="tableau">
                  <thead>
                    <tr><th style={{ width: "32%" }}>Article reçu</th><th style={{ width: "13%" }}>Quantité</th>
                      <th style={{ width: "15%" }}>Prix unitaire (Ar)</th><th style={{ width: "15%" }}>État</th>{colonneSerie && <th>N° de série</th>}<th style={{ width: 52 }} /></tr>
                  </thead>
                  <tbody>
                    {lignes.map((l, i) => {
                      const a = article(l.article);
                      return (
                        <tr key={l.cle}>
                          <td>
                            <ChoixArticle articles={articlesDuMagasin} valeur={l.article} invalide={Boolean(errLigne(i, "article"))}
                              dejaPris={lignes.map((x) => x.article).filter(Boolean)} texteDejaPris="Déjà sur la réception"
                              texteVide="Taper un nom ou un code, ou choisir…" onChoisir={(v) => changerLigne(i, "article", v)}
                              onCreer={(nom) => setCreation({ ligne: i, nom })} />
                            {errLigne(i, "article") && <em className="msg-erreur">{errLigne(i, "article")}</em>}
                          </td>
                          <td>
                            <div className="avec-unite">
                              <input className={`saisie petite${errLigne(i, "quantite") ? " invalide" : ""}`} type="number" min="1" step="1"
                                value={l.quantite} readOnly={a?.suivi_serie} title={a?.suivi_serie ? "Calculée à partir des n° de série" : undefined}
                                onChange={(e) => changerLigne(i, "quantite", e.target.value)} />
                              {a && <small>{UNITES[a.unite] ?? a.unite}</small>}
                            </div>
                            {errLigne(i, "quantite") && <em className="msg-erreur">{errLigne(i, "quantite")}</em>}
                          </td>
                          <td>
                            <input className={`saisie petite${errLigne(i, "prix_unitaire") ? " invalide" : ""}`} type="number" min="0" step="0.01"
                              placeholder="Facultatif" value={l.prix_unitaire} onChange={(e) => changerLigne(i, "prix_unitaire", e.target.value)} />
                            {errLigne(i, "prix_unitaire") && <em className="msg-erreur">{errLigne(i, "prix_unitaire")}</em>}
                          </td>
                          <td>
                            <ListeDeroulante ariaLabel="État du produit reçu" recherche={false} valeur={l.etat}
                              invalide={Boolean(errLigne(i, "etat"))} onChange={(v) => changerLigne(i, "etat", v)}
                              options={(choix.etats ?? []).map((e) => ({ valeur: e.valeur, libelle: e.libelle }))} />
                            {errLigne(i, "etat") && <em className="msg-erreur">{errLigne(i, "etat")}</em>}
                          </td>
                          {colonneSerie && <td>
                            {a?.suivi_serie ? (
                              <>
                                <textarea className={`saisie petite zone${errLigne(i, "numeros_serie") ? " invalide" : ""}`} rows={2}
                                  placeholder="Un n° par ligne" value={l.series} onChange={(e) => changerLigne(i, "series", e.target.value)} />
                                {errLigne(i, "numeros_serie") && <em className="msg-erreur">{errLigne(i, "numeros_serie")}</em>}
                              </>
                            ) : null}
                          </td>}
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
                <button type="button" className="btn lien ajouter" onClick={() => { setErreurs({}); setLignes([...lignes, ligneVide()]); }}>
                  <Icon name="plus" size={18} stroke={2.4} />Ajouter un article
                </button>
              </div>
              {articlesDuMagasin.length === 0 && (
                <p className="discret">Aucun article dans ce magasin : tapez son nom dans « Article reçu », puis « ＋ Créer l'article ».</p>
              )}
            </>
          )}
        </div>

        <div className="fiche-pied">
          <span className="total">Montant de la livraison : <b>{montant(total)}</b></span>
          <span className="sp" />
          <button key="annuler" className="btn" type="button" onClick={onFermer} disabled={envoi}>Annuler</button>
          <button key="enregistrer" className="btn pri" type="submit" disabled={envoi || !choix}>
            {envoi ? "Enregistrement…" : "Enregistrer"}
          </button>
        </div>
      </form>
      {creation && choix && (
        <NouvelArticle nomInitial={creation.nom} onFermer={() => setCreation(null)} onCree={articleCree}
          magasinImpose={choix.magasins.find((m) => String(m.id) === String(entete.magasin))?.nom ?? ""} />
      )}
    </>
  );
}
