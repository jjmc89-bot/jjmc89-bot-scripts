#!/bin/bash
set -euo pipefail

source .venvs/jjmc89-bot/bin/activate

python3 JJMC89_bot/enwiki/svg_validator.py -always -mysqlquery:"select 6, img_name from image i left join page p on i.img_name = p.page_title where img_media_type = 'DRAWING' and img_major_mime = 'image' and img_minor_mime = 'svg+xml' and page_namespace = 6 and page_is_redirect = 0 and not exists (select 1 from templatelinks tl where p.page_id = tl.tl_from and tl_namespace = 10 and tl_title in ('Valid_SVG', 'Invalid_SVG'))"
