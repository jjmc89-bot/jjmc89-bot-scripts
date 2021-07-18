#!/bin/bash
set -euo pipefail

source .venvs/jjmc89-bot/bin/activate

python3 JJMC89_bot/enwiki/massmessage_list_updater.py --always --meta --rename 'User:JJMC89 bot/config/UserGroupsMassMessageListUpdater'
