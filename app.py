from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import json, os, requests, hmac, hashlib
from dotenv import load_dotenv
from datetime import datetime
import logging

load_dotenv()

app = Flask(__name__)
app.secret_key = "smm_panel_secret"

USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"

# Coinbase env values
COINBASE_API_KEY = os.getenv("COINBASE_API_KEY")
COINBASE_WEBHOOK_SECRET = os.getenv("COINBASE_WEBHOOK_SECRET")
COINBASE_API_URL = "https://api.commerce.coinbase.com/charges"
COINBASE_HEADERS = {
    "Content-Type": "application/json",
    "X-CC-Api-Key": COINBASE_API_KEY,
    "X-CC-Version": "2018-03-22"
}

# Logok gyűjtése listába
logs = []

class ListHandler(logging.Handler):
    def emit(self, record):
        logs.append(self.format(record))

list_handler = ListHandler()
list_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
list_handler.setFormatter(formatter)

app.logger.addHandler(list_handler)
app.logger.setLevel(logging.DEBUG)

@app.context_processor
def inject_logs():
    return dict(logs=logs[-20:])  # utolsó 20 log

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

def load_orders():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_orders(orders):
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=4)

@app.route("/")
def main():
    return render_template("main.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        users = load_users()
        if username in users:
            return "Username already exists!"
        users[username] = {"password": password, "role": "user", "balance": 0}
        save_users(users)
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        users = load_users()
        if username in users and users[username]["password"] == password:
            session["username"] = username
            session["role"] = users[username]["role"]
            return redirect(url_for("dashboard"))
        return "Invalid credentials!"
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    users = load_users()
    user = users.get(session["username"], {})
    balance = float(user.get("balance", 0))

    active_services = 0
    try:
        response = requests.post("https://n1panel.com/api/v2", json={
            "key": "99e3b4020cb435a980441d72a0a7627b",
            "action": "services"
        })
        service_data = response.json()
        if isinstance(service_data, list):
            active_services = len(service_data)
    except Exception:
        active_services = 0

    orders = load_orders()
    user_orders = [o for o in orders if o.get("username") == session["username"]]
    total_orders = len(user_orders)

    return render_template("dashboard.html",
                           username=session["username"],
                           balance=balance,
                           active_services=active_services,
                           total_orders=total_orders)

@app.route("/services")
def services():
    if "username" not in session:
        return redirect(url_for("login"))

    api_key = '99e3b4020cb435a980441d72a0a7627b'
    url = 'https://n1panel.com/api/v2'
    payload = {
        "key": api_key,
        "action": "services"
    }

    try:
        response = requests.post(url, json=payload)
        data = response.json()
    except Exception:
        data = []

    categories = {
        'No Refill': [],
        '30d Refill': [],
        '60D Refill': [],
        '1Year Refill': []
    }

    for service in data:
        name = service.get("name", "").lower()
        if '1 year' in name or '365' in name:
            categories['1Year Refill'].append(service)
        elif '60' in name:
            categories['60D Refill'].append(service)
        elif '30' in name:
            categories['30d Refill'].append(service)
        else:
            categories['No Refill'].append(service)

    return render_template("services.html", categories=categories)

@app.route("/order")
def order():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("order.html")

@app.route("/support")
def support():
    if "username" not in session:
        return redirect(url_for("login"))
    discord_link = "https://discord.gg/Gu7SkkVKbk"
    return render_template("support.html", discord_link=discord_link)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main"))

@app.route("/topup", methods=["GET"])
def topup():
    if "username" not in session:
        return redirect(url_for("login"))
    users = load_users()
    balance = users.get(session["username"], {}).get("balance", 0)
    default_amount = "2.00"
    return render_template("topup.html", balance=balance, default_amount=default_amount)

@app.route("/create_charge", methods=["POST"])
def create_charge():
    if "username" not in session:
        return redirect(url_for("login"))

    amount = request.form.get("amount")
    currency = request.form.get("currency", "EUR").upper()
    payment_method = request.form.get("payment_method", "crypto")

    if not amount or not currency:
        return "Missing data", 400

    if payment_method == "paypal":
        discord_link = "https://discord.gg/Gu7SkkVKbk"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "message": "PayPal payment is only available through Discord. Please open a ticket for support.",
                "discord_link": discord_link
            })
        else:
            return f'PayPal payment is only available through Discord. <a href="{discord_link}" target="_blank">Open a ticket here</a>'

    dummy_addresses = {
        "BTC": "3Conja6xihViiaXaVMnQkiE7ymMYwBBgcg",
        "ETH": "0xcFF5215753A3F1efFBd0FDB8fFeCe60036E1F68C",
        "LTC": "MNTsQySNLf3pz1h9DyvDpFmkiNoGbv5m4Q",
        "BCH": "162jkxUMzz7n2kJa1LTP7tQwAwtMpHhVQ9",
        "USDC": "0xF5720F74406fFA36F513c8708d867046b8ab0B82"
    }

    address = dummy_addresses.get(currency, dummy_addresses["BTC"])

    payment_id = hashlib.sha256(f"{session['username']}{datetime.now().isoformat()}".encode()).hexdigest()[:16]

    app.logger.debug(f"Create charge: user={session['username']} amount={amount} currency={currency} address={address} payment_id={payment_id}")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({
            "address": address,
            "payment_id": payment_id,
            "amount": amount,
            "currency": currency
        })
    else:
        return f"Payment address: {address} (Amount: {amount} {currency})"

