#!/usr/bin/env python3
"""Gabarit « Signal » : quatre sections que les autres n'ont pas.

  bande horaire   La semaine en barres, avec un curseur « maintenant ».
                  Construite en Python depuis les horaires collectes, donc
                  lisible sans JavaScript ; le curseur seul est ajoute apres.
  symptome        Le visiteur choisit ce qui lui arrive, le message se
                  prepare tout seul et part en SMS ou declenche l'appel.
                  Aucune promesse : la page dit « on vous dira si c'est
                  faisable ici », elle n'affirme pas que ca l'est.
  parcours        Trois temps : vous appelez, on regarde, vous recuperez.
                  C'est une description du deroulement, pas un engagement
                  de delai -- aucun chiffre n'est avance.
  plan            Une vraie carte OpenStreetMap centree sur les coordonnees
                  relevees. Si elle ne charge pas, le panneau d'adresse
                  dessous reste affiche : la section ne casse jamais.
"""
from pathlib import Path

import gabarits as G

LAT, LON = 48.125452, -1.6667021
BBOX = f"{LON-0.006:.5f},{LAT-0.0035:.5f},{LON+0.006:.5f},{LAT+0.0035:.5f}"
CARTE = (f"https://www.openstreetmap.org/export/embed.html?bbox={BBOX}"
         f"&amp;layer=mapnik&amp;marker={LAT},{LON}")
CARTE_LIEN = f"https://www.openstreetmap.org/?mlat={LAT}&amp;mlon={LON}#map=17/{LAT}/{LON}"

DEBUT, FIN = 420, 1200          # la bande couvre 7h a 20h
COURTS = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
CRENEAUX = [None,
            [(480, 720), (840, 1140)], [(480, 720), (840, 1140)],
            [(480, 720), (840, 1140)], [(480, 720), (840, 1140)],
            [(480, 720), (840, 1110)], None]

SYMPTOMES = [
    "un voyant allumé au tableau de bord",
    "un bruit que la voiture ne faisait pas avant",
    "elle ne démarre pas",
    "les freins qui grincent",
    "une révision ou une vidange à faire",
    "une contre-visite à préparer",
]

ETAPES = [
    ("Vous appelez", "Vous décrivez ce qui se passe. Le numéro sonne à "
     "l'atelier, vous parlez à quelqu'un qui répare des voitures."),
    ("On regarde", "La voiture passe sur le pont. Ce qu'on trouve vous est "
     "dit avant qu'on touche à quoi que ce soit."),
    ("Vous récupérez", "Vous savez ce qui a été fait et pourquoi. Sans "
     "ligne de facture que personne ne sait expliquer."),
]


def bande():
    """La semaine en barres, calculee en Python : lisible sans JavaScript."""
    cols = []
    for j in range(1, 8):          # lundi -> dimanche
        i = j % 7
        cr = CRENEAUX[i]
        if cr:
            barres = "".join(
                f'<i style="--a:{(a-DEBUT)/(FIN-DEBUT):.4f};'
                f'--h:{(b-a)/(FIN-DEBUT):.4f}"></i>' for a, b in cr)
            resume = f"{cr[0][0]//60}h–{cr[-1][1]//60}h" + (
                "30" if cr[-1][1] % 60 else "")
            etat = ""
        else:
            barres = '<i class="vide"></i>'
            resume = "Fermé"
            etat = " jour--off"
        cols.append(
            f'      <div class="jour{etat}" data-j="{i}">\n'
            f'        <span class="jour__p">{barres}</span>\n'
            f'        <span class="jour__n">{COURTS[i]}</span>\n'
            f'        <span class="jour__h">{resume}</span>\n'
            f'      </div>')
    reperes = "".join(
        f'<span style="--y:{(h*60-DEBUT)/(FIN-DEBUT):.4f}">{h}h</span>'
        for h in (8, 10, 12, 14, 16, 18, 20))
    return f"""<section class="sec sec--clair" id="semaine">
  <div class="sec__in">
    <div class="tete">
      <h2>La semaine d'un coup d'œil</h2>
      <p class="chapo">Les plages colorées sont les heures d'ouverture. Le trait
        qui traverse marque l'heure qu'il est chez vous, pour savoir tout de
        suite si l'atelier est joignable.</p>
    </div>
    <div class="sem">
      <div class="sem__h" aria-hidden="true">{reperes}</div>
      <div class="sem__g" id="sem">
{chr(10).join(cols)}
        <div class="sem__now" id="now" hidden><span>maintenant</span></div>
      </div>
    </div>
  </div>
</section>"""


