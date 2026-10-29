import { useEffect, useRef, useState } from "react";
import { jourDe, manque, quantite, STATUTS_DEMANDE, LIBELLE_PRETE } from "../format.js";

// Mise à jour automatique : la liste et le panneau se rechargent seuls toutes les 30 secondes.
const INTERVALLE_MAJ = 30_000;

export const ONGLETS = [["attente", "En attente"], ["validees", "Validées"], ["refusees", "Refusées"], ["toutes", "Toutes"]];

/** Liste des demandes par onglet et par page, rechargée toutes les 30 s (écrans « Mes demandes » et « Demandes à valider »).
 *  `lister` : fonction de api.js qui lit une page. */
export function useListeDemandes(lister, ongletInitial = "attente") {
  const [onglet, setOnglet] = useState(ongletInitial);
  const [page, setPage] = useState(1);
  const [donnees, setDonnees] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [rafraichir, setRafraichir] = useState(0);
  const [majLe, setMajLe] = useState(null);    // heure de la dernière mise à jour réussie
  const discret = useRef(false);               // mise à jour automatique : sans afficher « Chargement… »

  // Changement d'onglet → première page, avant le chargement (une seule requête au lieu de deux).
  const [ongletVu, setOngletVu] = useState(onglet);
  if (ongletVu !== onglet) { setOngletVu(onglet); setPage(1); }

  useEffect(() => {
    let annule = false;
    if (!discret.current) setChargement(true);
    discret.current = false;
    lister({ onglet, page })
      .then((d) => { if (!annule) { setDonnees(d); setErreur(null); setMajLe(new Date()); } })
      .catch(() => !annule && setErreur("Impossible de joindre le serveur. Vérifiez que la fenêtre du backend (runserver) est ouverte."))
      .finally(() => !annule && setChargement(false));
    return () => { annule = true; };
  }, [lister, onglet, page, rafraichir]);

  // Toutes les 30 s (seulement si l'écran est visible), et dès qu'on revient sur l'onglet du navigateur.
  useEffect(() => {
    const recharger = () => { if (!document.hidden) { discret.current = true; setRafraichir((x) => x + 1); } };
    const minuteur = setInterval(recharger, INTERVALLE_MAJ);
    document.addEventListener("visibilitychange", recharger);
    return () => { clearInterval(minuteur); document.removeEventListener("visibilitychange", recharger); };
  }, []);

  const recharger = () => setRafraichir((x) => x + 1);
  return { onglet, setOnglet, page, setPage, donnees, erreur, chargement, majLe, recharger };
}

/** Le panneau suit la demande à jour : à chaque rechargement de la liste, il reprend sa nouvelle version ;
 *  si elle a quitté l'onglet (ex. visée), on la relit seule. Après une action, on lui donne directement
 *  la version renvoyée par le serveur (le panneau reste ouvert et montre le nouveau statut). */
export function useDemandeOuverte(liste, lire) {
  const [ouverte, setOuverte] = useState(null);
  useEffect(() => {
    if (!ouverte || !liste.donnees) return;
    const trouvee = liste.donnees.results.find((x) => x.id === ouverte.id);
    if (trouvee) { setOuverte(trouvee); return; }
    let annule = false;
    lire(ouverte.id).then((d) => !annule && setOuverte(d)).catch(() => {});
    return () => { annule = true; };
  }, [liste.donnees]); // eslint-disable-line react-hooks/exhaustive-deps
  return [ouverte, setOuverte];
}

export function Onglets({ liste, onglets = ONGLETS }) {
  return (
    <div className="onglets" role="tablist">
      {onglets.map(([cle, libelle]) => (
        <button key={cle} type="button" role="tab" aria-selected={liste.onglet === cle}
          className={`onglet${liste.onglet === cle ? " on" : ""}`} onClick={() => liste.setOnglet(cle)}>
          {libelle}<span className="compte">{liste.donnees?.compteurs?.[cle] ?? "·"}</span>
        </button>
      ))}
    </div>
  );
}

