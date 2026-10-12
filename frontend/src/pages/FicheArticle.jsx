import { useCallback, useEffect, useState } from "react";
import ListeDeroulante from "../ListeDeroulante.jsx";
import { lireArticle, lireChoix, modifierArticle } from "../api.js";
import { date, datePassee, ETATS, ETATS_UTILISABLES, montant, quantite, LIBELLE_PRETE } from "../format.js";
import EtatsProduit, { PastilleEtat } from "../EtatsProduit.jsx";
import Icon from "../icons.jsx";

/** Un champ : le libellé au-dessus, la valeur (ou la zone de saisie) en dessous. */
function Champ({ libelle, children, aide, large, erreur }) {
  return (
    <div className={`champ${large ? " large" : ""}${erreur ? " en-erreur" : ""}`}>
      <span>{libelle}</span>
      <b>{children ?? "—"}</b>
      {erreur && <em>{erreur}</em>}
      {aide && !erreur && <small>{aide}</small>}
    </div>
  );
}

/** Une section encadrée avec son titre. */
function Bloc({ titre, extra, children }) {
  return (
    <section className="bloc">
      <h3>{titre}{extra}</h3>
      {children}
    </section>
  );
}

const premier = (liste) => (Array.isArray(liste) ? liste[0] : liste);

/** Copie des valeurs modifiables, pour le formulaire. */
function versFormulaire(a, choix) {
  const idDe = (liste, nom) => liste.find((x) => x.nom === nom)?.id ?? "";
  return {
    nom: a.nom,
    categorie: idDe(choix.categories, a.categorie),
    unite: a.unite,
    qte_minimale: String(a.qte_minimale),
    emplacement: choix.emplacements.find((e) => e.nom === a.emplacement && e.magasin === a.magasin)?.id ?? "",
    prix_unitaire: String(a.prix_unitaire),
    fournisseur: idDe(choix.fournisseurs, a.fournisseur),
    ref_fournisseur: a.ref_fournisseur,
    ref_fabricant: a.ref_fabricant,
    marque: a.marque,
    modele: a.modele,
    exemplaires: a.exemplaires.map((e) => ({
      id: e.id, numero_serie: e.numero_serie, code_immo: e.code_immo, date_etalonnage: e.date_etalonnage ?? "",
    })),
  };
}

