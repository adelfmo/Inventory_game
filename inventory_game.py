import streamlit as st
import random
import pandas as pd
import textwrap
import requests
import re
from streamlit.components.v1 import html


st.set_page_config(page_title="Spare Parts Planning Game", layout="wide")


# =========================================================
# SECTION 1: CUSTOM STYLING
# =========================================================

st.markdown("""
<style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(95, 76, 196, 0.35), transparent 28%),
            radial-gradient(circle at top right, rgba(41, 160, 255, 0.20), transparent 22%),
            linear-gradient(180deg, #0d1430 0%, #12193a 45%, #10162d 100%);
        color: #f4f7ff;
    }

    .block-container {
        padding-top: 1.0rem;
        padding-bottom: 1rem;
        max-width: 1500px;
    }

    h1, h2, h3, p, li, label {
        color: #ffffff !important;
    }

    div[data-testid="stMetric"] {
        background: rgba(9, 18, 48, 0.75);
        border: 1px solid rgba(120, 140, 255, 0.18);
        border-radius: 16px;
        padding: 12px 14px;
        box-shadow: 0 4px 18px rgba(0,0,0,0.18);
    }

    div[data-testid="stMetricLabel"],
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricDelta"] {
        color: #ffffff !important;
    }

    .dashboard-panel {
        background: rgba(7, 14, 35, 0.80);
        border: 1px solid rgba(120, 140, 255, 0.18);
        border-radius: 18px;
        padding: 16px 18px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.22);
        margin-bottom: 14px;
    }

    .top-title-card {
        background: linear-gradient(90deg, rgba(21,31,72,0.95), rgba(14,20,53,0.9));
        border: 1px solid rgba(132, 156, 255, 0.18);
        border-radius: 18px;
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
        color: #ffffff;
        font-size: 1rem;
        margin-bottom: 0;
    }

    .cost-box {
        background: rgba(9, 20, 52, 0.92);
        border: 1px solid rgba(113, 145, 255, 0.20);
        border-radius: 16px;
        padding: 14px 18px;
        color: #eef2ff;
        margin-bottom: 14px;
    }

    .cost-chip {
        display: inline-block;
        padding: 7px 12px;
        border-radius: 10px;
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.08);
        margin-right: 8px;
        margin-top: 6px;
        font-family: monospace;
        font-size: 0.95rem;
        color: white;
    }

    .small-note {
        color: #ffffff;
        font-size: 0.95rem;
    }

    div.stButton > button {
        border-radius: 12px;
        font-weight: 700;
        border: none;
        min-height: 2.5rem;
    }

    .section-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: white;
        margin-bottom: 10px;
        margin-top: 6px;
    }
</style>
""", unsafe_allow_html=True)


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
        elif month == 4:
            return rng.randint(48, 52)
        elif month == 5:
            return rng.randint(54, 60)
        elif month in [6, 7]:
            return rng.randint(25, 35)
        elif month == 8:
            return rng.randint(51, 55)
        elif 9 <= month <= 12:
            return rng.randint(18, 27)
        elif 13 <= month <= 18:
            return rng.randint(12, 20)
        elif 19 <= month <= 24:
            return rng.randint(15, 23)
        return 0


cfg = Config()

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzxU3TxvbZ7QbQ8qBCueem9uVF0rHDND_gt6xLxnXmfEI7tp3lzJ6J3lg5GM0qmwE_R/exec"


# =========================================================
# SECTION 3: STATE
# =========================================================

def init_game():
    st.session_state.month = 1
    st.session_state.inventory = cfg.initial_inventory
    st.session_state.pipeline = []
    st.session_state.backlog = 0
    st.session_state.cumulative_cost = 0.0
    st.session_state.history = []
    st.session_state.submitted = False


if "player_ready" not in st.session_state:
    st.session_state.player_ready = False
    st.session_state.player_name = ""
    st.session_state.player_email = ""

if "month" not in st.session_state:
    init_game()


# =========================================================
# SECTION 4: HELPERS
# =========================================================

def valid_email(email):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()) is not None


def pipeline_total():
    return sum(x["qty"] for x in st.session_state.pipeline)