def symptome():
    jetons = "\n".join(
        f'        <button class="jeton" type="button" aria-pressed="false"'
        f' data-t="{s}">{s[0].upper() + s[1:]}</button>' for s in SYMPTOMES)
    return f"""<section class="sec" id="symptome">
  <div class="sec__in">
    <div class="tete">
      <h2>Dites ce qui vous arrive</h2>
      <p class="chapo">Pas besoin de connaître le nom de la pièce. Choisissez
        ce qui correspond : le message se prépare tout seul, et on vous dira
        si c'est faisable ici.</p>
    </div>
    <div class="sym">
      <div class="sym__l">
{jetons}
      </div>
      <div class="sym__r">
        <p class="sym__e">Votre message</p>
        <p class="sym__m" id="msg" role="status" aria-live="polite"></p>
        <div class="sym__a">
          <a class="btn btn--c" href="tel:{G.TELB}">Appeler le {G.TEL}</a>
          <a class="btn btn--f" id="sms" href="sms:{G.TELB}">Envoyer en SMS</a>
        </div>
      </div>
    </div>
  </div>
</section>"""


def parcours():
    pas = "\n".join(
        f'      <li><b>{t}</b><p>{d}</p></li>' for t, d in ETAPES)
    return f"""<section class="sec sec--clair" id="parcours">
  <div class="sec__in">
    <div class="tete">
      <h2>Comment ça se passe</h2>
      <p class="chapo">Trois temps, sans mauvaise surprise entre les deux.
        Aucun délai n'est promis ici : il dépend de ce que la voiture a.</p>
    </div>
    <ol class="pas">
{pas}
    </ol>
  </div>
</section>"""


def plan():
    return f"""<section class="sec" id="plan">
  <div class="sec__in">
    <div class="tete">
      <h2>Où se trouve l'atelier</h2>
      <p class="chapo">{G.RUE}, à {G.VILLE}. Le point sur la carte est
        l'entrée de l'atelier.</p>
    </div>
    <div class="plan">
      <div class="plan__c" id="carte" data-src="{CARTE}">
        <div class="plan__q" aria-hidden="true"></div>
        <div class="plan__repli">
          <b>{G.RUE}</b>
          <span>{G.CP} {G.VILLE}</span>
          <button class="btn btn--c" type="button" id="voir-carte">Afficher le plan</button>
          <a href="{CARTE_LIEN}" rel="noreferrer">ou l'ouvrir sur OpenStreetMap</a>
        </div>
      </div>
      <div class="plan__i">
        <h3>Venir</h3>
        <address class="adr">{G.RUE}<br>{G.CP} {G.VILLE}</address>
        <a class="btn btn--c" href="{G.ITIN}">Ouvrir l'itinéraire</a>
        <a class="btn btn--o" href="tel:{G.TELB}">Appeler avant de passer</a>
        <p class="plan__n">Un appel avant de venir permet de savoir si le
          créneau est libre et si la pièce est en stock.</p>
      </div>
    </div>
  </div>
</section>"""


