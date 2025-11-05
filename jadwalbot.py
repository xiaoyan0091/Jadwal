
import json
import asyncio
import logging
from datetime import datetime, time, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import requests
from calendar import month_name
from telegram.request import HTTPXRequest
import pytz
import signal
import sys
import os
from functools import lru_cache

# =================== CONFIG ===================
BOT_TOKEN = "7240322775:AAFw4mmT7NpDed38TX6jSLIYjxRLmM4fsW8"  
OWNER_ID = 6444305696               

# =================== SETUP ===================
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Timezone WIB
WIB = pytz.timezone('Asia/Jakarta')

# Data storage
jadwal_data = {
    "harian": {"Senin":[],"Selasa":[],"Rabu":[],"Kamis":[],"Jumat":[],"Sabtu":[],"Minggu":[]}, 
    "upcoming": [],
    "channels": [],  # List channel/group untuk auto post bergiliran
    "post_time": "06:00",
    "auto_post_enabled": False,
    "telegraph_token": "",
    "telegraph_url": "",
    "rules_text": ""  # Rules text dengan support HTML
}
user_cooldown = {}
last_jadwal_time = None  # Waktu terakhir jadwal dikirim
last_rules_time = None  # Waktu terakhir rules dikirim

# Global variable for application
app = None

# =================== CACHE ===================
@lru_cache(maxsize=128)
def cached_get_today():
    """Cache hari ini untuk meningkatkan performa"""
    days = {"Monday":"Senin","Tuesday":"Selasa","Wednesday":"Rabu","Thursday":"Kamis","Friday":"Jumat","Saturday":"Sabtu","Sunday":"Minggu"}
    return days[datetime.now(WIB).strftime("%A")]

@lru_cache(maxsize=64)
def cached_format_time(hour, minute):
    """Cache format waktu"""
    return f"{hour:02d}:{minute:02d}"

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

# =================== KILL EXISTING BOT INSTANCES ===================
def kill_existing_bots():
    """Kill any existing bot processes to prevent conflict"""
    try:
        current_pid = os.getpid()
        
        # Get list of Python processes
        import subprocess
        result = subprocess.run(['pgrep', '-f', 'jadwalbot.py'], capture_output=True, text=True)
        
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid and int(pid) != current_pid:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        print(f"🔫 Killed existing bot process: {pid}")
                    except:
                        pass
        
        # Wait a moment for processes to terminate
        import time
        time.sleep(2)
        
    except Exception as e:
        logger.error(f"Error killing existing bots: {e}")

