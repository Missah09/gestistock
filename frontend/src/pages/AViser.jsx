import { useCallback, useEffect, useState } from "react";
import { lireAViser, listerAViser, signalerChangement } from "../api.js";
import Icon from "../icons.jsx";
import ViserDemande from "./ViserDemande.jsx";
import { Onglets, TableauDemandes, useDemandeOuverte, useListeDemandes } from "./TableauDemandes.jsx";

const ONGLETS_VISA = [["attente", "À viser"], ["visees", "Visées"], ["refusees", "Refusées"], ["toutes", "Toutes"]];

/** Écran « À viser » (Responsable HBC). `ouvrirId` : demande à ouvrir tout de suite (lien de l'email). */
export default function AViser({ ouvrirId, compte }) {
  const liste = useListeDemandes(listerAViser);
  const [affichee, setOuverte] = useDemandeOuverte(liste, lireAViser);
  const [annonce, setAnnonce] = useState(null);
  const [erreurLien, setErreurLien] = useState(null);
  const fermer = useCallback(() => setOuverte(null), [setOuverte]);

  // Arrivée par le lien de l'email : la réquisition s'ouvre directement.
  useEffect(() => {
    if (!ouvrirId) return;
    lireAViser(ouvrirId).then(setOuverte).catch(() => setErreurLien("La réquisition du lien est introuvable."));
  }, [ouvrirId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <header className="top"><h1>À viser</h1></header>
      <div className="body">
        {(liste.erreur || erreurLien) && <div className="alerte">{liste.erreur || erreurLien}</div>}
        <div className="barre">
          <Onglets liste={liste} onglets={ONGLETS_VISA} />
          <span className="sp" />
          {liste.onglet === "attente" && <span className="aide">Cliquez sur une réquisition pour la relire, puis la viser ou la refuser.</span>}
        </div>

        {annonce && (
          <div className="succes annonce">
            <span>{annonce}</span>
            <button type="button" className="btn-icone" onClick={() => setAnnonce(null)} aria-label="Masquer le message"><Icon name="x" size={16} stroke={2.2} /></button>
          </div>
        )}

        <TableauDemandes liste={liste} ouverte={affichee} onOuvrir={(d) => { setAnnonce(null); setOuverte(d); }} vueAgent
          messageVide={liste.onglet === "attente" ? "Aucune réquisition à viser pour le moment." : "Aucune réquisition."} />
      </div>

      {affichee && (
        <ViserDemande demande={affichee} onFermer={fermer} signataire={compte?.nom ?? ""}
          onTraitee={(message, demande) => { setOuverte(demande); setAnnonce(message); liste.recharger(); signalerChangement(); }} />
      )}
    </>
  );
}
