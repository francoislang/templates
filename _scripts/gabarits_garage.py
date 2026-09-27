#!/usr/bin/env python3
"""Trois gabarits supplementaires, sur les memes faits verifies.

Chacun reprend les memes jetons de couleur que le gabarit « atelier », pour
que les dix identites visuelles de variantes.py s'appliquent telles quelles :
--encre, --encre-2, --cuivre, --cuivre-sombre, --txt-accent, --brume,
--brume-clair, --bord-fantome, plus les classes .btn--c, .band et
.hero__tread que la variante surcharge.
"""
from pathlib import Path

NOM = "Garage Patton"
VILLE = "Rennes"
CP = "35700"
RUE = "157 avenue du Général George S. Patton"
TEL = "02 99 36 18 08"
TELB = "+33299361808"
ITIN = ("https://www.google.com/maps/dir/?api=1&amp;destination="
        "157%20avenue%20du%20G%C3%A9n%C3%A9ral%20George%20S.%20Patton%2C%2035700%20Rennes")
DATA_H = ("[null,[480,720,840,1140],[480,720,840,1140],[480,720,840,1140],"
          "[480,720,840,1140],[480,720,840,1110],null]")

JOURS = [("Lundi", "8h–12h · 14h–19h"), ("Mardi", "8h–12h · 14h–19h"),
         ("Mercredi", "8h–12h · 14h–19h"), ("Jeudi", "8h–12h · 14h–19h"),
         ("Vendredi", "8h–12h · 14h–18h30"), ("Samedi", None),
         ("Dimanche", None)]

SERVICES = [
    ("Entretien courant",
     "Vidange, filtres, révision, pièces d'usure : ce qui se fait à échéance "
     "régulière pour qu'une voiture dure."),
    ("Réparation mécanique",
     "Chercher d'où vient la panne, puis la réparer. Le métier de base d'un "
     "atelier indépendant, et celui où parler au mécanicien change tout."),
    ("Le reste, au téléphone",
     "Plutôt qu'une liste qui promet tout, un numéro qui répond. Vous décrivez "
     "le problème, on vous dit si c'est faisable ici et quand."),
]

# --------------------------------------------------------------------- socle
JETONS = """:root{
  --encre:#101A2E; --encre-2:#182642; --cuivre:#E67E3D; --cuivre-sombre:#9C4712;
  --txt-accent:#1A1002; --brume:#93A1BC; --brume-clair:#C9D3E6;
  --bord-fantome:#526AA8; --papier:#F6F8FB; --papier-2:#EDF1F7;
  --blanc:#fff; --bord:#D2DAE8; --bord-sombre:#2C3B5C;
  --texte:#3F4C63; --texte-2:#5A6880;
  --r:14px; --r-s:10px;
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px;
  --s7:48px; --s8:64px; --s9:96px;
  --large:1180px;
  --police:'Inter';
  --aide:var(--texte-2);
}
*,*::before,*::after{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}
  *{animation-duration:.01ms !important;transition-duration:.01ms !important}}
body{margin:0;font-family:var(--police),ui-sans-serif,system-ui,-apple-system,
  'Segoe UI',Roboto,sans-serif;font-size:17px;line-height:1.62;
  color:var(--encre);background:var(--blanc);-webkit-font-smoothing:antialiased;
  overflow-x:clip}
h1,h2,h3{margin:0;line-height:1.14;letter-spacing:-.025em;font-weight:800}
p{margin:0}
a{color:inherit}
img,svg{max-width:100%}
:focus-visible{outline:3px solid var(--cuivre);outline-offset:3px;border-radius:5px}
.env{width:100%;max-width:var(--large);margin-inline:auto}
.saut{position:absolute;left:0;top:0;transform:translateY(-200%);z-index:200;
  background:var(--cuivre);color:var(--txt-accent);padding:12px 20px;
  font-weight:800;text-decoration:none;border-radius:0 0 var(--r-s) 0}
.saut:focus{transform:translateY(0)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:var(--s3);
  padding:15px var(--s6);border-radius:var(--r-s);font-weight:800;font-size:16px;
  text-decoration:none;border:2px solid transparent;cursor:pointer;
  font-family:inherit;min-height:48px;
  transition:transform .16s ease,background-color .16s ease,border-color .16s}
.btn:hover{transform:translateY(-2px)}
@media (prefers-reduced-motion:reduce){.btn:hover{transform:none}}
.btn--c{background:var(--cuivre);color:var(--txt-accent)}
.btn--c:hover{filter:brightness(1.07)}
.btn--o{border-color:var(--bord);color:var(--encre)}
.btn--o:hover{border-color:var(--encre)}
.btn--f{border-color:var(--bord-fantome);color:var(--blanc)}
.btn--f:hover{border-color:var(--brume-clair)}
.etat{font-weight:800}
.etat--oui{color:#18653F}
.etat--non{color:var(--texte-2)}
.hor{margin:0;border-top:1px solid var(--bord)}
.hor>div{display:flex;justify-content:space-between;gap:var(--s4);
  padding:11px 0;border-bottom:1px solid var(--bord);font-size:15px}
.hor dt{color:var(--texte);font-weight:600}
.hor dd{margin:0;font-weight:700;font-variant-numeric:tabular-nums}
.hor--off dd{font-weight:600;color:var(--texte-2)}
.hor--jour dt,.hor--jour dd{color:var(--cuivre-sombre)}
.f{display:flex;flex-direction:column;gap:6px}
.f label{font-size:14px;font-weight:700}
.f input,.f textarea,.f select{font:inherit;font-size:16px;padding:13px var(--s4);
  border:1px solid var(--bord);border-radius:var(--r-s);background:var(--blanc);
  color:var(--encre);width:100%}
.f input:focus-visible,.f textarea:focus-visible,.f select:focus-visible{
  outline:3px solid var(--cuivre);outline-offset:2px}
.fret{font-size:15px;font-weight:700}
"""

