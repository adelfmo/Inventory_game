import html as html_escape
import random
import re
import textwrap
import uuid

import pandas as pd
import requests
import streamlit as st
from streamlit.components.v1 import html as st_html


st.set_page_config(page_title="Spare Parts Planning Game", layout="wide")


# =========================================================
# SECTION 1: CUSTOM STYLING
# =========================================================

st.markdown(
    """
<style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(20, 184, 166, 0.18), transparent 26%),
            radial-gradient(circle at top right, rgba(245, 158, 11, 0.14), transparent 22%),
            linear-gradient(180deg, #07111f 0%, #0b1828 48%, #09121f 100%);
        color: #f4f7ff;
    }

    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 1500px;
    }

    h1, h2, h3, p, li, label {
        color: #ffffff !important;
    }

    div[data-testid="stMetric"] {
        background: rgba(7, 18, 33, 0.82);
        border: 1px solid rgba(125, 211, 252, 0.20);
        border-radius: 8px;
        padding: 12px 14px;
        box-shadow: 0 4px 18px rgba(0,0,0,0.18);
    }

    div[data-testid="stMetricLabel"],
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricDelta"] {
        color: #ffffff !important;
    }

    .dashboard-panel {
        background: rgba(5, 15, 28, 0.82);
        border: 1px solid rgba(125, 211, 252, 0.20);
        border-radius: 8px;
        padding: 16px 18px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.22);
        margin-bottom: 14px;
    }

    .top-title-card {
        background: linear-gradient(90deg, rgba(8, 28, 44, 0.96), rgba(23, 32, 50, 0.92));
        border: 1px solid rgba(125, 211, 252, 0.22);
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 14px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.24);
    }

    .top-title {
        font-size: 2rem;
        font-weight: 800;
        color: white;
        margin-bottom: 4px;
    }

    .top-subtitle {
        color: #d7e8f8;
        font-size: 1rem;
        margin-bottom: 0;
    }

    .cost-box {
        background: rgba(7, 18, 33, 0.92);
        border: 1px solid rgba(125, 211, 252, 0.20);
        border-radius: 8px;
        padding: 14px 18px;
        color: #eef2ff;
        margin-bottom: 14px;
    }

    .cost-chip {
        display: inline-block;
        padding: 7px 12px;
        border-radius: 8px;
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.08);
        margin-right: 8px;
        margin-top: 6px;
        font-family: monospace;
        font-size: 0.95rem;
        color: white;
    }

    .small-note {
        color: #d7e8f8;
        font-size: 0.95rem;
    }

    div.stButton > button {
        border-radius: 8px;
        font-weight: 700;
        border: none;
        min-height: 2.5rem;
    }

    div[data-testid="stNumberInput"] {
        padding: 10px 12px;
        border: 1px solid rgba(125, 211, 252, 0.24);
        border-radius: 10px;
        background: linear-gradient(180deg, rgba(2,8,18,0.92), rgba(7,18,33,0.92));
    }

    div[data-testid="stNumberInput"] label {
        color: #d7e8f8 !important;
        font-weight: 900;
    }

    div[data-testid="stNumberInput"] input {
        color: #ffffff !important;
        background: rgba(0,0,0,0.45) !important;
        border: 1px solid rgba(125, 211, 252, 0.32) !important;
        border-radius: 8px !important;
        font-size: 1.25rem !important;
        font-weight: 900 !important;
    }

    .section-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: white;
        margin-bottom: 10px;
        margin-top: 6px;
    }
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# SECTION 2: CONFIGURATION
# =========================================================


class Config:
    def __init__(self):
        self.months = 20
        self.initial_inventory = 40

        self.initial_lead_time = 1
        self.shock_month = 4
        self.shocked_lead_time = 3
        self.recovery_month = 11

        self.random_seed = 42

        self.holding_cost_per_unit = 5.0
        self.backlog_cost_per_unit = 20.0

    def lead_time(self, month):
        if month >= self.recovery_month:
            return self.initial_lead_time
        if month >= self.shock_month:
            return self.shocked_lead_time
        return self.initial_lead_time

    def demand(self, month):
        rng = random.Random(self.random_seed + month)

        if month in [1, 2, 3]:
            return rng.randint(18, 25)
        if month == 4:
            return rng.randint(48, 52)
        if month == 5:
            return rng.randint(54, 60)
        if month in [6, 7]:
            return rng.randint(25, 35)
        if month == 8:
            return rng.randint(51, 55)
        if 9 <= month <= 12:
            return rng.randint(18, 27)
        if 13 <= month <= 18:
            return rng.randint(12, 20)
        if 19 <= month <= 24:
            return rng.randint(15, 23)
        return 0


cfg = Config()

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw5dmER4cIUGVo72a0u4IgsuzdokTrVsz2RNjBjGA2-f5ATEcv9DKgyQtCPCtSDgSh5/exec"


# =========================================================
# SECTION 3: STATE
# =========================================================


def init_game():
    st.session_state.game_id = str(uuid.uuid4())
    st.session_state.month = 1
    st.session_state.inventory = cfg.initial_inventory
    st.session_state.pipeline = []
    st.session_state.backlog = 0
    st.session_state.cumulative_cost = 0.0
    st.session_state.history = []
    st.session_state.submitted = False
    st.session_state.last_row = None
    st.session_state.po_qty = 0


if "player_ready" not in st.session_state:
    st.session_state.player_ready = False
    st.session_state.player_name = ""
    st.session_state.player_email = ""

if "month" not in st.session_state:
    init_game()

if "po_qty" not in st.session_state:
    st.session_state.po_qty = 0


# =========================================================
# SECTION 4: HELPERS
# =========================================================


def valid_email(email):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()) is not None


def pipeline_total():
    return sum(x["qty"] for x in st.session_state.pipeline)


def pipeline_summary(pipeline):
    if not pipeline:
        return "Empty"
    by_arrival = {}
    for order in pipeline:
        by_arrival[order["arrival"]] = by_arrival.get(order["arrival"], 0) + order["qty"]
    return " | ".join(f"M{arrival}: {qty}" for arrival, qty in sorted(by_arrival.items()))


def scaled_units(qty, units_per_piece=5, max_units=12):
    if qty <= 0:
        return 0
    return max(1, min(max_units, round(qty / units_per_piece)))


def money(value):
    return f"{value:,.0f}"


def pile_html(qty, label, css_class, max_units=14):
    count = scaled_units(qty, max_units=max_units)
    if count == 0:
        return '<span class="empty">0</span>'
    label_html = html_escape.escape(label)
    return "".join(f'<span class="{css_class}">{label_html}</span>' for _ in range(count))


def moving_tokens(count, label, css_class, delay_step=0.08):
    label_html = html_escape.escape(label)
    return "\n".join(
        f'<span class="token {css_class}" style="--i:{i}; animation-delay:{i * delay_step:.2f}s"><span>{label_html}</span></span>'
        for i in range(count)
    )


def event_chip(label, value, tone="neutral"):
    return f"""
        <div class="event-chip {tone}">
            <span>{html_escape.escape(str(label))}</span>
            <strong>{html_escape.escape(str(value))}</strong>
        </div>
    """


def dataframe_records_for_json(df):
    report_df = df.astype(object).where(pd.notna(df), "")
    return report_df.to_dict(orient="records")


def submit_result_to_google_sheet(payload):
    if GOOGLE_SCRIPT_URL == "PASTE_YOUR_APPS_SCRIPT_WEB_APP_URL_HERE":
        raise ValueError("Set GOOGLE_SCRIPT_URL before submitting results.")

    return requests.post(GOOGLE_SCRIPT_URL, json=payload, timeout=10)


def adjust_po_qty(delta):
    current = int(st.session_state.get("po_qty", 0))
    st.session_state.po_qty = min(200, max(0, current + delta))


def clear_po_qty():
    st.session_state.po_qty = 0


def historical_demand(month_index):
    rng = random.Random(cfg.random_seed * 17 + month_index)
    if month_index in [-12, -11, -10]:
        return rng.randint(15, 24)
    if month_index in [-9, -8]:
        return rng.randint(28, 42)
    if month_index in [-7, -6, -5]:
        return rng.randint(18, 31)
    if month_index in [-4, -3]:
        return rng.randint(36, 52)
    return rng.randint(16, 27)


def demand_order_chart_df():
    rows = [
        {
            "Period": f"LY {13 + month_index}",
            "Demand": historical_demand(month_index),
            "Order Qty": None,
        }
        for month_index in range(-12, 0)
    ]

    for row in st.session_state.history:
        rows.append(
            {
                "Period": f"M{row['Month']}",
                "Demand": row["New Demand"],
                "Order Qty": row["PO Placed"],
            }
        )

    return pd.DataFrame(rows[-20:])


def chart_svg(series, width=720, height=210, padding=34):
    values = [float(v) for v in series if pd.notna(v)]
    if not values:
        return ""

    max_value = max(values)
    min_value = min(values)
    if max_value == min_value:
        max_value += 1
        min_value -= 1

    points = []
    count = len(series)
    for index, raw_value in enumerate(series):
        if pd.isna(raw_value):
            continue
        x = padding if count <= 1 else padding + index * ((width - padding * 2) / (count - 1))
        y = height - padding - ((float(raw_value) - min_value) / (max_value - min_value)) * (height - padding * 2)
        points.append((x, y))

    if not points:
        return ""

    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5"></circle>' for x, y in points)
    return f'<polyline points="{path}"></polyline>{circles}'


def gameplay_demand_order_chart():
    df = demand_order_chart_df()
    demand_values = [float(v) for v in df["Demand"].tolist()]
    order_values = [float(v) for v in df["Order Qty"].tolist() if pd.notna(v)]
    max_value = max(demand_values + order_values + [1])

    width = 900
    height = 280
    pad_left = 44
    pad_right = 24
    pad_top = 22
    pad_bottom = 44
    plot_width = width - pad_left - pad_right
    plot_height = height - pad_top - pad_bottom
    count = len(df)
    step = plot_width / max(1, count)
    bar_width = min(28, step * 0.58)

    bars = []
    order_points = []
    labels = []
    for index, row in df.reset_index(drop=True).iterrows():
        x_center = pad_left + step * index + step / 2
        demand = float(row["Demand"])
        bar_height = (demand / max_value) * plot_height
        x = x_center - bar_width / 2
        y = pad_top + plot_height - bar_height
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="5"></rect>'
        )

        order_qty = row["Order Qty"]
        if pd.notna(order_qty):
            order_y = pad_top + plot_height - (float(order_qty) / max_value) * plot_height
            order_points.append((x_center, order_y))

        if index % 2 == 0 or index == count - 1:
            label = html_escape.escape(str(row["Period"]))
            labels.append(f'<text x="{x_center:.1f}" y="264" text-anchor="middle">{label}</text>')

    order_path = ""
    order_circles = ""
    if order_points:
        order_path = " ".join(f"{x:.1f},{y:.1f}" for x, y in order_points)
        order_circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5"></circle>' for x, y in order_points)

    chart_html = f"""
    <html>
    <head>
    <style>
        body {{
            margin: 0;
            background: transparent;
            font-family: Inter, Arial, sans-serif;
            color: white;
        }}

        .chart-wrap {{
            border: 1px solid rgba(125, 211, 252, 0.22);
            border-radius: 12px;
            background:
                linear-gradient(180deg, rgba(0,0,0,0.88), rgba(2,8,18,0.96));
            padding: 16px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.05), 0 14px 30px rgba(0,0,0,0.24);
        }}

        .chart-head {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: flex-start;
            margin-bottom: 6px;
        }}

        .title {{
            font-size: 1.12rem;
            font-weight: 950;
            color: white;
        }}

        .subtitle {{
            color: #a9bfd5;
            font-size: 0.82rem;
            margin-top: 2px;
        }}

        .legend {{
            display: flex;
            gap: 12px;
            color: #c7d7e8;
            font-size: 0.78rem;
            font-weight: 900;
            white-space: nowrap;
        }}

        .legend span::before {{
            content: "";
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 999px;
            margin-right: 6px;
        }}

        .demand-key::before {{ background: #38bdf8; }}
        .order-key::before {{ background: #ef4444; }}

        svg {{
            width: 100%;
            height: 280px;
            display: block;
        }}

        .grid {{
            stroke: rgba(255,255,255,0.09);
            stroke-width: 1;
        }}

        .axis {{
            stroke: rgba(255,255,255,0.18);
            stroke-width: 1;
        }}

        .bars rect {{
            fill: url(#barGrad);
            filter: drop-shadow(0 6px 10px rgba(56,189,248,0.12));
        }}

        .order-line {{
            fill: none;
            stroke: #ef4444;
            stroke-width: 4;
            stroke-linecap: round;
            stroke-linejoin: round;
            filter: drop-shadow(0 0 9px rgba(239,68,68,0.28));
        }}

        .order-points circle {{
            fill: #ef4444;
            stroke: #fecaca;
            stroke-width: 2;
        }}

        text {{
            fill: #8fa6bd;
            font-size: 11px;
            font-weight: 800;
        }}
    </style>
    </head>
    <body>
        <div class="chart-wrap">
            <div class="chart-head">
                <div>
                    <div class="title">Demand History and Your Orders</div>
                    <div class="subtitle">Blue bars are known demand. Red line is your PO quantity after each played month.</div>
                </div>
                <div class="legend"><span class="demand-key">Demand</span><span class="order-key">PO Qty</span></div>
            </div>
            <svg viewBox="0 0 {width} {height}" preserveAspectRatio="none">
                <defs>
                    <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#7dd3fc"></stop>
                        <stop offset="100%" stop-color="#0284c7"></stop>
                    </linearGradient>
                </defs>
                <line class="grid" x1="{pad_left}" y1="60" x2="{width - pad_right}" y2="60"></line>
                <line class="grid" x1="{pad_left}" y1="118" x2="{width - pad_right}" y2="118"></line>
                <line class="grid" x1="{pad_left}" y1="176" x2="{width - pad_right}" y2="176"></line>
                <line class="axis" x1="{pad_left}" y1="{pad_top + plot_height}" x2="{width - pad_right}" y2="{pad_top + plot_height}"></line>
                <g class="bars">{"".join(bars)}</g>
                <polyline class="order-line" points="{order_path}"></polyline>
                <g class="order-points">{order_circles}</g>
                <g class="labels">{"".join(labels)}</g>
            </svg>
        </div>
    </body>
    </html>
    """
    st_html(chart_html, height=350)


def submit_game_result_if_needed(df):
    if st.session_state.submitted:
        return

    total_need = df["Total Customer Need"].sum()
    total_fulfilled = df["Fulfilled"].sum()
    service_level = total_fulfilled / total_need if total_need > 0 else 0

    payload = {
        "game_id": st.session_state.get("game_id", str(uuid.uuid4())),
        "player_name": st.session_state.player_name,
        "player_email": st.session_state.player_email,
        "service_level": round(service_level * 100, 1),
        "total_inventory_cost": round(float(df["Inventory Holding Cost"].sum()), 0),
        "total_backlog_cost": round(float(df["Backlog Cost"].sum()), 0),
        "cumulative_total_cost": round(float(df["Cumulative Total Cost"].iloc[-1]), 0),
        "months_played": int(len(st.session_state.history)),
        "peak_pipeline": round(float(df["Pipeline"].max()), 0),
        "peak_backlog": round(float(df["Ending Backlog"].max()), 0),
        "history": dataframe_records_for_json(df),
    }

    try:
        response = submit_result_to_google_sheet(payload)
        response.raise_for_status()

        try:
            result = response.json()
        except ValueError:
            result = {}

        status = result.get("status", "ok")
        if status in ["ok", "duplicate"]:
            st.session_state.submitted = True
            st.success(f"Your final report has been saved and emailed to {st.session_state.player_email}.")
        else:
            st.warning(f"Result not submitted: {result.get('message', 'Unknown error')}")
    except Exception as e:
        st.warning(f"Result not submitted: {e}")


# =========================================================
# SECTION 5: GAME LOGIC
# =========================================================


def run_month(order_qty):
    month = st.session_state.month
    lead_time = cfg.lead_time(month)

    incoming_orders = [x for x in st.session_state.pipeline if x["arrival"] == month]
    incoming = sum(x["qty"] for x in incoming_orders)
    st.session_state.pipeline = [x for x in st.session_state.pipeline if x["arrival"] != month]

    new_demand = cfg.demand(month)
    backlog_before = st.session_state.backlog
    total_customer_need = new_demand + backlog_before

    starting_inventory = st.session_state.inventory
    inventory_after_incoming = starting_inventory + incoming

    fulfilled = min(inventory_after_incoming, total_customer_need)
    ending_inventory = inventory_after_incoming - fulfilled
    ending_backlog = total_customer_need - fulfilled
    backlog_this_period = max(0, ending_backlog - backlog_before)

    if order_qty > 0:
        st.session_state.pipeline.append({"arrival": month + lead_time, "qty": order_qty})

    current_pipeline = pipeline_total()
    pipeline_orders_text = pipeline_summary(st.session_state.pipeline)

    inventory_holding_cost = ending_inventory * cfg.holding_cost_per_unit
    backlog_cost = ending_backlog * cfg.backlog_cost_per_unit
    month_total_cost = inventory_holding_cost + backlog_cost

    st.session_state.cumulative_cost += month_total_cost

    row = {
        "Month": month,
        "Lead Time": lead_time,
        "Previous Lead Time": cfg.lead_time(month - 1) if month > 1 else lead_time,
        "Starting Inventory": starting_inventory,
        "Incoming Purchases": incoming,
        "Inventory After Incoming": inventory_after_incoming,
        "New Demand": new_demand,
        "Backlog From Previous Month": backlog_before,
        "Total Customer Need": total_customer_need,
        "Fulfilled": fulfilled,
        "Backlog This Period": backlog_this_period,
        "Ending Backlog": ending_backlog,
        "Ending Inventory": ending_inventory,
        "PO Placed": order_qty,
        "PO Arrival Month": month + lead_time if order_qty > 0 else "",
        "Pipeline": current_pipeline,
        "Pipeline Orders": pipeline_orders_text,
        "Inventory Holding Cost": round(inventory_holding_cost, 2),
        "Backlog Cost": round(backlog_cost, 2),
        "Month Total Cost": round(month_total_cost, 2),
        "Cumulative Total Cost": round(st.session_state.cumulative_cost, 2),
    }

    st.session_state.history.append(row)
    st.session_state.inventory = ending_inventory
    st.session_state.backlog = ending_backlog
    st.session_state.month += 1
    st.session_state.last_row = row

    return row


# =========================================================
# SECTION 6: DISTINCT 3-BLOCK ANIMATION
# =========================================================


def month_notification(row, service):
    if row["Ending Backlog"] >= 60:
        return "Check the backlog", f"{row['Ending Backlog']} units are waiting. Build cover earlier.", "bad", "!"
    if row["Pipeline"] >= 120:
        return "Check your pipeline", f"{row['Pipeline']} units are already on order. Watch holding cost.", "warn", "?"
    if service >= 0.95 and row["Ending Backlog"] == 0:
        return "Good job", f"{service:.0%} service and no backlog this month.", "good", "+"
    if row["Ending Inventory"] == 0:
        return "Stockout!", "Warehouse stock reached zero after serving demand.", "warn", "!"
    return "Keep balancing", "Watch service, backlog, and pipeline before the next PO.", "neutral", "i"


def lead_time_popup(row):
    if row["Lead Time"] == row["Previous Lead Time"]:
        return ""

    is_shock = row["Lead Time"] > row["Previous Lead Time"]
    title = "Lead time shock!" if is_shock else "Lead time recovered!"
    detail = f"Supplier lead time changed from {row['Previous Lead Time']} to {row['Lead Time']} month(s)."
    tone = "shock" if is_shock else "recovery"
    return f"""
        <div class="lead-popup {tone}">
            <div class="lead-badge">LT</div>
            <div>
                <div class="lead-title">{title}</div>
                <div class="lead-detail">{detail}</div>
            </div>
        </div>
    """


def animate_month(row):
    service = row["Fulfilled"] / row["Total Customer Need"] if row["Total Customer Need"] else 1
    service_pct = f"{service:.0%}"
    service_class = "good" if service >= 0.95 else "warn" if service >= 0.75 else "bad"

    coach_title, coach_detail, coach_class, coach_icon = month_notification(row, service)
    arrival_text = f"ETA M{row['PO Arrival Month']}" if row["PO Placed"] > 0 else "No new PO"

    incoming_tokens = moving_tokens(scaled_units(row["Incoming Purchases"], max_units=10), "", "move-in carton")
    shipped_tokens = moving_tokens(scaled_units(row["Fulfilled"], max_units=12), "", "move-out part-token")
    po_tokens = moving_tokens(scaled_units(row["PO Placed"], max_units=8), "PO", "move-po", 0.07)

    animation_html = f"""
    <html>
    <head>
    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            font-family: Inter, Arial, sans-serif;
            color: white;
            background: transparent;
        }}

        .wrap {{
            position: relative;
            overflow: hidden;
            min-height: 690px;
            border: 1px solid rgba(125, 211, 252, 0.22);
            border-radius: 12px;
            padding: 16px;
            background:
                linear-gradient(180deg, rgba(3, 10, 20, 0.98), rgba(5, 12, 22, 0.98));
            box-shadow: 0 16px 38px rgba(0,0,0,0.34);
        }}

        .topbar {{
            display: flex;
            align-items: stretch;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 12px;
        }}

        .title {{
            font-size: 1.75rem;
            font-weight: 950;
            margin-bottom: 4px;
        }}

        .subtitle {{
            color: #cfe0f0;
            font-size: 0.98rem;
        }}

        .coach {{
            min-width: 330px;
            max-width: 430px;
            display: flex;
            align-items: center;
            gap: 10px;
            border: 1px solid rgba(255,255,255,0.13);
            border-left-width: 5px;
            border-radius: 8px;
            background: rgba(8, 20, 35, 0.92);
            padding: 10px 12px;
            animation: slideDown 0.55s ease-out both;
        }}

        .coach-icon {{
            width: 34px;
            height: 34px;
            border-radius: 999px;
            display: grid;
            place-items: center;
            font-weight: 950;
            color: white;
            background: rgba(255,255,255,0.12);
        }}

        .coach-title {{
            font-size: 0.94rem;
            font-weight: 950;
        }}

        .coach-detail {{
            color: #c7d7e8;
            font-size: 0.82rem;
            margin-top: 2px;
        }}

        .coach.good {{ border-left-color: #34d399; }}
        .coach.good .coach-icon {{ background: #15803d; }}
        .coach.warn {{ border-left-color: #fbbf24; }}
        .coach.warn .coach-icon {{ background: #b45309; }}
        .coach.bad {{ border-left-color: #fb7185; }}
        .coach.bad .coach-icon {{ background: #be123c; }}
        .coach.neutral {{ border-left-color: #7dd3fc; }}
        .coach.neutral .coach-icon {{ background: #0369a1; }}

        .badge {{
            min-width: 126px;
            border-radius: 8px;
            padding: 10px 12px;
            text-align: center;
            background: rgba(8, 20, 35, 0.88);
            border: 1px solid rgba(255,255,255,0.12);
        }}

        .badge .small {{
            color: #c7d7e8;
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
        }}

        .badge .big {{
            font-size: 1.55rem;
            font-weight: 950;
            margin-top: 2px;
        }}

        .badge.good .big {{ color: #34d399; }}
        .badge.warn .big {{ color: #fbbf24; }}
        .badge.bad .big {{ color: #fb7185; }}

        .events {{
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 8px;
            margin-bottom: 12px;
        }}

        .event-chip {{
            min-height: 58px;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px;
            background: rgba(9, 24, 42, 0.84);
            padding: 8px 10px;
        }}

        .event-chip span {{
            display: block;
            color: #c7d7e8;
            font-size: 0.76rem;
            font-weight: 900;
            text-transform: uppercase;
        }}

        .event-chip strong {{
            display: block;
            color: #ffffff;
            font-size: 1.28rem;
            margin-top: 3px;
        }}

        .event-chip.good strong {{ color: #34d399; }}
        .event-chip.warn strong {{ color: #fbbf24; }}
        .event-chip.bad strong {{ color: #fb7185; }}

        .board {{
            position: relative;
            min-height: 420px;
            border: 1px solid rgba(125, 211, 252, 0.14);
            border-radius: 10px;
            background: rgba(4, 11, 20, 0.42);
            overflow: hidden;
            padding: 16px;
        }}

        .flow-grid {{
            position: relative;
            z-index: 2;
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 28px;
            min-height: 360px;
        }}

        .block {{
            position: relative;
            overflow: hidden;
            min-height: 352px;
            border: 2px solid rgba(255,255,255,0.13);
            border-radius: 10px;
            padding: 16px;
            background: linear-gradient(180deg, rgba(10, 25, 43, 0.98), rgba(7, 15, 27, 0.98));
            box-shadow: 0 10px 26px rgba(0,0,0,0.28);
        }}

        .block.supplier {{ border-color: rgba(125, 211, 252, 0.72); }}
        .block.inventory {{ border-color: rgba(52, 211, 153, 0.72); }}
        .block.customer {{ border-color: rgba(251, 191, 36, 0.72); }}

        .block::before {{
            content: "";
            position: absolute;
            inset: 0;
            opacity: 0.14;
            pointer-events: none;
        }}

        .block.supplier::before {{ background: linear-gradient(135deg, #7dd3fc, transparent 42%); }}
        .block.inventory::before {{ background: linear-gradient(135deg, #34d399, transparent 42%); }}
        .block.customer::before {{ background: linear-gradient(135deg, #fbbf24, transparent 42%); }}

        .block-head {{
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }}

        .block-icon {{
            width: 42px;
            height: 42px;
            border-radius: 8px;
            display: grid;
            place-items: center;
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.14);
            color: white;
            font-size: 1.35rem;
            font-weight: 950;
        }}

        .block-name {{
            flex: 1;
            font-size: 1.28rem;
            font-weight: 950;
        }}

        .block-value {{
            font-size: 2.15rem;
            font-weight: 950;
        }}

        .block-sub {{
            position: relative;
            z-index: 1;
            color: #c7d7e8;
            font-size: 0.9rem;
            line-height: 1.28;
            min-height: 48px;
        }}

        .pile {{
            position: relative;
            z-index: 1;
            min-height: 116px;
            display: flex;
            flex-wrap: wrap;
            align-content: flex-start;
            gap: 6px;
            margin-top: 14px;
            padding: 8px;
            border-radius: 8px;
            background: rgba(255,255,255,0.05);
        }}

        .pile span {{
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 29px;
            height: 26px;
            padding: 0 5px;
            border-radius: 6px;
            background: rgba(255,255,255,0.08);
            font-size: 0.64rem;
            font-weight: 950;
        }}

        .box {{
            width: 30px;
            min-width: 30px !important;
            color: transparent;
            background: linear-gradient(145deg, #c98b4a 0%, #9b612e 100%) !important;
            border: 1px solid rgba(255,219,172,0.48);
            box-shadow: inset -6px -5px 0 rgba(80, 44, 18, 0.28), 0 4px 8px rgba(0,0,0,0.22);
        }}

        .box::before {{
            content: "";
            position: absolute;
            left: 12px;
            top: 0;
            width: 6px;
            height: 100%;
            background: rgba(255,226,178,0.52);
        }}

        .box::after {{
            content: "";
            position: absolute;
            left: 5px;
            right: 5px;
            top: 8px;
            height: 2px;
            background: rgba(90,50,20,0.38);
        }}

        .part {{
            width: 30px;
            min-width: 30px !important;
            color: transparent;
            border-radius: 999px !important;
            background: radial-gradient(circle at 35% 35%, #d7f7f0 0 18%, #34d399 20% 48%, #0f766e 50% 100%) !important;
            border: 1px solid rgba(167, 243, 208, 0.62);
            box-shadow: inset -5px -5px 0 rgba(4, 120, 87, 0.34), 0 4px 8px rgba(0,0,0,0.22);
        }}

        .part::after {{
            content: "";
            position: absolute;
            inset: 9px;
            border-radius: 999px;
            background: rgba(4, 11, 20, 0.88);
        }}

        .person {{
            width: 28px;
            min-width: 28px !important;
            height: 34px !important;
            color: transparent;
            background: transparent !important;
            border: 0 !important;
        }}

        .person::before {{
            content: "";
            position: absolute;
            top: 2px;
            left: 9px;
            width: 11px;
            height: 11px;
            border-radius: 999px;
            background: #fbbf24;
            box-shadow: 0 0 0 2px rgba(251,191,36,0.18);
        }}

        .person::after {{
            content: "";
            position: absolute;
            left: 6px;
            bottom: 2px;
            width: 16px;
            height: 18px;
            border-radius: 9px 9px 4px 4px;
            background: linear-gradient(180deg, #fbbf24, #b45309);
            box-shadow:
                -6px 8px 0 -3px rgba(251,191,36,0.82),
                6px 8px 0 -3px rgba(251,191,36,0.82);
        }}

        .late {{ color: #fb7185; }}

        .empty {{
            width: auto !important;
            padding: 0 9px !important;
            color: #9fb2c8;
            font-weight: 900;
        }}

        .block-metrics {{
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-top: 12px;
        }}

        .mini {{
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 8px;
            padding: 8px;
            background: rgba(4, 11, 20, 0.62);
        }}

        .mini span {{
            display: block;
            color: #a9bfd5;
            font-size: 0.7rem;
            font-weight: 900;
            text-transform: uppercase;
        }}

        .mini strong {{
            display: block;
            color: white;
            font-size: 1.08rem;
            margin-top: 2px;
        }}

        .connector {{
            position: absolute;
            z-index: 4;
            top: 122px;
            width: 12%;
            text-align: center;
            color: #d7e8f8;
            font-size: 0.76rem;
            font-weight: 950;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        .connector.si {{ left: 30.3%; }}
        .connector.ic {{ left: 63.8%; }}

        .connector-line {{
            height: 4px;
            margin-top: 10px;
            border-radius: 999px;
            background:
                repeating-linear-gradient(90deg, rgba(255,255,255,0.22) 0 8px, transparent 8px 16px),
                linear-gradient(90deg, rgba(125,211,252,0.15), rgba(125,211,252,0.92));
            position: relative;
            overflow: visible;
        }}

        .connector-line::after {{
            content: "";
            position: absolute;
            right: -2px;
            top: -5px;
            border-left: 12px solid rgba(125,211,252,0.92);
            border-top: 7px solid transparent;
            border-bottom: 7px solid transparent;
        }}

        .token {{
            position: absolute;
            z-index: 20;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 34px;
            width: 34px;
            height: 30px;
            padding: 0 7px;
            border-radius: 7px;
            background: rgba(255,255,255,0.13);
            border: 1px solid rgba(255,255,255,0.20);
            box-shadow: 0 10px 18px rgba(0,0,0,0.28);
            opacity: 0;
            font-size: 0.66rem;
            font-weight: 950;
        }}

        .token span {{
            position: relative;
            z-index: 2;
        }}

        .token.carton {{
            color: transparent;
            background: linear-gradient(145deg, #d19652 0%, #9b612e 100%);
            border-color: rgba(255,219,172,0.55);
            box-shadow: inset -7px -6px 0 rgba(80, 44, 18, 0.25), 0 12px 20px rgba(0,0,0,0.30);
        }}

        .token.carton::before {{
            content: "";
            position: absolute;
            left: 13px;
            top: 0;
            width: 7px;
            height: 100%;
            background: rgba(255,226,178,0.58);
        }}

        .token.carton::after {{
            content: "";
            position: absolute;
            left: 4px;
            right: 4px;
            bottom: -8px;
            height: 7px;
            border-radius: 999px;
            background: rgba(0,0,0,0.24);
            filter: blur(3px);
        }}

        .token.part-token {{
            color: transparent;
            border-radius: 999px;
            background: radial-gradient(circle at 35% 35%, #d7f7f0 0 18%, #34d399 20% 48%, #0f766e 50% 100%);
            border-color: rgba(167, 243, 208, 0.62);
            box-shadow: inset -5px -5px 0 rgba(4, 120, 87, 0.34), 0 12px 20px rgba(0,0,0,0.30);
        }}

        .token.part-token::before {{
            content: "";
            position: absolute;
            inset: 10px;
            border-radius: 999px;
            background: rgba(4, 11, 20, 0.88);
        }}

        .token.part-token::after {{
            content: "";
            position: absolute;
            left: 4px;
            right: 4px;
            bottom: -8px;
            height: 7px;
            border-radius: 999px;
            background: rgba(0,0,0,0.22);
            filter: blur(3px);
        }}

        .move-in {{
            left: calc(18% + (var(--i) % 3) * 8px);
            top: calc(138px + (var(--i) % 4) * 18px);
            color: #7dd3fc;
            animation: incoming 1.75s cubic-bezier(.2,.7,.2,1) forwards;
        }}

        .move-out {{
            left: calc(49% + (var(--i) % 3) * 8px);
            top: calc(138px + (var(--i) % 4) * 18px);
            color: #34d399;
            animation: outbound 1.85s cubic-bezier(.2,.7,.2,1) forwards;
            animation-delay: calc(0.55s + var(--i) * 0.08s);
        }}

        .move-po {{
            left: calc(50% + (var(--i) % 4) * 8px);
            bottom: calc(35px + (var(--i) % 3) * 17px);
            color: #7dd3fc;
            animation: poMove 1.08s ease-in-out forwards;
            animation-delay: calc(1.9s + var(--i) * 0.08s);
        }}

        @keyframes incoming {{
            0% {{ opacity: 0; left: 18%; transform: translateY(8px) scale(0.70) rotate(-8deg); }}
            12% {{ opacity: 1; }}
            45% {{ transform: translateY(-10px) scale(1.04) rotate(4deg); }}
            78% {{ opacity: 1; }}
            100% {{ opacity: 0; left: 48%; transform: translateY(6px) scale(0.88) rotate(0deg); }}
        }}

        @keyframes outbound {{
            0% {{ opacity: 0; left: 49%; transform: translateY(6px) scale(0.70) rotate(-10deg); }}
            14% {{ opacity: 1; }}
            52% {{ transform: translateY(-12px) scale(1.04) rotate(8deg); }}
            84% {{ opacity: 1; }}
            100% {{ opacity: 0; left: 80%; transform: translateY(7px) scale(0.86) rotate(0deg); }}
        }}

        @keyframes poMove {{
            0% {{ opacity: 0; left: 50%; transform: scale(0.6); }}
            20% {{ opacity: 1; }}
            100% {{ opacity: 1; left: 18%; transform: scale(0.9); }}
        }}

        .pulse {{
            animation: pulse 1.2s ease-in-out 2;
        }}

        @keyframes pulse {{
            0%, 100% {{ box-shadow: 0 10px 26px rgba(0,0,0,0.28); }}
            50% {{ box-shadow: 0 0 0 4px rgba(251,191,36,0.18), 0 14px 32px rgba(0,0,0,0.34); }}
        }}

        .lead-popup {{
            position: absolute;
            z-index: 50;
            left: 50%;
            top: 88px;
            transform: translateX(-50%);
            display: flex;
            gap: 12px;
            align-items: center;
            max-width: 480px;
            border-radius: 10px;
            padding: 14px 16px;
            background: rgba(5, 12, 22, 0.96);
            border: 2px solid #fbbf24;
            box-shadow: 0 18px 38px rgba(0,0,0,0.42);
            animation: burst 3.4s ease-in-out both;
        }}

        .lead-popup.recovery {{
            border-color: #34d399;
        }}

        .lead-badge {{
            width: 46px;
            height: 46px;
            border-radius: 999px;
            display: grid;
            place-items: center;
            font-weight: 950;
            color: #08111f;
            background: #fbbf24;
            animation: spinPop 1.4s ease-in-out both;
        }}

        .lead-popup.recovery .lead-badge {{
            background: #34d399;
        }}

        .lead-title {{
            color: white;
            font-size: 1.15rem;
            font-weight: 950;
        }}

        .lead-detail {{
            color: #d7e8f8;
            font-size: 0.9rem;
            margin-top: 2px;
        }}

        @keyframes burst {{
            0% {{ opacity: 0; transform: translate(-50%, -18px) scale(0.82); }}
            12% {{ opacity: 1; transform: translate(-50%, 0) scale(1.04); }}
            82% {{ opacity: 1; transform: translate(-50%, 0) scale(1); }}
            100% {{ opacity: 0; transform: translate(-50%, -10px) scale(0.96); }}
        }}

        @keyframes spinPop {{
            from {{ transform: rotate(-20deg) scale(0.6); }}
            to {{ transform: rotate(0deg) scale(1); }}
        }}

        @keyframes slideDown {{
            from {{ opacity: 0; transform: translateY(-8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .status-strip {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 8px;
            margin-top: 10px;
        }}

        .status-cell {{
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 8px;
            background: rgba(4, 11, 20, 0.72);
            padding: 8px;
        }}

        .status-cell span {{
            display: block;
            color: #a9bfd5;
            font-size: 0.75rem;
            font-weight: 900;
            text-transform: uppercase;
        }}

        .status-cell strong {{
            display: block;
            color: #ffffff;
            margin-top: 3px;
            font-size: 1.05rem;
        }}

        @media (max-width: 900px) {{
            .topbar {{
                flex-direction: column;
            }}

            .events, .status-strip {{
                grid-template-columns: repeat(2, 1fr);
            }}

            .flow-grid {{
                grid-template-columns: 1fr;
            }}

            .connector, .token {{
                display: none;
            }}
        }}
    </style>
    </head>
    <body>
        <div class="wrap">
            <div class="topbar">
                <div>
                    <div class="title">Month {row["Month"]}: Supplier -> Inventory -> Customer</div>
                    <div class="subtitle">Three distinctive blocks. POs wait at Supplier, boxes move to Warehouse, parts move to Customers.</div>
                </div>
                <div style="display:flex; gap:10px; align-items:stretch;">
                    <div class="coach {coach_class}">
                        <div class="coach-icon">{coach_icon}</div>
                        <div>
                            <div class="coach-title">{coach_title}</div>
                            <div class="coach-detail">{coach_detail}</div>
                        </div>
                    </div>
                    <div class="badge {service_class}">
                        <div class="small">Service</div>
                        <div class="big">{service_pct}</div>
                    </div>
                </div>
            </div>

            {lead_time_popup(row)}

            <div class="events">
                {event_chip("PO placed", row["PO Placed"], "good" if row["PO Placed"] else "neutral")}
                {event_chip("Incoming", row["Incoming Purchases"], "good" if row["Incoming Purchases"] else "neutral")}
                {event_chip("Demand", row["New Demand"], "warn")}
                {event_chip("Shipped", row["Fulfilled"], "good")}
                {event_chip("Backlog", row["Ending Backlog"], "bad" if row["Ending Backlog"] else "good")}
            </div>

            <div class="board">
                {incoming_tokens}
                {shipped_tokens}
                {po_tokens}

                <div class="connector si">
                    Boxes arriving {row["Incoming Purchases"]}
                    <div class="connector-line"></div>
                </div>
                <div class="connector ic">
                    Parts shipped {row["Fulfilled"]}
                    <div class="connector-line"></div>
                </div>

                <div class="flow-grid">
                    <div class="block supplier">
                        <div class="block-head">
                            <div class="block-icon">S</div>
                            <div class="block-name">Supplier</div>
                            <div class="block-value">{row["Pipeline"]}</div>
                        </div>
                        <div class="block-sub">Open PO pipeline: {html_escape.escape(str(row["Pipeline Orders"]))}</div>
                        <div class="pile">{pile_html(row["Pipeline"], "BOX", "box")}</div>
                        <div class="block-metrics">
                            <div class="mini"><span>New PO</span><strong>{row["PO Placed"]}</strong></div>
                            <div class="mini"><span>{arrival_text}</span><strong>{row["Lead Time"]} mo</strong></div>
                        </div>
                    </div>

                    <div class="block inventory pulse">
                        <div class="block-head">
                            <div class="block-icon">I</div>
                            <div class="block-name">Warehouse</div>
                            <div class="block-value">{row["Ending Inventory"]}</div>
                        </div>
                        <div class="block-sub">Started {row["Starting Inventory"]}, received {row["Incoming Purchases"]}, shipped {row["Fulfilled"]}.</div>
                        <div class="pile">{pile_html(row["Ending Inventory"], "PART", "part")}</div>
                        <div class="block-metrics">
                            <div class="mini"><span>After incoming</span><strong>{row["Inventory After Incoming"]}</strong></div>
                            <div class="mini"><span>Holding cost</span><strong>{money(row["Inventory Holding Cost"])}</strong></div>
                        </div>
                    </div>

                    <div class="block customer pulse">
                        <div class="block-head">
                            <div class="block-icon">C</div>
                            <div class="block-name">Customer</div>
                            <div class="block-value">{row["New Demand"]}</div>
                        </div>
                        <div class="block-sub">New demand plus previous backlog of {row["Backlog From Previous Month"]}.</div>
                        <div class="pile">{pile_html(row["New Demand"], "", "person", max_units=12)}</div>
                        <div class="block-metrics">
                            <div class="mini"><span>Fulfilled</span><strong>{row["Fulfilled"]}</strong></div>
                            <div class="mini"><span>Backlog</span><strong>{row["Ending Backlog"]}</strong></div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="status-strip">
                <div class="status-cell"><span>Lead time</span><strong>{row["Lead Time"]} month(s)</strong></div>
                <div class="status-cell"><span>Total need</span><strong>{row["Total Customer Need"]}</strong></div>
                <div class="status-cell"><span>Backlog this month</span><strong>{row["Backlog This Period"]}</strong></div>
                <div class="status-cell"><span>Inventory cost</span><strong>{money(row["Inventory Holding Cost"])}</strong></div>
                <div class="status-cell"><span>Backlog cost</span><strong>{money(row["Backlog Cost"])}</strong></div>
            </div>
        </div>
        <script>
            (() => {{
                const AudioContextClass = window.AudioContext || window.webkitAudioContext;
                if (!AudioContextClass) return;

                const audio = new AudioContextClass();

                function tone(freq, start, duration, type, gainValue) {{
                    const osc = audio.createOscillator();
                    const gain = audio.createGain();
                    osc.type = type;
                    osc.frequency.setValueAtTime(freq, audio.currentTime + start);
                    gain.gain.setValueAtTime(0.0001, audio.currentTime + start);
                    gain.gain.exponentialRampToValueAtTime(gainValue, audio.currentTime + start + 0.015);
                    gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + start + duration);
                    osc.connect(gain);
                    gain.connect(audio.destination);
                    osc.start(audio.currentTime + start);
                    osc.stop(audio.currentTime + start + duration + 0.02);
                }}

                function noise(start, duration, gainValue) {{
                    const bufferSize = Math.max(1, Math.floor(audio.sampleRate * duration));
                    const buffer = audio.createBuffer(1, bufferSize, audio.sampleRate);
                    const data = buffer.getChannelData(0);
                    for (let i = 0; i < bufferSize; i += 1) {{
                        data[i] = (Math.random() * 2 - 1) * (1 - i / bufferSize);
                    }}
                    const source = audio.createBufferSource();
                    const gain = audio.createGain();
                    const filter = audio.createBiquadFilter();
                    filter.type = "bandpass";
                    filter.frequency.value = 850;
                    gain.gain.setValueAtTime(gainValue, audio.currentTime + start);
                    gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + start + duration);
                    source.buffer = buffer;
                    source.connect(filter);
                    filter.connect(gain);
                    gain.connect(audio.destination);
                    source.start(audio.currentTime + start);
                }}

                async function playSequence() {{
                    try {{
                        await audio.resume();
                        tone(520, 0.03, 0.055, "square", 0.035);
                        noise(0.35, 0.16, 0.035);
                        tone(220, 0.40, 0.18, "triangle", 0.030);
                        tone(330, 0.72, 0.12, "triangle", 0.024);
                        tone(420, 0.92, 0.11, "triangle", 0.022);
                        tone(660, 1.22, 0.09, "sine", 0.026);
                        tone(880, 1.34, 0.12, "sine", 0.022);
                    }} catch (err) {{
                    }}
                }}

                window.addEventListener("pointerdown", playSequence, {{ once: true }});
                window.setTimeout(playSequence, 120);
            }})();
        </script>
    </body>
    </html>
    """

    st_html(animation_html, height=760)


def render_completion_summary(df):
    total_need = df["Total Customer Need"].sum()
    total_fulfilled = df["Fulfilled"].sum()
    service_level = total_fulfilled / total_need if total_need > 0 else 0
    total_inventory_cost = df["Inventory Holding Cost"].sum()
    total_backlog_cost = df["Backlog Cost"].sum()
    cumulative_total_cost = df["Cumulative Total Cost"].iloc[-1]
    peak_pipeline = df["Pipeline"].max()
    peak_backlog = df["Ending Backlog"].max()
    demand_order_df = demand_order_chart_df()
    demand_svg = chart_svg(demand_order_df["Demand"])
    order_svg = chart_svg(demand_order_df["Order Qty"])
    inventory_svg = chart_svg(df["Ending Inventory"])
    backlog_svg = chart_svg(df["Ending Backlog"])
    cost_svg = chart_svg(df["Month Total Cost"])

    if service_level >= 0.95 and peak_backlog == 0:
        verdict = "Excellent planning"
        verdict_detail = "You kept service high and avoided backlog."
        verdict_class = "great"
    elif service_level >= 0.85:
        verdict = "Strong run"
        verdict_detail = "Good service overall. The next win is reducing cost swings."
        verdict_class = "good"
    elif peak_backlog > 80:
        verdict = "Backlog pressure"
        verdict_detail = "Demand waited too long. Try ordering earlier before the shock."
        verdict_class = "warn"
    else:
        verdict = "Game complete"
        verdict_detail = "You finished the planning horizon. Review the trends below."
        verdict_class = "neutral"

    completion_html = f"""
    <html>
    <head>
    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            font-family: Inter, Arial, sans-serif;
            background: rgba(2, 6, 12, 0.54);
            color: white;
        }}

        .finish {{
            position: relative;
            overflow: hidden;
            min-height: 920px;
            display: grid;
            align-items: start;
            padding: 24px;
            background:
                radial-gradient(circle at 50% 20%, rgba(125, 211, 252, 0.16), transparent 34%),
                rgba(2, 6, 12, 0.58);
        }}

        .modal {{
            position: relative;
            z-index: 1;
            width: min(1280px, 100%);
            border: 1px solid rgba(125, 211, 252, 0.30);
            border-radius: 12px;
            padding: 22px;
            background:
                linear-gradient(135deg, rgba(20, 184, 166, 0.22), transparent 34%),
                linear-gradient(180deg, rgba(5, 15, 28, 0.98), rgba(7, 18, 33, 0.98));
            box-shadow: 0 24px 70px rgba(0,0,0,0.52);
            animation: modalIn 0.55s cubic-bezier(.2,.8,.2,1) both;
        }}

        .finish::before,
        .finish::after {{
            content: "";
            position: absolute;
            inset: -30%;
            background:
                radial-gradient(circle, rgba(52,211,153,0.85) 0 2px, transparent 3px),
                radial-gradient(circle, rgba(251,191,36,0.75) 0 2px, transparent 3px),
                radial-gradient(circle, rgba(125,211,252,0.75) 0 2px, transparent 3px);
            background-size: 80px 80px, 110px 110px, 140px 140px;
            opacity: 0;
            animation: confetti 2.8s ease-out both;
            pointer-events: none;
        }}

        .finish::after {{
            animation-delay: 0.18s;
            transform: rotate(8deg);
        }}

        .hero {{
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: 1.05fr 1.4fr;
            gap: 18px;
            align-items: stretch;
        }}

        .charts {{
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: 1.25fr 1fr;
            gap: 12px;
            margin-top: 14px;
        }}

        .chart-card {{
            border: 1px solid rgba(255,255,255,0.11);
            border-radius: 10px;
            background: rgba(4, 11, 20, 0.66);
            padding: 14px;
            min-height: 230px;
        }}

        .chart-card.wide {{
            grid-row: span 2;
        }}

        .chart-title {{
            color: white;
            font-size: 1rem;
            font-weight: 950;
            margin-bottom: 2px;
        }}

        .chart-subtitle {{
            color: #a9bfd5;
            font-size: 0.78rem;
            font-weight: 800;
            margin-bottom: 8px;
        }}

        svg {{
            width: 100%;
            height: 190px;
            overflow: visible;
        }}

        .axis {{
            stroke: rgba(255,255,255,0.16);
            stroke-width: 1;
        }}

        .grid {{
            stroke: rgba(255,255,255,0.08);
            stroke-width: 1;
        }}

        .demand-line polyline,
        .inventory-line polyline {{
            fill: none;
            stroke: #7dd3fc;
            stroke-width: 3;
            stroke-linecap: round;
            stroke-linejoin: round;
            filter: drop-shadow(0 0 8px rgba(125, 211, 252, 0.22));
        }}

        .order-line polyline {{
            fill: none;
            stroke: #34d399;
            stroke-width: 3;
            stroke-linecap: round;
            stroke-linejoin: round;
        }}

        .backlog-line polyline,
        .cost-line polyline {{
            fill: none;
            stroke: #fb7185;
            stroke-width: 3;
            stroke-linecap: round;
            stroke-linejoin: round;
        }}

        .demand-line circle,
        .inventory-line circle {{
            fill: #7dd3fc;
        }}

        .order-line circle {{
            fill: #34d399;
        }}

        .backlog-line circle,
        .cost-line circle {{
            fill: #fb7185;
        }}

        .legend {{
            display: flex;
            gap: 12px;
            color: #c7d7e8;
            font-size: 0.78rem;
            font-weight: 900;
            margin-top: 4px;
        }}

        .legend span::before {{
            content: "";
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 999px;
            margin-right: 6px;
        }}

        .legend .demand::before {{ background: #7dd3fc; }}
        .legend .order::before {{ background: #34d399; }}
        .legend .backlog::before {{ background: #fb7185; }}

        .headline {{
            border: 1px solid rgba(255,255,255,0.13);
            border-left: 6px solid #34d399;
            border-radius: 10px;
            background: rgba(4, 11, 20, 0.62);
            padding: 18px;
            animation: popIn 0.6s ease-out both;
        }}

        .headline.great {{ border-left-color: #34d399; }}
        .headline.good {{ border-left-color: #7dd3fc; }}
        .headline.warn {{ border-left-color: #fbbf24; }}
        .headline.neutral {{ border-left-color: #c4b5fd; }}

        .complete-label {{
            color: #a9bfd5;
            font-size: 0.82rem;
            font-weight: 950;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}

        .complete-title {{
            font-size: 2.4rem;
            line-height: 1;
            font-weight: 950;
            margin-top: 8px;
        }}

        .verdict {{
            color: #d7e8f8;
            font-size: 1rem;
            margin-top: 10px;
            line-height: 1.35;
        }}

        .kpis {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }}

        .kpi {{
            border: 1px solid rgba(255,255,255,0.11);
            border-radius: 10px;
            background: rgba(4, 11, 20, 0.66);
            padding: 14px;
            min-height: 92px;
            animation: rise 0.55s ease-out both;
        }}

        .kpi:nth-child(2) {{ animation-delay: 0.06s; }}
        .kpi:nth-child(3) {{ animation-delay: 0.12s; }}
        .kpi:nth-child(4) {{ animation-delay: 0.18s; }}
        .kpi:nth-child(5) {{ animation-delay: 0.24s; }}
        .kpi:nth-child(6) {{ animation-delay: 0.30s; }}

        .kpi span {{
            display: block;
            color: #a9bfd5;
            font-size: 0.76rem;
            font-weight: 950;
            text-transform: uppercase;
        }}

        .kpi strong {{
            display: block;
            color: white;
            font-size: 1.65rem;
            font-weight: 950;
            margin-top: 7px;
        }}

        .kpi.service strong {{ color: #34d399; }}
        .kpi.cost strong {{ color: #fb7185; }}
        .kpi.pipeline strong {{ color: #7dd3fc; }}
        .kpi.backlog strong {{ color: #fbbf24; }}

        @keyframes popIn {{
            from {{ opacity: 0; transform: translateY(12px) scale(0.97); }}
            to {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}

        @keyframes modalIn {{
            from {{ opacity: 0; transform: translateY(20px) scale(0.94); }}
            to {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}

        @keyframes rise {{
            from {{ opacity: 0; transform: translateY(14px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @keyframes confetti {{
            0% {{ opacity: 0; transform: translateY(-20%) rotate(0deg); }}
            12% {{ opacity: 0.55; }}
            100% {{ opacity: 0; transform: translateY(25%) rotate(12deg); }}
        }}

        @media (max-width: 900px) {{
            .hero {{
                grid-template-columns: 1fr;
            }}
            .kpis {{
                grid-template-columns: repeat(2, 1fr);
            }}
            .charts {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
    </head>
    <body>
        <div class="finish">
            <div class="modal">
                <div class="hero">
                    <div class="headline {verdict_class}">
                        <div class="complete-label">Planning horizon complete</div>
                        <div class="complete-title">Game Complete</div>
                        <div class="verdict"><strong>{verdict}</strong><br>{verdict_detail}</div>
                    </div>
                    <div class="kpis">
                        <div class="kpi service"><span>Service level</span><strong>{service_level:.1%}</strong></div>
                        <div class="kpi cost"><span>Total cost</span><strong>{money(cumulative_total_cost)}</strong></div>
                        <div class="kpi cost"><span>Inventory cost</span><strong>{money(total_inventory_cost)}</strong></div>
                        <div class="kpi cost"><span>Backlog cost</span><strong>{money(total_backlog_cost)}</strong></div>
                        <div class="kpi pipeline"><span>Peak pipeline</span><strong>{peak_pipeline:,.0f}</strong></div>
                        <div class="kpi backlog"><span>Peak backlog</span><strong>{peak_backlog:,.0f}</strong></div>
                    </div>
                </div>
                <div class="charts">
                    <div class="chart-card wide">
                        <div class="chart-title">Demand and Order Qty</div>
                        <div class="chart-subtitle">Rolling view: last-year demand history plus months played. Future demand is hidden.</div>
                        <svg viewBox="0 0 720 210" preserveAspectRatio="none">
                            <line class="grid" x1="34" y1="50" x2="686" y2="50"></line>
                            <line class="grid" x1="34" y1="105" x2="686" y2="105"></line>
                            <line class="grid" x1="34" y1="160" x2="686" y2="160"></line>
                            <line class="axis" x1="34" y1="176" x2="686" y2="176"></line>
                            <g class="demand-line">{demand_svg}</g>
                            <g class="order-line">{order_svg}</g>
                        </svg>
                        <div class="legend"><span class="demand">Demand</span><span class="order">Order Qty</span></div>
                    </div>
                    <div class="chart-card">
                        <div class="chart-title">Inventory vs Backlog</div>
                        <div class="chart-subtitle">How the operation recovered or fell behind.</div>
                        <svg viewBox="0 0 720 210" preserveAspectRatio="none">
                            <line class="grid" x1="34" y1="50" x2="686" y2="50"></line>
                            <line class="grid" x1="34" y1="105" x2="686" y2="105"></line>
                            <line class="grid" x1="34" y1="160" x2="686" y2="160"></line>
                            <line class="axis" x1="34" y1="176" x2="686" y2="176"></line>
                            <g class="inventory-line">{inventory_svg}</g>
                            <g class="backlog-line">{backlog_svg}</g>
                        </svg>
                        <div class="legend"><span class="demand">Inventory</span><span class="backlog">Backlog</span></div>
                    </div>
                    <div class="chart-card">
                        <div class="chart-title">Monthly Cost</div>
                        <div class="chart-subtitle">Cost spikes show where planning got expensive.</div>
                        <svg viewBox="0 0 720 210" preserveAspectRatio="none">
                            <line class="grid" x1="34" y1="50" x2="686" y2="50"></line>
                            <line class="grid" x1="34" y1="105" x2="686" y2="105"></line>
                            <line class="grid" x1="34" y1="160" x2="686" y2="160"></line>
                            <line class="axis" x1="34" y1="176" x2="686" y2="176"></line>
                            <g class="cost-line">{cost_svg}</g>
                        </svg>
                    </div>
                </div>
            </div>
        </div>
        <script>
            (() => {{
                const AudioContextClass = window.AudioContext || window.webkitAudioContext;
                if (!AudioContextClass) return;
                const audio = new AudioContextClass();

                function tone(freq, start, duration, type, gainValue) {{
                    const osc = audio.createOscillator();
                    const gain = audio.createGain();
                    osc.type = type;
                    osc.frequency.setValueAtTime(freq, audio.currentTime + start);
                    gain.gain.setValueAtTime(0.0001, audio.currentTime + start);
                    gain.gain.exponentialRampToValueAtTime(gainValue, audio.currentTime + start + 0.02);
                    gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + start + duration);
                    osc.connect(gain);
                    gain.connect(audio.destination);
                    osc.start(audio.currentTime + start);
                    osc.stop(audio.currentTime + start + duration + 0.03);
                }}

                async function fanfare() {{
                    try {{
                        await audio.resume();
                        tone(523, 0.05, 0.14, "triangle", 0.035);
                        tone(659, 0.20, 0.14, "triangle", 0.035);
                        tone(784, 0.35, 0.18, "triangle", 0.035);
                        tone(1046, 0.57, 0.32, "sine", 0.030);
                    }} catch (err) {{}}
                }}

                window.addEventListener("pointerdown", fanfare, {{ once: true }});
                window.setTimeout(fanfare, 160);
            }})();
        </script>
    </body>
    </html>
    """

    st_html(completion_html, height=960)


# =========================================================
# SECTION 7: HEADER
# =========================================================

st.markdown(
    """
<div class="top-title-card">
    <div class="top-title">Spare Parts Planning Game</div>
    <div class="top-subtitle">Place purchase orders, watch the lead-time lane, and keep service high without flooding the warehouse.</div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
<div class="cost-box">
    <div style="font-size:1.05rem; font-weight:800; margin-bottom:8px; color:white;">Cost Logic</div>
    <div class="small-note">Inventory Holding Cost = Ending Inventory x {cfg.holding_cost_per_unit}</div>
    <div class="small-note">Backlog Cost = Ending Backlog x {cfg.backlog_cost_per_unit}</div>
    <div style="margin-top:10px;">
        <span class="cost-chip">Month Total Cost = Inventory Cost + Backlog Cost</span>
        <span class="cost-chip">Lead-time shock: month {cfg.shock_month} to month {cfg.recovery_month - 1}</span>
    </div>
</div>
""",
    unsafe_allow_html=True,
)


# =========================================================
# SECTION 8: PLAYER REGISTRATION
# =========================================================

if not st.session_state.player_ready:
    st.markdown('<div class="dashboard-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Player information</div>', unsafe_allow_html=True)

    name_input = st.text_input("Your name")
    email_input = st.text_input("Your email")

    start_clicked = st.button("Start game", type="primary")

    if start_clicked:
        if not name_input.strip():
            st.error("Please enter your name.")
        elif not valid_email(email_input):
            st.error("Please enter a valid email address.")
        else:
            st.session_state.player_name = name_input.strip()
            st.session_state.player_email = email_input.strip().lower()
            st.session_state.player_ready = True
            init_game()
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

if st.session_state.history and st.session_state.month > cfg.months:
    final_df = pd.DataFrame(st.session_state.history)
    submit_game_result_if_needed(final_df)
    render_completion_summary(final_df)
    st.stop()


# =========================================================
# SECTION 9: TOP STATUS + CONTROLS
# =========================================================

st.caption(f"Player: {st.session_state.player_name} | {st.session_state.player_email}")

month_now = st.session_state.month
month_shown = min(month_now, cfg.months)

play = False
order_qty = int(st.session_state.get("po_qty", 0))

st.markdown('<div class="dashboard-panel">', unsafe_allow_html=True)

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric("Month", month_shown)
m2.metric("Inventory", st.session_state.inventory)
m3.metric("Pipeline", pipeline_total())
m4.metric("Backlog", st.session_state.backlog)
m5.metric("Lead Time", cfg.lead_time(month_shown))

st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="dashboard-panel">', unsafe_allow_html=True)
gameplay_demand_order_chart()
st.markdown(
    """
    <div style="
        margin-top: 12px;
        padding: 14px;
        border: 1px solid rgba(125, 211, 252, 0.20);
        border-radius: 10px;
        background: linear-gradient(90deg, rgba(2,8,18,0.92), rgba(7,18,33,0.92));
    ">
        <div style="font-size:0.82rem; font-weight:900; color:#a9bfd5; text-transform:uppercase; letter-spacing:0.05em;">
            Purchase decision
        </div>
        <div style="font-size:1.05rem; font-weight:900; color:white; margin-top:2px;">
            Choose your PO before this month's demand is revealed.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
po_col, play_col, reset_col = st.columns([1.2, 1, 1])
with po_col:
    order_qty = int(
        st.number_input(
            "PO Qty",
            min_value=0,
            max_value=200,
            step=1,
            key="po_qty",
            help="Stable manual input. It will not jump when demand or backlog changes.",
        )
    )
with play_col:
    st.write("")
    st.write("")
    play = st.button("Play next month", type="primary", use_container_width=True)
with reset_col:
    st.write("")
    st.write("")
    st.button("Reset game", type="secondary", use_container_width=True, on_click=init_game)
st.markdown("</div>", unsafe_allow_html=True)

if play:
    if st.session_state.month <= cfg.months:
        run_month(order_qty)
        st.rerun()
    else:
        st.info("Game finished. Result will be submitted automatically.")

if st.session_state.last_row:
    animate_month(st.session_state.last_row)


# =========================================================
# SECTION 10: KPI SUMMARY
# =========================================================

if st.session_state.history:
    df = pd.DataFrame(st.session_state.history)

    total_need = df["Total Customer Need"].sum()
    total_fulfilled = df["Fulfilled"].sum()
    service_level = total_fulfilled / total_need if total_need > 0 else 0

    total_inventory_cost = df["Inventory Holding Cost"].sum()
    total_backlog_cost = df["Backlog Cost"].sum()
    cumulative_total_cost = df["Cumulative Total Cost"].iloc[-1]

    kpi_html = textwrap.dedent(
        f"""
    <div style="padding:16px; font-family: Arial, sans-serif;">
        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:12px;">
            <div style="background:rgba(7,18,33,0.88); border:1px solid rgba(125,211,252,0.20); border-radius:8px; padding:12px;">
                <div style="color:white; font-size:0.95rem;">Service Level</div>
                <div style="color:white; font-size:1.8rem; font-weight:800;">{service_level:.1%}</div>
            </div>
            <div style="background:rgba(60,10,18,0.92); border:1px solid rgba(255,80,80,0.28); border-radius:8px; padding:12px;">
                <div style="color:white; font-size:0.95rem;">Total Inventory Cost</div>
                <div style="color:#ff6b6b; font-size:1.8rem; font-weight:800;">{total_inventory_cost:,.0f}</div>
            </div>
            <div style="background:rgba(60,10,18,0.92); border:1px solid rgba(255,80,80,0.28); border-radius:8px; padding:12px;">
                <div style="color:white; font-size:0.95rem;">Total Backlog Cost</div>
                <div style="color:#ff6b6b; font-size:1.8rem; font-weight:800;">{total_backlog_cost:,.0f}</div>
            </div>
            <div style="background:rgba(60,10,18,0.92); border:1px solid rgba(255,80,80,0.28); border-radius:8px; padding:12px;">
                <div style="color:white; font-size:0.95rem;">Cumulative Total Cost</div>
                <div style="color:#ff6b6b; font-size:1.8rem; font-weight:800;">{cumulative_total_cost:,.0f}</div>
            </div>
        </div>
    </div>
    """
    )

    st_html(kpi_html, height=150)


# =========================================================
# SECTION 11: TABLE
# =========================================================

if st.session_state.history:
    st.markdown('<div class="dashboard-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Month-by-month table</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True, height=420)
    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# SECTION 12: GRAPH
# =========================================================

if st.session_state.history:
    chart_df = pd.DataFrame(st.session_state.history).set_index("Month")

    st.markdown('<div class="dashboard-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Trends</div>', unsafe_allow_html=True)
    st.line_chart(
        chart_df[
            [
                "Ending Inventory",
                "Ending Backlog",
                "Pipeline",
                "Total Customer Need",
            ]
        ]
    )
    st.markdown("</div>", unsafe_allow_html=True)
