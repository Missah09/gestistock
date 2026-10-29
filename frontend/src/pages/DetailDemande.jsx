import { useEffect, useState } from "react";
import { annulerDemande } from "../api.js";
import { date, dateHeure, ETATS, manque, quantite, LIBELLE_PRETE, ETATS_UTILISABLES, texteEtats } from "../format.js";
import EtatsProduit from "../EtatsProduit.jsx";
import { statutAffiche } from "./TableauDemandes.jsx";
import Icon from "../icons.jsx";
import FenetreBon from "./FenetreBon.jsx";

export function Champ({ libelle, children, large, aide }) {
  return (
    <div className={`champ${large ? " large" : ""}`}>
      <span>{libelle}</span>
      <b>{children ?? "—"}</b>
      {aide && <small>{aide}</small>}
    </div>
  );
}

/** Suivi en 5 étapes : Envoyée → Validée par le Responsable Technique → Visée par le Responsable Logistique → Bon prêt → Remise. */
export function Suivi({ d, vueAgent = false }) {
  const r = d.requisition;
  const parQui = (nom) => (nom ? ` par ${nom}` : "");
  const validation = {
    EN_ATTENTE: ["encours", "En attente du Responsable Technique"],
    VALIDEE: ["fait", `${d.traitee_le ? dateHeure(d.traitee_le) : ""}${parQui(d.traitee_par)}`],
    REFUSEE: ["refus", `Refusée${parQui(d.traitee_par)}${d.motif_refus ? ` : ${d.motif_refus}` : ""}`],
    ANNULEE: ["refus", vueAgent ? "Annulée par le demandeur" : "Annulée par vous"],
  }[d.statut];
  let visa = ["attente", ""];
  if (r?.statut === "ATTENTE_VISA") visa = ["encours", "En attente du visa"];
  else if (r?.statut === "VISEE") visa = ["fait", `${r.visa_responsable_le ? dateHeure(r.visa_responsable_le) : ""}${parQui(r.visa_responsable)}`];
  else if (r?.statut === "REFUSEE") visa = ["refus", `Refusée${r.motif_refus ? ` : ${r.motif_refus}` : ""}`];
  const visee = r?.statut === "VISEE";
  const etapes = [
    ["fait", "Envoyée", dateHeure(d.cree_le)],
    [validation[0], "Validée par le Responsable Technique", validation[1]],
    [visa[0], "Visée par le Responsable Logistique", visa[1]],
    r?.imprimee_le
      ? ["fait", "Bon prêt", `Imprimé le ${dateHeure(r.imprimee_le)}${parQui(r.imprimee_par)}`]
      : [visee ? "encours" : "attente", "Bon prêt", visee ? "Bon de réquisition à imprimer" : ""],
    r?.sortie
      ? ["fait", "Remise", `Matériel remis le ${date(r.sortie.date_remise)}`]
      : [r?.imprimee_le ? "encours" : "attente", "Remise", r?.imprimee_le ? "Bon porté au magasin" : ""],
  ];
  return (
    <ol className="suivi cinq">
      {etapes.map(([etat, titre, detail], i) => (
        <li key={titre} className={etat}>
          <span className="rond">{etat === "fait" ? "✓" : etat === "refus" ? "✕" : i + 1}</span>
          <b>{titre}</b>
          {detail && <small>{detail}</small>}
        </li>
      ))}
    </ol>
  );
}

/** Bloc « La demande » (vue Responsable Technique : avec le demandeur et son service). */
export function BlocDemande({ d, vueAgent = false }) {
  return (
    <section className="bloc">
      <h3>La demande</h3>
      <div className="champs">
        {vueAgent && <Champ libelle="Demandeur">{d.demandeur || "—"}</Champ>}
        {vueAgent && (
          <Champ libelle="Service demandeur" aide={d.demandeur_departement ? undefined : "Département à renseigner sur le compte (administration)."}>
            {d.demandeur_departement || "—"}
          </Champ>
        )}
        <Champ libelle="Magasin">{d.magasin}</Champ>
        <Champ libelle="Chantier">{d.chantier || d.travail || "—"}</Champ>
        <Champ libelle="Date de la demande" large>{dateHeure(d.cree_le)}</Champ>
      </div>
    </section>
  );
}