SCRIPTS = """
// Etat d'ouverture, lu depuis data-h sur #etat : sept entrees, dimanche en
// premier, minutes depuis minuit par paires, null si ferme. Sans donnee, la
// phrase de repli ecrite dans le HTML reste affichee.
(function(){
  var el=document.getElementById("etat"); if(!el) return;
  var h; try{ h=JSON.parse(el.getAttribute("data-h")); }catch(e){ return; }
  if(!Array.isArray(h)||h.length!==7) return;
  var J=["dimanche","lundi","mardi","mercredi","jeudi","vendredi","samedi"];
  function pr(x){var r=[],i; if(!x) return r;
    for(i=0;i+1<x.length;i+=2) r.push([x[i],x[i+1]]); return r;}
  function hm(v){var a=Math.floor(v/60),b=v%60;
    return b? a+"h"+(b<10?"0":"")+b : a+"h";}
  var d=new Date(),j=d.getDay(),m=d.getHours()*60+d.getMinutes(),i,k,jj,cs;
  var cj=pr(h[j]);
  for(i=0;i<cj.length;i++){ if(m>=cj[i][0]&&m<cj[i][1]){
    el.textContent="Ouvert maintenant, jusqu'à "+hm(cj[i][1]);
    el.className="etat etat--oui"; return; } }
  for(k=0;k<8;k++){ jj=(j+k)%7; cs=pr(h[jj]);
    for(i=0;i<cs.length;i++){ if(k===0&&cs[i][0]<=m) continue;
      el.textContent="Fermé, ouvre "+(k===0?"à "+hm(cs[i][0])
        :(k===1?"demain à ":J[jj]+" à ")+hm(cs[i][0]));
      el.className="etat etat--non"; return; } }
})();

// Souligner la ligne du jour : lundi est la premiere du tableau.
(function(){ var l=document.querySelectorAll(".hor > div"),j=new Date().getDay();
  if(l.length>=7) l[(j+6)%7].classList.add("hor--jour"); })();

// Le formulaire compose un SMS : aucune adresse electronique publique n'a ete
// trouvee pour cet atelier. On n'annonce pas un envoi reussi, parce que rien
// ne permet de le verifier depuis la page.
(function(){
  var f=document.getElementById("dem"); if(!f) return;
  f.addEventListener("submit",function(e){
    e.preventDefault();
    var n=f.nom.value.trim(), t=f.tel.value.trim(), d=f.det.value.trim();
    if(!n||!t){ document.getElementById("ret").textContent=
      "Merci d'indiquer au moins votre nom et votre numéro."; return; }
    var corps="Bonjour, "+n+" ("+t+")."+(d?" "+d:"");
    document.getElementById("ret").textContent=
      "Votre application de messages s'ouvre avec la demande préremplie. "
      +"Si rien ne se passe, appelez le """ + TEL + """.";
    window.location.href="sms:""" + TELB + """?body="+encodeURIComponent(corps);
  });
})();
"""


