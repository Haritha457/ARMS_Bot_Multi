import requests
from bs4 import BeautifulSoup
import time
import os
import re
from flask import Flask
from threading import Thread

# Load from environment
BOT_TOKEN       = os.getenv("BOT_TOKEN")
CHAT_ID         = os.getenv("CHAT_ID")
USERNAME        = os.getenv("ARMS_USERNAME")
PASSWORD        = os.getenv("ARMS_PASSWORD")

TELEGRAM_URL    = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_MSG_URL    = f"{TELEGRAM_URL}/sendMessage"

# State
monitoring_enabled = False
current_course     = None
course_queue       = []    # Holds additional courses
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

# Extract vacancy count
def get_vacancy(html, course):
    soup = BeautifulSoup(html, "html.parser")
    for td in soup.find_all("td"):
        lbl = td.find("label")
        if lbl and course in lbl.get_text():
            span = td.find("span", class_="badge")
            if span and span.text.isdigit():
                return True, int(span.text)
            return True, 0
    return False, 0

# Handle commands
def check_for_commands():
    global monitoring_enabled, current_course, course_queue, last_update_id
    try:
        url = f"{TELEGRAM_URL}/getUpdates?timeout=5"
        if last_update_id is not None:
            url += f"&offset={last_update_id + 1}"
        updates = requests.get(url).json().get("result", [])
        for u in updates:
            msg  = u.get("message", {})
            text = msg.get("text", "").strip()
            cid  = msg.get("chat", {}).get("id")
            uid  = u.get("update_id")
            if str(cid) != CHAT_ID:
                continue
            last_update_id = uid

            if text.lower() == "/start":
                monitoring_enabled = True
                current_course     = None
                course_queue       = []
                send_telegram("🤖 Monitoring started. Enter one or more course codes separated by space or comma:")
            
            elif text.lower() == "/stop":
                monitoring_enabled = False
                current_course     = None
                course_queue       = []
                send_telegram("🛑 Monitoring stopped.")
            
            elif monitoring_enabled and not current_course and text:
                # Split input into multiple codes
                parts = re.split(r"[,\s]+", text.upper())
                if parts:
                    current_course = parts[0]
                    course_queue   = parts[1:]
                    send_telegram(f"📌 Monitoring course: {current_course}")

            elif text.lower() == "/list":
                lst = [current_course] + course_queue if current_course else course_queue
                send_telegram("📋 Queued courses: " + (", ".join(lst) if lst else "none"))

    except:
        pass

# Main course check logic
def check_course_in_slots(course_code):
    session   = requests.Session()
    login_url = "https://arms.sse.saveetha.com/"
    r         = session.get(login_url)
    soup      = BeautifulSoup(r.text, 'html.parser')
    payload   = {
        '__VIEWSTATE':         soup.find('input', {'name': '__VIEWSTATE'}).get('value'),
        '__VIEWSTATEGENERATOR':soup.find('input', {'name': '__VIEWSTATEGENERATOR'}).get('value'),
        '__EVENTVALIDATION':   soup.find('input', {'name': '__EVENTVALIDATION'}).get('value'),
        'txtusername':         USERNAME,
        'txtpassword':         PASSWORD,
        'btnlogin':            'Login'
    }
    session.post(login_url, data=payload)
    session.get("https://arms.sse.saveetha.com/StudentPortal/Enrollment.aspx")

    # Check each slot
    for slot, sid in slot_map.items():
        api_url = (
            f"https://arms.sse.saveetha.com/Handler/Student.ashx?"
            f"Page=StudentInfobyId&Mode=GetCourseBySlot&Id={sid}"
        )
        resp = session.get(api_url)
        if resp.status_code == 200:
            found, vac = get_vacancy(resp.text, course_code)
            if found and vac > 0:
                send_telegram(
                    f"🔄 Checking course: {course_code}\n"
                    f"🎯 Found in Slot {slot} with {vac} seats!"
                )
                return True
    send_telegram(
        f"🔄 Checking course: {course_code}\n"
        "❌ Not found in any slot or no seats available."
    )
    return False

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
    if monitoring_enabled and current_course:
        start = time.time()
        found = check_course_in_slots(current_course)
        # Advance to next course
        if course_queue:
            current_course = course_queue.pop(0)
            send_telegram(f"📌 Next course: {current_course}")
        else:
            current_course = None
        # Fixed 15-minute delay
        next_t = start + 900
        while time.time() < next_t:
            check_for_commands()
            time.sleep(min(3, next_t - time.time()))
    else:
        time.sleep(5)