/** Fiche d'un article demandé. `accorde` : contenu de la case « Qté accordée » (saisie pour le Responsable Technique). */
export function BlocArticle({ l, accorde, livree }) {
  const a = l.article;
  const insuffisant = manque(l.quantite, a.qte_disponible);
  const etat = ETATS[a.etat];
  return (
    <section className="bloc">
      <h3>{a.nom}</h3>
      <div className="champs">
        <Champ libelle="Code article"><span className="code">{a.code}</span></Champ>
        <Champ libelle="Catégorie">{a.categorie}</Champ>
        <Champ libelle="Type">{a.type === "PRETE" ? <span className="pill p-i">{LIBELLE_PRETE}</span> : "Consommable"}</Champ>
        <Champ libelle={a.modele ? "Modèle" : "Emplacement"}>{a.modele ? [a.marque, a.modele].filter(Boolean).join(" ") : a.emplacement}</Champ>
        <Champ libelle="Qté demandée">{quantite(l.quantite, a.unite)}</Champ>
        <Champ libelle="Qté disponible">
          <span className={insuffisant ? "rouge" : "vert"}>{quantite(a.qte_disponible, a.unite)}</span>
          {insuffisant && <> <span className="pill p-c">{insuffisant}</span></>}
        </Champ>
        {l.date_retour_prevue ? (
          <Champ libelle="Retour prévu">{date(l.date_retour_prevue)}</Champ>
        ) : (
          <Champ libelle="Retour prévu" aide={a.type === "PRETE" ? undefined : "Produit consommable : il ne revient pas au magasin."}>
            {a.type === "PRETE" ? "—" : "Sans objet"}
          </Champ>
        )}
        <Champ libelle="Motif">{l.motif || "—"}</Champ>
        <Champ libelle="État du stock"><span className={`pill ${etat.classe}`}>{etat.libelle}</span></Champ>
        <Champ libelle="Minimum">{quantite(a.qte_minimale, a.unite)}</Champ>
        {a.etats && (
          <Champ libelle="État du produit disponible" large>
            <EtatsProduit etats={a.etats} unite={a.unite} seulement={ETATS_UTILISABLES} vide="Rien de disponible" />
          </Champ>
        )}
        {accorde ?? (l.qte_accordee !== null && <Champ libelle="Qté accordée" large={!livree}>{quantite(l.qte_accordee, a.unite)}</Champ>)}
        {livree && (
          <Champ libelle="Qté remise par le magasin" aide={livree.exemplaires.length ? `N° de série : ${livree.exemplaires.join(", ")}` : undefined}>
            {quantite(livree.qte_livree, a.unite)}
            {texteEtats(livree.etats) && <span className="discret"> ({texteEtats(livree.etats)})</span>}
          </Champ>
        )}
      </div>
    </section>
  );
}

/** Bloc « Réquisition matière » (après validation).
 *  avecEmail : montre l'état de l'email au Responsable Logistique ; onRenvoyer : bouton « Renvoyer l'email » (Responsable Technique). */
