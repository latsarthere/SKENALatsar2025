import streamlit as st
import pandas as pd
import time
import io
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from pygooglenews import GoogleNews
from urllib.parse import urlparse

# Import baru untuk solusi yang benar
from requests_html import AsyncHTMLSession
import asyncio

# Fungsi yang sudah diperbaiki untuk mendapatkan link asli
@st.cache_data(show_spinner=False)
def get_real_url(gn_link):
    """
    Ambil URL asli dari link Google News menggunakan AsyncHTMLSession.
    Ini adalah metode yang paling andal karena bisa menjalankan JavaScript.
    """
    async def resolve_url():
        session = AsyncHTMLSession()
        try:
            r = await session.get(gn_link, timeout=25)
            await r.html.arender(sleep=2, timeout=25)
            final_url = r.url
            await session.close()
            return final_url
        except Exception as e:
            await session.close()
            print(f"Error saat merender URL {gn_link}: {e}")
            return gn_link

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    final_url = loop.run_until_complete(resolve_url())
    
    if "google.com" in final_url and "url=" not in final_url:
        return gn_link
    
    return final_url

# --- Konfigurasi Halaman Streamlit ---
st.set_page_config(
    page_title="SKENA",
    # page_icon="logo skena.png", # Pastikan file logo ada
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
        if not link.startswith(('http://', 'https://')):
            return ""
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

# --- Fungsi scraping utama ---
def start_scraping(tanggal_awal, tanggal_akhir, kata_kunci_lapus_df, kata_kunci_daerah_df, start_time, table_placeholder, keyword_placeholder):
    kata_kunci_lapus_dict = {
        c: kata_kunci_lapus_df[c].dropna().astype(str).str.strip().tolist()
        for c in kata_kunci_lapus_df.columns
    }
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
            status_placeholder.info(
                f"⏳ Proses... ({int(elapsed_time // 60)}m {int(elapsed_time % 60)}d) "
                f"| 📁 Kategori {kategori_ke}/{total_kategori}: {kategori}"
            )
            if pd.isna(keyword_raw): continue
            keyword = str(keyword_raw).strip()
            if not keyword: continue

            keyword_placeholder.text(f"  ➡️ 🔍 Mencari: '{keyword}' di '{nama_daerah}'")
            search_query = f'"{keyword}" "{nama_daerah}"'
            try:
                search_results = gn.search(search_query, from_=tanggal_awal, to_=tanggal_akhir)
                for entry in search_results['entries']:
                    real_url = get_real_url(entry.link)
                    if any(d['Link'] == real_url for d in semua_hasil):
                        continue
                    judul = entry.title
                    ringkasan = ambil_ringkasan(real_url)
                    
                    if not ringkasan and "google.com" not in real_url:
                        st.warning(f"Gagal mengambil ringkasan untuk: {real_url}")

                    judul_lower = judul.lower()
                    ringkasan_lower = ringkasan.lower()
                    keyword_lower = keyword.lower()
                    lokasi_ditemukan = any(loc in judul_lower or loc in ringkasan_lower for loc in lokasi_filter)
                    keyword_ditemukan = (keyword_lower in judul_lower or keyword_lower in ringkasan_lower)

                    if lokasi_ditemukan or keyword_ditemukan:
                        try:
                            tanggal_dt = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z')
                            tanggal_str = tanggal_dt.strftime('%d-%m-%Y')
                        except (ValueError, TypeError):
                            tanggal_str = "N/A"
                        sumber = urlparse(real_url).netloc.replace("www.", "")
                        semua_hasil.append({
                            "Nomor": len(semua_hasil) + 1, "Kata Kunci": keyword, "Judul": judul,
                            "Link": real_url, "Sumber": sumber, "Tanggal": tanggal_str, "Ringkasan": ringkasan
                        })
            except Exception as e:
                st.warning(f"Terjadi error saat mencari '{keyword}': {e}")
                continue
        if semua_hasil:
            df_live = pd.DataFrame(semua_hasil)
            kolom_urut = ["Nomor", "Kata Kunci", "Judul", "Link", "Sumber", "Tanggal", "Ringkasan"]
            df_live = df_live[kolom_urut]
            with table_placeholder.container():
                st.markdown("### Hasil Scraping Terkini")
                st.dataframe(df_live, use_container_width=True, height=400)
                st.caption(f"Total berita ditemukan: {len(df_live)}")
    if semua_hasil:
        return pd.DataFrame(semua_hasil)
    else:
        return pd.DataFrame()

# (Sisa kode untuk UI Streamlit tidak perlu diubah, biarkan seperti yang sudah ada)
def show_home_page():
    # ... (kode Anda sebelumnya)
    pass
def show_pendahuluan_page():
    # ... (kode Anda sebelumnya)
    pass
def show_documentation_page():
    # ... (kode Anda sebelumnya)
    pass
def show_scraping_page():
    # ... (kode Anda sebelumnya)
    pass
# --- MAIN LOGIC ---
# ... (kode Anda sebelumnya)
