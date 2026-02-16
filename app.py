import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
import random
import re
import time
from openai import OpenAI
import streamlit.components.v1 as components

# -------------------------------------------------
# [1] 기본 설정
# -------------------------------------------------
st.set_page_config(
    page_title="Haeil's Smart Voca",
    page_icon="🏎️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

os.environ["PYTHONIOENCODING"] = "utf-8"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    return conn.read(ttl=0)

def save_data(df):
    conn.update(data=df)

# -------------------------------------------------
# [2] 모바일 자동 감지
# -------------------------------------------------
if "is_mobile" not in st.session_state:
    st.session_state.is_mobile = False

components.html("""
<script>
const width = window.innerWidth;
const isMobile = width < 768;
window.parent.postMessage(
    {type: "streamlit:setComponentValue", value: isMobile},
    "*"
);
</script>
""", height=0)

IS_MOBILE = st.session_state.get("is_mobile", False)

# -------------------------------------------------
# [3] OpenAI 설정
# -------------------------------------------------
api_key = st.secrets.get("OPENAI_API_KEY", "").strip()
client = OpenAI(api_key=api_key)

# -------------------------------------------------
# [4] GPT 콘텐츠 생성
# -------------------------------------------------
def generate_content(word):
    prompt = f"""Provide an English definition and 10 high-quality example sentences for '{word}'.
RULES:
1. The word MUST appear in every sentence.
2. The definition must NOT contain the word.
Format:
DEF: definition
SENT: sentence (10 lines)"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a precise English lexicographer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )

        content = response.choices[0].message.content
        en_def = re.search(r"DEF:\s*(.*)", content).group(1)
        sentences = re.findall(r"SENT:\s*(.*)", content)
        return en_def, sentences[:10]

    except Exception as e:
        st.error(f"GPT 오류: {e}")
        return None, None

# -------------------------------------------------
# 상태 초기화
# -------------------------------------------------
if 'menu_selection' not in st.session_state:
    st.session_state.menu_selection = "새 단어 추가"

if 'quiz_state' not in st.session_state:
    st.session_state.quiz_state = 'setup'

# -------------------------------------------------
# 사이드바
# -------------------------------------------------
with st.sidebar:
    st.title("🚀 Haeil's Voca")
    pages = ["새 단어 추가", "단어장 보기", "QUIZ!!", "📊 통계 대시보드"]

    for page in pages:
        if st.button(page, use_container_width=True):
            st.session_state.menu_selection = page
            st.rerun()

menu = st.session_state.menu_selection

# -------------------------------------------------
# 1️⃣ 새 단어 추가
# -------------------------------------------------
if menu == "새 단어 추가":

    st.header("➕ 새 단어 등록")

    with st.form("add_form", clear_on_submit=True):
        word = st.text_input("영어 단어").strip()
        meaning = st.text_input("뜻").strip()
        submitted = st.form_submit_button("등록")

    if submitted and word and meaning:
        df = load_data()
        if word.lower() in df['word'].astype(str).str.lower().values:
            st.warning("이미 존재하는 단어입니다.")
        else:
            with st.spinner("AI 예문 생성 중..."):
                en_def, sentences = generate_content(word)
                if en_def:
                    new_row = {
                        "word": word,
                        "meaning": meaning,
                        "en_def": en_def,
                        "count": 0,
                        "mistakes": 0
                    }
                    for i in range(10):
                        new_row[f"s{i+1}"] = sentences[i]

                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    save_data(df)
                    st.success("저장 완료!")

# -------------------------------------------------
# 2️⃣ 단어장 보기
# -------------------------------------------------
elif menu == "단어장 보기":

    st.header("📚 나의 단어장")
    df = load_data()

    if df.empty:
        st.info("단어가 없습니다.")
    else:
        df["wrong_rate"] = df.apply(
            lambda r: (r["mistakes"]/r["count"]*100) if r["count"]>0 else 0,
            axis=1
        )

        sort_option = st.selectbox(
            "정렬 기준",
            ["기본", "오답률 높은 순", "풀이 많은 순"]
        )

        if sort_option == "오답률 높은 순":
            df = df.sort_values("wrong_rate", ascending=False)
        elif sort_option == "풀이 많은 순":
            df = df.sort_values("count", ascending=False)

        for idx, row in df.iterrows():
            st.markdown(f"""
            <div style="
                padding:12px;
                border-radius:10px;
                background:#f8f9fa;
                margin-bottom:8px;
                border:1px solid #ddd;">
                <b>{row['word']}</b><br>
                {row['meaning']}<br>
                풀이 {int(row['count'])}회 |
                오답률 {row['wrong_rate']:.1f}%
            </div>
            """, unsafe_allow_html=True)

# -------------------------------------------------
# 3️⃣ QUIZ (8:2 유지)
# -------------------------------------------------
elif menu == "QUIZ!!":

    st.header("🧠 QUIZ")

    if st.session_state.quiz_state == "setup":

        df = load_data()
        if df.empty:
            st.warning("단어를 먼저 추가하세요.")
            st.stop()

        num_q = st.selectbox("문제 수", [5,10,20])

        if st.button("START"):
            incorrect = df[df["mistakes"] > 0]
            new_words = df[df["mistakes"] == 0]

            n_inc = min(len(incorrect), int(num_q*0.2))
            n_new = num_q - n_inc

            pool = []
            if n_inc>0:
                pool += incorrect.sample(n=n_inc).to_dict("records")
            if n_new>0:
                pool += new_words.sample(n=min(n_new,len(new_words))).to_dict("records")

            random.shuffle(pool)

            st.session_state.quiz_pool = pool
            st.session_state.current = 0
            st.session_state.results = []
            st.session_state.total = len(pool)
            st.session_state.quiz_state = "playing"
            st.rerun()

    elif st.session_state.quiz_state == "playing":

        idx = st.session_state.current
        row = st.session_state.quiz_pool[idx]
        word = row["word"]
        sentence = random.choice([row[f"s{i}"] for i in range(1,11)])

        masked = re.sub(word, "(____)", sentence, flags=re.I)
        st.markdown(f"### {masked}")

        user_ans = st.text_input("정답 입력", key=f"quiz_{idx}")

        submit = st.button("제출")

        components.html("""
        <script>
        setTimeout(()=>{
            const inputs = window.parent.document.querySelectorAll('input[type="text"]');
            if(inputs.length>0) inputs[inputs.length-1].focus();
        },200);
        </script>
        """, height=0)

        if submit and user_ans:
            correct = user_ans.lower() == word.lower()
            st.session_state.results.append((word, correct))

            df = load_data()
            df.loc[df["word"]==word,"count"] += 1
            if not correct:
                df.loc[df["word"]==word,"mistakes"] += 1
            save_data(df)

            st.session_state.current += 1
            if st.session_state.current >= st.session_state.total:
                st.session_state.quiz_state = "finished"
            st.rerun()

    elif st.session_state.quiz_state == "finished":
        st.header("🏆 결과")

        correct_count = sum([1 for _,c in st.session_state.results if c])
        total = len(st.session_state.results)

        st.metric("정답률", f"{correct_count/total*100:.1f}%")

        if st.button("다시 시작"):
            st.session_state.quiz_state="setup"
            st.rerun()

# -------------------------------------------------
# 4️⃣ 통계 대시보드
# -------------------------------------------------
elif menu == "📊 통계 대시보드":

    st.header("📊 학습 통계")

    df = load_data()
    if df.empty:
        st.info("데이터 없음")
    else:
        total_words = len(df)
        total_attempts = df["count"].sum()
        total_mistakes = df["mistakes"].sum()
        accuracy = (total_attempts-total_mistakes)/total_attempts*100 if total_attempts>0 else 0

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("총 단어", total_words)
        c2.metric("총 풀이", total_attempts)
        c3.metric("총 오답", total_mistakes)
        c4.metric("전체 정답률", f"{accuracy:.1f}%")

        df["wrong_rate"] = df.apply(
            lambda r: (r["mistakes"]/r["count"]*100) if r["count"]>0 else 0,
            axis=1
        )

        df = df.sort_values("wrong_rate", ascending=False)

        st.subheader("🔥 오답률 높은 단어")

        for _,row in df.iterrows():
            st.write(f"{row['word']} - 오답률 {row['wrong_rate']:.1f}%")
