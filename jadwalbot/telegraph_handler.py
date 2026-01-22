import logging
import requests
from datetime import datetime
import pytz
from .data_manager import jadwal_data, save_data
from .utils import get_today

logger = logging.getLogger(__name__)
WIB = pytz.timezone('Asia/Jakarta')

# =================== TELEGRAPH FUNCTIONS ===================
def create_telegraph_account():
    """Buat akun Telegraph baru"""
    try:
        url = "https://api.telegra.ph/createAccount"
        data = {
            "short_name": "JadwalDonghua",
            "author_name": "Jadwal Donghua Bot",
            "author_url": "https://t.me/AnimeStreamingID"
        }
        response = requests.post(url, json=data, timeout=15)

        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                return result['result']['access_token']
    except Exception as e:
        logger.error(f"Telegraph account creation error: {e}")
    return None

def create_telegraph_page(token, title, content):
    """Buat/Update halaman Telegraph"""
    try:
        url = "https://api.telegra.ph/createPage"
        data = {
            "access_token": token,
            "title": title,
            "content": content,
            "return_content": False
        }
        response = requests.post(url, json=data, timeout=15)

        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                return result['result']['url']
    except Exception as e:
        logger.error(f"Telegraph page creation error: {e}")
    return None

def update_telegraph_page(token, path, title, content):
    """Update halaman Telegraph yang sudah ada"""
    try:
        url = f"https://api.telegra.ph/editPage/{path}"
        data = {
            "access_token": token,
            "title": title,
            "content": content,
            "return_content": False
        }
        response = requests.post(url, json=data, timeout=15)

        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                return result['result']['url']
    except Exception as e:
        logger.error(f"Telegraph page update error: {e}")
    return None

def generate_telegraph_content():
    """Generate konten Telegraph pakai HTML tags terstruktur"""
    now = datetime.now(WIB)
    today = get_today()

    bulan_indo = {
        1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
        7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember"
    }

    date = now.day
    month = bulan_indo[now.month]
    year = now.year
    update_time = now.strftime("%H:%M")

    content = []

    # Header dengan HTML br
    content.append({
        "tag": "p",
        "children": [f"Pembaruan pada {today}, {date} {month} {year} pukul {update_time} WIB"]
    })

    # BR tags untuk spasi
    content.append({"tag": "br"})
    content.append({"tag": "br"})

    for hari in ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]:
        if jadwal_data["harian"][hari]:
            # Nama hari
            content.append({
                "tag": "p",
                "children": [{"tag": "strong", "children": [hari]}]
            })

            # List anime
            for i, anime in enumerate(jadwal_data["harian"][hari], 1):
                if isinstance(anime, dict):
                    # Anime dengan link
                    content.append({
                        "tag": "p",
                        "children": [
                            f"   {i}. ",
                            {"tag": "a", "attrs": {"href": anime["link"]}, "children": [anime["judul"]]}
                        ]
                    })
                else:
                    # Anime tanpa link (string biasa)
                    content.append({
                        "tag": "p",
                        "children": [f"   {i}. {anime}"]
                    })

            # Spasi antar hari - double BR
            content.append({"tag": "br"})
            content.append({"tag": "br"})

    return content

def update_telegraph():
    """Update halaman Telegraph dengan jadwal terbaru"""
    if not jadwal_data.get("telegraph_token"):
        return False

    title = "Jadwal Donghua CA3D "
    content = generate_telegraph_content()

    if jadwal_data.get("telegraph_url"):
        # Update existing page
        try:
            path = jadwal_data["telegraph_url"].split("/")[-1]
            url = update_telegraph_page(jadwal_data["telegraph_token"], path, title, content)
            if url:
                jadwal_data["telegraph_url"] = url
                save_data()
                return True
        except Exception as e:
            logger.error(f"Telegraph update error: {e}")

    # Create new page jika update gagal
    url = create_telegraph_page(jadwal_data["telegraph_token"], title, content)
    if url:
        jadwal_data["telegraph_url"] = url
        save_data()
        return True

    return False
