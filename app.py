# streamlit run app.py
# ------------------------------------------------------------
# ポーカー振り返り UI（モック）
# - ヘッダー/フッターをCSSで非表示
# - 初回ロード時はページ最上部へスクロール
# - 解析ボタン押下後にのみチャットセクションを表示
# - カード/ポジションの重複制御、モバイルに寄せたコンパクトUI
# ------------------------------------------------------------

import streamlit as st
from itertools import product

# ページ基本設定（タイトル/絵文字/横幅）
st.set_page_config(page_title="Poker Review", page_icon="🃏", layout="centered")

# ==== グローバル定数（UIやデータの選択肢） =========================
SUITS_ORDER = ["♠", "♣", "♦", "♥"]  # 表示順：スート→ランク
RANKS_ORDER = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K"]
POS_ALL = ["UTG", "HJ", "CO", "BTN", "SB", "BB"]
ACTIONS_PRE = ["open", "limp", "call", "fold", "3bet", "4bet", "shove", "check"]
ACTIONS_POST = ["bet", "check", "call", "raise", "fold", "shove"]

# ===== GPT 呼び出し 最小実装 =====
import os
try:
    from openai import OpenAI
    _gpt = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
except Exception as _e:
    _gpt = None

def call_gpt(level: str, hero_cards: list[str], board: list[str], villains: list[dict], flow_text: str) -> str:
    """ UIで集めた情報から一回だけ回答を生成（ストリーミングなしの最小版）"""
    if not _gpt or not os.environ.get("OPENAI_API_KEY"):
        return "⚠️ OPENAI_API_KEY が設定されていません（Render の Environment に追加してください）"

    # --- プロンプト（最小） ---
    sys = {
        "初級": "あなたは初心者向けのポーカーコーチ。専門用語を避け、簡潔に。",
        "中級": "あなたは中級者向けコーチ。レンジ/ポジション/ベットサイズの意図を具体的に。",
        "上級(近似)": "あなたはGTO的思考手順を近似で説明する上級コーチ。バランス/混合戦略を踏まえて。"
    }.get(level, "あなたはポーカーコーチ。")

    vtext = "\n".join([f"- {v['pos']}: {v['type']}" for v in villains]) or "（未指定）"
    btext = " ".join([c for c in board if c]) or "（未指定）"
    user = f"""ハンド解説依頼
難易度: {level}

# ハンド
Hero: {hero_cards[0]} {hero_cards[1]}

# ボード
{btext}

# 相手タイプ
{vtext}

# 流れ
{flow_text}

# 出力フォーマット
- 最初に結論（1〜3行）
- 各ストリートの方針とベットサイズ指針（プリ 2.2/3bb、ポスト 33/66/100/AI）
- 想定レンジ（相手/自分）と主要ハンド例
- よくあるミスと修正ポイント
"""

    try:
        resp = _gpt.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=float(os.environ.get("OPENAI_TEMPERATURE", "0.3")),
            messages=[{"role":"system","content":sys},{"role":"user","content":user}],
        )
        return resp.choices[0].message.content or "（空の応答）"
    except Exception as e:
        return f"LLM呼び出しエラー: {e}"

def gen_cards() -> list[str]:
    """カード一覧 ["A♠","A♣",...,"K♥"] をスート→ランク順で生成"""
    return [f"{r}{s}" for s, r in product(SUITS_ORDER, RANKS_ORDER)]


ALL_CARDS = gen_cards()


def suit_color(suit: str) -> str:
    """スートに応じた色（♠黒, ♣緑, ♦黄, ♥赤）"""
    return {"♠": "#111111", "♣": "#1E9B57", "♦": "#F1C40F", "♥": "#E74C3C"}[suit]


def card_badge(card: str, size: int = 20) -> str:
    """カードをバッジ風にHTML表示（枠線・色付き）"""
    suit, rank = card[-1], card[:-1]
    color = suit_color(suit)
    return (
        f"<span style='display:inline-block;border:2px solid {color};"
        f"border-radius:10px;padding:6px 10px;margin-right:8px;"
        f"font-size:{size}px;color:{color};font-weight:700;'>{rank}{suit}</span>"
    )