CSS = """
body{background:var(--encre);color:var(--brume-clair)}
.sec{padding:var(--s8) var(--s5)}
@media (min-width:760px){.sec{padding:var(--s9) var(--s6)}}
.sec--clair{background:var(--papier);color:var(--encre)}
.sec__in{max-width:var(--large);margin-inline:auto}
.tete{display:grid;gap:var(--s4)}
@media (min-width:1000px){.tete{grid-template-columns:1.02fr .98fr;
  column-gap:56px;align-items:end}}
.tete h2{font-size:clamp(28px,4.2vw,44px);letter-spacing:-.032em;max-width:20ch;
  text-wrap:balance}
.chapo{font-size:18px;max-width:54ch;color:var(--texte)}
.sec:not(.sec--clair) .tete h2{color:var(--blanc)}
.sec:not(.sec--clair) .chapo{color:var(--brume)}
.sec:not(.sec--clair){--aide:var(--brume)}

/* ---- hero ---- */
.sig{padding:var(--s7) var(--s5) var(--s8);position:relative;overflow:hidden}
@media (min-width:760px){.sig{padding:var(--s8) var(--s6)}}
.hero__tread{position:absolute;inset:0;pointer-events:none;opacity:.7;
  background-image:repeating-radial-gradient(circle at 88% 6%,
    rgba(255,255,255,.09) 0 2px,transparent 2px 18px);
  mask-image:radial-gradient(62% 62% at 88% 6%,#000 55%,transparent 80%);
  -webkit-mask-image:radial-gradient(62% 62% at 88% 6%,#000 55%,transparent 80%)}
.sig__in{position:relative;max-width:var(--large);margin-inline:auto}
.sig__k{font-size:15px;font-weight:700;color:var(--cuivre)}
.sig h1{font-size:clamp(36px,6.4vw,68px);margin-top:var(--s4);color:var(--blanc);
  letter-spacing:-.04em;max-width:15ch;text-wrap:balance}
.sig__t{margin-top:var(--s5);font-size:19px;color:var(--brume);max-width:46ch}
.pave{display:grid;gap:var(--s4);margin-top:var(--s7)}
@media (min-width:860px){.pave{grid-template-columns:1.15fr .85fr;gap:var(--s6);
  align-items:stretch}}
.pave__a,.pave__b{background:var(--encre-2);border:1px solid var(--bord-sombre);
  border-radius:var(--r);padding:var(--s5)}
@media (min-width:760px){.pave__a,.pave__b{padding:var(--s6)}}
.pave__a{display:flex;flex-direction:column;justify-content:center}
.pave__lab{font-size:14px;font-weight:700;color:var(--brume)}
.pave__tel{display:inline-block;margin-top:var(--s2);font-size:clamp(30px,4.6vw,46px);
  font-weight:800;letter-spacing:-.04em;color:var(--cuivre);text-decoration:none;
  font-variant-numeric:tabular-nums;line-height:1.1}
.pave__tel:hover{filter:brightness(1.12)}
.pave__a .etat{display:block;margin-top:var(--s3);font-size:17px}
.pave__a .btn{margin-top:var(--s5);align-self:flex-start}
.pave__b dl{margin:0;display:grid;gap:var(--s4)}
.pave__b dt{font-size:13px;font-weight:700;color:var(--brume)}
.pave__b dd{margin:2px 0 0;font-weight:700;color:var(--blanc);font-size:16px;
  line-height:1.5}
.etat--oui{color:#7BD4A4}
.sec:not(.sec--clair) .etat--non,.sig .etat--non{color:var(--brume-clair)}

/* ---- bande horaire ---- */
.sem{--piste:236px;margin-top:var(--s7);display:grid;
  grid-template-columns:auto 1fr;gap:var(--s4);align-items:start}
.sem__h{position:relative;width:34px;height:var(--piste);font-size:12px;
  color:var(--texte-2);font-variant-numeric:tabular-nums}
.sem__h span{position:absolute;top:calc(var(--y) * var(--piste));right:0;
  transform:translateY(-50%)}
.sem__g{position:relative;display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
@media (min-width:600px){.sem__g{gap:10px}}
.jour{position:relative;display:flex;flex-direction:column}
.jour__p{position:relative;height:var(--piste);flex:none;
  background:var(--papier-2);border-radius:8px;overflow:hidden}
.jour__p i{position:absolute;left:0;right:0;top:calc(var(--a) * var(--piste));
  height:calc(var(--h) * var(--piste));background:var(--cuivre);
  border-radius:6px;display:block}
.jour__p i.vide{position:static;height:100%;background:repeating-linear-gradient(
  135deg,var(--papier-2) 0 7px,var(--bord) 7px 8px);border-radius:8px}
.jour__n{margin-top:10px;font-size:14px;font-weight:700;text-align:center}
.jour__h{font-size:12px;color:var(--texte-2);text-align:center;
  font-variant-numeric:tabular-nums}
.jour--off .jour__n,.jour--off .jour__h{color:var(--texte-2)}
.jour--auj .jour__n{color:var(--cuivre-sombre)}
.jour--auj .jour__p{box-shadow:0 0 0 2px var(--cuivre-sombre)}
.sem__now{position:absolute;left:0;right:0;top:calc(var(--y) * var(--piste));
  height:2px;
  background:var(--encre);z-index:2;pointer-events:none}
.sem__now span{position:absolute;right:0;top:-9px;font-size:11px;font-weight:700;
  background:var(--encre);color:var(--papier);padding:2px 7px;border-radius:5px}

/* ---- symptome ---- */
.sym{margin-top:var(--s7);display:grid;gap:var(--s5)}
@media (min-width:920px){.sym{grid-template-columns:1.1fr .9fr;gap:var(--s6);
  align-items:start}}
.sym__l{display:flex;flex-wrap:wrap;gap:10px;align-content:flex-start}
.jeton{font:inherit;font-size:15px;font-weight:650;color:var(--brume-clair);
  background:transparent;border:1px solid var(--bord-sombre);border-radius:999px;
  padding:11px 18px;cursor:pointer;min-height:44px;
  transition:border-color .15s,color .15s,background-color .15s}
.jeton:hover{border-color:var(--brume)}
.jeton[aria-pressed="true"]{background:var(--cuivre);color:var(--txt-accent);
  border-color:var(--cuivre)}
.sym__r{background:var(--encre-2);border:1px solid var(--bord-sombre);
  border-radius:var(--r);padding:var(--s5)}
@media (min-width:760px){.sym__r{padding:var(--s6)}}
.sym__e{font-size:13px;font-weight:700;color:var(--brume)}
.sym__m{margin-top:var(--s3);font-size:17px;line-height:1.6;color:var(--blanc);
  min-height:5.4em}
.sym__a{display:flex;flex-wrap:wrap;gap:var(--s3);margin-top:var(--s5)}
.sym__a .btn{flex:1 1 180px}

/* ---- parcours ---- */
.pas{list-style:none;margin:var(--s7) 0 0;padding:0;display:grid;gap:var(--s6);
  counter-reset:p}
@media (min-width:860px){.pas{grid-template-columns:repeat(3,1fr);gap:var(--s7)}}
.pas li{counter-increment:p;position:relative;padding-top:var(--s6)}
.pas li::before{content:counter(p);position:absolute;top:0;left:0;
  width:38px;height:38px;border-radius:50%;display:grid;place-items:center;
  background:var(--cuivre);color:var(--txt-accent);font-weight:800;font-size:16px}
@media (min-width:860px){.pas li:not(:last-child)::after{content:"";position:absolute;
  top:19px;left:50px;right:calc(var(--s7) * -1 + 8px);height:1px;background:var(--bord)}}
.pas b{display:block;font-size:21px;letter-spacing:-.015em}
.pas p{margin-top:var(--s3);color:var(--texte);font-size:16px;max-width:38ch}

/* ---- plan ---- */
.plan{margin-top:var(--s7);display:grid;gap:var(--s5)}
@media (min-width:920px){.plan{grid-template-columns:1.35fr .65fr;gap:var(--s6);
  align-items:stretch}}
.plan__c{position:relative;min-height:340px;border-radius:var(--r);
  overflow:hidden;border:1px solid var(--bord-sombre);background:var(--encre-2)}
.plan__q{position:absolute;inset:0;opacity:.5;
  background-image:linear-gradient(var(--bord-sombre) 1px,transparent 1px),
    linear-gradient(90deg,var(--bord-sombre) 1px,transparent 1px);
  background-size:48px 48px;
  mask-image:radial-gradient(80% 80% at 50% 50%,#000 20%,transparent 78%);
  -webkit-mask-image:radial-gradient(80% 80% at 50% 50%,#000 20%,transparent 78%)}
.plan__repli{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:10px;text-align:center;
  padding:var(--s5)}
.plan__repli b{font-size:19px;color:var(--blanc)}
.plan__repli span{color:var(--brume)}
.plan__repli a{color:var(--cuivre);font-weight:700;font-size:14px}
.plan__f{position:absolute;inset:0;width:100%;height:100%;border:0;display:block}
.plan__i{background:var(--encre-2);border:1px solid var(--bord-sombre);
  border-radius:var(--r);padding:var(--s5);display:flex;flex-direction:column}
@media (min-width:760px){.plan__i{padding:var(--s6)}}
.plan__i h3{font-size:20px;color:var(--blanc)}
.adr{font-style:normal;margin-top:var(--s3);font-size:17px;font-weight:700;
  color:var(--blanc);line-height:1.5}
.plan__i .btn{margin-top:var(--s4)}
.plan__i .btn--o{border-color:var(--bord-sombre);color:var(--brume-clair)}
.plan__i .btn--o:hover{border-color:var(--brume)}
.plan__n{margin-top:auto;padding-top:var(--s5);font-size:14px;color:var(--brume)}

/* ---- contact ---- */
.sec--clair .f input,.sec--clair .f textarea{background:var(--blanc)}
.ch{display:grid;gap:var(--s4)}
@media (min-width:560px){.ch{grid-template-columns:1fr 1fr}}
.duo{display:grid;gap:var(--s6);margin-top:var(--s7)}
@media (min-width:860px){.duo{grid-template-columns:1fr 1fr;gap:var(--s8)}}
.duo h3{font-size:21px;margin-bottom:var(--s4)}

/* ---- pied ---- */
.piedf{background:var(--encre);color:var(--brume);padding:var(--s7) var(--s5);
  font-size:14px;border-top:1px solid var(--bord-sombre)}
@media (min-width:760px){.piedf{padding:var(--s7) var(--s6)}}
.piedf__in{max-width:var(--large);margin-inline:auto;display:flex;
  flex-wrap:wrap;gap:var(--s4);justify-content:space-between}

/* ---- barre d'appel mobile ---- */
.bmob{position:fixed;left:0;right:0;bottom:0;z-index:40;display:grid;
  grid-template-columns:1fr auto;gap:10px;padding:10px 14px
  calc(10px + env(safe-area-inset-bottom));
  background:rgba(16,26,46,.97);border-top:1px solid var(--bord-sombre)}
.bmob .btn{padding:12px var(--s4);font-size:15px;min-height:46px}
@media (min-width:860px){.bmob{display:none}}
@media (max-width:859px){body{padding-bottom:84px}}
"""

