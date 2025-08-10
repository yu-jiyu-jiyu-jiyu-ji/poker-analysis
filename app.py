# streamlit run app.py
import streamlit as st
from itertools import product

st.set_page_config(page_title="Poker Review", page_icon="🃏", layout="centered")

# ==== 定数 ====
SUITS_ORDER = ["♠","♣","♦","♥"]                   # 並び：スート→ランク
RANKS_ORDER = ["A","2","3","4","5","6","7","8","9","T","J","Q","K"]
POS_ALL = ["UTG","HJ","CO","BTN","SB","BB"]
ACTIONS_PRE  = ["open","limp","call","fold","3bet","4bet","shove","check"]
ACTIONS_POST = ["bet","check","call","raise","fold","shove"]

def gen_cards():  # ["A♠","A♣",...,"K♥"] をスート→ランク順で
    return [f"{r}{s}" for s, r in product(SUITS_ORDER, RANKS_ORDER)]
ALL_CARDS = gen_cards()

def suit_color(suit):
    return {"♠":"#111111","♣":"#1E9B57","♦":"#F1C40F","♥":"#E74C3C"}[suit]

def card_badge(card, size=20):
    suit, rank = card[-1], card[:-1]
    color = suit_color(suit)
    return f"<span style='display:inline-block;border:2px solid {color};border-radius:10px;padding:6px 10px;margin-right:8px;font-size:{size}px;color:{color};font-weight:700;'>{rank}{suit}</span>"

def validate_amount(txt: str):
    t = txt.strip().replace(",", "")
    if t == "": return True, ""  # 金額不要アクション用に空は許可（上流で制御）
    if not t.isdigit() or int(t) <= 0:
        return False, "金額は正の数字（例: 200 / 5000）で入力してください"
    return True, t

def normalize_line(pos, act, amt):
    needs_amt = act not in ["check","fold","call"]
    if needs_amt:
        ok, v = validate_amount(amt)
        if not ok: return False, None, "金額エラー"
        return True, f"{pos} {act} {v}", ""
    return True, f"{pos} {act}", ""

# ==== state 初期化 ====
if "villains" not in st.session_state:
    st.session_state.villains = []
if "flow" not in st.session_state:
    st.session_state.flow = {
        "pre":   [{"pos":"UTG","act":"open","amt":""}],
        "flop":  [{"pos":"Hero","act":"bet","amt":""}],
        "turn":  [{"pos":"Hero","act":"check","amt":""}],
        "river": [{"pos":"Hero","act":"bet","amt":""}],
    }
if "messages" not in st.session_state:
    st.session_state.messages = []
# 解析後だけチャットを表示するフラグ
if "show_chat" not in st.session_state:
    st.session_state.show_chat = False

# ==== CSS（幅スリム & 縦位置調整） ====
st.markdown("""
<style>
.block-container { padding-top: .6rem; padding-bottom: 2rem; }
label { font-size: .95rem; }
/* カードセレクトをスリム化 */
.card-compact [data-baseweb="select"],
.card-compact div[role="combobox"] { min-width: 64px !important; width: 72px !important; }
.card-compact .stSelectbox label p { margin-bottom: 2px; }

/* 横並びのボタンをselect高さに揃える */
.inline-row .stButton>button { margin-top: 1.6rem; }      /* 追加ボタン */
.row-actions .stButton>button { margin-top: 1.6rem; }     /* 🗑 ボタン */
</style>
""", unsafe_allow_html=True)

st.title("ハンド解析")

# 初期表示は一番上から（ロード時スクロールトップ）
st.markdown("""
<script>
window.addEventListener('load', function() { window.scrollTo(0, 0); });
</script>
""", unsafe_allow_html=True)

# ==== 共通 ====
def selectable_cards(exclude=set()):
    return [c for c in ALL_CARDS if c not in exclude]

def pick_card(label: str, key: str, choices: list[str]) -> str:
    current = st.session_state.get(key)
    if current not in choices:
        current = choices[0]
    idx = choices.index(current)
    value = st.selectbox(label, choices, index=idx, key=key,
                         label_visibility="visible" if label else "collapsed")
    return value

# ==== ハンド：セレクト2つ横並び → バッジ表示 ====
used_cards = set()
st.markdown("<div class='card-compact'>", unsafe_allow_html=True)
hc1, hc2 = st.columns([1,1])
with hc1:
    hero_c1 = pick_card("1枚目", "hero_c1", selectable_cards(used_cards))
    used_cards.add(hero_c1)
with hc2:
    hero_c2 = pick_card("2枚目", "hero_c2", selectable_cards(used_cards))
    used_cards.add(hero_c2)
st.markdown("</div>", unsafe_allow_html=True)
st.markdown(card_badge(hero_c1, 24) + card_badge(hero_c2, 24), unsafe_allow_html=True)

# ==== 難易度 ====
level = st.radio("難易度", ["初級","中級","上級(近似)"], index=1, horizontal=True)

# ==== ポジション ====
pos_self = st.selectbox("自分のポジション", POS_ALL, index=5)

# ---- 相手のポジション（横並び完全揃え） ----
st.subheader("相手のポジション（＋で追加）")
def remaining_positions():
    used_pos = {pos_self} | {v["pos"] for v in st.session_state.villains}
    return [p for p in POS_ALL if p not in used_pos]

pos_options = remaining_positions()
st.markdown("ポジション　／　タイプ　／　追加")
st.markdown("<div class='inline-row'>", unsafe_allow_html=True)
c1, c2, c3 = st.columns([1.2,1.6,.8])
with c1:
    vp = st.selectbox("", pos_options if pos_options else ["（空きなし）"],
                      key="vill_add_pos", label_visibility="collapsed")
