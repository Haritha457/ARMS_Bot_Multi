import requests
from bs4 import BeautifulSoup
import time
import os
import re
from flask import Flask
from threading import Thread

# Load from environment
BOT_TOKEN   = os.getenv("BOT_TOKEN")
CHAT_ID     = os.getenv("CHAT_ID")
USERNAME    = os.getenv("ARMS_USERNAME")
PASSWORD    = os.getenv("ARMS_PASSWORD")

TELEGRAM_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_MSG_URL  = f"{TELEGRAM_URL}/sendMessage"

# State
monitoring_enabled = False
course_list        = []   # Multi-course list
last_update_id     = None

# Slot Map
slot_map = {
    'O': '15',
    'P': '16',
    'Q': '17',
    'R': '18',
    'S': '19',
    'T': '20'
}

# Send Telegram Message
def send_telegram(text):
    try:
        requests.post(SEND_MSG_URL, data={"chat_id": CHAT_ID, "text": text})
    except:
        pass

# Extract vacancy count with fallback
def get_vacancy(html, course):
    # 1) Precise extraction via BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for td in soup.find_all("td"):
        lbl = td.find("label")
        if lbl and course in lbl.get_text():
            span = td.find("span", class_="badge")
            if span and span.text.isdigit():
                return True, int(span.text)
            return True, 0
    # 2) Fallback: detect presence anywhere
    if course in html:
        return True, 0
    return False, 0

# Handle /start, /stop, /list, and multi-course input
def check_for_commands():
    global monitoring_enabled, course_list, last_update_id
    try:
        url = f"{TELEGRAM_URL}/getUpdates?timeout=5"
        if last_update_id is not None:
            url += f"&offset={last_update_id+1}"
        updates = requests.get(url).json().get("result", [])
        for u in updates:
            msg  = u.get("message", {})
            text = msg.get("text", "").strip()
            cid  = msg.get("chat", {}).get("id")
            uid  = u["update_id"]
            if str(cid) != CHAT_ID:
                continue
            last_update_id = uid

            cmd = text.lower()
            if cmd == "/start":
                monitoring_enabled = True
                course_list = []
                send_telegram(
                    "🤖 Monitoring started.\n"
                    "Enter courses (comma or space separated):"
                )
            elif cmd == "/stop":
                monitoring_enabled = False
                course_list = []
                send_telegram("🛑 Monitoring stopped.")
            elif cmd == "/list":
                send_telegram(
                    "📋 Monitoring courses: " +
                    (", ".join(course_list) if course_list else "none")
                )
            elif monitoring_enabled:
                # Parse comma/space separated course codes
                parts = re.split(r"[,\s]+", text)
                parsed = [p.upper() for p in parts if p]
                if parsed:
                    course_list = parsed
                    send_telegram(
                        f"📌 Monitoring courses: {', '.join(course_list)}"
                    )
    except:
        pass

# Main multi-course vacancy check
def check_courses():
    session    = requests.Session()
    login_url  = "https://arms.sse.saveetha.com/"
    r          = session.get(login_url)
    soup       = BeautifulSoup(r.text, 'html.parser')
    payload    = {
        '__VIEWSTATE':         soup.find('input', {'name': '__VIEWSTATE'}).get('value'),
        '__VIEWSTATEGENERATOR':soup.find('input', {'name': '__VIEWSTATEGENERATOR'}).get('value'),
        '__EVENTVALIDATION':   soup.find('input', {'name': '__EVENTVALIDATION'}).get('value'),
        'txtusername':         USERNAME,
        'txtpassword':         PASSWORD,
        'btnlogin':            'Login'
    }
    session.post(login_url, data=payload)
    session.get("https://arms.sse.saveetha.com/StudentPortal/Enrollment.aspx")

    for course in course_list:
        found = False
        vac   = 0
        for slot, sid in slot_map.items():
            api_url = (
                f"https://arms.sse.saveetha.com/Handler/Student.ashx?"
                f"Page=StudentInfobyId&Mode=GetCourseBySlot&Id={sid}"
            )
            resp = session.get(api_url)
            if resp.status_code == 200:
                ok, count = get_vacancy(resp.text, course)
                if ok and count > 0:
                    send_telegram(
                        f"🔄 Checking course: {course}\n"
                        f"🎯 Found in Slot {slot} with {count} seats!"
                    )
                    found = True
                    break
        if not found:
            send_telegram(
                f"🔄 Checking course: {course}\n"
                f"❌ Not found in any slot or no seats available."
            )

# Keep-alive for deployment
app = Flask('')
@app.route('/')
def home():
    return "✅ Bot is alive!"
def run():
    app.run(host='0.0.0.0', port=8080)
Thread(target=run, daemon=True).start()

# Startup
send_telegram("🤖 Bot is running. Send /start to begin monitoring.")
while True:
    check_for_commands()
    if monitoring_enabled and course_list:
        start = time.time()
        check_courses()
        # Fixed 15-minute interval
        next_t = start + 900
        while time.time() < next_t:
            check_for_commands()
            time.sleep(min(3, next_t - time.time()))
    else:
        time.sleep(5)
