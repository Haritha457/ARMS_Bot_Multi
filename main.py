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

# State - Multiple courses with vacancy and progress updates
monitoring_enabled = False
course_list = []  # List of courses to monitor
last_update_id = None
found_courses = set()

# Slot Map
slot_map = {
    'O': '15', 'P': '16', 'Q': '17', 'R': '18', 'S': '19', 'T': '20'
}

# Send Telegram Message
def send_telegram(text):
    try:
        requests.post(SEND_MSG_URL, data={"chat_id": CHAT_ID, "text": text})
    except:
        pass

# Extract vacancy count for a course in slot data
def get_course_vacancy(slot_data, course_code):
    if course_code not in slot_data:
        return False, 0
    idx = slot_data.find(course_code)
    snippet = slot_data[idx:idx+500]
    m = re.search(r'<span class="badge[^"]*">(\d+)</span>', snippet)
    if m:
        return True, int(m.group(1))
    return True, 0

# Handle commands
def check_for_commands():
    global monitoring_enabled, course_list, last_update_id, found_courses
    try:
        url = f"{TELEGRAM_URL}/getUpdates?timeout=5"
        if last_update_id: url += f"&offset={last_update_id+1}"
        resp = requests.get(url).json()
        for u in resp.get("result",[]):
            msg = u.get("message",{})
            text = msg.get("text","").strip()
            cid = msg.get("chat",{}).get("id")
            uid = u.get("update_id")
            if str(cid)!=CHAT_ID: continue
            last_update_id = uid
            parts = text.split()
            cmd = parts[0].lower()
            arg = parts[1].upper() if len(parts)>1 else None
            if cmd=="/start":
                monitoring_enabled=True; course_list=[]; found_courses=set()
                send_telegram("🤖 Monitoring started!\nCommands:\n/add [COURSE]\n/remove [COURSE]\n/list\n/clear\n/status\n/stop\n✨ vacancy >0 only, with progress updates.")
            elif cmd=="/stop":
                monitoring_enabled=False; course_list=[]; found_courses=set()
                send_telegram("🛑 Monitoring stopped and cleared.")
            elif cmd=="/add" and arg:
                if monitoring_enabled and arg not in course_list:
                    course_list.append(arg)
                    send_telegram(f"✅ Added {arg} ({len(course_list)} total)")
                else:
                    send_telegram("⚠️ Provide /start first or course exists.")
            elif cmd=="/remove" and arg:
                if arg in course_list:
                    course_list.remove(arg); found_courses.discard(arg)
                    send_telegram(f"❌ Removed {arg} ({len(course_list)} left)")
                else: send_telegram("⚠️ Course not in list.")
            elif cmd=="/list":
                send_telegram("📋 Monitoring: " + (", ".join(course_list) if course_list else "none"))
            elif cmd=="/clear":
                course_list=[]; found_courses=set(); send_telegram("🧹 Cleared list.")
            elif cmd=="/status":
                send_telegram(f"📊 monitor={'on' if monitoring_enabled else 'off'}, {len(course_list)} courses.")
            elif monitoring_enabled and not cmd.startswith("/") and text.isalnum():
                if text.upper() not in course_list:
                    course_list.append(text.upper())
                    send_telegram(f"✅ Added {text.upper()} ({len(course_list)} total)")
    except: pass

# Check courses
def check_multiple_courses_in_slots():
    session=requests.Session()
    base="https://arms.sse.saveetha.com/Handler/Student.ashx?Page=StudentInfobyId&Mode=GetCourseBySlot&Id="
    # login
    r=session.get("https://arms.sse.saveetha.com/")
    s=BeautifulSoup(r.text,'html.parser')
    payload={
        '__VIEWSTATE':s.find('input',{'name':'__VIEWSTATE'}).get('value'),
        '__VIEWSTATEGENERATOR':s.find('input',{'name':'__VIEWSTATEGENERATOR'}).get('value'),
        '__EVENTVALIDATION':s.find('input',{'name':'__EVENTVALIDATION'}).get('value'),
        'txtusername':USERNAME,'txtpassword':PASSWORD,'btnlogin':'Login'
    }
    session.post("https://arms.sse.saveetha.com/",data=payload)
    session.get("https://arms.sse.saveetha.com/StudentPortal/Enrollment.aspx")
    found=[]; details={}
    # progress update
    send_telegram(f"🔍 Scanning {len(course_list)} courses: {', '.join(course_list)}")
    for slot, sid in slot_map.items():
        send_telegram(f"🔎 Checking Slot {slot}...")
        data=session.get(base+sid).text
        for c in course_list:
            if c in found: continue
            f,v=get_course_vacancy(data,c)
            if f and v>0:
                found.append(c); details[c]=(slot,v)
    # notify
    if found:
        for c in found:
            sl,v=details[c]
            send_telegram(f"🎯 AVAILABLE: {c} has {v} seats in Slot {sl}!")
        summ=", ".join([f"{c}({details[c][1]}@{details[c][0]})" for c in found])
        send_telegram(f"✅ Found {len(found)} available: {summ}")
    else:
        send_telegram(f"❌ No vacancies found for {', '.join(course_list)}")
    return found

# Flask keep-alive
app=Flask('')
@app.route('/')
def home(): return "✅ Bot alive"
def run(): app.run(host='0.0.0.0',port=8080)
def keep_alive(): Thread(target=run).start()

# Start
keep_alive(); send_telegram("🤖 Bot running! Send /start.")
while True:
    check_for_commands()
    if monitoring_enabled and course_list:
        start=time.time(); found=check_multiple_courses_in_slots()
        nextt=start+900
        while time.time()<nextt:
            check_for_commands(); time.sleep(min(3,nextt-time.time()))
    else:
        time.sleep(5)