def validate_amount(txt: str) -> tuple[bool, str | None]:
    """金額入力（数字のみ）を簡易バリデーション。空文字はOK（不要アクション用）"""
    t = txt.strip().replace(",", "")
    if t == "":
        return True, ""
    if not t.isdigit() or int(t) <= 0:
        return False, None
    return True, t


def normalize_line(pos: str, act: str, amt: str) -> tuple[bool, str | None, str]:
    """
    アクション1行を整形して文字列化。
    - check/fold/call 以外は金額必須
    - 返り値: (OK?, 正規化文字列, エラーメッセージ)
    """
    needs_amt = act not in ["check", "fold", "call"]
    if needs_amt:
        ok, v = validate_amount(amt)
        if not ok:
            return False, None, "金額は正の数字で入力してください"
        return True, f"{pos} {act} {v}", ""
    return True, f"{pos} {act}", ""


# ==== セッション状態（永続UI状態）初期化 ===========================
if "villains" not in st.session_state:
    # 相手のポジションとタイプの配列（重複ポジションはUIで禁止）
    st.session_state.villains: list[dict] = []

if "flow" not in st.session_state:
    # ストリートごとのアクション行（デフォルト1行）
    st.session_state.flow = {
        "pre": [{"pos": "UTG", "act": "open", "amt": ""}],
        "flop": [{"pos": "Hero", "act": "bet", "amt": ""}],
        "turn": [{"pos": "Hero", "act": "check", "amt": ""}],
        "river": [{"pos": "Hero", "act": "bet", "amt": ""}],
    }

if "messages" not in st.session_state:
    # チャット履歴（解析後に利用）
    st.session_state.messages: list[dict] = []

if "show_chat" not in st.session_state:
    # 解析ボタン押下後のみチャットを表示するフラグ
    st.session_state.show_chat = False


# ==== 見た目の共通CSS（ヘッダー/フッター非表示・モバイル寄り調整） =====
st.markdown(
    """
    <style>
    /* Streamlitの上部ヘッダーと右上メニューを非表示 */
    header {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden !important;}
    /* 下部のフッターも非表示 */
    footer {visibility: hidden;}

    /* 余白＆フォント微調整（スマホ寄り） */
    .block-container { padding-top: .6rem; padding-bottom: 2rem; }
    label { font-size: .95rem; }

    /* カード選択セレクトをスリム化（横幅を狭く） */
    .card-compact [data-baseweb="select"],
    .card-compact div[role="combobox"] {
      min-width: 64px !important;
      width: 72px !important;
    }
    .card-compact .stSelectbox label p { margin-bottom: 2px; }

    /* 横並びのボタンをセレクト高さに揃える（縦位置ズレ対策） */
    .inline-row .stButton>button { margin-top: 1.6rem; }   /* 追加ボタン */
    .row-actions .stButton>button { margin-top: 1.6rem; }  /* 🗑ボタン   */
    </style>
    """,
    unsafe_allow_html=True,
)

# ==== タイトル（あなたの希望でここを変えると見出しが変わる） ==========
st.title("ハンド解析")

# ==== 初回ロード時は最上部にスクロール（自動スクロール抑止） ==========
st.markdown(
    """
    <script>
    window.addEventListener('load', function() { window.scrollTo(0, 0); });
    </script>
    """,
    unsafe_allow_html=True,
)

# ==== 共通ユーティリティ ===========================================
def selectable_cards(exclude: set[str] = set()) -> list[str]:
    """すでに使用済みのカードを除いて選択肢を返す"""
    return [c for c in ALL_CARDS if c not in exclude]


def pick_card(label: str, key: str, choices: list[str]) -> str:
    """
    カード選択セレクトボックス。
    - Streamlitのセオリーに従い、ウィジェット生成後に同keyへ代入しない
    - label_visibility は、見出し行などでラベル不要な時に collapsed を使う
    """
    current = st.session_state.get(key)
    if current not in choices:
        current = choices[0]
    idx = choices.index(current)
    return st.selectbox(
        label,
        choices,
        index=idx,
        key=key,
        label_visibility="visible" if label else "collapsed",
    )


# ==== ハンド（2枚選択） =============================================
used_cards: set[str] = set()

st.markdown("<div class='card-compact'>", unsafe_allow_html=True)
hc1, hc2 = st.columns([1, 1])
with hc1:
    hero_c1 = pick_card("1枚目", "hero_c1", selectable_cards(used_cards))
    used_cards.add(hero_c1)