def grouped_icons_html(qty, icon="📦", group_size=5, max_icons=10):
    if qty <= 0:
        return "—"
    n = max(1, min(max_icons, round(qty / group_size)))
    return " ".join([icon] * n)


def render_node_html(title, subtitle, qty, icon, border_color):
    icons = grouped_icons_html(qty, icon=icon)
    return f"""
        <div class="node" style="
            border: 2px solid {border_color};
            border-radius: 18px;
            padding: 14px;
            min-height: 180px;
            text-align: center;
            background: linear-gradient(180deg, rgba(15,20,32,0.96), rgba(10,14,26,0.96));
            position: relative;
            z-index: 2;
            box-shadow: 0 8px 28px rgba(0,0,0,0.35);
        ">
            <div style="font-size: 1.9rem; font-weight: 800; margin-bottom: 4px; color: #ffffff;">{title}</div>
            <div style="color: #ffffff; font-size: 0.88rem; margin-bottom: 12px;">{subtitle}</div>
            <div style="font-size: 1.8rem; min-height: 60px; line-height: 1.55;">{icons}</div>
            <div style="font-size: 2.15rem; font-weight: 900; margin-top: 10px; color: #ffffff;">{qty}</div>
        </div>
    """


def submit_result_to_google_sheet(payload):
    response = requests.post(
        GOOGLE_SCRIPT_URL,
        json=payload,
        timeout=10
    )
    return response


# =========================================================
# SECTION 5: GAME LOGIC
# =========================================================

def run_month(order_qty):
    month = st.session_state.month
    lead_time = cfg.lead_time(month)

    incoming = sum(x["qty"] for x in st.session_state.pipeline if x["arrival"] == month)
    st.session_state.pipeline = [x for x in st.session_state.pipeline if x["arrival"] != month]

    new_demand = cfg.demand(month)
    backlog_before = st.session_state.backlog
    total_customer_need = new_demand + backlog_before

    starting_inventory = st.session_state.inventory
    inventory_after_incoming = starting_inventory + incoming

    fulfilled = min(inventory_after_incoming, total_customer_need)
    ending_inventory = inventory_after_incoming - fulfilled
    ending_backlog = total_customer_need - fulfilled

    backlog_this_period = max(0, new_demand - min(inventory_after_incoming, new_demand))

    if order_qty > 0:
        st.session_state.pipeline.append({
            "arrival": month + lead_time,
            "qty": order_qty
        })

    current_pipeline = pipeline_total()

    inventory_holding_cost = ending_inventory * cfg.holding_cost_per_unit
    backlog_cost = ending_backlog * cfg.backlog_cost_per_unit
    month_total_cost = inventory_holding_cost + backlog_cost

    st.session_state.cumulative_cost += month_total_cost

    row = {
        "Month": month,
        "Lead Time": lead_time,
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
        "Pipeline": current_pipeline,
        "Inventory Holding Cost": round(inventory_holding_cost, 2),
        "Backlog Cost": round(backlog_cost, 2),
        "Month Total Cost": round(month_total_cost, 2),
        "Cumulative Total Cost": round(st.session_state.cumulative_cost, 2),
    }

    st.session_state.history.append(row)
    st.session_state.inventory = ending_inventory
    st.session_state.backlog = ending_backlog
    st.session_state.month += 1

    return row


# =========================================================
# SECTION 6: ANIMATION
# =========================================================

