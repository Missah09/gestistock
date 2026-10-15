import { useEffect, useMemo, useState } from "react";
import { activerCompte, changerMotDePasse, creerCompte, deconnecterCompte, listerComptes, modifierCompte, retirerSignatureCompte } from "../api.js";
import { dateHeure } from "../format.js";
import Icon from "../icons.jsx";
import ListeDeroulante from "../ListeDeroulante.jsx";
import JournalComptes from "./JournalComptes.jsx";

// Onglets (15/10/2026) : la liste des comptes, l'historique des comptes, le journal de connexion.
const VUES = [["liste", "users", "Comptes"], ["comptes", "clock", "Historique des comptes"], ["connexions", "cadenas", "Journal de connexion"]];

const simple = (t) => String(t ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const premier = (e) => (Array.isArray(e) ? e[0] : e);

function Roles({ c }) {
  return (
    <span className="roles">
      {c.administrateur && <span className="pill p-c">Administrateur</span>}
      {c.agent && <span className="pill p-i">Agent Logistique</span>}
      {c.responsable && <span className="pill p-ok">Responsable HBC</span>}
      {!c.administrateur && !c.agent && !c.responsable && <span className="pill p-g">Saisisseur</span>}
    </span>
  );
}

/** Champ mot de passe avec « Afficher ». */
function MotDePasse({ id, valeur, onChange, invalide, desactive }) {
  const [voir, setVoir] = useState(false);
  return (
    <span className="connexion-mdp">
      <input id={id} className={`saisie${invalide ? " invalide" : ""}`} type={voir ? "text" : "password"} autoComplete="new-password"
        value={valeur} disabled={desactive} onChange={(e) => onChange(e.target.value)} />
      <button type="button" className="connexion-oeil" onClick={() => setVoir(!voir)} aria-pressed={voir}
        aria-label={voir ? "Masquer le mot de passe" : "Afficher le mot de passe"} title={voir ? "Masquer" : "Afficher"}>
        <Icon name={voir ? "oeilBarre" : "oeil"} size={20} stroke={1.9} />
      </button>
    </span>
  );
}

/** Fenêtre « Nouveau compte » / « Modifier le compte ». */
function FenetreCompte({ compte: c, departements, moi, onFermer, onEnregistre }) {
  const nouveau = !c;
  const [f, setF] = useState(() => ({
    identifiant: c?.identifiant ?? "", prenom: c?.prenom ?? "", nom: c?.nom ?? "", email: c?.email ?? "",
    departement: c?.departement ? String(c.departement) : "", agent: c?.agent ?? false, responsable: c?.responsable ?? false,
    mot_de_passe: "",
  }));
  const [erreurs, setErreurs] = useState({});
  const [envoi, setEnvoi] = useState(false);
  const [action, setAction] = useState(null); // "mdp" | "desactiver" | "signature" (confirmation en bas)
  const [nouveauMdp, setNouveauMdp] = useState("");
  const [info, setInfo] = useState(null);
  const lui = c && moi && c.identifiant === moi;
  const changer = (cle, v) => { setF((x) => ({ ...x, [cle]: v })); setErreurs((e) => ({ ...e, [cle]: undefined, general: undefined })); };
  const err = (cle) => premier(erreurs[cle]);

  useEffect(() => {
    const touche = (e) => { if (e.key === "Escape" && !envoi) (action ? setAction(null) : onFermer()); };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [onFermer, envoi, action]);

  async function faire(promesse, fermer) {
    setEnvoi(true); setErreurs({}); setInfo(null);
    try {
      const r = await promesse;
      onEnregistre(r.message, r.compte, fermer);
      if (!fermer) { setInfo(r.message); setAction(null); setNouveauMdp(""); }
    } catch (e) {
      setErreurs(e.details ?? { general: ["L'enregistrement a échoué. Vérifiez que le serveur est démarré."] });
    } finally {
      setEnvoi(false);
    }
  }

  function enregistrer(e) {
    e.preventDefault();
    const donnees = { ...f, departement: f.departement ? Number(f.departement) : null };
    if (nouveau) faire(creerCompte(donnees), true);
    else { delete donnees.identifiant; delete donnees.mot_de_passe; faire(modifierCompte(c.id, donnees), true); }
  }

  const nbErreurs = Object.values(erreurs).filter(Boolean).length;
  return (
    <>
      <div className="voile" onClick={() => !envoi && onFermer()} />
      <form className="fenetre compte" role="dialog" aria-modal="true" aria-label={nouveau ? "Nouveau compte" : `Compte ${c.identifiant}`}
        onSubmit={enregistrer} noValidate>
        <div className="fenetre-tete">
          <h2>{nouveau ? "Nouveau compte" : `Compte « ${c.identifiant} »`}</h2>
          {!nouveau && <span className={`pill ${c.actif ? "p-ok" : "p-g"} titre-pill`}>{c.actif ? "Actif" : "Désactivé"}</span>}
          <span className="sp" />
          <button className="fermer" type="button" onClick={onFermer} disabled={envoi} aria-label="Fermer"><Icon name="x" size={22} stroke={2.2} /></button>
        </div>

        <div className="fenetre-corps">
          {err("general") && <div className="alerte">{err("general")}</div>}
          {!err("general") && nbErreurs > 0 && <div className="alerte">Certaines informations sont à corriger (en rouge ci-dessous).</div>}
          {info && <div className="succes">{info}</div>}

          <div className="entete-grille">
            <label className={err("identifiant") ? "en-erreur" : ""}>
              <span>Identifiant <em className="facultatif">(pour se connecter)</em></span>
              <input className="saisie" value={f.identifiant} readOnly={!nouveau} autoFocus={nouveau} placeholder="Ex. lova.randria"
                onChange={(e) => changer("identifiant", e.target.value)} />
              {err("identifiant") ? <em className="msg-erreur">{err("identifiant")}</em>
                : nouveau && <small className="aide">Sans espace ni accent. Il ne pourra plus être changé.</small>}
            </label>
            <label className={err("departement") ? "en-erreur" : ""}>
              <span>Département</span>
              <ListeDeroulante ariaLabel="Département" placeholder="— Choisir le département —" valeur={f.departement}
                invalide={Boolean(err("departement"))} onChange={(v) => changer("departement", v)}
                options={departements.map((d) => ({ valeur: String(d.id), libelle: d.nom }))} />
              {err("departement") ? <em className="msg-erreur">{err("departement")}</em> : <small className="aide">Imprimé comme « Service demandeur » sur le bon.</small>}
            </label>
            <label className={err("prenom") ? "en-erreur" : ""}>
              <span>Prénom</span>
              <input className="saisie" value={f.prenom} autoFocus={!nouveau} onChange={(e) => changer("prenom", e.target.value)} />
              {err("prenom") && <em className="msg-erreur">{err("prenom")}</em>}
            </label>
            <label className={err("nom") ? "en-erreur" : ""}>
              <span>Nom</span>
              <input className="saisie" value={f.nom} onChange={(e) => changer("nom", e.target.value)} />
              {err("nom") ? <em className="msg-erreur">{err("nom")}</em> : <small className="aide">Prénom et nom sont imprimés sur le bon (visas).</small>}
            </label>
            <label className={err("email") ? "en-erreur" : ""}>
              <span>Email <em className="facultatif">(facultatif)</em></span>
              <input className="saisie" type="email" value={f.email} onChange={(e) => changer("email", e.target.value)} />
              {err("email") && <em className="msg-erreur">{err("email")}</em>}
            </label>
            {nouveau && (
              <label className={err("mot_de_passe") ? "en-erreur" : ""}>
                <span>Mot de passe provisoire</span>
                <MotDePasse valeur={f.mot_de_passe} invalide={Boolean(err("mot_de_passe"))} onChange={(v) => changer("mot_de_passe", v)} />
                {err("mot_de_passe") ? <em className="msg-erreur">{erreurs.mot_de_passe.join(" ")}</em>
                  : <small className="aide">Au moins 8 caractères, pas trop simple. À donner à la personne.</small>}
              </label>
            )}
          </div>

          <fieldset className="roles-choix">
            <legend>Rôles</legend>
            <p className="aide">Tout compte peut faire des demandes de matériel (Saisisseur) : rien à cocher pour cela.</p>
            <label className="btn case">
              <input type="checkbox" checked={f.agent} onChange={(e) => changer("agent", e.target.checked)} />
              <span><b>Agent Logistique</b><small>Valide les demandes, crée les réquisitions, enregistre les réceptions.</small></span>
            </label>
            <label className="btn case">
              <input type="checkbox" checked={f.responsable} onChange={(e) => changer("responsable", e.target.checked)} />
              <span><b>Responsable HBC</b><small>Vise les réquisitions.</small></span>
            </label>
            {c?.administrateur && <p className="aide">Ce compte est <b>Administrateur</b> : il a déjà tous les rôles.</p>}
          </fieldset>

          {!nouveau && (
            <fieldset className="roles-choix acces">
              <legend>Accès</legend>
              <p className="aide">
                {c.connecte ? <><b className="vert">● Connecté en ce moment</b> sur un appareil. </> : "Pas connecté en ce moment. "}
                Dernière connexion : {c.derniere_connexion ? dateHeure(c.derniere_connexion) : "jamais"}.
                Un compte ne peut être connecté que sur un seul appareil à la fois.
              </p>
              {action === "mdp" ? (
                <div className={`mdp-saisie${err("mot_de_passe") ? " en-erreur" : ""}`}>
                  <label htmlFor="nouveau-mdp" className="etiquette">Nouveau mot de passe {lui ? "" : "(la personne sera déconnectée)"}</label>
                  <MotDePasse id="nouveau-mdp" valeur={nouveauMdp} invalide={Boolean(err("mot_de_passe"))} desactive={envoi}
                    onChange={(v) => { setNouveauMdp(v); setErreurs({}); }} />
                  {err("mot_de_passe") && <em className="msg-erreur">{erreurs.mot_de_passe.join(" ")}</em>}
                  <div className="boutons">
                    <button type="button" className="btn" disabled={envoi} onClick={() => setAction(null)}>Annuler</button>
                    <button type="button" className="btn pri" disabled={envoi || !nouveauMdp} onClick={() => faire(changerMotDePasse(c.id, nouveauMdp), false)}>
                      {envoi ? "Enregistrement…" : "Changer le mot de passe"}
                    </button>
                  </div>
                </div>
              ) : action === "desactiver" ? (
                <div className="boutons">
                  <span className="question">Désactiver « {c.identifiant} » ? Il ne pourra plus se connecter (ses demandes sont conservées).</span>
                  <span className="sp" />
                  <button type="button" className="btn" disabled={envoi} onClick={() => setAction(null)}>Non</button>
                  <button type="button" className="btn danger plein" disabled={envoi} onClick={() => faire(activerCompte(c.id, false), false)}>Oui, désactiver</button>
                </div>
              ) : (
                <div className="boutons">
                  <button type="button" className="btn" onClick={() => { setErreurs({}); setInfo(null); setAction("mdp"); }}>Changer le mot de passe</button>
                  {c.connecte && !lui && (
                    <button type="button" className="btn" disabled={envoi} onClick={() => faire(deconnecterCompte(c.id), false)}>Déconnecter l'appareil</button>
                  )}
                  {!lui && (c.actif
                    ? <button type="button" className="btn danger" onClick={() => { setInfo(null); setAction("desactiver"); }}>Désactiver le compte</button>
                    : <button type="button" className="btn" disabled={envoi} onClick={() => faire(activerCompte(c.id, true), false)}>Réactiver le compte</button>)}
                </div>
              )}
            </fieldset>
          )}

          {!nouveau && (
            <fieldset className="roles-choix signature-compte">
              <legend>Signature scannée</legend>
              {c.signature_enregistree ? (
                <>
                  <div className="signature-compte-image">
                    <img src={`/api/comptes/${c.id}/signature/?v=${encodeURIComponent(c.signature_le ?? "")}`} alt={`Signature enregistrée de ${c.nom_complet}`} />
                  </div>
                  <p className="aide">
                    Enregistrée par {lui ? "vous" : "la personne"}{c.signature_le ? ` le ${dateHeure(c.signature_le)}` : ""}.
                    La retirer n'efface pas les bons déjà signés ; {lui ? "vous pourrez" : "la personne pourra"} en importer une autre en signant.
                  </p>
                  {action === "signature" ? (
                    <div className="boutons">
                      <span className="question">Retirer la signature enregistrée de « {c.identifiant} » ?</span>
                      <span className="sp" />
                      <button type="button" className="btn" disabled={envoi} onClick={() => setAction(null)}>Non</button>
                      <button type="button" className="btn danger plein" disabled={envoi} onClick={() => faire(retirerSignatureCompte(c.id), false)}>
                        {envoi ? "Retrait…" : "Oui, retirer"}
                      </button>
                    </div>
                  ) : (
                    <div className="boutons">
                      <button type="button" className="btn danger" onClick={() => { setErreurs({}); setInfo(null); setAction("signature"); }}>Retirer la signature…</button>
                    </div>
                  )}
                </>
              ) : (
                <p className="aide">Aucune signature scannée enregistrée dans ce compte (elle s'enregistre au moment de signer un bon).</p>
              )}
            </fieldset>
          )}
        </div>

        <div className="fiche-pied">
          <span className="sp" />
          <button className="btn" type="button" onClick={onFermer} disabled={envoi}>Annuler</button>
          <button className="btn pri" type="submit" disabled={envoi}>{envoi ? "Enregistrement…" : nouveau ? "Créer le compte" : "Enregistrer"}</button>
        </div>
      </form>
    </>
  );
}

/** Écran « Comptes » (administrateur) : liste des comptes, création, modification. */
export default function Comptes({ compte: moi }) {
  const [donnees, setDonnees] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [q, setQ] = useState("");
  const [ouvert, setOuvert] = useState(undefined); // undefined : fermé ; null : nouveau ; objet : modification
  const [annonce, setAnnonce] = useState(null);
  const [vue, setVue] = useState("liste");

  const charger = () => listerComptes().then((d) => { setDonnees(d); setErreur(null); })
    .catch(() => setErreur("Impossible de joindre le serveur. Vérifiez que la fenêtre du backend (runserver) est ouverte."));
  useEffect(() => { charger(); }, []);

  const liste = useMemo(() => {
    const mots = simple(q).split(/\s+/).filter(Boolean);
    return (donnees?.comptes ?? []).filter((c) => {
      const t = simple(`${c.identifiant} ${c.prenom} ${c.nom} ${c.departement_nom} ${c.email}`);
      return mots.every((m) => t.includes(m));
    });
  }, [donnees, q]);

  return (
    <>
      <header className="top"><h1>Comptes</h1></header>
      <div className="body">
        <div className="onglets onglets-comptes" role="tablist">
          {VUES.map(([cle, icone, titre]) => (
            <button key={cle} type="button" role="tab" aria-selected={vue === cle} className={`onglet${vue === cle ? " on" : ""}`}
              onClick={() => setVue(cle)}>
              <Icon name={icone} size={16} stroke={2} />{titre}
            </button>
          ))}
        </div>
        {vue !== "liste" && <JournalComptes key={vue} vue={vue} />}
        {vue === "liste" && <>
        {erreur && <div className="alerte">{erreur}</div>}
        <div className="barre">
          <label className="recherche">
            <Icon name="search" size={18} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher : nom, identifiant, département" aria-label="Rechercher un compte" />
          </label>
          <span className="sp" />
          <button className="btn pri" type="button" onClick={() => { setAnnonce(null); setOuvert(null); }}>
            <Icon name="plus" size={18} stroke={2.4} />Nouveau compte
          </button>
        </div>
        {annonce && (
          <div className="succes annonce">
            <span>{annonce}</span>
            <button type="button" className="btn-icone" onClick={() => setAnnonce(null)} aria-label="Masquer le message"><Icon name="x" size={16} stroke={2.2} /></button>
          </div>
        )}
        <div className="card">
          <table className="tableau comptes">
            <thead>
              <tr><th>Nom</th><th>Identifiant</th><th>Département</th><th>Rôles</th><th>État</th><th>Dernière connexion</th><th style={{ width: 120 }} /></tr>
            </thead>
            <tbody>
              {liste.map((c) => (
                <tr key={c.id} className={`cliquable${c.actif ? "" : " inactif"}`} onClick={() => { setAnnonce(null); setOuvert(c); }}>
                  <td className="nom une-ligne">{c.prenom || c.nom ? `${c.prenom} ${c.nom}`.trim() : <span className="a-completer">Nom à compléter</span>}</td>
                  <td><span className="code">{c.identifiant}</span></td>
                  <td>{c.departement_nom || <span className="discret">—</span>}</td>
                  <td className="une-ligne"><Roles c={c} /></td>
                  <td className="une-ligne">
                    <span className={`pill ${c.actif ? "p-ok" : "p-g"}`}>{c.actif ? "Actif" : "Désactivé"}</span>
                    {c.connecte && <span className="connecte" title="Connecté en ce moment">● Connecté</span>}
                  </td>
                  <td className="discret une-ligne">{c.derniere_connexion ? dateHeure(c.derniere_connexion) : "Jamais"}</td>
                  <td><button type="button" className="btn-details"><Icon name="edit" size={15} stroke={2} />Modifier</button></td>
                </tr>
              ))}
              {donnees && liste.length === 0 && <tr><td colSpan={7} className="vide">Aucun compte ne correspond.</td></tr>}
              {!donnees && !erreur && <tr><td colSpan={7} className="vide">Chargement…</td></tr>}
            </tbody>
          </table>
          <div className="pied"><span>{donnees ? `${liste.length} compte${liste.length > 1 ? "s" : ""}` : ""}</span></div>
        </div>
        </>}
      </div>

      {ouvert !== undefined && (
        <FenetreCompte key={ouvert?.id ?? "nouveau"} compte={ouvert} departements={donnees?.departements ?? []} moi={moi?.identifiant}
          onFermer={() => setOuvert(undefined)}
          onEnregistre={(message, c, fermer) => {
            charger();
            if (fermer) { setOuvert(undefined); setAnnonce(message); } else setOuvert(c);
          }} />
      )}
    </>
  );
}
