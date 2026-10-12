import { LIBELLE_PRETE } from "../format.js";
import ListeDeroulante from "../ListeDeroulante.jsx";

/** Choix d'un article (Nouvelle demande, Enregistrer des produits) : on tape un bout du nom ou du code,
 *  ou on déroule toute la liste. Même liste déroulante que partout ailleurs, avec le code et le type. */
export default function ChoixArticle({ articles, valeur, onChoisir, desactive, invalide, texteVide, dejaPris = [],
  texteDejaPris = "Déjà sur la demande" }) {
  const options = articles.map((a) => ({
    valeur: String(a.id), code: a.code, libelle: a.nom,
    badge: a.type === "PRETE" ? <span className="pill p-i petite-pill">{LIBELLE_PRETE}</span> : null,
  }));
  return (
    <ListeDeroulante options={options} valeur={valeur} onChange={onChoisir} desactive={desactive} invalide={invalide}
      placeholder={texteVide} petite recherche largeurMin={460} ariaLabel="Article" dejaPris={dejaPris}
      texteDejaPris={texteDejaPris} texteAucun="Aucun article" />
  );
}
