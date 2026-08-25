#!/usr/bin/env python3
"""03 STRUCTURE · 위키 검사

louiswang524/llm-knowledge-base (MIT) 의 kb-lint 설계를 바탕으로 고쳐 썼다.
검사 다섯 중 넷을 쓰고 하나는 통째로 뺐다.

    A  얇은 문서                    그대로 쓴다
    B  링크는 걸렸는데 문서가 없다    그대로 쓴다
    C  깨진 링크                    그대로 쓴다. 재료 링크까지 본다
    D  겹쳐 보이는 개념 짝           슬러그 글자 겹침이 한글에서 안 먹어 판정을 바꿨다
    E  얇은 문서마다 웹 검색          뺐다. 아래

E 를 뺀 이유. 얇은 문서 하나마다 웹 검색을 하고 그 요약을 문서에 붙이는 검사다.
이 위키는 그 사람이 한 일을 증명하는 자리다.
남의 문장이 근거 옆에 붙으면 그게 곧 지어내기다.
「위키 안에서 빈 자리를 찾는 것」만 남기고 웹 검색은 통째로 뺐다.

03 이 더한 검사 셋

    F  고아                        어느 허브에도 안 붙은 문서
    G  근거 없는 문서               본인 자료 출처가 안 붙은 문서
    H  본문 없는 재료에서 만든 문서   알맹이 비율이 위키 값어치를 정한다
    I  개인정보가 안 처리된 재료를 근거로 걸었다

I 가 03 에서 제일 센 검사다. 02 는 근거를 뽑을 뿐이지만 03 은 위키 문서를 새로 쓴다.
그 문서가 06 에서 사이트가 되고 07 이 발행한다.
위키에 한 번 들어간 연락처는 그대로 공개된다.
값은 여기서도 안 적는다. 경로와 종류만 낸다.

    python3 lint.py {작업폴더}
    python3 lint.py {작업폴더} --조용히      결과를 화면에 안 내고 파일만 낸다

내는 것

    {작업폴더}/.kb/위키검사.json

고치지 않는다. 짚기만 한다. 고치는 건 스킬이 한다.
"""

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

NFC = lambda s: unicodedata.normalize("NFC", s)

얇은문서_기준 = 300        # 본문 글자수. 이보다 적으면 짚는다
겹침_기준 = 0.5            # 제목 어절이 이 비율 넘게 겹치면 짚는다

