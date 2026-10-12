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

export function listerArticles({ page = 1, q = "", categorie = "", magasin = "", sousSeuil = false } = {}) {
  const params = new URLSearchParams({ page });
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
/** lignes : [{ id, qte_accordee }] ; signature : image du stylo électronique – valide et crée la réquisition matière. */
export function validerDemande(id, lignes, signature) {
  return envoyer(`/api/a-valider/${id}/valider/`, { lignes, signature });
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
/** signature : image du stylo électronique (« data:image/png;base64,… »). */
export function viserRequisition(id, signature) {
  return envoyer(`/api/a-viser/${id}/viser/`, { signature });
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
export function lireSession() {
  return lire("/api/session/");
}
export function seConnecter(identifiant, mot_de_passe) {
  return envoyer("/api/connexion/", { identifiant, mot_de_passe });
}
export function seDeconnecter() {
  return envoyer("/api/deconnexion/");
}
