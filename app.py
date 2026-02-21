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
if "last_num_q" not in st.session_state:
    st.session_state["last_num_q"] = 10
if "last_range_option" not in st.session_state:
    st.session_state["last_range_option"] = "Entire Range"
if "last_range_values" not in st.session_state:
    st.session_state["last_range_values"] = (1, 50)
if "hint_stage" not in st.session_state:
    st.session_state.hint_stage = 0

def load_data(): return conn.read(ttl=0)
def save_data(df): conn.update(data=df)
def mask_phrase(sentence, phrase):
    words = phrase.split()
    masked_sentence = sentence

    for w in words:
        # 단어 변형 허용 (roll → rolls, rolled 등)
        pattern = re.compile(rf"\b{re.escape(w)}\w*\b", re.IGNORECASE)
        masked_sentence = pattern.sub("_____", masked_sentence)

    return masked_sentence


# [2] OpenAI API
api_key = st.secrets.get("OPENAI_API_KEY", "").strip()
client = OpenAI(api_key=api_key)

# 콘텐츠 생성 함수
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

# [3] 모바일 최적화 및 아이폰 15 프로 전용 가로 고정 CSS
st.set_page_config(page_title="Haeil's Voca", layout="centered")

# ✅ 세션 초기화 (무조건 여기)
if "menu" not in st.session_state:
    st.session_state["menu"] = "QUIZ"
if "quiz_state" not in st.session_state:
    st.session_state["quiz_state"] = "setup"
