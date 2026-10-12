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
      "Pour valider : « Valider… ». Le bon de réquisition s'affiche : relisez-le.",
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
    id: "reception", role: AGENT, icone: "box", titre: "Enregistrer une réception de produits", ecran: "Liste d'Articles",
    etapes: [
      "Menu « Liste d'Articles », bouton « Enregistrer des produits ».",
      "Indiquez le fournisseur, le n° de facture ou de bon de livraison, la date et le magasin.",
      "Pour chaque article reçu : l'article, la quantité, le prix unitaire (facultatif) et les n° de série s'il y en a.",
      "Cliquez sur « Enregistrer » : le stock augmente aussitôt.",
    ],
    astuces: ["Un article qui n'existe pas encore doit d'abord être créé par l'administrateur (service Informatique)."],
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
      "« Voir le bon » pour le relire ; « Télécharger le PDF » pour l'enregistrer (fichier RM-2026-0001.pdf, par exemple).",
      "Ouvrez le PDF et imprimez-le (format A4), puis portez le bon au magasin.",
      "Le magasinier remplit la « Qté livrée » et signe ; le demandeur signe à la réception du matériel.",
    ],
    astuces: [
      "Votre premier téléchargement fait passer le bon dans l'onglet « Imprimées », avec la date, l'heure et votre nom.",
      "Vous pouvez le retélécharger autant de fois que nécessaire : chaque téléchargement est noté.",
      "Les articles retirés à la validation (quantité 0) ne figurent pas sur le bon.",
    ],
  },
  {
    id: "sortie", role: AGENT, icone: "out", titre: "Confirmer la sortie (matériel remis)", ecran: "Sorties de stock",
    etapes: [
      "Quand le bon signé par le magasinier revient, ouvrez le menu « Sorties de stock », onglet « À confirmer ». La pastille rouge compte les bons en attente.",
      "Cliquez sur « Confirmer la sortie » à droite du bon.",
      "Recopiez, pour chaque article, la « Qté livrée » écrite par le magasinier (0 si rien n'a été remis). Si tout a été livré, le lien « Tout a été livré comme sur le bon » remplit les cases.",
      "Matériel avec n° de série : cochez les n° de série remis.",
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
    id: "bons", role: RESPONSABLE, icone: "doc", titre: "Consulter les bons signés", ecran: "Liste Réquisitions",
    etapes: [
      "Menu « Liste Réquisitions » : tous les bons signés par la Logistique et par vous.",
      "La colonne « Impression » indique si l'Agent Logistique a déjà imprimé le bon, quand, et combien de fois il a été téléchargé.",
      "« Voir le bon » ou « Télécharger le PDF » pour le consulter.",
    ],
    astuces: ["Votre téléchargement est une simple consultation : il ne fait pas passer le bon en « Imprimée »."],
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

export default function Aide({ compte, allerA, ecransDuMenu = [] }) {
  const mesRoles = rolesDe(compte);
  const [tout, setTout] = useState(false);
  const fiches = FICHES.filter((f) => tout || mesRoles.includes(f.role));
  const autres = FICHES.length - FICHES.filter((f) => mesRoles.includes(f.role)).length;

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
              <span className="pill p-i">{ROLES[f.role]}</span>
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
