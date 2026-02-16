import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
import random
import re
import time
from openai import OpenAI

# [1] 시스템 설정 (CSV 관련 초기화 코드 삭제)
os.environ["PYTHONIOENCODING"] = "utf-8"

# [2] Google Sheets 연결 설정 (DB_FILE 대체)
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # 실시간으로 구글 시트 데이터를 읽어옵니다.
    return conn.read(ttl=0)

def save_data(df):
    # 변경된 데이터프레임을 구글 시트에 즉시 반영합니다.
    conn.update(data=df)

# [3] OpenAI API 클라이언트 설정
try:
    api_key = st.secrets.get("OPENAI_API_KEY", "").strip()
    client = OpenAI(api_key=api_key)
except Exception as e:
    st.error(f"OpenAI API 설정 오류: {e}")

# [4] 콘텐츠 생성 함수 (로직 동일)
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

# [5] 앱 설정
st.set_page_config(page_title="Haeil's Smart Voca (SaaS)", page_icon="🏎️", layout="wide")

if 'menu_selection' not in st.session_state: st.session_state.menu_selection = "새 단어 추가"
if 'quiz_state' not in st.session_state: st.session_state.quiz_state = 'setup'

# --- 사이드바 메뉴 ---
with st.sidebar:
    st.title("🚀 Haeil's Voca")
    st.divider()
    pages = ["새 단어 추가", "단어장 보기", "QUIZ!!"]
    for page in pages:
        label = f"**[ {page} ]**" if st.session_state.menu_selection == page else page
        if st.button(label, use_container_width=True, key=f"menu_{page}"):
            st.session_state.menu_selection = page
            st.rerun()
    st.divider()
    st.caption("v1.5 | SaaS Cloud Ready")

menu = st.session_state.menu_selection

# --- 메뉴 1: 새 단어 추가 ---
if menu == "새 단어 추가":
    st.header("➕ 새 단어 등록 (Cloud)")
    with st.form("word_add_form", clear_on_submit=True):
        word = st.text_input("영어 단어").strip()
        meaning = st.text_input("뜻").strip()
        if st.form_submit_button("단어 등록"):
            if word and meaning:
                df = load_data()
                if word.lower() in df['word'].astype(str).str.lower().values:
                    st.warning(f"⚠️ '{word}'는 이미 등록되어 있습니다.")
                else:
                    with st.spinner(f"AI가 고품질 예문을 생성 중..."):
                        en_def, sentences = generate_content(word)
                        if en_def:
                            new_row = {"word": word, "meaning": meaning, "en_def": en_def, "count": 0, "mistakes": 0}
                            for i in range(1, 11): new_row[f"s{i}"] = sentences[i-1]
                            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                            save_data(df) # 구글 시트에 저장
                            st.success(f"🎉 '{word}' 클라우드 저장 완료!")

# --- 메뉴 2: 단어장 보기 ---
elif menu == "단어장 보기":
    st.header("📚 클라우드 단어 List")
    df = load_data()
    if not df.empty:
        col_info, col_reset = st.columns([3, 1])
        with col_reset:
            if st.button("🧹 정답률 초기화", use_container_width=True):
                df['count'] = 0; df['mistakes'] = 0
                save_data(df); st.rerun()
        
        st.divider()
        for idx, row in df.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.5, 2.5, 1.5, 0.5])
                total = row['count']
                rate = ((total - row['mistakes']) / total * 100) if total > 0 else 0
                c1.markdown(f"**{idx+1}. {row['word']}**")
                c2.markdown(f"{row['meaning']}")
                c3.markdown(f"📈 {int(total)}회 / 정답률 {rate:.0f}%")
                if c4.button("🗑️", key=f"del_{idx}"):
                    df = df.drop(idx)
                    save_data(df); st.rerun()
    else: st.info("등록된 단어가 없습니다.")

