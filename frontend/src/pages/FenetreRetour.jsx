import { useEffect, useMemo, useRef, useState } from "react";
import ListeDeroulante from "../ListeDeroulante.jsx";
import { annulerBonRetour, confirmerRetour, creerBonRetour, signalerChangement, telechargerBonRetour } from "../api.js";
import { PastilleEtat } from "../EtatsProduit.jsx";
import { date, dateHeure, ETATS_PRODUIT, joursDeRetard, ORDRE_ETATS, quantite } from "../format.js";
import Icon from "../icons.jsx";
import ZoneSignature from "./ZoneSignature.jsx";

const TEXTE_MAX = 120;
const OBSERVATION_MAX = 250;
const deux = (n) => String(n).padStart(2, "0");
const aujourdhui = () => { const d = new Date(); return `${d.getFullYear()}-${deux(d.getMonth() + 1)}-${deux(d.getDate())}`; };
const OPTIONS_ETATS = ORDRE_ETATS.map((e) => ({ valeur: e, libelle: ETATS_PRODUIT[e].libelle }));

/** Fenêtre « Retour » d'une réquisition (Responsable Technique, 12/10/2026).
 *  - Pas de bon en cours : on prépare le bon de retour (signature au stylo), puis on le télécharge pour le magasin.
 *  - Bon en cours : on recopie le bon rempli au magasin (Qté rendue, État au retour) → le stock remonte.
 *  - Historique des bons de retour et copies d'archive. */
