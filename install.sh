#!/usr/bin/env bash
# iny-structure 설치
# 사용법:  bash install.sh [작업폴더경로]
#          경로를 안 주면 01·02 에서 쓰던 폴더를 그대로 씁니다.
#
# 변수 이름은 영문만 씁니다. zsh 는 한글 변수를 받지만 bash 는 못 받고,
# bash -n 문법 검사는 통과해서 실행해야 잡힙니다.
set -e
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$HOME/.claude/iny-config.json"

# 01·02 가 이미 잡아둔 작업 폴더를 그대로 쓴다. 덮어쓰면 앞 단계가 만든 것을 못 찾는다.
EXISTING=""
if [ -f "$CONFIG" ]; then
  EXISTING="$(sed -n 's/.*"kb_path"[[:space:]]*:[[:space:]]*"\(.*\)".*/\1/p' "$CONFIG" | head -1)"
fi

KB_PATH="${1:-${EXISTING:-$HOME/asset-engine}}"
KB_PATH="${KB_PATH/#\~/$HOME}"

mkdir -p "$KB_PATH/outputs"
mkdir -p "$KB_PATH/wiki/concepts"
mkdir -p "$HOME/.claude"
cat > "$CONFIG" <<CFG
{
  "kb_path": "$KB_PATH"
}
CFG

DEST="$HOME/.claude/skills/iny-structure"
mkdir -p "$DEST"
cp "$SRC/SKILL.md" "$DEST/SKILL.md"
rm -rf "$DEST/scripts" "$DEST/references"
cp -R "$SRC/scripts" "$DEST/scripts"          # 재료를 훑고 가르는 것 · 위키를 검사하는 것
cp -R "$SRC/references" "$DEST/references"    # 위키 양식과 링크 규칙

echo
echo "설치됐습니다."
echo "  스킬      ~/.claude/skills/iny-structure/"
echo "  작업 폴더  $KB_PATH"

# 03 은 01 의 재료와 02 의 컨셉을 둘 다 읽습니다. 없으면 여기서 알려주고 멈춥니다.
if [ ! -d "$KB_PATH/raw" ]; then
  echo
  echo "다만 이 폴더에 자료가 없습니다."
  echo "03 은 01 이 만든 자료를 읽는 단계라 01 을 먼저 돌리셔야 합니다."
  echo "  https://github.com/iny101400-young/iny-material"
  exit 0
fi

if [ ! -f "$KB_PATH/outputs/02-identify/컨셉.md" ]; then
  echo
  echo "다만 02 에서 만든 컨셉 문서가 안 보입니다."
  echo "03 은 02 가 정한 컨셉을 기준으로 자료를 가르는 단계라 02 를 먼저 하셔야 합니다."
  echo "  https://github.com/iny101400-young/iny-identify"
  exit 0
fi

echo
echo "Claude Code 를 $KB_PATH 에서 열고 '구조 잡기' 라고 치세요."
