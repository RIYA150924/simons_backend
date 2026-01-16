import streamlit as st
import ccxt
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import requests
import time
import base64
from datetime import datetime, timedelta
import jwt
from urllib.parse import urlparse, parse_qs


# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    layout="wide", 
    page_title="Simons",
    page_icon="🧬",
    initial_sidebar_state="expanded"
)

# ================== AUTH GUARD (DO NOT TOUCH ANYTHING ELSE) ==================

BACKEND_URL = "http://localhost:8000"

# Read token from URL: http://localhost:8501?token=xxxx
query_params = st.experimental_get_query_params()
token = query_params.get("token", [None])[0]

def verify_token(token):
    try:
        r = requests.get(
            f"{BACKEND_URL}/verify-token",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        return r.status_code == 200
    except:
        return False

if not token:
    st.error("❌ Access Denied: Token missing. Please login from the main app.")
    st.stop()

if not verify_token(token):
    st.error("❌ Invalid or Expired Token. Please login again.")
    st.stop()

# ============================================================================ 


# --- 2. STATE MANAGEMENT & AUTO-FIX ---
if 'active_trade' not in st.session_state: st.session_state.active_trade = None 
if 'news_cache' not in st.session_state: st.session_state.news_cache = []
if 'last_news_fetch' not in st.session_state: st.session_state.last_news_fetch = datetime.min
if 'show_calc' not in st.session_state: st.session_state.show_calc = False
if 'last_alert_signal' not in st.session_state: st.session_state.last_alert_signal = "MONITORING" 

# [AUTO-FIX] Force symbol reset if stuck on old Binance format
if 'symbol' not in st.session_state or 'USDT' in st.session_state.symbol:
    st.session_state.symbol = 'BTC/USD'

# --- 3. VISUAL ENGINE ---
st.markdown("""
<style>
    /* IMPORTS */
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@900&family=Rajdhani:wght@300;500;700&family=JetBrains+Mono:wght@400;700&family=Inter:wght@300;400;600&display=swap');
    
    /* PALETTE */
    :root {
        --glass-surface: rgba(20, 25, 30, 0.6);
        --glass-border: rgba(255, 255, 255, 0.08);
        --neon-cyan: #00F0FF;
        --neon-danger: #FF2A6D;
        --neon-success: #05FFA1;
        --tech-grey: #9ca3af;
        --void-bg: #050505;
    }

    /* BACKGROUND STRUCTURE */
    .stApp { 
        background-color: var(--void-bg);
        background-image: 
            linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px), 
            linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
        background-size: 50px 50px;
        font-family: 'Inter', sans-serif;
    }
    
    /* Z-INDEX FIX */
    .stApp::after {
        content: ""; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: linear-gradient(to bottom, rgba(0,243,255,0) 50%, rgba(0,243,255,0.02) 50%);
        background-size: 100% 4px;
        animation: scanline 20s linear infinite;
        pointer-events: none;
        z-index: 0; 
    }
    @keyframes scanline { 0% { transform: translateY(-100%); } 100% { transform: translateY(100%); } }

    /* CONTENT LAYERING */
    .main .block-container { padding-top: 1rem; padding-bottom: 5rem; z-index: 10; position: relative; }
    
    /* CARDS */
    .metric-card {
        background: var(--glass-surface);
        border: 1px solid var(--glass-border);
        padding: 20px; position: relative;
        backdrop-filter: blur(10px);
    }
    .metric-card::before {
        content: ''; position: absolute; top: -1px; left: -1px; width: 10px; height: 10px;
        border-top: 2px solid var(--neon-cyan); border-left: 2px solid var(--neon-cyan);
    }
    
    /* TYPOGRAPHY */
    h1, h2, h3 { font-family: 'Rajdhani', sans-serif !important; text-transform: uppercase; letter-spacing: 2px; color: #fff; }
    .metric-label { font-family: 'Inter'; font-size: 11px; color: var(--tech-grey); text-transform: uppercase; letter-spacing: 1px; }
    .metric-value { font-family: 'Rajdhani'; font-size: 32px; color: #fff; font-weight: 500; }

    /* HEADER */
    .arch-header {
        font-size: 2.5rem; color: #fff;
        border-left: 4px solid var(--neon-cyan);
        padding-left: 20px; margin-bottom: 10px;
    }

    /* SIDEBAR */
    section[data-testid="stSidebar"] { background-color: #000; border-right: 1px solid var(--glass-border); z-index: 20; }
    
    /* PLAIN 2D LOGO */
    .sidebar-logo {
        font-family: 'Orbitron', sans-serif;
        font-size: 34px;
        font-weight: 900;
        text-align: center;
        color: #fff;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 25px;
    }
    
    /* BUTTONS */
    .stButton > button {
        background: transparent; border: 1px solid var(--glass-border);
        color: var(--tech-grey); font-family: 'Rajdhani'; font-weight: 600;
        text-transform: uppercase; border-radius: 0; transition: all 0.3s;
    }
    .stButton > button:hover { border-color: var(--neon-cyan); color: var(--neon-cyan); background: rgba(0, 240, 255, 0.05); }
    div[data-testid="column"]:nth-of-type(1) .stButton > button { border-left: 3px solid var(--neon-success); }
    div[data-testid="column"]:nth-of-type(2) .stButton > button { border-left: 3px solid var(--neon-danger); }

    /* EXPANDER STYLING */
    .streamlit-expanderHeader {
        background-color: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid #333 !important;
        border-radius: 4px !important;
        color: #fff !important;
        font-family: 'Rajdhani', sans-serif !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
    }
    .streamlit-expanderHeader:hover {
        border-color: var(--neon-cyan) !important;
        color: var(--neon-cyan) !important;
    }
    .streamlit-expanderContent {
        background-color: transparent !important;
        border: 1px solid #222 !important;
        border-top: none !important;
        padding: 15px !important;
    }

    /* PANELS */
    .calc-panel, .backtest-panel, .tutorial-panel {
        background: rgba(0,0,0,0.8); border: 1px solid var(--neon-cyan);
        padding: 20px; margin-bottom: 20px; border-radius: 4px;
    }
    
    /* DATAFRAME */
    div[data-testid="stDataFrame"] { border: 1px solid #333; }

    /* TICKER */
    .ticker-wrap {
        position: fixed; bottom: 0; left: 0; width: 100%;
        background-color: rgba(5, 5, 5, 0.95);
        border-top: 1px solid var(--neon-cyan);
        color: #fff; font-family: 'JetBrains Mono', monospace;
        font-size: 12px; line-height: 30px; height: 30px;
        overflow: hidden; z-index: 100; white-space: nowrap;
        pointer-events: auto;
    }
    .ticker { display: inline-block; padding-left: 100%; animation: marquee 60s linear infinite; }
    .ticker-item { display: inline-block; padding: 0 2rem; color: #ccc; cursor: pointer; }
    .ticker-item strong { color: var(--neon-cyan); }
    @keyframes marquee { 0% { transform: translate3d(0, 0, 0); } 100% { transform: translate3d(-100%, 0, 0); } }
    .ticker-wrap:hover .ticker { animation-play-state: paused !important; }
    
    /* ORDER FLOW WIDGETS */
    .orderflow-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #222; font-family: 'JetBrains Mono'; font-size: 11px; }
    .whale-alert { background: rgba(0, 240, 255, 0.1); border: 1px solid var(--neon-cyan); padding: 10px; margin-top: 10px; font-size: 12px; color: #fff; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- 4. DATA ENGINE (FIXED FOR KRAKEN COLUMNS) ---

@st.cache_data(ttl=5) 
def get_market_data(sym, tf, window, limit=300):
    try:
        exchange = ccxt.kraken({'enableRateLimit': True}) 
        bars = exchange.fetch_ohlcv(sym, timeframe=tf, limit=limit)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
        if not df.empty:
            df['Mean'] = df['close'].rolling(window).mean()
            df['StdDev'] = df['close'].rolling(window).std()
            df['Z_Score'] = (df['close'] - df['Mean']) / df['StdDev']
            df['Prev_StdDev'] = df['StdDev'].shift(1)
            df['Vol_Expansion'] = df['StdDev'] > (df['Prev_StdDev'] * 1.4)
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)

@st.cache_data(ttl=5)
def get_order_book(sym):
    try:
        exchange = ccxt.kraken({'enableRateLimit': True})
        ob = exchange.fetch_order_book(sym, limit=20)
        
        # --- KRAKEN FIX: Accept 3 columns (Price, Size, Timestamp) ---
        bids = pd.DataFrame(ob['bids'], columns=['price', 'size', 'timestamp'])
        asks = pd.DataFrame(ob['asks'], columns=['price', 'size', 'timestamp'])
        # -------------------------------------------------------------
        
        bid_vol = bids['size'].sum(); ask_vol = asks['size'].sum()
        total = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / total if total > 0 else 0
        return bids, asks, imbalance, bid_vol, ask_vol, None 
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), 0, 0, 0, str(e)

@st.cache_data(ttl=300) 
def calculate_volume_profile(df, bins=40):
    if df.empty: return pd.DataFrame()
    p_min = df['low'].min(); p_max = df['high'].max()
    bin_size = (p_max - p_min) / bins
    df['bin'] = ((df['close'] - p_min) / bin_size).astype(int)
    vp = df.groupby('bin')['volume'].sum().reset_index()
    vp['price_level'] = p_min + (vp['bin'] * bin_size)
    vp['norm_vol'] = vp['volume'] / vp['volume'].max()
    return vp

def get_crypto_news(symbol):
    now = datetime.now()
    if now - st.session_state.last_news_fetch > timedelta(minutes=5):
        try:
            url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
            data = requests.get(url).json().get('Data', [])[:10]
            st.session_state.news_cache = [f"[{i['source_info']['name']}] {i['title']}" for i in data]
            st.session_state.last_news_fetch = now
        except: pass
    return st.session_state.news_cache

# --- 5. ALERT SYSTEM ---

def send_telegram_alert(token, chat_id, message):
    if not token or not chat_id: return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.get(url, params=params)
    except: pass

# --- 6. VISUALIZATION FUNCTIONS ---

def render_volume_profile(fig, vp_df, min_time, max_time):
    if vp_df.empty: return fig
    time_span = (max_time - min_time).total_seconds() * 1000
    base_width = time_span * 0.15 
    for index, row in vp_df.iterrows():
        fig.add_shape(type="rect", x0=max_time - timedelta(milliseconds=base_width * row['norm_vol']), x1=max_time, y0=row['price_level'], y1=row['price_level'] + (row['price_level']*0.003), fillcolor="rgba(0, 240, 255, 0.1)", line=dict(color="rgba(0, 240, 255, 0.3)", width=1), layer="below")
    return fig

# --- 7. BACKTEST ENGINE & REPORTING ---

def run_backtest(df, entry_z):
    balance = 1000
    equity = [balance]
    position = 0; entry_price = 0; trades = []
    
    for i in range(20, len(df)):
        row = df.iloc[i]
        z = row['Z_Score']; price = row['close']; ts = row['timestamp']
        if pd.isna(z): continue
        
        if position == 0:
            if z < -entry_z:
                position = 1; entry_price = price
                trades.append({'Date': ts, 'Type': 'LONG', 'Entry': price, 'Exit': np.nan, 'PnL': np.nan, 'Result': 'OPEN'})
            elif z > entry_z:
                position = -1; entry_price = price
                trades.append({'Date': ts, 'Type': 'SHORT', 'Entry': price, 'Exit': np.nan, 'PnL': np.nan, 'Result': 'OPEN'})
        elif position == 1: # Long
            if z > -0.5: 
                pnl_pct = (price - entry_price) / entry_price * 100
                balance = balance * (1 + pnl_pct/100)
                trades[-1]['Exit'] = price; trades[-1]['PnL'] = round(pnl_pct, 2); trades[-1]['Result'] = 'WIN' if pnl_pct > 0 else 'LOSS'
                position = 0
        elif position == -1: # Short
            if z < 0.5:
                pnl_pct = (entry_price - price) / entry_price * 100
                balance = balance * (1 + pnl_pct/100)
                trades[-1]['Exit'] = price; trades[-1]['PnL'] = round(pnl_pct, 2); trades[-1]['Result'] = 'WIN' if pnl_pct > 0 else 'LOSS'
                position = 0
        equity.append(balance)
    
    trade_df = pd.DataFrame(trades)
    if not trade_df.empty: trade_df = trade_df.dropna()
    return trade_df, equity

def generate_html_report(symbol, timeframe, metrics, trade_df):
    html = f"""<html><head><style>body{{background:#050505;color:#e0e0e0;font-family:'Courier New',monospace;padding:40px;}}h1{{color:#00F0FF;border-bottom:2px solid #00F0FF;}}table{{width:100%;border-collapse:collapse;margin-top:20px;border:1px solid #333;}}th,td{{border:1px solid #333;padding:12px;}}th{{background:#1a1a1a;color:#00F0FF;}}.WIN{{color:#05FFA1;}}.LOSS{{color:#FF2A6D;}}</style></head><body><h1>SIMONS // REPORT</h1><div>SYMBOL: {symbol} | TF: {timeframe}</div><br><div>NET PROFIT: {metrics['ret']:.2f}% | WIN RATE: {metrics['wr']:.1f}%</div><table><thead><tr><th>DATE</th><th>TYPE</th><th>ENTRY</th><th>EXIT</th><th>PNL</th></tr></thead><tbody>"""
    for i, r in trade_df.iterrows(): html += f"<tr><td>{r['Date']}</td><td>{r['Type']}</td><td>{r['Entry']:.2f}</td><td>{r['Exit']:.2f}</td><td class='{r['Result']}'>{r['PnL']}%</td></tr>"
    html += "</tbody></table></body></html>"
    return html

# --- 8. SIDEBAR ---
with st.sidebar:
    # PLAIN 2D LOGO
    st.markdown('<div class="sidebar-logo">Simons</div>', unsafe_allow_html=True)
    st.caption(f"SERVER TIME: {datetime.now().strftime('%H:%M:%S UTC')}")
    
    menu = st.radio("MODULE", ["LIVE FEED", "STRATEGY LAB", "TUTORIAL"], label_visibility="collapsed")
    st.markdown("---")
    
    # --- 1. STRATEGY PARAMETERS MENU ---
    with st.expander("⚙️ STRATEGY PARAMETERS", expanded=True):
        timeframe = st.selectbox("TIMEFRAME", ["15m", "1h", "4h"], index=0)
        st.caption("✨ use on 15m ( best suitable ) or at max 1H")
        window = st.slider("WINDOW (n)", 10, 50, 20)
        entry_z = st.slider("THRESHOLD (z)", 1.5, 3.5, 2.0)
    
    # --- 2. INSTITUTIONAL ORDER FLOW MENU ---
    with st.expander("🌊 INSTITUTIONAL FLOW", expanded=False):
        bids, asks, imb, b_vol, a_vol, flow_err = get_order_book(st.session_state.symbol)
        
        if not bids.empty:
            wall_msg = "NEUTRAL LIQUIDITY"
            wall_color = "#888"
            if b_vol > a_vol * 1.5: wall_msg = "🐋 BUY WALL DETECTED"; wall_color = "#05FFA1"
            elif a_vol > b_vol * 1.5: wall_msg = "🐋 SELL WALL DETECTED"; wall_color = "#FF2A6D"
            
            st.markdown(f"<div class='whale-alert' style='border-color:{wall_color}; color:{wall_color}'>{wall_msg}</div>", unsafe_allow_html=True)
            
            imb_pct = int(((imb + 1) / 2) * 100)
            st.caption(f"IMBALANCE: {imb_pct}% BUY")
            st.progress(imb_pct / 100)
            
            st.caption("L2 DEPTH")
            for i in range(5):
                b_s = bids.iloc[i]['size']; a_s = asks.iloc[i]['size']
                b_c = "#05FFA1" if b_s > b_vol*0.1 else "#555"
                a_c = "#FF2A6D" if a_s > a_vol*0.1 else "#555"
                st.markdown(f"""<div class="orderflow-row"><span style="color:{b_c}">{b_s:.2f}</span><span style="color:#444">|</span><span style="color:{a_c}">{a_s:.2f}</span></div>""", unsafe_allow_html=True)
        else:
            st.error("OFFLINE")
            if flow_err: st.caption(f"Debug: {flow_err}")
            
    # --- 3. ASSET SELECTION MENU ---
    with st.expander("🪙 ASSET SELECTION", expanded=False):
        wl = ["BTC/USD", "ETH/USD", "SOL/USD"] 
        for s in wl:
            if st.button(f"{s}", key=s): 
                st.session_state.symbol = s
                st.rerun()

    # --- 4. ALERTS MENU ---
    with st.expander("🔔 TELEGRAM ALERTS", expanded=False):
        tg_token = st.text_input("Bot Token", type="password")
        tg_chat = st.text_input("Chat ID")
        st.caption("Enter credentials to receive instant signals.")

    if menu == "LIVE FEED":
        st.markdown("---")
        enable_refresh = st.toggle("⚡ LIVE MODE (5s)", value=True)

# --- 9. MAIN APP ---

if menu == "LIVE FEED":
    col_head, col_btn = st.columns([4, 1])
    with col_head:
        st.markdown(f"""<div class="arch-header">{st.session_state.symbol} <span style="font-weight:300; opacity:0.5">// REAL-TIME</span></div>""", unsafe_allow_html=True)
    with col_btn:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄", help="Manual Refresh"): st.rerun()
        with c2:
            if st.button("🧮", help="Toggle Calculator"): 
                st.session_state.show_calc = not st.session_state.show_calc
                st.rerun()
            
    df, err = get_market_data(st.session_state.symbol, timeframe, window)
    current_p = df['close'].iloc[-1] if not df.empty else 0

    if st.session_state.show_calc:
        st.markdown('<div class="calc-panel">', unsafe_allow_html=True)
        st.markdown("### 🧮 POSITION SIZE CALCULATOR")
        if enable_refresh: st.caption("⚠️ Turn OFF 'Live Mode' to type comfortably.")
        c_calc1, c_calc2, c_calc3, c_calc4 = st.columns(4)
        with c_calc1: account_bal = st.number_input("Account Balance ($)", value=1000.0)
        with c_calc2: risk_pct = st.number_input("Risk (%)", value=1.0, step=0.1)
        with c_calc3: entry_p = st.number_input("Entry Price ($)", value=float(current_p))
        with c_calc4: stop_loss = st.number_input("Stop Loss ($)", value=float(current_p * 0.99))
        
        if entry_p > 0 and stop_loss > 0 and entry_p != stop_loss:
            risk_amt = account_bal * (risk_pct / 100)
            price_diff = abs(entry_p - stop_loss)
            pos_size_units = risk_amt / price_diff
            pos_val_usd = pos_size_units * entry_p
            st.markdown("---")
            res1, res2, res3 = st.columns(3)
            with res1: st.metric("RISK AMOUNT", f"${risk_amt:.2f}")
            with res2: st.metric("POSITION SIZE", f"{pos_size_units:.4f}")
            with res3: st.metric("TOTAL VALUE", f"${pos_val_usd:.2f}")
        st.markdown('</div>', unsafe_allow_html=True)

    news_list = get_crypto_news(st.session_state.symbol)
    news_html = "".join([f'<div class="ticker-item"><strong>>></strong> {n}</div>' for n in news_list])
    st.markdown(f"""<div class="ticker-wrap"><div class="ticker">{news_html}</div></div>""", unsafe_allow_html=True)

    if not df.empty:
        curr_price = df['close'].iloc[-1]
        z_score = df['Z_Score'].iloc[-1]
        
        signal_text = "MONITORING"; signal_color = "#9ca3af"; accent_style = "border: 1px solid rgba(255,255,255,0.1);"
        
        # --- SIGNAL LOGIC ---
        new_signal = "MONITORING"
        if z_score < -entry_z: 
            new_signal = "ENTRY LONG"
            signal_text = "ENTRY LONG"; signal_color = "#05FFA1"; accent_style = "border: 1px solid #05FFA1; box-shadow: 0 0 15px rgba(5,255,161,0.2);"
        elif z_score > entry_z: 
            new_signal = "ENTRY SHORT"
            signal_text = "ENTRY SHORT"; signal_color = "#FF2A6D"; accent_style = "border: 1px solid #FF2A6D; box-shadow: 0 0 15px rgba(255,42,109,0.2);"
        
        # Check if signal changed (Spam Protection)
        if new_signal != "MONITORING" and new_signal != st.session_state.last_alert_signal:
            alert_msg = f"🚨 SIMONS ALERT: {st.session_state.symbol}\n\nSIGNAL: {new_signal}\nPRICE: ${curr_price:,.2f}\nZ-SCORE: {z_score:.2f}"
            send_telegram_alert(tg_token, tg_chat, alert_msg)
            st.session_state.last_alert_signal = new_signal # Update state so we don't send again
            st.toast(f"Telegram Alert Sent: {new_signal}", icon="🔔")
        elif new_signal == "MONITORING":
            st.session_state.last_alert_signal = "MONITORING" # Reset if price goes back to normal
        # ---------------------------------------

        c1, c2, c3, c4 = st.columns(4)
        with c1: st.markdown(f"""<div class="metric-card" style="{accent_style}"><div class="metric-label">ALGO STATUS</div><div class="metric-value" style="color:{signal_color}">{signal_text}</div></div>""", unsafe_allow_html=True)
        with c2: st.markdown(f"""<div class="metric-card"><div class="metric-label">LAST PRICE</div><div class="metric-value">${curr_price:,.2f}</div></div>""", unsafe_allow_html=True)
        with c3: st.markdown(f"""<div class="metric-card"><div class="metric-label">STD DEVIATION (Z)</div><div class="metric-value">{z_score:.2f}σ</div></div>""", unsafe_allow_html=True)
        with c4: st.markdown(f"""<div class="metric-card"><div class="metric-label">VOLATILITY</div><div class="metric-value" style="color:#eab308">{df["StdDev"].iloc[-1]:.2f}</div></div>""", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['Mean'] + (df['StdDev']*entry_z), line=dict(color='rgba(255, 255, 255, 0.1)', width=1), showlegend=False))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['Mean'] - (df['StdDev']*entry_z), line=dict(color='rgba(255, 255, 255, 0.1)', width=1), fill='tonexty', fillcolor='rgba(255, 255, 255, 0.02)', showlegend=False))
        fig.add_trace(go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], increasing_line_color='#05FFA1', decreasing_line_color='#FF2A6D', increasing_fillcolor='rgba(5, 255, 161, 0.1)', decreasing_fillcolor='rgba(255, 42, 109, 0.1)', name='Price'))
        vp_df = calculate_volume_profile(df)
        fig = render_volume_profile(fig, vp_df, df['timestamp'].min(), df['timestamp'].max())
        
        active = st.session_state.active_trade
        if active:
            ep = active['entry']
            fig.add_hline(y=ep, line_dash="solid", line_color="#fff", annotation_text="ENTRY", annotation_position="top left")
            fig.add_hline(y=ep*(0.98 if active['side']=="LONG" else 1.02), line_dash="dash", line_color="#FF2A6D")
            fig.add_hline(y=ep*(1.04 if active['side']=="LONG" else 0.96), line_dash="dash", line_color="#05FFA1")

        fig.update_layout(height=600, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="JetBrains Mono", size=10), margin=dict(l=0, r=50, t=30, b=0), xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", gridwidth=1), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", gridwidth=1, side="right"), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        c1, c2, c3 = st.columns([1,1,2])
        with c1: 
            if st.button("EXECUTE LONG"): st.session_state.active_trade = {'symbol': st.session_state.symbol, 'side': 'LONG', 'entry': curr_price}; st.rerun()
        with c2: 
            if st.button("EXECUTE SHORT"): st.session_state.active_trade = {'symbol': st.session_state.symbol, 'side': 'SHORT', 'entry': curr_price}; st.rerun()
        with c3:
            if active:
                pnl = ((curr_price - active['entry']) / active['entry']) * 100 * (1 if active['side']=='LONG' else -1)
                pnl_col = "#05FFA1" if pnl > 0 else "#FF2A6D"
                st.markdown(f"""<div style="background:rgba(255,255,255,0.05); padding:10px; border:1px solid #333; display:flex; justify-content:space-between; align-items:center;"><span style="font-size:12px; color:#888;">ACTIVE PNL</span><span style="font-size:20px; font-weight:bold; font-family:'Rajdhani'; color:{pnl_col}">{pnl:+.2f}%</span></div>""", unsafe_allow_html=True)
                if st.button("CLOSE POSITION"): st.session_state.active_trade = None; st.rerun()
    else:
        st.error(f"DATA FEED DISCONNECTED. ERROR: {err}")
        st.info("Try refreshing the page or checking your internet connection.")

    if enable_refresh:
        time.sleep(5)
        st.rerun()

