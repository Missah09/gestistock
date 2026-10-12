import { useCallback, useState } from "react";
import { listerSorties, lireSortie } from "../api.js";
import { date, dateHeure, quantite } from "../format.js";
import Icon from "../icons.jsx";
import ConfirmerSortie, { lignesDuBon } from "./ConfirmerSortie.jsx";
import { Onglets, useDemandeOuverte, useListeDemandes } from "./TableauDemandes.jsx";

const ONGLETS_SORTIES = [["a_confirmer", "À confirmer"], ["confirmees", "Confirmées"], ["toutes", "Toutes"]];

/** Écran « Sorties » (Agent Logistique, 12/10/2026) : les bons imprimés et portés au magasin.
 *  Au retour du bon signé par le magasinier, on confirme la sortie en recopiant les quantités livrées :
 *  c'est à ce moment que le stock de GestiStock diminue. */
export default function Sorties() {
  const liste = useListeDemandes(listerSorties, "a_confirmer");
  const [ouverte, setOuverte] = useDemandeOuverte(liste, lireSortie);
  const [annonce, setAnnonce] = useState(null);
  const fermer = useCallback(() => setOuverte(null), [setOuverte]);

  const { donnees, chargement, page, setPage, majLe } = liste;
  const total = donnees?.count ?? 0;
  const parPage = donnees?.par_page ?? 10;
  const derniere = Math.max(1, Math.ceil(total / parPage));
  const debut = total === 0 ? 0 : (page - 1) * parPage + 1;

  return (
    <>
      <header className="top"><h1>Sorties</h1></header>
      <div className="body">
        {liste.erreur && <div className="alerte">{liste.erreur}</div>}
        <div className="barre">
          <Onglets liste={liste} onglets={ONGLETS_SORTIES} />
          <span className="sp" />
          <span className="aide">Bons imprimés et portés au magasin. Quand le bon signé revient, confirmez la sortie : le stock diminue.</span>
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
                <th style={{ width: 200 }}>Demandeur</th>
                <th>Articles du bon</th>
                <th style={{ width: 170 }}>Bon imprimé</th>
                <th style={{ width: 190 }}>Sortie</th>
                <th style={{ width: 200 }} />
              </tr>
            </thead>
            {donnees?.results.map((d) => {
              const r = d.requisition;
              const s = r.sortie;
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
                        <span key={l.id} className="article-bon">
                          {s ? <><b>{quantite(s.lignes[l.id]?.qte_livree ?? 0, l.article.unite)}</b> <small className="sur">sur {quantite(l.qte, l.article.unite)}</small></>
                            : <b>{quantite(l.qte, l.article.unite)}</b>} {l.article.nom}
                        </span>
                      ))}
                      {lignes.length > 3 && <small>et {lignes.length - 3} autre{lignes.length > 4 ? "s" : ""} article{lignes.length > 4 ? "s" : ""}</small>}
                    </td>
                    <td className="cellule-demande">
                      <span className="demandeur">{dateHeure(r.imprimee_le).split(" à ")[0]}</span>
                      <small>par {r.imprimee_par}</small>
                    </td>
                    <td className="cellule-demande">
                      {s ? (
                        <>
                          <span className="pill p-ok">Matériel remis</span>
                          <small className="trace">le {date(s.date_remise)}<br />confirmée par {s.confirmee_par}</small>
                        </>
                      ) : <span className="pill p-w">À confirmer</span>}
                    </td>
                    <td className="cellule-demande actions-bon">
                      {s ? (
                        <button type="button" className="btn-details" onClick={(e) => { e.stopPropagation(); setOuverte(d); }}>
                          <Icon name="doc" size={15} stroke={2} />Voir la sortie
                        </button>
                      ) : (
                        <button type="button" className="btn pri" onClick={(e) => { e.stopPropagation(); setOuverte(d); }}>
                          <Icon name="out" size={17} stroke={2} />Confirmer la sortie
                        </button>
                      )}
                    </td>
                  </tr>
                </tbody>
              );
            })}
            {!chargement && donnees?.results.length === 0 && (
              <tbody><tr><td colSpan={6} className="vide">
                {liste.onglet === "a_confirmer"
                  ? "Aucune sortie à confirmer. Les bons apparaissent ici dès qu'ils sont imprimés (écran « Réquisitions »)."
                  : "Aucune sortie confirmée."}
              </td></tr></tbody>
            )}
          </table>
          <div className="pied">
            <span>
              {chargement ? "Chargement…" : `${debut} à ${Math.min(page * parPage, total)} sur ${total} bon${total > 1 ? "s" : ""}`}
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
        <ConfirmerSortie d={ouverte} onFermer={fermer}
          onConfirmee={(message, demande) => { setAnnonce(message); setOuverte(demande); liste.recharger(); }} />
      )}
    </>
  );
}