export default function FenetreRetour({ d, onFermer, onChange }) {
  const r = d.requisition;
  const ret = d.retour;
  const bon = ret.bon_ouvert;
  const [mode, setMode] = useState(null);           // null | "signer" (préparer le bon)
  const [signature, setSignature] = useState({ image: null, pret: false, corps: null }); // ZoneSignature
  const [saisie, setSaisie] = useState({});          // {idLigneBon: {etats: {BON: "6"}, exemplaires: {id: "BON"}, observation}}
  const [champs, setChamps] = useState({ date_retour: aujourdhui(), rendu_par: "", magasinier: "", observation: "" });
  const [verifier, setVerifier] = useState(false);
  const [annuler, setAnnuler] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreurs, setErreurs] = useState({});
  const [succes, setSucces] = useState(null);
  const [telechargement, setTelechargement] = useState(null);
  const corps = useRef(null);

  const cleBon = bon?.id ?? null;
  useEffect(() => {
    setSaisie({}); setVerifier(false); setAnnuler(false); setErreurs({}); setMode(null); setSignature({ image: null, pret: false, corps: null });
    setChamps({ date_retour: aujourdhui(), rendu_par: d.demandeur || "", magasinier: "", observation: "" });
  }, [d.id, cleBon]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setSucces(null); }, [d.id]);
  useEffect(() => {
    const touche = (e) => {
      if (e.key !== "Escape" || envoi) return;
      if (verifier) setVerifier(false); else if (annuler) setAnnuler(false); else if (mode) setMode(null); else onFermer();
    };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi, verifier, annuler, mode]);
  useEffect(() => { if ((erreurs.general || succes) && corps.current) corps.current.scrollTop = 0; }, [erreurs, succes]);

  const effacer = (cle) => setErreurs((e) => ({ ...e, [cle]: undefined, general: undefined }));
  const ligneDe = (idLigneSortie) => ret.lignes.find((l) => l.ligne_sortie === idLigneSortie);

  // ---------------------------------------------------------------- Préparer le bon de retour
  async function preparerBon() {
    setEnvoi(true); setErreurs({});
    try {
      const rep = await creerBonRetour(d.id, signature.corps);
      setSucces({ titre: `Bon de retour ${rep.numero} prêt`, texte: "Il se télécharge : imprimez-le et portez-le au magasin avec le matériel." });
      signalerChangement();
      onChange(rep.message, rep.demande);
      try { await telechargerBonRetour(rep.bon, rep.numero); } catch (e) { setErreurs({ general: e.message }); }
    } catch (err) {
      const det = err.details;
      const surSignature = det?.signature?.[0] ?? det?.mot_de_passe?.[0];
      setErreurs(surSignature && !det?.general ? { signature: surSignature }
        : { general: det?.general?.[0] ?? "L'enregistrement a échoué. Vérifiez que le serveur est démarré." });
    } finally {
      setEnvoi(false);
    }
  }

  async function telecharger(b) {
    setTelechargement(b.id); setErreurs({});
    try {
      await telechargerBonRetour(b.id, b.statut === "CONFIRME" ? `${b.numero}-archive` : b.numero);
    } catch (e) { setErreurs({ general: e.message }); } finally { setTelechargement(null); }
  }

  // ---------------------------------------------------------------- Confirmer le retour
  const lignesBon = bon?.lignes ?? [];
  const parSerie = (lb) => lb.article.suivi_par_serie;
  const rendus = (lb) => {
    if (parSerie(lb)) return Object.keys(saisie[lb.id]?.exemplaires ?? {}).length;
    return Object.values(saisie[lb.id]?.etats ?? {}).reduce((t, x) => t + (Number(x) || 0), 0);
  };
  const totalRendu = useMemo(() => lignesBon.reduce((t, lb) => t + rendus(lb), 0), [saisie, lignesBon]); // eslint-disable-line react-hooks/exhaustive-deps

  function changerEtatQte(lb, etat, valeur) {
    setSaisie((x) => ({ ...x, [lb.id]: { ...(x[lb.id] ?? {}), etats: { ...(x[lb.id]?.etats ?? {}), [etat]: valeur } } }));
    effacer(lb.id);
  }
  function cocherExemplaire(lb, e) {
    setSaisie((x) => {
      const ex = { ...(x[lb.id]?.exemplaires ?? {}) };
      if (ex[e.id] !== undefined) delete ex[e.id]; else ex[e.id] = e.etat; // état proposé : celui de la sortie
      return { ...x, [lb.id]: { ...(x[lb.id] ?? {}), exemplaires: ex } };
    });
    effacer(lb.id);
  }
  function etatExemplaire(lb, e, etat) {
    setSaisie((x) => ({ ...x, [lb.id]: { ...(x[lb.id] ?? {}), exemplaires: { ...(x[lb.id]?.exemplaires ?? {}), [e.id]: etat } } }));
    effacer(lb.id);
  }
  function observationLigne(lb, valeur) {
    setSaisie((x) => ({ ...x, [lb.id]: { ...(x[lb.id] ?? {}), observation: valeur } }));
  }
  /** « Tout a été rendu comme à la sortie » : remplit chaque ligne avec le reste, dans l'état de la sortie. */
  function toutRendu() {
    const n = {};
    lignesBon.forEach((lb) => {
      if (parSerie(lb)) {
        n[lb.id] = { ...(saisie[lb.id] ?? {}), exemplaires: Object.fromEntries(lb.exemplaires.map((e) => [e.id, e.etat])) };
      } else {
        const sortie = ligneDe(lb.ligne_sortie)?.etats_sortie ?? {};
        let reste = lb.qte_attendue;
        const etats = {};
        ORDRE_ETATS.forEach((e) => { const q = Math.min(reste, sortie[e] ?? 0); if (q > 0) { etats[e] = String(q); reste -= q; } });
        if (reste > 0) etats.BON = String((Number(etats.BON) || 0) + reste);
        n[lb.id] = { ...(saisie[lb.id] ?? {}), etats };
      }
    });
    setSaisie(n); setErreurs({});
  }

  function demanderConfirmation() {
    const err = {};
    lignesBon.forEach((lb) => {
      if (parSerie(lb)) return;
      const v = Object.values(saisie[lb.id]?.etats ?? {}).filter((x) => String(x).trim() !== "");
      if (v.some((x) => !/^\d+$/.test(String(x).trim()))) err[lb.id] = "Indiquez des nombres entiers, 0 ou plus.";
      else if (rendus(lb) > lb.qte_attendue) err[lb.id] = `Plus que le reste à rendre (${quantite(lb.qte_attendue, lb.article.unite)}).`;
    });
    if (!champs.date_retour) err.date_retour = "Indiquez la date du retour au magasin.";
    else if (champs.date_retour > aujourdhui()) err.date_retour = "Cette date est dans le futur.";
    if (!Object.keys(err).length && totalRendu === 0) {
      err.general = "Rien n'est rendu : recopiez les quantités rendues. Si le matériel n'est pas venu, annulez le bon de retour.";
    }
    if (Object.keys(err).length) { err.general ??= "Vérifiez les lignes signalées en rouge."; setErreurs(err); return; }
    setErreurs({}); setVerifier(true);
  }

  async function envoyerConfirmation() {
    setEnvoi(true); setErreurs({});
    try {
      const rep = await confirmerRetour(bon.id, {
        date_retour: champs.date_retour, rendu_par: champs.rendu_par.trim(), magasinier: champs.magasinier.trim(),
        observation: champs.observation.trim(),
        lignes: lignesBon.map((lb) => (parSerie(lb)
          ? { id: lb.id, exemplaires: saisie[lb.id]?.exemplaires ?? {}, observation: (saisie[lb.id]?.observation ?? "").trim() }
          : { id: lb.id, etats: Object.fromEntries(Object.entries(saisie[lb.id]?.etats ?? {}).map(([e, x]) => [e, Number(x) || 0])),
            observation: (saisie[lb.id]?.observation ?? "").trim() })),
      });
      setSucces({ titre: `Retour ${bon.numero} confirmé`, texte: rep.message });
      setVerifier(false);
      signalerChangement();
      onChange(rep.message, rep.demande);
    } catch (err) {
      const det = err.details;
      if (det) {
        setErreurs({ general: det.general?.[0], date_retour: det.date_retour?.[0], magasinier: det.magasinier?.[0], rendu_par: det.rendu_par?.[0],
          observation: det.observation?.[0], ...Object.fromEntries(Object.entries(det.lignes ?? {}).map(([k, v]) => [k, v[0]])) });
      } else {
        setErreurs({ general: "L'enregistrement a échoué. Vérifiez que le serveur est démarré." });
      }
      setVerifier(false);
    } finally {
      setEnvoi(false);
    }
  }

  async function annulerBon() {
    setEnvoi(true); setErreurs({});
    try {
      const rep = await annulerBonRetour(bon.id);
      setAnnuler(false);
      signalerChangement();
      onChange(rep.message, rep.demande);
    } catch (err) {
      setErreurs({ general: err.details?.general?.[0] ?? "L'annulation a échoué." });
    } finally {
      setEnvoi(false);
    }
  }

  const bloque = envoi || verifier || annuler;
  const titre = bon ? `Confirmer le retour · bon ${bon.numero}` : mode === "signer" ? "Préparer le bon de retour" : `Retours · réquisition ${r.numero}`;

  return (
    <>
      <div className="voile" onClick={() => !envoi && onFermer()} />
      <div className="fenetre large fenetre-sortie fenetre-retour" role="dialog" aria-modal="true" aria-label={titre}>
        <div className="fenetre-tete">
          <h2>{titre}</h2>
          {ret.en_retard && <span className="pill p-c titre-pill">En retard</span>}
          <span className="sp" />
          <button className="fermer" type="button" onClick={onFermer} disabled={envoi} aria-label="Fermer"><Icon name="x" size={22} stroke={2.2} /></button>
        </div>

        <div className="fenetre-corps" ref={corps}>
          {succes && (
            <div className="bandeau-fait" role="status">
              <span className="rond-fait">✓</span>
              <div><b>{succes.titre}</b><span>{succes.texte}</span></div>
            </div>
          )}
          {erreurs.general && <div className="alerte">{erreurs.general}</div>}
          {bon && (
            <div className="consigne">
              Prenez le <b>bon de retour {bon.numero} rempli au magasin</b>. Recopiez pour chaque ligne la <b>« Qté rendue »</b>
              {" "}et l'<b>« État au retour »</b> (Neuf, Bon, Moyen ou Mauvais), puis cliquez sur <b>« Confirmer le retour »</b> :
              le stock remonte.
            </div>
          )}
          {!bon && mode === "signer" && (
            <div className="consigne">
              Le bon de retour reprend <b>tout ce qui reste à rendre</b>. Signez dans le cadre en bas (case « Responsable Technique »),
              puis cliquez sur <b>« Signer et préparer le bon »</b> : il se télécharge, prêt à imprimer.
            </div>
          )}

          <div className="sortie-infos">
            <div><span>Demandeur</span><b>{d.demandeur || "—"}</b><small>{d.demandeur_departement || "—"}</small></div>
            <div><span>Chantier</span><b>{d.destination || "—"}</b><small>Magasin {d.magasin}</small></div>
            <div><span>Réquisition</span><b>{r.numero}</b><small>demande {d.numero}</small></div>
            <div><span>Matériel sorti le</span><b>{date(ret.date_remise)}</b>
              <small>{ret.solde ? "tout est rentré" : `${ret.reste_total} à rendre sur ${ret.sorti_total}`}</small></div>
          </div>

          {/* Bon en cours : la saisie du retour */}
          {bon ? (
            <>
              <div className="card">
                <table className="tableau table-sortie table-retour">
                  <thead>
                    <tr>
                      <th style={{ width: 40 }}>N°</th>
                      <th>Article</th>
                      <th style={{ width: 120 }}>État à la sortie</th>
                      <th style={{ width: 100 }} className="num">À rendre</th>
                      <th style={{ width: 440 }}>Qté rendue et état au retour</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lignesBon.map((lb, i) => {
                      const a = lb.article;
                      const ls = ligneDe(lb.ligne_sortie);
                      return (
                        <tr key={lb.id} className={erreurs[lb.id] ? "ligne-erreur" : undefined}>
                          <td className="centre">{i + 1}</td>
                          <td className="nom">
                            <span className="code">{a.code}</span> {a.nom}
                            {ls?.date_retour_prevue && (
                              <small className={`series-remis${ls.en_retard ? " rouge" : ""}`}>
                                Retour prévu le {date(ls.date_retour_prevue)}{ls.en_retard ? ` · en retard de ${joursDeRetard(ls.date_retour_prevue)} j` : ""}
                              </small>
                            )}
                            {ls?.deja_rendu > 0 && <small className="series-remis">Déjà rendu : {quantite(ls.deja_rendu, a.unite)} sur {quantite(ls.qte_sortie, a.unite)}</small>}
                          </td>
                          <td>{parSerie(lb) ? <small className="discret">par n° de série</small> : (ls?.etats_sortie_texte || "—")}</td>
                          <td className="num"><b>{quantite(lb.qte_attendue, a.unite)}</b></td>
                          <td>
                            {parSerie(lb) ? (
                              <fieldset className="retour-series" disabled={bloque}>
                                <legend>Cochez les n° de série rendus et choisissez leur état :</legend>
                                {lb.exemplaires.map((e) => {
                                  const choisi = saisie[lb.id]?.exemplaires?.[e.id];
                                  return (
                                    <div key={e.id} className={`retour-serie${choisi !== undefined ? " coche" : ""}`}>
                                      <label>
                                        <input type="checkbox" checked={choisi !== undefined} onChange={() => cocherExemplaire(lb, e)} />
                                        <span className="code">{e.numero_serie}</span>
                                        <small>sorti <PastilleEtat etat={e.etat} /></small>
                                      </label>
                                      {choisi !== undefined && (
                                        <ListeDeroulante ariaLabel={`État au retour du n° ${e.numero_serie}`} recherche={false} petite
                                          valeur={choisi} onChange={(v) => etatExemplaire(lb, e, v)} options={OPTIONS_ETATS} />
                                      )}
                                    </div>
                                  );
                                })}
                              </fieldset>
                            ) : (
                              <div className="retour-etats">
                                {ORDRE_ETATS.map((e) => (
                                  <label key={e} className={`retour-etat ${ETATS_PRODUIT[e].classe}-bord`}>
                                    <span>{ETATS_PRODUIT[e].libelle}</span>
                                    <input className={`saisie petite${erreurs[lb.id] ? " invalide" : ""}`} type="number" min="0" step="1" inputMode="numeric"
                                      value={saisie[lb.id]?.etats?.[e] ?? ""} disabled={bloque} placeholder="0"
                                      aria-label={`Qté rendue en « ${ETATS_PRODUIT[e].libelle} » : ${a.nom}`}
                                      onChange={(ev) => changerEtatQte(lb, e, ev.target.value)} />
                                  </label>
                                ))}
                              </div>
                            )}
                            <div className="retour-total">
                              Rendu : <b>{quantite(rendus(lb), a.unite)}</b> sur {quantite(lb.qte_attendue, a.unite)}
                              {rendus(lb) > 0 && rendus(lb) < lb.qte_attendue && (
                                <span className="partiel"> · reste {quantite(lb.qte_attendue - rendus(lb), a.unite)} (bon suivant)</span>
                              )}
                            </div>
                            <input className="saisie petite obs-ligne" maxLength={OBSERVATION_MAX} placeholder="Observation (facultatif)"
                              value={saisie[lb.id]?.observation ?? ""} disabled={bloque} aria-label={`Observation : ${a.nom}`}
                              onChange={(ev) => observationLigne(lb, ev.target.value)} />
                            {erreurs[lb.id] && <em className="msg-erreur">{erreurs[lb.id]}</em>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <button type="button" className="btn lien tout-livre" disabled={bloque} onClick={toutRendu}>
                <Icon name="check" size={16} stroke={2.2} />Tout a été rendu, dans l'état de la sortie (remplir les cases)
              </button>

              <div className="sortie-champs retour-champs">
                <div className={`champ-saisie${erreurs.date_retour ? " en-erreur" : ""}`}>
                  <label htmlFor="date-retour">Matériel rendu le</label>
                  <input id="date-retour" className="saisie" type="date" min={ret.date_remise} max={aujourdhui()} value={champs.date_retour}
                    disabled={bloque} onChange={(e) => { setChamps({ ...champs, date_retour: e.target.value }); effacer("date_retour"); }} />
                  {erreurs.date_retour && <em className="msg-erreur">{erreurs.date_retour}</em>}
                </div>
                <div className={`champ-saisie${erreurs.rendu_par ? " en-erreur" : ""}`}>
                  <label htmlFor="rendu-par">Rendu par <span className="facultatif">(nom écrit sur le bon)</span></label>
                  <input id="rendu-par" className="saisie" maxLength={TEXTE_MAX} value={champs.rendu_par} disabled={bloque}
                    onChange={(e) => setChamps({ ...champs, rendu_par: e.target.value })} />
                  {erreurs.rendu_par && <em className="msg-erreur">{erreurs.rendu_par}</em>}
                </div>
                <div className={`champ-saisie${erreurs.magasinier ? " en-erreur" : ""}`}>
                  <label htmlFor="magasinier-retour">Reçu par (magasinier) <span className="facultatif">(facultatif)</span></label>
                  <input id="magasinier-retour" className="saisie" maxLength={TEXTE_MAX} value={champs.magasinier} disabled={bloque}
                    onChange={(e) => setChamps({ ...champs, magasinier: e.target.value })} />
                  {erreurs.magasinier && <em className="msg-erreur">{erreurs.magasinier}</em>}
                </div>
                <div className={`champ-saisie large${erreurs.observation ? " en-erreur" : ""}`}>
                  <label htmlFor="observation-retour">Observation <span className="facultatif">(facultatif)</span></label>
                  <input id="observation-retour" className="saisie" maxLength={OBSERVATION_MAX} value={champs.observation} disabled={bloque}
                    onChange={(e) => setChamps({ ...champs, observation: e.target.value })} />
                  {erreurs.observation && <em className="msg-erreur">{erreurs.observation}</em>}
                </div>
              </div>
            </>
          ) : (
            /* Pas de bon en cours : ce qui est sorti et ce qui reste à rendre */
            <div className="card">
              <table className="tableau table-sortie table-retour">
                <thead>
                  <tr>
                    <th style={{ width: 110 }}>Code article</th>
                    <th>Désignation</th>
                    <th style={{ width: 150 }}>État à la sortie</th>
                    <th style={{ width: 90 }} className="num">Sorti</th>
                    <th style={{ width: 90 }} className="num">Rendu</th>
                    <th style={{ width: 90 }} className="num">Reste</th>
                    <th style={{ width: 130 }}>Retour prévu</th>
                  </tr>
                </thead>
                <tbody>
                  {ret.lignes.map((l) => (
                    <tr key={l.ligne_sortie}>
                      <td><span className="code">{l.article.code}</span></td>
                      <td className="nom">
                        {l.article.nom}
                        {l.exemplaires.length > 0 && (
                          <small className="series-remis">
                            {l.exemplaires.map((e) => `${e.numero_serie}${e.rendu ? ` (rendu, ${e.bon})` : ""}`).join(" · ")}
                          </small>
                        )}
                      </td>
                      <td>{l.etats_sortie_texte || "—"}</td>
                      <td className="num">{quantite(l.qte_sortie, l.article.unite)}</td>
                      <td className="num">{quantite(l.deja_rendu, l.article.unite)}</td>
                      <td className="num"><b className={l.reste ? (l.en_retard ? "rouge" : "") : "vert"}>{quantite(l.reste, l.article.unite)}</b></td>
                      <td className={l.en_retard ? "rouge" : ""}>
                        {date(l.date_retour_prevue)}
                        {l.en_retard && <small className="series-remis rouge">en retard de {joursDeRetard(l.date_retour_prevue)} j</small>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!bon && mode === "signer" && (
            <section className="signer">
              <h3>Votre signature <span className="facultatif">(case « Responsable Technique » du bon de retour)</span></h3>
              <p className="signataire">Le bon est daté d'aujourd'hui, {new Date().toLocaleDateString("fr-FR")}.</p>
              <ZoneSignature onChange={setSignature} desactive={envoi} erreur={erreurs.signature} />
            </section>
          )}

          {ret.bons.length > 0 && (
            <section className="bloc bons-retour">
              <h3>Bons de retour</h3>
              <ul>
                {ret.bons.map((b) => (
                  <li key={b.id}>
                    <span className="code">{b.numero}</span>
                    {b.statut === "CONFIRME" ? (
                      <span className="discret">
                        rendu le {date(b.date_retour)} · {b.lignes.reduce((t, lb) => t + lb.qte_rendue, 0)} article(s)
                        {b.lignes.some((lb) => lb.etats_texte) && ` (${b.lignes.map((lb) => lb.etats_texte).filter(Boolean).join(" ; ")})`}
                        {" "}· confirmé le {dateHeure(b.confirme_le)} par {b.confirme_par}
                      </span>
                    ) : <span className="pill p-w">À confirmer</span>}
                    <span className="sp" />
                    <button type="button" className="btn-details" disabled={telechargement === b.id} onClick={() => telecharger(b)}>
                      <Icon name="download" size={15} stroke={2} />{telechargement === b.id ? "…" : b.statut === "CONFIRME" ? "Copie d'archive" : "Bon (PDF)"}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <div className={`fiche-pied${verifier || annuler ? " verifier" : ""}`}>
          {bon && verifier ? (
            <>
              <div className="question">
                Confirmer le retour {bon.numero} ?
                <small>{totalRendu} article{totalRendu > 1 ? "s" : ""} rendu{totalRendu > 1 ? "s" : ""} : le stock va remonter. Cette opération ne peut pas être annulée dans GestiStock.</small>
              </div>
              <span className="sp" />
              <button className="btn" type="button" disabled={envoi} onClick={() => setVerifier(false)}>Non, revenir</button>
              <button className="btn pri" type="button" disabled={envoi} onClick={envoyerConfirmation} autoFocus>
                <Icon name="check" size={18} stroke={2.2} />{envoi ? "Enregistrement…" : "Oui, confirmer le retour"}
              </button>
            </>
          ) : bon && annuler ? (
            <>
              <div className="question">
                Annuler le bon de retour {bon.numero} ?
                <small>À faire si le matériel n'est pas venu au magasin. Le numéro ne sera pas réutilisé ; vous pourrez préparer un nouveau bon.</small>
              </div>
              <span className="sp" />
              <button className="btn" type="button" disabled={envoi} onClick={() => setAnnuler(false)}>Non, garder le bon</button>
              <button className="btn danger" type="button" disabled={envoi} onClick={annulerBon}>{envoi ? "Annulation…" : "Oui, annuler le bon"}</button>
            </>
          ) : bon ? (
            <>
              <button className="btn" type="button" disabled={telechargement === bon.id} onClick={() => telecharger(bon)}>
                <Icon name="download" size={17} stroke={2.2} />{telechargement === bon.id ? "Téléchargement…" : "Télécharger le bon"}
              </button>
              <button className="btn lien" type="button" onClick={() => setAnnuler(true)}>Annuler ce bon…</button>
              <span className="sp" />
              <button className="btn" type="button" onClick={onFermer}>Fermer</button>
              <button className="btn pri" type="button" onClick={demanderConfirmation}>
                <Icon name="back" size={18} stroke={2} />Confirmer le retour…
              </button>
            </>
          ) : mode === "signer" ? (
            <>
              <span className="sp" />
              <button className="btn" type="button" disabled={envoi} onClick={() => setMode(null)}>Annuler</button>
              <button className="btn pri" type="button" disabled={envoi || !signature.pret} onClick={preparerBon}
                title={signature.pret ? undefined : signature.image ? "Retapez votre mot de passe" : "Signez d'abord"}>
                <Icon name="sign" size={18} stroke={2} />{envoi ? "Préparation…" : "Signer et préparer le bon"}
              </button>
            </>
          ) : (
            <>
              <span className="sp" />
              <button className="btn" type="button" onClick={onFermer}>Fermer</button>
              {!ret.solde && (
                <button className="btn pri" type="button" onClick={() => { setSucces(null); setMode("signer"); }}>
                  <Icon name="doc" size={18} stroke={2} />Préparer le bon de retour…
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
