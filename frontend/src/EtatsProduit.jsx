import { ETATS_PRODUIT, ETATS_UTILISABLES, ORDRE_ETATS, quantite } from "./format.js";

/** Pastille d'un état du produit (Neuf, Bon, Moyen, Mauvais). */
export function PastilleEtat({ etat, children }) {
  const e = ETATS_PRODUIT[etat];
  if (!e) return null;
  return <span className={`pill etat-produit ${e.classe}`}>{children ?? e.libelle}</span>;
}

/** Répartition par état : « 12 Bon · 3 Moyen · 2 Mauvais » sous forme de pastilles.
 *  `seulement` : états à montrer (par défaut tous) ; les zéros sont omis. */
export default function EtatsProduit({ etats, unite, seulement = ORDRE_ETATS, vide = "—" }) {
  const presents = seulement.filter((e) => etats?.[e] > 0);
  if (!presents.length) return <span className="discret">{vide}</span>;
  return (
    <span className="etats-produit">
      {presents.map((e) => (
        <PastilleEtat key={e} etat={e}><b>{quantite(etats[e], unite)}</b> {ETATS_PRODUIT[e].libelle}</PastilleEtat>
      ))}
    </span>
  );
}

export { ETATS_UTILISABLES };