# --- 메뉴 3: QUIZ!! ---
# --- 메뉴 3: QUIZ!! (최적화 버전) ---
elif menu == "QUIZ!!":
    st.header("🧠 QUIZ!!")
    
    # [변경] 초기 진입 시에만 데이터를 불러오도록 setup 안에서만 호출합니다.
    if st.session_state.quiz_state == 'setup':
        df = load_data() # 여기서만 로딩바가 뜹니다.
        
        if df.empty: 
            st.warning("단어를 먼저 등록해주세요!")
            st.stop()

        with st.container(border=True):
            st.subheader("🏁 QUIZ SETTING")
            range_option = st.radio("출제 범위 선택", ["전체 리스트", "직접 범위 선택"], horizontal=True)
            
            if range_option == "직접 범위 선택":
                col1, col2 = st.columns(2)
                start_idx = col1.number_input("시작 번호", 1, len(df), 1)
                end_idx = col2.number_input("끝 번호", start_idx, len(df), len(df))
                quiz_pool_df = df.iloc[start_idx-1:end_idx].copy()
            else: 
                quiz_pool_df = df.copy()

            max_val = len(quiz_pool_df)
            num_q_option = st.selectbox("문제 수", [5, 10, 20, "직접 입력"])
            total_q = min(int(num_q_option if num_q_option != "직접 입력" else st.number_input(f"문제 수 (최대 {max_val})", 1, max_val, min(5, max_val))), max_val)

            if st.button("🚀 QUIZ START!", use_container_width=True):
                # 알고리즘 8:2 규칙 적용
                incorrect_pool = quiz_pool_df[quiz_pool_df['mistakes'] > 0]
                new_pool = quiz_pool_df[quiz_pool_df['mistakes'] == 0]
                
                num_incorrect = min(len(incorrect_pool), int(total_q * 0.2))
                num_new = total_q - num_incorrect
                
                final_list = []
                if num_incorrect > 0:
                    final_list.extend(incorrect_pool.sample(n=num_incorrect).to_dict('records'))
                
                if num_new > 0:
                    if len(new_pool) >= num_new:
                        final_list.extend(new_pool.sample(n=num_new).to_dict('records'))
                    else:
                        final_list.extend(quiz_pool_df.sample(n=num_new).to_dict('records'))
                
                random.shuffle(final_list)
                for item in final_list:
                    v_sents = [item[f's{i}'] for i in range(1, 11) if pd.notna(item[f's{i}'])]
                    item['selected_sentence'] = random.choice(v_sents)
                
                # 세션에 퀴즈 정보 저장
                st.session_state.quiz_pool = final_list[:total_q]
                st.session_state.total_q = len(st.session_state.quiz_pool)
                st.session_state.current_q_idx = 0
                st.session_state.results = []
                st.session_state.quiz_state = 'playing'
                # 퀴즈 종료 시 시트 업데이트를 위해 synced 상태 초기화
                if 'synced' in st.session_state: del st.session_state.synced 
                st.rerun()

    # [중요] playing 상태에서는 load_data()를 호출하지 않습니다!
    elif st.session_state.quiz_state == 'playing':
        q_idx = st.session_state.current_q_idx
        row = st.session_state.quiz_pool[q_idx]
        word, raw_sentence = str(row['word']), row['selected_sentence']
        
        # 자동 포커스 JS
        random_id = random.randint(1, 1000000)
        st.components.v1.html(f"""
            <div id="focus_id_{random_id}" style="display:none;"></div>
            <script>
                (function() {{
                    const focusInput = () => {{
                        const inputs = window.parent.document.querySelectorAll('input[type="text"]');
                        if (inputs.length > 0) {{ inputs[inputs.length - 1].focus(); }}
                    }};
                    setTimeout(focusInput, 150);
                    setTimeout(focusInput, 300);
                }})();
            </script>
        """, height=1)

        st.progress((q_idx) / st.session_state.total_q)
        st.markdown(f"##### 📝 다음 예문의 ( )에 알맞은 단어를 입력하세요.", unsafe_allow_html=True)
        masked_sentence = re.compile(re.escape(word), re.IGNORECASE).sub("( ______ )", raw_sentence)

        st.markdown(f"""<div style="background-color: #ffffff; padding: 25px 30px; border-radius: 12px; border: 1px solid #e1e4e8; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 15px; text-align: center; line-height: 1.5; font-size: 20px; color: #2c3e50; font-weight: 500;">{masked_sentence}</div>""", unsafe_allow_html=True)
        
        with st.expander("💡 Hint", expanded=True):
            st.markdown(f"<p style='color: #555;'>{row['en_def']}</p>", unsafe_allow_html=True)

        with st.form(f"quiz_form_{q_idx}", clear_on_submit=True):
            user_ans = st.text_input("정답 입력", placeholder="바로 입력하세요!", label_visibility="collapsed", key=f"input_field_{q_idx}").strip()
            if st.form_submit_button("제출하기 (Enter)", use_container_width=True):
                is_correct = user_ans.lower() == word.lower()
                st.session_state.results.append({
                    "word": word, 
                    "is_correct": is_correct, 
                    "raw_sentence": raw_sentence
                })
                
                if is_correct: st.success("🎯 정답입니다!")
                else: st.error(f"❌ 오답입니다. 정답: {word}")
                
                time.sleep(1.0)
                st.session_state.current_q_idx += 1
                if st.session_state.current_q_idx >= st.session_state.total_q:
                    st.session_state.quiz_state = 'finished'
                st.rerun()

        if st.button("🏠 퀴즈 중단"):
            st.session_state.quiz_state = 'setup'
            st.rerun()

    elif st.session_state.quiz_state == 'finished':
        st.header("🏆 QUIZ REPORT")
        
        # [일괄 저장] 리포트 진입 시 단 한 번만 로드 및 저장
        if 'synced' not in st.session_state:
            with st.spinner("최종 결과를 클라우드에 동기화 중..."):
                df = load_data() # 여기서 한 번만 "Running"이 뜹니다.
                for res in st.session_state.results:
                    word = res['word']
                    is_correct = res['is_correct']
                    idx = df[df['word'] == word].index
                    if not idx.empty:
                        df.loc[idx, 'count'] += 1
                        if not is_correct:
                            df.loc[idx, 'mistakes'] += 1
                save_data(df)
                st.session_state.synced = True

        for res in st.session_state.results:
            with st.container(border=True):
                icon = "⭕" if res['is_correct'] else "❌"
                bold_sent = re.compile(re.escape(res['word']), re.IGNORECASE).sub(f"**{res['word']}**", res['raw_sentence'])
                st.markdown(f"{icon} **{res['word']}**\n\n{bold_sent}")
        
        if st.button("🏠 다시 시작하기", use_container_width=True):
            st.session_state.quiz_state = 'setup'
            st.rerun()