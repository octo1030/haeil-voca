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
try:
    api_key = st.secrets.get("OPENAI_API_KEY", "").strip()
    client = OpenAI(api_key=api_key)
except Exception as e: st.error(f"API Key Error: {e}")

# [3] 앱 설정 및 모바일 극한 최적화 CSS
st.set_page_config(page_title="Haeil's Smart Voca", page_icon="🏎️", layout="centered")

st.markdown("""
    <style>
    /* 1. 단어장 보기: 한 줄 레이아웃 및 삭제 버튼 미니멀화 */
    .word-row {
        display: grid;
        grid-template-columns: 1fr auto;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid #eee;
    }
    .word-content { font-size: 15px; line-height: 1.4; }
    .word-main { font-weight: bold; color: #333; margin-right: 8px; }
    .word-mean { color: #666; font-size: 14px; }
    
    /* 삭제 버튼을 단어 우측 끝에 아주 작게 배치 */
    div[data-testid="column"] button[key^="del_"] {
        padding: 0 !important;
        width: 25px !important;
        height: 25px !important;
        min-height: 25px !important;
        background: transparent !important;
        border: none !important;
        font-size: 12px !important;
        color: #ddd !important;
    }
    
    /* 2. 퀴즈 화면 컴팩트화 */
    .quiz-box { background: #f9f9f9; padding: 15px; border-radius: 8px; margin-bottom: 5px; text-align: center; }
    .hint-box { font-size: 13px; color: #888; margin-bottom: 10px; text-align: center; }

    /* 3. 사이드바 닫기 버튼(X) 강제 숨김 해제 및 모바일 대응 */
    @media (max-width: 768px) {
        [data-testid="stSidebarResponsiveLayer"] { max-width: 100vw; }
    }
    </style>
    """, unsafe_allow_html=True)

if 'menu_selection' not in st.session_state: st.session_state.menu_selection = "새 단어 추가"
if 'quiz_state' not in st.session_state: st.session_state.quiz_state = 'setup'

# --- [핵심 1] 사이드바 메뉴 (강제 종료 로직) ---
with st.sidebar:
    st.title("🚀 Haeil's Voca")
    st.divider()
    pages = ["새 단어 추가", "단어장 보기", "📊 대시보드", "QUIZ!!"]
    for page in pages:
        is_selected = st.session_state.menu_selection == page
        if st.button(f"{'📍 ' if is_selected else ''}{page}", use_container_width=True, key=f"m_{page}"):
            st.session_state.menu_selection = page
            # 자바스크립트를 사용하여 모바일 사이드바 닫기 버튼을 즉시 클릭
            st.components.v1.html("""
                <script>
                const closeBtn = window.parent.document.querySelector('button[aria-label="Close"]');
                if (closeBtn) closeBtn.click();
                </script>
            """, height=0)
            st.rerun()

menu = st.session_state.menu_selection

# --- 메뉴 2: 단어장 보기 (의도하신 대로 수정) ---
if menu == "단어장 보기":
    st.header("📚 나의 단어장")
    df = load_data()
    if not df.empty:
        st.caption(f"총 {len(df)}개")
        for idx, row in df.iterrows():
            # 컬럼을 나누어 단어/뜻은 왼쪽, 삭제 버튼은 오른쪽 끝에 배치
            col_left, col_right = st.columns([0.9, 0.1])
            with col_left:
                st.markdown(f"<div class='word-content'><span class='word-main'>{row['word']}</span><span class='word-mean'>{row['meaning']}</span></div>", unsafe_allow_html=True)
            with col_right:
                if st.button("🗑️", key=f"del_{idx}"):
                    df = df.drop(idx)
                    save_data(df); st.rerun()
            st.markdown("<hr style='margin:0; border:0; border-top:1px solid #eee;'>", unsafe_allow_html=True)
    else: st.info("등록된 단어가 없습니다.")

# --- 메뉴 4: QUIZ!! (자동 커서 및 키보드 유지 로직) ---
elif menu == "QUIZ!!":
    if st.session_state.quiz_state == 'setup':
        st.header("🧠 QUIZ!!")
        df = load_data()
        if df.empty: st.warning("단어를 먼저 등록해주세요!"); st.stop()
        with st.container(border=True):
            num_q = st.selectbox("문제 수", [5, 10, 20])
            if st.button("🚀 QUIZ START!", use_container_width=True):
                # 8:2 하이브리드 로직 (생략 방지용 기존 로직 유지)
                incorrect = df[df['mistakes'] > 0]
                new_words = df[df['mistakes'] == 0]
                n_inc = min(len(incorrect), int(num_q * 0.2))
                n_new = num_q - n_inc
                pool = []
                if n_inc > 0: pool.extend(incorrect.sample(n=n_inc).to_dict('records'))
                if n_new > 0: pool.extend(new_words.sample(n=min(n_new, len(new_words))).to_dict('records')) if len(new_words) >= n_new else pool.extend(df.sample(n=n_new).to_dict('records'))
                random.shuffle(pool)
                for item in pool:
                    v_sents = [item[f's{i}'] for i in range(1, 11) if pd.notna(item[f's{i}'])]
                    item['selected_sentence'] = random.choice(v_sents)
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
        masked_sentence = re.compile(re.escape(word), re.IGNORECASE).sub(" ( ______ ) ", row['selected_sentence'])
        st.markdown(f"<div class='quiz-box'>{masked_sentence}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='hint-box'>💡 {row['en_def']}</div>", unsafe_allow_html=True)

        # [핵심 3] 자동 포커스 스크립트 (모바일 키보드 유지 유도)
        st.components.v1.html(f"""
            <script>
            const focusInput = () => {{
                const inputs = window.parent.document.querySelectorAll('input[type="text"]');
                if (inputs.length > 0) {{
                    const lastInput = inputs[inputs.length - 1];
                    lastInput.focus();
                    // 모바일에서 키보드를 강제로 유지시키기 위한 탭 시뮬레이션
                    lastInput.click(); 
                }}
            }};
            setTimeout(focusInput, 500);
            </script>
        """, height=0)

        with st.form(f"q_{q_idx}", clear_on_submit=True):
            user_ans = st.text_input("Answer", label_visibility="collapsed", key=f"in_{q_idx}").strip()
            if st.form_submit_button("Submit", use_container_width=True):
                is_correct = user_ans.lower() == word.lower()
                st.session_state.results.append({"word": word, "user_ans": user_ans, "is_correct": is_correct})
                if is_correct: st.success("🎯 Correct!")
                else: st.error(f"❌ Wrong: {word}")
                time.sleep(0.8)
                st.session_state.current_q_idx += 1
                if st.session_state.current_q_idx >= st.session_state.total_q: st.session_state.quiz_state = 'finished'
                st.rerun()
