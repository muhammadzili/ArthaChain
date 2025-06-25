# arthacore_gui.py

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from ttkthemes import ThemedTk
import threading
import time
import queue
import logging
import os
import sys
from decimal import Decimal, InvalidOperation

# Import modul-modul ArthaChain yang stabil
from artha_wallet import ArthaWallet
from artha_blockchain import ArthaBlockchain
from artha_node import ArthaNode

# --- Konfigurasi Logging ---
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        self.log_queue.put(self.format(record))

def setup_gui_logging(port):
    log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"arthacore_gui_{port}.log")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if root_logger.handlers: [h.close() for h in root_logger.handlers[:]]; root_logger.handlers = []
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(log_file_path, mode='w'); file_handler.setLevel(logging.DEBUG); file_handler.setFormatter(formatter); root_logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout); console_handler.setLevel(logging.INFO); console_handler.setFormatter(formatter); root_logger.addHandler(console_handler)

# --- Kelas Utama Aplikasi GUI ---
class ArthaCore(ThemedTk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.set_theme("arc")
        except tk.TclError:
            print("Tema 'arc' tidak ditemukan, menggunakan tema default.")
            
        self.title("ArthaCore")
        self.geometry("1200x800")

        self.wallet = None
        self.blockchain = None
        self.node = None
        self.password = None
        self.is_running = True

        self.style = ttk.Style(self)
        self.style.configure("TLabel", font=("Helvetica", 11))
        self.style.configure("TButton", font=("Helvetica", 11, "bold"), padding=10)
        self.style.configure("Accent.TButton", foreground="white", background="#007bff", font=("Helvetica", 11, "bold"), padding=10)
        self.style.map("Accent.TButton", background=[('active', '#0056b3')])
        self.style.configure("Treeview.Heading", font=("Helvetica", 12, "bold"))
        self.style.configure("Treeview", rowheight=25, font=("Helvetica", 10))

        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        logging.getLogger().addHandler(self.queue_handler)
        self.queue_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.create_menu()
        self.create_widgets()
        self.after(100, self.initialize_app)

    def initialize_app(self):
        self.password = simpledialog.askstring("Password Dompet", "Masukkan password untuk membuka atau membuat dompet:", show='*')
        if not self.password: self.destroy(); return
        
        try:
            self.wallet = ArthaWallet(password=self.password)
            self.blockchain = ArthaBlockchain()
            app_port = int(sys.argv[1]) if len(sys.argv) > 1 else 5002
            self.node = ArthaNode('0.0.0.0', app_port, self.blockchain, new_tx_event=None)
            threading.Thread(target=self.node.start, daemon=True).start()
            
            self.address_var.set(self.wallet.get_public_address())
            logging.info("Backend berhasil diinisialisasi.")
            
            self.after(5000, self.update_gui_data)
            self.process_log_queue()
        except ValueError as e:
            messagebox.showerror("Login Gagal", str(e))
            self.destroy()

    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Keluar", command=self.on_closing)

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")
        
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        dashboard_frame = ttk.Frame(self.notebook, padding="20"); self.notebook.add(dashboard_frame, text='   Dashboard   ')
        history_frame = ttk.Frame(self.notebook, padding="10"); self.notebook.add(history_frame, text='   Histori Saya   ')
        explorer_frame = ttk.Frame(self.notebook, padding="10"); self.notebook.add(explorer_frame, text='   Explorer / Pools   ')
        network_frame = ttk.Frame(self.notebook, padding="10"); self.notebook.add(network_frame, text='   Jaringan   ')
        log_frame = ttk.Frame(self.notebook, padding="10"); self.notebook.add(log_frame, text='   Log   ')
        
        self.create_dashboard_tab(dashboard_frame)
        self.create_history_tab(history_frame)
        self.create_explorer_tab(explorer_frame)
        self.create_network_tab(network_frame)
        self.create_log_tab(log_frame)

    def create_dashboard_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        
        balance_frame = ttk.LabelFrame(parent, text=" Saldo Terkonfirmasi ", padding="20")
        balance_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        balance_frame.grid_columnconfigure(0, weight=1)

        self.balance_var = tk.StringVar(value="0.00000000")
        balance_label = ttk.Label(balance_frame, textvariable=self.balance_var, font=("Helvetica", 36, "bold"), anchor="center")
        balance_label.grid(row=0, column=0, sticky="ew")
        ttk.Label(balance_frame, text="ARTH", font=("Helvetica", 14), anchor="center").grid(row=1, column=0, sticky="ew")

        address_frame = ttk.LabelFrame(parent, text=" Alamat Dompet Anda ", padding="15")
        address_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        address_frame.grid_columnconfigure(0, weight=1)

        self.address_var = tk.StringVar(value="Memuat...")
        address_entry = ttk.Entry(address_frame, textvariable=self.address_var, state="readonly", font=("Courier", 11), justify='center')
        address_entry.pack(fill='x', expand=True, ipady=5)

        action_frame = ttk.Frame(parent)
        action_frame.grid(row=2, column=0, pady=20)
        ttk.Button(action_frame, text="  Kirim ARTH  ", command=self.open_send_dialog, style="Accent.TButton").pack(side="left", padx=10)
        ttk.Button(action_frame, text="  Refresh Data  ", command=self.update_gui_data_now).pack(side="left", padx=10)

    def create_history_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1); parent.grid_rowconfigure(0, weight=1)
        cols = ('Tanggal', 'Tipe', 'Jumlah', 'Alamat Terkait')
        self.history_tree = ttk.Treeview(parent, columns=cols, show='headings')
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        for col in cols: self.history_tree.heading(col, text=col)
        self.history_tree.column('Tanggal', width=180, anchor='w'); self.history_tree.column('Tipe', width=80, anchor='center'); self.history_tree.column('Jumlah', width=150, anchor='e'); self.history_tree.column('Alamat Terkait', width=400, anchor='w')
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.history_tree.yview); self.history_tree.configure(yscrollcommand=scrollbar.set); scrollbar.grid(row=0, column=1, sticky="ns")
        self.history_tree.tag_configure('sent', foreground='#c0392b'); self.history_tree.tag_configure('received', foreground='#27ae60'); self.history_tree.tag_configure('reward', foreground='#2980b9')

    def create_explorer_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        search_frame = ttk.Frame(parent, padding="10")
        search_frame.grid(row=0, column=0, sticky="ew")
        search_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="Cari Alamat:").grid(row=0, column=0, padx=(0,10))
        self.search_entry = ttk.Entry(search_frame, font=("Courier", 10))
        self.search_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(search_frame, text="Cari", command=self.search_address).grid(row=0, column=2, padx=(10,0))

        info_frame = ttk.LabelFrame(parent, text="Info Alamat", padding="10")
        info_frame.grid(row=1, column=0, sticky="ew", pady=10)
        self.searched_balance_var = tk.StringVar(value="Saldo: -")
        ttk.Label(info_frame, textvariable=self.searched_balance_var).pack(anchor="w")

        history_frame = ttk.LabelFrame(parent, text="Histori Transaksi", padding="10")
        history_frame.grid(row=2, column=0, sticky="nsew")
        history_frame.grid_columnconfigure(0, weight=1); history_frame.grid_rowconfigure(0, weight=1)
        cols = ('Blok', 'Tanggal', 'Tipe', 'Jumlah', 'Alamat Terkait')
        self.searched_history_tree = ttk.Treeview(history_frame, columns=cols, show='headings')
        self.searched_history_tree.grid(row=0, column=0, sticky="nsew")
        for col in cols: self.searched_history_tree.heading(col, text=col)
        self.searched_history_tree.column('Blok', width=80, anchor='center'); self.searched_history_tree.column('Tanggal', width=180, anchor='w'); self.searched_history_tree.column('Tipe', width=80, anchor='center'); self.searched_history_tree.column('Jumlah', width=150, anchor='e'); self.searched_history_tree.column('Alamat Terkait', width=350, anchor='w')
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.searched_history_tree.yview); self.searched_history_tree.configure(yscrollcommand=scrollbar.set); scrollbar.grid(row=0, column=1, sticky="ns")

    def create_network_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1); parent.grid_rowconfigure(0, weight=1)
        main_frame = ttk.Frame(parent); main_frame.pack(expand=True, fill='both')
        blocks_frame = ttk.LabelFrame(main_frame, text="Blok Terbaru", padding="10"); blocks_frame.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        cols = ('Index', 'Timestamp', 'Miner', 'Tx Count')
        self.latest_blocks_tree = ttk.Treeview(blocks_frame, columns=cols, show='headings')
        for col in cols: self.latest_blocks_tree.heading(col, text=col)
        self.latest_blocks_tree.pack(expand=True, fill='both')
        pending_tx_frame = ttk.LabelFrame(main_frame, text="Transaksi Tertunda", padding="10"); pending_tx_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        self.pending_tx_list = tk.Listbox(pending_tx_frame, height=15); self.pending_tx_list.pack(expand=True, fill='both')
    
    def create_log_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1); parent.grid_rowconfigure(0, weight=1)
        self.log_text = tk.Text(parent, state='disabled', wrap='word', height=20, font=("Courier", 9)); self.log_text.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(parent, command=self.log_text.yview); self.log_text['yscrollcommand'] = scrollbar.set; scrollbar.grid(row=0, column=1, sticky='ns')

    def update_gui_data_now(self):
        if not self.is_running: return
        if hasattr(self, '_update_job'): self.after_cancel(self._update_job)
        self.update_gui_data(schedule_next=False)
        messagebox.showinfo("Refresh", "Data telah diperbarui.")

    def update_gui_data(self, schedule_next=True):
        if not self.is_running or not all([self.wallet, self.blockchain, self.node]):
            if schedule_next: self.after(5000, self.update_gui_data)
            return
        
        balance = self.blockchain.get_balance(self.wallet.get_public_address())
        self.balance_var.set(f"{balance:.8f}")
        self.update_history_view()
        self.update_latest_blocks_view()
        
        with self.node.lock: peers_copy = list(self.node.peers.keys())
        self.peers_list.delete(0, tk.END)
        for peer in peers_copy: self.peers_list.insert(tk.END, peer)
        
        self.pending_tx_list.delete(0, tk.END)
        for tx in self.blockchain.pending_transactions:
            self.pending_tx_list.insert(tk.END, f"ID: {tx['transaction_id'][:10]}... Jml: {tx['amount']}")
        
        if schedule_next: self.after(5000, self.update_gui_data)
    
    def update_history_view(self):
        # --- Fungsi ini ditambahkan kembali ---
        self.history_tree.delete(*self.history_tree.get_children())
        my_address = self.wallet.get_public_address()
        for block in reversed(self.blockchain.chain):
            for tx in reversed(block['transactions']):
                if tx['sender'] == my_address or tx['recipient'] == my_address:
                    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(tx['timestamp']))
                    if tx['sender'] == my_address:
                        tipe, color, amount_str, other_party = "Keluar", "sent", f"- {tx['amount']}", tx['recipient']
                    elif tx['recipient'] == my_address and tx['sender'] == "0":
                         tipe, color, amount_str, other_party = "Reward", "reward", f"+ {tx['amount']}", "Coinbase"
                    else:
                        tipe, color, amount_str, other_party = "Masuk", "received", f"+ {tx['amount']}", tx['sender']
                    
                    self.history_tree.insert("", "end", iid=tx['transaction_id'], values=(ts, tipe, amount_str, other_party), tags=(color,))
        
    def update_latest_blocks_view(self):
        self.latest_blocks_tree.delete(*self.latest_blocks_tree.get_children())
        for block in reversed(self.blockchain.chain[-10:]):
            ts = time.strftime('%H:%M:%S', time.localtime(block['timestamp']))
            miner = block['miner_address'][:15] + '...'
            tx_count = len(block['transactions'])
            self.latest_blocks_tree.insert("", 0, values=(block['index'], ts, miner, tx_count))

    def process_log_queue(self):
        # --- Fungsi ini ditambahkan kembali ---
        if not self.is_running: return
        try:
            while True: 
                record = self.log_queue.get_nowait()
                self.log_text.config(state='normal'); self.log_text.insert(tk.END, record + '\n'); self.log_text.config(state='disabled'); self.log_text.yview(tk.END)
        except queue.Empty: pass
        finally: self.after(100, self.process_log_queue)

    def open_send_dialog(self):
        # --- Fungsi ini ditambahkan kembali ---
        dialog = SendDialog(self)
        if dialog.recipient and dialog.amount:
            recipient, amount = dialog.recipient, dialog.amount
            if self.blockchain.get_balance(self.wallet.get_public_address()) < amount:
                messagebox.showerror("Gagal", "Saldo terkonfirmasi tidak mencukupi."); return
            
            canonical_amount_str = "{:.8f}".format(amount)
            tx_data = {'sender': self.wallet.get_public_address(), 'recipient': recipient, 'amount': canonical_amount_str}
            signature = self.wallet.sign_transaction(tx_data)
            added_tx = self.blockchain.add_transaction(self.wallet.get_public_address(), recipient, amount, signature, self.wallet.public_key.export_key().decode('utf-8'))
            if added_tx:
                self.node.broadcast_message('NEW_TRANSACTION', {'transaction': added_tx, 'public_key_str': self.wallet.public_key.export_key().decode('utf-8')})
                messagebox.showinfo("Sukses", "Transaksi berhasil disiarkan.")
            else: messagebox.showerror("Gagal", "Gagal membuat transaksi.")

    def search_address(self):
        address = self.search_entry.get().strip()
        if not address or len(address) < 64:
            messagebox.showerror("Error", "Alamat tidak valid.", parent=self)
            return
        
        self.searched_history_tree.delete(*self.searched_history_tree.get_children())
        balance = Decimal('0')
        chain_copy = self.blockchain.chain[:]
        
        for block in chain_copy:
            for tx in block['transactions']:
                amount = Decimal(tx['amount'])
                is_sent = tx['sender'] == address
                is_received = tx['recipient'] == address
                if is_sent: balance -= amount
                if is_received: balance += amount
                if is_sent or is_received:
                    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(tx['timestamp']))
                    if is_sent: tipe, other_party = "Keluar", tx['recipient']
                    else: tipe, other_party = "Masuk", tx['sender'] if tx['sender'] != '0' else "Coinbase"
                    self.searched_history_tree.insert("", 0, values=(block['index'], ts, tipe, tx['amount'], other_party))
        self.searched_balance_var.set(f"Saldo Alamat: {balance:.8f} ARTH")
        
    def force_resync(self):
        # --- Fungsi ini ditambahkan kembali ---
        if self.node: self.node.trigger_full_resync(); messagebox.showinfo("Info", "Permintaan sinkronisasi dikirim.")

    def on_closing(self):
        if messagebox.askokcancel("Keluar", "Yakin ingin keluar?"):
            self.is_running = False
            if self.node: self.node.stop()
            self.destroy()

