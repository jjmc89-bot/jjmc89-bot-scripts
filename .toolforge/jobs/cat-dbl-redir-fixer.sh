#!/bin/bash
set -euo pipefail

source .venvs/jjmc89-bot/bin/activate

python3 JJMC89_bot/enwiki/category_double_redirect_fixer.py -ns:14 -transcludes:'Category redirect' -always
