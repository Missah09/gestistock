import { useEffect, useMemo, useState } from "react";
import ListeDeroulante from "../ListeDeroulante.jsx";
import { creerArticle, lireChoix } from "../api.js";
import Icon from "../icons.jsx";

const premier = (x) => (Array.isArray(x) ? x[0] : x);
const VIDE = {
  nom: "", categorie: "", type: "", suivi_serie: false, unite: "piece", magasin: "", emplacement: "",
  qte_minimale: "0", prix_unitaire: "", fournisseur: "", ref_fournisseur: "", marque: "", modele: "", ref_fabricant: "",
};

/** Fenêtre « Nouvel article » (12/10/2026) : Responsable Technique et administrateur.
 *  S'ouvre par-dessus « Entrée en stock » (ligne « ＋ Créer l'article… » de la liste des articles) :
 *  le nom tapé est repris, le magasin est celui de la livraison. Le code est créé automatiquement ;
 *  l'article créé est aussitôt placé sur la ligne de la livraison. */
export default function NouvelArticle({ onFermer, onCree, nomInitial = "", magasinImpose = "" }) {
  const [choix, setChoix] = useState(null);
  const [f, setF] = useState({ ...VIDE, nom: nomInitial, magasin: magasinImpose });
  const [erreurs, setErreurs] = useState({});
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    lireChoix()
      .then((c) => { setChoix(c); setF((x) => ({ ...x, magasin: x.magasin || c.magasins[0]?.nom || "" })); })
      .catch(() => setErreurs({ general: ["Impossible de charger les listes. Vérifiez que le serveur est démarré."] }));
  }, []);

  useEffect(() => {
    const touche = (e) => e.key === "Escape" && !envoi && onFermer();
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi]);

  const changer = (cle, v) => {
    setF((x) => ({ ...x, [cle]: v, ...(cle === "magasin" ? { emplacement: "" } : {}) }));
    setErreurs((e) => ({ ...e, [cle]: undefined, general: undefined, ...(cle === "magasin" ? { emplacement: undefined } : {}) }));
  };
  const err = (cle) => premier(erreurs[cle]);
  const nbErreurs = Object.values(erreurs).filter(Boolean).length;

  const emplacements = useMemo(() => (choix ? choix.emplacements.filter((e) => e.magasin === f.magasin) : []), [choix, f.magasin]);
  const categorie = choix?.categories.find((c) => String(c.id) === String(f.categorie));

  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true); setErreurs({});
    const donnees = {
      nom: f.nom, type: f.type || null, suivi_serie: f.suivi_serie && (f.type === "PRETE" || (f.type === "CONSOMMABLE" && f.unite === "piece")), unite: f.unite,
      categorie: f.categorie ? Number(f.categorie) : null,
      emplacement: f.emplacement ? Number(f.emplacement) : null,
      qte_minimale: f.qte_minimale === "" ? 0 : f.qte_minimale,
      prix_unitaire: f.prix_unitaire === "" ? 0 : f.prix_unitaire,
      fournisseur: f.fournisseur ? Number(f.fournisseur) : null,
      ref_fournisseur: f.ref_fournisseur, marque: f.marque, modele: f.modele, ref_fabricant: f.ref_fabricant,
    };
    try {
      const r = await creerArticle(donnees);
      onCree(r);
    } catch (x) {
      setErreurs(x.details ?? { general: ["L'enregistrement a échoué. Vérifiez que le serveur est démarré."] });
    } finally {
      setEnvoi(false);
    }
  }

  const texte = (cle, libelle, props = {}) => (
    <label className={err(cle) ? "en-erreur" : ""}>
      <span>{libelle}</span>
      <input className={`saisie${err(cle) ? " invalide" : ""}`} value={f[cle]} onChange={(e) => changer(cle, e.target.value)} {...props} />
      {err(cle) && <em className="msg-erreur">{err(cle)}</em>}
    </label>
  );

  return (
    <>
      <div className="voile par-dessus" onClick={() => !envoi && onFermer()} />
      <form className="fenetre compte nouvel-article par-dessus" role="dialog" aria-modal="true" aria-label="Nouvel article" onSubmit={enregistrer} noValidate>
        <div className="fenetre-tete">
          <h2>Nouvel article</h2>
          <span className="sp" />
          <button className="fermer" type="button" onClick={onFermer} disabled={envoi} aria-label="Fermer"><Icon name="x" size={22} stroke={2.2} /></button>
        </div>

        <div className="fenetre-corps">
          {err("general") && <div className="alerte">{err("general")}</div>}
          {!err("general") && nbErreurs > 0 && <div className="alerte">Certaines informations sont à corriger (en rouge ci-dessous).</div>}

          {!choix ? (!err("general") && <p className="vide">Chargement…</p>) : (
            <>
              <div className="entete-grille">
                <label className={`pleine${err("nom") ? " en-erreur" : ""}`}>
                  <span>Nom de l'article</span>
                  <input className={`saisie${err("nom") ? " invalide" : ""}`} value={f.nom} autoFocus placeholder="Ex. Câble fibre 12 FO"
                    onChange={(e) => changer("nom", e.target.value)} />
                  {err("nom") && <em className="msg-erreur">{err("nom")}</em>}
                </label>
                <label className={err("categorie") ? "en-erreur" : ""}>
                  <span>Catégorie</span>
                  <ListeDeroulante ariaLabel="Catégorie" placeholder="— Choisir la catégorie —" valeur={f.categorie}
                    invalide={Boolean(err("categorie"))} onChange={(v) => changer("categorie", v)}
                    options={choix.categories.map((c) => ({ valeur: String(c.id), libelle: c.nom }))} />
                  {err("categorie") ? <em className="msg-erreur">{err("categorie")}</em>
                    : <small className="aide">{categorie ? <>Code créé automatiquement : <b className="code">{categorie.prochain_code}</b></> : "Le code article est créé automatiquement."}</small>}
                </label>
                <label className={err("unite") ? "en-erreur" : ""}>
                  <span>Unité</span>
                  <ListeDeroulante ariaLabel="Unité" recherche={false} valeur={f.unite} invalide={Boolean(err("unite"))}
                    onChange={(v) => changer("unite", v)} options={choix.unites.map((u) => ({ valeur: u.valeur, libelle: u.libelle }))} />
                  {err("unite") && <em className="msg-erreur">{err("unite")}</em>}
                </label>
              </div>

              <fieldset className={`roles-choix${err("type") ? " en-erreur" : ""}`}>
                <legend>Type d'article</legend>
                <label className="btn case">
                  <input type="radio" name="type" checked={f.type === "CONSOMMABLE"} onChange={() => changer("type", "CONSOMMABLE")} />
                  <span><b>Consommable</b><small>Ne revient pas au magasin : câble, connecteurs, gaines…</small></span>
                </label>
                {/* Consommable suivi par n° de série (26/10/2026) : seulement compté à la pièce (box ONT…). */}
                {f.type === "CONSOMMABLE" && (
                  <label className={`btn case sous-choix${f.unite !== "piece" ? " desactive" : ""}`}>
                    <input type="checkbox" checked={f.suivi_serie && f.unite === "piece"} disabled={f.unite !== "piece"}
                      onChange={(e) => changer("suivi_serie", e.target.checked)} />
                    <span><b>Suivi par n° de série</b><small>{f.unite === "piece"
                      ? "Chaque unité a son n° sur l'étiquette (box ONT…) : les n° seront demandés à la réception et cochés à la sortie. Sans cette case, suivi par quantité."
                      : "Le suivi par n° de série n'est possible que pour les articles comptés à la pièce."}</small></span>
                  </label>
                )}
                <label className="btn case">
                  <input type="radio" name="type" checked={f.type === "PRETE"} onChange={() => changer("type", "PRETE")} />
                  <span><b>Non consommable · à rendre</b><small>Prêté puis rendu : appareils, outillage, EPI…</small></span>
                </label>
                {f.type === "PRETE" && (
                  <label className="btn case sous-choix">
                    <input type="checkbox" checked={f.suivi_serie} onChange={(e) => changer("suivi_serie", e.target.checked)} />
                    <span><b>Suivi par n° de série</b><small>Chaque appareil a son n° (OTDR, soudeuse…) : les n° seront demandés à la réception. Sans cette case, suivi par quantité (pelles, casques…).</small></span>
                  </label>
                )}
                {err("suivi_serie") && <em className="msg-erreur">{err("suivi_serie")}</em>}
                {err("type") && <em className="msg-erreur">{err("type")}</em>}
                <p className="aide">Le type ne pourra plus être changé après la création.</p>
              </fieldset>

              <div className="entete-grille">
                <label>
                  <span>Magasin</span>
                  <ListeDeroulante ariaLabel="Magasin" recherche={false} valeur={f.magasin} onChange={(v) => changer("magasin", v)}
                    desactive={Boolean(magasinImpose)}
                    options={choix.magasins.map((m) => ({ valeur: m.nom, libelle: m.type === "CHANTIER" ? `Chantier : ${m.nom}` : m.nom }))} />
                  {magasinImpose && <small className="aide">Celui de la livraison.</small>}
                </label>
                <label className={err("emplacement") ? "en-erreur" : ""}>
                  <span>Emplacement</span>
                  <ListeDeroulante ariaLabel="Emplacement" placeholder="— Choisir l'emplacement —" valeur={f.emplacement}
                    invalide={Boolean(err("emplacement"))} onChange={(v) => changer("emplacement", v)}
                    options={emplacements.map((e) => ({ valeur: String(e.id), libelle: e.nom }))} />
                  {err("emplacement") ? <em className="msg-erreur">{err("emplacement")}</em>
                    : emplacements.length === 0 && <small className="aide">Aucun emplacement dans ce magasin : à créer dans l'administration.</small>}
                </label>
                <label className={err("qte_minimale") ? "en-erreur" : ""}>
                  <span>Quantité minimale <em className="facultatif">(seuil d'alerte)</em></span>
                  <input className={`saisie${err("qte_minimale") ? " invalide" : ""}`} type="number" min="0" step="1" value={f.qte_minimale}
                    onChange={(e) => changer("qte_minimale", e.target.value)} />
                  {err("qte_minimale") ? <em className="msg-erreur">{err("qte_minimale")}</em>
                    : <small className="aide">En dessous, l'article passe « Sous le seuil ». 0 = pas d'alerte.</small>}
                </label>
                <label className={err("prix_unitaire") ? "en-erreur" : ""}>
                  <span>Prix unitaire (Ar) <em className="facultatif">(facultatif)</em></span>
                  <input className={`saisie${err("prix_unitaire") ? " invalide" : ""}`} type="number" min="0" step="0.01" value={f.prix_unitaire}
                    placeholder="Mis à jour à chaque réception" onChange={(e) => changer("prix_unitaire", e.target.value)} />
                  {err("prix_unitaire") && <em className="msg-erreur">{err("prix_unitaire")}</em>}
                </label>
              </div>

              <fieldset className="roles-choix">
                <legend>Fournisseur et fabricant <em className="facultatif">(facultatif)</em></legend>
                <div className="entete-grille">
                  <label className={err("fournisseur") ? "en-erreur" : ""}>
                    <span>Fournisseur</span>
                    <ListeDeroulante ariaLabel="Fournisseur" placeholder="— Aucun —" valeur={f.fournisseur} onChange={(v) => changer("fournisseur", v)}
                      options={[{ valeur: "", libelle: "— Aucun —" }, ...choix.fournisseurs.map((x) => ({ valeur: String(x.id), libelle: x.nom }))]} />
                    {err("fournisseur") && <em className="msg-erreur">{err("fournisseur")}</em>}
                  </label>
                  {texte("ref_fournisseur", "Réf. fournisseur")}
                  {texte("marque", "Marque")}
                  {texte("modele", "Modèle")}
                  {texte("ref_fabricant", "Réf. fabricant")}
                </div>
              </fieldset>

              <p className="aide">Après « Créer l'article », il est placé sur la ligne de la livraison : il ne reste qu'à saisir la quantité.</p>
            </>
          )}
        </div>

        <div className="fiche-pied">
          <span className="sp" />
          <button key="annuler" className="btn" type="button" onClick={onFermer} disabled={envoi}>Annuler</button>
          <button key="creer" className="btn pri" type="submit" disabled={envoi || !choix}>
            {envoi ? "Création…" : "Créer l'article"}
          </button>
        </div>
      </form>
    </>
  );
}
