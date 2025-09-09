import streamlit as st
import pandas as pd
import time
import io
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from pygooglenews import GoogleNews
import google.generativeai as genai
from newspaper import Article

# --- Konfigurasi API Key Gemini ---
# Kode ini membaca dari Secrets Manager di dashboard Streamlit Cloud Anda
try:
    API_KEYS = [
        st.secrets["gemini_api_key_1"]  # <-- Cukup satu baris ini
    ]
    current_key_idx = 0
except (KeyError, FileNotFoundError):
    st.error("Secret 'gemini_api_key_1' tidak ditemukan. Harap tambahkan di menu 'Manage app' > 'Secrets' pada dashboard Streamlit Cloud Anda.")
    API_KEYS = []
    current_key_idx = 0


# --- FUNGSI-FUNGSI BARU & YANG DIPERBARUI ---

def get_rotating_model():
    """Mengambil model Gemini."""
    # Karena hanya ada satu key, rotasi tidak lagi diperlukan, tapi struktur fungsi dipertahankan.
    global current_key_idx
    if not API_KEYS:
        # Pesan error sudah ditampilkan di atas, jadi di sini tidak perlu lagi.
        return None
    
    key = API_KEYS[0] # Langsung ambil key pertama
    
    try:
        genai.configure(api_key=key)
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        st.warning(f"Gagal mengkonfigurasi API Key: {e}")
        return None

# ... (Sisa kode Anda dari baris `def ringkas_dengan_gemini` ke bawah tidak perlu diubah sama sekali) ...
