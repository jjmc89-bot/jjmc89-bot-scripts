#!/bin/bash
set -euo pipefail

source .venvs/jjmc89-bot/bin/activate

python3 JJMC89_bot/enwiki/inactive_admins.py -config:'User:JJMC89 bot/config/InactiveAdmins'
