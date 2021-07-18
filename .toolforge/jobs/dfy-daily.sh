#!/bin/bash
set -euo pipefail

source .venvs/jjmc89-bot/bin/activate

python3 JJMC89_bot/enwiki/draftification_report.py -page:'User:JJMC89 bot/report/Draftifications/daily'
