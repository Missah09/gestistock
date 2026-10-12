import { useCallback, useState } from "react";
import { lireRequisition, listerRequisitions, signalerChangement, telechargerBon } from "../api.js";
import { dateHeure, jourDe, quantite } from "../format.js";
import Icon from "../icons.jsx";
import FenetreBon from "./FenetreBon.jsx";
import { Onglets, useDemandeOuverte, useListeDemandes } from "./TableauDemandes.jsx";

const ONGLETS_BONS = [["a_imprimer", "À imprimer"], ["imprimees", "Imprimées"], ["toutes", "Toutes"]];

/** Lignes qui figurent sur le bon : quantité accordée (sinon demandée), sans les articles retirés (0). */
const lignesDuBon = (d) => d.lignes.map((l) => ({ ...l, qte: l.qte_accordee ?? l.quantite })).filter((l) => l.qte > 0);

/** Trace d'impression : premier téléchargement par l'Agent Logistique, et nombre total de téléchargements. */
function Impression({ r }) {
  const n = r.nb_telechargements ?? 0;
  return (
    <>
      {r.imprimee_le ? (
        <>
          <span className="pill p-ok">Imprimée</span>
          <small className="trace">le {dateHeure(r.imprimee_le)}<br />{" "}par {r.imprimee_par}</small>
        </>
      ) : <span className="pill p-w">À imprimer</span>}
      {n > 0 && <small className="trace discret">{n} téléchargement{n > 1 ? "s" : ""}</small>}
    </>
  );
}

/** Écran « Réquisitions » (Agent Logistique et Responsable HBC, 12/10/2026) :
 *  les bons signés par la Logistique et le Responsable, à télécharger en PDF pour impression.
 *  Le premier téléchargement par l'Agent Logistique marque le bon « imprimé » (c'est lui qui le porte au magasin). */
