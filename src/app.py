from __future__ import annotations

import asyncio
import csv
import threading
import time
from datetime import datetime
from queue import Queue, Empty
from tkinter import BOTH, END, LEFT, RIGHT, VERTICAL, X, Y, filedialog
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict

import ttkbootstrap as tb
from ttkbootstrap.constants import *

from .binance_service import BinanceFuturesService
from .config import load_app_state, load_settings, save_app_state, save_settings
from .demo_trading import PaperAccount
from .logging_service import build_logger
from .persistence import Persistence, append_ml_log, model_winrate
from .signal_engine import CandleBuilder, ImpulseSignalEngine, ReversalMeter
from .trade_tools import TradeToolsManager


class App(tb.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Belevaku Trading")
        self.ui_queue: Queue = Queue()
        self.logger = build_logger(self.ui_queue)
        self.settings = load_settings()
        self.app_state = load_app_state()
        self.geometry(self.app_state.get("geometry", "1380x860+100+60"))
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.persistence = Persistence()
        self.paper = PaperAccount()
        self.trade_tools = TradeToolsManager()
        self.signal_engine = ImpulseSignalEngine()
        self.c15 = CandleBuilder(15)
        self.c60 = CandleBuilder(60)
        self.reversal = ReversalMeter(self.settings["strategy"]["target_retrace_pct"])

        self.prices: Dict[str, float] = {}
        self.online = False
        self.running = False
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.loop_thread.start()
        self.ws_service = BinanceFuturesService(self.logger, self.settings["min_24h_volume_m"])

        self._build_styles()
        self._build_layout()
        self._load_history()

        self.after(150, self._drain_ui_queue)
        self.after(500, self._refresh_ui)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _submit_coro(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def _build_styles(self):
        style = ttk.Style()
        style.configure("Panel.TFrame", background="#1b1f24")
        style.configure("Card.TFrame", background="#23272f", relief="flat")
        style.configure("Sidebar.TFrame", background="#15181d")
        style.configure("Title.TLabel", font=("Georgia", 22, "italic"), foreground="#e2e6eb", background="#1b1f24")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#9da4ad", background="#1b1f24")
        style.configure("KPI.TLabel", font=("Segoe UI", 11, "bold"), foreground="#f2f5f7", background="#23272f")
        style.configure("Metric.TLabel", font=("Segoe UI", 10), foreground="#9fa6ae", background="#23272f")

    def _build_layout(self):
        self.container = ttk.Frame(self, style="Panel.TFrame")
        self.container.pack(fill=BOTH, expand=True)

        self.sidebar = ttk.Frame(self.container, width=230, style="Sidebar.TFrame")
        self.sidebar.pack(side=LEFT, fill=Y)
        self.sidebar.pack_propagate(False)

        main = ttk.Frame(self.container, style="Panel.TFrame")
        main.pack(side=RIGHT, fill=BOTH, expand=True)

        self._build_sidebar()
        self._build_topbar(main)
        self._build_pages(main)
        self._show_page(self.app_state.get("page", "TERMINAL"))

    def _build_sidebar(self):
        ttk.Label(self.sidebar, text="⚡ BELEVAKU", font=("Segoe UI", 18, "bold"), foreground="#f2f5f7", background="#15181d").pack(anchor=W, padx=16, pady=20)
        self.nav_buttons = {}
        for page in ["TERMINAL", "HISTORY", "DEV", "CONFIG"]:
            b = ttk.Button(self.sidebar, text=f"  {page}", command=lambda p=page: self._show_page(p), bootstyle="secondary")
            b.pack(fill=X, padx=10, pady=5)
            self.nav_buttons[page] = b

        ttk.Label(self.sidebar, text="Account Equity", foreground="#9ea5ad", background="#15181d").pack(anchor=W, padx=16, pady=(30, 0))
        self.equity_var = tk.StringVar(value="$1000.00")
        ttk.Label(self.sidebar, textvariable=self.equity_var, font=("Segoe UI", 16, "bold"), foreground="#eaf0f5", background="#15181d").pack(anchor=W, padx=16)
        ttk.Label(self.sidebar, text="Daily PNL", foreground="#9ea5ad", background="#15181d").pack(anchor=W, padx=16, pady=(20, 0))
        self.daily_var = tk.StringVar(value="$0.00")
        ttk.Label(self.sidebar, textvariable=self.daily_var, font=("Segoe UI", 14, "bold"), foreground="#4ad77f", background="#15181d").pack(anchor=W, padx=16)

    def _build_topbar(self, parent):
        top = ttk.Frame(parent, style="Panel.TFrame")
        top.pack(fill=X, padx=14, pady=10)

        left = ttk.Frame(top, style="Panel.TFrame")
        left.pack(side=LEFT)
        self.bot_status = tk.StringVar(value="BOT: STOPPED")
        ttk.Label(left, text="Belevaku Trading", style="Title.TLabel").pack(side=LEFT)
        ttk.Label(left, text="  ● ", foreground="#b6bdc6", background="#1b1f24").pack(side=LEFT)
        ttk.Label(left, textvariable=self.bot_status, style="Sub.TLabel").pack(side=LEFT)

        self.kpis = {}
        center = ttk.Frame(top, style="Panel.TFrame")
        center.pack(side=LEFT, padx=30)
        for key in ["WALLET BALANCE", "OPEN POSITIONS", "ACTIVE ORDERS", "TOTAL PNL"]:
            box = ttk.Frame(center, style="Card.TFrame", padding=8)
            box.pack(side=LEFT, padx=5)
            ttk.Label(box, text=key, style="Metric.TLabel").pack()
            v = tk.StringVar(value="—")
            ttk.Label(box, textvariable=v, style="KPI.TLabel").pack()
            self.kpis[key] = v

        right = ttk.Frame(top, style="Panel.TFrame")
        right.pack(side=RIGHT)
        self.binance_var = tk.StringVar(value="BINANCE OFFLINE")
        ttk.Label(right, textvariable=self.binance_var, style="Sub.TLabel").pack(side=LEFT, padx=12)
        self.start_btn = ttk.Button(right, text="START", command=self.toggle_run, bootstyle="success")
        self.start_btn.pack(side=LEFT)

    def _build_pages(self, parent):
        self.page_container = ttk.Frame(parent, style="Panel.TFrame")
        self.page_container.pack(fill=BOTH, expand=True, padx=14, pady=4)
        self.pages = {
            "TERMINAL": self._terminal_page(),
            "DEV": self._dev_page(),
            "CONFIG": self._config_page(),
            "HISTORY": self._history_page(),
        }

    def _terminal_page(self):
        f = ttk.Frame(self.page_container, style="Panel.TFrame")
        metrics = ttk.Frame(f, style="Panel.TFrame")
        metrics.pack(fill=X)
        self.term_metrics = {}
        for name in ["Total Balance", "Open Positions", "Active Orders", "Risk Score"]:
            c = ttk.Frame(metrics, style="Card.TFrame", padding=12)
            c.pack(side=LEFT, fill=X, expand=True, padx=5)
            ttk.Label(c, text=name, style="Metric.TLabel").pack(anchor=W)
            v = tk.StringVar(value="—")
            ttk.Label(c, textvariable=v, style="KPI.TLabel").pack(anchor=W)
            self.term_metrics[name] = v

        mid = ttk.Frame(f, style="Panel.TFrame")
        mid.pack(fill=X, pady=8)
        chart_card = ttk.Frame(mid, style="Card.TFrame", padding=10)
        chart_card.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 5))
        ttk.Label(chart_card, text="Market Performance", style="KPI.TLabel").pack(anchor=W)
        self.chart_canvas = tk.Canvas(chart_card, height=220, bg="#181c22", highlightthickness=0)
        self.chart_canvas.pack(fill=BOTH, expand=True)

        pos_card = ttk.Frame(mid, style="Card.TFrame", padding=10, width=320)
        pos_card.pack(side=RIGHT, fill=BOTH)
        pos_card.pack_propagate(False)
        ttk.Label(pos_card, text="Active Position", style="KPI.TLabel").pack(anchor=W)
        self.active_pos_var = tk.StringVar(value="No active position")
        ttk.Label(pos_card, textvariable=self.active_pos_var, style="Sub.TLabel").pack(anchor=W, pady=8)
        self.reversal_var = tk.IntVar(value=0)
        self.rev_bar = ttk.Progressbar(pos_card, maximum=100, variable=self.reversal_var, bootstyle="info-striped")
        self.rev_bar.pack(fill=X, pady=8)
        self.reversal_lbl = tk.StringVar(value="Reversal Readiness: inactive")
        ttk.Label(pos_card, textvariable=self.reversal_lbl, style="Sub.TLabel").pack(anchor=W)

        tools = ttk.Frame(f, style="Card.TFrame", padding=8)
        tools.pack(fill=X, pady=8)
        ttk.Label(tools, text="Trade Tools", style="KPI.TLabel").pack(anchor=W)
        cols = ("symbol", "dir", "entry", "status", "mode", "copy")
        self.tools_tree = ttk.Treeview(tools, columns=cols, show="headings", height=8)
        for c, h in zip(cols, ["Symbol", "Direction", "Entry", "WIN/LOSS", "Mode", "Copy"]):
            self.tools_tree.heading(c, text=h)
        self.tools_tree.pack(fill=X)
        ttk.Button(tools, text="Copy Selected Ticker", command=self.copy_selected_ticker).pack(anchor=E, pady=4)

        bottom = ttk.Frame(f, style="Panel.TFrame")
        bottom.pack(fill=BOTH, expand=True)

        feed_card = ttk.Frame(bottom, style="Card.TFrame", padding=8)
        feed_card.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 5))
        ttk.Label(feed_card, text="Activity Feed", style="KPI.TLabel").pack(anchor=W)
        self.feed = tk.Text(feed_card, bg="#0f1218", fg="#d7dbe0", height=12)
        self.feed.pack(fill=BOTH, expand=True)

        hist_card = ttk.Frame(bottom, style="Card.TFrame", padding=8)
        hist_card.pack(side=RIGHT, fill=BOTH, expand=True)
        ttk.Label(hist_card, text="Trade History", style="KPI.TLabel").pack(anchor=W)
        self.trade_tree = ttk.Treeview(hist_card, columns=("TIME", "SYMBOL", "SIDE", "PRICE", "SIZE", "STATUS"), show="headings", height=12)
        for c in ("TIME", "SYMBOL", "SIDE", "PRICE", "SIZE", "STATUS"):
            self.trade_tree.heading(c, text=c)
        self.trade_tree.pack(fill=BOTH, expand=True)

        self.status_var = tk.StringVar(value="VOL FILTER 25M | EXCHANGE BINANCE | MODE DEMO")
        bar = ttk.Frame(f, style="Card.TFrame")
        bar.pack(fill=X, pady=6)
        ttk.Label(bar, textvariable=self.status_var, style="Sub.TLabel").pack(side=LEFT, padx=8)
        self.server_time_var = tk.StringVar(value="SERVER TIME -- | RECONNECTING: NO")
        ttk.Label(bar, textvariable=self.server_time_var, style="Sub.TLabel").pack(side=RIGHT, padx=8)
        return f

    def _dev_page(self):
        f = ttk.Frame(self.page_container, style="Panel.TFrame")
        ttk.Label(f, text="Developer Console", style="Title.TLabel").pack(anchor=W)
        ttk.Label(f, text="Manual controls and diagnostics", style="Sub.TLabel").pack(anchor=W)
        grid = ttk.Frame(f, style="Panel.TFrame")
        grid.pack(fill=X, pady=10)

        p1 = ttk.Labelframe(grid, text="Trade Execution", padding=8)
        p1.pack(side=LEFT, fill=BOTH, expand=True, padx=5)
        ttk.Button(p1, text="Place Test Trade ($100 USDT)", command=self.place_test_trade).pack(fill=X, pady=4)
        ttk.Button(p1, text="Cancel Test Trade", command=lambda: self._dev_out("Cancel not needed for paper market fills")).pack(fill=X, pady=4)

        p2 = ttk.Labelframe(grid, text="Connectivity", padding=8)
        p2.pack(side=LEFT, fill=BOTH, expand=True, padx=5)
        ttk.Button(p2, text="Test Binance Connection", command=self.test_connection).pack(fill=X, pady=4)
        ttk.Button(p2, text="Clear System Logs", command=lambda: self.dev_console.delete("1.0", END)).pack(fill=X, pady=4)

        p3 = ttk.Labelframe(grid, text="Simulations", padding=8)
        p3.pack(side=LEFT, fill=BOTH, expand=True, padx=5)
        ttk.Button(p3, text="Sim Error", command=lambda: self._dev_out('{"error":"simulated"}')).pack(fill=X, pady=4)
        ttk.Button(p3, text="Sim Success", command=lambda: self._dev_out('{"result":"ok"}')).pack(fill=X, pady=4)

        ttk.Label(f, text="Console Output", style="KPI.TLabel").pack(anchor=W, pady=(10, 4))
        self.dev_console = tk.Text(f, bg="#07090d", fg="#a8ffbd", height=22, font=("Consolas", 10))
        self.dev_console.pack(fill=BOTH, expand=True)
        return f

    def _config_page(self):
        f = ttk.Frame(self.page_container, style="Panel.TFrame")
        ttk.Label(f, text="System Configuration", style="Title.TLabel").pack(anchor=W)
        ttk.Label(f, text="Version v2 desktop", style="Sub.TLabel").pack(anchor=W)

        exch = ttk.Labelframe(f, text="Exchange Connectivity", padding=10)
        exch.pack(fill=X, pady=6)
        self.mode_var = tk.StringVar(value=self.settings["mode"])
        ttk.Radiobutton(exch, text="DEMO", variable=self.mode_var, value="DEMO", command=self._save_config).pack(side=LEFT)
        ttk.Radiobutton(exch, text="REAL", variable=self.mode_var, value="REAL", command=self._save_config).pack(side=LEFT, padx=8)
        ttk.Label(exch, text="Min 24h volume (Millions USDT)").pack(side=LEFT, padx=12)
        self.min_vol_var = tk.DoubleVar(value=self.settings["min_24h_volume_m"])
        ttk.Entry(exch, textvariable=self.min_vol_var, width=8).pack(side=LEFT)

        api = ttk.Labelframe(f, text="API Credentials", padding=10)
        api.pack(fill=X, pady=6)
        self.real_key = tk.StringVar(value=self.settings["api"]["real_key"])
        self.real_secret = tk.StringVar(value=self.settings["api"]["real_secret"])
        self.demo_key = tk.StringVar(value=self.settings["api"]["demo_key"])
        self.demo_secret = tk.StringVar(value=self.settings["api"]["demo_secret"])
        for i, (lbl, var, mask) in enumerate([
            ("REAL Key", self.real_key, ""),
            ("REAL Secret", self.real_secret, "*"),
            ("DEMO Key", self.demo_key, ""),
            ("DEMO Secret", self.demo_secret, "*"),
        ]):
            ttk.Label(api, text=lbl).grid(row=i // 2, column=(i % 2) * 2, sticky=W, padx=4, pady=3)
            ttk.Entry(api, textvariable=var, show=mask, width=35).grid(row=i // 2, column=(i % 2) * 2 + 1, padx=4, pady=3)

        strat = ttk.Labelframe(f, text="Strategy Engine", padding=10)
        strat.pack(fill=X, pady=6)
        self.algo_var = tk.StringVar(value=self.settings["strategy"]["algorithm"])
        ttk.Combobox(strat, textvariable=self.algo_var, values=["Impulse Scalp (V1)"], width=28).pack(side=LEFT)
        self.entry_mode_var = tk.StringVar(value=self.settings["strategy"]["entry_mode"])
        ttk.Radiobutton(strat, text="SIMPLE", variable=self.entry_mode_var, value="SIMPLE", command=self._save_config).pack(side=LEFT, padx=8)
        ttk.Radiobutton(strat, text="ML", variable=self.entry_mode_var, value="ML", command=self._save_config).pack(side=LEFT)

        profile = ttk.Labelframe(f, text="Risk Profile", padding=10)
        profile.pack(fill=X, pady=6)
        self.profile_var = tk.StringVar(value=self.settings["risk_profile"])
        for p in ["SAFE", "MEDIUM", "AGGRESSIVE", "CUSTOM"]:
            ttk.Radiobutton(profile, text=p, variable=self.profile_var, value=p, command=self._apply_profile).pack(side=LEFT, padx=6)

        risk = ttk.Labelframe(f, text="Risk Management", padding=10)
        risk.pack(fill=X, pady=6)
        self.pos_size_var = tk.DoubleVar(value=self.settings["risk"]["position_size_usdt"])
        self.sl_var = tk.DoubleVar(value=self.settings["risk"]["stop_loss_pct"])
        self.tp_var = tk.DoubleVar(value=self.settings["risk"]["take_profit_pct"])
        for i, (lbl, var) in enumerate([
            ("Position Size (USDT)", self.pos_size_var),
            ("Stop Loss (%)", self.sl_var),
            ("Take Profit (%)", self.tp_var),
        ]):
            ttk.Label(risk, text=lbl).grid(row=0, column=i * 2, sticky=W)
            ttk.Entry(risk, textvariable=var, width=10).grid(row=0, column=i * 2 + 1, padx=5)

        ml = ttk.Labelframe(f, text="ML Settings", padding=10)
        ml.pack(fill=X, pady=6)
        self.ml_tol_var = tk.DoubleVar(value=self.settings["strategy"]["ml_tolerance"] * 100)
        ttk.Label(ml, text="Tolerance %").pack(side=LEFT)
        ttk.Entry(ml, textvariable=self.ml_tol_var, width=8).pack(side=LEFT, padx=6)
        self.reversal_size_var = tk.DoubleVar(value=self.settings["strategy"]["target_retrace_pct"])
        ttk.Label(ml, text="Reversal size (%)").pack(side=LEFT, padx=8)
        ttk.Scale(ml, from_=0.0, to=2.0, variable=self.reversal_size_var, orient=HORIZONTAL, length=240, command=lambda _e: self._save_config()).pack(side=LEFT)

        ttk.Button(f, text="Save Configuration", command=self._save_config, bootstyle="info").pack(anchor=E, pady=8)
        return f

    def _history_page(self):
        f = ttk.Frame(self.page_container, style="Panel.TFrame")
        top = ttk.Frame(f, style="Panel.TFrame")
        top.pack(fill=X)
        ttk.Label(top, text="Executed Trades", style="KPI.TLabel").pack(side=LEFT)
        ttk.Button(top, text="Export CSV", command=self.export_history).pack(side=RIGHT)
        self.history_tree = ttk.Treeview(f, columns=("TIME", "SYMBOL", "SIDE", "PRICE", "SIZE", "STATUS", "MODE"), show="headings")
        for c in ("TIME", "SYMBOL", "SIDE", "PRICE", "SIZE", "STATUS", "MODE"):
            self.history_tree.heading(c, text=c)
        self.history_tree.pack(fill=BOTH, expand=True, pady=6)
        return f

    def _show_page(self, page: str):
        self.app_state["page"] = page
        for name, frame in self.pages.items():
            frame.pack_forget()
            self.nav_buttons[name].configure(bootstyle="secondary")
        self.pages[page].pack(fill=BOTH, expand=True)
        self.nav_buttons[page].configure(bootstyle="light")

    def toggle_run(self):
        if self.running:
            self.running = False
            self.bot_status.set("BOT: STOPPED")
            self.start_btn.configure(text="START", bootstyle="success")
            return
        self.running = True
        self.bot_status.set("BOT: RUNNING")
        self.start_btn.configure(text="STOP", bootstyle="danger")
        self._submit_coro(self.ws_service.start(self._on_ws_event))

    def _on_ws_event(self, payload: Dict[str, Any]):
        data = payload.get("data", {})
        stream = payload.get("stream", "")
        event = data.get("e")
        if event == "aggTrade":
            symbol = data["s"]
            price = float(data["p"])
            qty = float(data["q"])
            ts = data["E"] / 1000.0
            self.prices[symbol] = price
            self.c15.on_trade(symbol, ts, price, qty)
            self.c60.on_trade(symbol, ts, price, qty)
            self.trade_tools.update_price(symbol, price)

            signal = self.signal_engine.on_trade(symbol, ts, price)
            if signal:
                if self.entry_mode_var.get() == "ML" and abs(signal.impulse_pct) < (self.settings["strategy"]["ml_tolerance"] * 0.8):
                    return
                idx = self.trade_tools.push_signal(signal, self.entry_mode_var.get(), self.tp_var.get(), self.sl_var.get())
                self.logger.info("signal %s %s impulse=%.3f%% row=%d", signal.symbol, signal.side, signal.impulse_pct, idx)
                self.reversal.arm(signal.symbol, signal.side, signal.price, ts)
                self.feed.insert(END, f"{datetime.utcnow().strftime('%H:%M:%S')} SIGNAL {signal.side} {signal.symbol} {signal.impulse_pct:.3f}%\n")
                self.feed.see(END)

        if "bookTicker" in stream:
            self.online = True

    def _refresh_ui(self):
        self.binance_var.set("BINANCE ONLINE" if self.online else "BINANCE OFFLINE")
        pnl = self.paper.mark(self.prices)
        self.kpis["WALLET BALANCE"].set(f"${self.paper.wallet_balance:,.2f}")
        self.kpis["OPEN POSITIONS"].set(str(len(self.paper.positions)))
        self.kpis["ACTIVE ORDERS"].set(str(self.paper.active_orders))
        self.kpis["TOTAL PNL"].set(f"${pnl:,.2f}")
        self.equity_var.set(f"${self.paper.wallet_balance + pnl:,.2f}")
        self.daily_var.set(f"${pnl:,.2f}")

        self.term_metrics["Total Balance"].set(f"${self.paper.wallet_balance + pnl:,.2f}")
        self.term_metrics["Open Positions"].set(str(len(self.paper.positions)))
        self.term_metrics["Active Orders"].set(str(self.paper.active_orders))
        risk = min(100, int((self.pos_size_var.get() / max(self.paper.wallet_balance, 1)) * 100))
        self.term_metrics["Risk Score"].set(f"{risk}%")

        self._redraw_chart()
        self._render_trade_tools()
        self.server_time_var.set(f"SERVER TIME {datetime.utcnow().strftime('%H:%M:%S')} | RECONNECTING: {'NO' if self.online else 'YES'}")

        if self.prices:
            sym = next(iter(self.prices.keys()))
            read, active = self.reversal.readiness(sym, self.prices[sym], time.time())
            self.reversal_var.set(read)
            self.reversal_lbl.set(f"Reversal Readiness: {read}%" if active else "Reversal Readiness: inactive")

        self.status_var.set(
            f"VOL FILTER {self.min_vol_var.get():.0f}M | EXCHANGE BINANCE | MODE {self.mode_var.get()}"
        )
        self.after(700, self._refresh_ui)

    def _redraw_chart(self):
        self.chart_canvas.delete("all")
        vals = list(self.prices.values())[:80]
        if len(vals) < 2:
            return
        w = self.chart_canvas.winfo_width() or 500
        h = self.chart_canvas.winfo_height() or 220
        lo, hi = min(vals), max(vals)
        span = max(hi - lo, 1e-9)
        pts = []
        for i, v in enumerate(vals):
            x = (i / (len(vals) - 1)) * (w - 20) + 10
            y = h - (((v - lo) / span) * (h - 30) + 15)
            pts.extend((x, y))
        self.chart_canvas.create_line(*pts, fill="#7dc6ff", width=2, smooth=True)

    def _render_trade_tools(self):
        self.tools_tree.delete(*self.tools_tree.get_children())
        for row in self.trade_tools.rows:
            self.tools_tree.insert("", END, values=(row.symbol, row.direction, row.entry_text, row.status, row.mode, "Copy"))

    def copy_selected_ticker(self):
        selected = self.tools_tree.selection()
        if not selected:
            return
        idx = self.tools_tree.index(selected[0])
        ticker = self.trade_tools.copy_ticker(idx)
        if ticker:
            self.clipboard_clear()
            self.clipboard_append(ticker)
            self.logger.info("Copied ticker %s", ticker)

    def _load_history(self):
        rows = self.persistence.list_trades(500)
        for tree in (self.trade_tree, self.history_tree):
            tree.delete(*tree.get_children())
            for r in rows:
                tree.insert("", END, values=r)

    def export_history(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        rows = self.persistence.list_trades(5000)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["TIME", "SYMBOL", "SIDE", "PRICE", "SIZE", "STATUS", "MODE"])
            w.writerows(rows)
        self.logger.info("Exported CSV %s", path)

    def place_test_trade(self):
        if not self.prices:
            self._dev_out('{"error":"no live prices yet"}')
            return
        symbol = next(iter(self.prices.keys()))
        price = self.prices[symbol]
        pos = self.paper.place_market(symbol, "LONG", price, 100)
        trade = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "symbol": symbol,
            "side": pos.side,
            "price": price,
            "size": pos.size_usdt,
            "status": "OPEN",
            "mode": self.entry_mode_var.get(),
        }
        self.persistence.add_trade(trade)
        self._load_history()
        self._dev_out(f'{{"placed":{trade}}}')
        append_ml_log([
            {
                "ts": trade["ts"],
                "symbol": symbol,
                "side": pos.side,
                "impulse_pct": 0.0,
                "mfe_pct": 0.0,
                "target_retrace_pct": self.reversal_size_var.get(),
                "win": False,
            }
        ])

    def test_connection(self):
        self._submit_coro(self._async_test())

    async def _async_test(self):
        try:
            syms = await self.ws_service.refresh_watchlist()
            self.ui_queue.put(f"{{\"watchlist\":{len(syms)}}}")
        except Exception as exc:
            self.ui_queue.put(f"{{\"error\":\"{exc}\"}}")

    def _dev_out(self, line: str):
        self.dev_console.insert(END, line + "\n")
        self.dev_console.see(END)

    def _drain_ui_queue(self):
        while True:
            try:
                msg = self.ui_queue.get_nowait()
            except Empty:
                break
            self._dev_out(msg)
        self.after(100, self._drain_ui_queue)

    def _apply_profile(self):
        p = self.profile_var.get()
        if p == "SAFE":
            self.pos_size_var.set(50)
            self.sl_var.set(0.25)
            self.tp_var.set(0.40)
        elif p == "MEDIUM":
            self.pos_size_var.set(100)
            self.sl_var.set(0.30)
            self.tp_var.set(0.50)
        elif p == "AGGRESSIVE":
            self.pos_size_var.set(200)
            self.sl_var.set(0.40)
            self.tp_var.set(0.80)
        self._save_config()

    def _save_config(self):
        self.settings["mode"] = self.mode_var.get()
        self.settings["min_24h_volume_m"] = float(self.min_vol_var.get())
        self.settings["api"]["real_key"] = self.real_key.get()
        self.settings["api"]["real_secret"] = self.real_secret.get()
        self.settings["api"]["demo_key"] = self.demo_key.get()
        self.settings["api"]["demo_secret"] = self.demo_secret.get()
        self.settings["strategy"]["algorithm"] = self.algo_var.get()
        self.settings["strategy"]["entry_mode"] = self.entry_mode_var.get()
        self.settings["strategy"]["ml_tolerance"] = float(self.ml_tol_var.get()) / 100.0
        self.settings["strategy"]["target_retrace_pct"] = float(self.reversal_size_var.get())
        self.settings["risk_profile"] = self.profile_var.get()
        self.settings["risk"]["position_size_usdt"] = float(self.pos_size_var.get())
        self.settings["risk"]["stop_loss_pct"] = float(self.sl_var.get())
        self.settings["risk"]["take_profit_pct"] = float(self.tp_var.get())
        self.reversal.target_pct = self.settings["strategy"]["target_retrace_pct"]
        save_settings(self.settings)
        wr = model_winrate()
        self.logger.info("Config saved | Model Winrate: %.2f%%", wr)

    def on_close(self):
        self.app_state["geometry"] = self.geometry()
        save_app_state(self.app_state)
        self._save_config()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.destroy()