def reset_quiz():
    for key in [
        "quiz_result",
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
    /* 모바일 키보드 대응 */
    @media (max-width: 768px) {
        .mobile-input-container {
            padding-bottom: env(safe-area-inset-bottom);
        }
    }

    
    .mobile-input-container {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background: white;
        padding: 10px;
        border-top: 1px solid #eee;
        z-index: 9999;
    }

    .main .block-container {
        padding-bottom: 120px !important;
    }

    .quiz-input-box input {
        font-size: 18px !important;
        height: 50px !important;
    }
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
if not (st.session_state.menu == "QUIZ" and st.session_state.quiz_state == "playing"):

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
# --- [QUIZ 메뉴: 최종 데이터 고정 버전] ---
if st.session_state.menu == "QUIZ":

    df = load_data()
    total_words = len(df)
    # [1] 데이터 보존을 위한 변수 초기화 (최초 1회만)
    if "final_num" not in st.session_state: st.session_state.final_num = 10
    if "final_option" not in st.session_state: st.session_state.final_option = "Entire Range"
    if "final_range" not in st.session_state: st.session_state.final_range = (total_words-50, total_words)
    # 콜백 함수들: 위젯이 바뀌는 즉시 'final' 변수에 값을 박제함
    def update_num(): st.session_state.final_num = st.session_state.tmp_num
    def update_option(): st.session_state.final_option = st.session_state.tmp_option
    def update_range(): st.session_state.final_range = st.session_state.tmp_range
    
    # [5] START 버튼 (여기서 num_q 등은 final 변수를 참조)
    
    if st.session_state.quiz_state == 'setup':
        # [2] 문제 개수
        st.select_slider(
            "How many words?",
            options=[5, 10, 15, 20, 30, 50],
            value=st.session_state.final_num,
            key="tmp_num",
            on_change=update_num
        )
        # [3] 범위 옵션
        st.radio(
            "What's the range?",
            ["Entire Range", "Custom Range"],
            index=0 if st.session_state.final_option == "Entire Range" else 1,
            horizontal=True,
            key="tmp_option",
            on_change=update_option
        )
        # [4] 상세 범위 (Custom Range일 때만 그리지만, 값은 final_range에서 가져옴)
        if st.session_state.final_option == "Custom Range":
            # 범위 보정
            low, high = st.session_state.final_range
            safe_range = (max(1, min(low, total_words)), max(1, min(high, total_words)))
            
            st.slider(
                "Range Setting",
                1, total_words,
                value=safe_range,
                key="tmp_range",
                on_change=update_range
            )
            start_idx = st.session_state.final_range[0] - 1
            end_idx = st.session_state.final_range[1]
        else:
            start_idx = 0
            end_idx = total_words
        st.subheader("🏁 아 유 레뒤?")
        if st.button("START", use_container_width=True, type="primary"):
            st.session_state.hint_stage = 0

            num_q = st.session_state.final_num
            df_range = df.iloc[start_idx:end_idx].copy()
            # ... 이하 START 로직 동일
            if df_range.empty:
                st.warning("No words in selected range.")
                st.stop()
            # 🔥 숫자형 강제 변환 (안전장치)
            df_range['count'] = pd.to_numeric(df_range['count'], errors='coerce').fillna(0)
            df_range['mistakes'] = pd.to_numeric(df_range['mistakes'], errors='coerce').fillna(0)
            # 🔥 가중치 계산
            df_range['weight'] = (
                (df_range['mistakes'] + 1) ** 1.5 /
                (df_range['count'] + 2)
            )
            # 🔥 가중 랜덤 추출
            pool_df = df_range.sample(
                n=min(num_q, len(df_range)),
                weights='weight',
                replace=False
            )
            pool = pool_df.to_dict('records')
            random.shuffle(pool)
            for item in pool:
                v_sents = [item[f's{i}'] for i in range(1, 11) if pd.notna(item[f's{i}'])]
                item['sel_sent'] = random.choice(v_sents) if v_sents else "No sentence."
            st.session_state.quiz_pool = pool
            st.session_state.full_df = df.copy()
            st.session_state.word_index_map = {
                word: idx for idx, word in enumerate(df['word'])
            }
            st.session_state.temp_score = {
                word: {"count": 0, "mistakes": 0}
                for word in df['word']
            }
            st.session_state.quiz_results = []
            st.session_state.current_idx = 0
            st.session_state.quiz_state = 'playing'
            st.rerun()
    elif st.session_state.quiz_state == 'playing':
        if st.button("🏠 Quit Quiz", use_container_width=True):
            reset_quiz()
            st.session_state.menu = "QUIZ"
            st.rerun()


        if "quiz_pool" not in st.session_state:
            st.session_state.quiz_state = "setup"
            st.rerun()

        q_idx = st.session_state.current_idx
        row = st.session_state.quiz_pool[q_idx]

        st.progress((q_idx + 1) / len(st.session_state.quiz_pool))
        masked = mask_phrase(row['sel_sent'], row['word'])

        st.markdown(
            f"""
            <div class="quiz-card">
                {masked}
            </div>
            """,
            unsafe_allow_html=True
        )



        # =========================
        # 🔥 단계형 힌트 시스템 (form 밖에서만 동작)
        # =========================

        st.markdown(" ")

        # =========================
        # 🔥 단계형 단일 힌트 버튼 시스템
        # =========================

        st.markdown("<div style='margin-top:10px;'>", unsafe_allow_html=True)

        col_hint_btn, col_hint_display = st.columns([1, 5])

        with col_hint_btn:

            if st.session_state.hint_stage == 0:
                if st.button("💡Meaning", key=f"hint_btn_{q_idx}"):
                    st.session_state.hint_stage = 1
                    st.rerun()

            elif st.session_state.hint_stage == 1:
                if st.button("🔤First Letter", key=f"hint_btn_{q_idx}"):

                    first_letter = row['word'].strip()[0]

                    # 입력창 key와 동일하게 맞춰줘야 함
                    st.session_state[f"quiz_input_{q_idx}"] = first_letter

                    st.session_state.hint_stage = 2
                    st.rerun()


            # stage == 2 → 버튼 안 보임


        with col_hint_display:

            if st.session_state.hint_stage >= 1:
                st.markdown(
                     f"""
                    <div style="
                        background:#f8f8f8;
                        color:#333;
                        padding:6px 10px;
                        border-radius:8px;
                        font-size:0.85rem;
                        line-height:1.3;
                        margin-bottom:6px;">
                        {row['en_def']}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            
        st.markdown("</div>", unsafe_allow_html=True)


        # =========================
        # 🔥 하단 고정 입력창 (모바일)
        # =========================
        st.markdown("<div class='mobile-input-container'>", unsafe_allow_html=True)

        with st.form(f"q_{q_idx}", clear_on_submit=True):

            ans = st.text_input(
                "",
                key=f"quiz_input_{q_idx}",
                label_visibility="collapsed",
                placeholder="Type your answer...",
            ).strip()

            submitted = st.form_submit_button("CHECK", use_container_width=True)

            if submitted:

                is_correct = ans.lower() == row['word'].lower()

                st.session_state.quiz_results.append({
                    "sentence": row['sel_sent'],
                    "word": row['word'],
                    "user_answer": ans,
                    "correct": is_correct
                })

                df = st.session_state.full_df
                idx = st.session_state.word_index_map[row['word']]
                df.at[idx, 'count'] = int(df.at[idx, 'count']) + 1

                if not is_correct:
                    df.at[idx, 'mistakes'] = int(df.at[idx, 'mistakes']) + 1

                if is_correct:
                    st.success("Awesome!")
                else:
                    st.error(f"Keep trying! It's '{row['word']}'")

                time.sleep(0.4)

                st.session_state.current_idx += 1
                st.session_state.hint_stage = 0


                if st.session_state.current_idx >= len(st.session_state.quiz_pool):
                    save_data(df)
                    st.session_state.quiz_state = "report"

                st.rerun()


        st.markdown("</div>", unsafe_allow_html=True)

        # =========================
        # 🔥 자동 포커스 + Enter 자동 제출
        # =========================
        st.components.v1.html("""
        <script>
        const parentDoc = window.parent.document;

        function focusLatestInput() {
            const inputs = parentDoc.querySelectorAll('input[type="text"]');
            if (inputs.length > 0) {
                const input = inputs[inputs.length - 1];
                input.focus();

                // 커서를 맨 뒤로 이동
                const val = input.value;
                input.value = '';
                input.value = val;
            }
        }

        function enableEnterSubmitOnce() {
            const inputs = parentDoc.querySelectorAll('input[type="text"]');
            if (inputs.length > 0) {
                const input = inputs[inputs.length - 1];

                if (!input.dataset.enterBound) {
                    input.dataset.enterBound = "true";

                    input.addEventListener("keydown", function(e) {
                        if (e.key === "Enter") {
                            e.preventDefault();
                            const buttons = parentDoc.querySelectorAll('button[kind="primary"]');
                            if (buttons.length > 0) {
                                buttons[buttons.length - 1].click();
                            }
                        }
                    });
                }
            }
        }

        // 모바일 키보드 대응 (viewport 재조정)
        function adjustForKeyboard() {
            window.scrollTo(0, document.body.scrollHeight);
        }

        setTimeout(focusLatestInput, 200);
        setTimeout(enableEnterSubmitOnce, 300);
        setTimeout(adjustForKeyboard, 400);

        </script>
        """, height=0)


    
    elif st.session_state.quiz_state == "report":
        st.subheader("📋 Quiz Report")
        results = st.session_state.quiz_results
        total = len(results)
        correct_cnt = sum(1 for r in results if r["correct"])
        st.markdown(f"## 🎯 Score: {correct_cnt} / {total}")
        st.divider()
        for i, r in enumerate(results, 1):
            with st.container():
                st.markdown(f"### Q{i}")
                # 빈칸 처리
                masked = mask_phrase(r["sentence"], r["word"])

                st.markdown(f"**Sentence:** {masked}")
                st.markdown(f"**Correct Word:** {r['word']}")
                if r["correct"]:
                    st.success("✅ Correct")
                else:
                    st.error("❌ Wrong")
                    st.markdown(f"Your Answer: `{r['user_answer']}`")
                st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🏠 Home", use_container_width=True):
                reset_quiz()
                st.rerun()
        with col2:
            if st.button("🔄 Retry", use_container_width=True):
                st.session_state.quiz_state = "setup"
                st.rerun()

# --- [Voca 메뉴: 군더더기 없는 순정 한 줄 레이아웃] ---
elif st.session_state.menu == "Voca":
    st.subheader("📚 Word Bank")
    df = load_data()

    
    if df.empty:
        st.info("저장된 단어가 없습니다.")
    else:
        search_term = st.text_input("🔍 Search", "").strip().lower()
        df['no'] = range(1, len(df) + 1)
        
        filtered_df = df[df['word'].str.lower().str.contains(search_term, na=False) | 
                         df['meaning'].str.lower().str.contains(search_term, na=False)] if search_term else df

        for idx, row in filtered_df.iloc[::-1].iterrows():

            with st.expander(f"#{row['no']}  **{row['word']}** : {row['meaning']}"):

                confirm_key = f"del_confirm_{idx}"
                if confirm_key not in st.session_state:
                    st.session_state[confirm_key] = False

                # ===============================
                # 🔥 English Meaning 추가
                # ===============================
                if pd.notna(row.get("en_def", "")):
                    st.markdown(
                        f"""
                        <div style="
                            margin-top:6px;
                            padding:10px;
                            background:#f8f8f8;
                            border-radius:10px;
                            font-size:0.9rem;
                            color:#333;">
                            <strong>📘 English Meaning</strong><br>
                            {row['en_def']}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                # ===============================
                # 🔥 예문 (highlight 제거)
                # ===============================
                st.markdown(
                    f"""
                    <div style="margin-top: 10px; border-top: 1px solid #eee; padding-top: 10px;">
                        <p style="font-size: 0.75rem; color: #888; margin-bottom: 6px;">📖 Examples</p>
                        <p style="font-size: 0.9rem;">1. {row['s1'] if pd.notna(row['s1']) else ''}</p>
                        <p style="font-size: 0.9rem;">2. {row['s2'] if pd.notna(row['s2']) else ''}</p>
                        <p style="font-size: 0.9rem;">3. {row['s3'] if pd.notna(row['s3']) else ''}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                st.markdown("---")

                # ===============================
                # 2️⃣ 하단 버튼 영역
                # ===============================
                def generate_tts_audio(word):
                    try:
                        response = client.audio.speech.create(
                            model="gpt-4o-mini-tts",
                            voice="alloy",
                            input=word
                        )

                        audio_path = f"/tmp/{word}.mp3"

                        with open(audio_path, "wb") as f:
                            f.write(response.read())

                        return audio_path

                    except Exception as e:
                        print("TTS error:", e)
                        return None

                if not st.session_state[confirm_key]:

                    col1, col2 = st.columns(2)

                    speak_clicked = col1.button(
                        "🔊 Pronounce",
                        key=f"v_spk_{idx}",
                        use_container_width=True
                    )

                    delete_clicked = col2.button(
                        "🗑️ Delete",
                        key=f"v_del_{idx}",
                        use_container_width=True
                    )

                    # 🔊 발음
                    if speak_clicked:

                        # 1️⃣ OpenAI TTS 먼저 시도
                        audio_file = generate_tts_audio(row['word'])

                        if audio_file:
                            st.audio(audio_file)

                        # 2️⃣ 실패 시 JS fallback
                        else:
                            safe_word = row['word'].replace("'", "\\'")

                            st.components.v1.html(
                                f"""
                                <script>
                                    const synth = window.speechSynthesis;

                                    function speak() {{
                                        synth.cancel();

                                        const utter = new SpeechSynthesisUtterance('{safe_word}');
                                        utter.lang = "en-US";
                                        utter.rate = 0.95;
                                        utter.pitch = 1.0;

                                        function loadVoicesAndSpeak() {{
                                            const voices = synth.getVoices();
                                            const usVoice = voices.find(v => v.lang === "en-US");
                                            if (usVoice) {{
                                                utter.voice = usVoice;
                                            }}
                                            synth.speak(utter);
                                        }}

                                        if (synth.getVoices().length === 0) {{
                                            synth.onvoiceschanged = loadVoicesAndSpeak;
                                        }} else {{
                                            loadVoicesAndSpeak();
                                        }}
                                    }}

                                    speak();
                                </script>
                                """,
                                height=0
                            )

                    # 🗑 삭제 클릭
                    if delete_clicked:
                        st.session_state[confirm_key] = True
                        st.rerun()

                # ===============================
                # 3️⃣ 삭제 확인 UI
                # ===============================
                else:
                    st.warning(f"Delete '{row['word']}'?")

                    c1, c2 = st.columns(2)

                    if c1.button("✅ Yes", key=f"y_confirm_{idx}", use_container_width=True):
                        new_df = df.drop(idx).drop(columns=['no'])
                        save_data(new_df)
                        st.session_state[confirm_key] = False
                        st.rerun()

                    if c2.button("❌ No", key=f"n_cancel_{idx}", use_container_width=True):
                        st.session_state[confirm_key] = False
                        st.rerun()





# --- [Stat 메뉴] 대시보드 (정수형) ---
elif st.session_state.menu == "Stat":
    st.subheader("📊 Your Progress")
    df = load_data()

    if not df.empty:
        # 데이터 타입 강제 변환
        df['count'] = pd.to_numeric(df['count'], errors='coerce').fillna(0).astype(int)
        df['mistakes'] = pd.to_numeric(df['mistakes'], errors='coerce').fillna(0).astype(int)

        total_count = int(df['count'].sum())
        total_mistakes = int(df['mistakes'].sum())

        col1, col2 = st.columns(2)
        col1.metric("총 단어 수", f"{len(df)}개")

        # 전체 정답률 계산
        if total_count > 0:
            correct_rate = int(((total_count - total_mistakes) / total_count) * 100)
        else:
            correct_rate = 100

        col2.metric("전체 정답률", f"{correct_rate}%")

        st.subheader("🔥 정답률 낮은 단어 (Top 20)")

        # 🔥 단어별 정답률 계산
        df['accuracy'] = (
            ((df['count'] - df['mistakes']) / df['count'].replace(0, 1)) * 100
        ).fillna(0)

        # count가 0인 단어 제외
        filtered = df[df['count'] > 0].copy()

        # 🔥 정렬 조건
        filtered = filtered.sort_values(
            by=['accuracy', 'mistakes'],
            ascending=[True, False]
        ).head(20)

        if not filtered.empty:
            display_df = filtered[['word', 'meaning', 'accuracy']].copy()
            display_df['accuracy'] = display_df['accuracy'].round(1).astype(str) + "%"

            st.table(display_df)
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
            