with hc2:
    hero_c2 = pick_card("2枚目", "hero_c2", selectable_cards(used_cards))
    used_cards.add(hero_c2)
st.markdown("</div>", unsafe_allow_html=True)

# 選択カードの視認性を上げる（色付きバッジ）
st.markdown(card_badge(hero_c1, 24) + card_badge(hero_c2, 24), unsafe_allow_html=True)

# ==== 難易度（横並びラジオ） =======================================
level = st.radio("難易度", ["初級", "中級", "上級(近似)"], index=1, horizontal=True)

# ==== 自分のポジション & 相手のポジション ============================
pos_self = st.selectbox("自分のポジション", POS_ALL, index=5)

st.subheader("相手のポジション（＋で追加）")

def remaining_positions() -> list[str]:
    """自分＋既存登録の相手ポジションを除いた残りを返す（重複ポジション防止）"""
    used_pos = {pos_self} | {v["pos"] for v in st.session_state.villains}
    return [p for p in POS_ALL if p not in used_pos]

pos_options = remaining_positions()

# ラベル行（高さ揃えのため、下のセレクトはラベルを隠す）
st.markdown("ポジション　／　タイプ　／　追加")
st.markdown("<div class='inline-row'>", unsafe_allow_html=True)
c1, c2, c3 = st.columns([1.2, 1.6, 0.8])
with c1:
    vp = st.selectbox(
        "",
        pos_options if pos_options else ["（空きなし）"],
        key="vill_add_pos",
        label_visibility="collapsed",
    )
with c2:
    vt = st.selectbox(
        "",
        ["tight-passive", "tight-aggressive", "loose-passive", "loose-aggressive"],
        key="vill_add_type",
        label_visibility="collapsed",
    )
with c3:
    add_ok = st.button(
        "＋ 追加", use_container_width=True, disabled=not pos_options, key="vill_add_btn"
    )
st.markdown("</div>", unsafe_allow_html=True)

if add_ok and pos_options:
    st.session_state.villains.append({"pos": vp, "type": vt})

# 追加済みの相手ポジション一覧（削除可能）
for i, v in enumerate(list(st.session_state.villains)):
    cols = st.columns([2, 3, 1])
    cols[0].markdown(f"- **{v['pos']}**")
    cols[1].markdown(f"タイプ：{v['type']}")
    with cols[2]:
        st.markdown("<div class='row-actions'>", unsafe_allow_html=True)
        if st.button("削除", key=f"vill_del_{i}"):
            st.session_state.villains.pop(i)
        st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# ==== ボード（Flop 3枚 1行 / Turn+River 1行） ======================
st.subheader("ボード")
st.markdown("<div class='card-compact'>", unsafe_allow_html=True)

# Flop（見出し1回＋各セレクトはラベル折りたたみで高さを統一）
st.markdown("Flop")
fcols = st.columns([1, 1, 1])
with fcols[0]:
    flop_1 = pick_card("", "flop_1", selectable_cards(used_cards))
    used_cards.add(flop_1)
with fcols[1]:
    flop_2 = pick_card("", "flop_2", selectable_cards(used_cards))
    used_cards.add(flop_2)
with fcols[2]:
    flop_3 = pick_card("", "flop_3", selectable_cards(used_cards))
    used_cards.add(flop_3)

# Turn / River（同様にラベル非表示で水平揃え）
st.markdown("Turn / River")
trcols = st.columns([1, 1])
with trcols[0]:
    turn = pick_card("", "turn", selectable_cards(used_cards))
    used_cards.add(turn)
with trcols[1]:
    river = pick_card("", "river", selectable_cards(used_cards))
    used_cards.add(river)

st.markdown("</div>", unsafe_allow_html=True)

# ボードの視認性（バッジ表示）
st.markdown(
    card_badge(flop_1) + card_badge(flop_2) + card_badge(flop_3),
    unsafe_allow_html=True,
)
st.markdown(card_badge(turn) + card_badge(river), unsafe_allow_html=True)

st.divider()

# ==== 流れ（ストリート別：1行以上。列高さをCSSで揃える） ============
st.subheader("流れ（アクション入力）")

