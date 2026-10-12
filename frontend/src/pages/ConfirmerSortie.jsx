import { useEffect, useMemo, useRef, useState } from "react";
import { confirmerSortie, signalerChangement, telechargerArchive } from "../api.js";
import { PastilleEtat } from "../EtatsProduit.jsx";
import { date, dateHeure, ETATS_PRODUIT, ETATS_UTILISABLES, quantite, texteEtats } from "../format.js";
import Icon from "../icons.jsx";
import FenetreBon from "./FenetreBon.jsx";

const OBSERVATION_MAX = 250;
const deux = (n) => String(n).padStart(2, "0");
const aujourdhui = () => { const d = new Date(); return `${d.getFullYear()}-${deux(d.getMonth() + 1)}-${deux(d.getDate())}`; };
const unite = (u) => (u === "m" ? "m" : u === "paire" ? "paire(s)" : "pièce(s)");

/** Lignes du bon : quantité accordée (sinon demandée), sans les articles retirés (0). */
export const lignesDuBon = (d) => d.lignes.map((l) => ({ ...l, qte: l.qte_accordee ?? l.quantite })).filter((l) => l.qte > 0);

/** Fenêtre « Confirmer la sortie » (Agent Logistique, 12/10/2026).
 *  Le bon signé par le magasinier revient du magasin : on recopie la colonne « Qté livrée »
 *  (on coche les n° de série remis pour le matériel suivi par exemplaire) → le stock diminue.
 *  Une sortie déjà confirmée s'ouvre en lecture, avec la copie d'archive du bon. */
