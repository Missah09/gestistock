import { useEffect, useRef, useState } from "react";
import { attribuerNumero, refuserDemande, renvoyerEmail, validerDemande } from "../api.js";
import { quantite } from "../format.js";
import Icon from "../icons.jsx";
import { BlocArticle, BlocDemande, BlocRequisition, Champ, Suivi } from "./DetailDemande.jsx";
import FenetreBon from "./FenetreBon.jsx";
import { statutAffiche } from "./TableauDemandes.jsx";

const MOTIF_MAX = 250;

/** Case « Qté accordée » modifiable (validation partielle possible ; 0 = article retiré). */
function SaisieAccorde({ l, valeur, onChange, erreur, desactive }) {
  const a = l.article;
  const n = valeur === "" ? null : Number(valeur);
  let aide = null;
  if (n === 0) aide = <small className="a-completer">Article retiré : il ne figurera pas sur la réquisition.</small>;
  else if (n !== null && n < l.quantite) aide = <small>Validation partielle : {quantite(l.quantite - n, a.unite)} de moins que demandé.</small>;
  else if (n !== null && n > l.quantite) aide = <small>{quantite(n - l.quantite, a.unite)} de plus que demandé.</small>;
  const auDela = n !== null && n > a.qte_disponible;
  return (
    <div className={`champ large accorde-saisie${erreur ? " en-erreur" : ""}`}>
      <label htmlFor={`accorde-${l.id}`}>Qté accordée <span className="facultatif">(modifiable)</span></label>
      <div className="avec-unite">
        <input id={`accorde-${l.id}`} className="saisie" type="number" min="0" step="1" inputMode="numeric"
          value={valeur} disabled={desactive} onChange={(e) => onChange(e.target.value)} />
        <small>{a.unite === "m" ? "m" : a.unite === "paire" ? "paire(s)" : "pièce(s)"}</small>
        {n !== l.quantite && (
          <button type="button" className="btn lien effacer" disabled={desactive} onClick={() => onChange(String(l.quantite))}>
            Remettre {quantite(l.quantite, a.unite)}
          </button>
        )}
      </div>
      {aide}
      {auDela && <small className="rouge">Plus que la quantité disponible ({quantite(a.qte_disponible, a.unite)}).</small>}
      {erreur && <em>{erreur}</em>}
    </div>
  );
}

