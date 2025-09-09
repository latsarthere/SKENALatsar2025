import requests
from urllib.parse import urlparse, parse_qs, unquote

def get_final_url(gn_link: str) -> str:
    """
    Mengambil URL asli dari sebuah link dengan mengikuti semua pengalihan (redirects).
    Metode ini lebih andal untuk berbagai jenis link, termasuk dari Google News.

    Args:
        gn_link: URL dari Google News atau link lain yang perlu dilacak.

    Returns:
        URL final setelah semua pengalihan, atau URL asli jika terjadi error.
    """
    # Header untuk meniru browser biasa, menghindari blokir dari beberapa situs.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        # --- Optimisasi: Cek cepat jika URL asli ada di query parameter ---
        # Ini sama seperti logikamu sebelumnya, sangat efisien jika berhasil.
        try:
            parsed_url = urlparse(gn_link)
            query_params = parse_qs(parsed_url.query)
            if "url" in query_params:
                # Menggunakan unquote untuk membersihkan URL dari encoding seperti %3D, dll.
                return unquote(query_params["url"][0])
        except Exception:
            # Jika parsing gagal, lanjutkan ke metode utama.
            pass

        # --- Metode Utama: Biarkan `requests` mengikuti semua redirect ---
        # Ini adalah cara paling ampuh dan sederhana. `requests` akan otomatis
        # menangani redirect 3xx, meta refresh (jika didukung oleh server-side), dll.
        with requests.Session() as session:
            session.headers.update(headers)
            # Lakukan request GET, dan biarkan `allow_redirects` (yang default-nya True) bekerja.
            # Timeout dinaikkan sedikit untuk koneksi yang lebih lambat.
            response = session.get(gn_link, timeout=15)
            
            # Atribut `.url` dari objek response akan berisi URL final setelah semua redirect.
            final_url = response.url
            
            # Pastikan URL final juga di-unquote untuk kebersihan maksimal.
            return unquote(final_url)

    except requests.exceptions.RequestException as e:
        print(f"Gagal mengambil URL karena masalah jaringan: {e}")
        # Jika terjadi error jaringan (misal: timeout, tidak bisa terhubung),
        # kembalikan link asli.
        return gn_link
    except Exception as e:
        print(f"Terjadi error tak terduga: {e}")
        # Menangkap error lainnya dan mengembalikan link asli.
        return gn_link

# --- Contoh Penggunaan ---
if __name__ == "__main__":
    # Ganti dengan link Google News yang ingin diuji
    # Contoh link (mungkin sudah tidak aktif, hanya sebagai format)
    example_link = "https://news.google.com/rss/articles/CBMiYmh0dHBzOi8vd3d3LmNubi5jb20vMjAyNC8wMS8wMS9wb2xpdGljcy90cnVtcC1tYWluZS1iYWxsb3QtYXBwZWFsL2luZGV4Lmh0bWzSAQA?oc=5"
    
    print(f"Link Asli:\n{example_link}\n")
    
    # Panggil fungsi untuk mendapatkan URL sebenarnya
    real_url = get_final_url(example_link)
    
    print(f"Link Sebenarnya (untuk AI):\n{real_url}")
