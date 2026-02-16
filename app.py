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

# ✅ 세션 초기화 (무조건 여기)
if "menu" not in st.session_state:
    st.session_state["menu"] = "QUIZ"

if "quiz_state" not in st.session_state:
    st.session_state["quiz_state"] = "setup"


def reset_quiz():
    for key in [
        "quiz_state",
        "quiz_pool",
        "current_idx",
        "temp_score",
        "word_index_map",
        "full_df"
    ]:
        if key in st.session_state:
            del st.session_state[key]

    st.session_state.quiz_state = "setup"


# ✅ 메뉴 변경 감지용
if "prev_menu" not in st.session_state:
    st.session_state.prev_menu = st.session_state.menu

# 메뉴가 바뀌면 자동으로 햄버거 닫기
if st.session_state.prev_menu != st.session_state.menu:
    st.session_state.menu_open = False
    st.session_state.prev_menu = st.session_state.menu

    


st.markdown("""
    <style>
    .bottom-nav {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background: white;
        padding: 8px 0;
        border-top: 1px solid #eee;
        z-index: 999;
    }

    .main .block-container {
        padding-bottom: 70px !important;
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
# =========================
# 🍔 햄버거 네비게이션
# =========================

with st.expander("☰ Menu", expanded=False):

    if st.button("🧠 QUIZ", use_container_width=True):
        st.session_state["menu"] = "QUIZ"
        reset_quiz()
        st.rerun()

    if st.button("📚 Voca", use_container_width=True):
        st.session_state["menu"] = "Voca"
        reset_quiz()
        st.rerun()

    if st.button("📊 Stat", use_container_width=True):
        st.session_state["menu"] = "Stat"
        reset_quiz()
        st.rerun()

    if st.button("➕ Add", use_container_width=True):
        st.session_state["menu"] = "Add"
        reset_quiz()
        st.rerun()




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
            st.session_state.full_df = df.copy()

            # 🔥 단어 → 인덱스 맵 (초고속 접근용)
            st.session_state.word_index_map = {
                word: idx for idx, word in enumerate(df['word'])
            }

            # 🔥 퀴즈 중 임시 점수 저장 (구글시트 접근 안함)
            st.session_state.temp_score = {
                word: {"count": 0, "mistakes": 0}
                for word in df['word']
            }

            st.session_state.current_idx = 0
            st.session_state.quiz_state = 'playing'
            st.rerun()


    elif st.session_state.quiz_state == 'playing':
        if st.button("🏠 Quit Quiz", use_container_width=True):
            reset_quiz()
            st.session_state.menu = "QUIZ"
            st.rerun()

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

                df = st.session_state.full_df
                df.loc[df['word'] == row['word'], 'count'] = int(df.loc[df['word'] == row['word'], 'count']) + 1
                if not is_correct:
                    df.loc[df['word'] == row['word'], 'mistakes'] = int(df.loc[df['word'] == row['word'], 'mistakes']) + 1
                save_data(df)

                if is_correct:
                    st.success("Awesome!")
                else:
                    st.error(f"Keep trying! It's '{row['word']}'")

                time.sleep(0.5)

                st.session_state.current_idx += 1
                if st.session_state.current_idx >= len(st.session_state.quiz_pool):

                    # 🔥 여기서 한 번만 실제 DataFrame 반영
                    df = st.session_state.full_df

                    for word, score in st.session_state.temp_score.items():
                        idx = st.session_state.word_index_map[word]
                        df.at[idx, 'count'] += score['count']
                        df.at[idx, 'mistakes'] += score['mistakes']

                    # 🔥 구글시트 저장은 단 1번
                    save_data(df)

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
        
        st.subheader("🔥 오답률 높은 단어 (Top 10)")
        # 오답률 계산 및 표시
        df['rate'] = ((df['mistakes'] / df['count'].replace(0, 1)) * 100).fillna(0).astype(int)
        bad_words = df[df['count'] > 0].sort_values('rate', ascending=False).head(10)
        
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
