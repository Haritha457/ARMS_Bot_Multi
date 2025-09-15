import requests
from bs4 import BeautifulSoup
import time
import os
from flask import Flask
from threading import Thread

# Load from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
USERNAME = os.getenv("ARMS_USERNAME")
PASSWORD = os.getenv("ARMS_PASSWORD")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_MSG_URL = f"{TELEGRAM_URL}/sendMessage"

# State - Changed to support multiple courses
monitoring_enabled = False
current_courses = []  # Changed from current_course to list
last_update_id = None
course_just_found = False

# Slot Map
slot_map = {
    'G': '7',
    'H': '8',
    'M': '13',
    'N': '14',
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

# Handle /start, /stop and course input
def check_for_commands():
    global monitoring_enabled, current_courses, last_update_id, course_just_found
    
    try:
        url = f"{TELEGRAM_URL}/getUpdates?timeout=5"
        if last_update_id is not None:
            url += f"&offset={last_update_id + 1}"
        
        resp = requests.get(url).json()
        updates = resp.get("result", [])
        
        for update in updates:
            msg = update.get("message", {})
            text = msg.get("text", "").strip()
            chat_id = msg.get("chat", {}).get("id")
            update_id = update["update_id"]
            
            if str(chat_id) != CHAT_ID:
                continue
                
            last_update_id = update_id
            
            if text.lower() == "/start":
                monitoring_enabled = True
                current_courses = []  # Reset to empty list
                course_just_found = False
                send_telegram("🤖 Monitoring started. Please enter course codes (e.g. ECA20,EEE20,CSA20):")
            
            elif text.lower() == "/stop":
                monitoring_enabled = False
                current_courses = []  # Reset to empty list
                course_just_found = False
                send_telegram("🛑 Monitoring stopped.")
            
            elif monitoring_enabled and not current_courses:  # Accept courses when list is empty
                # Parse multiple courses from input (comma-separated)
                courses = [x.strip().upper() for x in text.replace('\n', ',').split(",") if x.strip()]
                current_courses = courses
                course_just_found = False
                send_telegram(f"📌 Monitoring courses: {', '.join(current_courses)}")
                
    except Exception as e:
        send_telegram(f"⚠️ Error reading Telegram: {e}")

# Main course checking logic - Modified to check multiple courses
def check_courses_in_slots():
    session = requests.Session()
    login_url = "https://arms.sse.saveetha.com/"
    enrollment_url = "https://arms.sse.saveetha.com/StudentPortal/Enrollment.aspx"
    api_base = "https://arms.sse.saveetha.com/Handler/Student.ashx?Page=StudentInfobyId&Mode=GetCourseBySlot&Id="
    
    try:
        # Login
        resp = session.get(login_url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        payload = {
            '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'}).get('value'),
            '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'}).get('value'),
            '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'}).get('value'),
            'txtusername': USERNAME,
            'txtpassword': PASSWORD,
            'btnlogin': 'Login'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': login_url
        }
        
        login_resp = session.post(login_url, data=payload, headers=headers)
        
        if "Logout" not in login_resp.text:
            send_telegram("❌ Login failed.")
            return []
        
        enroll_resp = session.get(enrollment_url)
        if "Enrollment" not in enroll_resp.text:
            send_telegram("❌ Enrollment page failed.")
            return []
        
        found_courses = []
        
        # Check each slot for all courses
        for slot_name, slot_id in slot_map.items():
            if not monitoring_enabled:
                return []
                
            api_url = api_base + slot_id
            response = session.get(api_url)
            
            if response.status_code == 200:
                # Check each course in current slot
                for course_code in current_courses[:]:  # Use slice to avoid modification during iteration
                    if course_code in response.text:
                        send_telegram(f"🔄 Checking course: {course_code}\n🎯 Found in Slot {slot_name}!")
                        found_courses.append(course_code)
        
        # Send status for courses not found
        remaining_courses = [c for c in current_courses if c not in found_courses]
        if remaining_courses:
            send_telegram(f"🔄 Checking courses: {', '.join(remaining_courses)}\n❌ Not found in any slot.")
        
        return found_courses
        
    except Exception as e:
        send_telegram(f"❌ Error during check: {e}")
        return []

# Uptime keep-alive for Railway
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is alive!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# Start
keep_alive()
send_telegram("🤖 Bot is running. Send /start to begin monitoring.")

# 🔁 MAIN LOOP - Same timing logic, modified for multiple courses
while True:
    try:
        check_for_commands()
        
        if monitoring_enabled and current_courses:
            # Record start time for precise interval
            cycle_start_time = time.time()
            
            found_courses = check_courses_in_slots()
            
            # Remove found courses from monitoring list
            for course in found_courses:
                if course in current_courses:
                    current_courses.remove(course)
                    send_telegram(f"✅ Monitoring complete for {course}.")
            
            # If all courses found, stop monitoring
            if not current_courses:
                send_telegram("✅ All courses found. Please send new courses or /stop.")
                course_just_found = True
                continue
            
            # Wait for exactly 3 minutes from start of cycle, checking commands every 3 seconds
            next_check_time = cycle_start_time + 180  # 3 minutes = 180 seconds
            
            while time.time() < next_check_time:
                if not monitoring_enabled or course_just_found:
                    course_just_found = False
                    break
                    
                check_for_commands()
                
                # Sleep for 3 seconds, but don't exceed next check time
                remaining_time = next_check_time - time.time()
                sleep_time = min(3, remaining_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)
        else:
            time.sleep(5)
            
    except Exception as e:
        send_telegram(f"⚠️ Bot error: {str(e)[:100]}. Continuing...")
        time.sleep(10)