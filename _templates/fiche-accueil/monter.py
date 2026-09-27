#!/usr/bin/env python3
"""Assemble une page : base + un bloc couleur + un bloc effets.

    python3 monter.py --couleur couleur-xxx.css --effets effets-yyy.css \
                      [--js effets-yyy.js] --sortie page.html

Les blocs sont injectes en fin de <style> et en fin de <body>, donc ils
surchargent toujours la base sans avoir a la modifier.
"""
import argparse
from pathlib import Path

a = argparse.ArgumentParser()
a.add_argument("--couleur"); a.add_argument("--effets")
a.add_argument("--js"); a.add_argument("--sortie", required=True)
a.add_argument("--base", default="base.html")
o = a.parse_args()

t = Path(o.base).read_text(encoding="utf-8")
css = ""
for f in (o.couleur, o.effets):
    if f:
        css += f"\n/* ---- {Path(f).name} ---- */\n" + Path(f).read_text(encoding="utf-8")
t = t.replace("/* ==INJECTION-CSS== */", css)
if o.js:
    t = t.replace("<!-- ==INJECTION-JS== -->",
                  "<script>\n" + Path(o.js).read_text(encoding="utf-8") + "\n</script>")
Path(o.sortie).write_text(t, encoding="utf-8")
print(f"{o.sortie} ecrit ({len(t)//1024} Ko)")
