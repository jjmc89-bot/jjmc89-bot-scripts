#!/bin/bash
set -euo pipefail

source ~/.venvs/jjmc89-bot/bin/activate

python3 ~/repos/JJMC89_bot/multi/magic_links_replacer.py -dir:.pywikibot_mlb -lang:hu -config:'User:Magic links bot/config/MagicLinksReplacer' -cat:'Mágikus PMID-linkeket használó lapok' -cat:'Mágikus ISBN-linkeket használó lapok' -cat:'Mágikus RFC-linkeket használó lapok' -ns:0,6,10,12,14,100 -always