def tete(titre, desc, extra_css, police="Inter"):
    fam = police.replace(" ", "+")
    extra_css = f":root{{--police:'{police}'}}\n" + extra_css
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titre}</title>
<meta name="description" content="{desc}">
<meta name="theme-color" content="#101A2E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family={fam}:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
{JETONS}
{extra_css}
</style>
</head>
<body>
<a class="saut" href="#principal">Aller au contenu</a>
"""


def pied(extra_js=""):
    return f"""
<script>
{SCRIPTS}
{extra_js}
</script>
</body>
</html>
"""


def tableau_horaires():
    out = ['<dl class="hor">']
    for j, h in JOURS:
        if h:
            out.append(f"  <div><dt>{j}</dt><dd>{h}</dd></div>")
        else:
            out.append(f'  <div class="hor--off"><dt>{j}</dt><dd>Fermé</dd></div>')
    out.append('  <div class="hor--off"><dt>Jours fériés</dt><dd>Fermé</dd></div>')
    out.append("</dl>")
    return "\n".join(out)


FORMULAIRE = f"""<form id="dem" novalidate>
  <div class="ch">
    <div class="f"><label for="nom">Votre nom</label>
      <input id="nom" name="nom" type="text" autocomplete="name" required
             placeholder="Camille Renard"></div>
    <div class="f"><label for="tel">Votre téléphone</label>
      <input id="tel" name="tel" type="tel" inputmode="tel" autocomplete="tel"
             required placeholder="06 12 34 56 78"></div>
  </div>
  <div class="f" style="margin-top:var(--s4)">
    <label for="det">Ce qui vous amène</label>
    <textarea id="det" name="det" rows="3"
              placeholder="Voyant moteur allumé depuis hier sur une Clio de 2016."></textarea>
  </div>
  <button class="btn btn--c" type="submit"
          style="width:100%;margin-top:var(--s5)">Envoyer ma demande</button>
  <p class="fret" id="ret" role="status" aria-live="polite"
     style="margin-top:var(--s3)"></p>
  <p style="margin-top:var(--s3);font-size:14px;color:var(--aide)">
    Aucune adresse électronique publique n'a été trouvée pour cet atelier :
    le bouton ouvre un SMS prérempli vers le {TEL}.</p>
</form>"""


# ====================================================================== FICHE
CSS_FICHE = """
body{background:var(--papier)}
.ficheh{--aide:var(--brume)}
.ficheh{background:var(--encre);color:var(--blanc);padding:var(--s6) var(--s5) var(--s7)}
@media (min-width:760px){.ficheh{padding:var(--s7) var(--s6) var(--s8)}}
.ficheh__in{max-width:760px;margin-inline:auto}
.eyebrow{font-size:15px;font-weight:700;color:var(--cuivre)}
.ficheh h1{font-size:clamp(32px,6vw,50px);margin-top:var(--s3);color:var(--blanc);
  text-wrap:balance}
.ficheh__t{margin-top:var(--s4);color:var(--brume-clair);font-size:18px;max-width:42ch}
.ficheh__a{display:flex;flex-wrap:wrap;gap:var(--s3);margin-top:var(--s6)}
.ficheh__a .btn{flex:1 1 200px}
.corps{max-width:760px;margin:calc(var(--s7) * -1) auto var(--s8);
  padding-inline:var(--s5);display:grid;gap:var(--s4)}
@media (min-width:760px){.corps{padding-inline:var(--s6)}}
.bloc{background:var(--blanc);border:1px solid var(--bord);border-radius:var(--r);
  padding:var(--s5)}
@media (min-width:760px){.bloc{padding:var(--s6)}}
.bloc h2{font-size:22px}
.bloc>*+*{margin-top:var(--s4)}
.lig{display:flex;gap:var(--s4);align-items:baseline;justify-content:space-between;
  padding:12px 0;border-bottom:1px solid var(--bord);font-size:15px}
.lig:last-child{border-bottom:0;padding-bottom:0}
.lig b{font-size:17px;text-align:right}
.serv{display:grid;gap:var(--s4)}
.serv>div{padding-left:var(--s4);border-left:2px solid var(--cuivre-sombre)}
.serv h3{font-size:18px}
.serv p{margin-top:6px;color:var(--texte);font-size:15px;max-width:58ch}
.bloc p{max-width:58ch}
.ch{display:grid;gap:var(--s4)}
@media (min-width:560px){.ch{grid-template-columns:1fr 1fr}}
.piedf{max-width:760px;margin:0 auto;padding:0 var(--s5) var(--s8);
  color:var(--texte-2);font-size:14px}
