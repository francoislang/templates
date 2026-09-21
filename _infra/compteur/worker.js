/**
 * Compteur de vues des demos — Cloudflare Worker.
 *
 * Les sites sont servis par GitHub Pages, qui ne donne aucun journal
 * d'acces. Chaque page appelle donc un pixel sur ce Worker, qui incremente
 * un compteur dans KV. Aucun service tiers, aucune donnee personnelle :
 * on ne stocke qu'un slug, un nombre et deux horodatages.
 *
 * Routes
 *   GET /p?s=<slug>   pixel transparent, incremente le compteur
 *   GET /stats        JSON de tous les compteurs (jeton requis)
 *   GET /             message de sante
 */

// GIF transparent 1x1, en dur pour eviter tout decodage a chaud.
const PIXEL = new Uint8Array([
  0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00, 0x80, 0x00,
  0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0x21, 0xf9, 0x04, 0x01, 0x00,
  0x00, 0x00, 0x00, 0x2c, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
  0x00, 0x02, 0x01, 0x44, 0x00, 0x3b,
]);

const SLUG_OK = /^[a-z0-9][a-z0-9-]{0,79}$/;

function pixel() {
  return new Response(PIXEL, {
    headers: {
      "Content-Type": "image/gif",
      // Sans cela le navigateur servirait le pixel depuis son cache
      // et la deuxieme visite ne serait jamais comptee.
      "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
      "Pragma": "no-cache",
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/p") {
      const slug = (url.searchParams.get("s") || "").toLowerCase();
      // Un slug invalide ne doit pas casser l'affichage de la page :
      // on renvoie le pixel quand meme, sans rien enregistrer.
      if (!SLUG_OK.test(slug)) return pixel();

      const cle = `v:${slug}`;
      const maintenant = new Date().toISOString();
      try {
        const brut = await env.COMPTEUR.get(cle);
        const donnee = brut ? JSON.parse(brut) : { n: 0, premiere: maintenant };
        donnee.n += 1;
        donnee.derniere = maintenant;
        await env.COMPTEUR.put(cle, JSON.stringify(donnee));
      } catch (e) {
        // Mieux vaut perdre une vue qu'afficher une image cassee.
      }
      return pixel();
    }

    if (url.pathname === "/stats") {
      const attendu = env.TOKEN || "";
      const recu = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
      if (!attendu || recu !== attendu) {
        return new Response(JSON.stringify({ erreur: "jeton invalide" }), {
          status: 401, headers: { "Content-Type": "application/json" },
        });
      }
      const out = {};
      let curseur;
      do {
        const lot = await env.COMPTEUR.list({ prefix: "v:", cursor: curseur });
        for (const k of lot.keys) {
          const brut = await env.COMPTEUR.get(k.name);
          if (brut) out[k.name.slice(2)] = JSON.parse(brut);
        }
        curseur = lot.list_complete ? null : lot.cursor;
      } while (curseur);
      return new Response(JSON.stringify(out), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("compteur de demos — ok\n", {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  },
};
