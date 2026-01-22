from datetime import datetime
import pytz
from functools import lru_cache
import math
from telegram import InlineKeyboardButton
from .data_manager import jadwal_data

WIB = pytz.timezone('Asia/Jakarta')

# =================== CACHE ===================
def get_today():
    """Selalu ambil hari terbaru berdasarkan timezone WIB"""
    now = datetime.now(WIB)
    days = {
        "Monday": "Senin",
        "Tuesday": "Selasa",
        "Wednesday": "Rabu",
        "Thursday": "Kamis",
        "Friday": "Jumat",
        "Saturday": "Sabtu",
        "Sunday": "Minggu"
    }
    english_day = now.strftime("%A")
    return days[english_day]

@lru_cache(maxsize=64)
def cached_format_time(hour, minute):
    """Cache format waktu"""
    return f"{hour:02d}:{minute:02d}"

# =================== FUNGSI HELPER ===================
def get_media_for_today():
    """Ambil media untuk hari ini"""
    today = get_today()
    return jadwal_data.get("media_jadwal", {}).get(today, {"type": "", "url": ""})

def format_jadwal_hari_ini():
    """Format jadwal PERSIS seperti di foto contoh"""
    today = get_today()

    # Header dengan format persis seperti foto
    msg = f"<b>Jadwal Donghua Hari Ini :</b>\n"

    # Jadwal harian
    if jadwal_data["harian"][today]:
        for i, anime in enumerate(jadwal_data["harian"][today], 1):
            if isinstance(anime, dict):
                # Anime dengan link - tampilkan sebagai hyperlink
                msg += f"  {i}. <a href=\"{anime['link']}\">{anime['judul']}</a>\n"
            else:
                # Anime tanpa link
                msg += f"  {i}. {anime}\n"
    else:
        msg += "❌ <i>Tidak ada jadwal donghua hari ini dalam waktu dekat</i>\n"

    # Upcoming section dengan format blockquote seperti di foto
    msg += "\n<b>Upcoming Donghua :\n</b>"

    if jadwal_data["upcoming"]:
        for i, up in enumerate(jadwal_data["upcoming"], 1):
            # Format blockquote hijau seperti di foto dengan format yang diperbaiki
            msg += f'<blockquote>{i}. <b>{up["judul"]}</b>'
            if up.get("season"):
                msg += f'[Season {up["season"]}]'

            # Cek apakah ada link atau tidak
            if up.get("link"):
                msg += f'\n({up["hari"]}, {up["tanggal"]}) (<a href="{up["link"]}">PV</a>)</blockquote>\n'
            else:
                msg += f'\n({up["hari"]}, {up["tanggal"]})</blockquote>\n'
    else:
        msg += "<blockquote>Belum ada donghua dalam waktu dekat</blockquote>\n\n"

    # Footer dengan link Telegraph
    if jadwal_data.get("telegraph_url"):
        msg += f'<a href="{jadwal_data["telegraph_url"]}"><b>Jadwal Donghua Semua Hari</b></a>\n#botjadwal'
    else:
        msg += "<b>Jadwal Donghua Semua Hari</b>\n#botjadwal"

    return msg

def format_jadwal_lengkap():
    """Format jadwal lengkap untuk command /jadwal"""
    today = get_today()

    # Header
    msg = f"<b>Jadwal Donghua Hari Ini :</b>\n"

    # Jadwal hari ini
    if jadwal_data["harian"][today]:
        for i, anime in enumerate(jadwal_data["harian"][today], 1):
            if isinstance(anime, dict):
                # Anime dengan link - tampilkan sebagai hyperlink
                msg += f" {i}. <a href=\"{anime['link']}\">{anime['judul']}</a>\n"
            else:
                # Anime tanpa link
                msg += f" {i}. {anime}\n"
    else:
        msg += "Tidak ada jadwal hari ini\n"

    # Upcoming section
    msg += "\n<b>Upcoming Donghua :\n</b>"

    if jadwal_data["upcoming"]:
        for i, up in enumerate(jadwal_data["upcoming"], 1):
            msg += f'<blockquote>{i}. <b>{up["judul"]}</b>'
            if up.get("season"):
                msg += f'[Season {up["season"]}]'

            # Cek apakah ada link atau tidak
            if up.get("link"):
                msg += f'\n({up["hari"]}, {up["tanggal"]}) (<a href="{up["link"]}">PV</a>)</blockquote>\n'
            else:
                msg += f'\n({up["hari"]}, {up["tanggal"]})</blockquote>\n'
    else:
        msg += "<blockquote> Belum ada donghua dalam waktu dekat </blockquote>\n\n"

    # Footer dengan link Telegraph
    if jadwal_data.get("telegraph_url"):
        msg += f'<a href="{jadwal_data["telegraph_url"]}"><b>Jadwal Donghua Semua Hari</b></a>\n#botjadwal'
    else:
        msg += "<b>Jadwal Donghua Semua Hari</b>\n#botjadwal"

    return msg

