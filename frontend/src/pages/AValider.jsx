import { useCallback, useState } from "react";
import { lireAValider, listerAValider, signalerChangement } from "../api.js";
import Icon from "../icons.jsx";
import ValiderDemande from "./ValiderDemande.jsx";
import { Onglets, TableauDemandes, useDemandeOuverte, useListeDemandes } from "./TableauDemandes.jsx";

/** Écran « Demandes à valider » (Agent Logistique) : toutes les demandes ; en attente, les urgentes puis les plus anciennes. */
export default function AValider({ compte }) {
  const liste = useListeDemandes(listerAValider);
  const [affichee, setOuverte] = useDemandeOuverte(liste, lireAValider);
  const [annonce, setAnnonce] = useState(null);
  const [avertissement, setAvertissement] = useState(null); // ex. email au Responsable non envoyé
  const fermer = useCallback(() => setOuverte(null), [setOuverte]);

  return (
    <>
      <header className="top"><h1>Demandes à valider</h1></header>
      <div className="body">
        {liste.erreur && <div className="alerte">{liste.erreur}</div>}
        <div className="barre">
          <Onglets liste={liste} />
          <span className="sp" />
          {liste.onglet === "attente" && <span className="aide">Cliquez sur une demande pour la vérifier, puis la valider ou la refuser.</span>}
        </div>

        {avertissement && (
          <div className="avertissement annonce">
            <span>{avertissement}</span>
            <button type="button" className="btn-icone" onClick={() => setAvertissement(null)} aria-label="Masquer le message"><Icon name="x" size={16} stroke={2.2} /></button>
          </div>
        )}
        {annonce && (
          <div className="succes annonce">
            <span>{annonce}</span>
            <button type="button" className="btn-icone" onClick={() => setAnnonce(null)} aria-label="Masquer le message"><Icon name="x" size={16} stroke={2.2} /></button>
          </div>
        )}

        <TableauDemandes liste={liste} ouverte={affichee} onOuvrir={(d) => { setAnnonce(null); setAvertissement(null); setOuverte(d); }} vueAgent
          messageVide={liste.onglet === "attente" ? "Aucune demande en attente : tout est traité." : "Aucune demande."} />
      </div>

      {affichee && (
        <ValiderDemande demande={affichee} onFermer={fermer} emails={Boolean(compte?.emails)} signataire={compte?.nom ?? ""}
          onMiseAJour={(d) => { setOuverte(d); liste.recharger(); }}
          onTraitee={(message, alerte, demande) => { setOuverte(demande); setAnnonce(message); setAvertissement(alerte); liste.recharger(); signalerChangement(); }} />
      )}
    </>
  );
}