"""

def fiche():
    serv = "\n".join(
        f"        <div><h3>{t}</h3><p>{d}</p></div>" for t, d in SERVICES)
    return tete(
        f"{NOM} — entretien et réparation mécanique à {VILLE}",
        f"{NOM}, garage indépendant au {RUE} à {VILLE} ({CP}). "
        f"Entretien courant et réparation mécanique. Ouvert du lundi au vendredi. {TEL}.",
        CSS_FICHE, "Libre Franklin") + f"""
<header class="ficheh">
  <div class="ficheh__in">
    <p class="eyebrow">Garage indépendant, à {VILLE}</p>
    <h1>{NOM}</h1>
    <p class="ficheh__t">Entretien courant et réparation mécanique,
      {RUE}. Un seul numéro, une réponse directe.</p>
    <div class="ficheh__a">
      <a class="btn btn--c" href="tel:{TELB}">Appeler le {TEL}</a>
      <a class="btn btn--f" href="#demande">Laisser une demande</a>
    </div>
  </div>
</header>

<main id="principal" class="corps">
  <section class="bloc">
    <h2>L'essentiel</h2>
    <div>
      <div class="lig"><span>Téléphone</span><b><a href="tel:{TELB}">{TEL}</a></b></div>
      <div class="lig"><span>Adresse</span><b>{RUE}<br>{CP} {VILLE}</b></div>
      <div class="lig"><span>Aujourd'hui</span>
        <b><span class="etat" id="etat" data-h='{DATA_H}'>Voir les horaires</span></b></div>
    </div>
    <a class="btn btn--o" href="{ITIN}" style="width:100%">Ouvrir l'itinéraire</a>
  </section>

  <section class="bloc">
    <h2>Horaires</h2>
    {tableau_horaires()}
  </section>

  <section class="bloc">
    <h2>Ce que l'atelier prend en charge</h2>
    <div class="serv">
{serv}
    </div>
  </section>

  <section class="bloc" id="demande">
    <h2>Laisser une demande</h2>
    {FORMULAIRE}
  </section>
</main>

<footer class="piedf">
  © 2026 {NOM} — {RUE}, {CP} {VILLE}
