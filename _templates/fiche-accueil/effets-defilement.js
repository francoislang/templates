/* effets-defilement — l'observateur qui construit la page a la descente.
   Il n'ajoute la classe masquante (.rvl) que s'il peut garantir de la
   retirer : sans IntersectionObserver, ou si le mouvement reduit est
   demande, le script ne touche a rien. Une fois un element revele, ses
   classes lui sont retirees : il retrouve son etat naturel, et ne
   rejoue jamais quand on remonte. */
(function(){
  "use strict";
  var D = document;
  if (!("IntersectionObserver" in window) || !window.requestAnimationFrame) return;
  try {
    if (window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  } catch (e) { return; }

  /* [selecteur, glissement] — le decalage se calcule par parent, donc
     chaque groupe (les trois chiffres du bandeau, les lignes du
     registre, les lignes d'horaires) repart de zero. */
  var LOTS = [
    [".ouv__in > div > *", 1],
    [".fiche",             0],   /* deja inclinee : opacite seule */
    [".faits__g > div",    1],
    [".puces > li",        1],
    [".tete > *",          1],
    [".reg > li",          1],
    [".reg__f",            1],
    [".pan > *:not(.hor)", 1],
    [".hor > div",         1],
    [".ctc > div > *",     1],
    [".ctc > .form",       0],
    [".pied__in > span",   1]
  ];
  var DMAX = 4;                 /* quatre crans de 35 ms, pas davantage */
  var MARGE = 48;               /* on declenche 48 px avant le bas */
  var CLS = ["rvl","rvl--g","rvl--on","rvl--d1","rvl--d2","rvl--d3","rvl--d4"];
  var suivis = [], raf = 0;

  function finir(el){
    for (var i = 0; i < CLS.length; i++) el.classList.remove(CLS[i]);
  }
  function oter(el){
    var k = suivis.indexOf(el);
    if (k >= 0) suivis.splice(k, 1);
  }
  function montrer(el){
    oter(el);
    el.classList.add("rvl--on");
    /* 140 ms de decalage + 380 ms de transition : 700 ms de marge */
    setTimeout(function(){ finir(el); }, 700);
  }
  function tout(){
    while (suivis.length){ var el = suivis[0]; obs.unobserve(el); oter(el); finir(el); }
  }

  var obs = new IntersectionObserver(function(entrees){
    for (var i = 0; i < entrees.length; i++){
      if (!entrees[i].isIntersecting) continue;
      obs.unobserve(entrees[i].target);
      montrer(entrees[i].target);
    }
  }, { rootMargin: "0px 0px -" + MARGE + "px 0px", threshold: 0 });

  /* Filet : la marge negative cree une zone morte de 48 px tout en bas
     du document, ou l'observateur ne se declenche plus. Des que le bas
     est atteint (ou que la fenetre est plus haute que la page), on
     revele ce qui y reste — aucun contenu ne peut rester transparent. */
  function balayer(){
    raf = 0;
    if (!suivis.length) return;
    var de = D.documentElement, vh = window.innerHeight || de.clientHeight;
    if ((window.pageYOffset || de.scrollTop) + vh < de.scrollHeight - 2) return;
    for (var i = suivis.length - 1; i >= 0; i--){
      var el = suivis[i];
      if (el.getBoundingClientRect().top < vh){ obs.unobserve(el); montrer(el); }
    }
  }
  function planifier(){ if (!raf) raf = requestAnimationFrame(balayer); }

  for (var l = 0; l < LOTS.length; l++){
    var noeuds = D.querySelectorAll(LOTS[l][0]), parents = [], comptes = [];
    for (var n = 0; n < noeuds.length; n++){
      var el = noeuds[n];
      if (el.classList.contains("rvl")) continue;
      var p = el.parentElement, k = parents.indexOf(p), rang;
      if (k < 0){ parents.push(p); comptes.push(1); rang = 0; }
      else { rang = comptes[k]; comptes[k] = rang + 1; }
      el.classList.add("rvl");
      if (LOTS[l][1]) el.classList.add("rvl--g");
      if (rang > 0) el.classList.add("rvl--d" + (rang < DMAX ? rang : DMAX));
      suivis.push(el);
      obs.observe(el);
    }
  }

  window.addEventListener("scroll", planifier, { passive: true });
  window.addEventListener("resize", planifier);
  window.addEventListener("beforeprint", tout);   /* a l'impression, tout est la */
  planifier();                                    /* page plus courte que la fenetre */
})();
