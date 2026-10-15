// Appels au backend Django (transmis par Vite vers le port 8000).

function lireCookie(nom) {
  const morceau = document.cookie.split("; ").find((c) => c.startsWith(nom + "="));
  return morceau ? decodeURIComponent(morceau.slice(nom.length + 1)) : "";
}

/** fetch + cookie de session + jeton CSRF pour les envois.
 *  Si la session est terminée (401), l'application revient à l'écran de connexion. */
async function appel(url, options = {}) {
  const methode = (options.method || "GET").toUpperCase();
  const headers = { ...(options.headers || {}) };
  if (methode !== "GET") headers["X-CSRFToken"] = lireCookie("csrftoken");
  const reponse = await fetch(url, { credentials: "same-origin", ...options, headers });
  if (reponse.status === 401) {
    // Session terminée (ou compte ouvert sur un autre appareil) : retour à l'écran de connexion, avec la raison.
    const corps = await reponse.clone().json().catch(() => ({}));
    window.dispatchEvent(new CustomEvent("gestistock:deconnecte", { detail: corps.general?.[0] ?? null }));
  }
  return reponse;
}

async function lire(url) {
  const reponse = await appel(url);
  if (!reponse.ok) throw new Error(`Erreur ${reponse.status}`);
  return reponse.json();
}

export function listerArticles({ page = 1, q = "", categorie = "", magasin = "", sousSeuil = false, etat = "" } = {}) {
  const params = new URLSearchParams({ page });
  if (etat) params.set("etat", etat);
  if (q.trim()) params.set("q", q.trim());
  if (categorie) params.set("categorie", categorie);
  if (magasin) params.set("magasin", magasin);
  if (sousSeuil) params.set("sous_seuil", "1");
  return lire(`/api/articles/?${params}`);
}

export function lireFiltres() {
  return lire("/api/filtres/");
}

export function lireArticle(id) {
  return lire(`/api/articles/${id}/`);
}

export function lireChoix() {
  return lire("/api/choix/");
}

/** Enregistre les modifications. En cas de refus (400), l'erreur porte le détail par champ. */
export async function modifierArticle(id, donnees) {
  const reponse = await appel(`/api/articles/${id}/`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(donnees),
  });
  const corps = await reponse.json().catch(() => ({}));
  if (!reponse.ok) {
    const erreur = new Error(`Erreur ${reponse.status}`);
    erreur.details = reponse.status === 400 ? corps : null;
    throw erreur;
  }
  return corps;
}

/** « Nouvel article » (12/10/2026) : renvoie la fiche du nouvel article et un message. */
export function creerArticle(donnees) {
  return envoyer("/api/articles/", donnees);
}

/** Enregistre une réception de produits. En cas de refus (400), l'erreur porte le détail. */
export async function enregistrerEntree(donnees) {
  const reponse = await appel("/api/entrees/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(donnees),
  });
  const corps = await reponse.json().catch(() => ({}));
  if (!reponse.ok) {
    const erreur = new Error(`Erreur ${reponse.status}`);
    erreur.details = reponse.status === 400 ? corps : null;
    throw erreur;
  }
  return corps;
}

/** Envoi (POST) avec le détail des erreurs par champ en cas de refus (400). */
async function envoyer(url, donnees, methode = "POST") {
  const reponse = await appel(url, {
    method: methode,
    headers: { "Content-Type": "application/json" },
    body: donnees === undefined ? undefined : JSON.stringify(donnees),
  });
  const corps = await reponse.json().catch(() => ({}));
  if (!reponse.ok) {
    const erreur = new Error(`Erreur ${reponse.status}`);
    erreur.details = [400, 404, 429].includes(reponse.status) ? corps : null;
    throw erreur;
  }
  return corps;
}

// ---------- Demandes ----------
export function listerDemandes({ onglet = "attente", page = 1 } = {}) {
  return lire(`/api/demandes/?${new URLSearchParams({ onglet, page })}`);
}
export function lireChoixDemande() {
  return lire("/api/demandes/choix/");
}
export function envoyerDemande(donnees) {
  return envoyer("/api/demandes/", donnees);
}
export function lireDemande(id) {
  return lire(`/api/demandes/${id}/`);
}
export function annulerDemande(id) {
  return envoyer(`/api/demandes/${id}/annuler/`);
}

// ---------- Demandes à valider (Agent Logistique) ----------
export function listerAValider({ onglet = "attente", page = 1 } = {}) {
  return lire(`/api/a-valider/?${new URLSearchParams({ onglet, page })}`);
}
export function lireAValider(id) {
  return lire(`/api/a-valider/${id}/`);
}
/** lignes : [{ id, qte_accordee }] ; signature : corps de ZoneSignature ({ source, signature?, enregistrer?, mot_de_passe })
 *  – valide et crée la réquisition matière. */
export function validerDemande(id, lignes, signature) {
  return envoyer(`/api/a-valider/${id}/valider/`, { lignes, ...signature });
}
/** Clic sur « Valider » : le n° de réquisition est attribué tout de suite (affiché sur le bon à signer). */
export function attribuerNumero(id) {
  return envoyer(`/api/a-valider/${id}/numero/`);
}
export function refuserDemande(id, motif) {
  return envoyer(`/api/a-valider/${id}/refuser/`, { motif });
}

