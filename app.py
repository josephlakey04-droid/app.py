import os
import sqlite3
from datetime import datetime

from flask import Flask, g, redirect, render_template, request, url_for

app = Flask(__name__)
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal.db")


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    with sqlite3.connect(DB) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                entry_price REAL NOT NULL,
                size_usd REAL NOT NULL,
                stop_pct REAL NOT NULL,
                target_x REAL NOT NULL,
                notes TEXT DEFAULT '',
                opened_at TEXT NOT NULL,
                exit_price REAL,
                fees_usd REAL DEFAULT 0,
                pnl REAL,
                closed_at TEXT
            )"""
        )


def num(name, minimum=0.0):
    """Read a positive number from the form, or raise ValueError."""
    value = float(request.form.get(name, "").replace(",", "."))
    if value <= minimum:
        raise ValueError(name)
    return value


@app.template_filter("price")
def price(v):
    if v is None:
        return ""
    return f"{v:.10f}".rstrip("0").rstrip(".")


@app.template_filter("usd")
def usd(v):
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.2f}"


def get_stats(closed):
    wins = [t["pnl"] for t in closed if t["pnl"] > 0]
    losses = [t["pnl"] for t in closed if t["pnl"] <= 0]
    total = sum(t["pnl"] for t in closed)
    n = len(closed)
    return {
        "count": n,
        "win_rate": (len(wins) / n * 100) if n else 0,
        "avg_win": (sum(wins) / len(wins)) if wins else 0,
        "avg_loss": (sum(losses) / len(losses)) if losses else 0,
        "total": total,
        "expectancy": (total / n) if n else 0,
    }


@app.route("/")
def index():
    rows = db().execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    open_trades = [t for t in rows if t["exit_price"] is None]
    closed = [t for t in rows if t["exit_price"] is not None]
    return render_template(
        "index.html",
        open_trades=open_trades,
        closed=closed,
        stats=get_stats(closed),
        error=request.args.get("error"),
    )


@app.post("/trade")
def open_trade():
    token = request.form.get("token", "").strip()
    try:
        if not token:
            raise ValueError("token")
        values = (
            token,
            num("entry_price"),
            num("size_usd"),
            num("stop_pct"),
            num("target_x"),
            request.form.get("notes", "").strip(),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
    except ValueError as e:
        return redirect(url_for("index", error=f"Check the “{e}” field: it needs a value above zero."))
    db().execute(
        "INSERT INTO trades (token, entry_price, size_usd, stop_pct, target_x, notes, opened_at) "
        "VALUES (?,?,?,?,?,?,?)",
        values,
    )
    db().commit()
    return redirect(url_for("index"))


@app.post("/trade/<int:trade_id>/close")
def close_trade(trade_id):
    t = db().execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    if t is None:
        return redirect(url_for("index"))
    try:
        exit_price = num("exit_price")
        fees = float(request.form.get("fees_usd", "0").replace(",", ".") or 0)
        if fees < 0:
            raise ValueError("fees_usd")
    except ValueError as e:
        return redirect(url_for("index", error=f"Check the “{e}” field: enter a valid number."))
    pnl = t["size_usd"] * (exit_price / t["entry_price"] - 1) - fees
    db().execute(
        "UPDATE trades SET exit_price=?, fees_usd=?, pnl=?, closed_at=? WHERE id=?",
        (exit_price, fees, pnl, datetime.now().strftime("%Y-%m-%d %H:%M"), trade_id),
    )
    db().commit()
    return redirect(url_for("index"))


@app.post("/trade/<int:trade_id>/delete")
def delete_trade(trade_id):
    db().execute("DELETE FROM trades WHERE id=?", (trade_id,))
    db().commit()
    return redirect(url_for("index"))


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
