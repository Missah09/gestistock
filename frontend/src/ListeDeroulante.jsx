import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

// Recherche sans tenir compte des majuscules ni des accents : « epissure » trouve « Boîte d'épissure ».
const simple = (t) => String(t ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const texteDe = (o) => (o ? o.texte ?? (o.code ? `${o.code} · ${o.libelle}` : o.libelle) : "");

/** La liste déroulante de toute l'application (même présentation partout).
 *
 *  options : [{ valeur, libelle, code?, badge?, groupe?, texte? }]
 *    - code   : affiché en bleu devant le libellé (articles)
 *    - badge  : petite étiquette à droite (ex. « Non consommable · à rendre »)
 *    - groupe : titre de section (ex. le magasin pour les emplacements)
 *    - valeur "" : choix « vide » (ex. « — Aucun — »)
 *  recherche : on peut taper pour filtrer (activée d'office pour les longues listes).
 *  dejaPris  : valeurs déjà utilisées ailleurs (sur une autre ligne) : visibles mais non choisissables.
 *  creer     : { texte(saisie), onCreer(saisie) } : ligne « ＋ Créer… » tout en haut de la liste, toujours visible
 *              (ex. créer un article absent, 12/10/2026 ; placée en tête le 15/10/2026).
 *  La liste s'ouvre toujours vers le bas. */
export default function ListeDeroulante({
  options, valeur, onChange, placeholder = "", desactive, invalide, petite, className = "", ariaLabel,
  recherche, largeurMin = 0, dejaPris = [], texteDejaPris = "Déjà sur une autre ligne", texteAucun = "Aucun résultat",
  creer,
}) {
  const filtrable = recherche ?? options.length > 8;
  const choisi = options.find((o) => String(o.valeur) === String(valeur ?? ""));
  const [texte, setTexte] = useState(texteDe(choisi));
  const [ouvert, setOuvert] = useState(false);
  const [filtrer, setFiltrer] = useState(false); // false = toute la liste (ouverte par la flèche ou un clic)
  const [actif, setActif] = useState(0);
  const [pos, setPos] = useState(null);
  const champ = useRef(null);
  const liste = useRef(null);

  // Le texte suit la valeur choisie (ex. remise à zéro quand on change de magasin).
  const cleChoisi = choisi ? `${choisi.valeur}|${texteDe(choisi)}` : "";
  useEffect(() => { setTexte(texteDe(choisi)); }, [cleChoisi]); // eslint-disable-line react-hooks/exhaustive-deps

  const resultats = useMemo(() => {
    const mots = simple(texte).split(/\s+/).filter(Boolean);
    if (!filtrer || !mots.length) return options;
    return options.filter((o) => { const t = simple(`${o.code ?? ""} ${o.libelle} ${o.groupe ?? ""}`); return mots.every((m) => t.includes(m)); });
  }, [options, texte, filtrer]);

  const estPris = (o) => o && o.valeur !== "" && dejaPris.map(String).includes(String(o.valeur)) && String(o.valeur) !== String(valeur);
  // La ligne « ＋ Créer… » (si elle existe) s'affiche en tête de liste ; son index interne est resultats.length.
  const CREER = resultats.length;
  const libres = [...(creer ? [CREER] : []), ...resultats.map((o, i) => (estPris(o) ? -1 : i)).filter((i) => i >= 0)];
  const saisie = filtrer ? texte.trim() : "";
  // Après une frappe, on se place sur le premier résultat (Entrée choisit l'article trouvé) ; « Créer » seulement s'il n'y a rien.
  const premierLibre = () => libres.find((i) => i !== CREER) ?? libres[0] ?? 0;

  // La liste s'affiche par-dessus la fenêtre, juste sous le champ (toujours vers le bas).
  useLayoutEffect(() => {
    if (!ouvert) return;
    const placer = () => {
      const r = champ.current?.getBoundingClientRect();
      if (!r) return;
      const bas = window.innerHeight - r.bottom - 12;
      setPos({ left: r.left, width: Math.min(Math.max(r.width, largeurMin), window.innerWidth - r.left - 12),
        top: r.bottom + 4, max: Math.max(120, Math.min(300, bas)) });
    };
    // Pas assez de place sous le champ : on fait d'abord défiler la fenêtre pour lui en laisser.
    const r = champ.current?.getBoundingClientRect();
    if (r && window.innerHeight - r.bottom < 220) champ.current.scrollIntoView({ block: "center" });
    placer();
    window.addEventListener("resize", placer);
    window.addEventListener("scroll", placer, true);
    return () => { window.removeEventListener("resize", placer); window.removeEventListener("scroll", placer, true); };
  }, [ouvert, largeurMin]);

  // Après une frappe, la sélection se place sur le premier choix possible.
  useEffect(() => { if (ouvert && actif === -1) setActif(premierLibre()); }, [resultats, ouvert, actif]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { liste.current?.querySelector('[data-actif="1"]')?.scrollIntoView({ block: "nearest" }); }, [actif, ouvert]);

  function choisir(o) {
    if (estPris(o)) return;
    if (String(o.valeur) !== String(valeur ?? "")) onChange(String(o.valeur));
    setTexte(texteDe(o));
    setOuvert(false);
  }
  function lancerCreation() {
    const t = saisie;
    setOuvert(false);
    setTexte(texteDe(choisi));
    creer.onCreer(t);
  }
  function fermer() {
    setOuvert(false);
    setTexte(texteDe(choisi)); // texte tapé sans choisir : on revient au choix actuel
  }
  function ouvrirTout() {
    setFiltrer(false);
    const ici = options.findIndex((o) => String(o.valeur) === String(valeur ?? ""));
    setActif(ici >= 0 ? ici : options.findIndex((o) => !estPris(o)));
    setOuvert(true);
  }
  function touche(e) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!ouvert) return ouvrirTout();
      if (!libres.length) return;
      const p = libres.indexOf(actif);
      const n = libres.length;
      setActif(libres[p < 0 ? 0 : (p + (e.key === "ArrowDown" ? 1 : n - 1)) % n]);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (!ouvert) return ouvrirTout();
      if (creer && actif === CREER) lancerCreation();
      else if (resultats[actif] && !estPris(resultats[actif])) choisir(resultats[actif]);
    } else if (e.key === " " && !filtrable) {
      e.preventDefault();
      if (ouvert) fermer(); else ouvrirTout();
    } else if (e.key === "Escape") {
      if (ouvert) { e.stopPropagation(); e.nativeEvent.stopImmediatePropagation?.(); fermer(); }
    } else if (e.key === "Tab") {
      if (ouvert) fermer();
    }
  }

  let groupePrecedent = null;
  return (
    <div className={`liste-deroulante${desactive ? " desactive" : ""}${filtrable ? "" : " sans-saisie"} ${className}`}>
      <input ref={champ} className={`saisie${petite ? " petite" : ""}${invalide ? " invalide" : ""}`} value={texte} disabled={desactive}
        readOnly={!filtrable} placeholder={placeholder} role="combobox" aria-expanded={ouvert} aria-autocomplete={filtrable ? "list" : "none"}
        aria-label={ariaLabel} title={texte || placeholder}
        onChange={(e) => { setTexte(e.target.value); setFiltrer(true); setActif(-1); setOuvert(true); }}
        onClick={() => { if (!ouvert) ouvrirTout(); else if (!filtrable) fermer(); }}
        onFocus={(e) => { if (filtrable) e.target.select(); }}
        onBlur={() => setTimeout(fermer, 120)}
        onKeyDown={touche} />
      <button type="button" className="fleche" tabIndex={-1} disabled={desactive} aria-label="Afficher la liste"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => { if (ouvert) fermer(); else { champ.current?.focus(); ouvrirTout(); } }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>
      </button>
      {ouvert && pos && createPortal(
        <ul ref={liste} className="choix-liste" role="listbox" style={{ left: pos.left, width: pos.width, top: pos.top, maxHeight: pos.max }}
          onMouseDown={(e) => e.preventDefault()}>
          {creer && (
            <li role="option" aria-selected={false} data-actif={actif === CREER ? "1" : "0"}
              className={`creer${actif === CREER ? " actif" : ""}`} onMouseEnter={() => setActif(CREER)} onClick={lancerCreation}>
              <span className="nom">＋ {creer.texte(saisie)}</span>
            </li>
          )}
          {resultats.length === 0 && <li className="aucun">{texteAucun} pour « {texte} ».</li>}
          {resultats.map((o, i) => {
            const pris = estPris(o);
            const titre = o.groupe && o.groupe !== groupePrecedent ? o.groupe : null;
            groupePrecedent = o.groupe ?? null;
            return (
              <Fragment key={`${o.valeur}`}>
                {titre && <li className="groupe" role="presentation">{titre}</li>}
                <li role="option" aria-selected={String(o.valeur) === String(valeur ?? "")} aria-disabled={pris}
                  data-actif={i === actif ? "1" : "0"} title={pris ? texteDejaPris : undefined}
                  className={`${i === actif && !pris ? "actif" : ""}${pris ? " pris" : ""}${o.valeur === "" ? " choix-vide" : ""}`}
                  onMouseEnter={() => { if (!pris) setActif(i); }} onClick={() => choisir(o)}>
                  {o.code && <span className="code">{o.code}</span>}
                  <span className="nom">{o.libelle}</span>
                  {o.badge}
                  {pris && <span className="pill p-w petite-pill deja">{texteDejaPris}</span>}
                </li>
              </Fragment>
            );
          })}
        </ul>, document.body)}
    </div>
  );
}