export default function Requisitions({ compte }) {
  const liste = useListeDemandes(listerRequisitions, "a_imprimer");
  const [ouverte, setOuverte] = useDemandeOuverte(liste, lireRequisition);
  const [enCours, setEnCours] = useState(null);   // id de la demande dont le PDF se télécharge
  const [annonce, setAnnonce] = useState(null);
  const [erreur, setErreur] = useState(null);
  const fermer = useCallback(() => setOuverte(null), [setOuverte]);
  const agent = compte?.agent_logistique;

  async function telecharger(d) {
    setEnCours(d.id); setErreur(null); setAnnonce(null);
    try {
      await telechargerBon(d.id, d.requisition.numero);
      const premiere = agent && !d.requisition.imprimee_le;
      setAnnonce(premiere
        ? `Bon ${d.requisition.numero} téléchargé : il est maintenant noté « Imprimée ». Imprimez-le et portez-le au magasin.`
        : `Bon ${d.requisition.numero} téléchargé.`);
      liste.recharger(); signalerChangement();
    } catch (e) {
      setErreur(e.message || "Le téléchargement a échoué. Vérifiez que le serveur est démarré.");
    } finally {
      setEnCours(null);
    }
  }

  const { donnees, chargement, page, setPage, majLe } = liste;
  const total = donnees?.count ?? 0;
  const parPage = donnees?.par_page ?? 10;
  const derniere = Math.max(1, Math.ceil(total / parPage));
  const debut = total === 0 ? 0 : (page - 1) * parPage + 1;

  const boutonPdf = (d, classe = "btn pri") => (
    <button type="button" className={classe} disabled={enCours === d.id} onClick={(e) => { e.stopPropagation(); telecharger(d); }}>
      <Icon name="download" size={17} stroke={2.2} />{enCours === d.id ? "Téléchargement…" : "Télécharger le PDF"}
    </button>
  );

  return (
    <>
      <header className="top"><h1>Réquisitions</h1></header>
      <div className="body">
        {(liste.erreur || erreur) && <div className="alerte">{liste.erreur || erreur}</div>}
        <div className="barre">
          <Onglets liste={liste} onglets={ONGLETS_BONS} />
          <span className="sp" />
          <span className="aide">
            {agent ? "Bons signés par la Logistique et le Responsable : téléchargez le PDF, imprimez-le et portez-le au magasin."
              : "Bons signés par la Logistique et par vous. Le bon est noté « Imprimée » quand l'Agent Logistique le télécharge."}
          </span>
        </div>

        {annonce && (
          <div className="succes annonce">
            <span>{annonce}</span>
            <button type="button" className="btn-icone" onClick={() => setAnnonce(null)} aria-label="Masquer le message"><Icon name="x" size={16} stroke={2.2} /></button>
          </div>
        )}

        <div className="card">
          <table className="tableau demandes requisitions">
            <thead>
              <tr>
                <th style={{ width: 170 }}>Réquisition</th>
                <th style={{ width: 190 }}>Demandeur</th>
                <th>Articles</th>
                <th style={{ width: 175 }}>Signée</th>
                <th style={{ width: 190 }}>Impression</th>
                <th style={{ width: 200 }} />
              </tr>
            </thead>
            {donnees?.results.map((d) => {
              const r = d.requisition;
              const lignes = lignesDuBon(d);
              return (
                <tbody key={d.id} className={`groupe cliquable${ouverte?.id === d.id ? " choisie" : ""}`} onClick={() => setOuverte(d)}>
                  <tr>
                    <td className="cellule-demande">
                      <span className="code">{r.numero}</span>
                      <small>{d.numero}</small>
                      {d.urgent && <span className="pill p-c petite-pill">Urgent</span>}
                    </td>
                    <td className="cellule-demande">
                      <span className="demandeur">{d.demandeur || "—"}</span>
                      <small>{d.demandeur_departement || "—"}{d.destination ? ` · ${d.destination}` : ""}</small>
                    </td>
                    <td className="cellule-demande articles-bon">
                      {lignes.slice(0, 3).map((l) => (
                        <span key={l.id} className="article-bon"><b>{quantite(l.qte, l.article.unite)}</b> {l.article.nom}</span>
                      ))}
                      {lignes.length > 3 && <small>et {lignes.length - 3} autre{lignes.length > 4 ? "s" : ""} article{lignes.length > 4 ? "s" : ""}</small>}
                    </td>
                    <td className="cellule-demande">
                      <span className="demandeur">{jourDe(r.visa_responsable_le)}</span>
                      <small>par {r.visa_responsable}</small>
                    </td>
                    <td className="cellule-demande"><Impression r={r} /></td>
                    <td className="cellule-demande actions-bon">
                      {boutonPdf(d)}
                      <button type="button" className="btn-details" onClick={(e) => { e.stopPropagation(); setOuverte(d); }}>
                        <Icon name="doc" size={15} stroke={2} />Voir le bon
                      </button>
                    </td>
                  </tr>
                </tbody>
              );
            })}
            {!chargement && donnees?.results.length === 0 && (
              <tbody><tr><td colSpan={6} className="vide">
                {liste.onglet === "a_imprimer" ? "Aucun bon à imprimer pour le moment." : "Aucune réquisition signée."}
              </td></tr></tbody>
            )}
          </table>
          <div className="pied">
            <span>
              {chargement ? "Chargement…" : `${debut} à ${Math.min(page * parPage, total)} sur ${total} réquisition${total > 1 ? "s" : ""}`}
              {majLe && !chargement && <span className="maj"> · Mis à jour à {majLe.getHours()} h {String(majLe.getMinutes()).padStart(2, "0")}</span>}
            </span>
            <div className="pages">
              <button className="btn" type="button" disabled={page <= 1 || chargement} onClick={() => setPage(page - 1)}>← Page précédente</button>
              <button className="btn" type="button" disabled={page >= derniere || chargement} onClick={() => setPage(page + 1)}>Page suivante →</button>
            </div>
          </div>
        </div>
      </div>

      {ouverte && (
        <FenetreBon d={ouverte} titre={`Bon de réquisition ${ouverte.requisition.numero}`} onFermer={fermer}
          piedGauche={<><span className="trace-pied"><Impression r={ouverte.requisition} /></span>{boutonPdf(ouverte)}</>} />
      )}
    </>
  );
}