/** Statut affiché : après validation, l'étape de la réquisition (ex. « En attente du visa »). */
export function statutAffiche(d) {
  if (d.statut === "VALIDEE" && d.requisition?.statut === "ATTENTE_VISA") return { libelle: "Validée · attente du visa", classe: "p-ok" };
  if (d.statut === "VALIDEE" && d.requisition?.sortie) return { libelle: "Matériel remis", classe: "p-ok" };
  if (d.statut === "VALIDEE" && d.requisition?.statut === "VISEE") {
    return d.requisition.imprimee_le ? { libelle: "Bon imprimé", classe: "p-ok" } : { libelle: "Visée · bon à imprimer", classe: "p-ok" };
  }
  if (d.statut === "VALIDEE" && d.requisition?.statut === "REFUSEE") return { libelle: "Refusée (Resp. Logistique)", classe: "p-c" };
  return STATUTS_DEMANDE[d.statut];
}

/** Tableau des demandes : une ligne par article demandé, regroupées par demande.
 *  vueAgent : la 1re colonne montre le demandeur (au lieu de la seule date). */
export function TableauDemandes({ liste, ouverte, onOuvrir, vueAgent = false, messageVide }) {
  const { donnees, chargement, page, setPage, majLe } = liste;
  const total = donnees?.count ?? 0;
  const parPage = donnees?.par_page ?? 10;
  const derniere = Math.max(1, Math.ceil(total / parPage));
  const debut = total === 0 ? 0 : (page - 1) * parPage + 1;

  return (
    <div className="card">
      <table className="tableau demandes">
        <thead>
          <tr>
            <th style={{ width: vueAgent ? 210 : 190 }}>Demande</th>
            <th style={{ width: 110 }}>Code article</th>
            <th>Nom de l'Article</th>
            <th>Qté demandée</th>
            <th>Qté disponible</th>
            <th>Statut</th>
          </tr>
        </thead>
        {donnees?.results.map((d) => {
          const statut = statutAffiche(d);
          const n = d.lignes.length;
          return (
            <tbody key={d.id} className={`groupe cliquable${ouverte?.id === d.id ? " choisie" : ""}`} onClick={() => onOuvrir(d)}>
              {d.lignes.map((l, i) => {
                const a = l.article;
                const insuffisant = manque(l.quantite, a.qte_disponible);
                const modifiee = l.qte_accordee !== null && l.qte_accordee !== l.quantite;
                return (
                  <tr key={l.id}>
                    {i === 0 && (
                      <td rowSpan={n} className="cellule-demande">
                        <span className="code">{d.numero}</span>
                        {vueAgent && <span className="demandeur">{d.demandeur || "—"}</span>}
                        <small>{jourDe(d.cree_le)}{vueAgent && d.demandeur_departement ? ` · ${d.demandeur_departement}` : ""}</small>
                        {d.urgent && <span className="pill p-c petite-pill">Urgent</span>}
                      </td>
                    )}
                    <td><span className="code">{a.code}</span></td>
                    <td className="nom">{a.nom}{a.type === "PRETE" && <span className="pill p-i petite-pill">{LIBELLE_PRETE}</span>}</td>
                    <td className="num">
                      <span className={modifiee ? "barree" : ""}>{quantite(l.quantite, a.unite)}</span>
                      {modifiee && <span className="accorde">Accordé : {quantite(l.qte_accordee, a.unite)}</span>}
                    </td>
                    <td className="dispo">
                      <b className={insuffisant ? "rouge" : "vert"}>{quantite(a.qte_disponible, a.unite)}</b>
                      {insuffisant && <span className="pill p-c">{insuffisant}</span>}
                    </td>
                    {i === 0 && (
                      <td rowSpan={n} className="col-statut">
                        <span className={`pill ${statut.classe}`}>{statut.libelle}</span>
                        {d.requisition && <small className="sous-statut">{d.requisition.numero}</small>}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          );
        })}
        {!chargement && donnees?.results.length === 0 && (
          <tbody><tr><td colSpan={6} className="vide">{messageVide}</td></tr></tbody>
        )}
      </table>
      <div className="pied">
        <span>
          {chargement ? "Chargement…" : `${debut} à ${Math.min(page * parPage, total)} sur ${total} demande${total > 1 ? "s" : ""}`}
          {majLe && !chargement && <span className="maj"> · Mis à jour à {majLe.getHours()} h {String(majLe.getMinutes()).padStart(2, "0")}</span>}
        </span>
        <div className="pages">
          <button className="btn" type="button" disabled={page <= 1 || chargement} onClick={() => setPage(page - 1)}>← Page précédente</button>
          <button className="btn" type="button" disabled={page >= derniere || chargement} onClick={() => setPage(page + 1)}>Page suivante →</button>
        </div>
      </div>
    </div>
  );
}
