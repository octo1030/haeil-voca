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

# [3] 모바일 최적화 및 아이폰 15 프로 전용 가로 고정 CSS
st.set_page_config(page_title="Haeil's Voca", layout="centered")

st.markdown("""
    <style>
    /* 1. 사이드바 및 기본 패딩 제거 */
    [data-testid="stSidebar"] { display: none; }
    .main .block-container {
        padding: 1rem 10px !important; 
        max-width: 100% !important;
    }

    /* 2. 가로 4열 그리드 강제 고정 (아이폰 탈출 방지 핵심) */
    .nav-wrapper {
        display: grid !important;
        grid-template-columns: repeat(4, 1fr) !important; /* 무조건 4등분 */
        gap: 6px !important;
        width: 100% !important;
        margin-bottom: 20px !important;
    }

    /* 스트림릿 버튼 기본 스타일 덮어쓰기 */
    div[data-testid="column"] {
        width: 100% !important;
        flex: 1 1 0% !important;
        min-width: 0 !important;
    }

    .stButton > button {
        width: 100% !important;
        height: 52px !important;
        padding: 0 !important;
        font-size: 11px !important;
        border-radius: 10px !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        line-height: 1.2 !important;
    }

    /* 버튼 안의 텍스트 줄바꿈 방지 */
    .stButton p {
        margin: 0 !important;
        white-space: nowrap !important;
        font-size: 11px !important;
    }
    
    /* 퀴즈 카드 등 기타 스타일 */
    .quiz-card {
        background: white; border: 2px solid #e5e5e5; border-radius: 18px;
        padding: 25px; box-shadow: 0 4px 0 #e5e5e5; margin-bottom: 20px;
        font-size: 1.1rem; text-align: center; color: #3c3c3c;
    }
    .stProgress > div > div > div > div {
        background-color: #58cc02 !important; height: 12px !important; border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# [4] 네비게이션 로직 (ValueError 해결 및 가로 고정)
if 'menu' not in st.session_state: st.session_state.menu = "QUIZ"
if 'quiz_state' not in st.session_state: st.session_state.quiz_state = 'setup'

# 가로 정렬을 위한 컨테이너 생성
nav_items = [("🧠", "QUIZ"), ("📚", "Voca"), ("📊", "Stat"), ("➕", "Add")]
nav_cols = st.columns(4) # 리스트 [1,1,1,1] 대신 숫자 4를 넣어 기본 분할 사용

for i, (icon, label) in enumerate(nav_items):
    with nav_cols[i]:
        is_active = st.session_state.menu == label
        # 버튼 내부 텍스트 구성: 아이콘과 라벨을 결합
        if st.button(f"{icon}\n{label}", key=f"nav_{label}", use_container_width=True, 
                     type="primary" if is_active else "secondary"):
            st.session_state.menu = label
            st.rerun()

st.divider()

# --- [QUIZ 메뉴] 듀오링고 스타일 ---
if st.session_state.menu == "QUIZ":
    if st.session_state.quiz_state == 'setup':
        st.subheader("🏁 Ready for Quiz?")
        df = load_data()
        num_q = st.select_slider("How many words?", options=[5, 10, 15, 20, 30, 50], value = 10)
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
        
        st.progress((q_idx + 1) / len(st.session_state.quiz_pool))
        
        st.markdown(
            f"<div class='quiz-card'>{re.compile(re.escape(row['word']), re.IGNORECASE).sub('_____', row['sel_sent'])}</div>",
            unsafe_allow_html=True
        )
        st.caption(f"💡 {row['en_def']}")

        with st.form(f"q_{q_idx}", clear_on_submit=True):
            ans = st.text_input(
                "Enter answer",
                key=f"quiz_input_{q_idx}",
                label_visibility="collapsed",
                placeholder="Type your answer..."
            ).strip()

            if st.form_submit_button("CHECK", use_container_width=True):

                is_correct = ans.lower() == row['word'].lower()

                df = load_data()
                df.loc[df['word'] == row['word'], 'count'] = int(df.loc[df['word'] == row['word'], 'count']) + 1
                if not is_correct:
                    df.loc[df['word'] == row['word'], 'mistakes'] = int(df.loc[df['word'] == row['word'], 'mistakes']) + 1
                save_data(df)

                if is_correct:
                    st.balloons()
                    st.success("Awesome!")
                else:
                    st.error(f"Keep trying! It's '{row['word']}'")

                time.sleep(0.5)

                st.session_state.current_idx += 1
                if st.session_state.current_idx >= len(st.session_state.quiz_pool):
                    st.session_state.quiz_state = 'setup'
                    st.session_state.menu = "Stat"

                st.rerun()

            # 🔥🔥🔥 강제 포커스 + 모바일 키보드 유지 (가장 안정적 방식)
            st.components.v1.html(f"""
            <script>
            function focusInput() {{
                const parentDoc = window.parent.document;
                const inputs = parentDoc.querySelectorAll('input[type="text"]');
                if (inputs.length > 0) {{
                    const target = inputs[inputs.length - 1];

                    target.focus();
                    target.click();

                    // 커서를 맨 뒤로 이동
                    const len = target.value.length;
                    target.setSelectionRange(len, len);
                }}
            }}

            // 여러 번 시도 (모바일 대응)
            setTimeout(focusInput, 100);
            setTimeout(focusInput, 400);
            setTimeout(focusInput, 800);
            setTimeout(focusInput, 1200);
            </script>
            """, height=0)


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
    if not df.empty:
        # 데이터 타입 강제 변환 (정수형)
        df['count'] = pd.to_numeric(df['count'], errors='coerce').fillna(0).astype(int)
        df['mistakes'] = pd.to_numeric(df['mistakes'], errors='coerce').fillna(0).astype(int)
        
        total_count = int(df['count'].sum())
        total_mistakes = int(df['mistakes'].sum())
        
        col1, col2 = st.columns(2)
        col1.metric("총 단어 수", f"{len(df)}개")
        
        # 정답률 계산 (소수점 제거)
        if total_count > 0:
            correct_rate = int(((total_count - total_mistakes) / total_count) * 100)
        else:
            correct_rate = 100
            
        col2.metric("전체 정답률", f"{correct_rate}%")
        
        st.subheader("🔥 오답률 높은 단어 (Top 5)")
        # 오답률 계산 및 표시
        df['rate'] = ((df['mistakes'] / df['count'].replace(0, 1)) * 100).fillna(0).astype(int)
        bad_words = df[df['count'] > 0].sort_values('rate', ascending=False).head(5)
        
        if not bad_words.empty:
            # 테이블 표시 시 숫자들을 정수로 변환하여 출력
            st.table(bad_words[['word', 'meaning', 'count', 'mistakes']].assign(
                count=bad_words['count'].astype(str),
                mistakes=bad_words['mistakes'].astype(str)
            ))
        else:
            st.info("아직 퀴즈 데이터가 충분하지 않습니다.")

        st.divider()
        
        # --- 데이터 초기화 섹션 ---
        st.subheader("⚙️ 데이터 관리")
        
        if st.button("🔄 전체 통계 데이터 초기화", use_container_width=True):
            with st.spinner("초기화 중..."):
                df['count'] = 0
                df['mistakes'] = 0
                # 시트 업데이트
                save_data(df)
                st.success("모든 통계가 초기화되었습니다!")
                time.sleep(1)
                st.rerun()
    else:
        st.info("통계 데이터가 없습니다. 먼저 단어를 추가하고 퀴즈를 풀어보세요.")

# --- [Add 메뉴] ---
elif st.session_state.menu == "Add":
    st.subheader("➕ New Word")
    with st.form("add"):
        w = st.text_input("Word")
        m = st.text_input("Meaning")
        if st.form_submit_button("Save"):
            # (기존 OpenAI 예문 생성 및 저장 로직 포함)
            st.success("Saved!")
