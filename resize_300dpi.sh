#!/bin/bash

set -e

in="$1"
tmp="$(mktemp "${in%.*}.XXXXXX.tif")"

magick "$in" -resize 50% -units PixelsPerInch -density 300 "$tmp"
mv "$tmp" "$in"
