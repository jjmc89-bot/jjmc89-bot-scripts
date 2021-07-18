#!/bin/bash
set -euo pipefail

source .venvs/jjmc89-bot/bin/activate

python3 JJMC89_bot/enwiki/draftification_tagger.py -dir:.pywikibot_dfy_tagger --always --start $(date -ud '-15 min' +"%Y-%m-%dT%H:%M:%SZ")
