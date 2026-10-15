import { useCallback, useEffect, useState } from "react";
import { lireTableauDeBord } from "../api.js";
import { ETATS, montant, montantCourt, quantite } from "../format.js";
import Icon from "../icons.jsx";
import EntreeStock from "./EntreeStock.jsx";
import FicheArticle from "./FicheArticle.jsx";

/** Écran « Tableau de bord » (12/10/2026) : l'essentiel du jour, pour l'Agent Logistique et le Responsable HBC.
 *  Ouvert après la connexion. Chiffres et listes (pas de graphique), d'après la maquette.
 *  Mis à jour toutes les 30 s, au retour sur l'onglet et après chaque action (comme les pastilles du menu). */

// Couleur de la pastille de chaque événement de l'« Activité du jour ».
const TYPES_ACTIVITE = {
  entree: { classe: "a-entree", libelle: "Entrée en stock" },
  demande: { classe: "a-demande", libelle: "Nouvelle demande" },
  validation: { classe: "a-valide", libelle: "Demande validée" },
  visa: { classe: "a-valide", libelle: "Bon signé" },
  refus: { classe: "a-refus", libelle: "Refus" },
  sortie: { classe: "a-sortie", libelle: "Sortie de stock" },
  retour: { classe: "a-retour", libelle: "Retour de stock" },
};

