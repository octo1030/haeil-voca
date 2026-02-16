import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
import random
import re
import time
from openai import OpenAI

# [1] 시스템 설정 및 연결
os.environ["PYTHONIOENCODING"] = "utf-8"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(): return conn.read(ttl=0)
def save_data(df): conn.update(data=df)

# [2] OpenAI API
try:
    api_key = st.secrets.get("OPENAI_API_KEY", "").strip()
    client = OpenAI(api_key=api_key)
except Exception as e: st.error(f"API Key Error: {e}")

# [3] 앱 설정 및 모바일 극한 최적화 (가독성 & UI)
st.set_page_config(page_title="Haeil's Smart Voca", page_icon="🏎️", layout="centered")

st.markdown("""
    <style>
    /* 전체 폰트 압축 */
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    
    /* 단어장: 한 줄 레이아웃 강제 (Flexbox) */
    .word-line {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 5px;
        border-bottom: 1px solid #f0f0f0;
    }
    .word-info { flex: 1; display: flex; align-items: baseline; gap: 8px; overflow: hidden; }
    .w-main { font-weight: bold; font-size: 15px; white-space: nowrap; }
    .w-mean { color: #666; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    
    /* 삭제 버튼: 배경 빼고 아이콘만 작게 */
    .stButton > button[key^="del_"] {
        background: none !important;
        border: none !important;
        padding: 0 !important;
        color: #ddd !important;
        font-size: 14px !important;
        width: 30px !important;
    }
    
    /* 퀴즈 박스 압축 */
    .q-container { background: #f8f9fa; border-radius: 12px; padding: 15px; text-align: center; border: 1px solid #eee; margin-bottom: 10px; }
    .h-text { font-size: 12px; color: #999; text-align: center; margin-bottom: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- 사이드바 및 메뉴 (강제 종료 트리거) ---
if 'menu_selection' not in st.session_state: st.session_state.menu_selection = "새 단어 추가"
if 'quiz_state' not in st.session_state: st.session_state.quiz_state = 'setup'

with st.sidebar:
    st.title("🚀 Haeil's Voca")
    pages = ["새 단어 추가", "단어장 보기", "📊 대시보드", "QUIZ!!"]
    for page in pages:
        if st.button(page, use_container_width=True, key=f"btn_{page}"):
            st.session_state.menu_selection = page
            # JS: 사이드바 닫기 버튼 및 오버레이 클릭 (강제성 강화)
            st.components.v1.html("""
                <script>
                const parentDoc = window.parent.document;
                const closeBtn = parentDoc.querySelector('button[aria-label="Close"]');
                const overlay = parentDoc.querySelector('div[data-testid="stSidebarCollapseByDrag"]');
                if (closeBtn) { closeBtn.click(); }
                else if (overlay) { overlay.click(); }
                </script>
            """, height=0)
            st.rerun()

menu = st.session_state.menu_selection

# --- 메뉴 2: 단어장 보기 (100% 한 줄 보장) ---
if menu == "단어장 보기":
    st.header("📚 나의 단어장")
    df = load_data()
    if not df.empty:
        for idx, row in df.iterrows():
            # 단어/뜻은 HTML로 묶어 왼쪽, 버튼은 Streamlit 버튼으로 오른쪽
            m_col1, m_col2 = st.columns([0.85, 0.15])
            with m_col1:
                st.markdown(f"""
                    <div class="word-info">
                        <span class="w-main">{row['word']}</span>
                        <span class="w-mean">{row['meaning']}</span>
                    </div>
                """, unsafe_allow_html=True)
            with m_col2:
                if st.button("🗑️", key=f"del_{idx}"):
                    df = df.drop(idx)
                    save_data(df); st.rerun()
            st.markdown("<hr style='margin:0; opacity:0.3;'>", unsafe_allow_html=True)
    else: st.info("저장된 단어가 없습니다.")

# --- 메뉴 4: QUIZ!! (포커스 유지 튜닝) ---
elif menu == "QUIZ!!":
    if st.session_state.quiz_state == 'setup':
        st.header("🧠 QUIZ")
        df = load_data()
        num_q = st.selectbox("문제 수", [5, 10, 20])
        if st.button("🚀 시작", use_container_width=True):
            # (8:2 로직 생략 없이 기존 유지)
            incorrect = df[df['mistakes'] > 0]
            new_words = df[df['mistakes'] == 0]
            pool = []
            pool.extend(incorrect.sample(n=min(len(incorrect), int(num_q*0.2))).to_dict('records'))
            n_rest = num_q - len(pool)
            pool.extend(df.sample(n=min(len(df), n_rest)).to_dict('records'))
            random.shuffle(pool)
            for item in pool:
                v_sents = [item[f's{i}'] for i in range(1, 11) if pd.notna(item[f's{i}'])]
                item['sel_sent'] = random.choice(v_sents)
            st.session_state.quiz_pool = pool
            st.session_state.total_q = len(pool)
            st.session_state.current_q_idx = 0
            st.session_state.results = []
            st.session_state.quiz_state = 'playing'
            st.rerun()

    elif st.session_state.quiz_state == 'playing':
        q_idx = st.session_state.current_q_idx
        row = st.session_state.quiz_pool[q_idx]
        word = str(row['word'])
        
        st.progress((q_idx) / st.session_state.total_q)
        masked = re.compile(re.escape(word), re.IGNORECASE).sub(" ( ______ ) ", row['sel_sent'])
        
        st.markdown(f"<div class='q-container'>{masked}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='h-text'>💡 {row['en_def']}</div>", unsafe_allow_html=True)

        # 포커스 고정 스크립트
        st.components.v1.html(f"""
            <script>
            setTimeout(() => {{
                const inputs = window.parent.document.querySelectorAll('input[type="text"]');
                const lastInput = inputs[inputs.length - 1];
                if (lastInput) {{
                    lastInput.focus();
                    lastInput.click();
                }}
            }}, 400);
            </script>
        """, height=0)

        with st.form(f"q_form_{q_idx}", clear_on_submit=True):
            ans = st.text_input("Answer", label_visibility="collapsed", key=f"ans_{q_idx}").strip()
            if st.form_submit_button("Submit", use_container_width=True):
                is_correct = ans.lower() == word.lower()
                st.session_state.results.append({"word": word, "is_correct": is_correct})
                if is_correct: st.success("🎯 Correct!")
                else: st.error(f"❌ Wrong: {word}")
                time.sleep(0.6) # 키보드 내려가는 시간 최소화
                st.session_state.current_q_idx += 1
                if st.session_state.current_q_idx >= st.session_state.total_q: st.session_state.quiz_state = 'finished'
                st.rerun()
