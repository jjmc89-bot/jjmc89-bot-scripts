#!/bin/bash
set -euo pipefail

source ~/.venvs/jjmc89-bot/bin/activate

python3 ~/repos/JJMC89_bot/enwiki/inactive_interface_admins.py