export function renvoyerEmail(id) {
  return envoyer(`/api/a-valider/${id}/renvoyer-email/`);
}

// ---------- À viser (Responsable HBC) ----------
export function listerAViser({ onglet = "attente", page = 1 } = {}) {
  return lire(`/api/a-viser/?${new URLSearchParams({ onglet, page })}`);
}
export function lireAViser(id) {
  return lire(`/api/a-viser/${id}/`);
}
/** signature : corps de ZoneSignature ({ source, signature?, enregistrer?, mot_de_passe }). */
export function viserRequisition(id, signature) {
  return envoyer(`/api/a-viser/${id}/viser/`, signature);
}

// ---------- Signature scannée enregistrée dans le compte (15/10/2026) ----------
export function lireMaSignature() {
  return lire("/api/ma-signature/");
}
export function retirerMaSignature() {
  return envoyer("/api/ma-signature/", undefined, "DELETE");
}
export function refuserRequisition(id, motif) {
  return envoyer(`/api/a-viser/${id}/refuser/`, { motif });
}

// ---------- Réquisitions (Agent Logistique et Responsable HBC) : bons signés, PDF ----------
export function listerRequisitions({ onglet = "a_imprimer", page = 1 } = {}) {
  return lire(`/api/requisitions/?${new URLSearchParams({ onglet, page })}`);
}
export function lireRequisition(id) {
  return lire(`/api/requisitions/${id}/`);
}
/** Télécharge le PDF du bon (id de la demande) et l'enregistre sous « RM-2026-0001.pdf ».
 *  Le serveur note le téléchargement (premier téléchargement par l'Agent Logistique = bon imprimé). */
export function telechargerBon(id, numero) {
  return telechargerPdf(`/api/requisitions/${id}/pdf/`, `${numero}.pdf`);
}
/** « Imprimer » (12/10/2026) : le PDF du bon s'ouvre dans la fenêtre d'impression du navigateur.
 *  Le serveur note l'impression (première impression par l'Agent Logistique = bon « Imprimée »). */
export async function imprimerBon(id) {
  const reponse = await appel(`/api/requisitions/${id}/pdf/?impression=1`);
  if (!reponse.ok) {
    const corps = await reponse.json().catch(() => ({}));
    throw new Error(corps.general?.[0] ?? `Erreur ${reponse.status}`);
  }
  const lien = URL.createObjectURL(await reponse.blob());
  document.getElementById("cadre-impression")?.remove();
  const cadre = document.createElement("iframe");
  cadre.id = "cadre-impression";
  cadre.title = "Impression du bon";
  cadre.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
  cadre.src = lien;
  // Le PDF se charge dans un cadre invisible, puis la fenêtre d'impression du navigateur s'ouvre.
  const charge = await new Promise((ok) => {
    const minuteur = setTimeout(() => ok(false), 8000);
    cadre.onload = () => { clearTimeout(minuteur); ok(true); };
    document.body.appendChild(cadre);
  });
  try {
    if (!charge) throw new Error("PDF non affiché");
    cadre.contentWindow.focus();
    cadre.contentWindow.print();
  } catch {
    // Navigateur qui refuse : le PDF s'ouvre dans un onglet, imprimer avec Ctrl+P.
    window.open(lien, "_blank");
  }
  setTimeout(() => URL.revokeObjectURL(lien), 10 * 60_000);
}

// ---------- Sorties (Agent Logistique) : confirmation de la remise, le stock diminue (12/10/2026) ----------
export function listerSorties({ onglet = "a_confirmer", page = 1 } = {}) {
  return lire(`/api/sorties/?${new URLSearchParams({ onglet, page })}`);
}
export function lireSortie(id) {
  return lire(`/api/sorties/${id}/`);
}
/** donnees : { date_remise, magasinier, observation, lignes: [{ id, qte_livree, exemplaires: [id…] }] } */
export function confirmerSortie(id, donnees) {
  return envoyer(`/api/sorties/${id}/confirmer/`, donnees);
}

/** Télécharge un PDF et l'enregistre sous `nom` (bon de réquisition, copie d'archive…). */
async function telechargerPdf(url, nom) {
  const reponse = await appel(url);
  if (!reponse.ok) {
    const corps = await reponse.json().catch(() => ({}));
    throw new Error(corps.general?.[0] ?? `Erreur ${reponse.status}`);
  }
  const lienBlob = URL.createObjectURL(await reponse.blob());
  const lien = document.createElement("a");
  lien.href = lienBlob;
  lien.download = nom;
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lienBlob), 60_000);
}
/** Copie d'archive du bon (Qté livrée remplie), après confirmation de la sortie. */
export function telechargerArchive(id, numero) {
  return telechargerPdf(`/api/sorties/${id}/pdf/`, `${numero}-archive.pdf`);
}