def format_rules_message():
    """Format pesan rules dengan hashtag"""
    if not jadwal_data.get("rules_text"):
        return "❌ <i>Rules belum diset oleh admin</i>\n\n#rulesbot"

    return f"{jadwal_data['rules_text']}\n\n#rulesbot"

# =================== PAGINATION FUNCTIONS ===================
def get_all_schedule_items():
    """Dapatkan semua item jadwal (harian + upcoming) dengan indexing"""
    items = []

    # Jadwal harian
    for hari in ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]:
        for anime in jadwal_data["harian"][hari]:
            if isinstance(anime, dict):
                display_text = f"{anime['judul']} ({hari})"
                items.append({
                    'type': 'harian',
                    'text': display_text,
                    'hari': hari,
                    'anime': anime,
                    'hash': hash(anime['judul']) % 1000
                })
            else:
                items.append({
                    'type': 'harian',
                    'text': f"{anime} ({hari})",
                    'hari': hari,
                    'anime': anime,
                    'hash': hash(anime) % 1000
                })

    # Upcoming
    for i, up in enumerate(jadwal_data["upcoming"]):
        items.append({
            'type': 'upcoming',
            'text': f"{up['judul']} (Upcoming)",
            'index': i,
            'data': up
        })

    return items

def generate_delete_keyboard(page=1, items_per_page=10):
    """Generate keyboard dengan pagination 2 kolom, 5 baris"""
    all_items = get_all_schedule_items()
    total_items = len(all_items)
    total_pages = math.ceil(total_items / items_per_page)

    if total_pages == 0:
        return [[InlineKeyboardButton("Belum ada jadwal", callback_data="back")], [InlineKeyboardButton("Kembali", callback_data="back")]]

    # Pastikan page dalam range
    page = max(1, min(page, total_pages))

    start_index = (page - 1) * items_per_page
    end_index = min(start_index + items_per_page, total_items)
    current_items = all_items[start_index:end_index]

    keyboard = []

    # Items dalam 2 kolom, maksimal 5 baris (10 items per halaman)
    for i in range(0, len(current_items), 2):
        row = []
        for j in range(2):
            if i + j < len(current_items):
                item = current_items[i + j]
                # Truncate text jika terlalu panjang
                display_text = item['text'][:20] + "..." if len(item['text']) > 20 else item['text']

                if item['type'] == 'harian':
                    callback_data = f"del_h_{item['hari']}_{item['hash']}"
                else:
                    callback_data = f"del_u_{item['index']}"

                row.append(InlineKeyboardButton(f"❌ {display_text}", callback_data=callback_data))

        if row:
            keyboard.append(row)

    # Pagination controls jika lebih dari 1 halaman
    if total_pages > 1:
        pagination_row = []

        # Previous button
        if page > 1:
            pagination_row.append(InlineKeyboardButton("◀️", callback_data=f"del_page_{page-1}"))

        # Page numbers (maksimal 5 angka)
        start_page = max(1, page - 2)
        end_page = min(total_pages, start_page + 4)

        # Adjust start_page jika end_page sudah maksimal
        if end_page - start_page < 4:
            start_page = max(1, end_page - 4)

        for p in range(start_page, end_page + 1):
            if p == page:
                pagination_row.append(InlineKeyboardButton(f"• {p} •", callback_data=f"del_page_{p}"))
            else:
                pagination_row.append(InlineKeyboardButton(str(p), callback_data=f"del_page_{p}"))

        # Next button
        if page < total_pages:
            pagination_row.append(InlineKeyboardButton("▶️", callback_data=f"del_page_{page+1}"))

        keyboard.append(pagination_row)

    # Kembali button
    keyboard.append([InlineKeyboardButton("Kembali", callback_data="back")])

    return keyboard