def animate_month(row):
    supplier_node = render_node_html(
        "📦 Supplier",
        "On order / future arrivals",
        row["Pipeline"],
        "📦",
        "#7e57ff"
    )

    inventory_node = render_node_html(
        "🏭 Inventory",
        "Stock after incoming",
        row["Inventory After Incoming"],
        "🔩",
        "#1fd0c1"
    )

    customer_node = render_node_html(
        "👥 Customers",
        "Current demand",
        row["New Demand"],
        "🧍",
        "#ffb347"
    )

    animation_html = f"""
    <html>
    <head>
    <style>
        body {{
            margin: 0;
            font-family: Arial, sans-serif;
            background: transparent;
            color: white;
        }}

        .wrap {{
            border: 1px solid rgba(129, 149, 255, 0.18);
            border-radius: 20px;
            padding: 16px;
            background:
                radial-gradient(circle at top left, rgba(86,72,194,0.20), transparent 22%),
                linear-gradient(180deg, rgba(5,9,18,0.98), rgba(6,9,17,0.98));
            box-shadow: 0 16px 38px rgba(0,0,0,0.34);
            min-height: 560px;
        }}

        .title {{
            font-size: 2rem;
            font-weight: 800;
            margin-bottom: 4px;
            color: #ffffff;
        }}

        .subtitle {{
            color: #ffffff;
            margin-bottom: 14px;
            font-size: 1rem;
        }}

        .flow {{
            display: grid;
            grid-template-columns: 1fr 70px 1fr 70px 1fr;
            align-items: start;
            gap: 10px;
            position: relative;
            min-height: 440px;
        }}

        .col {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        .arrow {{
            text-align: center;
            font-size: 2rem;
            color: #ffffff;
            padding-top: 95px;
        }}

        .arrow-label {{
            font-size: 0.82rem;
            color: #ffffff;
            margin-top: 3px;
            font-weight: 700;
        }}

        .moving1 {{
            position: absolute;
            top: 82px;
            left: 11%;
            font-size: 1.9rem;
            opacity: 0;
            animation: supplier_to_inventory 1.2s ease-in-out forwards;
        }}

        .moving2 {{
            position: absolute;
            top: 165px;
            left: 45%;
            font-size: 1.9rem;
            opacity: 0;
            animation: inventory_to_customers 1.2s ease-in-out forwards;
            animation-delay: 1.1s;
        }}

        .demand-pop {{
            position: absolute;
            top: 20px;
            right: 6%;
            font-size: 1.9rem;
            opacity: 0;
            animation: demand_appear 0.8s ease forwards;
            animation-delay: 0.65s;
        }}

        @keyframes supplier_to_inventory {{
            0% {{ left: 11%; opacity: 0; }}
            10% {{ opacity: 1; }}
            100% {{ left: 41%; opacity: 1; }}
        }}

        @keyframes inventory_to_customers {{
            0% {{ left: 45%; opacity: 0; }}
            10% {{ opacity: 1; }}
            100% {{ left: 78%; opacity: 1; }}
        }}

        @keyframes demand_appear {{
            0% {{ opacity: 0; transform: scale(0.55); }}
            100% {{ opacity: 1; transform: scale(1); }}
        }}

        .mini-grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }}

        .mini-grid-3,
        .mini-grid-4 {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 8px;
        }}

        .mini {{
            border: 1px solid rgba(129, 149, 255, 0.14);
            border-radius: 12px;
            background: rgba(12, 19, 43, 0.88);
            padding: 8px;
            text-align: center;
            min-height: 62px;
        }}

        .mini-label {{
            font-size: 0.73rem;
            color: #ffffff;
            line-height: 1.15;
        }}

        .mini-value {{
            font-size: 1.2rem;
            font-weight: 900;
            margin-top: 5px;
            color: white;
        }}

        .cost-mini {{
            border: 1px solid rgba(255, 80, 80, 0.28);
            background: rgba(60, 10, 18, 0.92);
        }}

        .cost-value {{
            color: #ff6b6b !important;
        }}
    </style>
    </head>
    <body>
        <div class="wrap">
            <div class="title">Month {row["Month"]} flow</div>
            <div class="subtitle">Lead time this month: {row["Lead Time"]} month(s)</div>

            <div class="flow">
                <div class="moving1">📦 📦 📦</div>
                <div class="moving2">🔩 🔩 🔩</div>
                <div class="demand-pop">🧍 🧍 🧍</div>

                <div class="col">
                    {supplier_node}
                    <div class="mini-grid-2">
                        <div class="mini">
                            <div class="mini-label">Pipeline</div>
                            <div class="mini-value">{row["Pipeline"]}</div>
                        </div>
                        <div class="mini">
                            <div class="mini-label">Lead Time</div>
                            <div class="mini-value">{row["Lead Time"]}</div>
                        </div>
                    </div>
                </div>

                <div class="arrow">➡️<div class="arrow-label">Incoming</div></div>

                <div class="col">
                    {inventory_node}
                    <div class="mini-grid-3">
                        <div class="mini">
                            <div class="mini-label">Stock After Incoming</div>
                            <div class="mini-value">{row["Inventory After Incoming"]}</div>
                        </div>
                        <div class="mini">
                            <div class="mini-label">Ending Inventory</div>
                            <div class="mini-value">{row["Ending Inventory"]}</div>
                        </div>
                        <div class="mini cost-mini">
                            <div class="mini-label">Inventory Cost</div>
                            <div class="mini-value cost-value">{int(row["Inventory Holding Cost"])}</div>
                        </div>
                    </div>
                </div>

                <div class="arrow">➡️<div class="arrow-label">Serve</div></div>

                <div class="col">
                    {customer_node}
                    <div class="mini-grid-4">
                        <div class="mini">
                            <div class="mini-label">Fulfilled</div>
                            <div class="mini-value">{row["Fulfilled"]}</div>
                        </div>
                        <div class="mini">
                            <div class="mini-label">Backlog This Period</div>
                            <div class="mini-value">{row["Backlog This Period"]}</div>
                        </div>
                        <div class="mini">
                            <div class="mini-label">Total Backlog</div>
                            <div class="mini-value">{row["Ending Backlog"]}</div>
                        </div>
                        <div class="mini cost-mini">
                            <div class="mini-label">Total Backlog Cost</div>
                            <div class="mini-value cost-value">{int(row["Backlog Cost"])}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    html(animation_html, height=720)


# =========================================================
# SECTION 7: HEADER
# =========================================================

st.markdown("""
<div class="top-title-card">
    <div class="top-title">📊 Spare Parts Planning Game</div>
    <div class="top-subtitle">Plan your purchases, manage inventory, and minimize total cost.</div>
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="cost-box">
    <div style="font-size:1.05rem; font-weight:800; margin-bottom:8px; color:white;">Cost Logic</div>
    <div class="small-note">• Inventory Holding Cost = Ending Inventory × {cfg.holding_cost_per_unit}</div>
    <div class="small-note">• Backlog Cost = Ending Backlog × {cfg.backlog_cost_per_unit}</div>
    <div style="margin-top:10px;">
        <span class="cost-chip">Month Total Cost = (Ending Inventory × {cfg.holding_cost_per_unit}) + (Ending Backlog × {cfg.backlog_cost_per_unit})</span>
        <span class="cost-chip">Cumulative Total Cost = Sum of all monthly total costs</span>
    </div>