elif menu == "STRATEGY LAB":
    st.markdown(f"""<div class="arch-header">DEEP BACKTEST <span style="font-weight:300; opacity:0.5">// {st.session_state.symbol}</span></div>""", unsafe_allow_html=True)
    
    st.markdown('<div class="backtest-panel">', unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    with c1: st.write("The engine will fetch 1000 candles and simulate the strategy execution over historical data.")
    with c2: 
        if st.button("🚀 RUN SIMULATION"):
            with st.spinner("Processing market data..."):
                hist_df, err = get_market_data(st.session_state.symbol, timeframe, window, limit=1000)
                if not hist_df.empty:
                    trade_log, equity_curve = run_backtest(hist_df, entry_z)
                    
                    if not trade_log.empty:
                        final_eq = equity_curve[-1]
                        total_ret = ((final_eq - 1000) / 1000) * 100
                        win_rate = len(trade_log[trade_log['PnL'] > 0]) / len(trade_log) * 100
                        eq_series = pd.Series(equity_curve)
                        roll_max = eq_series.cummax()
                        drawdown = (eq_series - roll_max) / roll_max * 100
                        max_dd = drawdown.min()
                        
                        st.success("SIMULATION SUCCESSFUL")
                        m1, m2, m3, m4 = st.columns(4)
                        with m1: st.metric("NET PROFIT", f"{total_ret:.2f}%")
                        with m2: st.metric("WIN RATE", f"{win_rate:.1f}%")
                        with m3: st.metric("MAX DRAWDOWN", f"{max_dd:.2f}%")
                        with m4: st.metric("TOTAL TRADES", len(trade_log))
                        
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(y=equity_curve, mode='lines', line=dict(color='#00F0FF', width=2), fill='tozeroy', fillcolor='rgba(0, 240, 255, 0.1)'))
                        fig.update_layout(title="EQUITY CURVE", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=30, b=0), height=300)
                        st.plotly_chart(fig, use_container_width=True)
                        
                        metrics = {'ret': total_ret, 'wr': win_rate, 'dd': max_dd, 'tr': len(trade_log)}
                        html_report = generate_html_report(st.session_state.symbol, timeframe, metrics, trade_log)
                        b64 = base64.b64encode(html_report.encode()).decode()
                        href = f'<a href="data:text/html;base64,{b64}" download="SIMONS_REPORT_{st.session_state.symbol}.html" style="text-decoration:none;"><button style="width:100%; background:var(--glass-surface); color:#fff; border:1px solid var(--neon-cyan); padding:10px; font-weight:bold; cursor:pointer; font-family:Rajdhani; text-transform:uppercase;">🖨️ PRINT / SAVE REPORT</button></a>'
                        st.markdown(href, unsafe_allow_html=True)
                        
                        st.subheader("TRADE AUDIT LOG")
                        st.dataframe(trade_log[['Date', 'Type', 'Entry', 'Exit', 'PnL', 'Result']], use_container_width=True, column_config={"Date": st.column_config.DatetimeColumn(format="D MMM YYYY, h:mm a"), "Entry": st.column_config.NumberColumn(format="$%.2f"), "Exit": st.column_config.NumberColumn(format="$%.2f"), "PnL": st.column_config.NumberColumn(format="%.2f%%")})
                    else: st.warning("No trades found in this period. Adjust threshold.")
                else: st.error("Data fetch error.")
    st.markdown('</div>', unsafe_allow_html=True)

