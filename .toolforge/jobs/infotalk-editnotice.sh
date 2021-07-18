#!/bin/bash
set -euo pipefail

source .venvs/jjmc89-bot/bin/activate

python3 JJMC89_bot/enwiki/editnotice_deployer.py -dir:.pywikibot2 -cat:'Wikipedia information pages' -ns:4,12 -to_talk -talk_only -editnotice_template:'Wikipedia information pages talk page editnotice' -always
