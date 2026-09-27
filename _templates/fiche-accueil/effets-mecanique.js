/* effets-mecanique.js — piste « mecanique et net »

   Le script ne fait que trois choses : poser la classe html.mec (sans
   laquelle aucun etat masque de la feuille n'existe, donc aucun contenu
   ne peut rester invisible si ce fichier ne tourne pas), distribuer les
   crans et les volets, puis les declencher a l'approche.

   Trois filets de securite : mouvement reduit = tout ouvert d'emblee,
   pas d'IntersectionObserver = tout ouvert d'emblee, et un delai de
   1600 ms qui ouvre ce qui n'aurait pas ete vu. */
(function(){
  var r = document.documentElement;
  r.classList.add('mec');

  var reduit = window.matchMedia &&
               window.matchMedia('(prefers-reduced-motion:reduce)').matches;

  /* [ selecteur, geste, retard de base (ms), pas de decalage (ms) ]
     gestes : v = volet horizontal, p = volet vertical,
              c = cran de cinq pixels, f = filet vertical qui se trace */
  var plan = [
    ['.surt',          'c',   0,  0],
    ['.ouv h1',        'v',  60,  0],
    ['.ouv__t',        'c', 150,  0],
    ['.ouv__a',        'c', 210,  0],
    ['.fiche',         'p', 120,  0],
    ['.faits__g>div',  'f',   0, 90],
    ['.puces li',      'c',   0, 45],
    ['.tete h2',       'v',   0,  0],
    ['.chapo',         'c',  80,  0],
    ['.reg li',        'c',   0, 70],
    ['.reg__f',        'c',   0,  0],
    ['.pan',           'c',   0, 90],
    ['.hor>div',       'v', 120, 28],
    ['.ctc__tel',      'v',  60,  0],
    ['.ctc__l',        'c',   0, 70],
    ['.form',          'p',   0,  0]
  ];

  var lot = [];
  plan.forEach(function(p){
    var els = document.querySelectorAll(p[0]), n = 0;
    Array.prototype.forEach.call(els, function(el){
      if (el.hasAttribute('data-mec')) return;      /* premier geste gagne */
      el.setAttribute('data-mec', p[1]);
      var d = p[2] + n * p[3];
      n++;
      if (d) el.style.setProperty('--mec-d', d + 'ms');
      el.setAttribute('data-mec-d', d);
      lot.push(el);
    });
  });

  function ouvrir(el){
    if (el.classList.contains('mec-on')) return;
    el.classList.add('mec-on');
    var g = el.getAttribute('data-mec');
    if (g === 'v' || g === 'p'){
      /* le masque est retire une fois le volet ouvert : pas d'ombre
         rognee ni de couche de composition qui traine */
      var d = parseInt(el.getAttribute('data-mec-d'), 10) || 0;
      window.setTimeout(function(){ el.classList.add('mec-fini'); }, d + 520);
    }
  }

  function toutOuvrir(){
    lot.forEach(function(el){ el.classList.add('mec-on','mec-fini'); });
  }

  if (reduit || !('IntersectionObserver' in window)){
    toutOuvrir();
  } else {
    var io = new IntersectionObserver(function(entrees){
      entrees.forEach(function(e){
        if (e.isIntersecting){ ouvrir(e.target); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -5% 0px', threshold: 0 });
    lot.forEach(function(el){ io.observe(el); });
    window.setTimeout(function(){ lot.forEach(ouvrir); }, 1600);
  }

  /* la barre collante trace son filet des que la page a bouge d'un cran */
  function fige(){
    var y = window.scrollY || window.pageYOffset || 0;
    r.classList.toggle('mec-fige', y > 8);
  }
  fige();
  window.addEventListener('scroll', fige, { passive: true });
})();
