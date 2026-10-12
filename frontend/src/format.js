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

/** Montant court pour les cartes du Tableau de bord : 612 450 000 → « 612 M Ar », 4 750 000 → « 4,8 M Ar ». */
export function montantCourt(valeur) {
  const v = Number(valeur) || 0;
  const court = (n, suffixe) => `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: n < 100 ? 1 : 0 }).format(n)} ${suffixe}`;
  if (v >= 1e9) return court(v / 1e9, "Md Ar");
  if (v >= 1e6) return court(v / 1e6, "M Ar");
  return montant(Math.round(v));
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

// ---------- État du produit : le même partout dans l'application ----------
// Simplifié le 12/10/2026 (après-midi) : Neuf · Bon · Moyen · Mauvais, tous disponibles.
export const ETATS_PRODUIT = {
  NEUF: { libelle: "Neuf", classe: "e-neuf" },
  BON: { libelle: "Bon", classe: "e-bon" },
  MOYEN: { libelle: "Moyen", classe: "e-moyen" },
  MAUVAIS: { libelle: "Mauvais", classe: "e-mauvais" },
};
export const ORDRE_ETATS = ["NEUF", "BON", "MOYEN", "MAUVAIS"];
/** États disponibles (proposés dans les demandes, peuvent sortir) : tous. */
export const ETATS_UTILISABLES = ORDRE_ETATS;

/** {"NEUF": 3, "BON": 2} → « 3 Neuf · 2 Bon » (zéros omis ; `unite` : « 14 600 m Neuf »). */
export function texteEtats(etats, liste = ORDRE_ETATS, unite) {
  return liste.filter((e) => etats?.[e] > 0).map((e) => `${quantite(etats[e], unite)} ${ETATS_PRODUIT[e].libelle}`).join(" · ");
}

/** Nombre de jours de retard (date prévue dépassée). */
export function joursDeRetard(iso) {
  if (!iso) return 0;
  const [a, m, j] = iso.split("-").map(Number);
  const prevue = new Date(a, m - 1, j);
  const auj = new Date(new Date().toDateString());
  return Math.max(0, Math.round((auj - prevue) / 86_400_000));
}


/** État d'un article tel qu'il figure sur le bon avant la sortie (d'après la fiche) : « Neuf », « Bon / Moyen ». */
export function etatsDisponibles(etats) {
  return ETATS_UTILISABLES.filter((e) => etats?.[e] > 0).map((e) => ETATS_PRODUIT[e].libelle).join(" / ");
}
