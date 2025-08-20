import os
import json
import datetime
import secrets
from flask import Flask, render_template, request, redirect, url_for, session, flash
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.secret_key = 'your-secret-key'

USERS_FILE = "users.json"

reset_tokens = {}

# Load users from file or create empty list
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# ---------------- Routes ----------------

@app.route("/")
def home():
    return redirect("/login")

@app.route("/check_id")
def check_id():
    userid = request.args.get("userid")
    users = load_users()
    exists = userid in users
    return {"exists": exists}

@app.route("/signup", methods=["GET", "POST"])
def signup():
    users = load_users()

    if request.method == "POST":
        user_id = request.form["id"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if user_id in users:
            return render_template("signup.html", error="이미 존재하는 아이디입니다.")

        if password != confirm_password:
            return render_template("signup.html", error="비밀번호가 일치하지 않습니다.")

        # Store password as plain text
        users[user_id] = {
            "password": password,  # plain text
            "email": request.form["email"],
            "age": request.form["age"],
            "education": request.form["education"],
            "address": request.form["address"],
            "phone": request.form["phone"],
            "work_experience": request.form["work_experience"],
            "certificate": request.form["certificate"],
            "role": "user"  # default role
        }

        save_users(users)
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    users = load_users()
    if request.method == 'POST' and 'id' in request.form and 'password' in request.form:
        user_id = request.form['id']
        password = request.form['password']
        user = users.get(user_id)

        if user and user['password'] == password:  # plain-text comparison
            session['user_id'] = user_id
            session['role'] = user.get('role', 'user')

            if session['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('register'))
        else:
            flash("아이디 또는 비밀번호가 틀렸습니다.", 'danger')

    return render_template('login.html')

from flask import jsonify

@app.route('/forgot', methods=['POST'])
def forgot():
    email = request.form.get('email')
    users = load_users()
    
    # Find user by email
    matched_users = [uid for uid, info in users.items() if info.get("email") == email]

    if not matched_users:
        return {"success": False, "message": "등록된 이메일이 없습니다."}
    
    # Use user_id as token
    user_id = matched_users[0]
    reset_link = url_for('reset_password', token=user_id, _external=True)

    return {"success": True, "message": "비밀번호 재설정 링크를 생성했습니다.", "reset_link": reset_link}

@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    users = load_users()

    # Treat token as user_id
    user_id = token
    if user_id not in users:
        return "Invalid token"

    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            return render_template('reset.html', token=token, error="비밀번호가 일치하지 않습니다.")

        # Update password
        users[user_id]['password'] = new_password
        save_users(users)
        return "비밀번호가 성공적으로 변경되었습니다! <a href='/login'>로그인</a>"

    return render_template('reset.html', token=token)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    if request.method == 'POST':
        return redirect(url_for('info', scrape=1))

    return render_template('register.html', user_id=user_id)

@app.route('/info')
def info():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    users = load_users()
    user_id = session['user_id']
    user = users.get(user_id)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    submission = {
        "ID": user_id,
        "제출시간": timestamp,
        "나이": user["age"],
        "학력": user["education"],
        "주소": user["address"],
        "전화번호": user["phone"],
        "경력": user["work_experience"],
        "자격증": user["certificate"]
    }

    if request.args.get('scrape') == '1':
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = user_id
            response = client.get('/info')

        soup = BeautifulSoup(response.data, 'html.parser')
        rows = soup.select('table tbody tr')
        scraped_info = {}
        for row in rows:
            cols = row.find_all('td')
            if len(cols) == 2:
                scraped_info[cols[0].get_text(strip=True)] = cols[1].get_text(strip=True)

        if not os.path.exists('scraped'):
            os.makedirs('scraped')
        filename = f"scraped/scraped_user_{user_id}_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(scraped_info, f, ensure_ascii=False, indent=2)

        combined_filename = "scraped/all_scraped.json"
        if os.path.exists(combined_filename):
            with open(combined_filename, 'r', encoding='utf-8') as f:
                combined_data = json.load(f)
        else:
            combined_data = []
        combined_data.append(scraped_info)
        with open(combined_filename, 'w', encoding='utf-8') as f:
            json.dump(combined_data, f, ensure_ascii=False, indent=2)

    return render_template('info.html', info=submission)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    # Load all scraped JSON submissions
    combined_filename = "scraped/all_scraped.json"
    if os.path.exists(combined_filename):
        with open(combined_filename, 'r', encoding='utf-8') as f:
            all_data = json.load(f)
    else:
        all_data = []

    return render_template('admin.html', submissions=all_data)

import csv
@app.route('/admin/export')
def export_csv():
    combined_filename = "scraped/all_scraped.json"
    if os.path.exists(combined_filename):
        with open(combined_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        csv_file = "scraped/all_scraped.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        return send_file(csv_file, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