/** Panneau latéral « fiche article », en lecture ou en modification. */
export default function FicheArticle({ id, onFermer, onModifie, onEntreeStock, modifiable = true }) {
  const [a, setA] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [choix, setChoix] = useState(null);
  const [form, setForm] = useState(null);       // null = lecture, objet = modification en cours
  const [erreurs, setErreurs] = useState({});    // erreurs renvoyées par le serveur, par champ
  const [enregistrement, setEnregistrement] = useState(false);
  const [message, setMessage] = useState(null);

  const enModification = form !== null;

  useEffect(() => {
    let annule = false;
    setA(null); setErreur(null); setForm(null); setMessage(null);
    lireArticle(id)
      .then((d) => !annule && setA(d))
      .catch(() => !annule && setErreur("Impossible de charger la fiche de cet article."));
    return () => { annule = true; };
  }, [id]);

  // Pendant une modification, Échap et le clic sur le fond ne ferment pas la fiche
  // (pour ne pas perdre la saisie par erreur).
  const fermerSiPossible = useCallback(() => { if (!enModification) onFermer(); }, [enModification, onFermer]);
  useEffect(() => {
    const touche = (e) => e.key === "Escape" && fermerSiPossible();
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [fermerSiPossible]);

  async function commencerModification() {
    setMessage(null); setErreurs({});
    try {
      const c = choix ?? await lireChoix();
      setChoix(c);
      setForm(versFormulaire(a, c));
    } catch {
      setErreur("Impossible de charger les listes du formulaire.");
    }
  }

  function annuler() { setForm(null); setErreurs({}); }

  const changer = (champ) => (e) => setForm({ ...form, [champ]: e.target.value });
  const choisirListe = (champ) => (valeur) => setForm({ ...form, [champ]: valeur });
  const changerExemplaire = (i, champ) => (e) => {
    const exemplaires = form.exemplaires.map((x, j) => (j === i ? { ...x, [champ]: e.target.value } : x));
    setForm({ ...form, exemplaires });
  };

  async function enregistrer(e) {
    e.preventDefault();
    setEnregistrement(true); setErreurs({}); setMessage(null);
    const donnees = {
      ...form,
      fournisseur: form.fournisseur === "" ? null : Number(form.fournisseur),
      categorie: Number(form.categorie),
      emplacement: Number(form.emplacement),
      qte_minimale: form.qte_minimale === "" ? null : Number(form.qte_minimale),
      prix_unitaire: form.prix_unitaire === "" ? null : form.prix_unitaire,
      exemplaires: form.exemplaires.map((x) => ({ ...x, date_etalonnage: x.date_etalonnage || null })),
    };
    if (a.type !== "PRETE") delete donnees.exemplaires;
    try {
      const fiche = await modifierArticle(id, donnees);
      setA(fiche);
      setForm(null);
      setMessage("Modifications enregistrées.");
      onModifie?.();
    } catch (err) {
      setErreurs(err.details ?? { general: ["L'enregistrement a échoué. Vérifiez que le serveur est démarré."] });
    } finally {
      setEnregistrement(false);
    }
  }

  const prete = a?.type === "PRETE";
  const err = (champ) => premier(erreurs[champ]);
  const errEx = (i, champ) => premier(erreurs.exemplaires?.[i]?.[champ]);
  const nbErreurs = Object.keys(erreurs).length;

  const saisie = (champ, props = {}) => (
    <input className="saisie" value={form[champ]} onChange={changer(champ)} {...props} />
  );

  return (
    <>
      <div className="voile" onClick={fermerSiPossible} />
      <form className="fiche" role="dialog" aria-modal="true" aria-label="Fiche article" onSubmit={enregistrer}>
        <div className="fiche-tete">
          <div style={{ flex: 1, minWidth: 0 }}>
            {enModification ? (
              <>
                <label className="etiquette" htmlFor="nom-article">Nom de l'article</label>
                <input id="nom-article" className={`saisie titre${err("nom") ? " invalide" : ""}`} value={form.nom} onChange={changer("nom")} />
                {err("nom") && <em className="msg-erreur">{err("nom")}</em>}
              </>
            ) : (
              <h2>
                {a ? a.nom : "Chargement…"}
                {a && <span className="code titre-code">{a.code}</span>}
              </h2>
            )}
            {a && (
              <div className="meta meta-petite">
                {enModification && <span className="code">{a.code}</span>}
                {!enModification && <span className="pill p-g">{a.categorie}</span>}
                <span className={`pill ${prete ? "p-i" : "p-g"}`}>
                  {prete ? LIBELLE_PRETE : "Consommable"}
                </span>
              </div>
            )}
          </div>
          {!enModification && (
            <button className="fermer" type="button" onClick={onFermer} aria-label="Fermer la fiche">
              <Icon name="x" size={22} stroke={2.2} />
            </button>
          )}
        </div>

        <div className="fiche-corps">
          {erreur && <div className="alerte">{erreur}</div>}
          {message && <div className="succes">{message}</div>}
          {enModification && nbErreurs > 0 && (
            <div className="alerte">
              {premier(erreurs.general) ?? "Certaines informations sont à corriger (en rouge ci-dessous)."}
            </div>
          )}

          {a && (
            <>
              <Bloc titre="Stock" extra={<span className={`pill bloc-etat ${ETATS[a.etat].classe}`}>{ETATS[a.etat].libelle}</span>}>
                <div className="champs">
                  <Champ libelle="Qté disponible"
                    aide={enModification ? "Change par les entrées, sorties et l'inventaire" : prete && a.exemplaires.length > 0 ? `sur ${a.exemplaires.length} exemplaires` : null}>
                    {quantite(a.qte_disponible, a.unite)}
                  </Champ>
                  <Champ libelle="Qté minimale" erreur={enModification && err("qte_minimale")}>
                    {enModification ? saisie("qte_minimale", { type: "number", min: 0, step: 1 }) : quantite(a.qte_minimale, a.unite)}
                  </Champ>
                  <Champ libelle="Emplacement" erreur={enModification && err("emplacement")}>
                    {enModification ? (
                      <ListeDeroulante ariaLabel="Emplacement" valeur={form.emplacement} onChange={choisirListe("emplacement")}
                        invalide={Boolean(err("emplacement"))}
                        options={[...new Set(choix.emplacements.map((e) => e.magasin))].flatMap((m) =>
                          choix.emplacements.filter((e) => e.magasin === m)
                            .map((e) => ({ valeur: String(e.id), libelle: e.nom, groupe: m, texte: `${e.nom} – ${m}` })))} />
                    ) : a.emplacement}
                  </Champ>
                  {enModification ? (
                    <Champ libelle="Unité" erreur={err("unite")}>
                      <ListeDeroulante ariaLabel="Unité" valeur={form.unite} onChange={choisirListe("unite")} invalide={Boolean(err("unite"))}
                        options={choix.unites.map((u) => ({ valeur: u.valeur, libelle: u.libelle }))} />
                    </Champ>
                  ) : (
                    <Champ libelle="Magasin">{a.magasin}</Champ>
                  )}
                  {!enModification && a.repartition && (
                    <Champ libelle="État du produit" large
                      aide={a.repartition.par_serie && a.repartition.pretes ? `et ${a.repartition.pretes} prêté${a.repartition.pretes > 1 ? "s" : ""} (hors magasin)` : null}>
                      <EtatsProduit etats={a.repartition.etats} unite={a.unite} seulement={ETATS_UTILISABLES} vide="Rien de disponible" />
                    </Champ>
                  )}
                  {enModification && (
                    <Champ libelle="Catégorie" large erreur={err("categorie")}>
                      <ListeDeroulante ariaLabel="Catégorie" valeur={form.categorie} onChange={choisirListe("categorie")}
                        invalide={Boolean(err("categorie"))}
                        options={choix.categories.map((c) => ({ valeur: String(c.id), libelle: c.nom }))} />
                    </Champ>
                  )}
                </div>
              </Bloc>

              <Bloc titre="Prix et valeur">
                <div className="champs">
                  <Champ libelle="Prix unitaire (Ar)" erreur={enModification && err("prix_unitaire")}>
                    {enModification ? saisie("prix_unitaire", { type: "number", min: 0, step: "0.01" }) : montant(a.prix_unitaire)}
                  </Champ>
                  <Champ libelle="Montant du stock" aide={enModification ? "Recalculé à l'enregistrement" : "Calculé : qté disponible × prix unitaire"}>
                    {montant(a.montant_stock)}
                  </Champ>
                </div>
              </Bloc>

              <Bloc titre="Fournisseur et fabricant">
                <div className="champs">
                  <Champ libelle="Fournisseur" erreur={enModification && err("fournisseur")}>
                    {enModification ? (
                      <ListeDeroulante ariaLabel="Fournisseur" placeholder="— Aucun —" valeur={form.fournisseur ?? ""}
                        onChange={choisirListe("fournisseur")} invalide={Boolean(err("fournisseur"))}
                        options={[{ valeur: "", libelle: "— Aucun —" }, ...choix.fournisseurs.map((f) => ({ valeur: String(f.id), libelle: f.nom }))]} />
                    ) : a.fournisseur || null}
                  </Champ>
                  <Champ libelle="Réf. fournisseur" erreur={enModification && err("ref_fournisseur")}>
                    {enModification ? saisie("ref_fournisseur") : a.ref_fournisseur || null}
                  </Champ>
                  <Champ libelle="Marque" erreur={enModification && err("marque")}>
                    {enModification ? saisie("marque") : a.marque || null}
                  </Champ>
                  <Champ libelle="Modèle" erreur={enModification && err("modele")}>
                    {enModification ? saisie("modele") : a.modele || null}
                  </Champ>
                  <Champ libelle="Réf. fabricant" large erreur={enModification && err("ref_fabricant")}>
                    {enModification ? saisie("ref_fabricant") : a.ref_fabricant || null}
                  </Champ>
                </div>
              </Bloc>

              {/* Article suivi par n° de série, encore jamais reçu (créé avec « Nouvel article », 12/10/2026) */}
              {prete && a.suivi_serie && a.exemplaires.length === 0 && (
                <Bloc titre="Exemplaires (0)">
                  <p className="aide" style={{ margin: 0, padding: "12px 16px" }}>Suivi par n° de série : les n° seront saisis à l'entrée en stock.</p>
                </Bloc>
              )}

              {/* Section affichée seulement pour le matériel suivi par n° de série */}
              {prete && a.exemplaires.length > 0 && (
                <Bloc titre={`Exemplaires (${a.exemplaires.length})`}>
                  <div className="ex">
                    <table className="tableau">
                      <thead>
                        <tr><th>N° de série</th><th>Code immo</th><th>Étalonnage</th><th>État</th><th>Où il se trouve</th></tr>
                      </thead>
                      <tbody>
                        {a.exemplaires.map((e, i) => (
                          <tr key={e.id}>
                            {enModification ? (
                              <>
                                <td>
                                  <input className={`saisie petite${errEx(i, "numero_serie") ? " invalide" : ""}`} value={form.exemplaires[i].numero_serie} onChange={changerExemplaire(i, "numero_serie")} />
                                  {errEx(i, "numero_serie") && <em className="msg-erreur">{errEx(i, "numero_serie")}</em>}
                                </td>
                                <td>
                                  <input className={`saisie petite${errEx(i, "code_immo") ? " invalide" : ""}`} placeholder="À compléter" value={form.exemplaires[i].code_immo} onChange={changerExemplaire(i, "code_immo")} />
                                  {errEx(i, "code_immo") && <em className="msg-erreur">{errEx(i, "code_immo")}</em>}
                                </td>
                                <td>
                                  <input className="saisie petite" type="date" value={form.exemplaires[i].date_etalonnage} onChange={changerExemplaire(i, "date_etalonnage")} />
                                </td>
                              </>
                            ) : (
                              <>
                                <td className="code">{e.numero_serie}</td>
                                <td>{e.code_immo ? <span className="code">{e.code_immo}</span> : <span className="a-completer">À compléter (Finance)</span>}</td>
                                <td className={datePassee(e.date_etalonnage) ? "depasse" : ""}>{date(e.date_etalonnage)}</td>
                              </>
                            )}
                            <td><PastilleEtat etat={e.etat} /></td>
                            <td>
                              <span className={`pill ${e.statut === "EN_STOCK" ? "p-ok" : e.statut === "PRETE" ? "p-i" : e.statut === "REBUT" ? "p-g" : "p-w"}`}>{e.statut_libelle}</span>{" "}
                              {e.statut === "PRETE" ? [e.prete_a, e.chantier].filter(Boolean).join(" · ")
                                : e.statut === "REBUT" ? "" : a.emplacement}
                            </td>
                          </tr>
                        ))}
                        {a.exemplaires.length === 0 && (
                          <tr><td colSpan={5} className="vide">Aucun exemplaire enregistré.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </Bloc>
              )}
            </>
          )}
        </div>

        <div className="fiche-pied">
          {enModification ? (
            <>
              <button key="enregistrer" className="btn pri" type="submit" disabled={enregistrement}>
                {enregistrement ? "Enregistrement…" : "Enregistrer"}
              </button>
              <button key="annuler" className="btn" type="button" onClick={annuler} disabled={enregistrement}>Annuler</button>
            </>
          ) : (
            <>
              {/* Clés distinctes : le bouton « Modifier » ne doit jamais être réutilisé comme
                  bouton « Enregistrer », sinon le clic enregistre aussitôt le formulaire. */}
              {modifiable && (
                <button key="modifier" className="btn pri" type="button" onClick={(e) => { e.preventDefault(); commencerModification(); }} disabled={!a}>
                  <Icon name="edit" size={18} stroke={2} />Modifier
                </button>
              )}
              {/* Entrée en stock de cet article (12/10/2026) : la fenêtre s'ouvre avec l'article déjà choisi. */}
              {modifiable && onEntreeStock && (
                <button key="entree" className="btn" type="button" disabled={!a} title="Une livraison de cet article est arrivée"
                  onClick={(e) => { e.preventDefault(); onEntreeStock(id); }}>
                  <Icon name="plus" size={18} stroke={2.4} />Entrée en stock
                </button>
              )}
              <span className="sp" />
              <button key="fermer" className="btn" type="button" onClick={onFermer}>Fermer</button>
            </>
          )}
        </div>
      </form>
    </>
  );
}