export function BlocRequisition({ r, avecEmail = false, onRenvoyer, renvoiEnCours = false }) {
  if (!r) return null;
  const etape = { ATTENTE_VISA: "En attente du visa du Responsable Logistique", VISEE: "Visée par le Responsable Logistique",
    REFUSEE: "Refusée par le Responsable Logistique" }[r.statut] ?? r.statut_libelle;
  const emailOk = r.email_envoye_le && r.email_etat?.startsWith("Email envoyé");
  return (
    <section className="bloc">
      <h3>Réquisition matière</h3>
      <div className="champs">
        <Champ libelle="N° de réquisition"><span className="code">{r.numero}</span></Champ>
        <Champ libelle="Étape">{etape}</Champ>
        <Champ libelle="Visa du Responsable Technique" large>
          {r.visa_agent} <span className="discret">· visé électroniquement le {dateHeure(r.visa_agent_le)}</span>
        </Champ>
        {r.statut === "VISEE" && (
          <Champ libelle="Visa du Responsable Logistique" large>
            {r.visa_responsable} <span className="discret">· visé électroniquement le {dateHeure(r.visa_responsable_le)}</span>
          </Champ>
        )}
        {r.statut === "REFUSEE" && (
          <Champ libelle="Refus du Responsable Logistique" large>
            {r.motif_refus || "—"} <span className="discret">· {r.visa_responsable}, le {dateHeure(r.visa_responsable_le)}</span>
          </Champ>
        )}
        {avecEmail && r.statut === "ATTENTE_VISA" && (
          <div className="champ large">
            <span>Email au Responsable Logistique</span>
            <b className={emailOk ? "vert" : "a-completer"}>
              {r.email_etat || "Pas encore envoyé."}{emailOk && <span className="discret"> ({dateHeure(r.email_envoye_le)})</span>}
            </b>
            {onRenvoyer && (
              <button type="button" className="btn petit-btn" disabled={renvoiEnCours} onClick={onRenvoyer}>
                {renvoiEnCours ? "Envoi…" : "Renvoyer l'email"}
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/** Panneau latéral d'une demande (vue du demandeur). */
export default function DetailDemande({ demande: d, onFermer, onAnnulee }) {
  const [confirmer, setConfirmer] = useState(false);
  const [voirBon, setVoirBon] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState(null);
  const statut = statutAffiche(d);

  useEffect(() => { setConfirmer(false); setErreur(null); }, [d.id]);
  useEffect(() => {
    const touche = (e) => e.key === "Escape" && !envoi && onFermer();
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi]);

  async function annuler() {
    setEnvoi(true); setErreur(null);
    try {
      const r = await annulerDemande(d.id);
      onAnnulee(r.message);
    } catch (err) {
      setErreur(err.details?.general?.[0] ?? "L'annulation a échoué. Vérifiez que le serveur est démarré.");
      setEnvoi(false);
    }
  }

  return (
    <>
      <div className="voile" onClick={() => !envoi && onFermer()} />
      <aside className="fiche" role="dialog" aria-modal="true" aria-label={`Demande ${d.numero}`}>
        <div className="fiche-tete">
          <div>
            <h2>Demande {d.numero}</h2>
            <div className="meta">
              <span className={`pill ${statut.classe}`}>{statut.libelle}</span>
              {d.urgent && <span className="pill p-c">Urgent</span>}
              <span className="discret">{d.lignes.length} article{d.lignes.length > 1 ? "s" : ""}</span>
            </div>
          </div>
          <button className="fermer" type="button" onClick={onFermer} aria-label="Fermer"><Icon name="x" size={22} stroke={2.2} /></button>
        </div>

        <div className="fiche-corps">
          {erreur && <div className="alerte">{erreur}</div>}
          <section className="bloc">
            <h3>Suivi</h3>
            <Suivi d={d} />
          </section>

          <BlocDemande d={d} />
          <BlocRequisition r={d.requisition} />
          {d.statut === "REFUSEE" && d.motif_refus && (
            <section className="bloc"><h3>Motif du refus</h3><div className="champs"><Champ libelle="Refusée par le Responsable Technique" large>{d.motif_refus}</Champ></div></section>
          )}
          {d.lignes.map((l) => <BlocArticle key={l.id} l={l} livree={d.requisition?.sortie?.lignes[l.id]} />)}
        </div>

        <div className="fiche-pied">
          {d.statut === "EN_ATTENTE" && !confirmer && (
            <button className="btn danger" type="button" onClick={() => setConfirmer(true)}>Annuler ma demande</button>
          )}
          {confirmer && (
            <>
              <span className="question">Annuler cette demande ?</span>
              <button className="btn" type="button" disabled={envoi} onClick={() => setConfirmer(false)}>Non, la garder</button>
              <button className="btn danger plein" type="button" disabled={envoi} onClick={annuler}>
                {envoi ? "Annulation…" : "Oui, annuler"}
              </button>
            </>
          )}
          {d.requisition && !confirmer && (
            <button className="btn" type="button" onClick={() => setVoirBon(true)}><Icon name="doc" size={18} />Voir le bon de réquisition</button>
          )}
          <span className="sp" />
          <button className="btn" type="button" onClick={onFermer} disabled={envoi}>Fermer</button>
        </div>
      </aside>
      {voirBon && d.requisition && <FenetreBon d={d} titre={`Bon de réquisition ${d.requisition.numero}`} onFermer={() => setVoirBon(false)} />}
    </>
  );
}
