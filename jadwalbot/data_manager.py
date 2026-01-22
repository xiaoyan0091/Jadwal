import json
import logging

logger = logging.getLogger(__name__)

# Data storage
jadwal_data = {
    "harian": {"Senin":[],"Selasa":[],"Rabu":[],"Kamis":[],"Jumat":[],"Sabtu":[],"Minggu":[]},
    "upcoming": [],
    "channels": [],  # List channel/group untuk auto post bergiliran
    "post_time": "06:00",
    "auto_post_enabled": False,
    "telegraph_token": "",
    "telegraph_url": "",
    "rules_text": "",  # Rules text dengan support HTML
    "media_jadwal": {  # Media untuk setiap hari
        "Senin": {"type": "", "url": ""},
        "Selasa": {"type": "", "url": ""},
        "Rabu": {"type": "", "url": ""},
        "Kamis": {"type": "", "url": ""},
        "Jumat": {"type": "", "url": ""},
        "Sabtu": {"type": "", "url": ""},
        "Minggu": {"type": "", "url": ""}
    }
}

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
            # Migrate old foto/video to media_jadwal
            if "jadwal_foto" in jadwal_data or "jadwal_video" in jadwal_data:
                if not jadwal_data.get("media_jadwal"):
                    jadwal_data["media_jadwal"] = {
                        "Senin": {"type": "", "url": ""},
                        "Selasa": {"type": "", "url": ""},
                        "Rabu": {"type": "", "url": ""},
                        "Kamis": {"type": "", "url": ""},
                        "Jumat": {"type": "", "url": ""},
                        "Sabtu": {"type": "", "url": ""},
                        "Minggu": {"type": "", "url": ""}
                    }
                # Hapus old fields
                if "jadwal_foto" in jadwal_data:
                    del jadwal_data["jadwal_foto"]
                if "jadwal_video" in jadwal_data:
                    del jadwal_data["jadwal_video"]
                save_data()
            # Ensure all fields exist
            if "rules_text" not in jadwal_data:
                jadwal_data["rules_text"] = ""
            if "media_jadwal" not in jadwal_data:
                jadwal_data["media_jadwal"] = {
                    "Senin": {"type": "", "url": ""},
                    "Selasa": {"type": "", "url": ""},
                    "Rabu": {"type": "", "url": ""},
                    "Kamis": {"type": "", "url": ""},
                    "Jumat": {"type": "", "url": ""},
                    "Sabtu": {"type": "", "url": ""},
                    "Minggu": {"type": "", "url": ""}
                }
            save_data()
    except Exception as e:
        logger.error(f"Load data error: {e}")
        save_data()
