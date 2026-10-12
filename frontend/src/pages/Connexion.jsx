import { useState } from "react";
import logoHbc from "../assets/logo-hbc.png";
import { seConnecter } from "../api.js";
import Icon from "../icons.jsx";

/** Écran de connexion : identifiant + mot de passe (comptes créés par l'administrateur). */
export default function Connexion({ onConnecte, message }) {
  const [identifiant, setIdentifiant] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [voir, setVoir] = useState(false);
  const [erreurs, setErreurs] = useState({});
  const [envoi, setEnvoi] = useState(false);

  async function valider(e) {
    e.preventDefault();
    setErreurs({});
    setEnvoi(true);
    try {
      onConnecte(await seConnecter(identifiant.trim(), motDePasse));
    } catch (err) {
      setErreurs(err.details || { general: ["Connexion impossible : le serveur GestiStock ne répond pas."] });
      setMotDePasse("");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="connexion-fond">
      <form className="connexion card" onSubmit={valider} noValidate>
        <img className="connexion-logo" src={logoHbc} alt="HBC – To create a sustainable future" />
        <h1>GestiStock</h1>
        <p className="connexion-sous-titre">Connectez-vous pour continuer</p>

        {erreurs.general && <div className="connexion-erreur" role="alert">{erreurs.general[0]}</div>}
        {!erreurs.general && message && <div className="connexion-info" role="status">{message}</div>}

        <label className="connexion-champ">
          <span>Identifiant</span>
          <input autoFocus autoComplete="username" value={identifiant} onChange={(e) => setIdentifiant(e.target.value)}
            aria-invalid={!!erreurs.identifiant} />
          {erreurs.identifiant && <small className="err">{erreurs.identifiant[0]}</small>}
        </label>

        <label className="connexion-champ">
          <span>Mot de passe</span>
          <span className="connexion-mdp">
            <input type={voir ? "text" : "password"} autoComplete="current-password" value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)} aria-invalid={!!erreurs.mot_de_passe} />
            <button type="button" className="connexion-oeil" onClick={() => setVoir(!voir)}
              aria-label={voir ? "Masquer le mot de passe" : "Afficher le mot de passe"} aria-pressed={voir}
              title={voir ? "Masquer le mot de passe" : "Afficher le mot de passe"}>
              <Icon name={voir ? "oeilBarre" : "oeil"} size={22} stroke={1.9} />
            </button>
          </span>
          {erreurs.mot_de_passe && <small className="err">{erreurs.mot_de_passe[0]}</small>}
        </label>

        <button className="btn pri connexion-bouton" type="submit" disabled={envoi}>
          {envoi ? "Connexion…" : "Se connecter"}
        </button>
        <p className="connexion-aide">Mot de passe oublié ? Demandez au service Informatique.</p>
      </form>
    </div>
  );
}
