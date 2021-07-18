#!/bin/bash
set -euo pipefail

source .venvs/jjmc89-bot/bin/activate

python3 JJMC89_bot/enwiki/cfdw.py -dir:.pywikibot_cfdw -page:WP:Categories_for_discussion/Working
