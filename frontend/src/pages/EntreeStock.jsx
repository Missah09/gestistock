import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import ListeDeroulante from "../ListeDeroulante.jsx";
import ChoixArticle from "./ChoixArticle.jsx";
import NouvelArticle from "./NouvelArticle.jsx";
import PasserSuiviSerie from "./PasserSuiviSerie.jsx";
import { enregistrerEntree, lireArticle, lireChoix } from "../api.js";
import { montant } from "../format.js";
import Icon from "../icons.jsx";

// Date du jour en heure locale (toISOString donnerait la date UTC, fausse avant 3 h à Madagascar).
const aujourdhui = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const premier = (x) => (Array.isArray(x) ? x[0] : x);
const cle = () => Math.random();
// État du produit reçu (12/10/2026) : « Neuf » par défaut.
// cases (26/10/2026) : article suivi par n° de série, une case par unité reçue, chacune avec son état.
const ligneVide = () => ({ cle: cle(), article: "", quantite: "", prix_unitaire: "", etat: "NEUF", cases: [] });
const nouvelleCase = (etat) => ({ cle: cle(), numero: "", etat });
const UNITES = { m: "m", paire: "paire(s)", piece: "pièce(s)" };
const MAX_CASES = 500;
const entier = (v) => (/^\d+$/.test(String(v)) ? Number(v) : null);
const pluriel = (n, mot) => `${n} ${mot}${n > 1 ? "s" : ""}`;

/** Ajuste les cases à `n` unités. On ajoute des cases vides ; pour en retirer, les cases vides partent d'abord
 *  (en commençant par la fin). Renvoie aussi les n° déjà tapés qu'il faudrait effacer pour arriver à `n`. */
function ajuster(cases, n, etat) {
  if (n >= cases.length) return { cases: [...cases, ...Array.from({ length: n - cases.length }, () => nouvelleCase(etat))], effaces: [] };
  let trop = cases.length - n;
  const gardees = [...cases];
  for (let k = gardees.length - 1; k >= 0 && trop > 0; k--) {
    if (!gardees[k].numero.trim()) { gardees.splice(k, 1); trop--; }
  }
  return { cases: gardees, effaces: trop > 0 ? gardees.slice(gardees.length - trop).map((c) => c.numero.trim()) : [] };
}

/** Fenêtre « Entrée en stock » (anciennement « Enregistrer des produits », renommée le 12/10/2026) :
 *  réception d'une livraison, qui augmente le stock.
 *  - articleInitial : ouverte depuis la fiche d'un article, avec cet article déjà sur la 1re ligne.
 *  - Un article absent se crée depuis la liste des articles (« ＋ Créer l'article… ») : il est aussitôt placé sur la ligne.
 *  - Article suivi par n° de série (26/10/2026) : on tape la quantité, puis une case par unité apparaît sous la ligne
 *    (n° + état). Entrée passe à la case suivante (douchette), coller une liste remplit les cases, doublons en rouge.
 *  - « Ce produit a des n° de série ? » : le Responsable Technique passe l'article au suivi par n° de série, une seule fois (définitif). */
