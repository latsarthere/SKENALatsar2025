import streamlit as st

import pandas as pd

import time

import io

import requests

from bs4 import BeautifulSoup

from datetime import date, datetime, timedelta

from pygooglenews import GoogleNews



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

    

    /* [BARU] Class untuk perataan teks */

    .text-center { text-align: center; }

    .text-justify { text-align: justify; }

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



def ambil_ringkasan(link):

    try:

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

        response = requests.get(link, timeout=10, headers=headers)

        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        deskripsi = soup.find('meta', attrs={'name': 'description'})

        if deskripsi and deskripsi.get('content'): return deskripsi['content']

        og_desc = soup.find('meta', attrs={'property': 'og:description'})

        if og_desc and og_desc.get('content'): return og_desc['content']

        p_tag = soup.find('p')

        if p_tag: return p_tag.get_text(strip=True)

    except Exception:

        return ""

    return ""



def start_scraping(tanggal_awal, tanggal_akhir, kata_kunci_lapus_df, kata_kunci_daerah_df, start_time, table_placeholder, keyword_placeholder):

    kata_kunci_lapus_dict = {c: kata_kunci_lapus_df[c].dropna().astype(str).str.strip().tolist() for c in kata_kunci_lapus_df.columns}

    nama_daerah = "Konawe Selatan"

    

    kecamatan_list = kata_kunci_daerah_df[nama_daerah].dropna().astype(str).str.strip().tolist()

    lokasi_filter = [nama_daerah.lower()] + [kec.lower() for kec in kecamatan_list]

    

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

            

            keyword_placeholder.text(f"  ➡️ 🔍 Mencari: '{keyword}'")

            

            search_query = f'"{keyword}" "{nama_daerah}"'

            try:

                search_results = gn.search(search_query, from_=tanggal_awal, to_=tanggal_akhir)

                for entry in search_results['entries']:

                    link = entry.link

                    if any(d['Link'] == link for d in st.session_state.hasil_scraping): continue



                    judul = entry.title

                    ringkasan = ambil_ringkasan(link)

                    

                    judul_lower, ringkasan_lower, keyword_lower = judul.lower(), ringkasan.lower(), keyword.lower()

                    lokasi_ditemukan = any(loc in judul_lower or loc in ringkasan_lower for loc in lokasi_filter)

                    keyword_ditemukan = keyword_lower in judul_lower or keyword_lower in ringkasan_lower



                    if lokasi_ditemukan or keyword_ditemukan:

                        try:

                            tanggal_dt = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z')

                            tanggal_str = tanggal_dt.strftime('%d-%m-%Y')

                        except (ValueError, TypeError):

                            tanggal_str = "N/A"

                        

                        st.session_state.hasil_scraping.append({

                            "Nomor": len(st.session_state.hasil_scraping) + 1,

                            "Kategori": kategori,

                            "Kata Kunci": keyword, "Judul": judul,

                            "Link": link, "Tanggal": tanggal_str, "Ringkasan": ringkasan

                        })

            except Exception:

                continue



        if st.session_state.hasil_scraping:

            df_live = pd.DataFrame(st.session_state.hasil_scraping)

            kolom_urut = ["Nomor", "Kategori", "Kata Kunci", "Judul", "Link", "Tanggal", "Ringkasan"]

            df_live = df_live[kolom_urut]

            with table_placeholder.container():

                st.markdown("### Hasil Scraping Terkini")

                st.dataframe(df_live, use_container_width=True, height=400)

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

    st.image("logo skena full.png", use_container_width=True)

    st.markdown("---")

    

    # --- [DIUBAH] Teks pengantar menjadi justify ---

    st.markdown("""

    <div class='text-justify'>

        Hallo! Sistem Scraping Konawe Selatan (SKENA) merupakan alat bantu BPS Kabupaten Konawe Selatan dalam menyediakan data statistik yang lengkap. 

        Sistem ini melakukan pencarian (<i>scraping</i>) fenomena pendukung dalam bentuk berita di Google.

    </div>

    """, unsafe_allow_html=True)



    # --- [DIUBAH] Tombol Pendahuluan menjadi justify ---

    st.markdown("""

    <div class='text-justify' style='margin-top: 10px;'>

        Sebelum mengakses fitur utama, sangat disarankan untuk membaca bagian <b>Pendahuluan</b> terlebih dahulu.

    </div>

    """, unsafe_allow_html=True)

    

    if not st.session_state.get('logged_in', False):

        # --- [DIUBAH] Info Login menjadi justify ---

        st.markdown("<div class='text-justify' style='margin-top: 1rem;'>", unsafe_allow_html=True)

        st.info("Silakan Login melalui sidebar untuk menggunakan menu Scraping dan Dokumentasi.")

        st.markdown("</div>", unsafe_allow_html=True)

    

    st.markdown("<h2 class='text-center' style='margin-top: 2rem;'>Pilih Kategori Data</h2>", unsafe_allow_html=True)

    

    col1_btn, col2_btn, col3_btn, col4_btn = st.columns(4, gap="large")

    is_disabled = not st.session_state.get('logged_in', False)

    

    with col1_btn:

        st.subheader("📈 Neraca")

        if st.button("Pilih Neraca", key="home_neraca", use_container_width=True, disabled=is_disabled):

            st.session_state.page = "Scraping"; st.session_state.sub_page = "Neraca"; st.rerun()

    with col2_btn:

        st.subheader("👥 Sosial")

        if st.button("Pilih Sosial", key="home_sosial", use_container_width=True, disabled=is_disabled):

            st.session_state.page = "Scraping"; st.session_state.sub_page = "Sosial"; st.rerun()

    with col3_btn:

        st.subheader("🌾 Produksi")

        if st.button("Pilih Produksi", key="home_produksi", use_container_width=True, disabled=is_disabled):

            st.session_state.page = "Scraping"; st.session_state.sub_page = "Produksi"; st.rerun()

    with col4_btn:

        st.subheader("📑 Lainnya")

        if st.button("Pilih Lainnya", key="home_lainnya", use_container_width=True, disabled=is_disabled):

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

    st.link_button("Buka Google Drive", folder_url, use_container_width=True, type="primary")

    

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

        kategori_terpilih = st.multiselect('Pilih kategori untuk diproses:', options=original_categories)



    is_disabled = (tahun_input == "--Pilih Tahun--" or triwulan_input == "--Pilih Triwulan--" or (mode_kategori == 'Pilih Kategori Tertentu' and not kategori_terpilih))



    if st.button("🚀 Mulai Scraping", use_container_width=True, type="primary", disabled=is_disabled):

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

                

                st.download_button(

                    label="📥 Unduh Hasil Scraping (Excel)",

                    data=output.getvalue(),

                    file_name=f"Hasil_Scraping_{time.strftime('%Y%m%d-%H%M%S')}.xlsx",

                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

                    use_container_width=True

                )

            else:

                st.warning("Tidak ada berita yang ditemukan sesuai dengan parameter dan kata kunci yang Anda pilih.")



            if st.button("🔄 Mulai Scraping Baru (Reset)", use_container_width=True):

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

            if st.form_submit_button("Login", use_container_width=True, type="primary"):

                if username == "user7405" and password == "bps7405":

                    st.session_state.logged_in = True

                    st.session_state.page = "Home"

                    st.rerun()

                else:

                    st.warning("Username atau password salah. Hubungi admin untuk bantuan.")

    else:

        st.success(f"Selamat datang, **user7405**!")

        if st.button("Logout", use_container_width=True):

            st.session_state.logged_in = False

            st.session_state.page = "Home"

            st.rerun()



    st.markdown("---")

    st.header("Menu Navigasi")

    

    if st.button("🏠 Home", use_container_width=True):

        set_page("Home"); st.rerun()

        

    if st.button("📖 Pendahuluan", use_container_width=True):

        set_page("Pendahuluan"); st.rerun()



    if st.session_state.logged_in:

        if st.button("⚙️ Scraping", use_container_width=True):

            set_page("Scraping"); st.rerun()

        

        if st.button("🗂️ Dokumentasi", use_container_width=True):

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
