import requests
from bs4 import BeautifulSoup
import time
import os
import re
from flask import Flask
from threading import Thread

# Load from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
USERNAME = os.getenv("ARMS_USERNAME")
PASSWORD = os.getenv("ARMS_PASSWORD")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_MSG_URL = f"{TELEGRAM_URL}/sendMessage"

# State
monitoring_enabled = False
course_list = []  # Multi-course list
last_update_id = None

# Slot Map
tt={ 'O':'15','P':'16','Q':'17','R':'18','S':'19','T':'20' }

# Send Telegram Message
def send_telegram(text):
    try:
        requests.post(SEND_MSG_URL, data={"chat_id": CHAT_ID, "text": text})
    except:
        pass

# Vacancy extraction using BeautifulSoup
def get_vacancy(html, course):
    soup = BeautifulSoup(html, "html.parser")
    for td in soup.find_all("td"):
        lbl = td.find("label")
        if lbl and course in lbl.get_text():
            span = td.find("span", class_="badge")
            if span and span.text.isdigit():
                return int(span.text)
            return 0
    return -1  # not found

# Handle commands
def check_for_commands():
    global monitoring_enabled, course_list, last_update_id
    try:
        url = f"{TELEGRAM_URL}/getUpdates?timeout=5"
        if last_update_id is not None:
            url += f"&offset={last_update_id+1}"
        updates = requests.get(url).json().get("result", [])
        for u in updates:
            msg = u.get("message",{})
            text = msg.get("text","").strip()
            uid = u["update_id"]
            cid = msg.get("chat",{}).get("id")
            if str(cid)!=CHAT_ID: continue
            last_update_id = uid
            cmd = text.lower()
            if cmd=="/start":
                monitoring_enabled=True
                course_list=[]
                send_telegram("🤖 Monitoring started. Enter courses (comma or space separated):")
            elif cmd=="/stop":
                monitoring_enabled=False
                course_list=[]
                send_telegram("🛑 Monitoring stopped.")
            elif cmd=="/list":
                send_telegram("📋 Monitoring courses: " + (", ".join(course_list) if course_list else "none"))
            elif monitoring_enabled:
                # parse courses
                parts = re.split(r"[ ,]+", text)
                courses = [p.upper() for p in parts if p]
                course_list = courses
                send_telegram(f"📌 Monitoring courses: {', '.join(course_list)}")
    except:
        pass

# Check all courses in slots
def check_courses():
    session = requests.Session()
    # login
    login_url = "https://arms.sse.saveetha.com/"
    r = session.get(login_url)
    soup = BeautifulSoup(r.text,'html.parser')
    payload = {
        '__VIEWSTATE': soup.find('input',{'name':'__VIEWSTATE'}).get('value'),
        '__VIEWSTATEGENERATOR': soup.find('input',{'name':'__VIEWSTATEGENERATOR'}).get('value'),
        '__EVENTVALIDATION': soup.find('input',{'name':'__EVENTVALIDATION'}).get('value'),
        'txtusername':USERNAME,'txtpassword':PASSWORD,'btnlogin':'Login'
    }
    session.post(login_url,data=payload)
    session.get("https://arms.sse.saveetha.com/StudentPortal/Enrollment.aspx")
    # progress
    send_telegram(f"🔍 Scanning {len(course_list)} courses: {', '.join(course_list)}")
    found_any=False
    for slot, sid in tt.items():
        send_telegram(f"🔎 Checking Slot {slot}...")
        data = session.get(f"https://arms.sse.saveetha.com/Handler/Student.ashx?Page=StudentInfobyId&Mode=GetCourseBySlot&Id={sid}").text
        for c in course_list:
            vac = get_vacancy(data,c)
            if vac>0:
                send_telegram(f"🎯 AVAILABLE: {c} has {vac} seats in Slot {slot}!")
                found_any=True
    if not found_any:
        send_telegram(f"❌ No vacancies found for {', '.join(course_list)}")

# Keep-alive
app=Flask('')
@app.route('/')
def home(): return "✅ Bot alive"
def run(): app.run(host='0.0.0.0',port=8080)
Thread(target=run,daemon=True).start()

send_telegram("🤖 Bot is running. Send /start to begin.")
while True:
    check_for_commands()
    if monitoring_enabled and course_list:
        start=time.time()
        check_courses()
        # fixed 15-min
        nt = start+900
        while time.time()<nt:
            check_for_commands(); time.sleep(min(3,nt-time.time()))
    else:
        time.sleep(5)
