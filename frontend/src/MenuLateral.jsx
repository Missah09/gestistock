import { useEffect, useLayoutEffect, useRef, useState } from "react";
import symboleHbc from "./assets/logo-hbc-symbole.png"; // symbole HBC (les 4 barres) – à remplacer par la version haute qualité
import Icon from "./icons.jsx";

/** Menu de gauche (16/10/2026).
 *  - Entrées rangées dans l'ordre du circuit et regroupées (Demandes, Réquisitions et mouvements, Rapports et suivi…).
 *  - Un groupe se déroule ou se replie d'un clic sur son titre ; replié, il montre le total de ses compteurs.
 *  - Le menu tient toujours dans la hauteur de l'écran, sans barre de défilement : si la place manque,
 *    les groupes qui ne contiennent pas l'écran ouvert se replient d'eux-mêmes.
 *  - Le bouton « « » à côté du logo cache le menu ; le bouton ☰ en haut à gauche le réaffiche. */

// Compteur affiché à droite de l'entrée du menu (ce qui attend l'utilisateur).
const COMPTEUR_DU_MENU = { "Demandes à valider": "a_valider", "Demandes à viser": "a_viser", "Liste Réquisitions": "a_imprimer", "Sorties de stock": "a_confirmer", "Retours de stock": "retours_en_retard" };
const EN_RETARD = "Retours de stock";

/** Préférences gardées dans le navigateur (menu caché, groupes ouverts) ; sans effet si le stockage est bloqué. */
export function lirePreference(cle, defaut) {
  try { const v = window.localStorage.getItem(`gestistock:${cle}`); return v === null ? defaut : JSON.parse(v); } catch { return defaut; }
}
export function ecrirePreference(cle, valeur) {
  try { window.localStorage.setItem(`gestistock:${cle}`, JSON.stringify(valeur)); } catch { /* stockage indisponible */ }
}

function Pastille({ n, retard }) {
  if (!(n > 0)) return null;
  return (
    <span className={`pastille${retard ? " retard" : ""}`}
      title={retard ? "Matériel en retard (date de retour dépassée)" : "En attente de votre part"}>{n}</span>
  );
}

function Entree({ icone, titre, actif, compteurs, allerA, sous }) {
  return (
    <a className={`${titre === actif ? "on" : ""}${sous ? " sous" : ""}`} href="#" aria-current={titre === actif ? "page" : undefined}
      onClick={(e) => { e.preventDefault(); allerA(titre); }}>
      <Icon name={icone} size={sous ? 19 : 21} />{titre}
      <Pastille n={compteurs[COMPTEUR_DU_MENU[titre]]} retard={titre === EN_RETARD} />
    </a>
  );
}