# =================== FUNGSI HELPER ===================
def save_data():
    try:
        with open("jadwal.json", "w", encoding="utf-8") as f:
            json.dump(jadwal_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Save data error: {e}")

def load_data():
    global jadwal_data
    try:
        with open("jadwal.json", "r", encoding="utf-8") as f:
            loaded = json.load(f)
            jadwal_data.update(loaded)
            # Migrate old channel_id to channels list
            if "channel_id" in jadwal_data and jadwal_data["channel_id"] and jadwal_data["channel_id"] not in jadwal_data.get("channels", []):
                if not jadwal_data.get("channels"):
                    jadwal_data["channels"] = []
                jadwal_data["channels"].append(jadwal_data["channel_id"])
                del jadwal_data["channel_id"]
                save_data()
            # Ensure rules_text exists
            if "rules_text" not in jadwal_data:
                jadwal_data["rules_text"] = ""
                save_data()
    except Exception as e:
        logger.error(f"Load data error: {e}")
        save_data()

def get_today():
    return cached_get_today()

def format_jadwal_hari_ini():
    """Format jadwal PERSIS seperti di foto contoh"""
    today = get_today()
    
    # Header dengan format persis seperti foto
    msg = f"<b>Jadwal Donghua Hari Ini :</b>\n"
    
    # Jadwal harian
    if jadwal_data["harian"][today]:
        for i, anime in enumerate(jadwal_data["harian"][today], 1):
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
            msg += f'\n({up["hari"]}, {up["tanggal"]}) (<a href="{up["link"]}">PV</a>)</blockquote>\n'
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
            msg += f" {i}. {anime}\n"
    else:
        msg += "Tidak ada jadwal hari ini\n"
    
    # Upcoming section
    msg += "\n<b>Upcoming Donghua :\n</b>\n"
    
    if jadwal_data["upcoming"]:
        for i, up in enumerate(jadwal_data["upcoming"], 1):
            msg += f'<blockquote>{i}. <b>{up["judul"]}</b>'
            if up.get("season"):
                msg += f'[Season {up["season"]}]'
            msg += f'\n({up["hari"]}, {up["tanggal"]}) (<a href="{up["link"]}">PV</a>)</blockquote>\n'
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

# =================== COMMAND HANDLERS ===================
async def jadwal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_jadwal_time
    user_id = update.effective_user.id
    now = datetime.now(WIB)
    
    # Owner tidak perlu anti spam
    if user_id != OWNER_ID:
        # Cek anti spam 20 menit
        if last_jadwal_time:
            time_diff = now - last_jadwal_time
            if time_diff < timedelta(minutes=20):
                minutes_ago = int(time_diff.total_seconds() / 60)
                minutes_left = 20 - minutes_ago
                
                anti_spam_msg = f"""Anti Spam!
Command Jadwal dapat diakses {minutes_left} menit lagi. Jadwal sudah pernah dikirim {minutes_ago} menit yang lalu, tekan hashtag
#botjadwal"""
                
                # Tunggu 2 detik lalu hapus pesan command
                await asyncio.sleep(2)
                try: 
                    await update.message.delete()
                except Exception as e:
                    logger.error(f"Delete message error: {e}")
                
                # Kirim pesan anti spam
                spam_msg = await update.effective_chat.send_message(anti_spam_msg)
                
                # Hapus pesan anti spam setelah 5 detik
                await asyncio.sleep(5)
                try:
                    await spam_msg.delete()
                except Exception as e:
                    logger.error(f"Delete spam message error: {e}")
                
                return
    
    # Rate limit 5 per menit
    if user_id in user_cooldown:
        if len([t for t in user_cooldown[user_id] if (now-t).seconds < 60]) >= 5:
            return
        user_cooldown[user_id].append(now)
    else:
        user_cooldown[user_id] = [now]
    
    # Tunggu 2 detik lalu hapus pesan command
    await asyncio.sleep(2)
    try: 
        await update.message.delete()
    except Exception as e:
        logger.error(f"Delete message error: {e}")
    
    # Update waktu terakhir jadwal dikirim
    last_jadwal_time = now
    
    # Kirim jadwal dengan format seperti foto
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=format_jadwal_lengkap(),
            parse_mode='HTML',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Send message error: {e}")

async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_rules_time
    user_id = update.effective_user.id
    now = datetime.now(WIB)
    
    # Owner tidak perlu anti spam
    if user_id != OWNER_ID:
        # Cek anti spam 20 menit
        if last_rules_time:
            time_diff = now - last_rules_time
            if time_diff < timedelta(minutes=20):
                minutes_ago = int(time_diff.total_seconds() / 60)
                minutes_left = 20 - minutes_ago
                
                anti_spam_msg = f"""Anti Spam!
Command Rules dapat diakses {minutes_left} menit lagi. Rules sudah pernah dikirim {minutes_ago} menit yang lalu, tekan hashtag
#rulesbot"""
                
                # Tunggu 2 detik lalu hapus pesan command
                await asyncio.sleep(2)
                try: 
                    await update.message.delete()
                except Exception as e:
                    logger.error(f"Delete message error: {e}")
                
                # Kirim pesan anti spam
                spam_msg = await update.effective_chat.send_message(anti_spam_msg)
                
                # Hapus pesan anti spam setelah 5 detik
                await asyncio.sleep(5)
                try:
                    await spam_msg.delete()
                except Exception as e:
                    logger.error(f"Delete spam message error: {e}")
                
                return
    
    # Rate limit 5 per menit
    if user_id in user_cooldown:
        if len([t for t in user_cooldown[user_id] if (now-t).seconds < 60]) >= 5:
            return
        user_cooldown[user_id].append(now)
    else:
        user_cooldown[user_id] = [now]
    
    # Tunggu 2 detik lalu hapus pesan command
    await asyncio.sleep(2)
    try: 
        await update.message.delete()
    except Exception as e:
        logger.error(f"Delete message error: {e}")
    
    # Update waktu terakhir rules dikirim
    last_rules_time = now
    
    # Kirim rules
    try:
        rules_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=format_rules_message(),
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        
        # Hapus pesan rules setelah 10 detik
        await asyncio.sleep(10)
        try:
            await rules_msg.delete()
        except Exception as e:
            logger.error(f"Delete rules message error: {e}")
            
    except Exception as e:
        logger.error(f"Send rules message error: {e}")

async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Akses ditolak!")
        return
    
    channels_info = f"{len(jadwal_data['channels'])} channel/group" if jadwal_data["channels"] else "❌ Belum diset"
    time_info = jadwal_data["post_time"]
    auto_status = "🟢 AKTIF" if jadwal_data["auto_post_enabled"] else "🔴 NONAKTIF"
    telegraph_status = "🟢 AKTIF" if jadwal_data.get("telegraph_token") else "🔴 NONAKTIF"
    rules_status = "🟢 SUDAH DISET" if jadwal_data.get("rules_text") else "🔴 BELUM DISET"
    
    today = get_today()
    jadwal_hari_ini = len(jadwal_data["harian"][today])
    total_minggu = sum(len(jadwal_data["harian"][hari]) for hari in jadwal_data["harian"])
    
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Jadwal", callback_data="tambah"),
         InlineKeyboardButton("🗑️ Hapus Jadwal", callback_data="hapus")],
        [InlineKeyboardButton("📋 Lihat Semua", callback_data="lihat"),
         InlineKeyboardButton("📢 Preview Hari Ini", callback_data="preview")],
        [InlineKeyboardButton("📺 Kelola Channel", callback_data="manage_channels"),
         InlineKeyboardButton("⏰ Set Jam Post", callback_data="set_time")],
        [InlineKeyboardButton("📰 Setup Telegraph", callback_data="setup_telegraph"),
         InlineKeyboardButton("🚀 Toggle Auto Post", callback_data="toggle_auto")],
        [InlineKeyboardButton("📜 Set Rules", callback_data="set_rules"),
         InlineKeyboardButton("👀 Preview Rules", callback_data="preview_rules")]
    ]
    
    next_post = "Tidak ada" if not jadwal_data["auto_post_enabled"] else f"Bergiliran setiap hari jam {jadwal_data['post_time']}"
    
    msg = f"""<b>🎬 PANEL ADMIN JADWAL DONGHUA</b>

<b>📊 Status Sistem:</b>
📅 Hari ini: <b>{today}</b>
📝 Jadwal hari ini: <b>{jadwal_hari_ini} anime</b>
📈 Total minggu ini: <b>{total_minggu} anime</b>
📺 Channel/Group: <b>{channels_info}</b>
⏰ Jam auto post: <b>{time_info} WIB</b>
🤖 Status: <b>{auto_status}</b>
📰 Telegraph: <b>{telegraph_status}</b>
📜 Rules: <b>{rules_status}</b>
⏭️ Posting: <b>{next_post}</b>"""
    
    try:
        await update.message.reply_text(
            msg,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Panel message error: {e}")

# =================== CALLBACK HANDLERS ===================
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != OWNER_ID:
        await query.edit_message_text("⛔ Akses ditolak!")
        return
    
    data = query.data
    
    if data == "set_rules":
        await query.edit_message_text(
            "<b>📜 SET RULES GROUP</b>\n\n"
            "Kirim teks rules yang akan ditampilkan saat user ketik <code>/rules</code>\n\n"
            "<b>✨ Support HTML Tags:</b>\n"
            "• <code>&lt;b&gt;Bold&lt;/b&gt;</code> → <b>Bold</b>\n"
            "• <code>&lt;i&gt;Italic&lt;/i&gt;</code> → <i>Italic</i>\n"
            "• <code>&lt;u&gt;Underline&lt;/u&gt;</code> → <u>Underline</u>\n"
            "• <code>&lt;s&gt;Strike&lt;/s&gt;</code> → <s>Strike</s>\n"
            "• <code>&lt;code&gt;Code&lt;/code&gt;</code> → <code>Code</code>\n"
            "• <code>&lt;a href=\"link\"&gt;Text&lt;/a&gt;</code> → Link\n"
            "• <code>&lt;blockquote&gt;Quote&lt;/blockquote&gt;</code> → Quote\n\n"
            "<b>📝 Contoh Rules:</b>\n"
            "<code>&lt;b&gt;📜 RULES GRUP&lt;/b&gt;\n\n"
            "1. &lt;b&gt;Dilarang spam&lt;/b&gt;\n"
            "2. &lt;i&gt;Sopan dan santun&lt;/i&gt;\n"
            "3. &lt;u&gt;No 18+ content&lt;/u&gt;</code>\n\n"
            "<i>💡 Rules akan otomatis terhapus setelah 10 detik!</i>\n"
            "<i>🔒 Sistem anti spam 20 menit seperti jadwal!</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="back")]])
        )
        context.user_data['waiting_input'] = 'set_rules'
    
    elif data == "preview_rules":
        if jadwal_data.get("rules_text"):
            await query.edit_message_text(
                f"<b>👀 PREVIEW RULES</b>\n\n"
                f"<i>Ini yang akan tampil saat user ketik /rules:</i>\n\n"
                f"<blockquote >{format_rules_message()}</blockquote>\n\n"
                f"<i>💡 Rules akan otomatis terhapus setelah 10 detik!</i>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="back")]])
            )
        else:
            await query.edit_message_text(
                "<b>📜 PREVIEW RULES</b>\n\n"
                "❌ <b>Rules belum diset!</b>\n\n"
                "Klik 'Set Rules' untuk mengatur rules group.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📜 Set Rules", callback_data="set_rules")],
                    [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                ])
            )
    
    elif data == "manage_channels":
        if jadwal_data["channels"]:
            keyboard = []
            for i, channel in enumerate(jadwal_data["channels"]):
                keyboard.append([InlineKeyboardButton(f"❌ {channel}", callback_data=f"del_ch_{i}")])
            
            keyboard.append([InlineKeyboardButton("➕ Tambah Channel/Group", callback_data="add_channel")])
            keyboard.append([InlineKeyboardButton("◀️ Kembali", callback_data="back")])
            
            await query.edit_message_text(
                f"<b>📺 KELOLA CHANNEL/GROUP ({len(jadwal_data['channels'])})</b>\n\n"
                f"<b>✅ Terdaftar:</b>\n" + 
                "\n".join([f"  {i+1}. <code>{ch}</code>" for i, ch in enumerate(jadwal_data["channels"])]) +
                f"\n\n<i>💡 Auto post akan bergiliran ke semua channel/group setiap 1 menit!</i>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                "<b>📺 KELOLA CHANNEL/GROUP</b>\n\n"
                "<b>❌ Belum ada channel/group terdaftar</b>\n\n"
                "<i>💡 Tambahkan channel/group untuk auto posting bergiliran!</i>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Tambah Channel/Group", callback_data="add_channel")],
                    [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                ])
            )
    
    elif data == "add_channel":
        await query.edit_message_text(
            "<b>📺 TAMBAH CHANNEL/GROUP UNTUK AUTO POST</b>\n\n"
            "Kirim <b>Chat ID</b> channel atau group:\n\n"
            "<b>Format:</b> <code>-1001234567890</code>\n\n"
            "<b>🔍 Cara mendapatkan Chat ID:</b>\n"
            "1️⃣ Forward pesan dari channel ke @userinfobot\n"
            "2️⃣ Atau add @MissRose_bot ke channel → ketik /id\n"
            "3️⃣ Salin angka yang dimulai dengan -100\n\n"
            "<b>⚠️ Support channel DAN group!</b>\n"
            "• Bot harus jadi admin di channel/group\n"
            "• Bot harus punya permission 'Send Messages'\n\n"
            "<b>🔄 Auto Post Bergiliran:</b>\n"
            "• Jam 20:00 → Post ke channel/group pertama\n"
            "• Jam 20:01 → Post ke channel/group kedua\n"
            "• Jam 20:02 → Post ke channel/group ketiga\n"
            "• Dan seterusnya setiap 1 menit!\n\n",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="manage_channels")]])
        )
        context.user_data['waiting_input'] = 'add_channel'
    
    elif data.startswith("del_ch_"):
        try:
            idx = int(data.replace("del_ch_", ""))
            if 0 <= idx < len(jadwal_data["channels"]):
                deleted_channel = jadwal_data["channels"].pop(idx)
                save_data()
                await query.answer(f"✅ {deleted_channel} dihapus!")
            else:
                await query.answer("❌ Channel tidak ditemukan!")
        except Exception as e:
            logger.error(f"Delete channel error: {e}")
            await query.answer("❌ Error menghapus!")
        
        # Kembali ke manage channels
        if jadwal_data["channels"]:
            keyboard = []
            for i, channel in enumerate(jadwal_data["channels"]):
                keyboard.append([InlineKeyboardButton(f"❌ {channel}", callback_data=f"del_ch_{i}")])
            
            keyboard.append([InlineKeyboardButton("➕ Tambah Channel/Group", callback_data="add_channel")])
            keyboard.append([InlineKeyboardButton("◀️ Kembali", callback_data="back")])
            
            await query.edit_message_text(
                f"<b>📺 KELOLA CHANNEL/GROUP ({len(jadwal_data['channels'])})</b>\n\n"
                f"<b>✅ Terdaftar:</b>\n" + 
                "\n".join([f"  {i+1}. <code>{ch}</code>" for i, ch in enumerate(jadwal_data["channels"])]) +
                f"\n\n<i>💡 Auto post akan bergiliran ke semua channel/group setiap 1 menit!</i>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                "<b>📺 KELOLA CHANNEL/GROUP</b>\n\n"
                "<b>❌ Belum ada channel/group terdaftar</b>\n\n"
                "<i>💡 Tambahkan channel/group untuk auto posting bergiliran!</i>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Tambah Channel/Group", callback_data="add_channel")],
                    [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                ])
            )
    
    elif data == "setup_telegraph":
        if jadwal_data.get("telegraph_token"):
            # Sudah ada token, tampilkan status
            telegraph_info = jadwal_data.get("telegraph_url", "Belum ada halaman")
            await query.edit_message_text(
                "<b>📰 STATUS TELEGRAPH</b>\n\n"
                f"🔑 <b>Token:</b> Tersedia ✅\n"
                f"📄 <b>Halaman:</b> <a href='{telegraph_info}'>Lihat</a>\n\n"
                "<i>Silahkan pilih tombol di bawah ini:</i>",
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Update Manual", callback_data="update_telegraph")],
                    [InlineKeyboardButton("🆕 Buat Token Baru", callback_data="create_telegraph")],
                    [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                ])
            )
        else:
            # Belum ada token
            await query.edit_message_text(
                "<b>📰 SETUP TELEGRAPH</b>\n\n"
                "Telegraph diperlukan untuk halaman 'Jadwal Donghua Semua Hari'\n\n"
                "<b>✨ Fitur Telegraph:</b>\n"
                "• Link di footer jadwal\n"
                "• Auto update saat tambah jadwal\n"
                "• Format seperti contoh yang diminta\n\n"
                "Klik tombol di bawah untuk membuat akun Telegraph otomatis:",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🆕 Buat Akun Telegraph", callback_data="create_telegraph")],
                    [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                ])
            )
    
    elif data == "create_telegraph":
        await query.edit_message_text(
            "<b>📰 MEMBUAT AKUN TELEGRAPH...</b>\n\n"
            "<i>⏳ Sedang membuat akun dan halaman...</i>",
            parse_mode='HTML'
        )
        
        # Buat akun Telegraph
        token = create_telegraph_account()
        if token:
            jadwal_data["telegraph_token"] = token
            
            # Buat halaman pertama
            if update_telegraph():
                save_data()
                await query.edit_message_text(
                    f"<b>✅ TELEGRAPH BERHASIL DIBUAT!</b>\n\n"
                    f"🔑 <b>Token:</b> Tersimpan ✅\n"
                    f"📄 <b>Halaman:</b> <a href='{jadwal_data['telegraph_url']}'>Lihat Telegraph</a>\n\n"
                    f"<i>💡 Sekarang link 'Jadwal Donghua Semua Hari' akan mengarah ke Telegraph!</i>",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                    ])
                )
            else:
                await query.edit_message_text(
                    "<b>⚠️ TELEGRAPH TOKEN DIBUAT, TAPI HALAMAN GAGAL!</b>\n\n"
                    "Token tersimpan, coba update manual:",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Coba Update", callback_data="update_telegraph")],
                        [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                    ])
                )
        else:
            await query.edit_message_text(
                "<b>❌ GAGAL MEMBUAT AKUN TELEGRAPH!</b>\n\n"
                "Kemungkinan masalah:\n"
                "• Koneksi internet\n"
                "• Telegraph server down\n\n"
                "Silakan coba lagi nanti.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="create_telegraph")],
                    [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                ])
            )
    
    elif data == "update_telegraph":
        if not jadwal_data.get("telegraph_token"):
            await query.answer("❌ Token Telegraph belum ada!")
            return
        
        await query.edit_message_text(
            "<b>📰 MENGUPDATE TELEGRAPH...</b>\n\n"
            "<i>⏳ Sedang memperbarui halaman...</i>",
            parse_mode='HTML'
        )
        
        if update_telegraph():
            await query.edit_message_text(
                f"<b>✅ TELEGRAPH BERHASIL DIUPDATE!</b>\n\n"
                f"📄 <b>Halaman:</b> <a href='{jadwal_data['telegraph_url']}'>Lihat Telegraph</a>\n"
                f"⏰ <b>Update:</b> {datetime.now(WIB).strftime('%H:%M WIB')}\n\n"
                f"<i>💡 Semua jadwal terbaru sudah masuk Telegraph!</i>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                ])
            )
        else:
            await query.edit_message_text(
                "<b>❌ GAGAL UPDATE TELEGRAPH!</b>\n\n"
                "Kemungkinan:\n"
                "• Token tidak valid\n"
                "• Koneksi bermasalah\n"
                "• Telegraph server error\n\n"
                "Coba buat token baru:",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🆕 Buat Token Baru", callback_data="create_telegraph")],
                    [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                ])
            )
    
    elif data == "set_time":
        await query.edit_message_text(
            "<b>⏰ SET JAM AUTO POST BERGILIRAN</b>\n\n"
            f"Jam sekarang: <b>{jadwal_data['post_time']} WIB</b>\n\n"
            "Kirim jam posting otomatis dengan format <b>HH:MM</b>\n\n"
            "<b>Contoh:</b> <code>06:00</code> atau <code>18:30</code>\n\n"
            "<b>🔄 Cara Kerja Bergiliran:</b>\n"
            "• Jam 06:00 → Channel/Group 1 posting\n"
            "• Jam 06:01 → Channel/Group 2 posting\n"
            "• Jam 06:02 → Channel/Group 3 posting\n"
            "• Dan seterusnya setiap 1 menit!\n\n"
            "<i>🌏 Menggunakan timezone WIB (UTC+7)</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="back")]])
        )
        context.user_data['waiting_input'] = 'time'
    
    elif data == "toggle_auto":
        jadwal_data["auto_post_enabled"] = not jadwal_data["auto_post_enabled"]
        save_data()
        
        if jadwal_data["auto_post_enabled"]:
            # Enable jobs dengan timezone WIB
            if jadwal_data["channels"]:
                try:
                    hour, minute = map(int, jadwal_data["post_time"].split(":"))
                    # Schedule job untuk setiap channel dengan interval 1 menit
                    for i, channel in enumerate(jadwal_data["channels"]):
                        post_minute = (minute + i) % 60
                        post_hour = hour + (minute + i) // 60
                        if post_hour >= 24:
                            post_hour = post_hour % 24
                        
                        wib_time = time(post_hour, post_minute, tzinfo=WIB)
                        context.job_queue.run_daily(
                            scheduled_daily_post,
                            time=wib_time,
                            name=f'daily_auto_post_{i}',
                            data={'channel': channel, 'index': i}
                        )
                    
                    status_msg = f"✅ <b>AUTO POST DIAKTIFKAN!</b>\n\n📊 <b>Schedule Bergiliran:</b>\n"
                    for i, channel in enumerate(jadwal_data["channels"]):
                        post_minute = (minute + i) % 60
                        post_hour = hour + (minute + i) // 60
                        if post_hour >= 24:
                            post_hour = post_hour % 24
                        status_msg += f"  • {channel}: {cached_format_time(post_hour, post_minute)} WIB\n"
                    
                except Exception as e:
                    logger.error(f"Enable auto post error: {e}")
                    status_msg = "⚠️ <b>AUTO POST AKTIF</b>\nTapi ada error scheduling!"
            else:
                status_msg = "⚠️ <b>AUTO POST AKTIF</b>\nTapi belum ada channel terdaftar!"
        else:
            # Disable semua jobs
            for i in range(10):  # Max 10 channels untuk clean up
                current_jobs = context.job_queue.get_jobs_by_name(f'daily_auto_post_{i}')
                for job in current_jobs:
                    job.schedule_removal()
            
            status_msg = "🔴 <b>AUTO POST DINONAKTIFKAN!</b>\n\nBot tidak akan posting otomatis."
        
        await query.edit_message_text(
            status_msg + "\n\n<i>💡 Status disimpan otomatis!</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="back")]])
        )
    
    elif data == "tambah":
        await query.edit_message_text(
            "<b>➕ TAMBAH JADWAL DONGHUA</b>\n\n"
            "<b>Format Jadwal Harian:</b>\n"
            "<code>Judul Anime|Hari</code>\n\n"
            "<b>Format Upcoming:</b>\n"
            "<code>Judul|Hari|Tanggal|Link</code>\n"
            "<code>Judul|Hari|Tanggal|Link|Season</code>\n\n"
            "<b>📝 Contoh:</b>\n"
            "• <code>Purple River Season 2|Senin</code>\n"
            "• <code>The King Avatar|Minggu|25 Desember|https://link.com|3</code>\n\n"
            "<b>📅 Hari yang valid:</b>\n"
            "Senin, Selasa, Rabu, Kamis, Jumat, Sabtu, Minggu\n\n"
            "<i>💡 Jadwal harian akan muncul setiap hari sesuai hari yang dipilih!</i>\n"
            "<i>🔮 Upcoming akan muncul di blockquote hijau seperti contoh!</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="back")]])
        )
        context.user_data['waiting_input'] = 'tambah'
    
    elif data == "preview":
        msg = format_jadwal_hari_ini()
        try:
            await query.edit_message_text(
                f"<b>📢 PREVIEW HARI INI</b>\n\n"
                f"<i>Ini yang akan dipost otomatis:</i>\n\n"
                f"<blockquote><b>{msg}</b></blockquote>",
                parse_mode='HTML',
                disable_web_page_preview=True,  # TAMBAHKAN INI
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Send Now ke Semua", callback_data="send_now")],
                    [InlineKeyboardButton("◀️ Kembali", callback_data="back")]
                ])
            )
        except Exception as e:
            logger.error(f"Preview error: {e}")
            await query.edit_message_text(
                "<b>❌ Error Preview</b>\n\nGagal generate preview jadwal.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="back")]])
            )
    
    elif data == "send_now":
        if not jadwal_data["channels"]:
            await query.answer("❌ Belum ada channel terdaftar!")
            return
        
        await query.edit_message_text(
            "<b>🚀 MENGIRIM KE SEMUA CHANNEL/GROUP...</b>\n\n"
            f"📊 <b>Target:</b> {len(jadwal_data['channels'])} channel/group\n"
            "<i>⏳ Sedang mengirim bergiliran...</i>",
            parse_mode='HTML'
        )
        
        success_count = 0
        error_count = 0
        
        try:
            # Update Telegraph dulu
            if jadwal_data.get("telegraph_token"):
                update_telegraph()
            
            message = format_jadwal_hari_ini()
            
            # Kirim ke semua channel bergiliran dengan delay 1 menit
            for i, channel in enumerate(jadwal_data["channels"]):
                try:
                    if i > 0:  # Delay untuk channel kedua dan seterusnya
                        await asyncio.sleep(60)  # 1 menit delay
                    
                    await context.bot.send_message(
                        chat_id=channel,
                        text=message,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                    success_count += 1
                    
                    # Update progress
                    if i < len(jadwal_data["channels"]) - 1:
                        await query.edit_message_text(
                            f"<b>🚀 MENGIRIM BERGILIRAN...</b>\n\n"
                            f"✅ <b>Berhasil:</b> {success_count}\n"
                            f"❌ <b>Gagal:</b> {error_count}\n"
                            f"⏳ <b>Progress:</b> {i+1}/{len(jadwal_data['channels'])}\n\n"
                            f"<i>⏰ Menunggu 1 menit untuk channel berikutnya...</i>",
                            parse_mode='HTML'
                        )
                    
                except Exception as e:
                    logger.error(f"Send to {channel} error: {e}")
                    error_count += 1
            
            # Final result
            telegraph_info = " + Telegraph updated" if jadwal_data.get("telegraph_token") else ""
            
            await query.edit_message_text(
                f"<b>🎯 SEND NOW SELESAI!</b>\n\n"
                f"✅ <b>Berhasil:</b> {success_count}\n"
                f"❌ <b>Gagal:</b> {error_count}\n"
                f"📊 <b>Total:</b> {len(jadwal_data['channels'])} channel/group\n"
                f"⏰ <b>Waktu:</b> {datetime.now(WIB).strftime('%H:%M WIB')}\n"
                f"🎨 <b>Format:</b> Sama seperti foto contoh{telegraph_info}\n\n"
                f"<i>🔄 Dikirim bergiliran dengan interval 1 menit!</i>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="back")]])
            )
            
        except Exception as e:
            logger.error(f"Send now error: {e}")
            await query.answer(f"❌ Gagal kirim: {str(e)}")
        
    elif data == "hapus":
        keyboard = []
        
        # List jadwal harian
        for hari in ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]:
            if jadwal_data["harian"][hari]:
                for anime in jadwal_data["harian"][hari]:
                    short_name = anime[:20] if len(anime) > 20 else anime
                    keyboard.append([InlineKeyboardButton(
                        f"❌ {short_name} ({hari})", 
                        callback_data=f"del_h_{hari}_{hash(anime) % 1000}"
                    )])
        
        # List upcoming
        for i, up in enumerate(jadwal_data["upcoming"]):
            short_name = up['judul'][:20] if len(up['judul']) > 20 else up['judul']
            keyboard.append([InlineKeyboardButton(
                f"❌ {short_name} (Upcoming)", 
                callback_data=f"del_u_{i}"
            )])
        
        if not keyboard:
            keyboard.append([InlineKeyboardButton("📝 Belum ada jadwal", callback_data="back")])
            
        keyboard.append([InlineKeyboardButton("◀️ Kembali", callback_data="back")])
        
        await query.edit_message_text(
            "<b>🗑️ HAPUS JADWAL</b>\n\n"
            "<i>Pilih jadwal yang ingin dihapus:</i>\n"
            "<i>📰 Telegraph akan otomatis terupdate setelah dihapus!</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "lihat":
        msg = "<b>📋 SEMUA JADWAL DONGHUA</b>\n\n"
        
        total_harian = 0
        for hari in ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]:
            emoji_hari = {"Senin":"📅","Selasa":"📅","Rabu":"📅","Kamis":"📅","Jumat":"📅","Sabtu":"🎉","Minggu":"🎉"}
            msg += f"<b>{emoji_hari.get(hari,'📅')} {hari}:</b>\n"
            
            if jadwal_data["harian"][hari]:
                for i, anime in enumerate(jadwal_data["harian"][hari], 1):
                    msg += f"   {i}. {anime}\n"
                total_harian += len(jadwal_data["harian"][hari])
            else:
                msg += "   <i>- Jadwal belum di isi</i>\n"
            msg += "\n"
        
        msg += f"<b>🔮 Upcoming Donghua ({len(jadwal_data['upcoming'])}):</b>\n"
        if jadwal_data["upcoming"]:
            for i, up in enumerate(jadwal_data["upcoming"], 1):
                season_text = f"[Season {up.get('season')}]" if up.get('season') else ""
                msg += f"   {i}. <b>{up['judul']}</b>{season_text}\n"
                msg += f"      📅 {up['hari']}, {up['tanggal']}\n"
        else:
            msg += "   <i>- Belum ada upcoming</i>\n"
            
        msg += f"\n<b>📊 TOTAL: {total_harian} jadwal harian</b>"
        
        # Tambah info Telegraph
        if jadwal_data.get("telegraph_url"):
            msg += f"\n📰 <b>Telegraph:</b> <a href='{jadwal_data['telegraph_url']}'>Lihat</a>"
        
        await query.edit_message_text(
            msg,
            parse_mode='HTML',
            disable_web_page_preview= True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="back")]])
        )
            
    elif data == "back":
        await panel_refresh(query, context)
        
    elif data.startswith("del_h_"):
        parts = data.replace("del_h_", "").split("_")
        if len(parts) >= 2:
            hari = parts[0]
            target_hash = int(parts[1])
            
            original_list = jadwal_data["harian"][hari][:]
            for anime in original_list:
                if hash(anime) % 1000 == target_hash:
                    jadwal_data["harian"][hari].remove(anime)
                    save_data()
                    # Update Telegraph setelah hapus
                    if jadwal_data.get("telegraph_token"):
                        update_telegraph()
                    await query.answer(f"✅ {anime} dihapus dari {hari}!")
                    break
            else:
                await query.answer("❌ Jadwal tidak ditemukan!")
        
        await panel_refresh(query, context)
        
    elif data.startswith("del_u_"):
        try:
            idx = int(data.replace("del_u_", ""))
            if 0 <= idx < len(jadwal_data["upcoming"]):
                deleted_item = jadwal_data["upcoming"].pop(idx)
                save_data()
                await query.answer(f"✅ {deleted_item['judul']} dihapus!")
            else:
                await query.answer("❌ Item tidak ditemukan!")
        except Exception as e:
            logger.error(f"Delete upcoming error: {e}")
            await query.answer("❌ Error menghapus!")
            
        await panel_refresh(query, context)