export default function EntreeStock({ onFermer, onEnregistre, articleInitial = null, onArticleCree }) {
  const [choix, setChoix] = useState(null);
  const [entete, setEntete] = useState({ fournisseur: "", numero_facture: "", date_reception: aujourdhui(), magasin: "" });
  const [lignes, setLignes] = useState([ligneVide()]);
  const [erreurs, setErreurs] = useState({});
  const [envoi, setEnvoi] = useState(false);
  const [creation, setCreation] = useState(null); // { ligne, nom } : fenêtre « Nouvel article » ouverte par-dessus
  const [passage, setPassage] = useState(null);   // { ligne, fiche } : fenêtre « Passer au suivi par n° de série »
  const [chargeFiche, setChargeFiche] = useState(null); // ligne dont la fiche est en cours de chargement
  const [reductions, setReductions] = useState({}); // {cle de ligne: quantité voulue} : n° à effacer, à confirmer
  const [info, setInfo] = useState(null);         // ex. « Article CAB-0049 créé et ajouté à la livraison. »
  const champs = useRef({});                      // cases de n° de série : `${cle de ligne}:${index}` → <input>

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

  const pardessus = Boolean(creation || passage);
  useEffect(() => {
    const touche = (e) => e.key === "Escape" && !envoi && !pardessus && onFermer();
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi, pardessus]);

  /** Article créé depuis la ligne `creation.ligne` : on recharge les listes et on le place sur cette ligne. */
  async function articleCree(fiche) {
    const ligne = creation.ligne;
    setCreation(null);
    let c = choix;
    try { c = await lireChoix(); setChoix(c); } catch { /* la ligne garde l'id : l'enregistrement fonctionnera quand même */ }
    const serie = Boolean(fiche.suivi_serie);
    setLignes((ls) => ls.map((l, j) => (j === ligne
      ? { ...l, article: String(fiche.id), prix_unitaire: fiche.prix_unitaire > 0 ? String(fiche.prix_unitaire) : "",
          cases: serie ? ajuster([], Math.min(entier(l.quantite) ?? 0, MAX_CASES), l.etat).cases : [] } : l)));
    setErreurs({});
    setInfo(`Article ${fiche.code} – ${fiche.nom} créé et ajouté à la livraison. Indiquez la quantité reçue.`);
    onArticleCree?.();
  }

  /** « Ce produit a des n° de série ? » : on lit la fiche (stock actuel par état) puis on ouvre la fenêtre de passage. */
  async function demanderPassage(i) {
    setChargeFiche(i);
    try {
      setPassage({ ligne: i, fiche: await lireArticle(lignes[i].article) });
    } catch {
      setErreurs({ general: ["Impossible de lire la fiche de l'article. Vérifiez que le serveur est démarré."] });
    } finally {
      setChargeFiche(null);
    }
  }
  async function articlePasse(fiche) {
    const i = passage.ligne;
    setPassage(null);
    try { setChoix(await lireChoix()); } catch { /* la ligne sera contrôlée par le serveur à l'enregistrement */ }
    setLignes((ls) => ls.map((l, j) => (j === i
      ? { ...l, cases: ajuster([], Math.min(entier(l.quantite) ?? 0, MAX_CASES), l.etat).cases } : l)));
    setErreurs({});
    setInfo(`${fiche.code} est désormais suivi par n° de série : saisissez le n° de chaque unité reçue.`);
    onArticleCree?.(); // la liste des articles se met à jour derrière
  }

  const articlesDuMagasin = useMemo(
    () => (choix ? choix.articles.filter((a) => String(a.magasin) === String(entete.magasin)) : []),
    [choix, entete.magasin]
  );
  const article = (id) => choix?.articles.find((a) => String(a.id) === String(id));
  const parSerie = (l) => Boolean(article(l.article)?.suivi_serie);

  // N° tapés plusieurs fois (sur la même ligne ou sur deux lignes) : signalés en rouge tout de suite.
  const doublons = useMemo(() => {
    const vus = {};
    lignes.forEach((l) => l.cases.forEach((c) => { const n = c.numero.trim(); if (n) vus[n] = (vus[n] ?? 0) + 1; }));
    return new Set(Object.keys(vus).filter((n) => vus[n] > 1));
  }, [lignes]);

  function changerMagasin(valeur) {
    // Les articles dépendent du magasin : on repart d'une liste vide.
    setEntete({ ...entete, magasin: valeur });
    setLignes([ligneVide()]);
    setReductions({});
  }
  const oublierErreurs = () => { if (erreurs.general) setErreurs({}); }; // le message général ne correspond plus à la saisie
  const majLigne = (i, f) => setLignes((ls) => ls.map((l, j) => (j === i ? f(l) : l)));
  const finReduction = (l) => setReductions((r) => { const { [l.cle]: _, ...reste } = r; return reste; });

  function changerLigne(i, champ, valeur) {
    oublierErreurs();
    majLigne(i, (l) => {
      const n = { ...l, [champ]: valeur };
      if (champ === "article") {
        const a = article(valeur);
        n.prix_unitaire = a && a.prix_unitaire > 0 ? String(a.prix_unitaire) : "";
        n.cases = a?.suivi_serie ? ajuster([], Math.min(entier(l.quantite) ?? 0, MAX_CASES), l.etat).cases : [];
      }
      return n;
    });
    if (champ === "article") finReduction(lignes[i]);
  }

  /** Quantité : les cases suivent. Les cases vides partent d'abord ; effacer un n° déjà tapé se confirme. */
  function changerQuantite(i, valeur) {
    oublierErreurs();
    const l = lignes[i];
    finReduction(l);
    const n = entier(valeur);
    if (!parSerie(l) || n === null || n === 0) { majLigne(i, (x) => ({ ...x, quantite: valeur })); return; }
    const { cases, effaces } = ajuster(l.cases, Math.min(n, MAX_CASES), l.etat);
    majLigne(i, (x) => ({ ...x, quantite: valeur, cases }));
    if (effaces.length) setReductions((r) => ({ ...r, [l.cle]: Math.min(n, MAX_CASES) }));
  }
  function confirmerReduction(i) {
    const l = lignes[i];
    majLigne(i, (x) => ({ ...x, cases: x.cases.slice(0, reductions[l.cle]) }));
    finReduction(l);
  }
  function annulerReduction(i) {
    const l = lignes[i];
    majLigne(i, (x) => ({ ...x, quantite: String(x.cases.length) }));
    finReduction(l);
  }

  function changerCase(i, k, champ, valeur) {
    oublierErreurs();
    majLigne(i, (l) => ({ ...l, cases: l.cases.map((c, j) => (j === k ? { ...c, [champ]: valeur } : c)) }));
    // L'erreur du serveur sur cette case ne vaut plus.
    if (erreurs.lignes?.[i]?.exemplaires?.[k]) {
      setErreurs((e) => ({ ...e, lignes: e.lignes.map((x, j) => (j === i && x
        ? { ...x, numeros_serie: undefined, exemplaires: x.exemplaires.map((y, m) => (m === k ? {} : y)) } : x)) }));
    }
  }
  /** « Tous : » état choisi pour toutes les unités de la ligne (on peut ensuite en changer une). */
  function etatPourTous(i, etat) {
    oublierErreurs();
    majLigne(i, (l) => ({ ...l, etat, cases: l.cases.map((c) => ({ ...c, etat })) }));
  }

  const focaliser = (l, k) => setTimeout(() => champs.current[`${l.cle}:${k}`]?.focus(), 0);
  /** Entrée (clavier ou douchette code-barres) : case suivante, sans enregistrer la fenêtre. */
  function toucheCase(e, i, k) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const l = lignes[i];
    // Tout de suite (sans attendre) : une douchette envoie le n° suivant aussitôt après Entrée.
    if (k < l.cases.length - 1) champs.current[`${l.cle}:${k + 1}`]?.focus();
  }
  /** Coller une liste (bon du fournisseur, Excel…) : un n° par case à partir de celle-ci ; la quantité suit si besoin. */
  function collerCase(e, i, k) {
    const texte = e.clipboardData.getData("text");
    const valeurs = texte.split(/[\r\n\t;,]+/).map((s) => s.trim()).filter(Boolean);
    if (valeurs.length < 2) return; // un seul n° : collage normal
    e.preventDefault();
    oublierErreurs();
    const l = lignes[i];
    const total = Math.min(Math.max(l.cases.length, k + valeurs.length), MAX_CASES);
    const cases = ajuster(l.cases, total, l.etat).cases.map((c, j) =>
      (j >= k && j - k < valeurs.length ? { ...c, numero: valeurs[j - k] } : c));
    majLigne(i, (x) => ({ ...x, cases, quantite: String(Math.max(cases.length, entier(x.quantite) ?? 0)) }));
    finReduction(l);
    focaliser(l, Math.min(k + valeurs.length, total - 1));
  }

  const retirer = (i) => { finReduction(lignes[i]); setLignes(lignes.length > 1 ? lignes.filter((_, j) => j !== i) : [ligneVide()]); };

  const total = lignes.reduce((t, l) => t + (Number(l.quantite) || 0) * (Number(l.prix_unitaire) || 0), 0);

  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true); setErreurs({});
    // Les lignes vides ne partent pas : on garde leur position pour remettre les erreurs sur la bonne ligne.
    const envoyees = lignes.map((l, i) => ({ l, i })).filter(({ l }) => l.article || l.quantite);
    const donnees = {
      fournisseur: entete.fournisseur ? Number(entete.fournisseur) : null,
      numero_facture: entete.numero_facture,
      date_reception: entete.date_reception || null,
      magasin: entete.magasin ? Number(entete.magasin) : null,
      lignes: envoyees.map(({ l }) => ({
        article: l.article ? Number(l.article) : null,
        quantite: l.quantite === "" ? null : Number(l.quantite),
        prix_unitaire: l.prix_unitaire === "" ? null : l.prix_unitaire,
        etat: l.etat,
        ...(parSerie(l) ? { exemplaires: l.cases.map((c) => ({ numero_serie: c.numero.trim(), etat: c.etat })) } : {}),
      })),
    };
    try {
      const r = await enregistrerEntree(donnees);
      onEnregistre(r.message);
    } catch (err) {
      const d = err.details ?? { general: ["L'enregistrement a échoué. Vérifiez que le serveur est démarré."] };
      if (Array.isArray(d.lignes)) {
        const parLigne = [];
        envoyees.forEach(({ i }, j) => { parLigne[i] = d.lignes[j]; });
        d.lignes = parLigne;
      }
      setErreurs(d);
    } finally {
      setEnvoi(false);
    }
  }

  const errLigne = (i, champ) => premier(erreurs.lignes?.[i]?.[champ]);
  const errCase = (i, k) => premier(erreurs.lignes?.[i]?.exemplaires?.[k]?.numero_serie);
  const err = (champ) => premier(erreurs[champ]);
  const optionsEtat = (choix?.etats ?? []).map((x) => ({ valeur: x.valeur, libelle: x.libelle }));

  /** Zone sous la ligne : une case par unité reçue (article suivi par n° de série). */
  function zoneSeries(l, i) {
    const qte = entier(l.quantite) ?? 0;
    const saisis = l.cases.filter((c) => c.numero.trim()).length;
    const manque = Math.max(0, Math.min(qte, MAX_CASES) - saisis);
    const enDouble = l.cases.filter((c) => doublons.has(c.numero.trim())).length;
    const reduction = reductions[l.cle];
    const aEffacer = reduction !== undefined ? l.cases.slice(reduction).map((c) => c.numero.trim()) : [];
    return (
      <tr className="ligne-series">
        <td colSpan={5}>
          <div className={`series${errLigne(i, "numeros_serie") ? " series-erreur" : ""}`}>
            <div className="series-tete">
              <b>N° de série</b>
              {qte > 0 && !aEffacer.length && <span className={`series-compte${manque || enDouble ? "" : " complet"}`}>{saisis} sur {Math.min(qte, MAX_CASES)} saisi{saisis > 1 ? "s" : ""}</span>}
            </div>
            {qte === 0 && <p className="aide series-vide">Indiquez la quantité reçue : une case par unité apparaîtra ici.</p>}
            {qte > MAX_CASES && <p className="msg-erreur">{MAX_CASES} unités au maximum par ligne : ajoutez une autre ligne pour le reste.</p>}
            {l.cases.length > 0 && (
              <ol className="series-cases">
                {l.cases.map((c, k) => {
                  const double = doublons.has(c.numero.trim());
                  const erreur = errCase(i, k) ?? (double ? "En double" : null);
                  return (
                    <li key={c.cle} className="case-serie">
                      <span className="case-num">{k + 1}.</span>
                      <div className="case-champ">
                        <input ref={(el) => { champs.current[`${l.cle}:${k}`] = el; }}
                          className={`saisie petite${erreur ? " invalide" : ""}`} value={c.numero} placeholder="N° de série"
                          aria-label={`N° de série de l'unité ${k + 1}`} autoComplete="off" spellCheck={false}
                          onChange={(e) => changerCase(i, k, "numero", e.target.value)}
                          onKeyDown={(e) => toucheCase(e, i, k)} onPaste={(e) => collerCase(e, i, k)} />
                        {erreur && <em className="msg-erreur">{erreur}</em>}
                      </div>
                      <div className="case-etat">
                        <ListeDeroulante petite recherche={false} ariaLabel={`État de l'unité ${k + 1}`} valeur={c.etat}
                          options={optionsEtat} onChange={(v) => changerCase(i, k, "etat", v)} />
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
            {aEffacer.length > 0 && (
              <div className="series-confirmer">
                <span>Passer à {pluriel(reduction, "unité")} efface {aEffacer.length > 1 ? "les n° déjà saisis" : "le n° déjà saisi"} : <b className="code">{aEffacer.join(", ")}</b>.</span>
                <button type="button" className="btn danger btn-court" onClick={() => confirmerReduction(i)}>Effacer</button>
                <button type="button" className="btn btn-court" onClick={() => annulerReduction(i)}>Garder ({l.cases.length})</button>
              </div>
            )}
            {errLigne(i, "numeros_serie")
              ? <em className="msg-erreur">{errLigne(i, "numeros_serie")}</em>
              : !aEffacer.length && qte > 0 && (manque > 0 || enDouble > 0) && (
                <p className="series-alerte">
                  <Icon name="attention" size={15} stroke={2.2} />
                  {[manque > 0 && `Il manque ${manque} n° de série`, enDouble > 0 && `${enDouble} n° en double`].filter(Boolean).join(" · ")}
                </p>
              )}
          </div>
        </td>
      </tr>
    );
  }

  return (
    <>
      <div className="voile" onClick={() => !envoi && !pardessus && onFermer()} />
      <form className="fenetre entree-stock" role="dialog" aria-modal="true" aria-label="Entrée en stock" onSubmit={enregistrer}>
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
                    <tr><th style={{ width: "38%" }}>Article reçu</th><th style={{ width: "16%" }}>Quantité</th>
                      <th style={{ width: "18%" }}>Prix unitaire (Ar)</th><th>État</th><th style={{ width: 52 }} /></tr>
                  </thead>
                  <tbody>
                    {lignes.map((l, i) => {
                      const a = article(l.article);
                      const serie = Boolean(a?.suivi_serie);
                      const etatsCases = new Set(l.cases.map((c) => c.etat));
                      return (
                        <Fragment key={l.cle}>
                          <tr className={serie ? "avec-series" : ""}>
                            <td>
                              <ChoixArticle articles={articlesDuMagasin} valeur={l.article} invalide={Boolean(errLigne(i, "article"))}
                                dejaPris={lignes.map((x) => x.article).filter(Boolean)} texteDejaPris="Déjà sur la réception"
                                texteVide="Taper un nom ou un code, ou choisir…" onChoisir={(v) => changerLigne(i, "article", v)}
                                onCreer={(nom) => setCreation({ ligne: i, nom })} />
                              {errLigne(i, "article") && <em className="msg-erreur">{errLigne(i, "article")}</em>}
                              {a && !serie && a.serie_possible && (
                                <button type="button" className="btn lien lien-serie" disabled={chargeFiche === i}
                                  onClick={() => demanderPassage(i)}>
                                  {chargeFiche === i ? "Ouverture…" : "Ce produit a des n° de série ?"}
                                </button>
                              )}
                            </td>
                            <td>
                              <div className="avec-unite">
                                <input className={`saisie petite${errLigne(i, "quantite") ? " invalide" : ""}`} type="number" min="1" step="1"
                                  value={l.quantite} onChange={(e) => changerQuantite(i, e.target.value)}
                                  aria-label="Quantité reçue" />
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
                              {serie ? (
                                <ListeDeroulante ariaLabel="État de toutes les unités" recherche={false} placeholder="Plusieurs états"
                                  valeur={etatsCases.size === 1 ? [...etatsCases][0] : etatsCases.size ? "" : l.etat}
                                  onChange={(v) => etatPourTous(i, v)} options={optionsEtat} />
                              ) : (
                                <ListeDeroulante ariaLabel="État du produit reçu" recherche={false} valeur={l.etat}
                                  invalide={Boolean(errLigne(i, "etat"))} onChange={(v) => changerLigne(i, "etat", v)} options={optionsEtat} />
                              )}
                              {errLigne(i, "etat") && <em className="msg-erreur">{errLigne(i, "etat")}</em>}
                            </td>
                            <td>
                              <button type="button" className="btn-icone" onClick={() => retirer(i)} aria-label="Retirer cette ligne" title="Retirer cette ligne">
                                <Icon name="x" size={16} stroke={2.2} />
                              </button>
                            </td>
                          </tr>
                          {serie && zoneSeries(l, i)}
                        </Fragment>
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
      {passage && (
        <PasserSuiviSerie article={passage.fiche} depuisEntree onFermer={() => setPassage(null)} onPasse={articlePasse} />
      )}
    </>
  );
}
