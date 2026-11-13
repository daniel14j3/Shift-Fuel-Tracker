import os
import sqlite3
from flask import Flask, render_template, request, jsonify
from google import genai

app = Flask(__name__)
DB_PATH = "shifts.db"

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_date TEXT NOT NULL,
                hours REAL NOT NULL,
                gross_pay REAL NOT NULL,
                km_driven REAL NOT NULL,
                fuel_cost REAL NOT NULL
            )
        """)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/shifts", methods=["GET"])
def get_shifts():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM shifts ORDER BY shift_date DESC, id DESC").fetchall()
        shifts = []
        for r in rows:
            net = round(r["gross_pay"] - r["fuel_cost"], 2)
            hourly = round(net / r["hours"], 2) if r["hours"] > 0 else 0
            shifts.append({**dict(r), "net_pay": net, "net_hourly": hourly})
    return jsonify(shifts)


@app.route("/api/shifts", methods=["POST"])
def add_shift():
    data = request.get_json(silent=True) or {}
    try:
        shift_date = str(data["shift_date"]).strip()
        hours = float(data["hours"])
        gross_pay = float(data["gross_pay"])
        km_driven = float(data["km_driven"])
        fuel_cost = float(data["fuel_cost"])
        if not shift_date or hours <= 0 or gross_pay < 0 or km_driven < 0 or fuel_cost < 0:
            raise ValueError("Invalid numeric values.")
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Please provide valid positive numbers for all fields."}), 400

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO shifts (shift_date, hours, gross_pay, km_driven, fuel_cost) VALUES (?, ?, ?, ?, ?)",
            (shift_date, hours, gross_pay, km_driven, fuel_cost),
        )
    return jsonify({"status": "saved"}), 201


@app.route("/api/analyze", methods=["GET"])
def analyze_shifts():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM shifts").fetchall()

    if not rows:
        return jsonify({"insight": "Log at least one shift to generate efficiency insights."})

    total_net = sum(r["gross_pay"] - r["fuel_cost"] for r in rows)
    total_hours = sum(r["hours"] for r in rows)
    total_km = sum(r["km_driven"] for r in rows)
    avg_hourly = round(total_net / total_hours, 2) if total_hours else 0

    summary_text = (
        f"Total shifts: {len(rows)}, Total hours: {total_hours:.1f}h, "
        f"Total distance: {total_km:.1f}km, Net earnings: €{total_net:.2f} (€{avg_hourly}/hr)."
    )

    if client:
        try:
            prompt = (
                "You are a concise fleet & gig-work efficiency assistant. "
                "Give 2 short, practical bullet points analyzing this driver's shift stats:\n"
                f"{summary_text}"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return jsonify({"source": "ai", "insight": response.text.strip()})
        except Exception:
            pass

    return jsonify({
        "source": "local",
        "insight": f"{summary_text} Keep tracking fuel-to-km ratio to spot high-traffic shifts."
    })


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