JS = """
// Bande horaire : la colonne du jour se marque, et le trait « maintenant »
// se place s'il tombe dans la plage affichee (7h-20h).
(function(){
  var g=document.getElementById("sem"); if(!g) return;
  var d=new Date(), j=d.getDay(), m=d.getHours()*60+d.getMinutes();
  var c=g.querySelector('[data-j="'+j+'"]'); if(c) c.classList.add("jour--auj");
  var n=document.getElementById("now"); if(!n) return;
  if(m<420||m>1200) return;
  n.style.setProperty("--y",((m-420)/780).toFixed(4));
  n.hidden=false;
})();

// La carte ne se charge qu'au clic : la page reste legere, rien n'est
// demande a OpenStreetMap tant que le visiteur ne l'a pas voulu, et si le
// service est injoignable le panneau d'adresse reste ce qu'on voit.
(function(){
  var b=document.getElementById("voir-carte"), c=document.getElementById("carte");
  if(!b||!c) return;
  b.addEventListener("click",function(){
    var f=document.createElement("iframe");
    f.className="plan__f"; f.title="Plan d'acces a l'atelier";
    f.setAttribute("loading","lazy"); f.src=c.getAttribute("data-src");
    c.appendChild(f);
  });
})();

// Choix des symptomes : le message se compose tout seul.
(function(){
  var l=document.querySelectorAll(".jeton"), m=document.getElementById("msg"),
      s=document.getElementById("sms");
  if(!l.length||!m) return;
  var BASE="Bonjour, je vous contacte au sujet de ma voiture";
  function refaire(){
    var pris=[];
    l.forEach(function(b){ if(b.getAttribute("aria-pressed")==="true")
      pris.push(b.getAttribute("data-t")); });
    var t;
    if(!pris.length) t=BASE+". Sélectionnez ce qui vous arrive pour préparer le message.";
    else if(pris.length===1) t=BASE+" : "+pris[0]+". Est-ce que c'est quelque chose que vous prenez ?";
    else t=BASE+" : "+pris.slice(0,-1).join(", ")+" et "+pris[pris.length-1]
         +". Est-ce que c'est quelque chose que vous prenez ?";
    m.textContent=t;
    if(s) s.setAttribute("href","sms:TELB?body="+encodeURIComponent(t));
  }
  l.forEach(function(b){ b.addEventListener("click",function(){
    b.setAttribute("aria-pressed", b.getAttribute("aria-pressed")==="true"?"false":"true");
    refaire(); }); });
  refaire();
})();
"""


