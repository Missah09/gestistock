import { useCallback, useState } from "react";
import { listerRetours, lireRetour } from "../api.js";
import { date, jourDe, joursDeRetard, quantite } from "../format.js";
import Icon from "../icons.jsx";
import FenetreRetour from "./FenetreRetour.jsx";
import { Onglets, useDemandeOuverte, useListeDemandes } from "./TableauDemandes.jsx";

const ONGLETS_RETOURS = [["attendu", "Matériel attendu"], ["en_retard", "En retard"], ["soldes", "Rentrés"], ["toutes", "Tous"]];

/** Écran « Retours de stock » (Responsable Technique, 12/10/2026) : le matériel prêté revient au magasin.
 *  On imprime un bon de retour avec ce qui reste à rendre, le magasinier le remplit (Qté rendue, État au retour),
 *  puis on confirme le retour en recopiant le bon : le stock remonte. Retour partiel : un bon par passage. */
export default function Retours() {
  const liste = useListeDemandes(listerRetours, "attendu");
  const [ouverte, setOuverte] = useDemandeOuverte(liste, lireRetour);
  const [annonce, setAnnonce] = useState(null);
  const fermer = useCallback(() => setOuverte(null), [setOuverte]);

  const { donnees, chargement, page, setPage, majLe } = liste;
  const total = donnees?.count ?? 0;
  const parPage = donnees?.par_page ?? 10;
  const derniere = Math.max(1, Math.ceil(total / parPage));
  const debut = total === 0 ? 0 : (page - 1) * parPage + 1;

  return (
    <>
      <header className="top"><h1>Retours de stock</h1></header>
      <div className="body">
        {liste.erreur && <div className="alerte">{liste.erreur}</div>}
        <div className="barre">
          <Onglets liste={liste} onglets={ONGLETS_RETOURS} />
          <span className="sp" />
          <span className="aide">Matériel prêté sorti du magasin. Imprimez un bon de retour, puis confirmez le retour : le stock remonte.</span>
        </div>

        {annonce && (
          <div className="succes annonce">
            <span>{annonce}</span>
            <button type="button" className="btn-icone" onClick={() => setAnnonce(null)} aria-label="Masquer le message"><Icon name="x" size={16} stroke={2.2} /></button>
          </div>
        )}

        <div className="card">
          <table className="tableau demandes requisitions retours">
            <thead>
              <tr>
                <th style={{ width: 160 }}>Réquisition</th>
                <th style={{ width: 190 }}>Demandeur</th>
                <th>Matériel à rendre</th>
                <th style={{ width: 150 }}>Retour prévu</th>
                <th style={{ width: 170 }}>Bon de retour</th>
                <th style={{ width: 210 }} />
              </tr>
            </thead>
            {donnees?.results.map((d) => {
              const r = d.requisition;
              const ret = d.retour;
              const ouvert = ret.bon_ouvert;
              const aRendre = ret.lignes.filter((l) => l.reste > 0);
              const montrees = (aRendre.length ? aRendre : ret.lignes);
              const retard = ret.en_retard ? joursDeRetard(ret.prochaine_date) : 0;
              return (
                <tbody key={d.id} className={`groupe cliquable${ouverte?.id === d.id ? " choisie" : ""}${ret.en_retard ? " en-retard" : ""}`}
                  onClick={() => setOuverte(d)}>
                  <tr>
                    <td className="cellule-demande">
                      <span className="code">{r.numero}</span>
                      <small>{d.numero}</small>
                    </td>
                    <td className="cellule-demande">
                      <span className="demandeur">{d.demandeur || "—"}</span>
                      <small>{d.demandeur_departement || "—"}{d.destination ? ` · ${d.destination}` : ""}</small>
                    </td>
                    <td className="cellule-demande articles-bon">
                      {montrees.slice(0, 3).map((l) => (
                        <span key={l.ligne_sortie} className="article-bon">
                          {ret.solde ? <b>{quantite(l.qte_sortie, l.article.unite)}</b>
                            : <><b>{quantite(l.reste, l.article.unite)}</b>{l.reste !== l.qte_sortie && <small className="sur"> sur {quantite(l.qte_sortie, l.article.unite)}</small>}</>}
                          {" "}{l.article.nom}
                          {l.etats_sortie_texte && <small className="sur"> · sorti {l.etats_sortie_texte.toLowerCase()}</small>}
                        </span>
                      ))}
                      {montrees.length > 3 && <small>et {montrees.length - 3} autre{montrees.length > 4 ? "s" : ""} article{montrees.length > 4 ? "s" : ""}</small>}
                    </td>
                    <td className="cellule-demande">
                      {ret.solde ? <span className="pill p-ok">Tout est rentré</span> : (
                        <>
                          <span className={`demandeur${ret.en_retard ? " rouge" : ""}`}>{date(ret.prochaine_date)}</span>
                          {ret.en_retard
                            ? <small className="rouge">En retard de {retard} jour{retard > 1 ? "s" : ""}</small>
                            : <small>sorti le {date(ret.date_remise)}</small>}
                        </>
                      )}
                    </td>
                    <td className="cellule-demande">
                      {ouvert ? (
                        <><span className="pill p-w">{ouvert.numero}</span><small className="trace">à confirmer · imprimé le {jourDe(ouvert.imprime_le)}</small></>
                      ) : ret.bons.length ? (
                        <small className="trace">{ret.bons.length} retour{ret.bons.length > 1 ? "s" : ""} confirmé{ret.bons.length > 1 ? "s" : ""}<br />{ret.bons.map((b) => b.numero).join(", ")}</small>
                      ) : <span className="discret">—</span>}
                    </td>
                    <td className="cellule-demande actions-bon">
                      {ouvert ? (
                        <button type="button" className="btn pri" onClick={(e) => { e.stopPropagation(); setOuverte(d); }}>
                          <Icon name="back" size={17} stroke={2} />Confirmer le retour
                        </button>
                      ) : !ret.solde ? (
                        <button type="button" className="btn" onClick={(e) => { e.stopPropagation(); setOuverte(d); }}>
                          <Icon name="doc" size={16} stroke={2} />Préparer le bon de retour
                        </button>
                      ) : (
                        <button type="button" className="btn-details" onClick={(e) => { e.stopPropagation(); setOuverte(d); }}>
                          <Icon name="doc" size={15} stroke={2} />Voir les retours
                        </button>
                      )}
                    </td>
                  </tr>
                </tbody>
              );
            })}
            {!chargement && donnees?.results.length === 0 && (
              <tbody><tr><td colSpan={6} className="vide">
                {liste.onglet === "attendu" ? "Aucun matériel prêté n'est attendu. Il apparaît ici dès que sa sortie est confirmée (écran « Sorties de stock »)."
                  : liste.onglet === "en_retard" ? "Aucun retard : tout le matériel attendu est dans les temps."
                    : "Aucun retour."}
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
        <FenetreRetour d={ouverte} onFermer={fermer}
          onChange={(message, demande) => { if (message) setAnnonce(message); if (demande) setOuverte(demande); liste.recharger(); }} />
      )}
    </>
  );
}