elif menu == "TUTORIAL":
    st.markdown(f"""<div class="arch-header">SYSTEM MANUAL <span style="font-weight:300; opacity:0.5">// GUIDE</span></div>""", unsafe_allow_html=True)
    st.markdown('<div class="tutorial-panel">', unsafe_allow_html=True)
    
    st.subheader("1. READING THE ALGORITHM")
    st.markdown("""
    The core strategy relies on **Statistical Mean Reversion** (Z-Score).
    * **Z-Score < -2.0:** Price is statistically "Oversold". The bot looks for a **LONG** entry.
    * **Z-Score > 2.0:** Price is statistically "Overbought". The bot looks for a **SHORT** entry.
    * **White Line (Mean):** This is the "Fair Value". Price tends to return here after an extension.
    """)
    
    st.divider()
    
    st.subheader("2. INSTITUTIONAL ORDER FLOW (SIDEBAR)")
    st.markdown("""
    Use the sidebar widget to confirm the algorithm's signals with real market data.
    
    * **WHALE WALLS:**
        * <span style="color:#05FFA1">**BUY WALL DETECTED:**</span> Massive limit orders waiting to buy below. Good support for LONGS.
        * <span style="color:#FF2A6D">**SELL WALL DETECTED:**</span> Massive limit orders waiting to sell above. Good resistance for SHORTS.
    
    * **IMBALANCE METER:**
        * Shows the ratio of Buyers vs Sellers in the top 20 order book levels.
        * **> 60% BUY:** Bullish pressure.
        * **> 60% SELL:** Bearish pressure.
    """)
    
    st.divider()
    
    st.subheader("3. PRO TRADING STRATEGY (CONFLUENCE)")
    st.info("💡 **GOLDEN RULE:** Only take a trade when the ALGO SIGNAL matches the ORDER FLOW.")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**✅ HIGH PROBABILITY LONG:**")
        st.markdown("- Algo Status: **ENTRY LONG**")
        st.markdown("- Whale Alert: **BUY WALL**")
        st.markdown("- Imbalance: **> 55% BUY**")
    with c2:
        st.markdown("**✅ HIGH PROBABILITY SHORT:**")
        st.markdown("- Algo Status: **ENTRY SHORT**")
        st.markdown("- Whale Alert: **SELL WALL**")
        st.markdown("- Imbalance: **> 55% SELL**")
        
    st.markdown('</div>', unsafe_allow_html=True)