export default function ConfirmerSortie({ d, onFermer, onConfirmee }) {
  const r = d.requisition;
  const sortie = r.sortie;
  const lignes = useMemo(() => lignesDuBon(d), [d]);
  const [livrees, setLivrees] = useState({});       // {idLigne: "6"}
  const [series, setSeries] = useState({});         // {idLigne: [idExemplaire…]}
  const [parEtat, setParEtat] = useState({});       // {idLigne: {NEUF: "3", BON: "2"}} quand le stock a plusieurs états
  const [dateRemise, setDateRemise] = useState(aujourdhui);
  const [magasinier, setMagasinier] = useState("");
  const [observation, setObservation] = useState("");
  const [verifier, setVerifier] = useState(false);  // dernière question avant d'enregistrer
  const [envoi, setEnvoi] = useState(false);
  const [erreurs, setErreurs] = useState({});
  const [succes, setSucces] = useState(null);
  const [voirBon, setVoirBon] = useState(false);
  const [archive, setArchive] = useState(false);
  const corps = useRef(null);

  useEffect(() => {
    setLivrees({}); setSeries({}); setParEtat({}); setDateRemise(aujourdhui()); setMagasinier(""); setObservation("");
    setVerifier(false); setErreurs({}); setSucces(null);
  }, [d.id]);
  useEffect(() => {
    const touche = (e) => {
      if (e.key !== "Escape" || envoi || voirBon) return;
      if (verifier) setVerifier(false); else onFermer();
    };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi, verifier, voirBon]);
  useEffect(() => { if ((erreurs.general || succes) && corps.current) corps.current.scrollTop = 0; }, [erreurs, succes]);

  const parSerie = (l) => l.article.suivi_par_serie;
  // État du produit (12/10/2026) : si le stock disponible a plusieurs états, on indique combien de chaque état est sorti.
  const etatsEnStock = (l) => ETATS_UTILISABLES.filter((e) => (l.article.etats?.[e] ?? 0) > 0);
  const plusieursEtats = (l) => !parSerie(l) && etatsEnStock(l).length > 1;
  const sommeEtats = (l) => {
    const v = Object.values(parEtat[l.id] ?? {}).filter((x) => String(x).trim() !== "");
    return v.length ? String(v.reduce((t, x) => t + (Number(x) || 0), 0)) : "";
  };
  const valeur = (l) => (parSerie(l) ? String((series[l.id] ?? []).length) : plusieursEtats(l) ? sommeEtats(l) : (livrees[l.id] ?? ""));
  const effacer = (cle) => setErreurs((e) => ({ ...e, [cle]: undefined, general: undefined }));

  function toutLivre() {
    setLivrees(Object.fromEntries(lignes.filter((l) => !parSerie(l) && !plusieursEtats(l)).map((l) => [l.id, String(l.qte)])));
    setErreurs({});
  }

  function cocher(l, id) {
    setSeries((x) => {
      const deja = x[l.id] ?? [];
      return { ...x, [l.id]: deja.includes(id) ? deja.filter((i) => i !== id) : [...deja, id] };
    });
    effacer(l.id);
  }

  // Contrôles immédiats (le serveur vérifie aussi), puis la question « Confirmer ? ».
  function demanderConfirmation() {
    const err = {};
    lignes.forEach((l) => {
      if (parSerie(l)) {
        if ((series[l.id] ?? []).length > l.qte) err[l.id] = `Pas plus de ${l.qte} n° de série (quantité du bon).`;
        return;
      }
      if (plusieursEtats(l)) {
        const saisies = Object.entries(parEtat[l.id] ?? {}).filter(([, x]) => String(x).trim() !== "");
        if (!saisies.length) err[l.id] = "Indiquez combien sont sortis dans chaque état (0 si rien n'a été remis).";
        else if (saisies.some(([, x]) => !/^\d+$/.test(String(x).trim()))) err[l.id] = "Indiquez des nombres entiers, 0 ou plus.";
        else if (saisies.some(([e, x]) => Number(x) > (l.article.etats?.[e] ?? 0))) err[l.id] = "Plus que le stock de cet état.";
        else if (Number(sommeEtats(l)) > l.qte) err[l.id] = `Plus que la quantité du bon (${quantite(l.qte, l.article.unite)}).`;
        return;
      }
      const v = (livrees[l.id] ?? "").trim();
      if (v === "") err[l.id] = "Recopiez la quantité livrée (0 si le magasin n'a rien remis).";
      else if (!/^\d+$/.test(v)) err[l.id] = "Indiquez un nombre entier, 0 ou plus.";
      else if (Number(v) > l.qte) err[l.id] = `Plus que la quantité du bon (${quantite(l.qte, l.article.unite)}).`;
    });
    if (!dateRemise) err.date_remise = "Indiquez la date de remise du matériel.";
    else if (dateRemise > aujourdhui()) err.date_remise = "Cette date est dans le futur.";
    if (!Object.keys(err).length && lignes.every((l) => Number(valeur(l)) === 0)) {
      err.general = "Toutes les quantités livrées sont à 0 : si le magasin n'a rien remis, ne confirmez pas la sortie.";
    }
    if (Object.keys(err).length) {
      err.general ??= "Vérifiez les cases signalées en rouge.";
      setErreurs(err);
      return;
    }
    setErreurs({});
    setVerifier(true);
  }

  async function envoyer() {
    setEnvoi(true); setErreurs({});
    try {
      const rep = await confirmerSortie(d.id, {
        date_remise: dateRemise, magasinier: magasinier.trim(), observation: observation.trim(),
        lignes: lignes.map((l) => (parSerie(l) ? { id: l.id, exemplaires: series[l.id] ?? [] }
          : plusieursEtats(l) ? { id: l.id, qte_livree: Number(sommeEtats(l)),
            etats: Object.fromEntries(Object.entries(parEtat[l.id] ?? {}).map(([e, x]) => [e, Number(x) || 0])) }
            : { id: l.id, qte_livree: Number(livrees[l.id]) })),
      });
      setSucces(rep.message); setVerifier(false);
      signalerChangement();
      onConfirmee(rep.message, rep.demande);
    } catch (err) {
      const det = err.details;
      if (det) {
        setErreurs({ general: det.general?.[0], date_remise: det.date_remise?.[0], magasinier: det.magasinier?.[0],
          observation: det.observation?.[0], ...Object.fromEntries(Object.entries(det.lignes ?? {}).map(([k, v]) => [k, v[0]])) });
      } else {
        setErreurs({ general: "L'enregistrement a échoué. Vérifiez que le serveur est démarré." });
      }
      setVerifier(false);
    } finally {
      setEnvoi(false);
    }
  }

  async function telechargerCopie() {
    setArchive(true); setErreurs({});
    try { await telechargerArchive(d.id, r.numero); } catch (e) { setErreurs({ general: e.message }); } finally { setArchive(false); }
  }

  const aSaisir = !sortie;
  const partielles = lignes.filter((l) => valeur(l) !== "" && Number(valeur(l)) < l.qte).length;

  return (
    <>
      <div className="voile" onClick={() => !envoi && onFermer()} />
      <div className="fenetre large fenetre-sortie" role="dialog" aria-modal="true" aria-label={`Sortie du bon ${r.numero}`}>
        <div className="fenetre-tete">
          <h2>{aSaisir ? "Confirmer la sortie" : "Sortie confirmée"} · bon {r.numero}</h2>
          {d.urgent && <span className="pill p-c titre-pill">Urgent</span>}
          <span className="sp" />
          <button className="fermer" type="button" onClick={onFermer} disabled={envoi} aria-label="Fermer"><Icon name="x" size={22} stroke={2.2} /></button>
        </div>

        <div className="fenetre-corps" ref={corps}>
          {succes && (
            <div className="bandeau-fait" role="status">
              <span className="rond-fait">✓</span>
              <div><b>Sortie confirmée</b><span>{succes}</span></div>
            </div>
          )}
          {erreurs.general && <div className="alerte">{erreurs.general}</div>}
          {aSaisir && (
            <div className="consigne">
              Prenez le <b>bon signé par le magasinier</b>. Recopiez les colonnes <b>« Qté livrée »</b> et <b>« État »</b>
              {lignes.some(parSerie) && <> et cochez les <b>n° de série remis</b></>}, puis cliquez sur <b>« Confirmer la sortie »</b>.
              Le stock de GestiStock diminuera de ces quantités.
            </div>
          )}

          <div className="sortie-infos">
            <div><span>Demandeur</span><b>{d.demandeur || "—"}</b><small>{d.demandeur_departement || "—"}</small></div>
            <div><span>Chantier</span><b>{d.destination || "—"}</b><small>Magasin {d.magasin}</small></div>
            <div><span>Demande</span><b>{d.numero}</b><small>du {dateHeure(d.cree_le)}</small></div>
            <div><span>Bon imprimé</span><b>{dateHeure(r.imprimee_le)}</b><small>par {r.imprimee_par}</small></div>
          </div>

          <div className="card">
            <table className="tableau table-sortie">
              <thead>
                <tr>
                  <th style={{ width: 44 }}>N°</th>
                  <th style={{ width: 110 }}>Code article</th>
                  <th>Désignation</th>
                  <th style={{ width: 120 }} className="num">Qté sur le bon</th>
                  {aSaisir && <th style={{ width: 120 }} className="num">En stock</th>}
                  <th style={{ width: aSaisir ? 230 : 140 }}>Qté livrée</th>
                </tr>
              </thead>
              <tbody>
                {lignes.map((l, i) => {
                  const a = l.article;
                  const fait = sortie?.lignes[l.id];
                  const v = valeur(l);
                  const partielle = !parSerie(l) && v !== "" && /^\d+$/.test(v) && Number(v) < l.qte;
                  return (
                    <tr key={l.id} className={erreurs[l.id] ? "ligne-erreur" : undefined}>
                      <td className="centre">{i + 1}</td>
                      <td><span className="code">{a.code}</span></td>
                      <td className="nom">
                        {a.nom}
                        {aSaisir && parSerie(l) && (
                          <fieldset className="series" disabled={envoi || verifier}>
                            <legend>Cochez les n° de série remis par le magasinier :</legend>
                            {(l.exemplaires_en_stock ?? []).length === 0 && <small className="rouge">Aucun exemplaire « En stock » pour cet article.</small>}
                            {(l.exemplaires_en_stock ?? []).map((e) => (
                              <label key={e.id} className="serie">
                                <input type="checkbox" checked={(series[l.id] ?? []).includes(e.id)} onChange={() => cocher(l, e.id)} />
                                <span className="code">{e.numero_serie}</span>{e.code_immo && <small> · immo {e.code_immo}</small>} <PastilleEtat etat={e.etat} />
                              </label>
                            ))}
                          </fieldset>
                        )}
                        {fait?.exemplaires.length > 0 && <small className="series-remis">N° de série : {fait.exemplaires.join(", ")}</small>}
                        {fait && texteEtats(fait.etats) && <small className="series-remis">État : {texteEtats(fait.etats)}</small>}
                      </td>
                      <td className="num"><b>{quantite(l.qte, a.unite)}</b></td>
                      {aSaisir && (
                        <td className="num">
                          <span className={a.qte_disponible < l.qte ? "rouge" : "vert"}>{quantite(a.qte_disponible, a.unite)}</span>
                        </td>
                      )}
                      <td>
                        {aSaisir ? (
                          parSerie(l) ? (
                            <div className="livree-serie"><b>{v}</b> <small>coché{Number(v) > 1 ? "s" : ""} sur {l.qte}</small></div>
                          ) : plusieursEtats(l) ? (
                            <div className="livree-etats">
                              {etatsEnStock(l).map((e) => (
                                <label key={e} className="livree-etat">
                                  <span>{ETATS_PRODUIT[e].libelle} <small>({quantite(a.etats[e], a.unite)} en stock)</small></span>
                                  <input className={`saisie petite${erreurs[l.id] ? " invalide" : ""}`} type="number" min="0" max={a.etats[e]} step="1"
                                    inputMode="numeric" value={parEtat[l.id]?.[e] ?? ""} disabled={envoi || verifier}
                                    aria-label={`Qté livrée en « ${ETATS_PRODUIT[e].libelle} » : ${a.nom}`}
                                    onChange={(ev) => { setParEtat((x) => ({ ...x, [l.id]: { ...(x[l.id] ?? {}), [e]: ev.target.value } })); effacer(l.id); }} />
                                </label>
                              ))}
                              <small className="livree-total">Total livré : <b>{v === "" ? "—" : quantite(Number(v), a.unite)}</b></small>
                            </div>
                          ) : (
                            <div className="avec-unite">
                              <input id={`livree-${l.id}`} className={`saisie livree${erreurs[l.id] ? " invalide" : ""}`} type="number" min="0" max={l.qte}
                                step="1" inputMode="numeric" value={v} disabled={envoi || verifier} aria-label={`Qté livrée : ${a.nom}`}
                                onChange={(e) => { setLivrees((x) => ({ ...x, [l.id]: e.target.value })); effacer(l.id); }} />
                              <small>{unite(a.unite)}</small>
                              {etatsEnStock(l).length === 1 && <PastilleEtat etat={etatsEnStock(l)[0]} />}
                            </div>
                          )
                        ) : (
                          <b className={fait && fait.qte_livree < l.qte ? "a-completer" : ""}>{quantite(fait?.qte_livree ?? 0, a.unite)}</b>
                        )}
                        {aSaisir && partielle && !erreurs[l.id] && <small className="partiel">{quantite(l.qte - Number(v), a.unite)} de moins que le bon</small>}
                        {erreurs[l.id] && <em className="msg-erreur">{erreurs[l.id]}</em>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {aSaisir && lignes.some((l) => !parSerie(l)) && (
            <button type="button" className="btn lien tout-livre" disabled={envoi || verifier} onClick={toutLivre}>
              <Icon name="check" size={16} stroke={2.2} />Tout a été livré comme sur le bon (remplir les cases)
            </button>
          )}

          {aSaisir ? (
            <div className="sortie-champs">
              <div className={`champ-saisie${erreurs.date_remise ? " en-erreur" : ""}`}>
                <label htmlFor="date-remise">Matériel remis le</label>
                <input id="date-remise" className="saisie" type="date" max={aujourdhui()} value={dateRemise} disabled={envoi || verifier}
                  onChange={(e) => { setDateRemise(e.target.value); effacer("date_remise"); }} />
                {erreurs.date_remise && <em className="msg-erreur">{erreurs.date_remise}</em>}
              </div>
              <div className={`champ-saisie${erreurs.magasinier ? " en-erreur" : ""}`}>
                <label htmlFor="magasinier">Magasinier <span className="facultatif">(nom écrit sur le bon, facultatif)</span></label>
                <input id="magasinier" className="saisie" maxLength={120} value={magasinier} disabled={envoi || verifier}
                  onChange={(e) => { setMagasinier(e.target.value); effacer("magasinier"); }} />
                {erreurs.magasinier && <em className="msg-erreur">{erreurs.magasinier}</em>}
              </div>
              <div className={`champ-saisie large${erreurs.observation ? " en-erreur" : ""}`}>
                <label htmlFor="observation">Observation <span className="facultatif">(facultatif, ex. « 2 manquants, rupture »)</span></label>
                <input id="observation" className="saisie" maxLength={OBSERVATION_MAX} value={observation} disabled={envoi || verifier}
                  onChange={(e) => { setObservation(e.target.value); effacer("observation"); }} />
                {erreurs.observation && <em className="msg-erreur">{erreurs.observation}</em>}
              </div>
            </div>
          ) : (
            <section className="bloc">
              <div className="champs">
                <div className="champ"><span>Matériel remis le</span><b>{date(sortie.date_remise)}</b></div>
                <div className="champ"><span>Magasinier</span><b>{sortie.magasinier || "—"}</b></div>
                <div className="champ large"><span>Sortie confirmée</span><b>{dateHeure(sortie.confirmee_le)} <span className="discret">par {sortie.confirmee_par}</span></b></div>
                {sortie.observation && <div className="champ large"><span>Observation</span><b>{sortie.observation}</b></div>}
              </div>
            </section>
          )}
        </div>

        <div className={`fiche-pied${verifier ? " verifier" : ""}`}>
          {aSaisir && verifier ? (
            <>
              <div className="question">
                Confirmer la sortie du bon {r.numero} ?
                <small>
                  Le stock va diminuer{partielles ? ` (${partielles} article${partielles > 1 ? "s" : ""} livré${partielles > 1 ? "s" : ""} en partie)` : ""}.
                  Vérifiez les quantités : cette opération ne peut pas être annulée dans GestiStock.
                </small>
              </div>
              <span className="sp" />
              <button className="btn" type="button" disabled={envoi} onClick={() => setVerifier(false)}>Non, revenir</button>
              <button className="btn pri" type="button" disabled={envoi} onClick={envoyer} autoFocus>
                <Icon name="check" size={18} stroke={2.2} />{envoi ? "Enregistrement…" : "Oui, confirmer la sortie"}
              </button>
            </>
          ) : (
            <>
              <button className="btn" type="button" onClick={() => setVoirBon(true)}><Icon name="doc" size={18} />Voir le bon</button>
              {!aSaisir && (
                <button className="btn" type="button" disabled={archive} onClick={telechargerCopie}>
                  <Icon name="download" size={17} stroke={2.2} />{archive ? "Téléchargement…" : "Copie d'archive (PDF)"}
                </button>
              )}
              <span className="sp" />
              <button className="btn" type="button" onClick={onFermer}>{aSaisir ? "Annuler" : "Fermer"}</button>
              {aSaisir && (
                <button className="btn pri" type="button" onClick={demanderConfirmation}>
                  <Icon name="out" size={18} stroke={2} />Confirmer la sortie…
                </button>
              )}
            </>
          )}
        </div>
      </div>
      {voirBon && <FenetreBon d={d} titre={`Bon de réquisition ${r.numero}`} onFermer={() => setVoirBon(false)} />}
    </>
  );
}
