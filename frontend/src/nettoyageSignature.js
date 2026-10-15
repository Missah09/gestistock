// Signature scannée (papier + stylo) : nettoyage dans le navigateur (15/10/2026).
// Fond du papier rendu transparent (même avec un éclairage inégal sur une photo de téléphone), petites taches retirées,
// image recadrée autour du trait puis réduite : le serveur reçoit un PNG transparent, comme la signature dessinée.

const COTE_TRAVAIL = 1600;           // plus grand côté de l'image analysée (px)
const SORTIE_MAX = { l: 900, h: 360 }; // taille maximale de la signature enregistrée
const OCTETS_MAX = 480 * 1024;       // le serveur accepte 500 Ko
export const FICHIER_MAX = 15 * 1024 * 1024;

// Force du nettoyage : seuil de « noirceur » par rapport au papier autour (0 = papier, 1 = noir).
export const NIVEAUX = [
  { cle: "leger", libelle: "Léger", seuil: 0.10 },   // stylo pâle, trait fin
  { cle: "normal", libelle: "Normal", seuil: 0.17 },
  { cle: "fort", libelle: "Fort", seuil: 0.26 },     // papier gris, ombres, grain de la photo
];

/** Lit le fichier choisi (JPG ou PNG) ; l'orientation des photos de téléphone est respectée. */
export async function chargerImage(fichier) {
  if (!fichier) throw new Error("Aucun fichier choisi.");
  if (fichier.type === "application/pdf" || /\.pdf$/i.test(fichier.name)) {
    throw new Error("Les PDF ne sont pas acceptés : enregistrez le scan en image (JPG ou PNG), ou prenez la signature en photo.");
  }
  if (!/^image\/(png|jpeg)$/.test(fichier.type) && !/\.(png|jpe?g)$/i.test(fichier.name)) {
    throw new Error("Choisissez une image JPG ou PNG (scan ou photo de la signature).");
  }
  if (fichier.size > FICHIER_MAX) throw new Error("Fichier trop lourd (15 Mo au maximum).");
  try {
    if (window.createImageBitmap) return await createImageBitmap(fichier, { imageOrientation: "from-image" });
  } catch { /* on essaie avec une balise image */ }
  const url = URL.createObjectURL(fichier);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } catch {
    throw new Error("Image illisible : choisissez un autre fichier.");
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Nettoie l'image : renvoie { image: "data:image/png;base64,…", largeur, hauteur, avertissement }.
 *  rotation : 0, 90, 180 ou 270 (sens des aiguilles d'une montre). Lève une Error avec un message pour l'utilisateur. */
export function nettoyer(source, { niveau = "normal", rotation = 0 } = {}) {
  const seuil = (NIVEAUX.find((n) => n.cle === niveau) ?? NIVEAUX[1]).seuil;
  const sw = source.width, sh = source.height;
  if (!sw || !sh) throw new Error("Image illisible : choisissez un autre fichier.");

  // 1. Image de travail (réduite, tournée)
  const k = Math.min(1, COTE_TRAVAIL / Math.max(sw, sh));
  const tw = Math.max(1, Math.round(sw * k)), th = Math.max(1, Math.round(sh * k));
  const tourne = rotation === 90 || rotation === 270;
  const W = tourne ? th : tw, H = tourne ? tw : th;
  const toile = document.createElement("canvas");
  toile.width = W; toile.height = H;
  const ctx = toile.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, W, H); // PNG déjà transparent : fond blanc
  ctx.translate(W / 2, H / 2);
  ctx.rotate((rotation * Math.PI) / 180);
  ctx.drawImage(source, -tw / 2, -th / 2, tw, th);
  const donnees = ctx.getImageData(0, 0, W, H);
  const px = donnees.data;
  const N = W * H;

  // 2. Luminosité de chaque point
  const lum = new Uint8ClampedArray(N);
  for (let i = 0, j = 0; i < N; i++, j += 4) lum[i] = (px[j] * 299 + px[j + 1] * 587 + px[j + 2] * 114) / 1000;

  // 3. Couleur du papier, zone par zone (85e centile de chaque bloc), puis interpolée : corrige ombres et éclairage inégal
  const B = Math.max(16, Math.round(Math.max(W, H) / 40));
  const bx = Math.ceil(W / B), by = Math.ceil(H / B);
  const blocs = new Float32Array(bx * by);
  const histo = new Uint32Array(256);
  for (let yb = 0; yb < by; yb++) {
    for (let xb = 0; xb < bx; xb++) {
      histo.fill(0);
      const x0 = xb * B, y0 = yb * B, x1 = Math.min(W, x0 + B), y1 = Math.min(H, y0 + B);
      for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) histo[lum[y * W + x]]++;
      let cible = (x1 - x0) * (y1 - y0) * 0.85, v = 0;
      for (let c = 0; c < 256; c++) { cible -= histo[c]; if (cible <= 0) { v = c; break; } }
      blocs[yb * bx + xb] = v;
    }
  }
  // Zones sans papier (bureau, main, bord sombre de la photo) : blocs bien plus sombres que le papier,
  // élargies de 2 blocs pour ne pas garder la limite papier / bureau comme un trait.
  const tries = Array.from(blocs).sort((u, v) => u - v);
  const papier = tries[Math.floor(tries.length * 0.6)] || 255;
  const sansPapierBloc = new Uint8Array(bx * by);
  for (let yb = 0; yb < by; yb++) for (let xb = 0; xb < bx; xb++) {
    if (blocs[yb * bx + xb] >= Math.max(70, papier * 0.62)) continue;
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {
      const yy = yb + dy, xx = xb + dx;
      if (yy >= 0 && yy < by && xx >= 0 && xx < bx) sansPapierBloc[yy * bx + xx] = 1;
    }
  }
  const fondEn = (x, y) => {
    const fx = Math.min(bx - 1, Math.max(0, (x + 0.5) / B - 0.5)), fy = Math.min(by - 1, Math.max(0, (y + 0.5) / B - 0.5));
    const x0 = Math.floor(fx), y0 = Math.floor(fy), x1 = Math.min(bx - 1, x0 + 1), y1 = Math.min(by - 1, y0 + 1);
    const ax = fx - x0, ay = fy - y0;
    const h = blocs[y0 * bx + x0] * (1 - ax) + blocs[y0 * bx + x1] * ax;
    const b = blocs[y1 * bx + x0] * (1 - ax) + blocs[y1 * bx + x1] * ax;
    return h * (1 - ay) + b * ay;
  };

  // 4. Encre = nettement plus foncé que le papier autour ; transparence progressive (bords du trait adoucis)
  const alpha = new Uint8ClampedArray(N);
  const fond = new Float32Array(N);
  const RAMPE = 0.2;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = y * W + x;
      const f = fondEn(x, y);
      fond[i] = f;
      if (f < 70 || sansPapierBloc[Math.floor(y / B) * bx + Math.floor(x / B)]) continue; // pas de papier ici
      const noirceur = 1 - Math.min(1, lum[i] / f);
      if (noirceur <= seuil) continue;
      alpha[i] = Math.round(255 * Math.min(1, (noirceur - seuil) / RAMPE));
    }
  }

  // 5. Taches isolées (grain, poussière) et traits collés au bord de la photo (ombre, bord de la feuille) retirés
  const etiquette = new Int32Array(N).fill(-1);
  const morceaux = [];
  const pile = new Int32Array(N);
  for (let depart = 0; depart < N; depart++) {
    if (alpha[depart] < 60 || etiquette[depart] !== -1) continue;
    const m = { n: 0, encre: 0, bord: false, x0: W, y0: H, x1: 0, y1: 0 };
    const id = morceaux.length;
    let haut = 0;
    pile[haut++] = depart; etiquette[depart] = id;
    while (haut) {
      const i = pile[--haut];
      const x = i % W, y = (i - x) / W;
      m.n++; m.encre += alpha[i];
      if (x < m.x0) m.x0 = x; if (x > m.x1) m.x1 = x; if (y < m.y0) m.y0 = y; if (y > m.y1) m.y1 = y;
      if (x === 0 || y === 0 || x === W - 1 || y === H - 1) m.bord = true;
      for (let dy = -1; dy <= 1; dy++) {
        const yy = y + dy; if (yy < 0 || yy >= H) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const xx = x + dx; if (xx < 0 || xx >= W) continue;
          const v = yy * W + xx;
          if (alpha[v] >= 60 && etiquette[v] === -1) { etiquette[v] = id; pile[haut++] = v; }
        }
      }
    }
    morceaux.push(m);
  }
  if (!morceaux.length) throw new Error(AUCUNE);
  const total = morceaux.reduce((s, m) => s + m.encre, 0);
  const tailleMin = Math.max(12, N * 0.00003);
  const plusGros = morceaux.reduce((a, m) => (m.encre > a.encre ? m : a));
  const encreBord = morceaux.filter((m) => m.bord && m !== plusGros).reduce((s, m) => s + m.encre, 0);
  const garde = morceaux.map((m) => {
    if (m.n < tailleMin) return false;
    if (m.bord && m !== plusGros && encreBord < total * 0.5) return false;
    // Morceau collé au bord ET très étendu le long de ce bord : bord de la feuille, pas la signature
    if (m.bord && m === plusGros && morceaux.length > 1 && (m.x1 - m.x0 > W * 0.9 || m.y1 - m.y0 > H * 0.9) && m.n < (m.x1 - m.x0 + m.y1 - m.y0) * 6) return false;
    return true;
  });

  // 6. Cadre autour de l'encre gardée
  let x0 = W, y0 = H, x1 = -1, y1 = -1, points = 0;
  morceaux.forEach((m, id) => {
    if (!garde[id]) return;
    points += m.n;
    x0 = Math.min(x0, m.x0); y0 = Math.min(y0, m.y0); x1 = Math.max(x1, m.x1); y1 = Math.max(y1, m.y1);
  });
  if (x1 < 0 || points < 120 || x1 - x0 < 30) throw new Error(AUCUNE);

  // Petites marges ; les points faibles autour du trait (alpha < 60, bords adoucis) restent
  const marge = Math.round(Math.max(x1 - x0, y1 - y0) * 0.04) + 2;
  x0 = Math.max(0, x0 - marge); y0 = Math.max(0, y0 - marge); x1 = Math.min(W - 1, x1 + marge); y1 = Math.min(H - 1, y1 + marge);
  const cw = x1 - x0 + 1, ch = y1 - y0 + 1;

  // 7. Image finale : encre seule, couleur d'origine corrigée (papier → blanc) et foncée, fond transparent
  const coupe = new ImageData(cw, ch);
  const out = coupe.data;
  for (let y = 0; y < ch; y++) {
    for (let x = 0; x < cw; x++) {
      const i = (y + y0) * W + (x + x0), o = (y * cw + x) * 4;
      const e = etiquette[i];
      let a = alpha[i];
      if (!a) continue;
      if (e !== -1 && !garde[e]) continue;
      if (e === -1) { // point faible : gardé seulement s'il touche un morceau gardé
        let voisin = false;
        for (let dy = -1; dy <= 1 && !voisin; dy++) for (let dx = -1; dx <= 1; dx++) {
          const xx = x + x0 + dx, yy = y + y0 + dy;
          if (xx < 0 || yy < 0 || xx >= W || yy >= H) continue;
          const ev = etiquette[yy * W + xx];
          if (ev !== -1 && garde[ev]) { voisin = true; break; }
        }
        if (!voisin) continue;
      }
      const f = Math.max(1, fond[i]), j = i * 4;
      out[o] = Math.min(255, (px[j] / f) * 255) * 0.55;
      out[o + 1] = Math.min(255, (px[j + 1] / f) * 255) * 0.55;
      out[o + 2] = Math.min(255, (px[j + 2] / f) * 255) * 0.6;
      out[o + 3] = a;
    }
  }
  const morceau = document.createElement("canvas");
  morceau.width = cw; morceau.height = ch;
  morceau.getContext("2d").putImageData(coupe, 0, 0);

  // 8. Réduction (900 × 360 au plus) et contrôle du poids
  let echelle = Math.min(1, SORTIE_MAX.l / cw, SORTIE_MAX.h / ch);
  let image, l, h;
  for (let essai = 0; essai < 6; essai++) {
    l = Math.max(1, Math.round(cw * echelle)); h = Math.max(1, Math.round(ch * echelle));
    const fin = document.createElement("canvas");
    fin.width = l; fin.height = h;
    const c2 = fin.getContext("2d");
    c2.imageSmoothingQuality = "high";
    c2.drawImage(morceau, 0, 0, l, h);
    image = fin.toDataURL("image/png");
    if (image.length * 0.75 <= OCTETS_MAX) break;
    echelle *= 0.75;
  }

  // Beaucoup d'« encre » sur toute l'image : probablement une photo sans fond blanc net
  const avertissement = points > cw * ch * 0.35 && cw > W * 0.8 && ch > H * 0.8
    ? "Le fond n'a pas été bien retiré : essayez le nettoyage « Fort », ou une photo de la signature seule sur papier blanc, bien éclairée."
    : null;
  return { image, largeur: l, hauteur: h, avertissement };
}

const AUCUNE = "Aucune signature n'a été trouvée sur l'image : vérifiez le fichier, essayez le nettoyage « Léger », "
  + "ou photographiez la signature de plus près, sur papier blanc et bien éclairée.";
