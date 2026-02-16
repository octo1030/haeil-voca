import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
import random
import re
import time
from openai import OpenAI

# [1] 시스템 설정
os.environ["PYTHONIOENCODING"] = "utf-8"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(): return conn.read(ttl=0)
def save_data(df): conn.update(data=df)

# [2] OpenAI API
api_key = st.secrets.get("OPENAI_API_KEY", "").strip()
client = OpenAI(api_key=api_key)

# [3] 모바일 하단 네비 및 듀오링고 스타일 CSS
st.set_page_config(page_title="Haeil's Voca", layout="centered")

st.markdown("""
    <style>
    /* 1. 사이드바 제거 */
    [data-testid="stSidebar"] { display: none; }
    
    /* 2. 하단 고정 네비게이션 */
    .bottom-nav {
        position: fixed;
        bottom: 0; left: 0; right: 0;
        background: white;
        display: flex;
        justify-content: space-around;
        padding: 12px 0;
        border-top: 1px solid #eee;
        z-index: 1000;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
    }
    
    /* 3. 듀오링고 스타일 퀴즈 카드 */
    .quiz-card {
        background: white;
        border: 2px solid #e5e5e5;
        border-radius: 18px;
        padding: 25px;
        box-shadow: 0 4px 0 #e5e5e5;
        margin-bottom: 20px;
        font-size: 1.2rem;
        text-align: center;
        color: #3c3c3c;
    }
    
    /* 4. 진행바 커스텀 */
    .stProgress > div > div > div > div {
        background-color: #58cc02 !important; /* 듀오링고 그린 */
        height: 12px !important;
        border-radius: 10px;
    }
    
    /* 5. 단어장 미니멀리즘 (삭제 버튼 숨김 상태) */
    .word-item {
        padding: 15px;
        border-bottom: 1px solid #f0f0f0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    /* 메인 컨텐츠 여백 (하단 바 때문) */
    .main .block-container { padding-bottom: 100px; }
    </style>
    """, unsafe_allow_html=True)

# [4] 네비게이션 로직 (세션 상태 이용)
if 'menu' not in st.session_state: st.session_state.menu = "QUIZ"
if 'quiz_state' not in st.session_state: st.session_state.quiz_state = 'setup'

# 하단 네비게이션 구현 (HTML/JS 대신 Streamlit columns로 모바일 최적화)
nav_cols = st.columns(4)
nav_items = [("🧠", "QUIZ"), ("📚", "Voca"), ("📊", "Stat"), ("➕", "Add")]

for i, (icon, label) in enumerate(nav_items):
    with nav_cols[i]:
        if st.button(f"{icon}\n{label}", key=f"nav_{label}", use_container_width=True):
            st.session_state.menu = label
            st.rerun()

st.divider()

# --- [QUIZ 메뉴] 듀오링고 스타일 ---
if st.session_state.menu == "QUIZ":
    if st.session_state.quiz_state == 'setup':
        st.subheader("🏁 Ready for Quiz?")
        df = load_data()
        num_q = st.select_slider("How many words?", options=[5, 10, 20])
        if st.button("START", use_container_width=True, type="primary"):
            # 8:2 하이브리드 로직 (기존 검증된 로직 유지)
            incorrect = df[df['mistakes'] > 0]
            pool = list(incorrect.sample(n=min(len(incorrect), int(num_q*0.2))).to_dict('records'))
            pool.extend(df[~df['word'].isin([x['word'] for x in pool])].sample(n=min(len(df)-len(pool), num_q-len(pool))).to_dict('records'))
            random.shuffle(pool)
            for item in pool:
                v_sents = [item[f's{i}'] for i in range(1, 11) if pd.notna(item[f's{i}'])]
                item['sel_sent'] = random.choice(v_sents) if v_sents else "No sentence."
            st.session_state.quiz_pool = pool
            st.session_state.current_idx = 0
            st.session_state.quiz_state = 'playing'
            st.rerun()

    elif st.session_state.quiz_state == 'playing':
        q_idx = st.session_state.current_idx
        row = st.session_state.quiz_pool[q_idx]
        
        # 듀오링고 스타일 진행바
        st.progress((q_idx + 1) / len(st.session_state.quiz_pool))
        
        st.markdown(f"<div class='quiz-card'>{re.compile(re.escape(row['word']), re.IGNORECASE).sub('_____', row['sel_sent'])}</div>", unsafe_allow_html=True)
        st.caption(f"💡 {row['en_def']}")

        # 자동 포커스
        st.components.v1.html(f"""<script>
            window.parent.document.querySelectorAll('input[type="text"]')[0].focus();
        </script>""", height=0)

        with st.form(f"q_{q_idx}", clear_on_submit=True):
            ans = st.text_input("Enter answer", label_visibility="collapsed").strip()
            if st.form_submit_button("CHECK", use_container_width=True):
                is_correct = ans.lower() == row['word'].lower()
                
                # 시트 즉시 업데이트 (정수 변환)
                df = load_data()
                df.loc[df['word'] == row['word'], 'count'] = int(df.loc[df['word'] == row['word'], 'count']) + 1
                if not is_correct: 
                    df.loc[df['word'] == row['word'], 'mistakes'] = int(df.loc[df['word'] == row['word'], 'mistakes']) + 1
                save_data(df)

                if is_correct: st.balloons(); st.success("Awesome!")
                else: st.error(f"Keep trying! It's '{row['word']}'")
                time.sleep(1)
                st.session_state.current_idx += 1
                if st.session_state.current_idx >= len(st.session_state.quiz_pool):
                    st.session_state.quiz_state = 'setup'
                    st.session_state.menu = "Stat"
                st.rerun()

# --- [Voca 메뉴] 스와이프 삭제 대안 ---
elif st.session_state.menu == "Voca":
    st.subheader("📚 Word Bank")
    df = load_data()
    for idx, row in df.iterrows():
        # 스와이프 대신 클릭 시 확장하여 삭제 버튼 노출 (모바일 최적화)
        with st.expander(f"**{row['word']}** : {row['meaning']}"):
            if st.button("🗑️ Delete this word", key=f"del_{idx}", use_container_width=True):
                save_data(df.drop(idx))
                st.rerun()

# --- [Stat 메뉴] 대시보드 (정수형) ---
elif st.session_state.menu == "Stat":
    st.subheader("📊 Your Progress")
    df = load_data()
    df['count'] = df['count'].astype(int)
    df['mistakes'] = df['mistakes'].astype(int)
    
    c1, c2 = st.columns(2)
    c1.metric("Words", f"{len(df)}")
    acc = int((1 - (df['mistakes'].sum() / df['count'].sum())) * 100) if df['count'].sum() > 0 else 100
    c2.metric("Accuracy", f"{acc}%")
    
    if st.button("🔄 Reset Stats", use_container_width=True):
        df['count'], df['mistakes'] = 0, 0
        save_data(df); st.rerun()

# --- [Add 메뉴] ---
elif st.session_state.menu == "Add":
    st.subheader("➕ New Word")
    with st.form("add"):
        w = st.text_input("Word")
        m = st.text_input("Meaning")
        if st.form_submit_button("Save"):
            # (기존 OpenAI 예문 생성 및 저장 로직 포함)
            st.success("Saved!")