def street_block(key: str, title: str, postflop: bool = True) -> None:
    st.markdown(f"**{title}**")
    rows = st.session_state.flow[key]
    to_del = []

    for i, r in enumerate(rows):
        st.markdown("<div class='row-actions'>", unsafe_allow_html=True)
        cols = st.columns([1.2, 1.2, 1, 0.6])

        # ポジション（Hero含む）
        with cols[0]:
            rows[i]["pos"] = st.selectbox(
                "ポジション",
                POS_ALL + ["Hero"],
                index=(POS_ALL + ["Hero"]).index(r.get("pos", "Hero")),
                key=f"{key}_pos_{i}",
                label_visibility="collapsed",
            )

        # アクション（プリ/ポストで選択肢を分ける）
        with cols[1]:
            acts = ACTIONS_POST if postflop else ACTIONS_PRE
            rows[i]["act"] = st.selectbox(
                "アクション",
                acts,
                index=acts.index(r.get("act", acts[0])),
                key=f"{key}_act_{i}",
                label_visibility="collapsed",
            )

        # 金額（数字のみ／bet/raise/3bet系は必須）
        with cols[2]:
            rows[i]["amt"] = st.text_input(
                "金額（数字のみ）",
                r.get("amt", ""),
                key=f"{key}_amt_{i}",
                placeholder="200 / 5000",
                label_visibility="collapsed",
            )
            needs_amt = rows[i]["act"] not in ["check", "fold", "call"]
            if needs_amt and rows[i]["amt"] == "":
                # 軽いガイドのみ（エラーはプレビューで弾く）
                st.caption("※ 数字を入力", help="bet/raise/3betなどは金額が必要です")

        # 行削除ボタン（縦位置をCSSで合わせる）
        with cols[3]:
            if st.button("🗑️", key=f"{key}_del_{i}"):
                to_del.append(i)

        st.markdown("</div>", unsafe_allow_html=True)

    # 後ろから消すとインデックスが崩れない
    for i in reversed(to_del):
        rows.pop(i)

    # 1行追加
    if st.button(f"+ 行を追加（{title}）", key=f"{key}_add"):
        rows.append(
            {
                "pos": "Hero" if postflop else "UTG",
                "act": "check" if postflop else "open",
                "amt": "",
            }
        )

    # プレビュー（エラーのある行は除外して出力）
    parts = []
    for r in rows:
        ok, text, _ = normalize_line(r["pos"], r["act"], r["amt"])
        if ok:
            parts.append(text)
    st.caption(" / ".join(parts) if parts else "（未入力）")


# 各ストリートを描画
street_block("pre", "プリフロップ", postflop=False)
street_block("flop", "フロップ", postflop=True)
street_block("turn", "ターン", postflop=True)
street_block("river", "リバー", postflop=True)

# ==== 解析ボタン & チャット（解析後のみ表示） =======================
def build_flow_text() -> str:
    """現在のアクション入力をLLM向けの文章ブロックに整形（モック用）"""
    def join(key: str) -> str:
        out = []
        for r in st.session_state.flow[key]:
            ok, text, _ = normalize_line(r["pos"], r["act"], r["amt"])
            if ok:
                out.append(text)
        return " / ".join(out) if out else "（なし）"

    return f"""・プリフロップ
　{join('pre')}
・フロップ
　{join('flop')}
・ターン
　{join('turn')}
・リバー
　{join('river')}"""


# 解析を実行（ここではモックでメッセージを詰めるだけ）
if st.button("解析する", use_container_width=True):
    # 既存の build_flow_text() を再利用
    flow_text = build_flow_text()

    # 解析を実行（APIコール）
    answer = call_gpt(
        level=level,
        hero_cards=[hero_c1, hero_c2],
        board=[flop_1, flop_2, flop_3, turn, river],
        villains=st.session_state.villains,
        flow_text=flow_text
    )

    # チャットUIは解析後にだけ開く仕様
    st.session_state.show_chat = True
    st.session_state.messages.append({"role":"user","content":"解析してください"})
    st.session_state.messages.append({"role":"assistant","content":answer})


st.divider()

# 解析後だけチャットUIを表示
if st.session_state.show_chat:
    st.subheader("チャット")
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    # ユーザー入力（今はモック応答）
    if q := st.chat_input("質問を入力…"):
        st.session_state.messages.append({"role": "user", "content": q})
        st.session_state.messages.append(
            {"role": "assistant", "content": "（モック）LLM接続は後でONにします。"}
        )
