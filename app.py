import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
import random
import re
import time
from openai import OpenAI

# [1] 시스템 및 연결 설정
os.environ["PYTHONIOENCODING"] = "utf-8"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    return conn.read(ttl=0)

def save_data(df):
    conn.update(data=df)

# [2] OpenAI API 설정
try:
    api_key = st.secrets.get("OPENAI_API_KEY", "").strip()
    client = OpenAI(api_key=api_key)
except Exception as e:
    st.error(f"OpenAI API 설정 오류: {e}")

# [3] 콘텐츠 생성 함수 (동일)
def generate_content(word):
    prompt = f"Provide an English definition and 10 high-quality, distinct example sentences for the word '{word}'..."
    # ... (기존 로직 유지)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "system", "content": "You are a precise English lexicographer."},
                      {"role": "user", "content": prompt}],
            temperature=0.4
        )
        content = response.choices[0].message.content
        en_def = re.search(r"DEF:\s*(.*)", content).group(1).strip()
        en_def = re.compile(re.escape(word), re.IGNORECASE).sub("*****", en_def)
        raw_sentences = re.findall(r"SENT:\s*(.*)", content)
        return en_def, raw_sentences[:10]
    except: return None, None

# [4] 앱 설정 및 미니멀 디자인 CSS
st.set_page_config(page_title="Haeil's Smart Voca", page_icon="🏎️", layout="centered")

st.markdown("""
    <style>
    /* 퀴즈 컴팩트 레이아웃 */
    .quiz-container { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #ddd; margin-bottom: 5px; }
    .hint-text { font-size: 13px; color: #666; font-style: italic; margin-bottom: 10px; }
    
    /* 단어장 리스트 미니멀 디자인 */
    .word-item { display: flex; align-items: center; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #eee; }
    .word-text { font-size: 15px; font-weight: 600; color: #333; }
    .mean-text { font-size: 14px; color: #666; margin-left: 10px; flex: 1; }
    
    /* 삭제 버튼 극한의 압축 */
    div[data-testid="column"] > div > div > button {
        padding: 0px !important;
        border: none !important;
        background-color: transparent !important;
        font-size: 14px !important;
        color: #ccc !important;
        height: 30px !important;
        width: 30px !important;
    }
    div[data-testid="column"] > div > div > button:hover { color: #ff4b4b !important; }
    </style>
    """, unsafe_allow_html=True)

if 'menu_selection' not in st.session_state: st.session_state.menu_selection = "새 단어 추가"
if 'quiz_state' not in st.session_state: st.session_state.quiz_state = 'setup'

# --- 사이드바 메뉴 (JS 강화) ---
with st.sidebar:
    st.title("🚀 Haeil's Voca")
    st.divider()
    pages = ["새 단어 추가", "단어장 보기", "📊 대시보드", "QUIZ!!"]
    for page in pages:
        is_selected = st.session_state.menu_selection == page
        if st.button(f"{'📍 ' if is_selected else ''}{page}", use_container_width=True, key=f"menu_{page}"):
            st.session_state.menu_selection = page
            st.components.v1.html("""<script>window.parent.document.querySelector('button[aria-label="Close"]').click();</script>""", height=0)
            st.rerun()

menu = st.session_state.menu_selection

# --- 메뉴 1: 새 단어 추가 ---
if menu == "새 단어 추가":
    st.header("➕ 새 단어 등록")
    with st.form("word_add_form", clear_on_submit=True):
        word = st.text_input("영어 단어").strip()
        meaning = st.text_input("뜻").strip()
        if st.form_submit_button("단어 등록"):
            if word and meaning:
                df = load_data()
                if word.lower() in df['word'].astype(str).str.lower().values:
                    st.warning(f"⚠️ 이미 등록된 단어입니다.")
                else:
                    with st.spinner("AI 예문 생성 중..."):
                        en_def, sentences = generate_content(word)
                        if en_def:
                            new_row = {"word": word, "meaning": meaning, "en_def": en_def, "count": 0, "mistakes": 0}
                            for i in range(1, 11): new_row[f"s{i}"] = sentences[i-1]
                            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                            save_data(df)
                            st.success(f"🎉 '{word}' 저장 완료!")

# --- 메뉴 2: 단어장 보기 (미니멀 튜닝 완료) ---
elif menu == "단어장 보기":
    st.header("📚 나의 단어장")
    df = load_data()
    if not df.empty:
        st.caption(f"총 {len(df)}개의 단어가 저장되어 있습니다.")
        st.divider()
        for idx, row in df.iterrows():
            # 컬럼 비율 조정: 단어/뜻에 8.5, 삭제버튼에 1.5 할당
            c1, c2 = st.columns([8.5, 1.5])
            with c1:
                st.markdown(f"<span class='word-text'>{row['word']}</span> <span class='mean-text'>{row['meaning']}</span>", unsafe_allow_html=True)
            with c2:
                if st.button("🗑️", key=f"del_{idx}"):
                    df = df.drop(idx)
                    save_data(df); st.rerun()
            st.markdown("<div style='margin-bottom: -15px;'></div>", unsafe_allow_html=True)
            st.divider()
    else: st.info("등록된 단어가 없습니다.")

# --- 메뉴 3: 📊 대시보드 ---
elif menu == "📊 대시보드":
    st.header("📊 학습 통계")
    df = load_data()
    if not df.empty:
        df['error_rate'] = (df['mistakes'] / df['count'] * 100).fillna(0)
        col1, col2 = st.columns(2)
        col1.metric("총 단어 수", f"{len(df)}개")
        col2.metric("평균 정답률", f"{100 - df['error_rate'].mean():.1f}%")
        st.subheader("🔥 집중 복습 대상 (Top 10)")
        sort_df = df[df['count'] > 0].sort_values(by='error_rate', ascending=False).head(10)
        for _, row in sort_df.iterrows():
            st.warning(f"**{row['word']}**: {row['error_rate']:.0f}% ({row['mistakes']}/{row['count']})")
    else: st.info("데이터가 없습니다.")

# --- 메뉴 4: QUIZ!! (컴팩트 유지) ---
elif menu == "QUIZ!!":
    if st.session_state.quiz_state == 'setup':
        st.header("🧠 QUIZ!!")
        df = load_data()
        if df.empty: st.warning("단어를 먼저 등록해주세요!"); st.stop()
        with st.container(border=True):
            num_q = st.selectbox("문제 수", [5, 10, 20])
            if st.button("🚀 QUIZ START!", use_container_width=True):
                # 8:2 하이브리드 추출 로직
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
        st.markdown(f"<div class='quiz-container'>{masked_sentence}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='hint-text'>💡 {row['en_def']}</div>", unsafe_allow_html=True)
        st.components.v1.html(f"""<script>window.parent.document.querySelectorAll('input[type="text"]')[0].focus();</script>""", height=0)
        with st.form(f"quiz_form_{q_idx}", clear_on_submit=True):
            user_ans = st.text_input("Answer", label_visibility="collapsed", key=f"in_{q_idx}").strip()
            if st.form_submit_button("Submit", use_container_width=True):
                is_correct = user_ans.lower() == word.lower()
                st.session_state.results.append({"word": word, "user_ans": user_ans, "is_correct": is_correct, "raw_sentence": row['selected_sentence']})
                if is_correct: st.success("🎯 Correct!")
                else: st.error(f"❌ Wrong! : {word}")
                time.sleep(1); st.session_state.current_q_idx += 1
                if st.session_state.current_q_idx >= st.session_state.total_q: st.session_state.quiz_state = 'finished'
                st.rerun()
