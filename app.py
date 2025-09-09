import streamlit as st
import pandas as pd
import time
import io
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from pygooglenews import GoogleNews
import google.generativeai as genai
from newspaper import Article # <-- IMPORT BARU

# --- Konfigurasi API Key Gemini ---
# Kode ini akan secara otomatis membaca dari file .streamlit/secrets.toml Anda
try:
    API_KEYS = [
        st.secrets["gemini_api_key_1"]
    ]
    current_key_idx = 0
except (KeyError, FileNotFoundError):
    st.error("File secrets.toml atau API key di dalamnya tidak ditemukan. Harap periksa kembali.")
    API_KEYS = [] # Atur ke list kosong jika tidak ada key
    current_key_idx = 0


# --- FUNGSI-FUNGSI BARU & YANG DIPERBARUI ---

def get_rotating_model():
    """Mengambil model Gemini dengan rotasi API key."""
    global current_key_idx
    if not API_KEYS:
        st.error("Tidak ada Gemini API Key yang dikonfigurasi.")
        return None
    
    key = API_KEYS[current_key_idx]
    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
    
    try:
        genai.configure(api_key=key)
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        st.warning(f"Gagal mengkonfigurasi API Key: {e}")
        return None

def ringkas_dengan_gemini(text: str, wilayah: str, usaha: str) -> str:
    """Membuat ringkasan relevan menggunakan Gemini AI."""
    model = get_rotating_model()
    if not model or not text.strip() or "Gagal mengambil konten" in text or "Konten artikel kosong" in text:
        return "TIDAK RELEVAN"

    prompt = (
        f"Buat paragraf ringkas dan padu dalam 2 kalimat dengan maksimal 40 kata. "
        f"Paragraf harus fokus pada topik '{usaha}' di wilayah '{wilayah}'. "
        f"Jika teks yang diberikan TIDAK membahas topik '{usaha}' di '{wilayah}' atau tidak mengandung fenomena ekonomi yang relevan (seperti kenaikan/penurunan) terkait topik tersebut, tulis HANYA 'TIDAK RELEVAN'.\n\n"
        f"Teks untuk dianalisis:\n---\n{text}\n---"
    )
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"[Gagal meringkas: {e}]"

