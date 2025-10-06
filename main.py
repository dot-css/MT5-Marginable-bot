import tkinter as tk
from tkinter import ttk, messagebox
import MetaTrader5 as mt5
import csv
from datetime import datetime
import time
import threading

# --- MT5 setup ---
ACCOUNT = 1
PASSWORD = ""
SERVER = ""

if not mt5.initialize():
    print("MT5 init failed", mt5.last_error())
    quit()

if not mt5.login(ACCOUNT, PASSWORD, SERVER):
    print("Login failed", mt5.last_error())
    mt5.shutdown()
    quit()

# --- CSV setup ---
CSV_FILE = "mt5_orders.csv"
try:
    with open(CSV_FILE, "x", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Symbol", "OrderType", "ExecutionType", "LotSize", "Price", "SL", "TP", "Result", "Profit"])
except FileExistsError:
    pass

# --- Trade function ---
def execute_trade(symbol, order_type, lot_size, execution_type="market", limit_price=None):
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"Symbol {symbol} not found")
        return None, None, None, None, None

    if execution_type == "limit" and limit_price:
        price = limit_price
        action = mt5.TRADE_ACTION_PENDING
        order_type_exec = mt5.ORDER_TYPE_BUY_LIMIT if order_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_SELL_LIMIT
    else:
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        action = mt5.TRADE_ACTION_DEAL
        order_type_exec = order_type

    if symbol == "BTCUSDm":
        sl_points = 100
        tp_points = 200
    elif symbol == "XAUUSDm":
        sl_points = 1
        tp_points = 2
    elif symbol in ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm", "USDCADm", "NZDUSDm"]:
        sl_points = 0.001
        tp_points = 0.002
    elif symbol == "USTEC":
        sl_points = 10
        tp_points = 20
    elif symbol == "US30":
        sl_points = 50
        tp_points = 100
    elif symbol == "XAGUSDm":
        sl_points = 0.1
        tp_points = 0.2
    else:
        sl_points = 10
        tp_points = 20

    if order_type == mt5.ORDER_TYPE_BUY or order_type_exec == mt5.ORDER_TYPE_BUY_LIMIT:
        sl = price - sl_points
        tp = price + tp_points
    else:
        sl = price + sl_points
        tp = price - tp_points

    request = {
        "action": action,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type_exec,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 50,
        "magic": 123456,
        "comment": "Auto Martingale",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Trade failed: {result.comment}")
        return None, None, None, None, None

    return result, sl, tp, price, result.order

def wait_for_trade_close(order_ticket):
    print(f"Monitoring order {order_ticket}...")
    
    while True:
        time.sleep(0.5)
        
        positions = mt5.positions_get(ticket=order_ticket)
        if positions and len(positions) > 0:
            continue
        
        deals = mt5.history_deals_get(ticket=order_ticket)
        if deals and len(deals) > 0:
            for deal in deals:
                if deal.entry == mt5.DEAL_ENTRY_OUT:
                    profit = deal.profit
                    print(f"Trade closed. Profit: {profit}")
                    return profit > 0, profit
        
        history = mt5.history_orders_get(ticket=order_ticket)
        if history and len(history) > 0:
            time.sleep(0.5)
            deals = mt5.history_deals_get(position=order_ticket)
            if deals:
                total_profit = sum(deal.profit for deal in deals)
                print(f"Trade closed via history. Profit: {total_profit}")
                return total_profit > 0, total_profit
        
        time.sleep(1)

def martingale_trade(symbol, order_type, base_lot, execution_type, limit_price, max_steps=4, status_label=None):
    lot_size = base_lot
    
    for step in range(max_steps):
        if status_label:
            status_label.config(text=f"Step {step+1}/{max_steps} - Lot: {lot_size} - Executing...")
        
        result, sl, tp, entry_price, ticket = execute_trade(symbol, order_type, lot_size, execution_type, limit_price)
        
        if not result or not ticket:
            if status_label:
                status_label.config(text="Trade execution failed!")
            messagebox.showerror("Error", "Trade failed to execute!")
            return
        
        if status_label:
            status_label.config(text=f"Step {step+1}/{max_steps} - Lot: {lot_size} - Waiting...")
        
        is_profit, profit_amount = wait_for_trade_close(ticket)
        
        with open(CSV_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
                execution_type.upper(),
                lot_size,
                entry_price,
                sl,
                tp,
                "PROFIT" if is_profit else "LOSS",
                profit_amount
            ])
        
        if is_profit:
            if status_label:
                status_label.config(text=f"Profit! ${profit_amount:.2f} - Complete!")
            print(f"Profit: ${profit_amount:.2f}")
            break
        else:
            print(f"Loss: ${profit_amount:.2f}")
            
            if step == max_steps - 1:
                if status_label:
                    status_label.config(text="Max steps reached. Stopped.")
                break
            else:
                lot_size *= 2
                if status_label:
                    status_label.config(text=f"Doubling to {lot_size}...")
                time.sleep(1)
                continue

def start_martingale_thread(symbol, order_type, base_lot, execution_type, limit_price, status_label):
    thread = threading.Thread(target=martingale_trade, args=(symbol, order_type, base_lot, execution_type, limit_price, 4, status_label))
    thread.daemon = True
    thread.start()

