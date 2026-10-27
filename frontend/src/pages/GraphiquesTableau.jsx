import { useState } from "react";
import { montant, montantCourt, quantite } from "../format.js";

/** Graphiques du Tableau de bord (16/10/2026), sous les 4 cartes chiffrées :
 *  1. Top des sorties (articles les plus remis, 30 derniers jours) ;
 *  2. Entrées et sorties par jour (14 derniers jours) ;
 *  3. Valeur du stock par catégorie.
 *  Dessinés en HTML/CSS (aucune bibliothèque) ; chaque barre donne le détail au survol. */

const JOURS = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];
const jourCourt = (iso) => { const [, m, j] = iso.split("-"); return `${j}/${m}`; };
const jourLong = (iso) => { const d = new Date(`${iso}T12:00:00`); return `${JOURS[d.getDay()]} ${jourCourt(iso)}`; };
const pluriel = (n, mot) => `${n} ${mot}${n > 1 ? "s" : ""}`;

/** Graduations « rondes » d'un axe qui part de 0 (au moins 1). */
function graduations(max) {
  const m = Math.max(1, max);
  const pas = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000].find((p) => m / p <= 4) ?? Math.ceil(m / 4);
  const haut = Math.ceil(m / pas) * pas;
  const ticks = [];
  for (let v = 0; v <= haut; v += pas) ticks.push(v);
  return { haut, ticks };
}

/** Barres horizontales : libellé à gauche, barre, valeur écrite au bout. */
function BarresHorizontales({ lignes, classe, onClic }) {
  const max = Math.max(...lignes.map((l) => l.valeur), 1);
  return (
    <ul className="gr-barres">
      {lignes.map((l) => (
        <li key={l.cle} className={onClic && l.id ? "cliquable" : undefined} title={l.aide}
          onClick={onClic && l.id ? () => onClic(l.id) : undefined}>
          <span className="gr-libelle" title={l.libelle}>{l.libelle}</span>
          <span className="gr-piste">
            <span className={`gr-barre ${l.autres ? "autres" : classe}`} style={{ width: `${Math.max(2, (l.valeur / max) * 100)}%` }} />
          </span>
          <span className="gr-valeur">{l.texte}</span>
        </li>
      ))}
    </ul>
  );
}

function TopSorties({ donnees, onArticle }) {
  const lignes = donnees.top_sorties.map((a) => ({
    cle: a.id, id: a.id, libelle: a.nom, valeur: a.qte, texte: quantite(a.qte, a.unite),
    aide: `${a.code} · ${a.nom} : ${quantite(a.qte, a.unite)} remis en ${pluriel(a.nb_sorties, "sortie")} — cliquez pour voir la fiche`,
  }));
  return (
    <section className="card tdb-panneau gr-carte">
      <div className="gr-tete">
        <h2>Top des sorties</h2>
        <span className="gr-sous-titre">Articles les plus remis · {donnees.jours_top_sorties} derniers jours</span>
      </div>
      {lignes.length ? <BarresHorizontales lignes={lignes} classe="sortie" onClic={onArticle} />
        : <p className="gr-vide">Aucune sortie confirmée sur cette période.</p>}
    </section>
  );
}

function Mouvements({ donnees }) {
  const jours = donnees.mouvements;
  const [survol, setSurvol] = useState(null);
  const total = (cle) => jours.reduce((t, j) => t + j[cle], 0);
  const { haut, ticks } = graduations(Math.max(...jours.map((j) => Math.max(j.entrees, j.sorties)), 0));
  const j = survol != null ? jours[survol] : null;
  return (
    <section className="card tdb-panneau gr-carte">
      <div className="gr-tete">
        <h2>Entrées et sorties</h2>
        <span className="gr-sous-titre">Nombre de bons par jour · {jours.length} derniers jours</span>
      </div>
      <div className="gr-legende">
        <span><i className="gr-pastille entree" />Entrées <b>{total("entrees")}</b></span>
        <span><i className="gr-pastille sortie" />Sorties <b>{total("sorties")}</b></span>
        <span className="gr-detail" aria-live="polite">
          {j ? <>{jourLong(j.jour)} : <b>{j.entrees}</b> entrée{j.entrees > 1 ? "s" : ""} · <b>{j.sorties}</b> sortie{j.sorties > 1 ? "s" : ""}</> : "Survolez un jour pour le détail"}
        </span>
      </div>
      <div className="gr-colonnes" onMouseLeave={() => setSurvol(null)}>
        <div className="gr-axe">
          {ticks.map((t) => <span key={t} style={{ bottom: `${(t / haut) * 100}%` }}>{t}</span>)}
        </div>
        <div className="gr-zone">
          <div className="gr-trace">
            {ticks.map((t) => <span key={t} className={`gr-grille${t === 0 ? " zero" : ""}`} style={{ bottom: `${(t / haut) * 100}%` }} />)}
            {jours.map((x, i) => (
              <div key={x.jour} className={`gr-jour${survol === i ? " survol" : ""}`} onMouseEnter={() => setSurvol(i)}
                title={`${jourLong(x.jour)} : ${pluriel(x.entrees, "entrée")}, ${pluriel(x.sorties, "sortie")}`}>
                <span className="gr-col entree" style={{ height: `${(x.entrees / haut) * 100}%` }} />
                <span className="gr-col sortie" style={{ height: `${(x.sorties / haut) * 100}%` }} />
              </div>
            ))}
          </div>
          <div className="gr-xs">
            {jours.map((x, i) => <span key={x.jour}>{i % 2 === (jours.length - 1) % 2 ? jourCourt(x.jour) : ""}</span>)}
          </div>
        </div>
      </div>
    </section>
  );
}

function ValeurParCategorie({ donnees }) {
  const lignes = donnees.categories.map((c) => ({
    cle: c.nom, libelle: c.nom, valeur: Number(c.valeur), texte: montantCourt(c.valeur), autres: c.autres,
    aide: `${c.nom} : ${montant(c.valeur)}`,
  }));
  return (
    <section className="card tdb-panneau gr-carte">
      <div className="gr-tete">
        <h2>Valeur du stock par catégorie</h2>
        <span className="gr-sous-titre">Quantité disponible × prix unitaire</span>
      </div>
      {lignes.length ? <BarresHorizontales lignes={lignes} classe="valeur" />
        : <p className="gr-vide">Aucun article en stock avec un prix unitaire.</p>}
    </section>
  );
}

export default function GraphiquesTableau({ donnees, onArticle }) {
  if (!donnees?.graphiques) return null;
  const g = donnees.graphiques;
  return (
    <div className="tdb-graphiques">
      <TopSorties donnees={g} onArticle={onArticle} />
      <Mouvements donnees={g} />
      <ValeurParCategorie donnees={g} />
    </div>
  );
}