function heure(iso) {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Une carte chiffrée ; cliquable quand l'écran correspondant est dans le menu de la personne. */
function Carte({ icone, ton, titre, valeur, detail, aide, onOuvrir }) {
  const contenu = (
    <>
      <span className={`tdb-icone ${ton}`}><Icon name={icone} size={26} /></span>
      <span className="tdb-texte">
        <span className="tdb-titre">{titre}</span>
        <span className={`tdb-valeur ${ton}`}>{valeur}</span>
        {detail && <span className="tdb-detail">{detail}</span>}
      </span>
    </>
  );
  return onOuvrir
    ? <button type="button" className="card tdb-carte cliquable" title={aide} onClick={onOuvrir}>{contenu}</button>
    : <div className="card tdb-carte" title={aide}>{contenu}</div>;
}

export default function TableauDeBord({ compte, allerA, ecransDuMenu = [] }) {
  const agent = !!compte?.agent_logistique;
  const [donnees, setDonnees] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [ouvert, setOuvert] = useState(null);       // fiche article ouverte
  const [reception, setReception] = useState(null); // fenêtre « Entrée en stock » ouverte depuis une fiche
  const [rafraichir, setRafraichir] = useState(0);

  useEffect(() => {
    let annule = false;
    const charger = () => {
      if (document.hidden) return;
      lireTableauDeBord()
        .then((d) => { if (!annule) { setDonnees(d); setErreur(null); } })
        .catch(() => !annule && setErreur("Impossible de joindre le serveur. Vérifiez que la fenêtre du backend (runserver) est ouverte."));
    };
    charger();
    const minuteur = setInterval(charger, 30_000);
    document.addEventListener("visibilitychange", charger);
    window.addEventListener("gestistock:compteurs", charger);
    return () => {
      annule = true; clearInterval(minuteur);
      document.removeEventListener("visibilitychange", charger); window.removeEventListener("gestistock:compteurs", charger);
    };
  }, [rafraichir]);

  const fermerFiche = useCallback(() => setOuvert(null), []);
  const ouvrir = (ecran, reglages) => (ecransDuMenu.includes(ecran) ? () => allerA(ecran, reglages) : null);

  const c = donnees?.cartes ?? {};
  const liste = donnees?.a_reapprovisionner ?? [];
  const activite = donnees?.activite ?? [];
  const autresSousSeuil = (c.sous_seuil ?? 0) - liste.length;
  const voirSousSeuil = ouvrir("Liste d'Articles", { sousSeuil: true });
  // Carte « en attente » : demandes à valider (Agent Logistique) ou bons à viser (Responsable HBC).
  const attente = "a_valider" in c
    ? { titre: "Demandes à valider", valeur: c.a_valider, ecran: "Demandes à valider", aide: "Demandes envoyées qui attendent votre validation" }
    : { titre: "Bons à viser", valeur: c.a_viser, ecran: "Demandes à viser", aide: "Réquisitions qui attendent votre signature" };

  return (
    <>
      <header className="top">
        <h1>Tableau de bord</h1>
        {donnees && <span className="tdb-maj">Mis à jour à {heure(donnees.maintenant)}</span>}
      </header>
      <div className="body tdb">
        {erreur && <div className="alerte">{erreur}</div>}

        <div className="tdb-cartes">
          <Carte icone="attention" ton={c.sous_seuil > 0 ? "rouge" : "vert"} titre="Articles sous le seuil"
            valeur={donnees ? c.sous_seuil : "…"} aide="Articles sous la quantité minimale, ou épuisés"
            onOuvrir={voirSousSeuil} />
          <Carte icone="clip" ton={attente.valeur > 0 ? "orange" : "vert"} titre={attente.titre}
            valeur={donnees ? attente.valeur : "…"} aide={attente.aide} onOuvrir={ouvrir(attente.ecran)} />
          <Carte icone="back" ton={c.retours_en_retard > 0 ? "rouge" : "vert"} titre="Retours en retard"
            valeur={donnees ? c.retours_en_retard : "…"} aide="Réquisitions dont du matériel prêté n'est pas rentré à la date prévue"
            onOuvrir={ouvrir("Retours de stock")} />
          <Carte icone="billet" ton="bleu" titre="Valeur du stock" valeur={donnees ? montantCourt(c.valeur_stock) : "…"}
            aide={donnees ? `${montant(c.valeur_stock)} : quantité disponible × prix unitaire (le matériel prêté n'est pas compté)` : undefined} />
        </div>

        <div className="tdb-grille">
          <section className="card tdb-panneau">
            <div className="tdb-panneau-tete">
              <h2>À réapprovisionner</h2>
              {voirSousSeuil && liste.length > 0 && (
                <button type="button" className="btn lien" onClick={voirSousSeuil}>Voir tout<Icon name="fleche" size={16} stroke={2.2} /></button>
              )}
            </div>
            <table className="tableau">
              <thead>
                <tr><th>Article</th><th className="centre">Stock</th><th className="centre">Minimum</th><th>État</th></tr>
              </thead>
              <tbody>
                {liste.map((a) => {
                  const etat = ETATS[a.etat];
                  return (
                    <tr key={a.id} className={`cliquable ${a.id === ouvert ? "choisie" : ""}`} onClick={() => setOuvert(a.id)}
                      title="Voir la fiche de l'article">
                      <td className="nom" title={a.code}>{a.nom}</td>
                      <td className="num centre">{quantite(a.qte_disponible, a.unite)}</td>
                      <td className="discret centre">{quantite(a.qte_minimale, a.unite)}</td>
                      <td><span className={`pill ${etat.classe}`}>{etat.libelle}</span></td>
                    </tr>
                  );
                })}
                {donnees && liste.length === 0 && (
                  <tr><td colSpan={4} className="vide">Aucun article sous le seuil : tout le stock est au-dessus du minimum.</td></tr>
                )}
              </tbody>
            </table>
            {autresSousSeuil > 0 && (
              <div className="tdb-pied">
                Et {autresSousSeuil} autre{autresSousSeuil > 1 ? "s" : ""} article{autresSousSeuil > 1 ? "s" : ""} sous le seuil.
                {voirSousSeuil && <button type="button" className="btn lien" onClick={voirSousSeuil}>Voir la liste complète</button>}
              </div>
            )}
          </section>

          <section className="card tdb-panneau">
            <div className="tdb-panneau-tete">
              <h2>Activité du jour</h2>
              {ouvrir("Historique") && (
                <button type="button" className="btn lien" onClick={ouvrir("Historique", { periode: "jour" })}>
                  Historique<Icon name="fleche" size={16} stroke={2.2} />
                </button>
              )}
            </div>
            <ul className="tdb-activite">
              {activite.map((e, i) => {
                const t = TYPES_ACTIVITE[e.type] ?? TYPES_ACTIVITE.demande;
                return (
                  <li key={i}>
                    <span className={`tdb-point ${t.classe}`} title={t.libelle} />
                    <span className="tdb-evenement">{e.texte}</span>
                    <time dateTime={e.le}>{heure(e.le)}</time>
                  </li>
                );
              })}
              {donnees && activite.length === 0 && <li className="vide">Rien d'enregistré aujourd'hui pour l'instant.</li>}
            </ul>
            {donnees && donnees.nb_activites > activite.length && (
              <div className="tdb-pied">Et {donnees.nb_activites - activite.length} événement(s) plus ancien(s) aujourd'hui.</div>
            )}
          </section>
        </div>
      </div>

      {reception && (
        <EntreeStock
          articleInitial={reception.article}
          onFermer={() => { const id = reception.article; setReception(null); if (id) setOuvert(id); }}
          onArticleCree={() => setRafraichir((n) => n + 1)}
          onEnregistre={() => { const id = reception.article; setReception(null); setRafraichir((n) => n + 1); if (id) setOuvert(id); }}
        />
      )}
      {ouvert && <FicheArticle id={ouvert} modifiable={agent} onFermer={fermerFiche} onModifie={() => setRafraichir((n) => n + 1)}
        onEntreeStock={(id) => { setOuvert(null); setReception({ article: id }); }} />}
    </>
  );
}
