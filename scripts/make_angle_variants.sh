#!/bin/bash
# 칠한 이미지를 각도별로 돌린 변형을 만든다. 정답은 원본과 같다.
# 실행: bash scripts/make_angle_variants.sh <이미지> <저장 폴더>
set -e
input="$1"
outdir="$2"
mkdir -p "$outdir"
name="$(basename "${input%.*}")"
for angle in 5 15 90 180 270 345; do
  sips -r "$angle" --padColor FFFFFF "$input" --out "$outdir/${name}_rot$(printf %03d "$angle").png" >/dev/null 2>&1
done
