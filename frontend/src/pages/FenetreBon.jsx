import { useEffect, useState } from "react";
import Icon from "../icons.jsx";
import BonRequisition, { visasDe } from "./BonRequisition.jsx";
import StyloSignature from "./StyloSignature.jsx";

/** Fenêtre « bon de réquisition » : aperçu du bon, et, si `role` est donné, le cadre de signature au stylo électronique.
 *  role : "agent" | "responsable" | undefined (simple lecture)
 *  signataire : nom imprimé (celui du compte connecté) ; onSigner(image) ; piedGauche : boutons en plus (ex. Refuser…). */
export default function FenetreBon({ d, role, signataire, quantites, titre, texteBouton = "Signer", onSigner, onFermer,
  envoi = false, erreur, succes, piedGauche, remplacerPied }) {
  const [image, setImage] = useState(null);
  const [maintenant, setMaintenant] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setMaintenant(new Date()), 30_000); return () => clearInterval(t); }, []);
  useEffect(() => {
    const touche = (e) => e.key === "Escape" && !envoi && onFermer();
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi]);

  const visas = { ...visasDe(d) };
  if (role && !succes) visas[role] = { nom: signataire, le: null, image };
  const libelleRole = role === "agent" ? "Agent Logistique" : "Responsable HBC";

  return (
    <>
      <div className="voile au-dessus" onClick={() => !envoi && onFermer()} />
      <div className="fenetre fenetre-bon" role="dialog" aria-modal="true" aria-label={titre}>
        <div className="fenetre-tete">
          <h2>{titre}</h2>
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
              Relisez le bon de réquisition, puis <b>signez dans le cadre en bas de la fenêtre</b> (faites défiler vers le bas),
              et cliquez sur <b>« {texteBouton} »</b>.
            </div>
          )}
          <BonRequisition d={d} quantites={quantites} visas={visas} aSigner={role && !succes ? role : undefined} dateBon={maintenant.toISOString()} />
          {role && !succes && (
            <section className="signer">
              <h3>Votre signature <span className="facultatif">(case « {libelleRole} » du bon)</span></h3>
              <p className="signataire">
                Signataire : <b>{signataire}</b>, {libelleRole} · {maintenant.toLocaleDateString("fr-FR")} à {maintenant.getHours()} h {String(maintenant.getMinutes()).padStart(2, "0")}
              </p>
              <StyloSignature onChange={setImage} desactive={envoi} />
            </section>
          )}
        </div>
        <div className="fiche-pied">
          {remplacerPied ?? (
            <>
              {!succes && piedGauche}
              <span className="sp" />
              {role && !succes ? (
                <>
                  <button className="btn" type="button" onClick={onFermer} disabled={envoi}>Annuler</button>
                  <button className="btn pri" type="button" disabled={envoi || !image} onClick={() => onSigner(image)}
                    title={image ? undefined : "Signez d'abord dans le cadre"}>
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
