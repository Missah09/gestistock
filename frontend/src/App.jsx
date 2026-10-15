import symboleHbc from "./assets/logo-hbc-symbole.png"; // symbole HBC (les 4 barres) – à remplacer par la version haute qualité
import Icon from "./icons.jsx";
import { useEffect, useState } from "react";
import { lireCompteurs, lireSession, seDeconnecter } from "./api.js";
import Aide from "./pages/Aide.jsx";
import Articles from "./pages/Articles.jsx";
import Comptes from "./pages/Comptes.jsx";
import Connexion from "./pages/Connexion.jsx";
import AValider from "./pages/AValider.jsx";
import AViser from "./pages/AViser.jsx";
import Demandes from "./pages/Demandes.jsx";
import Historique from "./pages/Historique.jsx";
import Rapports from "./pages/Rapports.jsx";
import Requisitions from "./pages/Requisitions.jsx";
import Retours from "./pages/Retours.jsx";
import Sorties from "./pages/Sorties.jsx";
import TableauDeBord from "./pages/TableauDeBord.jsx";

// Écrans déjà développés ; les autres entrées du menu affichent « en préparation ».
const ECRANS = { Aide, "Tableau de bord": TableauDeBord, "Liste d'Articles": Articles, "Mes demandes": Demandes, "Demandes à valider": AValider, "Demandes à viser": AViser, "Liste Réquisitions": Requisitions, "Sorties de stock": Sorties, "Retours de stock": Retours, "Générer Rapports": Rapports, Historique, Comptes };

/** Menu selon le rôle (ordre fixé le 11/10/2026).
 *  Articles (consultation) pour tous ; Tableau de bord pour l'Agent Logistique et le Responsable HBC. */
function menuPour(compte) {
  const agent = compte.agent_logistique;
  const menu = [];
  if (agent || compte.responsable) menu.push(["home", "Tableau de bord"]);
  menu.push(["box", "Liste d'Articles"], ["clip", "Mes demandes"]);
  if (agent) menu.push(["check", "Demandes à valider"]);
  if (compte.responsable) menu.push(["sign", "Demandes à viser"]);
  // Réquisitions (bons signés, PDF) : Agent Logistique et Responsable HBC (12/10/2026)
  if (agent || compte.responsable) menu.push(["doc", "Liste Réquisitions"]);
  if (agent) menu.push(["out", "Sorties de stock"], ["back", "Retours de stock"], ["chart", "Générer Rapports"], ["clock", "Historique"]);
  if (compte.administrateur) menu.push(["users", "Comptes"]);
  return menu;
}

/** Écran ouvert après la connexion (12/10/2026) : le Tableau de bord pour l'Agent Logistique et le Responsable HBC,
 *  « Mes demandes » pour les Saisisseurs. */
function accueil(compte) {
  return compte && (compte.agent_logistique || compte.responsable) ? "Tableau de bord" : "Mes demandes";
}

// Compteur affiché à droite de l'entrée du menu (ce qui attend l'utilisateur).
const COMPTEUR_DU_MENU = { "Demandes à valider": "a_valider", "Demandes à viser": "a_viser", "Liste Réquisitions": "a_imprimer", "Sorties de stock": "a_confirmer", "Retours de stock": "retours_en_retard" };

