import { useState } from "react";
import Icon from "../icons.jsx";

/** Écran « Aide » (12/10/2026) : tutoriel d'utilisation de GestiStock, pas à pas.
 *  Chaque personne voit les fiches qui la concernent (selon ses rôles) ; « Tout afficher » montre tout. */

const POUR_TOUS = "tous", AGENT = "agent", RESPONSABLE = "responsable", ADMIN = "admin";
const ROLES = {
  [POUR_TOUS]: "Tout le monde",
  [AGENT]: "Agent Logistique",
  [RESPONSABLE]: "Responsable HBC",
  [ADMIN]: "Administrateur",
};

// ecran : entrée du menu ouverte par le bouton « Aller à l'écran ».
const FICHES = [
  {
    id: "connexion", role: POUR_TOUS, icone: "logout", titre: "Se connecter et se déconnecter",
    etapes: [
      "Ouvrez GestiStock dans le navigateur (adresse donnée par le service Informatique).",
      "Tapez votre identifiant (les majuscules n'ont pas d'importance) et votre mot de passe.",
      "Cliquez sur l'œil à droite du mot de passe pour vérifier ce que vous avez tapé.",
      "Cliquez sur « Se connecter ».",
      "Pour partir, cliquez sur « Se déconnecter » en bas du menu, à gauche.",
    ],
    astuces: [
      "Mot de passe oublié : demandez au service Informatique, il vous en donnera un nouveau.",
      "Après 5 essais ratés, il faut patienter 5 minutes.",
      "Un compte ne peut être ouvert que sur un seul appareil à la fois : si vous vous connectez ailleurs, le premier appareil est déconnecté (un message l'explique).",
      "Fermer le navigateur vous déconnecte ; de toute façon la connexion s'arrête après 10 heures.",
    ],
  },
  {
    id: "menu", role: POUR_TOUS, icone: "home", titre: "Se repérer dans GestiStock",
    etapes: [
      "Le menu bleu à gauche donne accès aux écrans. L'écran ouvert est surligné.",
      "En bas du menu : votre nom, votre département et votre rôle.",
      "Une pastille rouge sur une entrée du menu indique combien de choses attendent votre action.",
      "Les écrans marqués « en préparation » ne sont pas encore terminés.",
    ],
  },
  {
    id: "tableau", role: [AGENT, RESPONSABLE], icone: "home", titre: "Lire le Tableau de bord", ecran: "Tableau de bord",
    etapes: [
      "Le Tableau de bord s'ouvre tout seul après la connexion (Agent Logistique et Responsable HBC).",
      "En haut, quatre chiffres : articles sous le seuil, demandes à valider (ou bons à viser pour le Responsable), retours en retard et valeur du stock au magasin.",
      "Cliquez sur un chiffre pour ouvrir l'écran correspondant (par exemple la Liste d'Articles filtrée « Sous le seuil »).",
      "« À réapprovisionner » : les articles épuisés, critiques puis en stock bas. Cliquez sur une ligne pour ouvrir la fiche de l'article.",
      "« Activité du jour » : les entrées, demandes, validations, signatures, sorties et retours d'aujourd'hui, les plus récents en haut.",
    ],
    astuces: [
      "L'écran se met à jour tout seul toutes les 30 secondes.",
      "La valeur du stock = quantité disponible × prix unitaire ; le matériel prêté (dehors) n'est pas compté.",
    ],
  },
  {
    id: "demande", role: POUR_TOUS, icone: "plus", titre: "Faire une demande de matériel", ecran: "Mes demandes",
    etapes: [
      "Menu « Mes demandes », puis le bouton bleu « Nouvelle demande ».",
      "Choisissez le magasin (obligatoire). Le chantier est facultatif.",
      "Dans « Article demandé », cliquez pour voir toute la liste, ou tapez une partie du nom ou du code (sans vous soucier des accents), puis choisissez l'article.",
      "Indiquez la quantité demandée. La quantité disponible est affichée à côté : en rouge si le stock ne suffit pas (la demande reste possible).",
      "Pour un article non consommable (à rendre), indiquez la date de retour prévue.",
      "Ajoutez un motif si besoin, puis « Ajouter un article » pour une autre ligne.",
      "Cochez « Urgent » si c'est pressé, puis cliquez sur « Envoyer la demande ».",
    ],
    astuces: [
      "Ce qui manque ou est à corriger s'affiche en rouge, sous chaque case.",
      "La date et l'heure de la demande sont mises automatiquement.",
      "Envoyer une demande ne retire rien du stock : c'est seulement une demande.",
    ],
  },
  {
    id: "suivi", role: POUR_TOUS, icone: "clip", titre: "Suivre ou annuler ma demande", ecran: "Mes demandes",
    etapes: [
      "Menu « Mes demandes ». Les onglets trient vos demandes : En attente, Validées, Refusées, Toutes.",
      "Cliquez sur une demande pour ouvrir sa fiche à droite.",
      "Le suivi montre les 5 étapes : Envoyée → Validée par la Logistique → Visée par le Responsable → Bon prêt → Remise.",
      "Tant qu'elle est « En attente », vous pouvez cliquer sur « Annuler ma demande ».",
      "Une fois visée, « Voir le bon de réquisition » montre le bon avec les signatures.",
    ],
    astuces: [
      "L'écran se met à jour tout seul toutes les 30 secondes.",
      "Si la demande est refusée, le motif du refus est écrit dans le suivi.",
    ],
  },
  {
    id: "articles", role: POUR_TOUS, icone: "box", titre: "Consulter les articles", ecran: "Liste d'Articles",
    etapes: [
      "Menu « Liste d'Articles » : la liste du stock, 10 articles par page.",
      "Tapez dans « Rechercher un article… » un nom, un code, un n° de série ou un code immo (les accents et majuscules ne comptent pas).",
      "Filtrez par catégorie ou par magasin ; cochez « Sous le seuil seulement » pour voir ce qui manque.",
      "Cliquez sur « Détails » pour ouvrir la fiche de l'article.",
    ],
  },
  {
    id: "valider", role: AGENT, icone: "check", titre: "Valider ou refuser une demande", ecran: "Demandes à valider",
    etapes: [
      "Menu « Demandes à valider » : les demandes urgentes d'abord, puis les plus anciennes.",
      "Cliquez sur une demande et vérifiez chaque article.",
      "Modifiez au besoin la « Qté accordée » (0 = article retiré). La quantité demandée d'origine reste visible.",
      "Pour refuser : « Refuser… », écrivez le motif (il sera montré au demandeur), puis « Refuser la demande ».",
      "Pour valider : « Valider… ». Le n° de réquisition (RM-…) est attribué à ce moment ; le bon s'affiche avec ce n° : relisez-le.",
      "Signez dans le cadre en bas avec la souris (bouton gauche enfoncé), puis « Signer et valider ».",
    ],
    astuces: [
      "La validation crée la réquisition matière (n° RM-…) et vaut votre visa ; elle part ensuite au Responsable HBC.",
      "Vos propres demandes passent par le même circuit : vous pouvez les valider, mais elles vont toujours au Responsable HBC.",
      "Signature ratée : « Effacer », puis recommencez.",
      "Le stock ne baisse pas encore à cette étape.",
    ],
  },
  {
    id: "reception", role: AGENT, icone: "box", titre: "Entrée en stock : enregistrer une livraison", ecran: "Liste d'Articles",
    etapes: [
      "Menu « Liste d'Articles », bouton « Entrée en stock » (en haut à droite).",
      "Indiquez le fournisseur, le n° de facture ou de bon de livraison, la date et le magasin.",
      "Pour chaque article reçu : tapez un bout de son nom ou de son code et choisissez-le, puis la quantité, le prix unitaire (facultatif), l'état (« Neuf » par défaut) et les n° de série s'il y en a.",
      "Cliquez sur « Enregistrer » : le stock augmente aussitôt.",
    ],
    astuces: [
      "Livraison d'un seul article : ouvrez sa fiche et cliquez sur « Entrée en stock » ; l'article est déjà choisi.",
      "Produit jamais reçu auparavant : tapez son nom, puis cliquez sur « ＋ Créer l'article » en bas de la liste. Indiquez la catégorie (le code est créé automatiquement), le type, l'unité, l'emplacement et le seuil d'alerte ; l'article est aussitôt placé sur la ligne de la livraison.",
      "Appareil avec un n° de série (OTDR, soudeuse…) : à la création, choisissez « Non consommable · à rendre » et cochez « Suivi par n° de série ». Le type et ce choix ne peuvent plus être changés ensuite.",
      "État du produit reçu : Neuf, Bon, Moyen ou Mauvais. Tous les états comptent dans la quantité disponible.",
      "Dans la liste, sous l'état du stock, la répartition par état (ex. « 12 Bon · 3 Moyen ») ; le filtre « État » trouve par exemple tous les articles qui ont du matériel en mauvais état.",
    ],
  },
  {
    id: "modifier", role: AGENT, icone: "edit", titre: "Modifier la fiche d'un article", ecran: "Liste d'Articles",
    etapes: [
      "Menu « Liste d'Articles », « Détails » sur la ligne de l'article, puis « Modifier ».",
      "Changez le nom, l'emplacement, le minimum, le prix, le fournisseur…, puis « Enregistrer ».",
    ],
    astuces: ["Le code, le type et la quantité ne se modifient pas ici : la quantité change par les réceptions et les sorties."],
  },
  {
    id: "viser", role: RESPONSABLE, icone: "sign", titre: "Viser (signer) une réquisition", ecran: "Demandes à viser",
    etapes: [
      "Menu « Demandes à viser » : la pastille rouge indique combien de réquisitions attendent votre signature.",
      "Cliquez sur une réquisition : le bon s'ouvre tel qu'il sera imprimé.",
      "Relisez-le, puis signez dans le cadre en bas avec la souris (bouton gauche enfoncé).",
      "Cliquez sur « Signer ». Votre nom, la date et l'heure sont ajoutés automatiquement.",
      "Pour refuser : « Refuser… », écrivez le motif, puis « Refuser la réquisition ».",
    ],
    astuces: ["Le motif du refus est montré à la Logistique et au demandeur."],
  },
  {
    id: "imprimer", role: AGENT, icone: "doc", titre: "Imprimer le bon de réquisition", ecran: "Liste Réquisitions",
    etapes: [
      "Menu « Liste Réquisitions », onglet « À imprimer » : les bons signés par vous et par le Responsable HBC. La pastille rouge les compte.",
      "Cliquez sur « Voir le bon » pour le relire.",
      "En bas de l'aperçu : « Imprimer » ouvre la fenêtre d'impression (format A4) ; « Télécharger le PDF » l'enregistre (fichier RM-2026-0001.pdf, par exemple).",
      "Portez le bon imprimé au magasin.",
      "Le magasinier remplit la « Qté livrée » et signe ; le demandeur signe à la réception du matériel.",
    ],
    astuces: [
      "Votre première impression (ou votre premier téléchargement) fait passer le bon dans l'onglet « Imprimées », avec la date, l'heure et votre nom.",
      "Vous pouvez le réimprimer ou le retélécharger autant de fois que nécessaire : chaque fois est noté.",
      "Les articles retirés à la validation (quantité 0) ne figurent pas sur le bon.",
    ],
  },
  {
    id: "sortie", role: AGENT, icone: "out", titre: "Confirmer la sortie (matériel remis)", ecran: "Sorties de stock",
    etapes: [
      "Quand le bon signé par le magasinier revient, ouvrez le menu « Sorties de stock », onglet « À confirmer ». La pastille rouge compte les bons en attente.",
      "Cliquez sur « Confirmer la sortie » à droite du bon.",
      "Recopiez, pour chaque article, la « Qté livrée » écrite par le magasinier (0 si rien n'a été remis). Si tout a été livré, le lien « Tout a été livré comme sur le bon » remplit les cases.",
      "Recopiez aussi la colonne « État » : si le stock de l'article a plusieurs états (ex. Bon et Moyen), indiquez combien de chaque état est sorti.",
      "Matériel avec n° de série : cochez les n° de série remis (leur état est affiché à côté).",
      "Vérifiez la date de remise, écrivez au besoin le nom du magasinier et une observation.",
      "Cliquez sur « Confirmer la sortie… », relisez, puis « Oui, confirmer la sortie ». Le stock diminue aussitôt.",
    ],
    astuces: [
      "Le bon apparaît dans « Sorties de stock » dès que vous l'avez imprimé (écran « Liste Réquisitions »).",
      "La sortie ne peut pas être confirmée deux fois, ni annulée dans GestiStock : vérifiez bien les quantités.",
      "Après confirmation, « Copie d'archive (PDF) » donne le bon avec la colonne « Qté livrée » remplie.",
      "Le demandeur voit l'étape « Remise » cochée dans « Mes demandes ».",
    ],
  },
  {
    id: "retour", role: AGENT, icone: "back", titre: "Enregistrer un retour de matériel", ecran: "Retours de stock",
    etapes: [
      "Menu « Retours de stock », onglet « Matériel attendu » : le matériel prêté sorti et pas encore rentré (jamais les consommables). Les retards sont en rouge ; la pastille du menu les compte.",
      "Quand le demandeur rapporte le matériel, cliquez sur « Préparer le bon de retour », signez dans le cadre, puis « Signer et préparer le bon » : le BON DE RETOUR (BR-…) se télécharge avec tout ce qui reste à rendre. Imprimez-le.",
      "Au magasin, le magasinier remplit à la main « Qté rendue » et « État au retour » ; le demandeur et lui signent.",
      "Au retour du bon, cliquez sur « Confirmer le retour ». Recopiez, pour chaque ligne, combien sont rendus dans chaque état (Neuf, Bon, Moyen, Mauvais) ; pour le matériel avec n° de série, cochez les n° rendus et choisissez leur état.",
      "Cliquez sur « Confirmer le retour… », relisez, puis « Oui, confirmer le retour ». Le stock remonte et l'état est mis à jour.",
    ],
    astuces: [
      "Retour partiel : confirmez seulement ce qui est rendu. Le reste reste attendu ; le bon suivant (BR-…) ne listera que lui.",
      "Si le matériel n'est pas venu, « Annuler ce bon… » libère la réquisition pour préparer un autre bon.",
      "Après confirmation, la « Copie d'archive » du bon de retour garde les colonnes remplies.",
    ],
  },
  {
    id: "bons", role: RESPONSABLE, icone: "doc", titre: "Consulter les bons signés", ecran: "Liste Réquisitions",
    etapes: [
      "Menu « Liste Réquisitions » : tous les bons signés par la Logistique et par vous.",
      "La colonne « Impression » indique si l'Agent Logistique a déjà imprimé le bon, quand, et combien de fois il a été téléchargé.",
      "« Voir le bon » pour le consulter ; en bas de l'aperçu, « Imprimer » ou « Télécharger le PDF ».",
    ],
    astuces: ["Votre impression ou téléchargement est une simple consultation : il ne fait pas passer le bon en « Imprimée »."],
  },
  {
    id: "comptes", role: ADMIN, icone: "users", titre: "Créer et gérer les comptes", ecran: "Comptes",
    etapes: [
      "Menu « Comptes », bouton « Nouveau compte ».",
      "Identifiant (sans accent ni espace), département, prénom et nom (imprimés sur le bon), mot de passe provisoire.",
      "Cochez « Agent Logistique » et/ou « Responsable HBC » si besoin. Sans case cochée, la personne peut faire des demandes.",
      "« Modifier » sur un compte : changer le mot de passe, déconnecter l'appareil, désactiver ou réactiver le compte.",
    ],
    astuces: [
      "Donnez à la personne son identifiant et son mot de passe provisoire.",
      "Départements et chantiers se gèrent dans l'administration (lien « Administration » du menu).",
    ],
  },
];

