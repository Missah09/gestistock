import { useCallback, useState } from "react";
import { lireDemande, listerDemandes } from "../api.js";
import Icon from "../icons.jsx";
import DetailDemande from "./DetailDemande.jsx";
import NouvelleDemande from "./NouvelleDemande.jsx";
import { Onglets, TableauDemandes, useDemandeOuverte, useListeDemandes } from "./TableauDemandes.jsx";

/** Écran « Mes demandes » (vue du demandeur) : une ligne par article demandé, regroupées par demande. */
export default function Demandes() {
  const liste = useListeDemandes(listerDemandes);
  const [affichee, setOuverte] = useDemandeOuverte(liste, lireDemande);
  const [nouvelle, setNouvelle] = useState(false);
  const [annonce, setAnnonce] = useState(null);
  const fermer = useCallback(() => setOuverte(null), [setOuverte]);

  return (
    <>
      <header className="top"><h1>Mes demandes</h1></header>
      <div className="body">
        {liste.erreur && <div className="alerte">{liste.erreur}</div>}

        <div className="barre">
          <Onglets liste={liste} />
          <span className="sp" />
          <button className="btn pri" type="button" onClick={() => { setAnnonce(null); setNouvelle(true); }}>
            <Icon name="plus" size={18} stroke={2.4} />Nouvelle demande
          </button>
        </div>

        {annonce && (
          <div className="succes annonce">
            <span>{annonce}</span>
            <button type="button" className="btn-icone" onClick={() => setAnnonce(null)} aria-label="Masquer le message"><Icon name="x" size={16} stroke={2.2} /></button>
          </div>
        )}

        <TableauDemandes liste={liste} ouverte={affichee} onOuvrir={setOuverte}
          messageVide={liste.onglet === "attente" ? "Aucune demande en attente. Cliquez sur « Nouvelle demande » pour demander du matériel." : "Aucune demande."} />
      </div>

      {nouvelle && (
        <NouvelleDemande
          onFermer={() => setNouvelle(false)}
          onEnvoyee={(message) => { setNouvelle(false); setAnnonce(message); liste.setOnglet("attente"); liste.recharger(); }}
        />
      )}
      {affichee && (
        <DetailDemande demande={affichee} onFermer={fermer}
          onAnnulee={(message) => { setOuverte(null); setAnnonce(message); liste.recharger(); }} />
      )}
    </>
  );
}
