// Mise en forme commune : nombres à la française, unités, états du stock.
const nombre = new Intl.NumberFormat("fr-FR");

export function quantite(valeur, unite) {
  const n = nombre.format(valeur);
  if (unite === "m") return `${n} m`;
  if (unite === "paire") return `${n} ${valeur > 1 ? "paires" : "paire"}`;
  return n; // pièces : le nombre seul
}

export const ETATS = {
  OK: { libelle: "OK", classe: "p-ok" },
  BAS: { libelle: "Stock bas", classe: "p-w" },
  CRITIQUE: { libelle: "Critique", classe: "p-c" },
  EPUISE: { libelle: "Épuisé", classe: "p-c" },
};

const ariary = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
export function montant(valeur) {
  return `${ariary.format(Number(valeur))} Ar`;
}

export function date(iso) {
  if (!iso) return "—";
  const [a, m, j] = iso.split("-");
  return `${j}/${m}/${a}`;
}

/** Jour (à l'heure du PC) d'un horodatage du serveur : 12/10/2026. */
export function jourDe(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const deux = (n) => String(n).padStart(2, "0");
  return `${deux(d.getDate())}/${deux(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export function datePassee(iso) {
  return Boolean(iso) && new Date(iso) < new Date(new Date().toDateString());
}

/** Statut d'une demande → libellé et couleur. */
export const STATUTS_DEMANDE = {
  EN_ATTENTE: { libelle: "En attente", classe: "p-w" },
  VALIDEE: { libelle: "Validée", classe: "p-ok" },
  REFUSEE: { libelle: "Refusée", classe: "p-c" },
  ANNULEE: { libelle: "Annulée", classe: "p-g" },
};

/** Quantité demandée comparée au stock : « Épuisé », « Insuffisant » ou rien (suffisant). */
export function manque(demande, disponible) {
  if (disponible <= 0) return "Épuisé";
  if (demande > disponible) return "Insuffisant";
  return null;
}

/** Date et heure d'un horodatage du serveur : 08/10/2026 à 11 h 40. */
export function dateHeure(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const deux = (n) => String(n).padStart(2, "0");
  return `${deux(d.getDate())}/${deux(d.getMonth() + 1)}/${d.getFullYear()} à ${d.getHours()} h ${deux(d.getMinutes())}`;
}

// Libellé des deux types d'article (le même dans toutes les fenêtres).
export const LIBELLE_PRETE = "Non consommable · à rendre";
export const LIBELLE_CONSOMMABLE = "Consommable";