// ---------- Retours (Agent Logistique) : bons de retour, le stock remonte (12/10/2026) ----------
export function listerRetours({ onglet = "attendu", page = 1 } = {}) {
  return lire(`/api/retours/?${new URLSearchParams({ onglet, page })}`);
}
export function lireRetour(id) {
  return lire(`/api/retours/${id}/`);
}
/** Prépare le bon de retour (ce qui reste à rendre), signé au stylo par l'Agent Logistique. */
export function creerBonRetour(id, signature) {
  return envoyer(`/api/retours/${id}/bon/`, signature);
}
export function annulerBonRetour(bonId) {
  return envoyer(`/api/retours/bons/${bonId}/annuler/`);
}
/** donnees : { date_retour, magasinier, rendu_par, observation, lignes: [{ id, etats } | { id, exemplaires }] } */
export function confirmerRetour(bonId, donnees) {
  return envoyer(`/api/retours/bons/${bonId}/confirmer/`, donnees);
}
/** Bon de retour (ou sa copie d'archive une fois confirmé). */
export function telechargerBonRetour(bonId, nom) {
  return telechargerPdf(`/api/retours/bons/${bonId}/pdf/`, `${nom}.pdf`);
}

// ---------- Écran « Comptes » (administrateur) ----------
export function listerComptes() {
  return lire("/api/comptes/");
}
export function creerCompte(donnees) {
  return envoyer("/api/comptes/", donnees);
}
export function modifierCompte(id, donnees) {
  return envoyer(`/api/comptes/${id}/`, donnees, "PATCH");
}
export function activerCompte(id, actif) {
  return envoyer(`/api/comptes/${id}/activer/`, { actif });
}
export function changerMotDePasse(id, mot_de_passe) {
  return envoyer(`/api/comptes/${id}/mot-de-passe/`, { mot_de_passe });
}
export function deconnecterCompte(id) {
  return envoyer(`/api/comptes/${id}/deconnecter/`);
}
/** Retire la signature scannée enregistrée dans un compte (administrateur, 15/10/2026). */
export function retirerSignatureCompte(id) {
  return envoyer(`/api/comptes/${id}/signature/`, undefined, "DELETE");
}

// ---------- Générer Rapports et Historique (Agent Logistique, 15/10/2026) ----------
/** Réglages d'un écran → paramètres de l'adresse (les valeurs vides ne sont pas envoyées). */
function parametres(reglages = {}) {
  const p = new URLSearchParams();
  Object.entries(reglages).forEach(([k, v]) => { if (v !== "" && v != null && v !== false) p.set(k, v); });
  return p;
}
/** Télécharge un fichier (PDF, Excel) sous le nom donné par le serveur. */
async function telechargerFichier(url, nomParDefaut) {
  const reponse = await appel(url);
  if (!reponse.ok) {
    const corps = await reponse.json().catch(() => ({}));
    throw new Error(corps.general?.[0] ?? `Erreur ${reponse.status}`);
  }
  const nom = (reponse.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/)?.[1] || nomParDefaut;
  const lienBlob = URL.createObjectURL(await reponse.blob());
  const lien = document.createElement("a");
  lien.href = lienBlob;
  lien.download = nom;
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lienBlob), 60_000);
}
/** Les six rapports (cartes de l'écran) et les listes des filtres. */
export function lireCatalogueRapports() {
  return lire("/api/rapports/");
}
export function lireRapport(cle, reglages) {
  return lire(`/api/rapports/${cle}/?${parametres(reglages)}`);
}
/** fichier : "pdf" ou "xlsx" */
export function telechargerRapport(cle, reglages, fichier) {
  return telechargerFichier(`/api/rapports/${cle}/?${parametres({ ...reglages, fichier })}`, `${cle}.${fichier}`);
}
export function lireHistorique(reglages) {
  return lire(`/api/historique/?${parametres(reglages)}`);
}
export function exporterHistorique(reglages, fichier) {
  const { page, ...filtres } = reglages; // eslint-disable-line no-unused-vars
  return telechargerFichier(`/api/historique/export/?${parametres({ ...filtres, fichier })}`, `historique.${fichier}`);
}

// ---------- Comptes ----------
/** Qui est connecté ? Renvoie { connecte: false } ou les informations du compte. */
/** Nombres affichés sur le menu : demandes à valider (Agent Logistique), réquisitions à viser (Responsable). */
export function lireCompteurs() {
  return lire("/api/compteurs/");
}
/** À appeler après une validation, un visa ou un refus : le menu met ses compteurs à jour tout de suite. */
export function signalerChangement() {
  window.dispatchEvent(new Event("gestistock:compteurs"));
}
/** Écran « Tableau de bord » : cartes chiffrées, articles à réapprovisionner, activité du jour (12/10/2026). */
export function lireTableauDeBord() {
  return lire("/api/tableau-de-bord/");
}
export function lireSession() {
  return lire("/api/session/");
}
export function seConnecter(identifiant, mot_de_passe) {
  return envoyer("/api/connexion/", { identifiant, mot_de_passe });
}
export function seDeconnecter() {
  return envoyer("/api/deconnexion/");
}
