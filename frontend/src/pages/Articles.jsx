import { useCallback, useEffect, useState } from "react";
import ListeDeroulante from "../ListeDeroulante.jsx";
import { lireFiltres, listerArticles } from "../api.js";
import { ETATS, quantite } from "../format.js";
import Icon from "../icons.jsx";
import EnregistrerProduits from "./EnregistrerProduits.jsx";
import FicheArticle from "./FicheArticle.jsx";

const PAR_PAGE = 10;

export default function Articles({ compte }) {
  // Consultation pour tous ; réception et modification réservées à l'Agent Logistique.
  const gestion = !!compte?.agent_logistique;
  const [page, setPage] = useState(1);
  const [donnees, setDonnees] = useState(null); // { count, results }
  const [erreur, setErreur] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [ouvert, setOuvert] = useState(null); // id de l'article dont la fiche est ouverte
  const [rafraichir, setRafraichir] = useState(0); // +1 après une modification → recharge la liste
  const [reception, setReception] = useState(false); // fenêtre « Enregistrer des produits » ouverte
  const [annonce, setAnnonce] = useState(null);      // message de réussite affiché au-dessus de la liste

  // Recherche et filtres
  const [saisie, setSaisie] = useState("");        // ce que l'utilisateur tape
  const [recherche, setRecherche] = useState("");  // appliqué après une courte pause
  const [categorie, setCategorie] = useState("");
  const [magasin, setMagasin] = useState("");
  const [sousSeuil, setSousSeuil] = useState(false);
  const [options, setOptions] = useState({ categories: [], magasins: [] });

  // Listes Catégorie / Magasin : chargées une fois, et rechargées si le premier essai a échoué
  // (par exemple si Django n'était pas encore démarré).
  const optionsChargees = options.categories.length > 0;
  useEffect(() => {
    if (optionsChargees) return;
    lireFiltres()
      .then(setOptions)
      .catch((e) => console.error("Listes Catégorie/Magasin non chargées :", e));
  }, [optionsChargees, donnees]);

  // On attend 300 ms après la dernière touche avant de chercher.
  useEffect(() => {
    const minuteur = setTimeout(() => setRecherche(saisie), 300);
    return () => clearTimeout(minuteur);
  }, [saisie]);

  // Tout changement de filtre ramène à la première page — avant le chargement,
  // pour ne pas demander au serveur une page qui n'existe pas (ex. page 3 d'une recherche à 2 résultats).
  const cleFiltres = JSON.stringify([recherche, categorie, magasin, sousSeuil]);
  const [filtresVus, setFiltresVus] = useState(cleFiltres);
  if (filtresVus !== cleFiltres) { setFiltresVus(cleFiltres); setPage(1); }

  const fermerFiche = useCallback(() => setOuvert(null), []);

  const filtreActif = recherche || categorie || magasin || sousSeuil;
  function effacerFiltres() {
    setSaisie(""); setRecherche(""); setCategorie(""); setMagasin(""); setSousSeuil(false);
  }

  useEffect(() => {
    let annule = false;
    setChargement(true);
    setErreur(null);
    listerArticles({ page, q: recherche, categorie, magasin, sousSeuil })
      .then((d) => !annule && setDonnees(d))
      .catch(() => !annule && setErreur("Impossible de joindre le serveur. Vérifiez que la fenêtre du backend (runserver) est ouverte."))
      .finally(() => !annule && setChargement(false));
    return () => { annule = true; };
  }, [page, recherche, categorie, magasin, sousSeuil, rafraichir]);

  const total = donnees?.count ?? 0;
  const debut = total === 0 ? 0 : (page - 1) * PAR_PAGE + 1;
  const fin = Math.min(page * PAR_PAGE, total);
  const derniere = Math.max(1, Math.ceil(total / PAR_PAGE));

  return (
    <>
      <header className="top"><h1>Liste d'Articles</h1></header>
      <div className="body">
        {erreur && <div className="alerte">{erreur}</div>}

        <div className="barre">
          <label className="recherche">
            <Icon name="search" size={19} />
            <input
              type="search"
              placeholder="Rechercher un article…"
            title="Recherche par nom, code article, n° de série ou code immo"
              value={saisie}
              onChange={(e) => setSaisie(e.target.value)}
              aria-label="Rechercher un article"
            />
          </label>
          <ListeDeroulante className="filtre" ariaLabel="Catégorie" recherche={false} valeur={categorie} onChange={setCategorie}
            options={[{ valeur: "", libelle: "Catégorie : Toutes" },
              ...options.categories.map((c) => ({ valeur: String(c.id), libelle: c.nom, texte: `Catégorie : ${c.nom}` }))]} />
          <ListeDeroulante className="filtre" ariaLabel="Magasin" recherche={false} valeur={magasin} onChange={setMagasin}
            options={[{ valeur: "", libelle: "Magasin : Tous" },
              ...options.magasins.map((m) => ({ valeur: String(m.id), libelle: m.type === "CHANTIER" ? `Chantier : ${m.nom}` : m.nom,
                texte: `Magasin : ${m.nom}` }))]} />
          <label className="btn case">
            <input type="checkbox" checked={sousSeuil} onChange={(e) => setSousSeuil(e.target.checked)} />
            Sous le seuil seulement
          </label>
          {filtreActif && (
            <button className="btn lien effacer" type="button" onClick={effacerFiltres}>
              <Icon name="x" size={14} stroke={2.2} />Effacer les filtres
            </button>
          )}
          <span className="sp" />
          {gestion && (
            <button className="btn pri" type="button" onClick={() => { setAnnonce(null); setReception(true); }}>
              <Icon name="plus" size={18} stroke={2.4} />Enregistrer des produits
            </button>
          )}
        </div>

        {annonce && (
          <div className="succes annonce">
            <span>{annonce}</span>
            <button type="button" className="btn-icone" onClick={() => setAnnonce(null)} aria-label="Masquer le message"><Icon name="x" size={16} stroke={2.2} /></button>
          </div>
        )}

        <div className="card">
          <table className="tableau">
            <thead>
              <tr>
                <th style={{ width: 210 }}>Code article</th>
                <th>Nom de l'article</th>
                <th>Catégorie</th>
                <th className="centre">Qté disponible</th>
                <th className="centre">Qté minimale</th>
                <th>État du stock</th>
                <th>Emplacement</th>
              </tr>
            </thead>
            <tbody>
              {donnees?.results.map((a) => {
                const etat = ETATS[a.etat];
                const alerte = a.etat === "CRITIQUE" || a.etat === "EPUISE";
                return (
                  <tr
                    key={a.id}
                    className={`cliquable ${a.id === ouvert ? "choisie" : alerte ? "alerte-ligne" : ""}`}
                    onClick={() => setOuvert(a.id)}
                  >
                    <td>
                      <div className="code-cell">
                        <span className="code">{a.code}</span>
                        <button className="btn-details" type="button" title="Voir la fiche de l'article"
                          onClick={(e) => { e.stopPropagation(); setOuvert(a.id); }}>
                          <Icon name="doc" size={15} stroke={2} />Détails
                        </button>
                      </div>
                    </td>
                    <td className="nom">{a.nom}</td>
                    <td>{a.categorie}</td>
                    <td className="num centre">{quantite(a.qte_disponible, a.unite)}</td>
                    <td className="discret centre">{quantite(a.qte_minimale, a.unite)}</td>
                    <td><span className={`pill ${etat.classe}`}>{etat.libelle}</span></td>
                    <td>{a.emplacement}</td>
                  </tr>
                );
              })}
              {!chargement && donnees?.results.length === 0 && (
                <tr><td colSpan={7} className="vide">
                  {filtreActif ? "Aucun article ne correspond à votre recherche." : "Aucun article."}
                </td></tr>
              )}
            </tbody>
          </table>

          <div className="pied">
            <span>{chargement ? "Chargement…" : `${debut} à ${fin} sur ${total} articles`}</span>
            <div className="pages">
              <button className="btn" type="button" disabled={page <= 1 || chargement} onClick={() => setPage(page - 1)}>← Page précédente</button>
              <button className="btn" type="button" disabled={page >= derniere || chargement} onClick={() => setPage(page + 1)}>Page suivante →</button>
            </div>
          </div>
        </div>
      </div>

      {reception && (
        <EnregistrerProduits
          onFermer={() => setReception(false)}
          onEnregistre={(message) => { setReception(false); setAnnonce(message); setRafraichir((n) => n + 1); }}
        />
      )}
      {ouvert && <FicheArticle id={ouvert} modifiable={gestion} onFermer={fermerFiche} onModifie={() => setRafraichir((n) => n + 1)} />}
    </>
  );
}
