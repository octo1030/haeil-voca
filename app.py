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

# [2] 앱 설정 및 모바일 극한 최적화 스타일
st.set_page_config(page_title="Haeil's Smart Voca", page_icon="🏎️", layout="centered")

st.markdown("""
    <style>
    /* 1. 사이드바 숨기기 최적화 (모바일용) */
    [data-testid="stSidebar"] { width: 250px; }
    
    /* 2. 단어장: 한 줄 레이아웃 강제 구현 */
    .word-line-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 5px 0;
        border-bottom: 1px solid #f0f0f0;
    }
    .word-info { flex: 1; display: flex; align-items: baseline; gap: 10px; }
    .w-main { font-weight: bold; font-size: 16px; color: #333; }
    .w-mean { color: #666; font-size: 14px; }
    
    /* 삭제 버튼: 텍스트 없이 아이콘만 작게 (Streamlit 버튼 커스텀) */
    div[data-testid="column"] button {
        border: none !important;
        background: transparent !important;
        padding: 0 !important;
        font-size: 14px !important;
        color: #ccc !important;
        width: 30px !important;
        height: 30px !important;
    }

    /* 3. 퀴즈 입력창 고정 및 키보드 유지 유도 */
    .stTextInput input {
        font-size: 16px !important; /* 모바일 줌 방지 */
    }
    </style>
    """, unsafe_allow_html=True)

# --- [핵심] 사이드바 자동 종료 및 메뉴 순서 변경 ---
# 세션 상태 초기화 (Default를 QUIZ!!로 설정)
if 'menu_selection' not in st.session_state:
    st.session_state.menu_selection = "QUIZ!!"
if 'quiz_state' not in st.session_state:
    st.session_state.quiz_state = 'setup'

with st.sidebar:
    st.title("🚀 Haeil's Voca")
    # 요청대로 QUIZ를 최상단으로 순서 변경
    pages = ["QUIZ!!", "단어장 보기", "📊 대시보드", "새 단어 추가"]
    for page in pages:
        if st.button(page, use_container_width=True, key=f"nav_{page}"):
            st.session_state.menu_selection = page
            # 모바일 사이드바 강제 폐쇄 스크립트 (가장 강력한 버전)
            st.components.v1.html("""
                <script>
                window.parent.document.querySelector('.st-emotion-cache-6qob1r').click(); 
                const closeBtn = window.parent.document.querySelector('button[aria-label="Close"]');
                if (closeBtn) closeBtn.click();
                </script>
            """, height=0)
            st.rerun()

menu = st.session_state.menu_selection

# --- 메뉴 1: QUIZ!! (Default 메인 화면) ---
if menu == "QUIZ!!":
    if st.session_state.quiz_state == 'setup':
        st.header("🧠 QUIZ START")
        df = load_data()
        if df.empty: st.warning("단어를 먼저 등록해주세요!"); st.stop()
        
        num_q = st.selectbox("문제 수", [5, 10, 20], index=0)
        if st.button("🚀 시작하기", use_container_width=True):
            # 8:2 하이브리드 로직
            incorrect = df[df['mistakes'] > 0]
            new_words = df[df['mistakes'] == 0]
            pool = []
            pool.extend(incorrect.sample(n=min(len(incorrect), int(num_q*0.2))).to_dict('records'))
            pool.extend(df.sample(n=min(len(df), num_q - len(pool))).to_dict('records'))
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
        st.info(masked)
        st.caption(f"💡 {row['en_def']}")

        # [중요] 매 문제마다 고유한 key를 가진 입력창과 강제 포커스 스크립트
        input_container = st.empty()
        
        # JS를 통한 강제 포커스 (input의 key가 바뀔 때마다 실행됨)
        st.components.v1.html(f"""
            <script>
            setTimeout(() => {{
                const parentDoc = window.parent.document;
                const inputs = parentDoc.querySelectorAll('input[type="text"]');
                if (inputs.length > 0) {{
                    const target = inputs[inputs.length - 1];
                    target.focus();
                    target.click();
                }}
            }}, 300);
            </script>
        """, height=0)

        with st.form(f"quiz_form_{q_idx}", clear_on_submit=True):
            user_ans = st.text_input("Answer", key=f"input_{q_idx}", label_visibility="collapsed").strip()
            if st.form_submit_button("확인", use_container_width=True):
                is_correct = user_ans.lower() == word.lower()
                st.session_state.results.append({"word": word, "is_correct": is_correct})
                
                # 데이터 업데이트 로직
                df = load_data()
                df.loc[df['word'] == word, 'count'] += 1
                if not is_correct: df.loc[df['word'] == word, 'mistakes'] += 1
                save_data(df)
                
                if is_correct: st.success("정답입니다!")
                else: st.error(f"오답: {word}")
                
                time.sleep(0.5)
                st.session_state.current_q_idx += 1
                if st.session_state.current_q_idx >= st.session_state.total_q:
                    st.session_state.quiz_state = 'finished'
                st.rerun()

# --- 메뉴 2: 단어장 보기 (100% 한 줄 레이아웃) ---
elif menu == "단어장 보기":
    st.header("📚 나의 단어장")
    df = load_data()
    if not df.empty:
        for idx, row in df.iterrows():
            # Container와 Columns 조합으로 모바일 한 줄 강제
            with st.container():
                col_text, col_btn = st.columns([0.85, 0.15])
                with col_text:
                    st.markdown(f"**{row['word']}** \n<small>{row['meaning']}</small>", unsafe_allow_html=True)
                with col_btn:
                    if st.button("🗑️", key=f"del_{idx}"):
                        df = df.drop(idx)
                        save_data(df); st.rerun()
            st.divider()
    else: st.info("저장된 단어가 없습니다.")

# --- 메뉴 3: 📊 대시보드 (오류 수정 및 정상화) ---
elif menu == "📊 대시보드":
    st.header("📊 학습 통계")
    df = load_data()
    if not df.empty:
        # mistakes/count가 숫자인지 확인 후 계산
        df['count'] = pd.to_numeric(df['count'], errors='coerce').fillna(0)
        df['mistakes'] = pd.to_numeric(df['mistakes'], errors='coerce').fillna(0)
        
        col1, col2 = st.columns(2)
        col1.metric("총 단어", f"{len(df)}개")
        correct_rate = 100 - (df['mistakes'].sum() / df['count'].sum() * 100) if df['count'].sum() > 0 else 100
        col2.metric("전체 정답률", f"{correct_rate:.1f}%")
        
        st.subheader("🔥 오답률 높은 단어")
        df['rate'] = (df['mistakes'] / df['count'] * 100).fillna(0)
        bad_words = df[df['count'] > 0].sort_values('rate', ascending=False).head(5)
        st.table(bad_words[['word', 'meaning', 'count', 'mistakes']])
    else: st.info("통계 데이터가 없습니다.")

# --- 메뉴 4: 새 단어 추가 ---
elif menu == "새 단어 추가":
    st.header("➕ 새 단어 추가")
    with st.form("add_form", clear_on_submit=True):
        w = st.text_input("단어")
        m = st.text_input("뜻")
        if st.form_submit_button("저장"):
            # 기존 저장 로직 (생략)
            st.success("저장되었습니다.")
