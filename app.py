if st.button("START", use_container_width=True, type="primary"):

    df_range = df.iloc[start_idx:end_idx].copy()

    if df_range.empty:
        st.warning("No words in selected range.")
        st.stop()

    # 8:2 하이브리드 로직 (범위 적용)
    incorrect = df_range[df_range['mistakes'] > 0]

    pool = list(
        incorrect.sample(
            n=min(len(incorrect), int(num_q * 0.2))
        ).to_dict('records')
    )

    remaining = df_range[
        ~df_range['word'].isin([x['word'] for x in pool])
    ]

    pool.extend(
        remaining.sample(
            n=min(len(remaining), num_q - len(pool))
        ).to_dict('records')
    )

    random.shuffle(pool)
