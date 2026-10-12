import { useEffect, useRef, useState } from "react";

const ENCRE_MIN = 120; // longueur de trait minimale (px) : un simple clic ou petit trait n'est pas une signature

/** Cadre de signature au stylo électronique : souris (bouton gauche maintenu), doigt ou stylet.
 *  onChange(image) : « data:image/png;base64,… » (signature recadrée), ou null si le cadre est vide / insuffisant. */
export default function StyloSignature({ onChange, desactive = false }) {
  const toile = useRef(null);
  const etat = useRef({ trace: false, points: [], encre: 0, boite: null });
  const [vide, setVide] = useState(true);
  const [tropCourt, setTropCourt] = useState(false);

  // Taille réelle de la toile = taille affichée × densité de l'écran (trait net).
  useEffect(() => {
    const c = toile.current;
    const r = c.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.round(r.width * dpr);
    c.height = Math.round(r.height * dpr);
    const ctx = c.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#1b2a4a"; ctx.lineWidth = 2.4;
  }, []);

  const position = (e) => {
    const r = toile.current.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const agrandirBoite = ({ x, y }) => {
    const b = etat.current.boite;
    etat.current.boite = b ? { x0: Math.min(b.x0, x), y0: Math.min(b.y0, y), x1: Math.max(b.x1, x), y1: Math.max(b.y1, y) }
      : { x0: x, y0: y, x1: x, y1: y };
  };

  function debut(e) {
    if (desactive || (e.pointerType === "mouse" && e.button !== 0)) return;
    e.preventDefault();
    toile.current.setPointerCapture(e.pointerId);
    const p = position(e);
    etat.current.trace = true;
    etat.current.points = [p];
    agrandirBoite(p);
    const ctx = toile.current.getContext("2d");
    ctx.beginPath(); ctx.arc(p.x, p.y, 1.1, 0, Math.PI * 2); ctx.fillStyle = "#1b2a4a"; ctx.fill();
  }
  function trait(e) {
    const s = etat.current;
    if (!s.trace) return;
    e.preventDefault();
    const p = position(e);
    const pts = s.points;
    const der = pts[pts.length - 1];
    const dist = Math.hypot(p.x - der.x, p.y - der.y);
    if (dist < 1.5) return;
    s.encre += dist;
    pts.push(p);
    agrandirBoite(p);
    // Courbe lissée : on passe par les milieux des segments (trait propre même à la souris).
    const ctx = toile.current.getContext("2d");
    if (pts.length >= 3) {
      const a = pts[pts.length - 3], b = pts[pts.length - 2], c = p;
      ctx.beginPath();
      ctx.moveTo((a.x + b.x) / 2, (a.y + b.y) / 2);
      ctx.quadraticCurveTo(b.x, b.y, (b.x + c.x) / 2, (b.y + c.y) / 2);
      ctx.stroke();
    } else {
      ctx.beginPath(); ctx.moveTo(der.x, der.y); ctx.lineTo(p.x, p.y); ctx.stroke();
    }
  }
  function fin() {
    const s = etat.current;
    if (!s.trace) return;
    s.trace = false;
    setVide(false);
    const assez = s.encre >= ENCRE_MIN;
    setTropCourt(!assez);
    onChange(assez ? exporter() : null);
  }

  /** Image de la signature seule (recadrée avec une petite marge, fond transparent). */
  function exporter() {
    const c = toile.current, b = etat.current.boite;
    const dpr = c.width / c.getBoundingClientRect().width;
    const marge = 8;
    const x = Math.max(0, (b.x0 - marge) * dpr), y = Math.max(0, (b.y0 - marge) * dpr);
    const w = Math.min(c.width - x, (b.x1 - b.x0 + 2 * marge) * dpr), h = Math.min(c.height - y, (b.y1 - b.y0 + 2 * marge) * dpr);
    const sortie = document.createElement("canvas");
    sortie.width = Math.max(1, Math.round(w)); sortie.height = Math.max(1, Math.round(h));
    sortie.getContext("2d").drawImage(c, x, y, w, h, 0, 0, sortie.width, sortie.height);
    return sortie.toDataURL("image/png");
  }

  function effacer() {
    const c = toile.current;
    c.getContext("2d").clearRect(0, 0, c.width, c.height);
    etat.current = { trace: false, points: [], encre: 0, boite: null };
    setVide(true); setTropCourt(false);
    onChange(null);
  }

  return (
    <div className={`stylo${desactive ? " desactive" : ""}`}>
      <div className="stylo-cadre">
        <canvas ref={toile} className="stylo-toile" aria-label="Cadre de signature : signez avec la souris en gardant le bouton gauche enfoncé"
          onPointerDown={debut} onPointerMove={trait} onPointerUp={fin} onPointerCancel={fin} onPointerLeave={(e) => etat.current.trace && e.buttons === 0 && fin()} />
        <span className="stylo-ligne" aria-hidden="true" />
        {vide && <span className="stylo-invite" aria-hidden="true">Signez ici avec la souris (bouton gauche enfoncé)</span>}
      </div>
      <div className="stylo-bas">
        {tropCourt ? <span className="a-completer">Signature trop courte : signez comme sur papier.</span>
          : <span className="aide">Gardez le bouton gauche de la souris enfoncé pendant que vous signez.</span>}
        <span className="sp" />
        <button type="button" className="btn" onClick={effacer} disabled={desactive || vide}>Effacer</button>
      </div>
    </div>
  );
}