def toggle_limit_price(*args):
    if execution_var.get() == "Limit":
        limit_frame.pack(after=execution_frame, pady=10, padx=40, fill="x")
    else:
        limit_frame.pack_forget()

# --- GUI ---
root = tk.Tk()
root.title("MT5 Martingale Bot")
root.geometry("500x600")
root.configure(bg="#1e1e2e")

# Header
header = tk.Frame(root, bg="#2d2d44", height=80)
header.pack(fill="x")
header.pack_propagate(False)

tk.Label(header, text="⚡ MT5 MARTINGALE BOT", 
         bg="#2d2d44", fg="#00d9ff",
         font=("Arial", 20, "bold")).pack(pady=25)

# Main content area
content = tk.Frame(root, bg="#1e1e2e")
content.pack(fill="both", expand=True, padx=30, pady=20)

# Symbol section
symbol_frame = tk.Frame(content, bg="#1e1e2e")
symbol_frame.pack(pady=10, fill="x")

tk.Label(symbol_frame, text="Trading Pair", bg="#1e1e2e", fg="#00d9ff",
         font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 5))

symbol_var = tk.StringVar(value="XAUUSDm")
symbol_dropdown = ttk.Combobox(symbol_frame, textvariable=symbol_var, 
                               state="readonly", font=("Arial", 11), width=35)
symbol_dropdown['values'] = (
    "XAUUSDm", "BTCUSDm", "EURUSDm", "GBPUSDm", "USDJPYm", 
    "AUDUSDm", "USDCADm", "NZDUSDm", "USTEC", "US30"
)
symbol_dropdown.pack(fill="x", ipady=6)

# Execution type section
execution_frame = tk.Frame(content, bg="#1e1e2e")
execution_frame.pack(pady=10, fill="x")

tk.Label(execution_frame, text="Execution Type", bg="#1e1e2e", fg="#00d9ff",
         font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 5))

execution_var = tk.StringVar(value="Market")
execution_dropdown = ttk.Combobox(execution_frame, textvariable=execution_var,
                                  state="readonly", font=("Arial", 11), width=35)
execution_dropdown['values'] = ("Market", "Limit")
execution_dropdown.pack(fill="x", ipady=6)
execution_var.trace('w', toggle_limit_price)

# Limit price section (hidden initially)
limit_frame = tk.Frame(content, bg="#1e1e2e")

tk.Label(limit_frame, text="Limit Price", bg="#1e1e2e", fg="#00d9ff",
         font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 5))

limit_entry = tk.Entry(limit_frame, font=("Arial", 12), bg="#2d2d44", 
                      fg="white", insertbackground="white", relief="flat", bd=2)
limit_entry.pack(fill="x", ipady=8)

# Lot size section
lot_frame = tk.Frame(content, bg="#1e1e2e")
lot_frame.pack(pady=10, fill="x")

tk.Label(lot_frame, text="Base Lot Size", bg="#1e1e2e", fg="#00d9ff",
         font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 5))

lot_entry = tk.Entry(lot_frame, font=("Arial", 12), bg="#2d2d44", 
                    fg="white", insertbackground="white", relief="flat", bd=2)
lot_entry.insert(0, "0.01")
lot_entry.pack(fill="x", ipady=8)

# Status section
status_frame = tk.Frame(content, bg="#2d2d44", relief="flat", bd=1)
status_frame.pack(pady=20, fill="x")

status_label = tk.Label(status_frame, text="Ready to trade", 
                       bg="#2d2d44", fg="#00ff88",
                       font=("Arial", 10), pady=15)
status_label.pack(fill="x")

# Buttons
button_frame = tk.Frame(content, bg="#1e1e2e")
button_frame.pack(pady=15)

def execute_buy():
    exec_type = execution_var.get().lower()
    limit = float(limit_entry.get()) if exec_type == "limit" and limit_entry.get() else None
    start_martingale_thread(symbol_var.get(), mt5.ORDER_TYPE_BUY, 
                          float(lot_entry.get()), exec_type, limit, status_label)

def execute_sell():
    exec_type = execution_var.get().lower()
    limit = float(limit_entry.get()) if exec_type == "limit" and limit_entry.get() else None
    start_martingale_thread(symbol_var.get(), mt5.ORDER_TYPE_SELL, 
                          float(lot_entry.get()), exec_type, limit, status_label)

buy_btn = tk.Button(button_frame, text="BUY", bg="#00ff88", fg="#1e1e2e",
                   font=("Arial", 12, "bold"), width=12, height=2,
                   relief="flat", cursor="hand2", command=execute_buy)
buy_btn.grid(row=0, column=0, padx=8)

sell_btn = tk.Button(button_frame, text="SELL", bg="#ff4757", fg="white",
                    font=("Arial", 12, "bold"), width=12, height=2,
                    relief="flat", cursor="hand2", command=execute_sell)
sell_btn.grid(row=0, column=1, padx=8)

# Footer
tk.Label(content, text="Auto SL/TP Detection • Martingale Strategy", 
         bg="#1e1e2e", fg="#6b6b7f", font=("Arial", 9)).pack(pady=10)

root.mainloop()
mt5.shutdown()