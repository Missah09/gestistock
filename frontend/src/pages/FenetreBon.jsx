import { useEffect, useState } from "react";
import Icon from "../icons.jsx";
import BonRequisition, { visasDe } from "./BonRequisition.jsx";
import ZoneSignature from "./ZoneSignature.jsx";

/** Fenêtre « bon de réquisition » : aperçu du bon, et, si `role` est donné, le cadre de signature au stylo électronique.
 *  role : "agent" | "responsable" | undefined (simple lecture)
 *  signataire : nom imprimé (celui du compte connecté) ; onSigner(corps) : corps de ZoneSignature (signature + mot de passe) ;
 *  erreurSignature : erreur du serveur sur la signature ou le mot de passe ; piedGauche : boutons en plus (ex. Refuser…). */
export default function FenetreBon({ d, role, signataire, quantites, numero, titre, enTete, texteBouton = "Signer", onSigner, onFermer,
  envoi = false, erreur, erreurSignature, succes, piedGauche, remplacerPied }) {
  const [sig, setSig] = useState({ image: null, pret: false, corps: null });
  const image = sig.image;
  const [maintenant, setMaintenant] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setMaintenant(new Date()), 30_000); return () => clearInterval(t); }, []);
  useEffect(() => {
    const touche = (e) => e.key === "Escape" && !envoi && onFermer();
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi]);

  const visas = { ...visasDe(d) };
  if (role && !succes) visas[role] = { nom: signataire, le: null, image };
  const libelleRole = role === "agent" ? "Responsable Technique" : "Responsable Logistique";

  return (
    <>
      <div className="voile au-dessus" onClick={() => !envoi && onFermer()} />
      <div className="fenetre fenetre-bon" role="dialog" aria-modal="true" aria-label={titre}>
        <div className="fenetre-tete">
          <h2>{titre}</h2>
          {enTete && <span className="trace-pied tete-bon">{enTete}</span>}
          <span className="sp" />
          <button className="fermer" type="button" onClick={onFermer} disabled={envoi} aria-label="Fermer"><Icon name="x" size={22} stroke={2.2} /></button>
        </div>
        <div className="fenetre-corps">
          {succes && (
            <div className={`bandeau-fait${succes.refus ? " refus" : ""}`} role="status">
              <span className="rond-fait">{succes.refus ? "✕" : "✓"}</span>
              <div><b>{succes.titre}</b><span>{succes.texte}</span></div>
            </div>
          )}
          {erreur && <div className="alerte">{erreur}</div>}
          {role && !succes && (
            <div className="consigne">
              Relisez le bon de réquisition, puis <b>signez en bas de la fenêtre</b> (faites défiler vers le bas) : signature enregistrée,
              signature scannée ou dessinée à la souris. Retapez votre mot de passe et cliquez sur <b>« {texteBouton} »</b>.
            </div>
          )}
          <BonRequisition d={d} quantites={quantites} numero={numero} visas={visas} aSigner={role && !succes ? role : undefined} dateBon={maintenant.toISOString()} />
          {role && !succes && (
            <section className="signer">
              <h3>Votre signature <span className="facultatif">(case « {libelleRole} » du bon)</span></h3>
              <p className="signataire">
                Signataire : <b>{signataire}</b>, {libelleRole} · {maintenant.toLocaleDateString("fr-FR")} à {maintenant.getHours()} h {String(maintenant.getMinutes()).padStart(2, "0")}
              </p>
              <ZoneSignature onChange={setSig} desactive={envoi} erreur={erreurSignature} />
            </section>
          )}
        </div>
        <div className="fiche-pied">
          {remplacerPied ?? (
            <>
              {(!succes || !role) && piedGauche}
              <span className="sp" />
              {role && !succes ? (
                <>
                  <button className="btn" type="button" onClick={onFermer} disabled={envoi}>Annuler</button>
                  <button className="btn pri" type="button" disabled={envoi || !sig.pret} onClick={() => onSigner(sig.corps)}
                    title={sig.pret ? undefined : image ? "Retapez votre mot de passe" : "Signez d'abord (en bas de la fenêtre)"}>
                    <Icon name="sign" size={18} stroke={2} />{envoi ? "Enregistrement…" : texteBouton}
                  </button>
                </>
              ) : (
                <button className="btn" type="button" onClick={onFermer}>Fermer</button>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
