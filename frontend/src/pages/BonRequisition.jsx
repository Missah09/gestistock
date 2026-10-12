import logoHbc from "../assets/logo-hbc.png";
import { date, dateHeure, etatsDisponibles, quantite, texteEtats } from "../format.js";

const jour = (iso) => (iso ? dateHeure(iso).split(" à ")[0] : "");

/** Une case de visa électronique (Agent Logistique ou Responsable HBC). */
function CaseVisa({ titre, visa, enCours }) {
  return (
    <div className={`bon-case${enCours ? " a-signer" : ""}`}>
      <div className="bon-case-titre">{titre}</div>
      <div className="bon-case-ligne"><span>Nom :</span> <b>{visa?.nom ?? ""}</b></div>
      <div className="bon-case-signature">
        {visa?.image ? <img src={visa.image} alt={`Signature de ${visa.nom}`} />
          : visa?.le ? <span className="bon-attente">Visé (avant la signature au stylo)</span>
          : enCours ? <span className="bon-attente">Votre signature apparaîtra ici</span>
          : <span className="bon-attente">En attente</span>}
      </div>
      <div className="bon-case-ligne petit">{visa?.le ? `Visé électroniquement le ${dateHeure(visa.le)}` : " "}</div>
    </div>
  );
}

/** Une case à remplir à la main (Demandeur, Magasinier). */
function CaseMain({ titre, nom, date }) {
  return (
    <div className="bon-case">
      <div className="bon-case-titre">{titre}</div>
      <div className="bon-case-ligne"><span>Nom :</span> <b>{nom ?? ""}</b></div>
      <div className="bon-case-signature main"><span>Signature :</span></div>
      <div className="bon-case-ligne petit"><span>Date :</span> {date ?? ""}</div>
    </div>
  );
}

/** Aperçu du bon de réquisition de matières, d'après le modèle papier HBC (maquette validée le 11/10/2026).
 *  d : la demande ; quantites : {idLigne: quantité retenue} (sinon la quantité accordée, sinon demandée) ;
 *  visas : { agent: {nom, le, image}, responsable: {nom, le, image} } ; aSigner : "agent" | "responsable" (case en cours). */
export default function BonRequisition({ d, quantites, numero, visas = {}, aSigner, dateBon }) {
  const r = d.requisition;
  const lignes = d.lignes
    .map((l) => ({ ...l, qte: quantites?.[l.id] ?? l.qte_accordee ?? l.quantite }))
    .filter((l) => Number(l.qte) > 0); // article retiré (0) : il ne figure pas sur le bon
  return (
    <div className="bon" aria-label="Bon de réquisition de matières">
      <div className="bon-tete">
        <img src={logoHbc} alt="HBC" className="bon-logo" />
        <div className="bon-titre">BON DE RÉQUISITION DE MATIÈRES</div>
        <div className="bon-numero"><span>N°</span> <b>{r?.numero ?? numero ?? (d.numero_requisition || "attribué à la validation")}</b></div>
      </div>

      <div className="bon-section">1. Informations générales</div>
      <div className="bon-infos">
        <div><span>Date :</span> <b>{jour(r?.visa_agent_le ?? dateBon)}</b></div>
        <div><span>Projet (ou chantier) :</span> <b>{d.chantier || d.travail || "—"}</b></div>
        <div><span>Service demandeur :</span> <b>{d.demandeur_departement || "—"}</b></div>
        <div><span>Nature des travaux :</span> <span className="bon-pointilles" /></div>
      </div>

      <div className="bon-section">2. Liste des articles</div>
      <table className="bon-table">
        <thead>
          <tr><th>N°</th><th>Code article</th><th>Désignation</th><th>Catégorie</th><th>Qté demandée</th><th>Qté livrée</th><th>État</th><th>Motif</th></tr>
        </thead>
        <tbody>
          {lignes.map((l, i) => (
            <tr key={l.id}>
              <td className="centre">{i + 1}</td><td>{l.article.code}</td><td>{l.article.nom}</td><td>{l.article.categorie}</td>
              <td className="centre"><b>{quantite(Number(l.qte), l.article.unite)}</b></td>
              <td className="centre">{r?.sortie ? quantite(r.sortie.lignes[l.id]?.qte_livree ?? 0, l.article.unite) : ""}</td>
              <td>{r?.sortie ? texteEtats(r.sortie.lignes[l.id]?.etats) : etatsDisponibles(l.article.etats)}</td><td>{l.motif}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="bon-note">{r?.sortie
        ? `Qté livrée et État : recopiés du bon signé par le magasinier. Matériel remis le ${date(r.sortie.date_remise)}${r.sortie.magasinier ? ` par ${r.sortie.magasinier}` : ""}.`
        : "Qté livrée : à remplir à la main par le magasinier lors de la remise du matériel. État : d'après la fiche article (à corriger à la main si besoin)."}</p>

      <div className="bon-section">3. Visas et signatures</div>
      <div className="bon-visas">
        <CaseMain titre="Demandeur" nom={d.demandeur} date={jour(d.cree_le)} />
        <CaseVisa titre="Agent Logistique" visa={visas.agent} enCours={aSigner === "agent"} />
        <CaseVisa titre="Responsable HBC" visa={visas.responsable} enCours={aSigner === "responsable"} />
        <CaseMain titre="Magasinier" nom={r?.sortie?.magasinier} date={r?.sortie ? date(r.sortie.date_remise) : undefined} />
      </div>
      <div className="bon-pied">GestiStock – Demande {d.numero} – aperçu à l'écran</div>
    </div>
  );
}

/** Les visas déjà posés sur la réquisition (noms, dates et images des signatures). */
export function visasDe(d) {
  const r = d.requisition;
  if (!r) return {};
  const v = {
    agent: { nom: r.visa_agent, le: r.visa_agent_le, image: r.signature_agent ? `/api/requisitions/${d.id}/signature/agent/` : null },
  };
  if (r.statut === "VISEE") {
    v.responsable = { nom: r.visa_responsable, le: r.visa_responsable_le,
      image: r.signature_responsable ? `/api/requisitions/${d.id}/signature/responsable/` : null };
  }
  return v;
}