/** Panneau de l'Agent Logistique : vérifier la demande, ajuster les quantités, Valider (crée la réquisition) ou Refuser. */
export default function ValiderDemande({ demande: d, onFermer, onTraitee, onMiseAJour, emails = false, signataire = "" }) {
  const enAttente = d.statut === "EN_ATTENTE";
  const [accordes, setAccordes] = useState({});
  const [numero, setNumero] = useState(null); // n° de réquisition attribué au clic sur « Valider »
  const [mode, setMode] = useState(null); // null | "valider" (fenêtre de signature) | "refuser" (motif en bas) | "voir" (bon)
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreurs, setErreurs] = useState({});
  const [succes, setSucces] = useState(null); // confirmation affichée dans le panneau après Valider / Refuser
  const statut = statutAffiche(d);
  const corps = useRef(null);

  // Une erreur apparaît : on la montre (le panneau peut être défilé plus bas).
  useEffect(() => {
    if (erreurs.general || succes) { if (corps.current) corps.current.scrollTop = 0; if (erreurs.general) return; }
    const ligne = d.lignes.find((l) => erreurs[l.id]);
    if (ligne) document.getElementById(`accorde-${ligne.id}`)?.focus();
  }, [erreurs, succes]); // eslint-disable-line react-hooks/exhaustive-deps

  // Nouvelle demande ouverte : les quantités accordées repartent des quantités demandées.
  useEffect(() => {
    setAccordes(Object.fromEntries(d.lignes.map((l) => [l.id, String(l.quantite)])));
    setMode(null); setMotif(""); setErreurs({}); setSucces(null); setNumero(null);
  }, [d.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // La demande a changé pendant la lecture (ex. annulée par le demandeur) : plus de confirmation en cours.
  useEffect(() => { if (!enAttente) setMode(null); }, [enAttente]);

  useEffect(() => {
    const touche = (e) => {
      if (e.key !== "Escape" || envoi) return;
      if (mode) setMode(null); else onFermer();
    };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi, mode]);

  // « Renvoyer l'email » au Responsable (ex. après avoir configuré Gmail).
  const [renvoi, setRenvoi] = useState(false);
  async function renvoyer() {
    setRenvoi(true); setErreurs({});
    try {
      const r = await renvoyerEmail(d.id);
      onMiseAJour?.(r.demande);
      if (!r.email_ok) setErreurs({ general: r.message });
    } catch (err) {
      setErreurs({ general: err.details?.general?.[0] ?? "L'envoi a échoué. Vérifiez que le serveur est démarré." });
    } finally {
      setRenvoi(false);
    }
  }

  const valeurs = d.lignes.map((l) => accordes[l.id] ?? String(l.quantite));
  const toutAZero = valeurs.every((v) => v !== "" && Number(v) === 0);
  const modifiees = d.lignes.filter((l, i) => valeurs[i] !== String(l.quantite)).length;

  async function demanderValidation() {
    // Contrôle immédiat, avant la confirmation (le serveur vérifie aussi).
    const err = {};
    d.lignes.forEach((l, i) => {
      const v = valeurs[i];
      if (v === "") err[l.id] = "Indiquez la quantité accordée (0 pour retirer l'article).";
      else if (!/^\d+$/.test(v)) err[l.id] = "Indiquez un nombre entier, 0 ou plus.";
    });
    if (!Object.keys(err).length && toutAZero) err.general = "Toutes les quantités sont à 0 : accordez au moins un article, ou refusez la demande.";
    setErreurs(err);
    if (Object.keys(err).length) return;
    // Le n° de réquisition est attribué dès ce clic : il s'affiche sur le bon à signer (12/10/2026).
    try {
      const rep = await attribuerNumero(d.id);
      setNumero(rep.numero);
      setMode("valider");
    } catch (e) {
      setErreurs({ general: e.details?.general?.[0] ?? "Le n° de réquisition n'a pas pu être attribué. Vérifiez que le serveur est démarré." });
    }
  }

  async function envoyer(action, signature) {
    setEnvoi(true); setErreurs({});
    try {
      const r = action === "valider"
        ? await validerDemande(d.id, d.lignes.map((l, i) => ({ id: l.id, qte_accordee: Number(valeurs[i]) })), signature)
        : await refuserDemande(d.id, motif.trim());
      setSucces({ refus: action !== "valider", texte: r.message });
      setMode(null); setEnvoi(false);
      onTraitee(r.message, action === "valider" && !r.email_ok ? r.email : null, r.demande);
    } catch (err) {
      const det = err.details;
      if (det) {
        setErreurs({ general: det.general?.[0], motif: det.motif?.[0], signature: det.signature?.[0],
          ...Object.fromEntries(Object.entries(det.lignes ?? {}).map(([k, v]) => [k, v[0]])) });
        // Erreur sur les quantités : on ferme la fenêtre du bon pour les montrer ; sinon elle reste ouverte.
        if (det.lignes || (action === "refuser" && !det.motif)) setMode(null);
      } else {
        setErreurs({ general: "L'envoi a échoué. Vérifiez que le serveur est démarré." });
      }
      setEnvoi(false);
    }
  }

  return (
    <>
      <div className="voile" onClick={() => !envoi && onFermer()} />
      <aside className="fiche" role="dialog" aria-modal="true" aria-label={`Demande ${d.numero}`}>
        <div className="fiche-tete">
          <div>
            <h2>Demande {d.numero}</h2>
            <div className="meta">
              <span className={`pill ${statut.classe}`}>{statut.libelle}</span>
              {d.urgent && <span className="pill p-c">Urgent</span>}
              <span className="discret">{d.demandeur || "Demandeur inconnu"} · {d.lignes.length} article{d.lignes.length > 1 ? "s" : ""}</span>
            </div>
          </div>
          <button className="fermer" type="button" onClick={onFermer} disabled={envoi} aria-label="Fermer"><Icon name="x" size={22} stroke={2.2} /></button>
        </div>

        <div className="fiche-corps" ref={corps}>
          {erreurs.general && <div className="alerte">{erreurs.general}</div>}
          {succes && (
            <div className={`bandeau-fait${succes.refus ? " refus" : ""}`} role="status">
              <span className="rond-fait">{succes.refus ? "✕" : "✓"}</span>
              <div><b>{succes.refus ? "Demande refusée" : "Demande validée"}</b><span>{succes.texte}</span></div>
            </div>
          )}
          {enAttente && (
            <div className="consigne">
              Vérifiez chaque article. Modifiez au besoin la <b>Qté accordée</b> (0 pour retirer un article),
              puis cliquez sur <b>Valider</b> ou <b>Refuser</b> en bas.
            </div>
          )}
          <section className="bloc">
            <h3>Suivi</h3>
            <Suivi d={d} vueAgent />
          </section>
          <BlocDemande d={d} vueAgent />
          <BlocRequisition r={d.requisition} avecEmail={emails} onRenvoyer={emails ? renvoyer : undefined} renvoiEnCours={renvoi} />
          {d.statut === "REFUSEE" && (
            <section className="bloc"><h3>Refus</h3><div className="champs">
              <Champ libelle="Motif du refus" large>{d.motif_refus || "—"}</Champ>
            </div></section>
          )}
          {d.lignes.map((l, i) => (
            <BlocArticle key={l.id} l={l} livree={d.requisition?.sortie?.lignes[l.id]} accorde={enAttente ? (
              <SaisieAccorde l={l} valeur={valeurs[i]} erreur={erreurs[l.id]} desactive={envoi || mode === "valider"}
                onChange={(v) => { setAccordes((x) => ({ ...x, [l.id]: v })); setErreurs((e) => ({ ...e, [l.id]: undefined, general: undefined })); }} />
            ) : undefined} />
          ))}
        </div>

        <div className={`fiche-pied${mode === "refuser" ? " refus" : ""}`}>
          {enAttente && !mode && (
            <>
              <button className="btn danger" type="button" onClick={() => { setErreurs({}); setMode("refuser"); }}>Refuser…</button>
              <span className="sp" />
              <button className="btn" type="button" onClick={onFermer}>Fermer</button>
              <button className="btn pri" type="button" onClick={demanderValidation}>
                <Icon name="check" size={18} stroke={2.2} />Valider…
              </button>
            </>
          )}
          {mode === "refuser" && (
            <div className="refus-saisie">
              <label htmlFor="motif-refus" className="question">Motif du refus <span className="facultatif">(obligatoire, montré au demandeur)</span></label>
              <textarea id="motif-refus" className={`saisie zone${erreurs.motif ? " invalide" : ""}`} rows={2} maxLength={MOTIF_MAX} autoFocus
                value={motif} disabled={envoi} onChange={(e) => { setMotif(e.target.value); setErreurs((x) => ({ ...x, motif: undefined })); }}
                placeholder="Ex. : article réservé à un autre chantier" />
              <div className="refus-boutons">
                {erreurs.motif ? <em className="msg-erreur">{erreurs.motif}</em> : <small className="aide">{motif.length} / {MOTIF_MAX}</small>}
                <span className="sp" />
                <button className="btn" type="button" disabled={envoi} onClick={() => setMode(null)}>Non, revenir</button>
                <button className="btn danger plein" type="button" disabled={envoi || !motif.trim()} onClick={() => envoyer("refuser")}>
                  {envoi ? "Refus…" : "Refuser la demande"}
                </button>
              </div>
            </div>
          )}
          {!enAttente && (
            <>
              {d.requisition && (
                <button className="btn" type="button" onClick={() => setMode("voir")}><Icon name="doc" size={18} />Voir le bon de réquisition</button>
              )}
              <span className="sp" />
              <button className="btn" type="button" onClick={onFermer}>Fermer</button>
            </>
          )}
        </div>
      </aside>

      {/* Valider = signer au stylo électronique la case « Agent Logistique » du bon */}
      {mode === "valider" && (
        <FenetreBon d={d} role="agent" numero={numero ?? d.numero_requisition} signataire={signataire}
          quantites={Object.fromEntries(d.lignes.map((l, i) => [l.id, Number(valeurs[i])]))}
          titre={`Valider la demande ${d.numero}${modifiees ? ` (${modifiees} quantité${modifiees > 1 ? "s" : ""} modifiée${modifiees > 1 ? "s" : ""})` : ""}`}
          texteBouton="Signer et valider" envoi={envoi} erreur={erreurs.general || erreurs.signature}
          onSigner={(image) => envoyer("valider", image)} onFermer={() => { if (!envoi) { setMode(null); setErreurs({}); } }} />
      )}
      {mode === "voir" && d.requisition && (
        <FenetreBon d={d} titre={`Bon de réquisition ${d.requisition.numero}`} onFermer={() => setMode(null)} />
      )}
    </>
  );
}
