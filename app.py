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

# [3] 콘텐츠 생성 함수
def generate_content(word):
    prompt = f"""Provide an English definition and 10 high-quality, distinct example sentences for the word '{word}'.
    RULES: 1. The word '{word}' MUST be included in EVERY sentence. 2. Each sentence must represent a different context. 3. The definition (DEF:) should NOT contain the word '{word}'.
    Format: DEF: [definition] SENT: [sentence containing {word}] (total 10 SENT lines)"""
    try:
        for attempt in range(3):
            response = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role": "system", "content": "You are a precise English lexicographer."},
                          {"role": "user", "content": prompt}],
                temperature=0.4
            )
            content = response.choices[0].message.content
            if not content: continue
            en_def_match = re.search(r"DEF:\s*(.*)", content)
            en_def = en_def_match.group(1).strip() if en_def_match else ""
            en_def = re.compile(re.escape(word), re.IGNORECASE).sub("*****", en_def)
            raw_sentences = re.findall(r"SENT:\s*(.*)", content)
            valid_sentences = [s.strip().replace('"', '') for s in raw_sentences if re.search(re.escape(word), s, re.IGNORECASE)]
            if len(valid_sentences) >= 10: return en_def, valid_sentences[:10]
            time.sleep(0.5)
        while len(valid_sentences) < 10: valid_sentences.append(f"It is essential to maintain {word} in any challenging situation.")
        return en_def, valid_sentences[:10]
    except Exception as e:
        st.error(f"🚨 GPT 오류: {e}")
    return None, None

# [4] 앱 설정 및 스타일 (모바일 최적화 CSS 추가)
st.set_page_config(page_title="Haeil's Smart Voca", page_icon="🏎️", layout="wide")

st.markdown("""
    <style>
    /* 단어장 리스트 여백 축소 */
    .word-row { font-size: 14px; border-bottom: 1px solid #eee; padding: 5px 0; }
    /* 모바일에서 버튼 크기 조정 */
    .stButton button { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

if 'menu_selection' not in st.session_state: st.session_state.menu_selection = "새 단어 추가"
if 'quiz_state' not in st.session_state: st.session_state.quiz_state = 'setup'

# --- 사이드바 메뉴 (자동 접힘 JS 추가) ---
with st.sidebar:
    st.title("🚀 Haeil's Voca")
    st.divider()
    pages = ["새 단어 추가", "단어장 보기", "QUIZ!!"]
    for page in pages:
        label = f"**[ {page} ]**" if st.session_state.menu_selection == page else page
        if st.button(label, use_container_width=True, key=f"menu_{page}"):
            st.session_state.menu_selection = page
            # [JS] 모바일에서 메뉴 클릭 시 사이드바를 자동으로 닫는 마법
            st.components.v1.html("""
                <script>
                var nextButton = window.parent.document.querySelector('button[kind="headerNoPadding"]');
                if (nextButton) nextButton.click();
                </script>
                """, height=0)
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

# --- 메뉴 2: 단어장 보기 (모바일 최적화 한 줄 보기) ---
elif menu == "단어장 보기":
    st.header("📚 나의 단어장")
    df = load_data()
    if not df.empty:
        if st.button("🧹 정답률 초기화"):
            df['count'] = 0; df['mistakes'] = 0
            save_data(df); st.rerun()
        
        st.divider()
        # [모바일 최적화] HTML 테이블 형식으로 한 줄 표시
        for idx, row in df.iterrows():
            total = int(row['count'])
            rate = ((total - int(row['mistakes'])) / total * 100) if total > 0 else 0
            
            col_text, col_del = st.columns([6, 1])
            with col_text:
                # 테이블 태그를 이용해 간격 유지 및 한 줄 표시
                st.markdown(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eee; padding: 8px 0;">
                    <div style="flex: 1; font-weight: bold;">{idx+1}. {row['word']}</div>
                    <div style="flex: 1.5; font-size: 14px; color: #666;">{row['meaning']}</div>
                    <div style="flex: 0.8; text-align: right; font-size: 13px; color: #007bff;">{rate:.0f}%</div>
                </div>
                """, unsafe_allow_html=True)
            with col_del:
                if st.button("🗑️", key=f"del_{idx}"):
                    df = df.drop(idx)
                    save_data(df); st.rerun()
    else: st.info("등록된 단어가 없습니다.")

