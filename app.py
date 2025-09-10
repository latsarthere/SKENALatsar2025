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
    page_icon="logo skena.png", # Pastikan file ini ada di folder yang sama
    layout="wide"
)

# --- TEMA WARNA & GAYA ---
custom_css = """
<style>
    .block-container { padding-top: 2rem; }
    h1, h2, h3, h4, h5 { color: #0073C4; }
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
    [data-testid="stSidebar"] { background-color: #f8f9fa; }
    .stAlert { border-radius: 5px; }
    .stAlert[data-baseweb="notification"][data-testid*="info"] { border-left: 5px solid #0073C4; }
    .stAlert[data-baseweb="notification"][data-testid*="success"] { border-left: 5px solid #65B32E; }
    .stAlert[data-baseweb="notification"][data-testid*="warning"] { border-left: 5px solid #F17822; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# --- FUNGSI-FUNGSI PENDUKUNG ---

@st.cache_data
def load_data_from_url(url, sheet_name=0):
    try:
        df = pd.read_excel(url, sheet_name=sheet_name)
        return df
    except Exception as e:
        st.error(f"Gagal memuat data dari URL: {e}")
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

# --- Fungsi untuk Koneksi ke Google Sheets ---
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
        # Buka spreadsheet berdasarkan nama yang sudah diperbarui
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

def ekstrak_info_artikel(driver, link_google):
    try:
        driver.get(link_google)
        time.sleep(2)
        url_final = driver.current_url
        if "google.com/url" in url_final or "consent.google.com" in url_final:
            return None, "", ""
        parsed_uri = urlparse(url_final)
        sumber_dari_url = parsed_uri.netloc.replace('www.', '')
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        ringkasan_meta = ""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        og_desc = soup.find('meta', attrs={'property': 'og:description'})
        if og_desc and og_desc.get('content'):
            ringkasan_meta = og_desc['content']
        elif meta_desc and meta_desc.get('content'):
            ringkasan_meta = meta_desc['content']

        kalimat_fenomena = ""
        paragraphs = soup.find_all('p', limit=5)
        text_content = " ".join([p.get_text(strip=True) for p in paragraphs])
        keywords_regex = r"(karena|penyebab|akibat|dampak|memicu|meningkat|menurun|naik|turun)"
        sentences = re.split(r'(?<=[.!?])\s+', text_content)
        kalimat_penting = [s for s in sentences if re.search(keywords_regex, s, re.IGNORECASE)]
        if kalimat_penting:
            kalimat_fenomena = " ".join(kalimat_penting[:2])

        ringkasan_final = f"{kalimat_fenomena} {ringkasan_meta}".strip()
        if not ringkasan_final and paragraphs:
            ringkasan_final = paragraphs[0].get_text(strip=True)
            
        return url_final, ringkasan_final, sumber_dari_url
    except Exception:
        return None, "", ""

def start_scraping(tanggal_awal, tanggal_akhir, kata_kunci_lapus_df, kata_kunci_daerah_df, start_time, table_placeholder, keyword_placeholder):
    driver = get_selenium_driver()
    kata_kunci_lapus_dict = {c: kata_kunci_lapus_df[c].dropna().astype(str).str.strip().tolist() for c in kata_kunci_lapus_df.columns}
    nama_daerah = "Konawe Selatan"
    kecamatan_list = kata_kunci_daerah_df[nama_daerah].dropna().astype(str).str.strip().tolist()
    lokasi_filter = [nama_daerah.lower()] + [kec.lower() for kec in kecamatan_list]
    status_placeholder = st.empty()
    gn = GoogleNews(lang='id', country='ID')
    semua_hasil = []
    total_kategori = len(kata_kunci_lapus_dict)
    
    for kategori_ke, (kategori, kata_kunci_list) in enumerate(kata_kunci_lapus_dict.items(), 1):
        for keyword_raw in kata_kunci_list:
            elapsed_time = time.time() - start_time
            status_placeholder.info(f"⏳ Proses... ({int(elapsed_time // 60)}m {int(elapsed_time % 60)}d) | 📁 Kategori {kategori_ke}/{total_kategori}: {kategori}")
            if pd.isna(keyword_raw): continue
            keyword = str(keyword_raw).strip()
            if not keyword: continue
            keyword_placeholder.text(f"  ➡️ 🔍 Mencari: '{keyword}' di '{nama_daerah}'")
            search_query = f'"{keyword}" "{nama_daerah}"'
            try:
                search_results = gn.search(search_query, from_=tanggal_awal, to_=tanggal_akhir)
                for entry in search_results['entries']:
                    link_final, ringkasan, sumber_dari_url = ekstrak_info_artikel(driver, entry.link)
                    if not link_final or any(d['Link'] == link_final for d in semua_hasil): continue
                    judul_asli = entry.title
                    sumber_final = ""
                    judul_bersih = judul_asli
                    if ' - ' in judul_asli:
                        parts = judul_asli.rsplit(' - ', 1)
                        if len(parts) == 2 and parts[1].strip():
                            judul_bersih, sumber_final = parts[0].strip(), parts[1].strip()
                        else: sumber_final = sumber_dari_url
                    else: sumber_final = sumber_dari_url
                    judul_lower, ringkasan_lower, keyword_lower = judul_bersih.lower(), ringkasan.lower(), keyword.lower()
                    lokasi_ditemukan = any(loc in judul_lower or loc in ringkasan_lower for loc in lokasi_filter)
                    keyword_ditemukan = keyword_lower in judul_lower or keyword_lower in ringkasan_lower
                    if lokasi_ditemukan or keyword_ditemukan:
                        try:
                            tanggal_dt = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z')
                            tanggal_str = tanggal_dt.strftime('%d-%m-%Y')
                        except (ValueError, TypeError): tanggal_str = "N/A"
                        semua_hasil.append({"Nomor": len(semua_hasil) + 1, "Kategori": kategori, "Kata Kunci": keyword, "Judul": judul_bersih, "Link": link_final, "Tanggal": tanggal_str, "Sumber": sumber_final, "Ringkasan": ringkasan})
            except Exception: continue

    if semua_hasil:
        df_live = pd.DataFrame(semua_hasil)[["Nomor", "Kategori", "Kata Kunci", "Judul", "Link", "Tanggal", "Sumber", "Ringkasan"]]
        with table_placeholder.container():
            st.markdown("### Hasil Scraping Terkini")
            st.dataframe(df_live, use_container_width=True, height=400, column_config={"Judul": st.column_config.TextColumn(width="large"), "Link": st.column_config.LinkColumn("Link Berita", help="Klik untuk membuka tautan berita di tab baru.", width="medium"), "Sumber": st.column_config.TextColumn("Sumber Berita", width="small"), "Ringkasan": st.column_config.TextColumn(width="large")})
            st.caption(f"Total berita ditemukan: {len(df_live)}")

    status_placeholder.empty()
    keyword_placeholder.empty()
    return pd.DataFrame(semua_hasil) if semua_hasil else pd.DataFrame()

# --- HALAMAN-HALAMAN APLIKASI ---
def show_home_page():
    st.image("logo skena full.png", width=200)
    st.markdown("---")
    st.markdown("Halo! Sistem ini merupakan alat bantu BPS Kab. Konawe Selatan untuk pengumpulan data.\n\n_Sebelum mengakses fitur utama, sangat disarankan untuk membaca bagian **Panduan** terlebih dahulu._")
    if not st.session_state.get('logged_in', False):
        st.info("Silakan **Login** melalui sidebar untuk menggunakan menu Scraping dan Dokumentasi.")
    st.header("Pilih Kategori Data")
    col1, col2, col3, col4 = st.columns(4, gap="large")
    is_disabled = not st.session_state.get('logged_in', False)
    with col1:
        st.subheader("👥 Sosial")
        if st.button("Pilih Sosial", use_container_width=True, disabled=is_disabled): st.session_state.page, st.session_state.sub_page = "Scraping", "Sosial"; st.rerun()
    with col2:
        st.subheader("📈 Neraca")
        if st.button("Pilih Neraca", use_container_width=True, disabled=is_disabled): st.session_state.page, st.session_state.sub_page = "Scraping", "Neraca"; st.rerun()
    with col3:
        st.subheader("🌾 Produksi")
        if st.button("Pilih Produksi", use_container_width=True, disabled=is_disabled): st.session_state.page, st.session_state.sub_page = "Scraping", "Produksi"; st.rerun()
    with col4:
        st.subheader("📰 Lainnya")
        if st.button("Pilih Lainnya", use_container_width=True, disabled=is_disabled): st.session_state.page, st.session_state.sub_page = "Scraping", "Lainnya"; st.rerun()

def show_panduan_page():
    st.title("📖 Panduan Pengguna")
    st.markdown("---")
    st.markdown("Selamat datang di **SKENA (Sistem Scraping Fenomena Konawe Selatan)**.\n\nAplikasi ini dirancang untuk membantu dalam pengumpulan data berita online yang relevan dengan Kabupaten Konawe Selatan. Dengan memanfaatkan teknologi web scraping, SKENA dapat secara otomatis mencari, mengumpulkan, dan menyajikan data dari berbagai sumber berita di internet.")
    if not st.session_state.get('logged_in', False):
        st.markdown("Silakan **Login** melalui sidebar untuk mengakses fitur utama.")

def show_documentation_page():
    st.title("🗂️ Dokumentasi")
    folder_url = "https://drive.google.com/drive/folders/1z1_w_FyFmNB7ExfVzFVc3jH5InWmQSvZ"
    st.link_button("Buka Folder Dokumentasi di Google Drive", folder_url, use_container_width=True, type="primary")

def show_saran_page():
    st.title("✍️ Kotak Saran")
    st.markdown("---")
    st.info("Punya ide untuk pengembangan atau menemukan bug? Beri tahu kami di sini!")
    with st.form("saran_form"):
        nama = st.text_input("Nama Anda", placeholder="Masukkan nama lengkap Anda")
        saran = st.text_area("Saran atau Masukan", placeholder="Tuliskan saran, ide, atau laporan bug Anda di sini...", height=200)
        
        submitted = st.form_submit_button("🚀 Kirim Saran", use_container_width=True, type="primary")

        if submitted:
            # Validasi input
            nama_valid = len(nama.strip()) > 5
            saran_valid = len(saran.strip()) > 0

            if nama_valid and saran_valid:
                if save_saran_to_sheet(nama, saran):
                    st.success(f"Terima kasih, {nama}! Saran Anda telah kami terima.")
                    st.balloons()
            else:
                # Menampilkan pesan error yang spesifik
                if not nama_valid:
                    st.warning("Nama wajib diisi dan harus lebih dari 5 karakter.")
                if not saran_valid:
                    st.warning("Kolom saran tidak boleh kosong.")

def show_scraping_page():
    st.title(f"⚙️ Halaman Scraping Data")
    sub_page_options = ["Neraca", "Sosial", "Produksi", "Lainnya"]
    st.session_state.sub_page = st.radio("Pilih Kategori Data:", sub_page_options, horizontal=True, key="sub_page_radio")
    st.markdown("---")

    if st.session_state.sub_page in ["Sosial", "Produksi"]:
        st.header(f" Scraping Berita Kategori - {st.session_state.sub_page}")
        st.info(f"Fitur scraping untuk data **{st.session_state.sub_page}** sedang dalam pengembangan.")
        st.balloons()
        return

    elif st.session_state.sub_page == "Lainnya":
        st.header("📑 Scraping Manual Berdasarkan Kata Kunci")
        tahun_sekarang = date.today().year
        tahun_input = st.selectbox("Pilih Tahun:", ["--Pilih Tahun--"] + list(range(2020, tahun_sekarang + 1)))
        triwulan_input = st.selectbox("Pilih Triwulan:", ["--Pilih Triwulan--", "Triwulan 1", "Triwulan 2", "Triwulan 3", "Triwulan 4", "Tanggal Custom"])
        if triwulan_input == "Tanggal Custom":
            col1, col2 = st.columns(2)
            start_date_input = col1.date_input("Tanggal Awal", date.today() - timedelta(days=30))
            end_date_input = col2.date_input("Tanggal Akhir", date.today())
        kata_kunci_manual = st.text_input("Masukkan kata kunci:", placeholder="Contoh: Bantuan Pangan")
        
        if st.button("🚀 Mulai Scraping Manual", use_container_width=True, type="primary", disabled=(tahun_input == "--Pilih Tahun--" or triwulan_input == "--Pilih Triwulan--")):
            if not kata_kunci_manual.strip():
                st.warning("Harap isi kata kunci terlebih dahulu."); return
            tanggal_awal, tanggal_akhir = get_rentang_tanggal(int(tahun_input), triwulan_input, locals().get('start_date_input'), locals().get('end_date_input'))
            if tanggal_awal and tanggal_akhir:
                # ... Lanjutan logika scraping ...
                st.session_state.scraping_result = None
                with st.spinner("Memuat data pendukung..."):
                    df_daerah = load_data_from_url("https://docs.google.com/spreadsheets/d/1Y2SbHlWBWwcxCdAhHiIkdQmcmq--NkGk/export?format=xlsx")
                if df_daerah is not None:
                    hasil_df = start_scraping(tanggal_awal, tanggal_akhir, pd.DataFrame({"Lainnya": [kata_kunci_manual]}), df_daerah, time.time(), st.empty(), st.empty())
                    st.session_state.scraping_result = {'df': hasil_df, 'triwulan': triwulan_input, 'tahun': int(tahun_input)}

    elif st.session_state.sub_page == "Neraca":
        st.header(f"📊 Scraping Berita Kategori - {st.session_state.sub_page}")
        with st.spinner("Memuat data kata kunci..."):
            df_lapus = load_data_from_url("https://docs.google.com/spreadsheets/d/19FRmYvDvjhCGL3vDuOLJF54u7U7hnfic/export?format=xlsx", 'Sheet1')
            df_daerah = load_data_from_url("https://docs.google.com/spreadsheets/d/1Y2SbHlWBWwcxCdAhHiIkdQmcmq--NkGk/export?format=xlsx")
        if df_lapus is None or df_daerah is None: st.error("Gagal memuat data kata kunci."); return
        st.success("✅ Data kata kunci berhasil dimuat.")
        
        st.subheader("Atur Parameter Scraping")
        tahun_sekarang = date.today().year
        tahun_input = st.selectbox("Pilih Tahun:", ["--Pilih Tahun--"] + list(range(2020, tahun_sekarang + 1)))
        triwulan_input = st.selectbox("Pilih Triwulan:", ["--Pilih Triwulan--", "Triwulan 1", "Triwulan 2", "Triwulan 3", "Triwulan 4", "Tanggal Custom"])
        if triwulan_input == "Tanggal Custom":
            col1, col2 = st.columns(2)
            start_date_input = col1.date_input("Tanggal Awal", date.today() - timedelta(days=30))
            end_date_input = col2.date_input("Tanggal Akhir", date.today())
        mode_kategori = st.radio("Pilih Opsi Kategori:", ["Semua Kategori", "Pilih Kategori Tertentu"], horizontal=True)
        kategori_terpilih = st.multiselect('Pilih sub-kategori:', df_lapus.columns.tolist()) if mode_kategori == 'Pilih Kategori Tertentu' else []
        
        if st.button("🚀 Mulai Scraping Kategori", use_container_width=True, type="primary", disabled=(tahun_input == "--Pilih Tahun--" or triwulan_input == "--Pilih Triwulan--" or (mode_kategori == 'Pilih Kategori Tertentu' and not kategori_terpilih))):
            tanggal_awal, tanggal_akhir = get_rentang_tanggal(int(tahun_input), triwulan_input, locals().get('start_date_input'), locals().get('end_date_input'))
            if tanggal_awal and tanggal_akhir:
                st.session_state.scraping_result = None
                df_proses = df_lapus[kategori_terpilih] if kategori_terpilih else df_lapus
                hasil_df = start_scraping(tanggal_awal, tanggal_akhir, df_proses, df_daerah, time.time(), st.empty(), st.empty())
                st.session_state.scraping_result = {'df': hasil_df, 'triwulan': triwulan_input, 'tahun': int(tahun_input)}

    if 'scraping_result' in st.session_state and st.session_state.scraping_result is not None:
        st.markdown("---")
        st.header("✅ Proses Selesai")
        hasil_df = st.session_state.scraping_result['df']
        if not hasil_df.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                hasil_df.to_excel(writer, index=False, sheet_name="Hasil Scraping")
            now = datetime.now()
            if st.session_state.scraping_result['triwulan'] != "Tanggal Custom":
                filename = f"Hasil_Scraping_{st.session_state.sub_page}_{st.session_state.scraping_result['triwulan']}_{st.session_state.scraping_result['tahun']}_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
            else:
                filename = f"Hasil_Scraping_{st.session_state.sub_page}_Custom_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
            st.download_button("📥 Unduh Hasil Scraping (Excel)", output.getvalue(), filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        else:
            st.warning("Tidak ada berita yang ditemukan sesuai parameter yang dipilih.")
        if st.button("🔄 Mulai Scraping Baru (Reset)", use_container_width=True):
            st.session_state.scraping_result = None; st.rerun()

# --- NAVIGASI DAN LOGIKA UTAMA ---
if "page" not in st.session_state: st.session_state.page = "Home"
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "sub_page" not in st.session_state: st.session_state.sub_page = "Neraca"

with st.sidebar:
    st.image("logo bps konsel.png") # Pastikan file ini ada di folder yang sama
    if not st.session_state.logged_in:
        with st.form("login_form"):
            st.header("Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True, type="primary"):
                if username == "user7405" and password == "bps7405":
                    st.session_state.logged_in = True; st.session_state.page = "Home"; st.rerun()
                else:
                    st.warning("Username atau password salah.")
    else:
        st.success(f"Selamat datang, **user7405**!")
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False; st.session_state.page = "Home"; st.rerun()
    st.markdown("---")
    st.header("Menu Navigasi")
    if st.button("🏠 Home", use_container_width=True): st.session_state.page = "Home"; st.rerun()
    if st.button("📖 Panduan", use_container_width=True): st.session_state.page = "Panduan"; st.rerun()
    if st.session_state.logged_in:
        if st.button("⚙️ Scraping", use_container_width=True): st.session_state.page = "Scraping"; st.rerun()
        if st.button("🗂️ Dokumentasi", use_container_width=True): st.session_state.page = "Dokumentasi"; st.rerun()
        if st.button("✍️ Saran", use_container_width=True): st.session_state.page = "Saran"; st.rerun()

# --- Logika Tampilan Halaman ---
page_functions = {"Home": show_home_page, "Panduan": show_panduan_page, "Scraping": show_scraping_page, "Dokumentasi": show_documentation_page, "Saran": show_saran_page}
if st.session_state.page in page_functions and (st.session_state.page in ["Home", "Panduan"] or st.session_state.logged_in):
    page_functions[st.session_state.page]()
else:
    st.session_state.page = "Home"; st.rerun()

