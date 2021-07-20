#!/bin/bash
set -euo pipefail

source ~/.venvs/jjmc89-bot/bin/activate

python3 ~/repos/JJMC89_bot/multi/commons_potd_importer.py -always -page:'User:JJMC89 bot/Commons picture of the day'