</div>
""", unsafe_allow_html=True)


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

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# =========================================================
# SECTION 9: TOP STATUS + CONTROLS
# =========================================================

st.caption(f"Player: {st.session_state.player_name} | {st.session_state.player_email}")

month_now = st.session_state.month
month_shown = min(month_now, cfg.months)

st.markdown('<div class="dashboard-panel">', unsafe_allow_html=True)

m1, m2, m3, m4, m5, ctrl = st.columns([1, 1, 1, 1, 1, 2.2])

m1.metric("Month", month_shown)
m2.metric("Inventory", st.session_state.inventory)
m3.metric("Pipeline", pipeline_total())
m4.metric("Backlog", st.session_state.backlog)
m5.metric("Lead Time", cfg.lead_time(month_shown))

with ctrl:
    order_qty = st.slider("PO Qty", 0, 200, 0, 1)
    cb1, cb2 = st.columns(2)
    with cb1:
        play = st.button("▶ Play next month", type="primary", use_container_width=True)
    with cb2:
        reset = st.button("↻ Reset game", type="secondary", use_container_width=True)

st.markdown('</div>', unsafe_allow_html=True)

if month_now <= cfg.months:
    st.caption(f"Demand for month {month_shown}: {cfg.demand(month_shown)}")

if month_now == cfg.shock_month:
    st.warning(f"Lead time shock starts now: lead time increased from {cfg.initial_lead_time} to {cfg.shocked_lead_time}.")
elif month_now == cfg.recovery_month:
    st.success(f"Lead time recovery starts now: lead time returns to {cfg.initial_lead_time}.")

if reset:
    init_game()
    st.rerun()

if play:
    if st.session_state.month <= cfg.months:
        row = run_month(order_qty)
        animate_month(row)
    else:
        st.info("Game finished. Result will be submitted automatically.")


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

    kpi_html = textwrap.dedent(f"""
    <div style="padding:16px; font-family: Arial, sans-serif;">
        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:12px;">
            <div style="background:rgba(9,18,48,0.85); border:1px solid rgba(120,140,255,0.18); border-radius:16px; padding:12px;">
                <div style="color:white; font-size:0.95rem;">Service Level</div>
                <div style="color:white; font-size:1.8rem; font-weight:800;">{service_level:.1%}</div>
            </div>
            <div style="background:rgba(60,10,18,0.92); border:1px solid rgba(255,80,80,0.28); border-radius:16px; padding:12px;">
                <div style="color:white; font-size:0.95rem;">Total Inventory Cost</div>
                <div style="color:#ff6b6b; font-size:1.8rem; font-weight:800;">{total_inventory_cost:,.0f}</div>
            </div>
            <div style="background:rgba(60,10,18,0.92); border:1px solid rgba(255,80,80,0.28); border-radius:16px; padding:12px;">
                <div style="color:white; font-size:0.95rem;">Total Backlog Cost</div>
                <div style="color:#ff6b6b; font-size:1.8rem; font-weight:800;">{total_backlog_cost:,.0f}</div>
            </div>
            <div style="background:rgba(60,10,18,0.92); border:1px solid rgba(255,80,80,0.28); border-radius:16px; padding:12px;">
                <div style="color:white; font-size:0.95rem;">Cumulative Total Cost</div>
                <div style="color:#ff6b6b; font-size:1.8rem; font-weight:800;">{cumulative_total_cost:,.0f}</div>
            </div>
        </div>
    </div>
    """)

    html(kpi_html, height=150)


# =========================================================
# SECTION 11: AUTO-SUBMIT WHEN GAME ENDS
# =========================================================

if (
    st.session_state.history
    and st.session_state.month > cfg.months
    and not st.session_state.submitted
):
    df = pd.DataFrame(st.session_state.history)

    total_need = df["Total Customer Need"].sum()
    total_fulfilled = df["Fulfilled"].sum()
    service_level = total_fulfilled / total_need if total_need > 0 else 0

    total_inventory_cost = df["Inventory Holding Cost"].sum()
    total_backlog_cost = df["Backlog Cost"].sum()
    cumulative_total_cost = df["Cumulative Total Cost"].iloc[-1]

    payload = {
        "player_name": st.session_state.player_name,
        "player_email": st.session_state.player_email,
        "service_level": round(service_level * 100, 1),
        "total_inventory_cost": round(total_inventory_cost, 0),
        "total_backlog_cost": round(total_backlog_cost, 0),
        "cumulative_total_cost": round(cumulative_total_cost, 0),
        "months_played": len(st.session_state.history)
    }

    try:
        response = submit_result_to_google_sheet(payload)

        if response.status_code == 200:
            st.session_state.submitted = True
            st.success("Your result has been submitted.")
        else:
            st.error("Result submission failed.")

    except Exception as e:
        st.error(f"Submission failed: {e}")


# =========================================================
# SECTION 12: TABLE
# =========================================================

if st.session_state.history:
    st.markdown('<div class="dashboard-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Month-by-month table</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True, height=420)
    st.markdown('</div>', unsafe_allow_html=True)


# =========================================================
# SECTION 13: GRAPH
# =========================================================

if st.session_state.history:
    chart_df = pd.DataFrame(st.session_state.history).set_index("Month")

    st.markdown('<div class="dashboard-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Trends</div>', unsafe_allow_html=True)
    st.line_chart(chart_df[[
        "Ending Inventory",
        "Ending Backlog",
        "Pipeline",
        "Total Customer Need"
    ]])
    st.markdown('</div>', unsafe_allow_html=True)