def signal():
    return G.tete(
        f"{G.NOM} — entretien et réparation mécanique à {G.VILLE}",
        f"{G.NOM}, garage indépendant au {G.RUE} à {G.VILLE} ({G.CP}). "
        f"Entretien courant et réparation mécanique. Ouvert du lundi au "
        f"vendredi. {G.TEL}.",
        CSS, "Manrope") + f"""
<main id="principal">
<section class="sig">
  <div class="hero__tread" aria-hidden="true"></div>
  <div class="sig__in">
    <p class="sig__k">Garage indépendant, à {G.VILLE}</p>
    <h1>Un atelier qui répond, et qui explique.</h1>
    <p class="sig__t">Entretien courant et réparation mécanique,
      {G.RUE}. Vous parlez au mécanicien, pas à un standard.</p>

    <div class="pave">
      <div class="pave__a">
        <span class="pave__lab">Un seul numéro</span>
        <a class="pave__tel" href="tel:{G.TELB}">{G.TEL}</a>
        <span class="etat" id="etat" data-h='{G.DATA_H}'>Du lundi au vendredi, 8h–12h et 14h–19h.</span>
        <a class="btn btn--f" href="#symptome">Préparer mon message</a>
      </div>
      <div class="pave__b">
        <dl>
          <div><dt>Adresse</dt><dd>{G.RUE}<br>{G.CP} {G.VILLE}</dd></div>
          <div><dt>Ouvert</dt><dd>Du lundi au vendredi</dd></div>
          <div><dt>Fermé</dt><dd>Samedi, dimanche et jours fériés</dd></div>
        </dl>
      </div>
    </div>
  </div>
</section>

{bande()}

{symptome()}

{parcours()}

{plan()}

<section class="sec sec--clair" id="contact">
  <div class="sec__in">
    <div class="tete">
      <h2>Ou laissez vos coordonnées</h2>
      <p class="chapo">Si vous préférez ne pas appeler tout de suite : votre
        nom, votre numéro, deux lignes. C'est tout ce qu'il faut.</p>
    </div>
    <div class="duo">
      <div>
        <h3>Horaires</h3>
        {G.tableau_horaires()}
      </div>
      <div>
        <h3>Votre demande</h3>
        {G.FORMULAIRE}
      </div>
    </div>
  </div>
</section>
</main>

<div class="bmob">
  <a class="btn btn--c" href="tel:{G.TELB}">Appeler l'atelier</a>
  <a class="btn btn--f" href="#symptome">Décrire</a>
</div>

<footer class="piedf">
  <div class="piedf__in">
    <span>© 2026 {G.NOM}</span>
    <span>{G.RUE}, {G.CP} {G.VILLE} — {G.TEL}</span>
  </div>
</footer>
""" + G.pied(JS.replace("TELB", G.TELB))


if __name__ == "__main__":
    p = Path("travail/gab-signal.html")
    p.write_text(signal(), encoding="utf-8")
    print(f"  {p}  {len(p.read_text(encoding='utf-8'))//1024} Ko")
