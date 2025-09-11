import streamlit as st
import pandas as pd
import time
import io
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from pygooglenews import GoogleNews
from urllib.parse import urlparse
import re

# --- Impor untuk integrasi Google Sheets ---
import gspread
from google.oauth2.service_account import Credentials

# --- Impor untuk Selenium ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- Konfigurasi Halaman Streamlit ---
st.set_page_config(
    page_title="SKENA",
    page_icon="logo skena.png",
    layout="wide"
)

# --- TEMA WARNA & GAYA ---
custom_css = """
<style>
    .block-container { padding-top: 2rem; }
    h1, h2, h3, h4, h5 { } 
    div[data-testid="stButton"] > button[kind="primary"],
    div[data-testid="stForm"] > form > div > button {
        background-color: #0073C4;
        color: white;
        border: none;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover,
    div[data-testid="stForm"] > form > div > button:hover {
        background-color: #005A9E;
        color: white;
    }

    .stAlert { border-radius: 5px; }
    .stAlert[data-baseweb="notification"][data-testid*="info"] { border-left: 5px solid #0073C4; }
    .stAlert[data-baseweb="notification"][data-testid*="success"] { border-left: 5px solid #65B32E; }
    .stAlert[data-baseweb="notification"][data-testid*="warning"] { border-left: 5px solid #F17822; }

    .stop-button button {
        background-color: #D9534F;
        color: white;
        border: 1px solid #D43F3A;
    }
    .stop-button button:hover {
        background-color: #C9302C;
        color: white;
        border: 1px solid #AC2925;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)


# --- FUNGSI-FUNGSI PENDUKUNG ---
@st.cache_data
def load_data_from_url(url, sheet_name=0):
    try:
        url_no_cache = f"{url}&t={int(time.time())}"
        df = pd.read_excel(url_no_cache, sheet_name=sheet_name)
        return df
    except Exception as e:
        st.error(f"Gagal memuat data dari URL (Sheet: {sheet_name}): {e}")
        return None

@st.cache_resource
def get_selenium_driver():
    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    driver = webdriver.Chrome(options=options)
    return driver

@st.cache_resource
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scope
    )
    client = gspread.authorize(creds)
    return client

def save_saran_to_sheet(nama, saran):
    try:
        client = get_gspread_client()
        sheet = client.open("Saran dan Masukan SKENA - Streamlit").sheet1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_row = [timestamp, nama, saran]
        sheet.append_row(new_row)
        return True
    except Exception as e:
        st.error(f"Terjadi kesalahan saat menyimpan saran: {e}")
        return False

def get_rentang_tanggal(tahun: int, triwulan: str, start_date=None, end_date=None):
    if triwulan == "Tanggal Custom":
        if start_date and end_date:
            return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
        return None, None
    triwulan_map = {
        "Triwulan 1": (f"{tahun}-01-01", f"{tahun}-03-31"),
        "Triwulan 2": (f"{tahun}-04-01", f"{tahun}-06-30"),
        "Triwulan 3": (f"{tahun}-07-01", f"{tahun}-09-30"),
        "Triwulan 4": (f"{tahun}-10-01", f"{tahun}-12-31"),
    }
    return triwulan_map.get(triwulan, (None, None))

def ekstrak_info_artikel(driver, link_google, keyword):
    try:
        driver.get(link_google)
        time.sleep(2)
        url_final = driver.current_url

        if "google.com/url" in url_final or "consent.google.com" in url_final:
            return None, "", ""

        parsed_uri = urlparse(url_final)
        sumber_dari_url = parsed_uri.netloc.replace('www.', '')

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        teks_artikel = " ".join(p.get_text(strip=True) for p in soup.find_all('p'))
        if not teks_artikel:
            return url_final, "", sumber_dari_url

        kalimat_list = re.split(r'(?<=[.!?])\s+', teks_artikel)
        ringkasan = ""

        for kalimat in kalimat_list:
            if keyword.lower() in kalimat.lower():
                ringkasan = kalimat.strip()
                break 

        if not ringkasan and kalimat_list:
            ringkasan = kalimat_list[0].strip()

        return url_final, ringkasan, sumber_dari_url

    except Exception:
        return None, "", ""

def start_scraping(tanggal_awal, tanggal_akhir, kata_kunci_lapus_df, kata_kunci_daerah_df, start_time, status_placeholder, keyword_placeholder, table_placeholder, mode_ringkasan):
    use_summary = (mode_ringkasan == "Dengan Ringkasan (cukup lama)")
    
    driver = get_selenium_driver() if use_summary else None
    
    kata_kunci_lapus_dict = {c: kata_kunci_lapus_df[c].dropna().astype(str).str.strip().tolist() for c in kata_kunci_lapus_df.columns}
    nama_daerah = "Konawe Selatan"
    kecamatan_list = kata_kunci_daerah_df[nama_daerah].dropna().astype(str).str.strip().tolist()
    lokasi_filter = [nama_daerah.lower()] + [kec.lower() for kec in kecamatan_list]
    gn = GoogleNews(lang='id', country='ID')
    
    kolom_tabel = ["Nomor", "Kategori", "Kata Kunci", "Judul", "Link", "Tanggal", "Sumber"]
    if use_summary:
        kolom_tabel.append("Ringkasan")

    semua_hasil = []
    df_live = pd.DataFrame(columns=kolom_tabel)
    total_kategori = len(kata_kunci_lapus_dict)
    
    scraping_stopped = False
    for kategori_ke, (kategori, kata_kunci_list) in enumerate(kata_kunci_lapus_dict.items(), 1):
        for keyword_raw in kata_kunci_list:
            if st.session_state.get('stop_scraping', False):
                status_placeholder.warning("Proses dihentikan oleh pengguna.")
                scraping_stopped = True
                break
            
            elapsed_time = time.time() - start_time
            menit, detik = divmod(int(elapsed_time), 60)
            status_placeholder.info(f"⏳ Proses Berjalan: {menit}m {detik}d | 📁 Kategori {kategori_ke}/{total_kategori}: {kategori}")
            
            if pd.isna(keyword_raw): continue
            keyword = str(keyword_raw).strip()
            if not keyword: continue
            
            keyword_placeholder.text(f"  ➡️ 🔍 Mencari: '{keyword}' di '{nama_daerah}'")
            search_query = f'"{keyword}" "{nama_daerah}"'
            
            try:
                search_results = gn.search(search_query, from_=tanggal_awal, to_=tanggal_akhir)
                for entry in search_results['entries']:
                    
                    if use_summary:
                        link_final, ringkasan, sumber_dari_url = ekstrak_info_artikel(driver, entry.link, keyword)
                    else:
                        link_final = entry.link
                        ringkasan = ""
                        sumber_dari_url = entry.source.title if entry.source else ""

                    if not link_final or any(d['Link'] == link_final for d in semua_hasil): continue
                    
                    judul_asli = entry.title
                    judul_bersih, sumber_final = judul_asli, sumber_dari_url
                    if ' - ' in judul_asli:
                        parts = judul_asli.rsplit(' - ', 1)
                        if len(parts) == 2 and parts[1].strip():
                            judul_bersih, sumber_final = parts[0].strip(), parts[1].strip()

                    judul_lower = judul_bersih.lower()
                    lokasi_ditemukan = any(loc in judul_lower for loc in lokasi_filter)
                    keyword_ditemukan = keyword.lower() in judul_lower

                    if lokasi_ditemukan or keyword_ditemukan:
                        try:
                            tanggal_dt = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z')
                            tanggal_str = tanggal_dt.strftime('%d-%m-%Y')
                        except (ValueError, TypeError): tanggal_str = "N/A"
                        
                        new_data = {
                            "Nomor": len(semua_hasil) + 1, "Kategori": kategori, "Kata Kunci": keyword, 
                            "Judul": judul_bersih, "Link": link_final, "Tanggal": tanggal_str, 
                            "Sumber": sumber_final
                        }
                        if use_summary:
                            new_data["Ringkasan"] = ringkasan
                        
                        semua_hasil.append(new_data)
                        new_row_df = pd.DataFrame([new_data], columns=kolom_tabel)
                        df_live = pd.concat([df_live, new_row_df], ignore_index=True)

                        with table_placeholder.container():
                            st.markdown("### Hasil Scraping (Live)")
                            column_config = {"Link": st.column_config.LinkColumn("Link", width="medium")}
                            if use_summary:
                                column_config["Ringkasan"] = st.column_config.TextColumn("Ringkasan Penting", width="large")
                            
                            st.dataframe(
                                df_live, use_container_width=True, height=500,
                                column_config=column_config
                            )
                            st.caption(f"Total berita ditemukan: {len(df_live)}")

            except Exception as e:
                st.warning(f"Gagal mencari '{keyword}': {e}")
                continue
        
        if scraping_stopped:
            break

    return pd.DataFrame(semua_hasil)

# --- HALAMAN-HALAMAN APLIKASI ---
def show_home_page():
    with st.container():
        col1, col2, col3 = st.columns([1,3,1])
        with col2:
            st.image("logo skena full.png", use_container_width=True)
    st.markdown("---")
    st.markdown("""<div style="text-align: center;"><p>Halo! Sistem ini merupakan alat bantu BPS Kab. Konawe Selatan untuk pengumpulan data.</p><p><em>Sebelum mengakses fitur utama, sangat disarankan untuk membaca bagian <strong>Panduan</strong> terlebih dahulu.</em></p></div>""", unsafe_allow_html=True)
    if not st.session_state.get('logged_in', False):
        st.info("Silakan **Login** melalui sidebar untuk menggunakan menu Scraping dan Dokumentasi.")
    st.header("Pilih Kategori Data")
    is_disabled = not st.session_state.get('logged_in', False)
    col1, col2, col3, col4 = st.columns(4, gap="large")
    with col1:
        st.subheader("📈 Neraca")
        st.write("Data mengenai neraca perdagangan, PDB, inflasi, dan ekonomi lainnya.")
        if st.button("Pilih Neraca", use_container_width=True, disabled=is_disabled): 
            st.session_state.page = "Scraping"
            st.session_state.sub_page = "Neraca"
            st.rerun()
    with col2:
        st.subheader("🌾 Produksi")
        st.write("Informasi seputar produksi tanaman pangan, perkebunan, dan pertanian.")
        if st.button("Pilih Produksi", use_container_width=True, disabled=is_disabled): 
            st.session_state.page = "Scraping"
            st.session_state.sub_page = "Produksi"
            st.rerun()
    with col3:
        st.subheader("👥 Sosial")
        st.write("Data terkait demografi, kemiskinan, pendidikan, dan kesehatan.")
        if st.button("Pilih Sosial", use_container_width=True, disabled=is_disabled): 
            st.session_state.page = "Scraping"
            st.session_state.sub_page = "Sosial"
            st.rerun()
    with col4:
        st.subheader("📰 Lainnya")
        st.write("Informasi seputar lainnya dapat dicari bagian ini.")
        if st.button("Pilih Lainnya", use_container_width=True, disabled=is_disabled): 
            st.session_state.page = "Scraping"
            st.session_state.sub_page = "Lainnya"
            st.rerun()

def show_panduan_page():
    st.title("📖 Panduan Pengguna")
    st.markdown("---")
    st.markdown("Selamat datang di **SKENA (Sistem Scraping Fenomena Konawe Selatan)**.\n\nAplikasi ini dirancang untuk membantu dalam pengumpulan data berita online yang relevan dengan Kabupaten Konawe Selatan. Dengan memanfaatkan teknologi web scraping, SKENA dapat secara otomatis mencari, mengumpulkan, dan menyajikan data dari berbagai sumber berita di internet.")
    if not st.session_state.get('logged_in', False):
        st.markdown("Silakan **Login** melalui sidebar untuk mengakses fitur utama.")

def show_documentation_page():
    st.title("🗂️ Dokumentasi")
    folder_id = "1z1_w_FyFmNB7ExfVzFVc3jH5InWmQSvZ"
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
    st.link_button("Buka Folder di Google Drive", folder_url, use_container_width=True, type="primary")
    st.markdown("---")
    st.subheader("Pratinjau Isi Folder")
    embed_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}"
    st.components.v1.html(f'<iframe src="{embed_url}" width="100%" height="600" style="border:1px solid #ddd; border-radius: 8px;"></iframe>', height=620)

def show_saran_page():
    st.title("✍️ Kotak Saran")
    st.markdown("---")
    st.info("Punya ide untuk pengembangan atau menemukan bug? Beri tahu kami di sini!")
    with st.form("saran_form"):
        nama = st.text_input("Nama Anda", placeholder="Masukkan nama lengkap Anda")
        saran = st.text_area("Saran atau Masukan", placeholder="Tuliskan saran, ide, atau laporan bug Anda di sini...", height=200)
        submitted = st.form_submit_button("🚀 Kirim Saran", use_container_width=True, type="primary")
        if submitted:
            nama_valid = len(nama.strip()) > 5
            saran_valid = len(saran.strip()) > 0
            if nama_valid and saran_valid:
                if save_saran_to_sheet(nama, saran):
                    st.success(f"Terima kasih, {nama}! Saran Anda telah kami terima.")
                    st.balloons()
            else:
                if not nama_valid: st.warning("Nama wajib diisi dan harus lebih dari 5 karakter.")
                if not saran_valid: st.warning("Kolom saran tidak boleh kosong.")

def show_scraping_page():
    st.title(f"⚙️ Halaman Scraping Data")
    
    # Konten utama akan menyesuaikan berdasarkan st.session_state.sub_page
    # yang dikontrol oleh tombol-tombol di sidebar.
    
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
                'mode_ringkasan': mode_ringkasan
            }
            st.rerun()

    else: # Neraca, Sosial, Produksi
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
                'mode_ringkasan': mode_ringkasan
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
                
                status_placeholder.empty()
                keyword_placeholder.empty()
                
                st.session_state.scraping_result = {'df': hasil_df, 'params': params}
        
        del st.session_state.start_scraping
        if 'stop_scraping' in st.session_state: 
            del st.session_state.stop_scraping
        st.rerun()

    if st.session_state.get('scraping_result'):
        st.markdown("---"); st.header("✅ Proses Selesai")
        result = st.session_state.scraping_result
        hasil_df = result['df']
        
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


# --- NAVIGASI DAN LOGIKA UTAMA ---
if "page" not in st.session_state: st.session_state.page = "Home"
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "sub_page" not in st.session_state: st.session_state.sub_page = "Neraca"

with st.sidebar:
    st.image("logo bps konsel.png")
    if not st.session_state.logged_in:
        with st.form("login_form"):
            st.header("Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True, type="primary"):
                if username == "user7405" and password == "bps7405":
                    st.session_state.logged_in = True
                    st.session_state.page = "Home"
                    st.rerun()
                else:
                    st.warning("Username atau password salah.")
    else:
        st.success(f"Selamat datang, **user7405**!")
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.page = "Home"
            st.rerun()

    st.markdown("---")
    st.header("Menu Navigasi")
    if st.button("🏠 Home", use_container_width=True): 
        st.session_state.page = "Home"
        st.rerun()
    if st.button("📖 Panduan", use_container_width=True): 
        st.session_state.page = "Panduan"
        st.rerun()
    if st.session_state.logged_in:
        if st.button("⚙️ Scraping", use_container_width=True): 
            st.session_state.page = "Scraping"
            st.rerun()
        if st.button("🗂️ Dokumentasi", use_container_width=True): 
            st.session_state.page = "Dokumentasi"
            st.rerun()
        if st.button("✍️ Saran", use_container_width=True): 
            st.session_state.page = "Saran"
            st.rerun()

    # --- [MODIFIKASI] Logika tombol sidebar diubah total ---
    if st.session_state.page == "Scraping":
        st.markdown("---")
        st.header("Pilih Topik Data")

        # Daftar semua topik dengan label, ikon, dan nama state
        scraping_topics = {
            "Neraca": "📊 Neraca",
            "Sosial": "👥 Sosial",
            "Produksi": "🌾 Produksi",
            "Lainnya": "📰 Lainnya"
        }

        # Loop untuk membuat setiap tombol
        for topic_name, topic_label in scraping_topics.items():
            # Tentukan tipe tombol: 'primary' (biru) jika aktif, 'secondary' (abu-abu) jika tidak
            is_active = (st.session_state.sub_page == topic_name)
            button_type = "primary" if is_active else "secondary"
            
            # Buat tombol. Jika diklik, update state dan rerun
            if st.button(topic_label, use_container_width=True, type=button_type):
                st.session_state.sub_page = topic_name
                st.rerun()


page_functions = {"Home": show_home_page, "Panduan": show_panduan_page, "Scraping": show_scraping_page, "Dokumentasi": show_documentation_page, "Saran": show_saran_page}
if st.session_state.page in page_functions and (st.session_state.page in ["Home", "Panduan"] or st.session_state.logged_in):
    page_functions[st.session_state.page]()
else:
    st.session_state.page = "Home"
    st.rerun()