def get_article_text_with_newspaper(link):
    """
    Mengambil teks konten utama dari link berita menggunakan newspaper3k.
    Fungsi ini lebih andal dalam menangani redirect dan struktur web yang beragam.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        article = Article(link, config={'headers': headers}, request_timeout=15)
        article.download()
        article.parse()
        return article.text[:4000] if article.text else "Konten artikel kosong atau tidak dapat di-parse."
    except Exception:
        return "Gagal mengambil konten artikel."

# --- Konfigurasi Halaman & Tampilan (CSS) ---
st.set_page_config(
    page_title="SKENA",
    page_icon="logo skena.png",
    layout="wide"
)

custom_css = """
<style>
    .block-container { padding-top: 2rem; }
    h1, h2, h3, h4, h5 { color: #0073C4; }
    div[data-testid="stButton"] > button[kind="primary"],
    div[data-testid="stForm"] > form > div > button {
        background-color: #0073C4; color: white; border: none;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover,
    div[data-testid="stForm"] > form > div > button:hover {
        background-color: #005A9E; color: white;
    }
    [data-testid="stSidebar"] { background-color: #f8f9fa; }
    .stAlert { border-radius: 5px; }
    .stAlert[data-baseweb="notification"][data-testid*="info"] { border-left: 5px solid #0073C4; }
    .stAlert[data-baseweb="notification"][data-testid*="success"] { border-left: 5px solid #65B32E; }
    .stAlert[data-baseweb="notification"][data-testid*="warning"] { border-left: 5px solid #F17822; }
    .text-center { text-align: center; }
    .text-justify { text-align: justify; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)


# --- FUNGSI-FUNGSI PENDUKUNG LAINNYA ---
@st.cache_data
def load_data_from_url(url, sheet_name=0):
    try:
        df = pd.read_excel(url, sheet_name=sheet_name)
        return df
    except Exception as e:
        st.error(f"Gagal memuat data dari URL: {e}")
        return None

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


# --- FUNGSI UTAMA SCRAPING ---
def start_scraping(tanggal_awal, tanggal_akhir, kata_kunci_lapus_df, kata_kunci_daerah_df, start_time, table_placeholder, keyword_placeholder):
    kata_kunci_lapus_dict = {c: kata_kunci_lapus_df[c].dropna().astype(str).str.strip().tolist() for c in kata_kunci_lapus_df.columns}
    nama_daerah = "Konawe Selatan"
    
    status_placeholder = st.empty()
    gn = GoogleNews(lang='id', country='ID')
    
    if 'hasil_scraping' not in st.session_state:
        st.session_state.hasil_scraping = []
    
    for kategori, kata_kunci_list in kata_kunci_lapus_dict.items():
        for keyword_raw in kata_kunci_list:
            elapsed_time = time.time() - start_time
            status_placeholder.info(f"⏳ Memproses: {kategori} | Waktu: {int(elapsed_time // 60)}m {int(elapsed_time % 60)}d")
            
            if pd.isna(keyword_raw): continue
            keyword = str(keyword_raw).strip()
            if not keyword: continue
            
            keyword_placeholder.text(f"  ➡️ 🔍 Mencari: '{keyword}'")
            
            search_query = f'"{keyword}" "{nama_daerah}"'
            try:
                search_results = gn.search(search_query, from_=tanggal_awal, to_=tanggal_akhir)
                for entry in search_results['entries']:
                    link = entry.link
                    if any(d['Link'] == link for d in st.session_state.hasil_scraping): continue

                    judul = entry.title
                    
                    # Mengambil teks artikel dengan newspaper3k
                    article_text = get_article_text_with_newspaper(link)
                    
                    # Meringkas teks dengan Gemini
                    ringkasan_ai = ringkas_dengan_gemini(article_text, nama_daerah, keyword)

                    if ringkasan_ai != "TIDAK RELEVAN":
                        try:
                            tanggal_dt = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z')
                            tanggal_str = tanggal_dt.strftime('%d-%m-%Y')
                        except (ValueError, TypeError):
                            tanggal_str = "N/A"
                        
                        st.session_state.hasil_scraping.append({
                            "Nomor": len(st.session_state.hasil_scraping) + 1,
                            "Kategori": kategori,
                            "Kata Kunci": keyword, "Judul": judul,
                            "Link": link, "Tanggal": tanggal_str, "Ringkasan AI": ringkasan_ai
                        })
            except Exception as e:
                st.warning(f"Error saat mencari '{keyword}': {e}")
                continue

        if st.session_state.hasil_scraping:
            df_live = pd.DataFrame(st.session_state.hasil_scraping)
            kolom_urut = ["Nomor", "Kategori", "Kata Kunci", "Judul", "Link", "Tanggal", "Ringkasan AI"]
            df_live = df_live[kolom_urut]
            with table_placeholder.container():
                st.markdown("### Hasil Scraping Terkini")
                st.dataframe(df_live, width=None, height=400) # Menggunakan width=None untuk auto-width
                st.caption(f"Total berita ditemukan: {len(df_live)}")

    status_placeholder.empty()
    keyword_placeholder.empty()
    
    if st.session_state.hasil_scraping:
        return pd.DataFrame(st.session_state.hasil_scraping)
    else:
        return pd.DataFrame()


# --- HALAMAN-HALAMAN APLIKASI ---
def set_page(page_name):
    st.session_state.page = page_name

def show_home_page():
    st.image("logo skena full.png", width=None)
    st.markdown("---")
    
    st.markdown("""
    <div class='text-justify'>
        Hallo! Sistem Scraping Konawe Selatan (SKENA) merupakan alat bantu BPS Kabupaten Konawe Selatan dalam menyediakan data statistik yang lengkap. 
        Sistem ini melakukan pencarian (<i>scraping</i>) fenomena pendukung dalam bentuk berita di Google.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class='text-justify' style='margin-top: 10px;'>
        Sebelum mengakses fitur utama, sangat disarankan untuk membaca bagian <b>Pendahuluan</b> terlebih dahulu.
    </div>
    """, unsafe_allow_html=True)
    
    if not st.session_state.get('logged_in', False):
        st.markdown("<div class='text-justify' style='margin-top: 1rem;'>", unsafe_allow_html=True)
        st.info("Silakan Login melalui sidebar untuk menggunakan menu Scraping dan Dokumentasi.")
        st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<h2 class='text-center' style='margin-top: 2rem;'>Pilih Kategori Data</h2>", unsafe_allow_html=True)
    
    col1_btn, col2_btn, col3_btn, col4_btn = st.columns(4, gap="large")
    is_disabled = not st.session_state.get('logged_in', False)
    
    with col1_btn:
        st.subheader("📈 Neraca")
        if st.button("Pilih Neraca", key="home_neraca", width='stretch', disabled=is_disabled):
            st.session_state.page = "Scraping"; st.session_state.sub_page = "Neraca"; st.rerun()
    with col2_btn:
        st.subheader("👥 Sosial")
        if st.button("Pilih Sosial", key="home_sosial", width='stretch', disabled=is_disabled):
            st.session_state.page = "Scraping"; st.session_state.sub_page = "Sosial"; st.rerun()
    with col3_btn:
        st.subheader("🌾 Produksi")
        if st.button("Pilih Produksi", key="home_produksi", width='stretch', disabled=is_disabled):
            st.session_state.page = "Scraping"; st.session_state.sub_page = "Produksi"; st.rerun()
    with col4_btn:
        st.subheader("📑 Lainnya")
        if st.button("Pilih Lainnya", key="home_lainnya", width='stretch', disabled=is_disabled):
            st.session_state.page = "Scraping"; st.session_state.sub_page = "Lainnya"; st.rerun()

def show_pendahuluan_page():
    st.title("📖 Pendahuluan")
    st.markdown("---")
    st.markdown("""
    Selamat datang di **SKENA (Sistem Scraping Fenomena Konawe Selatan)**.

    Aplikasi ini dirancang untuk membantu dalam pengumpulan data berita online yang relevan dengan Kabupaten Konawe Selatan. 
    Dengan memanfaatkan teknologi web scraping, SKENA dapat secara otomatis mencari, mengumpulkan, dan menyajikan data dari berbagai sumber berita di internet.
    """)
    if not st.session_state.get('logged_in', False):
        st.markdown("Silakan **Login** melalui sidebar untuk mengakses fitur utama.")

def show_documentation_page():
    st.title("🗂️ Dokumentasi")
    st.markdown("Seluruh file, dataset, dan dokumentasi terkait proyek ini tersimpan di Google Drive.")
    
    folder_id = "1z1_w_FyFmNB7ExfVzFVc3jH5InWmQSvZ"
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
    st.link_button("Buka Google Drive", folder_url, width='stretch', type="primary")
    
    st.markdown("---")
    
    with st.expander("Tampilkan Pratinjau Folder di Sini"):
        embed_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}"
        st.components.v1.html(f'<iframe src="{embed_url}" width="100%" height="600" style="border:1px solid #ddd; border-radius: 8px;"></iframe>', height=620)

def show_scraping_page():
    st.title(f"⚙️ Halaman Scraping Data")
    
    sub_page_options = ["Neraca", "Sosial", "Produksi", "Lainnya"]
    st.session_state.sub_page = st.radio(
        "Pilih Kategori Data:",
        sub_page_options,
        horizontal=True,
        key="sub_page_radio"
    )
    st.markdown("---")
    
    if st.session_state.sub_page in ["Sosial", "Produksi", "Lainnya"]:
        st.header("Segera Hadir!")
        st.info(f"Fitur scraping untuk data **{st.session_state.sub_page}** sedang dalam pengembangan.")
        st.balloons()
        return

    url_lapus = "https://docs.google.com/spreadsheets/d/19FRmYvDvjhCGL3vDuOLJF54u7U7hnfic/export?format=xlsx"
    url_daerah = "https://docs.google.com/spreadsheets/d/1Y2SbHlWBWwcxCdAhHiIkdQmcmq--NkGk/export?format=xlsx"

    with st.spinner("Memuat data kata kunci..."):
        df_lapus = load_data_from_url(url_lapus, sheet_name='Sheet1')
        df_daerah = load_data_from_url(url_daerah)

    if df_lapus is None or df_daerah is None:
        st.error("Gagal memuat data kata kunci. Aplikasi tidak dapat berjalan.")
        return

    st.success("✅ Data kata kunci berhasil dimuat.")
    original_categories = df_lapus.columns.tolist()

    st.header("Atur Parameter Scraping")
    
    tahun_sekarang = date.today().year
    tahun_list = ["--Pilih Tahun--"] + list(range(2020, tahun_sekarang + 1))
    tahun_input = st.selectbox("Pilih Tahun:", options=tahun_list)
    triwulan_list = ["--Pilih Triwulan--", "Triwulan 1", "Triwulan 2", "Triwulan 3", "Triwulan 4", "Tanggal Custom"]
    triwulan_input = st.selectbox("Pilih Triwulan:", options=triwulan_list)
    start_date_input, end_date_input = None, None
    if triwulan_input == "Tanggal Custom":
        col1, col2 = st.columns(2)
        with col1:
            start_date_input = st.date_input("Tanggal Awal", date.today() - timedelta(days=30))
        with col2:
            end_date_input = st.date_input("Tanggal Akhir", date.today())
    
    opsi_kategori_list = ["Semua Kategori", "Pilih Kategori Tertentu"]
    mode_kategori = st.radio("Pilih Opsi Kategori:", opsi_kategori_list, horizontal=True)
    
    kategori_terpilih = []
    if mode_kategori == 'Pilih Kategori Tertentu':
        kategori_terpilih = st.multiselect(
            'Pilih kategori untuk diproses:',
            options=original_categories,
            max_selections=3
        )
        st.caption("Catatan: Anda hanya dapat memilih maksimal 3 kategori.")

    is_disabled = (tahun_input == "--Pilih Tahun--" or triwulan_input == "--Pilih Triwulan--" or (mode_kategori == 'Pilih Kategori Tertentu' and not kategori_terpilih))

    if st.button("🚀 Mulai Scraping", width='stretch', type="primary", disabled=is_disabled):
        st.session_state.hasil_scraping = []
        
        tahun_int = int(tahun_input)
        tanggal_awal, tanggal_akhir = get_rentang_tanggal(tahun_int, triwulan_input, start_date_input, end_date_input)
        
        if tanggal_awal and tanggal_akhir:
            start_time = time.time()
            df_lapus_untuk_proses = df_lapus[kategori_terpilih] if mode_kategori == 'Pilih Kategori Tertentu' else df_lapus
            
            st.markdown("---")
            st.header("Proses & Hasil Scraping")
            
            keyword_placeholder = st.empty()
            table_placeholder = st.empty()
            
            with table_placeholder.container():
                st.markdown("### Hasil Scraping Terkini")
                st.info("Menunggu hasil pertama ditemukan...")
            
            hasil_df = start_scraping(tanggal_awal, tanggal_akhir, df_lapus_untuk_proses, df_daerah, start_time, table_placeholder, keyword_placeholder)
            
            end_time = time.time()
            total_duration_str = f"{int((end_time - start_time) // 60)} menit {int((end_time - start_time) % 60)} detik"

            st.header("✅ Proses Selesai")
            st.success(f"Scraping telah selesai dalam {total_duration_str}.")

            if not hasil_df.empty:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    hasil_df.to_excel(writer, sheet_name="Hasil Scraping", index=False)
                
                kategori_file = st.session_state.sub_page
                periode_file = triwulan_input.replace(' ', '_')
                tahun_file = tahun_input
                tanggal_running = time.strftime('%Y%m%d')
                jam_running = time.strftime('%H%M%S')
                
                nama_file_baru = f"Hasil Scraping_{kategori_file}_{periode_file}_{tahun_file}_{tanggal_running}_{jam_running}.xlsx"
                
                st.download_button(
                    label="📥 Unduh Hasil Scraping (Excel)",
                    data=output.getvalue(),
                    file_name=nama_file_baru,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width='stretch'
                )
            else:
                st.warning("Tidak ada berita yang ditemukan sesuai dengan parameter dan kata kunci yang Anda pilih.")

            if st.button("🔄 Mulai Scraping Baru (Reset)", width='stretch'):
                if 'hasil_scraping' in st.session_state:
                    del st.session_state.hasil_scraping
                st.rerun()
        else:
            st.error("Rentang tanggal tidak valid. Silakan periksa kembali pilihan Anda.")

# --- NAVIGASI DAN LOGIKA UTAMA ---
if "page" not in st.session_state:
    st.session_state.page = "Home"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "sub_page" not in st.session_state:
    st.session_state.sub_page = "Neraca"

with st.sidebar:
    st.image("logo bps konsel.png")
    
    if not st.session_state.logged_in:
        with st.form("login_form"):
            st.header("Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", width='stretch', type="primary"):
                if username == "user7405" and password == "bps7405":
                    st.session_state.logged_in = True
                    st.session_state.page = "Home"
                    st.rerun()
                else:
                    st.warning("Username atau password salah. Hubungi admin untuk bantuan.")
    else:
        st.success(f"Selamat datang, **user7405**!")
        if st.button("Logout", width='stretch'):
            st.session_state.logged_in = False
            st.session_state.page = "Home"
            st.rerun()

    st.markdown("---")
    st.header("Menu Navigasi")
    
    if st.button("🏠 Home", width='stretch'):
        set_page("Home"); st.rerun()
        
    if st.button("📖 Pendahuluan", width='stretch'):
        set_page("Pendahuluan"); st.rerun()

    if st.session_state.logged_in:
        if st.button("⚙️ Scraping", width='stretch'):
            set_page("Scraping"); st.rerun()
        
        if st.button("🗂️ Dokumentasi", width='stretch'):
            set_page("Dokumentasi"); st.rerun()

if st.session_state.page == "Home":
    show_home_page()
elif st.session_state.page == "Pendahuluan":
    show_pendahuluan_page()
elif st.session_state.page == "Scraping" and st.session_state.logged_in:
    show_scraping_page()
elif st.session_state.page == "Dokumentasi" and st.session_state.logged_in:
    show_documentation_page()
else:
    st.session_state.page = "Home"
    st.rerun()