export default function MenuLateral({ menu, actif, compte, compteurs, allerA, onDeconnecter, onCacher }) {
  // Choix de la personne : {titre du groupe: true (ouvert) | false (replié)} ; sinon ouvert par défaut.
  const [choix, setChoix] = useState(() => lirePreference("menu-groupes", {}));
  const [auto, setAuto] = useState([]); // groupes repliés d'eux-mêmes faute de place
  const [hauteur, setHauteur] = useState(() => window.innerHeight);
  const cote = useRef(null);

  const groupeDe = (titre) => menu.find((m) => m[0] === "groupe" && m[3].some(([, t]) => t === titre))?.[2];
  const groupeActif = groupeDe(actif);
  const ouvert = (g) => choix[g] ?? (g === groupeActif || !auto.includes(g));

  function basculer(g) {
    const suivant = { ...choix, [g]: !ouvert(g) };
    setChoix(suivant); ecrirePreference("menu-groupes", suivant);
  }

  // L'écran ouvert est dans un groupe replié (ex. ouvert depuis le Tableau de bord) : on déroule ce groupe.
  useEffect(() => {
    if (groupeActif && choix[groupeActif] === false) {
      const suivant = { ...choix }; delete suivant[groupeActif];
      setChoix(suivant); ecrirePreference("menu-groupes", suivant);
    }
  }, [actif]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fenêtre redimensionnée : on recalcule la place disponible.
  useEffect(() => {
    let minuteur;
    const changer = () => { clearTimeout(minuteur); minuteur = setTimeout(() => { setAuto([]); setHauteur(window.innerHeight); }, 120); };
    window.addEventListener("resize", changer);
    return () => { clearTimeout(minuteur); window.removeEventListener("resize", changer); };
  }, []);

  // Tenir dans la hauteur de l'écran : on replie, du bas vers le haut, les groupes ouverts par défaut
  // qui ne contiennent pas l'écran actif, jusqu'à ce qu'il n'y ait plus de débordement.
  useLayoutEffect(() => {
    const el = cote.current;
    if (!el || el.scrollHeight <= el.clientHeight + 1) return;
    const candidats = menu.filter((m) => m[0] === "groupe" && m[2] !== groupeActif && choix[m[2]] === undefined && !auto.includes(m[2]))
      .map((m) => m[2]);
    if (candidats.length) setAuto((a) => [...a, candidats[candidats.length - 1]]);
  }, [menu, choix, auto, groupeActif, hauteur]);

  return (
    <aside className="side" ref={cote}>
      <div className="brand">
        <span className="logo-rond"><img src={symboleHbc} alt="Logo HBC" /></span>
        <span className="brand-texte">
          <span className="nom-appli">GestiStock</span>
          <span className="societe">H.B.C</span>
        </span>
        <button type="button" className="menu-cacher" onClick={onCacher} title="Cacher le menu" aria-label="Cacher le menu">
          <Icon name="replier" size={20} stroke={2.2} />
        </button>
      </div>
      <nav className="nav">
        {menu.map((m) => {
          if (m[0] === "entree") {
            return <Entree key={m[2]} icone={m[1]} titre={m[2]} actif={actif} compteurs={compteurs} allerA={allerA} />;
          }
          const [, icone, titre, entrees] = m;
          const deroule = ouvert(titre);
          const total = entrees.reduce((t, [, e]) => t + (compteurs[COMPTEUR_DU_MENU[e]] || 0), 0);
          const retard = entrees.some(([, e]) => e === EN_RETARD && compteurs[COMPTEUR_DU_MENU[e]] > 0);
          return (
            <div key={titre} className={`nav-groupe${deroule ? " ouvert" : ""}${titre === groupeActif ? " contient-actif" : ""}`}>
              <button type="button" className="nav-groupe-titre" aria-expanded={deroule} onClick={() => basculer(titre)}>
                <Icon name={icone} size={21} /><span className="nav-groupe-nom">{titre}</span>
                {!deroule && <Pastille n={total} retard={retard && total === (compteurs[COMPTEUR_DU_MENU[EN_RETARD]] || 0)} />}
                <span className="nav-chevron"><Icon name="chevron" size={16} stroke={2.4} /></span>
              </button>
              {deroule && (
                <div className="nav-groupe-entrees">
                  {entrees.map(([ic, t]) => <Entree key={t} icone={ic} titre={t} actif={actif} compteurs={compteurs} allerA={allerA} sous />)}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      <nav className="nav bottom">
        <a className={actif === "Aide" ? "on" : ""} href="#" aria-current={actif === "Aide" ? "page" : undefined}
          onClick={(e) => { e.preventDefault(); allerA("Aide"); }}><Icon name="help" size={21} />Aide</a>
        {compte.administrateur && <a href="/admin/" target="_blank" rel="noreferrer"><Icon name="sliders" size={21} />Administration</a>}
      </nav>
      <div className="carte-compte">
        <div className="compte-texte">
          <div className="compte-nom" title={compte.nom}>{compte.nom}</div>
          {!compte.administrateur && (
            <div className="compte-info">{compte.roles.filter((r) => r !== "Saisisseur").join(" · ") || "Saisisseur"}</div>
          )}
          {compte.departement && <div className="compte-info compte-dep">{/^d[ée]partement/i.test(compte.departement) ? compte.departement : `Département ${compte.departement}`}</div>}
        </div>
        <button className="btn compte-sortie" onClick={onDeconnecter} title="Se déconnecter"><Icon name="logout" size={18} />Se déconnecter</button>
      </div>
    </aside>
  );
}