with c2:
    vt = st.selectbox("", ["tight-passive","tight-aggressive","loose-passive","loose-aggressive"],
                      key="vill_add_type", label_visibility="collapsed")
with c3:
    add_ok = st.button("＋ 追加", use_container_width=True, disabled=not pos_options, key="vill_add_btn")
st.markdown("</div>", unsafe_allow_html=True)
if add_ok and pos_options:
    st.session_state.villains.append({"pos": vp, "type": vt})

# 一覧 & 削除
for i, v in enumerate(list(st.session_state.villains)):
    cols = st.columns([2,3,1])
    cols[0].markdown(f"- **{v['pos']}**")
    cols[1].markdown(f"タイプ：{v['type']}")
    with cols[2]:
        st.markdown("<div class='row-actions'>", unsafe_allow_html=True)
        if st.button("削除", key=f"vill_del_{i}"):
            st.session_state.villains.pop(i)
        st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# ==== ボード（Flop1行、Turn/River1行・セレクト幅スリム/位置揃え） ====
st.subheader("ボード")
st.markdown("<div class='card-compact'>", unsafe_allow_html=True)

st.markdown("Flop")
fcols = st.columns([1,1,1])
with fcols[0]:
    flop_1 = pick_card("", "flop_1", selectable_cards(used_cards))
    used_cards.add(flop_1)
with fcols[1]:
    flop_2 = pick_card("", "flop_2", selectable_cards(used_cards))
    used_cards.add(flop_2)
with fcols[2]:
    flop_3 = pick_card("", "flop_3", selectable_cards(used_cards))
    used_cards.add(flop_3)

st.markdown("Turn / River")
trcols = st.columns([1,1])
with trcols[0]:
    turn = pick_card("", "turn", selectable_cards(used_cards))
    used_cards.add(turn)
with trcols[1]:
    river = pick_card("", "river", selectable_cards(used_cards))
    used_cards.add(river)

st.markdown("</div>", unsafe_allow_html=True)
st.markdown(card_badge(flop_1) + card_badge(flop_2) + card_badge(flop_3), unsafe_allow_html=True)
st.markdown(card_badge(turn) + card_badge(river), unsafe_allow_html=True)

st.divider()

# ==== 流れ（各行の縦位置を統一） ====
st.subheader("流れ（アクション入力）")

def street_block(key, title, postflop=True):
    st.markdown(f"**{title}**")
    rows = st.session_state.flow[key]
    to_del = []
    for i, r in enumerate(rows):
        st.markdown("<div class='row-actions'>", unsafe_allow_html=True)
        cols = st.columns([1.2,1.2,1,.6])
        with cols[0]:
            rows[i]["pos"] = st.selectbox("ポジション", POS_ALL+["Hero"],
                                          index=(POS_ALL+["Hero"]).index(r.get("pos","Hero")),
                                          key=f"{key}_pos_{i}", label_visibility="collapsed")
        with cols[1]:
            acts = ACTIONS_POST if postflop else ACTIONS_PRE
            rows[i]["act"] = st.selectbox("アクション", acts,
                                          index=acts.index(r.get("act", acts[0])),
                                          key=f"{key}_act_{i}", label_visibility="collapsed")
        with cols[2]:
            rows[i]["amt"] = st.text_input("金額（数字のみ）", r.get("amt",""),
                                           key=f"{key}_amt_{i}", placeholder="200 / 5000",
                                           label_visibility="collapsed")
            needs_amt = rows[i]["act"] not in ["check","fold","call"]
            if needs_amt and rows[i]["amt"] == "":
                st.caption("※ 数字を入力", help="bet/raise/3betなどは金額が必要です")
        with cols[3]:
            if st.button("🗑️", key=f"{key}_del_{i}"):
                to_del.append(i)
        st.markdown("</div>", unsafe_allow_html=True)
    for i in reversed(to_del):
        rows.pop(i)

    if st.button(f"+ 行を追加（{title}）", key=f"{key}_add"):
        rows.append({"pos":"Hero" if postflop else "UTG", "act":"check" if postflop else "open", "amt":""})

    parts = []
    for r in rows:
        ok, text, _ = normalize_line(r["pos"], r["act"], r["amt"])
        if ok: parts.append(text)
    st.caption(" / ".join(parts) if parts else "（未入力）")

street_block("pre",   "プリフロップ", postflop=False)
street_block("flop",  "フロップ",     postflop=True)
street_block("turn",  "ターン",       postflop=True)
street_block("river", "リバー",       postflop=True)

# ==== 解析 & チャット ====
def build_flow_text():
    def join(key):
        out=[]
        for r in st.session_state.flow[key]:
            ok,text,_ = normalize_line(r["pos"], r["act"], r["amt"])
            if ok: out.append(text)
        return " / ".join(out) if out else "（なし）"
    return f"""・プリフロップ
　{join('pre')}
・フロップ
　{join('flop')}
・ターン
　{join('turn')}
・リバー
　{join('river')}"""

if st.button("解析する", use_container_width=True):
    st.session_state.messages.append({"role":"user","content":"解析してください"})
    st.session_state.messages.append({
        "role":"assistant",
        "content":f"【{level}の視点】UI整形OK。流れ: \n{build_flow_text()}"
    })
    st.session_state.show_chat = True   # 解析後にチャット表示をON

st.divider()

# 解析後だけチャットを表示
if st.session_state.show_chat:
    st.subheader("チャット")
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    if q := st.chat_input("質問を入力…"):
        st.session_state.messages.append({"role":"user","content":q})
        st.session_state.messages.append({"role":"assistant","content":"（モック）LLM接続は後でONにします。"})
