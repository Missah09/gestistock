import { useEffect, useState } from "react";
import { refuserRequisition, viserRequisition } from "../api.js";
import FenetreBon from "./FenetreBon.jsx";
import { statutAffiche } from "./TableauDemandes.jsx";

const MOTIF_MAX = 250;

/** Responsable HBC : la réquisition s'ouvre dans une fenêtre, sous forme de bon de réquisition.
 *  Il signe sa case au stylo électronique (souris), ou refuse avec un motif. */
export default function ViserDemande({ demande: d, signataire, onFermer, onTraitee }) {
  const r = d.requisition;
  const aViser = r?.statut === "ATTENTE_VISA";
  const [refus, setRefus] = useState(false);
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreurs, setErreurs] = useState({});
  const [succes, setSucces] = useState(null);

  useEffect(() => { setRefus(false); setMotif(""); setErreurs({}); setSucces(null); }, [d.id]);

  async function envoyer(action, corps) {
    setEnvoi(true); setErreurs({});
    try {
      const rep = action === "viser" ? await viserRequisition(d.id, corps) : await refuserRequisition(d.id, motif.trim());
      setSucces(action === "viser"
        ? { titre: "Réquisition signée", texte: rep.message }
        : { refus: true, titre: "Réquisition refusée", texte: rep.message });
      setRefus(false);
      onTraitee(rep.message, rep.demande);
    } catch (err) {
      const det = err.details;
      setErreurs(det ? { general: det.general?.[0], signature: det.signature?.[0] ?? det.mot_de_passe?.[0], motif: det.motif?.[0] }
        : { general: "L'envoi a échoué. Vérifiez que le serveur est démarré." });
    } finally {
      setEnvoi(false);
    }
  }

  const statut = statutAffiche(d);
  const titre = aViser && !succes ? `Réquisition ${r.numero} à signer` : `Réquisition ${r?.numero} · ${statut.libelle}`;

  const piedRefus = (
    <div className="refus-saisie">
      <label htmlFor="motif-refus-visa" className="question">Motif du refus <span className="facultatif">(obligatoire, montré à la Logistique et au demandeur)</span></label>
      <textarea id="motif-refus-visa" className={`saisie zone${erreurs.motif ? " invalide" : ""}`} rows={2} maxLength={MOTIF_MAX} autoFocus
        value={motif} disabled={envoi} onChange={(e) => { setMotif(e.target.value); setErreurs((x) => ({ ...x, motif: undefined })); }}
        placeholder="Ex. : budget du mois dépassé" />
      <div className="refus-boutons">
        {erreurs.motif ? <em className="msg-erreur">{erreurs.motif}</em> : <small className="aide">{motif.length} / {MOTIF_MAX}</small>}
        <span className="sp" />
        <button className="btn" type="button" disabled={envoi} onClick={() => setRefus(false)}>Non, revenir</button>
        <button className="btn danger plein" type="button" disabled={envoi || !motif.trim()} onClick={() => envoyer("refuser")}>
          {envoi ? "Refus…" : "Refuser la réquisition"}
        </button>
      </div>
    </div>
  );

  return (
    <FenetreBon d={d} role={aViser ? "responsable" : undefined} signataire={signataire} titre={titre}
      texteBouton="Signer" envoi={envoi} erreur={erreurs.general} erreurSignature={erreurs.signature} succes={succes}
      onSigner={(corps) => envoyer("viser", corps)} onFermer={onFermer}
      piedGauche={aViser ? <button className="btn danger" type="button" onClick={() => { setErreurs({}); setRefus(true); }}>Refuser…</button> : null}
      remplacerPied={refus && !succes ? <div className="pied-refus">{piedRefus}</div> : undefined} />
  );
}
