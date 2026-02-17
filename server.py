from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "CHANGE_ME_TO_SOMETHING_RANDOM"

# -------------------- DB --------------------
def get_db():
    return sqlite3.connect("app.db")

def init_db(): #definira se baza podataka
    db = get_db()
    c = db.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    """)
    # izrada baze podataka users
    # korisničko ime mora postojati, ne smije biti isto koje već postoji, 
    # id je jednistveni označivač korisnika koji mora biti različit od svakog korisnika pojedinačno, te se povećava svakim unosom novog korisnika, zaporka se hešira te se mora unijeti
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        user_id INTEGER PRIMARY KEY,
        unit TEXT NOT NULL,                 -- 'cm' or 'in'
        background TEXT NOT NULL,           -- e.g. '#111111'
        green_limit REAL NOT NULL,          -- threshold (cm)
        yellow_limit REAL NOT NULL,         -- threshold (cm)
        red_limit REAL NOT NULL,            -- threshold (cm) -> below this = "very near"
        blink_far_ms INTEGER NOT NULL,
        blink_mid_ms INTEGER NOT NULL,
        blink_near_ms INTEGER NOT NULL,
        blink_very_near_ms INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
# izrada baze podataka settings
    
    db.commit()
    db.close()

init_db()

# -------------------- SENSOR DATA --------------------
sensor_data = {"SENSOR_1": None, "SENSOR_2": None}

def require_login():
    return "user_id" in session #provjerava postoji li taj ključ unutar session objekta i vraća True ili False, bez greške

def create_default_settings(user_id: int):
    db = get_db()
    c = db.cursor()
    c.execute("""
    INSERT OR REPLACE INTO settings
    (user_id, unit, background, green_limit, yellow_limit, red_limit,
     blink_far_ms, blink_mid_ms, blink_near_ms, blink_very_near_ms)
    VALUES (?, 'cm', '#111111', 50, 20, 10, 1000, 600, 300, 150)
    """, (user_id,))# postojećem korisniku se postavljene vrijednosti, a novom se stavljaju zadane vrijednosti
    db.commit()
    db.close()

def get_user_settings(user_id: int):
    db = get_db()
    c = db.cursor()
    c.execute("""
    SELECT unit, background, green_limit, yellow_limit, red_limit,
           blink_far_ms, blink_mid_ms, blink_near_ms, blink_very_near_ms
    FROM settings WHERE user_id=?
    """, (user_id,))
    row = c.fetchone()
    db.close()
    if not row:
        create_default_settings(user_id)
        return get_user_settings(user_id)

    keys = ["unit","background","green","yellow","red","blink_far_ms","blink_mid_ms","blink_near_ms","blink_very_near_ms"]
    return dict(zip(keys, row)) #spaja svako ime ključa s odgovarajućom vrijednošću iz baze. praktično jer se taj rječnik može direktno poslati kao JSON web sučelju

def update_user_settings(user_id: int, s: dict):
    db = get_db()
    c = db.cursor()
    c.execute("""
    UPDATE settings SET
      unit=?,
      background=?,
      green_limit=?,
      yellow_limit=?,
      red_limit=?,
      blink_far_ms=?,
      blink_mid_ms=?,
      blink_near_ms=?,
      blink_very_near_ms=?
    WHERE user_id=?
    """, (
        s["unit"],
        s["background"],
        float(s["green"]),
        float(s["yellow"]),# prevođenjem JSON poruke, osigurava se da je ta vrijednost broj a ne string u bazi podataka tako što se pretvori u float
        float(s["red"]),
        int(s["blink_far_ms"]),
        int(s["blink_mid_ms"]),
        int(s["blink_near_ms"]),
        int(s["blink_very_near_ms"]),
        user_id
    ))
    db.commit()
    db.close()

# -------------------- AUTH --------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if not username or not password:
        return render_template("register.html", error="Upiši korisničko ime i lozinku.")

    db = get_db()
    c = db.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                  (username, generate_password_hash(password))) #(password, method="pbkdf2:sha256")
        user_id = c.lastrowid
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return render_template("register.html", error="Korisničko ime već postoji.")
    db.close()

    create_default_settings(user_id)
    session["user_id"] = user_id
    session["username"] = username
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    db = get_db()
    c = db.cursor() #Cursor služi za izvršavanje SQL naredbi nad bazom podataka
    c.execute("SELECT id, password_hash FROM users WHERE username=?", (username,))
    row = c.fetchone()
    db.close()

    if not row or not check_password_hash(row[1], password):
        return render_template("login.html", error="Pogrešno korisničko ime ili lozinka.")

    session["user_id"] = row[0]
    session["username"] = username
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -------------------- PAGES --------------------
@app.route("/")
def root():
    return redirect(url_for("dashboard") if require_login() else url_for("login"))

@app.route("/dashboard")
def dashboard():
    if not require_login():
        return redirect(url_for("login"))
    return render_template("dashboard.html", username=session.get("username", ""))

# -------------------- API --------------------
@app.route("/data", methods=["POST"])
def receive_data():
    # ESP32 šalje bez logina
    data = request.get_json(silent=True) or {}
    sid = data.get("sensor_id")
    dist = data.get("distance")

    if sid in sensor_data: #provjerava se koji senzor šalje podatke, sid = sensor id
        try:
            sensor_data[sid] = float(dist)
        except:
            pass
    return jsonify({"status": "ok"})

@app.route("/status")
def status():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401 #služi za zaštitu rute /status da netko tko nije prijavljen ne može dohvaćati podatke senzora
    return jsonify(sensor_data)

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401

    user_id = session["user_id"]

    if request.method == "POST":
        s = request.get_json(silent=True) or {}#osigurava da, ako get_json() vrati None (npr. nije poslan JSON ili je neispravan),
        # varijabla data postane prazan rječnik umjesto None, čime se sprječava rušenje programa pri daljnjem pristupu podacima.
        # minimalna validacija
        required = ["unit","background","green","yellow","red",
                    "blink_far_ms","blink_mid_ms","blink_near_ms","blink_very_near_ms"]
        for k in required:
            if k not in s:
                return jsonify({"error": f"missing {k}"}), 400
        if s["unit"] not in ["cm","in"]:
            return jsonify({"error": "unit must be cm or in"}), 400
        update_user_settings(user_id, s)
        return jsonify({"status": "saved"})

    return jsonify(get_user_settings(user_id))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