@app.route("/confirm_payment", methods=["POST"])
def confirm_payment():
    if "username" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.get_json()
    payment_id = data.get("payment_id")
    txid = data.get("txid")

    if not payment_id or not txid:
        return jsonify({"success": False, "error": "Missing payment_id or txid"}), 400

    users = load_users()
    username = session["username"]

    if username in users:
        users[username]["balance"] = users[username].get("balance", 0) + 2  # Demo hozzáadás
        save_users(users)

        app.logger.debug(f"Payment confirmed: user={username} txid={txid} payment_id={payment_id}")
        return jsonify({"success": True})

    return jsonify({"success": False, "error": "User not found"}), 404

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-CC-Webhook-Signature", "")
    payload = request.data

    computed_sig = hmac.new(
        COINBASE_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_sig, signature):
        app.logger.warning("Invalid webhook signature")
        return "Invalid signature", 400

    data = request.json

    if data.get("event", {}).get("type") == "charge:confirmed":
        charge = data.get("event", {}).get("data", {})
        metadata = charge.get("metadata", {})
        username = metadata.get("username")
        amount = float(charge.get("pricing", {}).get("local", {}).get("amount", 0))

        users = load_users()
        if username in users:
            users[username]["balance"] = users[username].get("balance", 0) + amount
            save_users(users)
            app.logger.info(f"Added {amount} EUR to user {username} via Coinbase")
    return "", 200

@app.route("/api/users")
def api_users():
    users = load_users()
    return jsonify(users)

@app.route("/api/orders", methods=["GET", "POST"])
def api_orders():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == "GET":
        orders = load_orders()
        user_orders = [o for o in orders if o.get("username") == session["username"]]
        return jsonify(user_orders)

    # POST - rendelés leadása
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid data"}), 400

    service_id = data.get("service_id")
    link = data.get("link")
    quantity = data.get("quantity")
    price = data.get("price")

    if not all([service_id, link, quantity, price]):
        return jsonify({"error": "Missing fields"}), 400

    users = load_users()
    username = session["username"]
    user = users.get(username)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # *** Fontos: Ellenőrzés, hogy elég-e az egyenleg ***
    if user.get("balance", 0) < float(price):
        return jsonify({"error": "Insufficient balance"}), 400

    # Ha van elég egyenleg, rögzítjük a rendelést és levonjuk a pénzt
    orders = load_orders()
    order = {
        "username": username,
        "service_id": service_id,
        "link": link,
        "quantity": quantity,
        "price": float(price),
        "timestamp": datetime.now().isoformat()
    }
    orders.append(order)
    save_orders(orders)

    user["balance"] -= float(price)
    save_users(users)

    return jsonify({"success": True, "order": order})

if __name__ == "__main__":
    app.run(debug=True)