</footer>
""" + pied()


# ==================================================================== AFFICHE
CSS_AFFICHE = """
body{background:var(--encre);color:var(--blanc)}
.aff{padding:var(--s6) var(--s5) var(--s8);position:relative;overflow:hidden}
@media (min-width:760px){.aff{padding:var(--s7) var(--s6) var(--s9)}}
.hero__tread{position:absolute;inset:0;pointer-events:none;opacity:.6;
  background-image:repeating-radial-gradient(circle at 88% 6%,
    rgba(255,255,255,.09) 0 2px,transparent 2px 18px);
  mask-image:radial-gradient(62% 62% at 88% 6%,#000 55%,transparent 80%);
  -webkit-mask-image:radial-gradient(62% 62% at 88% 6%,#000 55%,transparent 80%)}
.aff__in{position:relative;max-width:var(--large);margin-inline:auto}
.kick{display:inline-block;font-size:16px;font-weight:700;color:var(--cuivre)}
.aff h1{font-size:clamp(46px,11vw,120px);line-height:.93;letter-spacing:-.045em;
  margin-top:var(--s5);color:var(--blanc);text-wrap:balance}
.aff__t{margin-top:var(--s5);font-size:clamp(18px,2.2vw,22px);color:var(--brume-clair);
  max-width:40ch}
.tel{display:inline-flex;align-items:center;gap:var(--s4);margin-top:var(--s7);
  font-size:clamp(28px,5.5vw,56px);font-weight:800;letter-spacing:-.04em;
  color:var(--cuivre);text-decoration:none;font-variant-numeric:tabular-nums;
  border-bottom:3px solid currentColor;padding-bottom:6px}
.tel:hover{filter:brightness(1.1)}
.sous{margin-top:var(--s4);font-size:16px;color:var(--brume)}
.aff{--aide:var(--brume)}
.aff .etat--non{color:var(--brume-clair)}
.aff .etat--oui{color:#7BD4A4}
.band{background:var(--cuivre);color:var(--txt-accent);padding:var(--s6) var(--s5)}
@media (min-width:760px){.band{padding:var(--s6)}}
.band__in{max-width:var(--large);margin-inline:auto;display:grid;gap:var(--s5);
  grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
.band dt{font-size:clamp(20px,2.6vw,28px);font-weight:800;letter-spacing:-.03em;
  line-height:1.1}
.band dd{margin:6px 0 0;font-size:14px;font-weight:700;line-height:1.45}
.sec{padding:var(--s8) var(--s5)}
@media (min-width:760px){.sec{padding:var(--s9) var(--s6)}}
.sec--clair{background:var(--papier);color:var(--encre)}
.sec__in{max-width:var(--large);margin-inline:auto}
.sec h2{font-size:clamp(30px,5vw,54px);letter-spacing:-.035em;text-wrap:balance;
  max-width:16ch}
.gros{display:grid;gap:var(--s6);margin-top:var(--s7);counter-reset:n}
@media (min-width:860px){.gros{grid-template-columns:repeat(3,1fr);gap:var(--s7)}}
.gros>div{counter-increment:n;padding-top:var(--s5);
  border-top:1px solid var(--bord)}
.gros>div::before{content:"0" counter(n);display:block;font-size:14px;
  font-weight:800;letter-spacing:.14em;color:var(--cuivre-sombre)}
.gros h3{font-size:26px;margin-top:var(--s3)}
.gros p{margin-top:var(--s3);color:var(--texte);font-size:16px}
.sec:not(.sec--clair){--aide:var(--brume)}
.sec:not(.sec--clair) .gros>div{border-top-color:var(--bord-sombre)}
.sec:not(.sec--clair) .gros>div::before{color:var(--cuivre)}
.sec:not(.sec--clair) .gros p,.sec:not(.sec--clair) .hor dt{color:var(--brume-clair)}
.sec:not(.sec--clair) .hor{border-top-color:var(--bord-sombre)}
.sec:not(.sec--clair) .hor>div{border-bottom-color:var(--bord-sombre)}
.sec:not(.sec--clair) .hor dd{color:var(--blanc)}
.sec:not(.sec--clair) .hor--off dd{color:var(--brume)}
.sec:not(.sec--clair) .hor--jour dt,.sec:not(.sec--clair) .hor--jour dd{color:var(--cuivre)}
.sec:not(.sec--clair) .etat--non{color:var(--brume-clair)}
.sec:not(.sec--clair) .etat--oui{color:#7BD4A4}
.sec:not(.sec--clair) .f input,.sec:not(.sec--clair) .f textarea{
  background:var(--encre-2);border-color:var(--bord-sombre);color:var(--blanc)}
.sec:not(.sec--clair) .fret{color:var(--brume-clair)}
.deux{display:grid;gap:var(--s7);margin-top:var(--s7)}
@media (min-width:900px){.deux{grid-template-columns:1fr 1fr;gap:var(--s8)}}
.deux h3{font-size:22px;margin-bottom:var(--s4)}
.ch{display:grid;gap:var(--s4)}
@media (min-width:560px){.ch{grid-template-columns:1fr 1fr}}
.piedf{background:var(--encre);color:var(--brume);padding:var(--s7) var(--s5);
  font-size:14px}
@media (min-width:760px){.piedf{padding:var(--s7) var(--s6)}}
.piedf__in{max-width:var(--large);margin-inline:auto;display:flex;
  flex-wrap:wrap;gap:var(--s4);justify-content:space-between}
"""

def affiche():
    gros = "\n".join(
        f"      <div><h3>{t}</h3><p>{d}</p></div>" for t, d in SERVICES)
    return tete(
        f"{NOM} — entretien et réparation mécanique à {VILLE}",
        f"{NOM}, garage indépendant au {RUE} à {VILLE} ({CP}). "
        f"Entretien courant et réparation mécanique. Ouvert du lundi au vendredi. {TEL}.",
        CSS_AFFICHE, "Archivo") + f"""
<main id="principal">
<section class="aff">
  <div class="hero__tread" aria-hidden="true"></div>
  <div class="aff__in">
    <p class="kick">Garage indépendant · {VILLE}</p>
    <h1>Un mécanicien<br>qui décroche.</h1>
    <p class="aff__t">Entretien courant et réparation mécanique,
      {RUE}, à {VILLE}.</p>
    <a class="tel" href="tel:{TELB}">{TEL}</a>
    <p class="sous"><span class="etat" id="etat" data-h='{DATA_H}'>Du lundi au vendredi, 8h–12h et 14h–19h.</span></p>
  </div>
</section>

<section class="band" aria-label="En bref">
  <dl class="band__in">
    <div><dt>Lun–ven</dt><dd>8h–12h puis 14h, jusqu'à 19h</dd></div>
    <div><dt>{VILLE}</dt><dd>{RUE}, {CP}</dd></div>
    <div><dt>Sans standard</dt><dd>Le numéro tombe directement à l'atelier</dd></div>
  </dl>
</section>

<section class="sec sec--clair">
  <div class="sec__in">
    <h2>Ce que l'atelier prend en charge</h2>
    <div class="gros">
{gros}
    </div>
  </div>
</section>

<section class="sec">
  <div class="sec__in">
    <h2>Horaires, accès et demande</h2>
    <div class="deux">
      <div>
        <h3>Horaires d'ouverture</h3>
        {tableau_horaires()}
        <p style="margin-top:var(--s5)"><a class="btn btn--c" href="{ITIN}">Ouvrir l'itinéraire</a></p>
      </div>
      <div>
        <h3>Laisser une demande</h3>
        {FORMULAIRE}
      </div>
    </div>
  </div>
</section>
</main>

<footer class="piedf">
  <div class="piedf__in">
    <span>© 2026 {NOM}</span>
    <span>{RUE}, {CP} {VILLE} — {TEL}</span>
  </div>
</footer>
""" + pied()


# =================================================================== COMPTOIR
CSS_COMPTOIR = """
body{background:var(--blanc)}
.top{border-bottom:1px solid var(--bord);background:var(--blanc);
  position:sticky;top:0;z-index:20;padding:0 var(--s5)}
@media (min-width:760px){.top{padding:0 var(--s6)}}
.top__in{max-width:var(--large);margin-inline:auto;display:flex;
  align-items:center;gap:var(--s5);min-height:68px}
.mq{font-weight:800;font-size:18px;letter-spacing:-.02em;text-decoration:none}
.mq span{display:block;font-size:13px;font-weight:600;color:var(--texte-2)}
.top .btn{margin-left:auto;padding:11px var(--s5);font-size:15px;min-height:44px}
.cadre{padding:var(--s7) var(--s5) var(--s8)}
@media (min-width:760px){.cadre{padding:var(--s8) var(--s6) var(--s9)}}
.cadre__in{max-width:var(--large);margin-inline:auto;display:grid;gap:var(--s7)}
@media (min-width:980px){.cadre__in{grid-template-columns:1fr 380px;gap:var(--s8);
  align-items:start}}
.intro h1{font-size:clamp(32px,4.6vw,52px);text-wrap:balance;max-width:18ch}
.intro__t{margin-top:var(--s5);font-size:19px;color:var(--texte);max-width:54ch}
.tbl{width:100%;border-collapse:collapse;margin-top:var(--s7)}
.tbl caption{text-align:left;font-size:16px;font-weight:700;
  color:var(--texte-2);padding-bottom:var(--s4)}
.tbl th{text-align:left;font-size:19px;font-weight:800;padding:var(--s5) var(--s4) var(--s3) 0;
  border-top:1px solid var(--bord);width:34%;vertical-align:top}
.tbl td{padding:var(--s5) 0 var(--s3);border-top:1px solid var(--bord);
  color:var(--texte);font-size:16px;vertical-align:top}
@media (max-width:660px){.tbl th,.tbl td{display:block;width:auto;border-top:0;padding:0}
  .tbl th{border-top:1px solid var(--bord);padding-top:var(--s5)}
  .tbl td{padding:6px 0 var(--s5)}}
.rail{background:var(--papier);border:1px solid var(--bord);border-radius:var(--r);
  padding:var(--s5)}
@media (min-width:980px){.rail{position:sticky;top:92px;padding:var(--s6)}}
.rail h2{font-size:20px}
.rail__tel{display:block;margin-top:var(--s4);font-size:27px;font-weight:800;
  letter-spacing:-.03em;text-decoration:none;font-variant-numeric:tabular-nums}
.rail__tel:hover{color:var(--cuivre-sombre)}
.rail .etat{display:block;margin-top:var(--s2);font-size:15px}
.rail .btn{width:100%;margin-top:var(--s5)}
.rail .hor{margin-top:var(--s5)}
.adr{font-style:normal;margin-top:var(--s5);padding-top:var(--s5);
  border-top:1px solid var(--bord);font-size:15px;line-height:1.55;color:var(--texte)}
.bas{background:var(--encre);color:var(--brume-clair);padding:var(--s8) var(--s5)}
@media (min-width:760px){.bas{padding:var(--s8) var(--s6)}}
.bas__in{max-width:var(--large);margin-inline:auto;display:grid;gap:var(--s6)}
@media (min-width:860px){.bas__in{grid-template-columns:1fr 1fr;gap:var(--s8)}}
.bas h2{font-size:clamp(26px,3.4vw,38px);color:var(--blanc);max-width:16ch}
.bas p{margin-top:var(--s4);max-width:46ch}
.bas .f label{color:var(--blanc)}
.bas .f input,.bas .f textarea{background:var(--encre-2);border-color:var(--bord-sombre);
  color:var(--blanc)}
.bas .fret{color:var(--brume-clair)}
.bas{--aide:var(--brume-clair)}
.bas .etat--non{color:var(--brume-clair)}
.ch{display:grid;gap:var(--s4)}
@media (min-width:560px){.ch{grid-template-columns:1fr 1fr}}
.piedf{background:var(--encre);color:var(--brume);padding:0 var(--s5) var(--s7);
  font-size:14px}
@media (min-width:760px){.piedf{padding:0 var(--s6) var(--s7)}}
.piedf__in{max-width:var(--large);margin-inline:auto;border-top:1px solid var(--bord-sombre);
  padding-top:var(--s5)}
"""

def comptoir():
    lignes = "\n".join(
        f"      <tr><th scope=\"row\">{t}</th><td>{d}</td></tr>" for t, d in SERVICES)
    return tete(
        f"{NOM} — entretien et réparation mécanique à {VILLE}",
        f"{NOM}, garage indépendant au {RUE} à {VILLE} ({CP}). "
        f"Entretien courant et réparation mécanique. Ouvert du lundi au vendredi. {TEL}.",
        CSS_COMPTOIR, "Manrope") + f"""
<header class="top">
  <div class="top__in">
    <a class="mq" href="#principal">{NOM}<span>{VILLE}</span></a>
    <a class="btn btn--c" href="tel:{TELB}">Appeler le {TEL}</a>
  </div>
</header>

<main id="principal" class="cadre">
  <div class="cadre__in">
    <div class="intro">
      <h1>Un atelier indépendant, à l'est de {VILLE}.</h1>
      <p class="intro__t">Vous parlez au mécanicien qui ouvrira le capot.
        Pas de standard, pas de centre d'appel : le numéro ci-contre sonne
        à l'atelier, {RUE}.</p>

      <table class="tbl">
        <caption>Ce que l'atelier prend en charge</caption>
        <tbody>
{lignes}
        </tbody>
      </table>
    </div>

    <aside class="rail" aria-label="Contact et horaires">
      <h2>Joindre l'atelier</h2>
      <a class="rail__tel" href="tel:{TELB}">{TEL}</a>
      <span class="etat" id="etat" data-h='{DATA_H}'>Du lundi au vendredi, 8h–12h et 14h–19h.</span>
      <a class="btn btn--c" href="tel:{TELB}">Appeler maintenant</a>
      <a class="btn btn--o" href="{ITIN}">Ouvrir l'itinéraire</a>
      {tableau_horaires()}
      <address class="adr">{RUE}<br>{CP} {VILLE}</address>
    </aside>
  </div>
</main>

<section class="bas">
  <div class="bas__in">
    <div>
      <h2>Décrivez le problème, on vous rappelle</h2>
      <p>Un voyant, un bruit, une révision qui tombe : laissez votre numéro et
         deux lignes. C'est souvent plus rapide que de chercher soi-même.</p>
    </div>
    <div>{FORMULAIRE}</div>
  </div>
</section>

<footer class="piedf">
  <div class="piedf__in">© 2026 {NOM} — {RUE}, {CP} {VILLE} — {TEL}</div>
</footer>
""" + pied()


if __name__ == "__main__":
    d = Path("travail")
    for nom, f in (("fiche", fiche), ("affiche", affiche), ("comptoir", comptoir)):
        p = d / f"gab-{nom}.html"
        p.write_text(f(), encoding="utf-8")
        print(f"  {p}  {len(p.read_text(encoding='utf-8'))//1024} Ko")