class SendDialog(simpledialog.Dialog):
    # --- Kelas ini ditambahkan kembali ---
    def __init__(self, parent):
        self.recipient = None
        self.amount = None
        super().__init__(parent, "Kirim ARTH")

    def body(self, master):
        ttk.Label(master, text="Alamat Penerima:").grid(row=0, sticky=tk.W, padx=5, pady=2)
        self.recipient_entry = ttk.Entry(master, width=65); self.recipient_entry.grid(row=1, padx=5, pady=5)
        ttk.Label(master, text="Jumlah ARTH:").grid(row=2, sticky=tk.W, padx=5, pady=2)
        self.amount_entry = ttk.Entry(master, width=30); self.amount_entry.grid(row=3, padx=5, pady=5)
        return self.recipient_entry

    def apply(self):
        try:
            self.recipient = self.recipient_entry.get().strip()
            self.amount = Decimal(self.amount_entry.get())
            if not self.recipient or self.amount <= 0 or len(self.recipient) < 64: raise ValueError()
        except (ValueError, TypeError, InvalidOperation):
            self.recipient, self.amount = None, None; messagebox.showerror("Error", "Input tidak valid.", parent=self)

if __name__ == "__main__":
    try:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 5002
        setup_gui_logging(port)
        app = ArthaCore()
        app.mainloop()
    except Exception as e:
        logging.critical(f"Aplikasi ArthaCore gagal dijalankan: {e}")
        messagebox.showerror("Error Kritis", f"Aplikasi tidak dapat berjalan:\n{e}")
