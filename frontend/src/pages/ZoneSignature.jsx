import { useEffect, useRef, useState } from "react";
import Icon from "../icons.jsx";
import { lireMaSignature, retirerMaSignature } from "../api.js";
import { NIVEAUX, chargerImage, nettoyer } from "../nettoyageSignature.js";
import StyloSignature from "./StyloSignature.jsx";

/** Zone « Votre signature » (15/10/2026) : trois façons de signer + mot de passe retapé.
 *  - Ma signature enregistrée : la signature scannée gardée dans le compte, réutilisée d'un clic ;
 *  - Importer ma signature scannée : scan ou photo (JPG, PNG), fond rendu transparent, recadrée ;
 *  - Dessiner à la souris : le stylo électronique.
 *  onChange(etat) : { image (aperçu dans la case du bon) | null, pret, corps } ;
 *  corps = ce que le serveur attend : { source, signature?, enregistrer?, mot_de_passe }.
 *  erreur : message du serveur (signature ou mot de passe). */
export default function ZoneSignature({ onChange, desactive = false, erreur }) {
  const [enregistree, setEnregistree] = useState(undefined); // undefined = en cours de lecture ; null = aucune
  const [onglet, setOnglet] = useState(null);
  const [dessin, setDessin] = useState(null);
  const [import_, setImport] = useState({ source: null, nom: "", niveau: "normal", rotation: 0, resultat: null, erreur: null, calcul: false });
  const [enregistrer, setEnregistrer] = useState(true);
  const [motDePasse, setMotDePasse] = useState("");
  const [retirer, setRetirer] = useState(false);
  const [erreurLocale, setErreurLocale] = useState(null);
  const champFichier = useRef(null);
  const champMdp = useRef(null);

  // Signature enregistrée dans le compte ? (onglet ouvert par défaut si oui)
  useEffect(() => {
    let fini = false;
    lireMaSignature()
      .then((r) => { if (!fini) { setEnregistree(r.enregistree ? r : null); setOnglet((o) => o ?? (r.enregistree ? "enregistree" : "dessin")); } })
      .catch(() => { if (!fini) { setEnregistree(null); setOnglet((o) => o ?? "dessin"); } });
    return () => { fini = true; };
  }, []);

  // Nouvelle erreur de mot de passe : on resélectionne le champ
  useEffect(() => { if (erreur && /mot de passe/i.test(erreur)) champMdp.current?.select(); }, [erreur]);

  const image = onglet === "enregistree" ? enregistree?.image ?? null
    : onglet === "import" ? import_.resultat?.image ?? null
      : onglet === "dessin" ? dessin : null;

  useEffect(() => {
    const corps = { source: onglet === "dessin" ? "dessinee" : onglet === "import" ? "importee" : "enregistree", mot_de_passe: motDePasse };
    if (onglet !== "enregistree" && image) corps.signature = image;
    if (onglet === "import") corps.enregistrer = enregistrer;
    onChange({ image, pret: Boolean(image && motDePasse), corps });
  }, [onglet, image, motDePasse, enregistrer]); // eslint-disable-line react-hooks/exhaustive-deps

  // Nettoyage du scan (relancé quand on change la force ou qu'on fait pivoter)
  function traiter(source, niveau, rotation) {
    setImport((s) => ({ ...s, calcul: true, erreur: null }));
    setTimeout(() => { // laisse s'afficher « Nettoyage… »
      try {
        const resultat = nettoyer(source, { niveau, rotation });
        setImport((s) => ({ ...s, resultat, calcul: false }));
      } catch (e) {
        setImport((s) => ({ ...s, resultat: null, erreur: e.message, calcul: false }));
      }
    }, 30);
  }
  async function choisirFichier(fichier) {
    if (!fichier) return;
    setImport({ source: null, nom: fichier.name, niveau: "normal", rotation: 0, resultat: null, erreur: null, calcul: true });
    try {
      const source = await chargerImage(fichier);
      setImport((s) => ({ ...s, source }));
      traiter(source, "normal", 0);
    } catch (e) {
      setImport((s) => ({ ...s, erreur: e.message, calcul: false }));
    }
  }
  const regler = (champ, valeur) => {
    const s = { ...import_, [champ]: valeur };
    setImport(s);
    if (s.source) traiter(s.source, s.niveau, s.rotation);
  };

  async function retirerDuCompte() {
    setErreurLocale(null);
    try {
      await retirerMaSignature();
      setEnregistree(null); setRetirer(false); setOnglet("import");
    } catch {
      setErreurLocale("La signature n'a pas pu être retirée. Vérifiez que le serveur est démarré.");
    }
  }

  const onglets = [
    ...(enregistree ? [{ cle: "enregistree", libelle: "Ma signature enregistrée" }] : []),
    { cle: "import", libelle: "Importer ma signature scannée" },
    { cle: "dessin", libelle: "Dessiner à la souris" },
  ];
  const erreurMdp = erreur && /mot de passe|essais/i.test(erreur) ? erreur : null;
  const erreurSignature = erreur && !erreurMdp ? erreur : null;

  if (onglet === null) return <p className="zs-aide">Chargement…</p>;

  return (
    <div className={`zone-signature${desactive ? " desactive" : ""}`}>
      <div className="onglets zs-onglets" role="tablist" aria-label="Façon de signer">
        {onglets.map((o) => (
          <button key={o.cle} type="button" role="tab" aria-selected={onglet === o.cle} className={`onglet${onglet === o.cle ? " on" : ""}`}
            disabled={desactive} onClick={() => { setOnglet(o.cle); setRetirer(false); }}>{o.libelle}</button>
        ))}
      </div>

      {onglet === "enregistree" && enregistree && (
        <div className="zs-panneau">
          <div className="zs-apercu"><img src={enregistree.image} alt="Votre signature enregistrée" /></div>
          <div className="zs-bas">
            <span className="zs-aide">
              Signature scannée enregistrée dans votre compte
              {enregistree.le ? ` le ${new Date(enregistree.le).toLocaleDateString("fr-FR")}` : ""}. Elle sera posée dans votre case du bon.
            </span>
            {!retirer ? (
              <>
                <button type="button" className="btn" disabled={desactive} onClick={() => setOnglet("import")}>Remplacer…</button>
                <button type="button" className="btn lien" disabled={desactive} onClick={() => setRetirer(true)}>Retirer de mon compte</button>
              </>
            ) : (
              <>
                <span className="a-completer">Retirer la signature de votre compte ?</span>
                <button type="button" className="btn" onClick={() => setRetirer(false)}>Non</button>
                <button type="button" className="btn danger" onClick={retirerDuCompte}>Oui, retirer</button>
              </>
            )}
          </div>
          {erreurLocale && <p className="msg-erreur">{erreurLocale}</p>}
        </div>
      )}

      {onglet === "import" && (
        <div className="zs-panneau">
          <input ref={champFichier} type="file" accept="image/png,image/jpeg,.png,.jpg,.jpeg" hidden
            onChange={(e) => { choisirFichier(e.target.files?.[0]); e.target.value = ""; }} />
          {!import_.source && !import_.calcul ? (
            <button type="button" className="zs-depot" disabled={desactive} onClick={() => champFichier.current?.click()}
              onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (!desactive) choisirFichier(e.dataTransfer.files?.[0]); }}>
              <Icon name="upload" size={28} stroke={1.8} />
              <b>Choisir le fichier de ma signature</b>
              <span>Scan ou photo de votre signature sur papier blanc (JPG ou PNG), ou glissez le fichier ici.</span>
              <span>Le fond du papier est retiré automatiquement.</span>
            </button>
          ) : (
            <>
              <div className="zs-apercu damier">
                {import_.calcul ? <span className="zs-aide">Nettoyage de l'image…</span>
                  : import_.resultat ? <img src={import_.resultat.image} alt="Votre signature après nettoyage" />
                    : <span className="zs-aide">—</span>}
              </div>
              <div className="zs-reglages">
                <span className="zs-fichier" title={import_.nom}>{import_.nom}</span>
                <span className="zs-etiquette">Nettoyage du fond :</span>
                <div className="onglets zs-niveaux" role="radiogroup" aria-label="Nettoyage du fond">
                  {NIVEAUX.map((n) => (
                    <button key={n.cle} type="button" role="radio" aria-checked={import_.niveau === n.cle}
                      className={`onglet${import_.niveau === n.cle ? " on" : ""}`} disabled={desactive || !import_.source || import_.calcul}
                      onClick={() => regler("niveau", n.cle)}>{n.libelle}</button>
                  ))}
                </div>
                <button type="button" className="btn" disabled={desactive || !import_.source || import_.calcul}
                  onClick={() => regler("rotation", (import_.rotation + 90) % 360)} title="Faire pivoter d'un quart de tour">
                  <Icon name="pivoter" size={18} stroke={2} />Pivoter
                </button>
                <span className="sp" />
                <button type="button" className="btn" disabled={desactive || import_.calcul} onClick={() => champFichier.current?.click()}>
                  Choisir un autre fichier
                </button>
              </div>
            </>
          )}
          {import_.erreur && <p className="msg-erreur">{import_.erreur}</p>}
          {import_.resultat?.avertissement && <p className="a-completer">{import_.resultat.avertissement}</p>}
          <label className="zs-coche">
            <input type="checkbox" checked={enregistrer} disabled={desactive} onChange={(e) => setEnregistrer(e.target.checked)} />
            <span>
              <b>Enregistrer cette signature dans mon compte</b>
              <small>{enregistree ? "Elle remplacera celle déjà enregistrée. " : ""}Les prochaines fois, un clic suffira (avec votre mot de passe).</small>
            </span>
          </label>
        </div>
      )}

      {onglet === "dessin" && (
        <div className="zs-panneau">
          <StyloSignature onChange={setDessin} desactive={desactive} />
        </div>
      )}

      {erreurSignature && <p className="msg-erreur">{erreurSignature}</p>}

      <div className={`zs-mdp${erreurMdp ? " en-erreur" : ""}`}>
        <label htmlFor="mdp-signature"><Icon name="cadenas" size={16} stroke={2} /> Votre mot de passe <span className="facultatif">(pour confirmer que c'est bien vous qui signez)</span></label>
        <input id="mdp-signature" ref={champMdp} type="password" className="saisie" autoComplete="current-password" disabled={desactive}
          value={motDePasse} onChange={(e) => setMotDePasse(e.target.value)} />
        {erreurMdp && <em className="msg-erreur">{erreurMdp}</em>}
      </div>
    </div>
  );
}