링크패턴 = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
# scan.py 와 같은 패턴이다. 두 스크립트가 같은 기준으로 봐야 어긋나지 않는다.
# 고칠 때 두 파일을 같이 고친다. 값은 어디에도 안 적는다. 종류만 남긴다.
개인정보패턴 = [
    ("전화번호", re.compile(r"01[016789]-?[0-9]{3,4}-?[0-9]{4}")),
    ("이메일", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("주민번호꼴", re.compile(r"(?<![0-9])[0-9]{6}-[1-4][0-9]{6}(?![0-9])")),
    ("생년월일", re.compile(
        r"(생년월일|생일|birth\s*date|date\s*of\s*birth)[^\n]{0,20}"
        r"(19|20)[0-9]{2}[.\-/ ]\s*(0?[1-9]|1[0-2])", re.I)),
    ("계좌번호꼴", re.compile(r"(계좌|은행)[^\n]{0,20}[0-9]{2,6}-[0-9]{2,6}-[0-9]{2,8}")),
]

조사 = ("을", "를", "이", "가", "은", "는", "의", "에", "로", "으로", "와", "과", "도", "만")


def 머리말_가르기(글):
    """첫 --- 블록만 걷어낸다. 위키 문서는 우리가 쓴 것이라 두 겹이 안 나온다."""
    if not 글.startswith("---"):
        return {}, 글
    끝 = 글.find("\n---", 3)
    if 끝 == -1:
        return {}, 글
    값 = {}
    for 줄 in 글[3:끝].splitlines():
        if ":" in 줄 and not 줄.startswith((" ", "\t", "#")):
            열쇠, _, 값1 = 줄.partition(":")
            값[열쇠.strip()] = 값1.strip()
    return 값, 글[끝 + 4:].lstrip("\n")


def 어절_고르기(제목):
    """한글 제목을 어절로 쪼개고 조사를 뗀다.

    kb-lint 는 슬러그를 하이픈으로 쪼개 글자가 겹치는지 봤다.
    한글 제목은 하이픈으로 안 쪼개지고 조사가 붙어 같은 말이 다른 낱말로 갈린다.
    그래서 띄어쓰기와 가운뎃점으로 쪼개고 조사를 뗀다.
    """
    낱말 = set()
    for 조각 in re.split(r"[\s·,/()\[\]-]+", NFC(제목)):
        조각 = 조각.strip()
        if len(조각) < 2:
            continue
        for ㅈ in sorted(조사, key=len, reverse=True):
            if 조각.endswith(ㅈ) and len(조각) - len(ㅈ) >= 2:
                조각 = 조각[:-len(ㅈ)]
                break
        낱말.add(조각)
    return 낱말


def 알맹이_글자수(몸):
    """표 · 제목 · 링크 줄을 뺀 글줄만 센다.

    「어디서 나왔나」 표가 길다고 두꺼운 문서가 아니다.
    표를 본문으로 세면 근거만 잔뜩 달린 빈 껍데기가 검사를 통과한다.
    """
    글줄 = []
    for 줄 in 몸.splitlines():
        ㅈ = 줄.strip()
        if not ㅈ or ㅈ.startswith(("#", "|", ">", "```", "---")):
            continue
        ㅈ = 링크패턴.sub(r"\1", ㅈ)          # 링크는 글자만 남긴다
        글줄.append(ㅈ)
    return len(re.sub(r"\s+", "", "".join(글줄)))


def 위키_읽기(작업폴더):
    개념뿌리 = os.path.join(작업폴더, "wiki", "concepts")
    문서 = {}
    if not os.path.isdir(개념뿌리):
        return 문서, 개념뿌리
    for 뿌리, 폴더들, 이름들 in os.walk(개념뿌리):
        폴더들[:] = [d for d in 폴더들 if not d.startswith(".")]
        for 이름 in sorted(이름들):
            if not 이름.endswith(".md"):
                continue
            길 = os.path.join(뿌리, 이름)
            try:
                글 = open(길, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            머리, 몸 = 머리말_가르기(글)
            제목맞 = re.search(r"^#\s+(.+)$", 몸, re.M)
            문서[NFC(os.path.relpath(길, 개념뿌리))] = {
                "길": 길,
                "머리": 머리,
                "몸": 몸,
                "제목": 제목맞.group(1).strip() if 제목맞 else 이름[:-3],
                "글자수": 알맹이_글자수(몸),
                "링크": [(이, 주) for 이, 주 in 링크패턴.findall(몸)],
            }
    return 문서, 개념뿌리


def 검사(작업폴더):
    문서, 개념뿌리 = 위키_읽기(작업폴더)
    나온것 = defaultdict(list)

    if not 문서:
        return {"문서수": 0, "짚은것": {}, "말": "wiki/concepts/ 에 문서가 없습니다."}

    # A · 얇은 문서
    for 이름, d in 문서.items():
        if d["글자수"] < 얇은문서_기준:
            나온것["A_얇은문서"].append({"문서": 이름, "글자수": d["글자수"]})

    # B · 링크는 걸렸는데 문서가 없다   C · 깨진 링크
    #
    # 목차와 허브 문서가 거는 링크도 「가리킨 것」으로 센다.
    # 안 그러면 목차에만 실린 문서가 전부 고아로 잡힌다.
    가리켜짐 = Counter()
    위키뿌리 = os.path.dirname(개념뿌리)
    for 바깥 in ("index.md", "hubs"):
        길 = os.path.join(위키뿌리, 바깥)
        후보 = []
        if os.path.isfile(길):
            후보 = [길]
        elif os.path.isdir(길):
            후보 = [os.path.join(길, n) for n in sorted(os.listdir(길))
                    if n.endswith(".md")]
        for ㄱ in 후보:
            try:
                글2 = open(ㄱ, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for _, 주소 in 링크패턴.findall(글2):
                대상 = os.path.normpath(
                    os.path.join(os.path.dirname(ㄱ), 주소.split("#")[0].strip()))
                if 대상.startswith(개념뿌리) and os.path.exists(대상):
                    가리켜짐[NFC(os.path.relpath(대상, 개념뿌리))] += 1

    for 이름, d in 문서.items():
        for 글자, 주소 in d["링크"]:
            주소 = 주소.split("#")[0].strip()
            if not 주소 or 주소.startswith(("http://", "https://", "mailto:")):
                continue
            대상 = os.path.normpath(os.path.join(os.path.dirname(d["길"]), 주소))
            if os.path.exists(대상):
                if 대상.startswith(개념뿌리):
                    가리켜짐[NFC(os.path.relpath(대상, 개념뿌리))] += 1
                continue
            안쪽 = 주소.endswith(".md") and not 주소.startswith("..")
            나온것["B_없는문서" if 안쪽 else "C_깨진링크"].append(
                {"문서": 이름, "글자": 글자, "주소": 주소})

    # D · 겹쳐 보이는 개념 짝
    낱말 = {이름: 어절_고르기(d["제목"]) for 이름, d in 문서.items()}
    이름들 = sorted(문서)
    for i, ㄱ in enumerate(이름들):
        for ㄴ in 이름들[i + 1:]:
            ㄱ낱, ㄴ낱 = 낱말[ㄱ], 낱말[ㄴ]
            if not ㄱ낱 or not ㄴ낱:
                continue
            겹침 = len(ㄱ낱 & ㄴ낱) / min(len(ㄱ낱), len(ㄴ낱))
            if 겹침 >= 겹침_기준:
                나온것["D_겹쳐보임"].append({
                    "한쪽": 문서[ㄱ]["제목"], "다른쪽": 문서[ㄴ]["제목"],
                    "겹친말": sorted(ㄱ낱 & ㄴ낱),
                })

    # F · 고아   허브가 안 적혔거나 아무 문서도 안 가리킨다
    for 이름, d in 문서.items():
        허브 = d["머리"].get("허브", "").strip()
        if not 허브:
            나온것["F_고아"].append({"문서": 이름, "왜": "허브가 안 적혀 있다"})
        elif 가리켜짐[이름] == 0 and len(문서) > 1:
            나온것["F_고아"].append({"문서": 이름, "왜": "아무 문서도 이걸 안 가리킨다"})

    # G · 근거 없는 문서   H · 본문 없는 재료에서 만든 문서   I · 개인정보
    for 이름, d in 문서.items():
        재료링크 = [주 for _, 주 in d["링크"] if "raw/" in 주]
        if not 재료링크:
            나온것["G_근거없음"].append({"문서": 이름})
            continue
        빈재료, 위험재료 = [], []
        for 주 in 재료링크:
            대상 = os.path.normpath(os.path.join(os.path.dirname(d["길"]),
                                                 주.split("#")[0]))
            if not os.path.exists(대상):
                continue
            try:
                글 = open(대상, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            머리, 몸 = 머리말_가르기(글)
            if len(re.sub(r"\s+", "", 몸)) < 100:
                빈재료.append(주)
            # 이미 가려둔 것은 안 짚는다. 02 가 [가림] 으로 바꾸고 표기를 남겼다
            if 머리.get("sensitive") or 머리.get("masked_at"):
                continue
            걸린것 = [ㄱ for ㄱ, 패턴 in 개인정보패턴 if 패턴.search(몸)]
            if 걸린것:
                위험재료.append({"재료": 주, "종류": 걸린것})
        if 빈재료 and len(빈재료) == len(재료링크):
            나온것["H_빈재료에서만듦"].append({"문서": 이름, "재료": 빈재료})
        if 위험재료:
            나온것["I_개인정보"].append({"문서": 이름, "재료": 위험재료})

    # 위키 본문 자체에 값이 딸려 들어갔는지도 본다. 인용문에 섞여 오는 자리다
    for 이름, d in 문서.items():
        걸린것 = [ㄱ for ㄱ, 패턴 in 개인정보패턴 if 패턴.search(d["몸"])]
        if 걸린것:
            나온것["I_개인정보"].append({"문서": 이름, "본문에직접": 걸린것})

    결과 = {
        "문서수": len(문서),
        "글자수": sum(d["글자수"] for d in 문서.values()),
        "짚은것": {k: v for k, v in sorted(나온것.items())},
        "합계": {k: len(v) for k, v in sorted(나온것.items())},
    }

    칸 = os.path.join(작업폴더, ".kb")
    os.makedirs(칸, exist_ok=True)
    with open(os.path.join(칸, "위키검사.json"), "w", encoding="utf-8") as 손:
        json.dump(결과, 손, ensure_ascii=False, indent=2)
    return 결과


설명 = {
    "A_얇은문서": "본문이 얇습니다. 합치거나 자료를 더 붙여야 합니다",
    "B_없는문서": "링크는 걸렸는데 그 문서가 없습니다",
    "C_깨진링크": "링크가 안 열립니다",
    "D_겹쳐보임": "두 문서가 같은 것을 말하는 것 같습니다",
    "F_고아": "어느 갈래에도 안 붙어 있습니다",
    "G_근거없음": "본인 자료 출처가 안 붙어 있습니다",
    "H_빈재료에서만듦": "본문이 없는 자료에서만 만들어졌습니다",
    "I_개인정보": "개인정보가 아직 안 가려진 자리입니다. 값은 여기 안 적습니다",
}


def 요약(결과):
    if not 결과.get("문서수"):
        return 결과.get("말", "위키가 비어 있습니다.")
    줄 = [f"위키 문서 {결과['문서수']}장 · {결과['글자수']:,}자", ""]
    if not 결과["합계"]:
        줄.append("짚을 것이 없습니다.")
        return "\n".join(줄)
    for 이름, 개수 in 결과["합계"].items():
        줄.append(f"  {개수:>4}건  {설명.get(이름, 이름)}")
    return "\n".join(줄)


if __name__ == "__main__":
    인자 = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not 인자:
        print(__doc__)
        sys.exit(1)
    결과 = 검사(os.path.expanduser(인자[0]))
    if "--조용히" not in sys.argv:
        print(요약(결과))
