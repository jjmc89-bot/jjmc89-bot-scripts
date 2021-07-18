#!/bin/bash
set -euo pipefail

source .venvs/jjmc89-bot/bin/activate

DATE=$(date -d yesterday +'%Y%m%d')

python3 JJMC89_bot/enwiki/svg_validator.py -always -mysqlquery:"select log_namespace, log_title from logging_logindex where log_namespace=6 and (log_type='upload' or (log_type='delete' and log_action='restore')) and log_title rlike '(?i)\.svg$' and log_timestamp like '$DATE%'"