# --- 메뉴 3: QUIZ!! ---
elif menu == "QUIZ!!":
    st.header("🧠 QUIZ!!")
    
    if st.session_state.quiz_state == 'setup':
        df = load_data()
        if df.empty: st.warning("단어를 먼저 등록해주세요!"); st.stop()

        with st.container(border=True):
            st.subheader("🏁 QUIZ SETTING")
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
                if 'synced' in st.session_state: del st.session_state.synced
                st.rerun()

    elif st.session_state.quiz_state == 'playing':
        q_idx = st.session_state.current_q_idx
        row = st.session_state.quiz_pool[q_idx]
        word, raw_sentence = str(row['word']), row['selected_sentence']
        
        # 포커스 JS
        st.components.v1.html(f"""<script>
            var f = () => {{ var i = window.parent.document.querySelectorAll('input[type="text"]'); if(i.length>0) i[i.length-1].focus(); }};
            setTimeout(f, 300);
        </script>""", height=0)

        st.progress((q_idx) / st.session_state.total_q)
        masked_sentence = re.compile(re.escape(word), re.IGNORECASE).sub("( ______ )", raw_sentence)

        st.markdown(f"""<div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 1px solid #ddd; margin-bottom: 10px; text-align: center; font-size: 18px;">{masked_sentence}</div>""", unsafe_allow_html=True)
        with st.expander("💡 Hint", expanded=True):
            st.write(row['en_def'])

        with st.form(f"quiz_form_{q_idx}", clear_on_submit=True):
            user_ans = st.text_input("정답 입력", label_visibility="collapsed", key=f"in_{q_idx}").strip()
            if st.form_submit_button("제출 (Enter)", use_container_width=True):
                is_correct = user_ans.lower() == word.lower()
                # [수정] 사용자가 입력한 오답(user_ans)을 결과에 추가 저장
                st.session_state.results.append({
                    "word": word, 
                    "user_ans": user_ans, 
                    "is_correct": is_correct, 
                    "raw_sentence": raw_sentence
                })
                
                if is_correct: st.success("🎯 정답!")
                else: st.error(f"❌ 오답! 정답은: {word}")
                
                time.sleep(1)
                st.session_state.current_q_idx += 1
                if st.session_state.current_q_idx >= st.session_state.total_q: st.session_state.quiz_state = 'finished'
                st.rerun()

    elif st.session_state.quiz_state == 'finished':
        st.header("🏆 QUIZ REPORT")
        
        if 'synced' not in st.session_state:
            with st.spinner("데이터 동기화 중..."):
                df = load_data()
                for res in st.session_state.results:
                    idx = df[df['word'] == res['word']].index
                    if not idx.empty:
                        df.loc[idx, 'count'] += 1
                        if not res['is_correct']: df.loc[idx, 'mistakes'] += 1
                save_data(df)
                st.session_state.synced = True

        for res in st.session_state.results:
            with st.container(border=True):
                icon = "⭕" if res['is_correct'] else "❌"
                st.markdown(f"### {icon} {res['word']}")
                # [수정] 오답일 경우 내가 쓴 답 표시
                if not res['is_correct']:
                    st.markdown(f"<span style='color:red;'>Your Answer: {res['user_ans']}</span>", unsafe_allow_html=True)
                
                bold_sent = re.compile(re.escape(res['word']), re.IGNORECASE).sub(f"**{res['word']}**", res['raw_sentence'])
                st.write(f"Context: {bold_sent}")
        
        if st.button("🏠 다시 시작하기"): st.session_state.quiz_state = 'setup'; st.rerun()