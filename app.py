# GANTI SELURUH FUNGSI show_scraping_page ANDA DENGAN INI

def show_scraping_page():
    st.title(f"⚙️ Halaman Scraping Data")
    sub_page_options = ["Neraca", "Sosial", "Produksi", "Lainnya"]
    st.session_state.sub_page = st.radio("Pilih Topik Data:", sub_page_options, horizontal=True, key="sub_page_radio")
    st.markdown("---")

    if st.session_state.sub_page in ["Sosial", "Produksi"]:
        icon = "👥" if st.session_state.sub_page == "Sosial" else "🌾"
        st.header(f"{icon} Scraping Berita - {st.session_state.sub_page}")
        st.info(f"Fitur scraping untuk data **{st.session_state.sub_page}** sedang dalam pengembangan.")
        st.balloons()
        return
    
    is_manual = st.session_state.sub_page == "Lainnya"
    if is_manual:
        st.header("📑 Scraping Manual Berdasarkan Kata Kunci")
    else: # Neraca
        st.header(f"📊 Scraping Berita - {st.session_state.sub_page}")

    if not is_manual:
        with st.spinner("Memuat data kategori & sub-kategori..."):
            base_url = "https://docs.google.com/spreadsheets/d/19FRmYvDvjhCGL3vDuOLJF54u7U7hnfic/export?format=xlsx"
            df_kat = load_data_from_url(base_url, sheet_name='Sheet1_Kat')
            df_subkat = load_data_from_url(base_url, sheet_name='Sheet1_SubKat')

        if df_kat is None or df_subkat is None:
            st.error("Gagal memuat data. Pastikan sheet 'Sheet1_Kat' dan 'Sheet1_SubKat' ada di Google Sheet.")
            return
        st.success("✅ Data kategori & sub-kategori berhasil dimuat.")
    
    st.subheader("Atur Parameter Scraping")
    
    tahun_input_str = st.text_input("Masukkan Tahun:", placeholder="Contoh: 2023", max_chars=4, key="tahun_input")
    triwulan_input = st.selectbox("Pilih Triwulan:", ["--Pilih Triwulan--", "Triwulan 1", "Triwulan 2", "Triwulan 3", "Triwulan 4", "Tanggal Custom"])
    start_date_input, end_date_input = None, None
    if triwulan_input == "Tanggal Custom":
        col1, col2 = st.columns(2)
        start_date_input = col1.date_input("Tanggal Awal", date.today() - timedelta(days=30))
        end_date_input = col2.date_input("Tanggal Akhir", date.today())
    
    def validate_year(year_str):
        if not year_str.strip():
            st.warning("Tahun wajib diisi.")
            return None
        if not year_str.isdigit() or len(year_str) != 4:
            st.warning("Harap masukkan 4 digit angka untuk tahun.")
            return None
        year_int = int(year_str)
        if year_int < 2015:
            st.warning(f"Tahun tidak boleh kurang dari 2015.")
            return None
        return year_int

    if is_manual:
        mode_ringkasan = st.radio(
            "Pilih Opsi Ringkasan:",
            ["Dengan Ringkasan (cukup lama)", "Tanpa Ringkasan (lebih cepat)"],
            horizontal=True, key="manual_ringkasan"
        )
        kata_kunci_manual = st.text_input("Masukkan kata kunci:", placeholder="Contoh: Bantuan Pangan")
        is_disabled = (triwulan_input == "--Pilih Triwulan--")
        if st.button("🚀 Mulai Scraping Manual", use_container_width=True, type="primary", disabled=is_disabled):
            tahun_input = validate_year(tahun_input_str)
            if tahun_input is None: return
            
            if not kata_kunci_manual.strip():
                st.warning("Harap isi kata kunci terlebih dahulu."); return
            
            df_proses = pd.DataFrame({kata_kunci_manual: [kata_kunci_manual]})
            st.session_state.start_scraping = True
            st.session_state.scraping_params = {
                'df': df_proses, 'tahun': tahun_input, 'triwulan': triwulan_input, 
                'start_date': start_date_input, 'end_date': end_date_input,
                'mode_ringkasan': mode_ringkasan,
                'start_time_obj': datetime.now()
            }
            st.rerun()

    else: # Neraca
        mode_ringkasan = st.radio(
            "Pilih Opsi Ringkasan:",
            ["Dengan Ringkasan (cukup lama)", "Tanpa Ringkasan (lebih cepat)"],
            horizontal=True, key="kategori_ringkasan"
        )
        mode_pencarian = st.radio("Pilih Mode Pencarian:", ["Kategori", "Sub Kategori"], horizontal=True)
        
        kategori_terpilih = []
        sub_kategori_terpilih = []

        if mode_pencarian == 'Kategori':
            kategori_terpilih = st.multiselect(
                'Pilih Kategori:', 
                df_kat.columns.tolist(),
                max_selections=3,
                help="Anda dapat memilih maksimal 3 kategori.",
                key='kategori_multiselect'
            )
        elif mode_pencarian == 'Sub Kategori':
            sub_kategori_terpilih = st.multiselect(
                'Pilih Sub Kategori:', 
                df_subkat.columns.tolist(),
                max_selections=3,
                help="Anda dapat memilih maksimal 3 sub-kategori.",
                key='sub_kategori_multiselect'
            )

        is_disabled = (
            triwulan_input == "--Pilih Triwulan--" or
            (mode_pencarian == 'Kategori' and not kategori_terpilih) or
            (mode_pencarian == 'Sub Kategori' and not sub_kategori_terpilih)
        )

        if st.button("🚀 Mulai Scraping", use_container_width=True, type="primary", disabled=is_disabled):
            tahun_input = validate_year(tahun_input_str)
            if tahun_input is None: return

            if mode_pencarian == "Kategori":
                df_proses = df_kat[kategori_terpilih]
            else:
                df_proses = df_subkat[sub_kategori_terpilih]

            st.session_state.start_scraping = True
            st.session_state.scraping_params = {
                'df': df_proses, 'tahun': tahun_input, 'triwulan': triwulan_input, 
                'start_date': start_date_input, 'end_date': end_date_input,
                'mode_ringkasan': mode_ringkasan,
                'start_time_obj': datetime.now()
            }
            st.rerun()

    if st.session_state.get('start_scraping'):
        params = st.session_state.scraping_params
        tanggal_awal, tanggal_akhir = get_rentang_tanggal(params['tahun'], params['triwulan'], params['start_date'], params['end_date'])
        
        if tanggal_awal and tanggal_akhir:
            with st.spinner("Memuat data daerah..."):
                df_daerah = load_data_from_url("https://docs.google.com/spreadsheets/d/1Y2SbHlWBWwcxCdAhHiIkdQmcmq--NkGk/export?format=xlsx")
            if df_daerah is not None:
                st.markdown("---")
                
                col_header, col_button = st.columns([3, 1])
                with col_header:
                    st.header("Proses & Hasil Scraping")
                with col_button:
                    st.markdown('<div class="stop-button">', unsafe_allow_html=True)
                    if st.button("🛑 Hentikan Proses", use_container_width=True, key="stop_button"):
                        st.session_state.stop_scraping = True
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                
                status_placeholder = st.empty()
                keyword_placeholder = st.empty()
                table_placeholder = st.empty()

                hasil_df = start_scraping(
                    tanggal_awal, tanggal_akhir, params['df'], df_daerah, time.time(),
                    status_placeholder, keyword_placeholder, table_placeholder,
                    mode_ringkasan=params['mode_ringkasan']
                )
                
                end_time_obj = datetime.now()
                
                status_placeholder.empty()
                keyword_placeholder.empty()
                
                st.session_state.scraping_result = {
                    'df': hasil_df, 
                    'params': params,
                    'start_time': params['start_time_obj'],
                    'end_time': end_time_obj
                }
        
        del st.session_state.start_scraping
        if 'stop_scraping' in st.session_state: 
             del st.session_state.stop_scraping
        st.rerun()

    if st.session_state.get('scraping_result'):
        result = st.session_state.scraping_result
        hasil_df = result['df']
        
        st.markdown("---"); st.header("✅ Proses Selesai")
        
        # --- [PERBAIKAN KODE] ---
        # Cek apakah informasi waktu ada di session_state sebelum menampilkannya
        if 'start_time' in result and 'end_time' in result:
            start_time = result['start_time']
            end_time = result['end_time']
            duration = end_time - start_time
            
            total_seconds = int(duration.total_seconds())
            minutes, seconds = divmod(total_seconds, 60)
            duration_str = f"{minutes} menit {seconds} detik"
            
            st.success(f"Proses scraping berhasil diselesaikan dalam **{duration_str}**.")
            st.markdown("---")
        
        if not hasil_df.empty:
            st.markdown("#### Ringkasan Hasil Ditemukan")
            
            use_summary = (result['params']['mode_ringkasan'] == "Dengan Ringkasan (cukup lama)")
            column_config = {"Link": st.column_config.LinkColumn("Link", width="medium")}
            if use_summary:
                column_config["Ringkasan"] = st.column_config.TextColumn("Ringkasan Penting", width="large")

            st.dataframe(
                hasil_df,
                use_container_width=True,
                height=500, 
                column_config=column_config
            )
            st.caption(f"Total {len(hasil_df)} berita ditemukan.")
            st.write("") 

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_to_excel = hasil_df.copy()
                if not use_summary and "Ringkasan" in df_to_excel.columns:
                    df_to_excel = df_to_excel.drop(columns=["Ringkasan"])
                df_to_excel.to_excel(writer, index=False, sheet_name="Hasil Scraping")

            file_bytes = output.getvalue()
            
            params = result['params']
            now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            topic_str = st.session_state.get('sub_page', 'Data')

            if params['triwulan'] == "Tanggal Custom":
                start_str = params['start_date'].strftime('%Y%m%d')
                end_str = params['end_date'].strftime('%Y%m%d')
                period_str = f"{start_str} s.d {end_str}"
            else:
                period_str = f"{params['triwulan']}_{params['tahun']}"

            kategori_list = params['df'].columns.tolist()
            kategori_str = ",".join(kategori_list)
            kategori_str = re.sub(r'[\\/*?:"<>|]', "", kategori_str)

            filename = f"Hasil_Scraping_{topic_str}_{period_str}_{kategori_str}_{now_str}.xlsx"
            
            st.download_button("📥 Unduh Hasil (Excel)", file_bytes, filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")
            
        else:
            st.warning("Tidak ada berita yang ditemukan sesuai parameter yang dipilih.")
            
        if st.button("🔄 Mulai Scraping Baru (Reset)", use_container_width=True):
            if 'scraping_result' in st.session_state:
                del st.session_state.scraping_result
            st.rerun()