/** Lien de l'email au Responsable : http://…/#a-viser/<id de la demande> → écran « Demandes à viser », réquisition ouverte. */
function lienDeLEmail() {
  const m = window.location.hash.match(/^#a-viser\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export default function App() {
  const [compte, setCompte] = useState(undefined); // undefined : vérification en cours ; null : non connecté
  const [ecran, setEcran] = useState("Mes demandes");
  const [ouvrirId, setOuvrirId] = useState(lienDeLEmail);
  // Réglages passés à l'écran ouvert depuis un autre (ex. Tableau de bord → Liste d'Articles filtrée « Sous le seuil »).
  const [parametres, setParametres] = useState(null);
  const [compteurs, setCompteurs] = useState({});
  const [raisonDeconnexion, setRaisonDeconnexion] = useState(null); // ex. « compte ouvert sur un autre appareil »

  // Un compte = un seul appareil connecté : toutes les 30 s on vérifie que la session est toujours ouverte.
  useEffect(() => {
    if (!compte) return;
    const verifier = () => {
      if (document.hidden) return;
      lireSession().then((s) => {
        if (!s.connecte) { setRaisonDeconnexion(s.message || "Votre session est terminée : reconnectez-vous."); setCompte(null); }
      }).catch(() => {});
    };
    const minuteur = setInterval(verifier, 30_000);
    document.addEventListener("visibilitychange", verifier);
    return () => { clearInterval(minuteur); document.removeEventListener("visibilitychange", verifier); };
  }, [compte]);

  // Compteurs du menu : au démarrage, toutes les 30 s, au retour sur l'onglet et après chaque action.
  useEffect(() => {
    if (!compte || !(compte.agent_logistique || compte.responsable)) { setCompteurs({}); return; }
    let annule = false;
    const charger = () => { if (!document.hidden) lireCompteurs().then((c) => !annule && setCompteurs(c)).catch(() => {}); };
    charger();
    const minuteur = setInterval(charger, 30_000);
    document.addEventListener("visibilitychange", charger);
    window.addEventListener("gestistock:compteurs", charger);
    return () => {
      annule = true; clearInterval(minuteur);
      document.removeEventListener("visibilitychange", charger); window.removeEventListener("gestistock:compteurs", charger);
    };
  }, [compte]);
  // Le lien a servi (une fois connecté) : on le retire de la barre d'adresse.
  useEffect(() => {
    if (compte && ouvrirId) {
      if (compte.responsable) setEcran("Demandes à viser");
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, [compte]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    lireSession().then((s) => {
      setRaisonDeconnexion(s.message || null);
      if (s.connecte) setEcran(accueil(s));
      setCompte(s.connecte ? s : null);
    }).catch(() => setCompte(null));
    // Session terminée pendant le travail : retour à l'écran de connexion.
    const fin = (e) => { setRaisonDeconnexion(e.detail || null); setCompte(null); };
    window.addEventListener("gestistock:deconnecte", fin);
    return () => window.removeEventListener("gestistock:deconnecte", fin);
  }, []);

  if (compte === undefined) return <div className="connexion-fond" />;
  if (compte === null) return <Connexion message={raisonDeconnexion}
    onConnecte={(c) => { setRaisonDeconnexion(null); setEcran(ouvrirId && c.responsable ? "Demandes à viser" : accueil(c)); setCompte(c); }} />;

  const menu = menuPour(compte);
  const actif = ecran === "Aide" || menu.some(([, l]) => l === ecran) ? ecran : accueil(compte);
  const Ecran = ECRANS[actif];

  /** Ouvre un écran du menu, avec d'éventuels réglages (filtre…). */
  function allerA(nom, reglages = null) {
    setOuvrirId(null); setParametres(reglages); setEcran(nom);
  }

  async function deconnecter() {
    try { await seDeconnecter(); } finally { setRaisonDeconnexion(null); setCompte(null); }
  }

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <span className="logo-rond"><img src={symboleHbc} alt="Logo HBC" /></span>
          <span className="brand-texte">
            <span className="nom-appli">GestiStock</span>
            <span className="societe">H.B.C</span>
          </span>
        </div>
        <nav className="nav">
          {menu.map(([icon, label]) => (
            <a key={label} className={label === actif ? "on" : ""} href="#" aria-current={label === actif ? "page" : undefined}
              onClick={(e) => { e.preventDefault(); allerA(label); }}><Icon name={icon} />{label}
              {compteurs[COMPTEUR_DU_MENU[label]] > 0 && (
                <span className={`pastille${label === "Retours de stock" ? " retard" : ""}`}
                  title={label === "Retours de stock" ? "Matériel en retard (date de retour dépassée)" : "En attente de votre part"}>{compteurs[COMPTEUR_DU_MENU[label]]}</span>
              )}</a>
          ))}
        </nav>
        <nav className="nav bottom">
          <a className={actif === "Aide" ? "on" : ""} href="#" aria-current={actif === "Aide" ? "page" : undefined}
            onClick={(e) => { e.preventDefault(); allerA("Aide"); }}><Icon name="help" />Aide</a>
          {compte.administrateur && <a href="/admin/" target="_blank" rel="noreferrer"><Icon name="sliders" />Administration</a>}
        </nav>
        <div className="carte-compte">
          <div className="compte-nom" title={compte.nom}>{compte.nom}</div>
          {!compte.administrateur && (
            <div className="compte-info">{compte.roles.filter((r) => r !== "Saisisseur").join(" · ") || "Saisisseur"}</div>
          )}
          {compte.departement && <div className="compte-info compte-dep">{/^d[ée]partement/i.test(compte.departement) ? compte.departement : `Département ${compte.departement}`}</div>}
          <button className="btn compte-sortie" onClick={deconnecter}><Icon name="logout" />Se déconnecter</button>
        </div>
      </aside>
      <main className="main">
        {Ecran ? <Ecran key={actif} compte={compte} ouvrirId={actif === "Demandes à viser" ? ouvrirId : null}
          parametres={parametres} allerA={allerA} ecransDuMenu={menu.map(([, l]) => l)} /> : (
          <>
            <header className="top"><h1>{actif}</h1></header>
            <div className="body"><div className="card prepa">Cet écran est en préparation.</div></div>
          </>
        )}
      </main>
    </div>
  );
}
