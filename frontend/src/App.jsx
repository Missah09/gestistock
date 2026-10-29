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
import MenuLateral, { lirePreference, ecrirePreference } from "./MenuLateral.jsx";

// Écrans déjà développés ; les autres entrées du menu affichent « en préparation ».
const ECRANS = { Aide, "Tableau de bord": TableauDeBord, "Liste d'Articles": Articles, "Mes demandes": Demandes, "Demandes à valider": AValider, "Demandes à viser": AViser, "Liste Réquisitions": Requisitions, "Sorties de stock": Sorties, "Retours de stock": Retours, "Générer Rapports": Rapports, Historique, Comptes };

/** Menu selon le rôle, rangé dans l'ordre du circuit (16/10/2026) :
 *  Tableau de bord → Articles → Demandes → Réquisitions et mouvements → Rapports et suivi → Administration.
 *  Un groupe d'une seule entrée s'affiche comme une entrée simple (ex. « Mes demandes » pour un Saisisseur).
 *  Chaque élément : ["entrée", icône, titre] ou ["groupe", icône, titre du groupe, [[icône, titre]…]]. */
function menuPour(compte) {
  const agent = compte.agent_logistique;
  const resp = compte.responsable;
  const groupe = (icone, titre, entrees) => {
    const e = entrees.filter(Boolean);
    if (!e.length) return null;
    return e.length === 1 ? ["entree", ...e[0]] : ["groupe", icone, titre, e];
  };
  return [
    (agent || resp) && ["entree", "home", "Tableau de bord"],
    ["entree", "box", "Liste d'Articles"],
    groupe("clip", "Demandes", [["clip", "Mes demandes"], agent && ["check", "Demandes à valider"], resp && ["sign", "Demandes à viser"]]),
    groupe("out", "Mouvements de stock", [
      (agent || resp) && ["doc", "Liste Réquisitions"], agent && ["out", "Sorties de stock"], agent && ["back", "Retours de stock"]]),
    groupe("chart", "Rapports et suivi", [agent && ["chart", "Générer Rapports"], agent && ["clock", "Historique"]]),
    groupe("users", "Administration", [compte.administrateur && ["users", "Comptes"]]),
  ].filter(Boolean);
}

/** Toutes les entrées du menu, à plat : [[icône, titre]…]. */
const entreesDu = (menu) => menu.flatMap((m) => (m[0] === "groupe" ? m[3] : [[m[1], m[2]]]));

/** Écran ouvert après la connexion (12/10/2026) : le Tableau de bord pour le Responsable Technique et le Responsable Logistique,
 *  « Mes demandes » pour les Saisisseurs. */
function accueil(compte) {
  return compte && (compte.agent_logistique || compte.responsable) ? "Tableau de bord" : "Mes demandes";
}

/** Lien de l'email au Responsable Logistique : http://…/#a-viser/<id de la demande> → écran « Demandes à viser », réquisition ouverte. */
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
  // Menu de gauche caché (16/10/2026) : un clic le cache, un clic le réaffiche ; gardé d'une visite à l'autre.
  const [menuCache, setMenuCache] = useState(() => lirePreference("menu-cache", false));
  const basculerMenu = () => setMenuCache((v) => { ecrirePreference("menu-cache", !v); return !v; });

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
  const entrees = entreesDu(menu);
  const actif = ecran === "Aide" || entrees.some(([, l]) => l === ecran) ? ecran : accueil(compte);
  const Ecran = ECRANS[actif];

  /** Ouvre un écran du menu, avec d'éventuels réglages (filtre…). */
  function allerA(nom, reglages = null) {
    setOuvrirId(null); setParametres(reglages); setEcran(nom);
  }

  async function deconnecter() {
    try { await seDeconnecter(); } finally { setRaisonDeconnexion(null); setCompte(null); }
  }

  return (
    <div className={`app${menuCache ? " menu-cache" : ""}`}>
      {menuCache ? (
        <button type="button" className="menu-afficher" onClick={basculerMenu} title="Afficher le menu" aria-label="Afficher le menu">
          <Icon name="menu" size={22} stroke={2} />
        </button>
      ) : (
        <MenuLateral menu={menu} actif={actif} compte={compte} compteurs={compteurs} allerA={allerA}
          onDeconnecter={deconnecter} onCacher={basculerMenu} />
      )}
      <main className="main">
        {Ecran ? <Ecran key={actif} compte={compte} ouvrirId={actif === "Demandes à viser" ? ouvrirId : null}
          parametres={parametres} allerA={allerA} ecransDuMenu={entrees.map(([, l]) => l)} /> : (
          <>
            <header className="top"><h1>{actif}</h1></header>
            <div className="body"><div className="card prepa">Cet écran est en préparation.</div></div>
          </>
        )}
      </main>
    </div>
  );
}