function rolesDe(compte) {
  const r = [POUR_TOUS];
  if (compte?.agent_logistique) r.push(AGENT);
  if (compte?.responsable) r.push(RESPONSABLE);
  if (compte?.administrateur) r.push(ADMIN);
  return r;
}

/** Une fiche peut concerner plusieurs rôles (ex. le Tableau de bord : Agent Logistique et Responsable HBC). */
function pourMoi(fiche, mesRoles) {
  return [].concat(fiche.role).some((r) => mesRoles.includes(r));
}

export default function Aide({ compte, allerA, ecransDuMenu = [] }) {
  const mesRoles = rolesDe(compte);
  const [tout, setTout] = useState(false);
  const fiches = FICHES.filter((f) => tout || pourMoi(f, mesRoles));
  const autres = FICHES.length - FICHES.filter((f) => pourMoi(f, mesRoles)).length;

  function voir(id) {
    document.getElementById(`aide-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <>
      <header className="top"><h1>Aide : utiliser GestiStock</h1></header>
      <div className="body aide">
        <div className="card aide-intro">
          <p>
            Voici, pas à pas, comment utiliser GestiStock. Cliquez sur un sujet pour y aller directement.
            {autres > 0 && !tout && " Seuls les sujets qui vous concernent sont affichés."}
          </p>
          <nav className="aide-sommaire" aria-label="Sujets de l'aide">
            {fiches.map((f) => (
              <button key={f.id} type="button" className="btn" onClick={() => voir(f.id)}>
                <Icon name={f.icone} size={18} />{f.titre}
              </button>
            ))}
          </nav>
          {autres > 0 && (
            <button type="button" className="btn lien" onClick={() => setTout(!tout)}>
              {tout ? "N'afficher que les sujets qui me concernent" : `Tout afficher (${autres} sujet${autres > 1 ? "s" : ""} pour d'autres rôles)`}
            </button>
          )}
        </div>

        {fiches.map((f) => (
          <section key={f.id} id={`aide-${f.id}`} className="card aide-fiche">
            <div className="aide-fiche-tete">
              <span className="aide-icone"><Icon name={f.icone} size={22} /></span>
              <h2>{f.titre}</h2>
              <span className="pill p-i">{[].concat(f.role).map((r) => ROLES[r]).join(" · ")}</span>
            </div>
            <ol className="aide-etapes">
              {f.etapes.map((e, i) => <li key={i}>{e}</li>)}
            </ol>
            {f.astuces && (
              <div className="aide-astuces">
                <b>Bon à savoir</b>
                <ul>{f.astuces.map((a, i) => <li key={i}>{a}</li>)}</ul>
              </div>
            )}
            {f.ecran && ecransDuMenu.includes(f.ecran) && (
              <button type="button" className="btn pri" onClick={() => allerA?.(f.ecran)}>
                Aller à l'écran « {f.ecran} »
              </button>
            )}
          </section>
        ))}
      </div>
    </>
  );
}