async def panel_refresh(query, context):
    """Refresh panel dengan info terbaru"""
    channels_info = f"{len(jadwal_data['channels'])} channel/group" if jadwal_data["channels"] else "❌ Belum diset"
    time_info = jadwal_data["post_time"]
    auto_status = "🟢 AKTIF" if jadwal_data["auto_post_enabled"] else "🔴 NONAKTIF"
    telegraph_status = "🟢 AKTIF" if jadwal_data.get("telegraph_token") else "🔴 NONAKTIF"
    rules_status = "🟢 SUDAH DISET" if jadwal_data.get("rules_text") else "🔴 BELUM DISET"
    
    today = get_today()
    jadwal_hari_ini = len(jadwal_data["harian"][today])
    total_minggu = sum(len(jadwal_data["harian"][hari]) for hari in jadwal_data["harian"])
    
    keyboard = [
        [InlineKeyboardButton("➕ Tambah Jadwal", callback_data="tambah"),
         InlineKeyboardButton("🗑️ Hapus Jadwal", callback_data="hapus")],
        [InlineKeyboardButton("📋 Lihat Semua", callback_data="lihat"),
         InlineKeyboardButton("📢 Preview Hari Ini", callback_data="preview")],
        [InlineKeyboardButton("📺 Kelola Channel", callback_data="manage_channels"),
         InlineKeyboardButton("⏰ Set Jam Post", callback_data="set_time")],
        [InlineKeyboardButton("📰 Setup Telegraph", callback_data="setup_telegraph"),
         InlineKeyboardButton("🚀 Toggle Auto Post", callback_data="toggle_auto")],
        [InlineKeyboardButton("📜 Set Rules", callback_data="set_rules"),
         InlineKeyboardButton("👀 Preview Rules", callback_data="preview_rules")]
    ]
    
    next_post = "Tidak ada" if not jadwal_data["auto_post_enabled"] else f"Bergiliran setiap hari jam {jadwal_data['post_time']}"
    
    msg = f"""<b>🎬 PANEL ADMIN JADWAL DONGHUA</b>

<b>📊 Status Sistem:</b>
📅 Hari ini: <b>{today}</b>
📝 Jadwal hari ini: <b>{jadwal_hari_ini} anime</b>
📈 Total minggu ini: <b>{total_minggu} anime</b>
📺 Channel/Group: <b>{channels_info}</b>
⏰ Jam auto post: <b>{time_info} WIB</b>
🤖 Status: <b>{auto_status}</b>
📰 Telegraph: <b>{telegraph_status}</b>
📜 Rules: <b>{rules_status}</b>
⏭️ Posting: <b>{next_post}</b>"""
    
    try:
        await query.edit_message_text(
            msg,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Panel refresh error: {e}")

# =================== TEXT INPUT HANDLER ===================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
        
    waiting_for = context.user_data.get('waiting_input')
    if not waiting_for:
        return
    
    text = update.message.text.strip()
    
    if waiting_for == 'set_rules':
        if not text:
            await update.message.reply_text("❌ Rules tidak boleh kosong!")
            return
        
        # Simpan rules dengan support HTML
        jadwal_data["rules_text"] = text
        save_data()
        
        await update.message.reply_text(
            f"✅ <b>Rules Berhasil Diset!</b>\n\n"
            f"<b>📜 Preview Rules:</b>\n"
            f"<blockquote>{format_rules_message()}</blockquote>\n\n"
            f"<b>✨ Fitur Rules:</b>\n"
            f"• Command: <code>/rules</code>\n"
            f"• Anti spam: 20 menit\n"
            f"• Auto delete: 10 detik\n"
            f"• Support HTML tags\n\n"
            f"<i>💡 User sekarang bisa ketik /rules untuk melihat rules!</i>",
            parse_mode='HTML'
        )
    
    elif waiting_for == 'tambah':
        if "|" not in text:
            await update.message.reply_text(
                "❌ <b>Format Salah!</b>\n\n"
                "Harus menggunakan separator <b>|</b>\n\n"
                "Contoh:\n<code>Purple River Season 2|Senin</code>", 
                parse_mode='HTML'
            )
            return
        
        parts = [p.strip() for p in text.split("|")]
        
        if len(parts) == 2:  # Jadwal harian
            judul, hari = parts
            
            if not judul:
                await update.message.reply_text("❌ Judul anime tidak boleh kosong!")
                return
                
            if hari not in ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]:
                await update.message.reply_text("❌ Hari tidak valid! Gunakan: Senin, Selasa, Rabu, Kamis, Jumat, Sabtu, Minggu")
                return
            
            if judul in jadwal_data["harian"][hari]:
                await update.message.reply_text(f"⚠️ <b>{judul}</b> sudah ada di hari {hari}!", parse_mode='HTML')
                return
                
            jadwal_data["harian"][hari].append(judul)
            save_data()
            
            # Update Telegraph otomatis setelah tambah jadwal
            telegraph_updated = ""
            if jadwal_data.get("telegraph_token"):
                if update_telegraph():
                    telegraph_updated = "\n📰 <b>Telegraph:</b> Otomatis terupdate ✅"
                else:
                    telegraph_updated = "\n📰 <b>Telegraph:</b> Gagal update ❌"
            
            await update.message.reply_text(
                f"✅ <b>Jadwal Harian Berhasil Ditambah!</b>\n\n"
                f"📝 <b>Anime:</b> {judul}\n"
                f"📅 <b>Hari:</b> {hari}{telegraph_updated}\n\n"
                f"<i>💡 Akan muncul di jadwal harian dengan format seperti foto!</i>", 
                parse_mode='HTML'
            )
                
        elif len(parts) in [4, 5]:  # Upcoming (dengan atau tanpa season)
            if len(parts) == 4:
                judul, hari, tanggal, link = parts
                season = None
            else:  # len(parts) == 5
                judul, hari, tanggal, link, season = parts
            
            if not all([judul, hari, tanggal, link]):
                await update.message.reply_text("❌ Judul, hari, tanggal, dan link harus diisi!")
                return
                
            if hari not in ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]:
                await update.message.reply_text("❌ Hari tidak valid!")
                return
                
            if not link.startswith(("http://", "https://")):
                await update.message.reply_text("❌ Link harus dimulai dengan http:// atau https://")
                return
            
            if any(up["judul"] == judul for up in jadwal_data["upcoming"]):
                await update.message.reply_text(f"⚠️ <b>{judul}</b> sudah ada di upcoming!", parse_mode='HTML')
                return
            
            upcoming_item = {
                "judul": judul,
                "hari": hari, 
                "tanggal": tanggal,
                "link": link
            }
            
            if season:
                upcoming_item["season"] = season
            
            jadwal_data["upcoming"].append(upcoming_item)
            save_data()
            
            season_text = f"\n📺 <b>Season:</b> {season}" if season else ""
            
            await update.message.reply_text(
                f"✅ <b>Upcoming Berhasil Ditambah!</b>\n\n"
                f"📝 <b>Anime:</b> {judul}{season_text}\n"
                f"📅 <b>Rilis:</b> {hari}, {tanggal}\n"
                f"🔗 <b>Preview:</b> <a href='{link}'>Link</a>\n\n"
                f"<i>💡 Akan muncul di blockquote hijau seperti foto contoh!</i>", 
                parse_mode='HTML'
            )
            
        else:
            await update.message.reply_text(
                "❌ <b>Format Salah!</b>\n\n"
                "<b>Untuk jadwal harian:</b>\n"
                "<code>Judul|Hari</code>\n\n"
                "<b>Untuk upcoming:</b>\n"
                "<code>Judul|Hari|Tanggal|Link</code>\n"
                "<code>Judul|Hari|Tanggal|Link|Season</code> (dengan season)",
                parse_mode='HTML'
            )
    
    elif waiting_for == 'add_channel':
        # Support channel dan group
        if not (text.startswith('-') and len(text) > 5):
            await update.message.reply_text(
                "❌ <b>Format Chat ID Salah!</b>\n\n"
                "Chat ID channel/group harus:\n"
                "• Dimulai dengan tanda <b>-</b>\n"
                "• Berupa angka panjang\n"
                "• Contoh: <code>-1001234567890</code>\n\n"
                "<b>Support channel DAN group!</b>",
                parse_mode='HTML'
            )
            return
            
        if text in jadwal_data["channels"]:
            await update.message.reply_text(
                f"⚠️ <b>Channel/Group Sudah Terdaftar!</b>\n\n"
                f"📺 <b>Chat ID:</b> <code>{text}</code>\n\n"
                f"<i>💡 Channel/Group ini sudah ada dalam daftar auto posting bergiliran!</i>", 
                parse_mode='HTML'
            )
            return
            
        try:
            test_msg = await asyncio.wait_for(
                context.bot.send_message(text, "🔧 <i>Testing access...</i>", parse_mode='HTML'),
                timeout=15
            )
            await test_msg.delete()
            
            jadwal_data["channels"].append(text)
            save_data()
            
            await update.message.reply_text(
                f"✅ <b>Channel/Group Berhasil Ditambah!</b>\n\n"
                f"📺 <b>Chat ID:</b> <code>{text}</code>\n"
                f"🔗 <b>Status:</b> Terhubung\n"
                f"📊 <b>Total Channel/Group:</b> {len(jadwal_data['channels'])}\n\n"
                f"<b>🔄 Urutan Auto Posting Bergiliran:</b>\n"
                + "\n".join([f"  {i+1}. <code>{ch}</code> → +{i} menit" for i, ch in enumerate(jadwal_data["channels"])]) +
                f"\n\n<i>💡 Bot siap posting bergiliran format seperti foto contoh!</i>", 
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Channel test error: {e}")
            error_msg = str(e).lower()
            if "chat not found" in error_msg:
                await update.message.reply_text(
                    "❌ <b>Channel/Group Tidak Ditemukan!</b>\n\n"
                    "Pastikan Chat ID benar dan bot pernah di-add",
                    parse_mode='HTML'
                )
            elif "not enough rights" in error_msg:
                await update.message.reply_text(
                    "❌ <b>Permission Denied!</b>\n\n"
                    "Bot belum jadi admin atau tidak punya izin posting",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(f"❌ Error: {str(e)}", parse_mode='HTML')
    
    elif waiting_for == 'time':
        if not (":" in text and len(text) == 5):
            await update.message.reply_text(
                "❌ <b>Format Jam Salah!</b>\n\n"
                "Harus format <b>HH:MM</b>\n\n"
                "Contoh: <code>06:00</code> atau <code>18:15</code>",
                parse_mode='HTML'
            )
            return
            
        try:
            hour, minute = map(int, text.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                await update.message.reply_text("❌ Jam/menit tidak valid!", parse_mode='HTML')
                return
            
            old_time = jadwal_data["post_time"]
            jadwal_data["post_time"] = text
            save_data()
            
            # Update job schedule jika auto post aktif dengan timezone WIB
            if jadwal_data["auto_post_enabled"]:
                # Remove old jobs
                for i in range(len(jadwal_data.get("channels", []))):
                    current_jobs = context.job_queue.get_jobs_by_name(f'daily_auto_post_{i}')
                    for job in current_jobs:
                        job.schedule_removal()
                
                # Create new jobs with new time
                for i, channel in enumerate(jadwal_data["channels"]):
                    post_minute = (minute + i) % 60
                    post_hour = hour + (minute + i) // 60
                    if post_hour >= 24:
                        post_hour = post_hour % 24
                    
                    wib_time = time(post_hour, post_minute, tzinfo=WIB)
                    context.job_queue.run_daily(
                        scheduled_daily_post,
                        time=wib_time,
                        name=f'daily_auto_post_{i}',
                        data={'channel': channel, 'index': i}
                    )
            
            await update.message.reply_text(
                f"✅ <b>Jam Auto Post Berhasil Diupdate!</b>\n\n"
                f"⏰ <b>Jam lama:</b> {old_time} WIB\n"
                f"⏰ <b>Jam baru:</b> {text} WIB\n\n"
                f"<b>🔄 Jadwal Posting Bergiliran:</b>\n"
                + (("\n".join([f"  • Channel/Group {i+1}: {cached_format_time(hour + (minute + i) // 60, (minute + i) % 60)} WIB" for i in range(len(jadwal_data["channels"]))])) if jadwal_data["channels"] else "  Belum ada channel/group terdaftar") +
                f"\n\n<i>💡 Bot akan posting otomatis bergiliran sesuai jam yang sudah diset!</i>\n"
                f"<i>🌏 Menggunakan timezone WIB (UTC+7)</i>", 
                parse_mode='HTML'
            )
            
        except ValueError:
            await update.message.reply_text("❌ Format jam salah! Harus angka HH:MM")
        except Exception as e:
            logger.error(f"Time setting error: {e}")
            await update.message.reply_text("❌ Error setting time!")
    
    # Reset waiting state
    context.user_data['waiting_input'] = None

# =================== SCHEDULED DAILY POST ===================
async def scheduled_daily_post(context: ContextTypes.DEFAULT_TYPE):
    """Job harian bergiliran - kirim dengan format seperti foto contoh dengan timezone WIB yang benar"""
    if not jadwal_data["auto_post_enabled"] or not jadwal_data["channels"]:
        return
    
    # Get channel info from job data
    job_data = context.job.data
    if not job_data:
        return
        
    target_channel = job_data.get('channel')
    channel_index = job_data.get('index', 0)
    
    if not target_channel:
        return
    
    try:
        # Gunakan WIB timezone untuk mendapatkan hari yang benar
        now_wib = datetime.now(WIB)
        today = get_today()
        today_schedule = jadwal_data["harian"][today]
        
        # Update Telegraph sebelum posting (hanya untuk channel pertama)
        if channel_index == 0 and jadwal_data.get("telegraph_token"):
            update_telegraph()
        
        # Post dengan format persis seperti foto
        message = format_jadwal_hari_ini()
        
        await context.bot.send_message(
            chat_id=target_channel,
            text=message,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        
        # Notifikasi ke owner (hanya untuk channel pertama untuk menghindari spam)
        if channel_index == 0:
            try:
                status = f"{len(today_schedule)} anime" if today_schedule else "Libur hari ini"
                telegraph_info = " + Telegraph updated" if jadwal_data.get("telegraph_token") else ""
                
                await context.bot.send_message(
                    OWNER_ID,
                    f"✅ <b>Auto Post Bergiliran Berhasil!</b>\n\n"
                    f"📅 <b>Hari:</b> {today}\n"
                    f"📝 <b>Jadwal:</b> {status}\n"
                    f"⏰ <b>Waktu Mulai:</b> {now_wib.strftime('%H:%M WIB')}\n"
                    f"🎨 <b>Format:</b> contoh{telegraph_info}\n"
                    f"📊 <b>Target:</b> {len(jadwal_data['channels'])} channel/group bergiliran\n"
                    f"🔄 <b>Interval:</b> 1 menit per channel/group",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Owner notification error: {e}")
            
    except Exception as e:
        logger.error(f"Scheduled post error for {target_channel}: {e}")
        # Hanya kirim notifikasi error untuk channel pertama
        if channel_index == 0:
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"❌ <b>Auto Post GAGAL!</b>\n\n"
                    f"⏰ <b>Waktu:</b> {datetime.now(WIB).strftime('%H:%M WIB')}\n"
                    f"📺 <b>Target:</b> <code>{target_channel}</code>\n"
                    f"🐛 <b>Error:</b> <code>{str(e)[:150]}</code>",
                    parse_mode='HTML'
                )
            except Exception as notif_error:
                logger.error(f"Error notification failed: {notif_error}")

# =================== SIGNAL HANDLER UNTUK GRACEFUL SHUTDOWN ===================
async def shutdown_handler(signum, loop):
    """Handle shutdown signals gracefully"""
    print(f"\n📴 Received signal {signum}. Shutting down gracefully...")
    
    # Cleanup tasks
    tasks = [task for task in asyncio.all_tasks(loop) if task is not asyncio.current_task()]
    
    if tasks:
        print(f"🔄 Cancelling {len(tasks)} outstanding tasks...")
        for task in tasks:
            task.cancel()
        
        # Wait for tasks to complete with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), 
                timeout=5.0
            )
        except asyncio.TimeoutError:
            print("⚠️ Some tasks did not complete in time")
    
    # Stop the application properly
    if app and app.running:
        print("🛑 Stopping application...")
        try:
            await app.stop()
            await app.shutdown()
        except Exception as e:
            logger.error(f"Error during app shutdown: {e}")
    
    print("✅ Bot stopped gracefully")
    loop.stop()

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    print(f"\n📴 Received signal {signum}. Initiating graceful shutdown...")
    if app and app.running:
        asyncio.create_task(shutdown_handler(signum, asyncio.get_event_loop()))
    else:
        sys.exit(0)

# =================== MAIN FUNCTION ===================
def main():
    global app
    
    # Kill existing bot instances to prevent conflicts
    print("🔍 Checking for existing bot instances...")
    kill_existing_bots()
    
    load_data()
    
    # Create custom request with proper timeout settings
    request = HTTPXRequest(
        connection_pool_size=1,
        read_timeout=30.0,
        write_timeout=30.0,
        connect_timeout=30.0,
        pool_timeout=30.0
    )
    
    # Konfigurasi Application dengan request object yang diperbaiki
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    
    # Add handlers
    app.add_handler(CommandHandler("jadwal", jadwal_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Setup jobs dengan timezone WIB yang benar
    if jadwal_data["auto_post_enabled"] and jadwal_data["channels"]:
        try:
            hour, minute = map(int, jadwal_data["post_time"].split(":"))
            # Schedule job untuk setiap channel dengan interval 1 menit
            for i, channel in enumerate(jadwal_data["channels"]):
                post_minute = (minute + i) % 60
                post_hour = hour + (minute + i) // 60
                if post_hour >= 24:
                    post_hour = post_hour % 24
                
                wib_time = time(post_hour, post_minute, tzinfo=WIB)
                app.job_queue.run_daily(
                    scheduled_daily_post,
                    time=wib_time,
                    name=f'daily_auto_post_{i}',
                    data={'channel': channel, 'index': i}
                )
            
            print(f"⏰ Auto post jobs scheduled for {len(jadwal_data['channels'])} channels starting at {jadwal_data['post_time']} WIB")
            
        except Exception as e:
            logger.error(f"Job scheduling error: {e}")
            print(f"❌ Error scheduling jobs: {e}")
    
    print("🚀 Jadwal Donghua Bot is running...")
    print(f"📊 Loaded {sum(len(jadwal_data['harian'][d]) for d in jadwal_data['harian'])} harian + {len(jadwal_data['upcoming'])} upcoming")
    print(f"📺 {len(jadwal_data['channels'])} channels configured for auto posting")
    print(f"📜 Rules {'configured' if jadwal_data.get('rules_text') else 'not configured'}")
    print(f"⏰ Auto post: {'enabled' if jadwal_data['auto_post_enabled'] else 'disabled'}")
    print("📱 Commands available: /jadwal, /rules, /panel (owner only)")
    print("🔄 Press Ctrl+C to stop")
    
    try:
        # Run dengan polling sederhana tanpa signal handling yang rumit
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            close_loop=False,  # PENTING: Biarkan loop terbuka
            stop_signals=None  # Disable default signal handlers
        )
    except KeyboardInterrupt:
        print("\n📴 Shutting down...")
        try:
            app.stop()
        except:
            pass
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        print("🔚 Bot stopped")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        os._exit(0)  # Force exit tanpa cleanup yang rumit
