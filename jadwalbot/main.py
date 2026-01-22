import logging
import sys
import pytz
from datetime import time
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from .config import BOT_TOKEN
from .data_manager import load_data, jadwal_data
from .handlers import (
    jadwal_cmd,
    rules_cmd,
    panel_cmd,
    handle_callbacks,
    handle_media,
    handle_text,
    scheduled_daily_post,
)

# =================== SETUP ===================
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Timezone WIB
WIB = pytz.timezone('Asia/Jakarta')

# Global variable for application
app = None

# =================== MAIN FUNCTION ===================
def main():
    global app

    load_data()

    # Build aplikasi dengan pengaturan yang disederhanakan
    app = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("jadwal", jadwal_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.ANIMATION, handle_media))
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
    media_count = sum(1 for hari in jadwal_data["media_jadwal"] if jadwal_data["media_jadwal"][hari]["url"])
    print(f"🎨 Media {media_count}/7 days configured")
    print(f"⏰ Auto post: {'enabled' if jadwal_data['auto_post_enabled'] else 'disabled'}")
    print("📱 Commands available: /jadwal, /rules, /panel (owner only)")
    print("🎯 Group commands: /jadwal (auto-delete), /rules (auto-delete)")
    print("🔒 PM commands: Owner only")
    print("🔄 Press Ctrl+C to stop")

    try:
        # Run dengan polling yang disederhanakan
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\n📴 Shutting down...")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        print("🔚 Bot stopped")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Critical error: {e}")
        sys.exit(1)
