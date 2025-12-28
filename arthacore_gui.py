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

# Import modul-modul ArthaChain
try:
    from artha_wallet import ArthaWallet
    from artha_blockchain import ArthaBlockchain
    from artha_node import ArthaNode
except ImportError as e:
    print(f"Error: Pastikan semua modul ArthaChain tersedia di folder ini. ({e})")
    sys.exit(1)

# --- Konfigurasi Logging ---
LOG_FILE_PATH = ""

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        self.log_queue.put(self.format(record))

def setup_gui_logging(port):
    global LOG_FILE_PATH
    log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
    os.makedirs(log_dir, exist_ok=True)
    LOG_FILE_PATH = os.path.join(log_dir, f"arthacore_gui_{port}.log")
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    if root_logger.handlers:
        for h in root_logger.handlers[:]:
            h.close()
            root_logger.removeHandler(h)
            
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(LOG_FILE_PATH, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

# --- Kelas Utama Aplikasi GUI ---
class ArthaCore(ThemedTk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.set_theme("arc") 
        except tk.TclError:
            pass
            
        self.title("ArthaCore - ArthaChain Wallet & Node")
        self.geometry("1100x780")
        self.minsize(1050, 720)

        self.wallet = None
        self.blockchain = None
        self.node = None
        self.password = None
        self.is_running = True

        # Status variabel
        self.address_var = tk.StringVar(value="Memuat...")
        self.balance_var = tk.StringVar(value="0.00000000")
        self.status_text = tk.StringVar(value="Memulai sistem...")

        self.setup_styles()
        self.setup_menu()

        # Log Queue untuk thread-safe logging
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        self.queue_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logging.getLogger().addHandler(self.queue_handler)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.create_widgets()
        
        # Inisialisasi tertunda agar GUI muncul dulu
        self.after(500, self.initialize_app)

    def setup_styles(self):
        self.style = ttk.Style(self)
        self.style.configure("TLabel", font=("Segoe UI", 10))
        self.style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        self.style.configure("Balance.TLabel", font=("Segoe UI", 32, "bold"), foreground="#2c3e50")
        self.style.configure("TButton", font=("Segoe UI", 10))
        self.style.configure("Nav.TButton", font=("Segoe UI", 11, "bold"), padding=10)
        self.style.configure("Status.TLabel", font=("Segoe UI", 9), background="#f8f9fa")
        self.style.configure("Treeview", rowheight=30, font=("Segoe UI", 10))
        self.style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def setup_menu(self):
        menubar = tk.Menu(self)
        # Menu File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Salin Alamat Dompet", command=self.copy_address)
        file_menu.add_separator()
        file_menu.add_command(label="Keluar", command=self.on_closing)
        menubar.add_cascade(label="Berkas", menu=file_menu)
        
        # Menu Settings
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Sinkronisasi Paksa", command=self.force_resync)
        menubar.add_cascade(label="Pengaturan", menu=settings_menu)
        
        # Menu Help
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Tentang ArthaCore", command=lambda: messagebox.showinfo("ArthaCore", "ArthaChain Ecosystem v1.5\nDecentralized Hybrid Blockchain."))
        menubar.add_cascade(label="Bantuan", menu=help_menu)
        
        self.config(menu=menubar)

    def initialize_app(self):
        # Minta password di awal
        self.password = simpledialog.askstring("Autentikasi", "Masukkan kata sandi dompet Anda:", show='*')
        if not self.password:
            self.destroy()
            return
        
        try:
            self.wallet = ArthaWallet(password=self.password)
            self.blockchain = ArthaBlockchain()
            
            app_port = int(sys.argv[1]) if len(sys.argv) > 1 else 5002
            setup_gui_logging(app_port)
            
            self.node = ArthaNode('0.0.0.0', app_port, self.blockchain, new_tx_event=None)
            threading.Thread(target=self.node.start, daemon=True).start()
            
            self.address_var.set(self.wallet.get_public_address())
            self.status_text.set("Terhubung ke Jaringan")
            logging.info(f"Node aktif di port {app_port}")
            
            # Memulai loop update
            self.update_gui_data()
            self.process_log_queue()
        except Exception as e:
            messagebox.showerror("Gagal Inisialisasi", f"Terjadi kesalahan: {e}")
            self.destroy()

    def create_widgets(self):
        # Toolbar Navigasi Atas
        self.toolbar = ttk.Frame(self, padding=5)
        self.toolbar.pack(side="top", fill="x")

        # Container Tab
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Inisialisasi Tab
        self.tab_overview = ttk.Frame(self.notebook, padding=15)
        self.tab_send = ttk.Frame(self.notebook, padding=15)
        self.tab_transactions = ttk.Frame(self.notebook, padding=15)
        self.tab_explorer = ttk.Frame(self.notebook, padding=15)
        self.tab_network = ttk.Frame(self.notebook, padding=15)
        self.tab_logs = ttk.Frame(self.notebook, padding=15)

        self.notebook.add(self.tab_overview, text="  Ikhtisar  ")
        self.notebook.add(self.tab_send, text="  Kirim ARTH  ")
        self.notebook.add(self.tab_transactions, text="  Riwayat  ")
        self.notebook.add(self.tab_explorer, text="  Penjelajah  ")
        self.notebook.add(self.tab_network, text="  Jaringan  ")
        self.notebook.add(self.tab_logs, text="  Log Sistem  ")

        self.build_overview()
        self.build_send()
        self.build_transactions()
        self.build_explorer()
        self.build_network()
        self.build_logs()

        # Status Bar Bawah
        self.status_bar = ttk.Frame(self, relief="sunken", padding=(5, 2))
        self.status_bar.pack(side="bottom", fill="x")
        
        ttk.Label(self.status_bar, textvariable=self.status_text, style="Status.TLabel").pack(side="left", padx=10)
        self.status_peers = ttk.Label(self.status_bar, text="Peers: 0", style="Status.TLabel")
        self.status_peers.pack(side="right", padx=10)
        self.status_height = ttk.Label(self.status_bar, text="Tinggi Blok: 0", style="Status.TLabel")
        self.status_height.pack(side="right", padx=10)

    # --- TAB BUILDERS ---

    def build_overview(self):
        # Kiri: Saldo
        left_side = ttk.Frame(self.tab_overview)
        left_side.pack(side="left", fill="both", expand=True)

        bal_frame = ttk.LabelFrame(left_side, text=" Saldo Dompet ", padding=25)
        bal_frame.pack(fill="x", pady=(0, 20))
        
        ttk.Label(bal_frame, text="Tersedia:", font=("Segoe UI", 11)).pack(anchor="w")
        ttk.Label(bal_frame, textvariable=self.balance_var, style="Balance.TLabel").pack(anchor="w")
        ttk.Label(bal_frame, text="ARTH", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        addr_frame = ttk.LabelFrame(left_side, text=" Alamat Anda (Klik untuk Salin) ", padding=15)
        addr_frame.pack(fill="x")
        
        addr_entry = ttk.Entry(addr_frame, textvariable=self.address_var, state="readonly", font=("Consolas", 11), justify="center")
        addr_entry.pack(fill="x", pady=5)
        addr_entry.bind("<Button-1>", lambda e: self.copy_address())
        
        ttk.Button(addr_frame, text="Salin Alamat Dompet", command=self.copy_address).pack(pady=5)

        # Kanan: Riwayat Terakhir
        right_side = ttk.LabelFrame(self.tab_overview, text=" Transaksi Terakhir ", padding=10)
        right_side.pack(side="right", fill="both", expand=True, padx=(20, 0))
        
        cols = ('Tipe', 'Jumlah', 'Status')
        self.recent_tree = ttk.Treeview(right_side, columns=cols, show='headings', height=10)
        for col in cols:
            self.recent_tree.heading(col, text=col)
            self.recent_tree.column(col, anchor="center", width=100)
        self.recent_tree.pack(fill="both", expand=True)

    def build_send(self):
        container = ttk.Frame(self.tab_send)
        container.pack(pady=20)
        
        ttk.Label(container, text="Kirim Pembayaran", style="Header.TLabel").grid(row=0, column=0, columnspan=2, pady=10)
        
        ttk.Label(container, text="Bayar Ke:").grid(row=1, column=0, sticky="e", pady=5, padx=5)
        self.send_to_var = tk.StringVar()
        ttk.Entry(container, textvariable=self.send_to_var, width=60, font=("Consolas", 10)).grid(row=1, column=1, pady=5)
        
        ttk.Label(container, text="Jumlah (ARTH):").grid(row=2, column=0, sticky="e", pady=5, padx=5)
        self.send_amount_var = tk.StringVar()
        ttk.Entry(container, textvariable=self.send_amount_var, width=20).grid(row=2, column=1, sticky="w", pady=5)
        
        ttk.Button(container, text="Kirim ARTH Sekarang", style="Accent.TButton", command=self.process_send).grid(row=3, column=1, sticky="w", pady=20)

    def build_transactions(self):
        cols = ('Waktu', 'Tipe', 'Jumlah', 'Partner', 'Blok')
        self.trans_tree = ttk.Treeview(self.tab_transactions, columns=cols, show='headings')
        for col in cols:
            self.trans_tree.heading(col, text=col)
            self.trans_tree.column(col, anchor='center')
        
        self.trans_tree.column('Waktu', width=150)
        self.trans_tree.column('Partner', width=350)
        
        sb = ttk.Scrollbar(self.tab_transactions, orient="vertical", command=self.trans_tree.yview)
        self.trans_tree.configure(yscrollcommand=sb.set)
        
        self.trans_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        self.trans_tree.tag_configure('sent', foreground='#e74c3c')
        self.trans_tree.tag_configure('received', foreground='#27ae60')
        self.trans_tree.tag_configure('reward', foreground='#2980b9')

    def build_explorer(self):
        header = ttk.Frame(self.tab_explorer)
        header.pack(fill="x", pady=(0, 15))
        
        ttk.Label(header, text="Cari Alamat/Hash:").pack(side="left", padx=5)
        self.explorer_search_var = tk.StringVar()
        search_entry = ttk.Entry(header, textvariable=self.explorer_search_var, font=("Consolas", 10))
        search_entry.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(header, text="Cari", command=self.search_explorer).pack(side="left", padx=5)
        
        # Fitur Copy Alamat yang sedang dicari
        self.btn_copy_searched = ttk.Button(header, text="Salin Alamat", command=self.copy_searched_address, state="disabled")
        self.btn_copy_searched.pack(side="left", padx=5)

        # Notebook Explorer
        self.exp_notebook = ttk.Notebook(self.tab_explorer)
        self.exp_notebook.pack(fill="both", expand=True)
        
        # Blok Terbaru
        self.tab_blocks = ttk.Frame(self.exp_notebook, padding=10)
        self.exp_notebook.add(self.tab_blocks, text=" Blok Terbaru ")
        
        cols_b = ('Index', 'Hash', 'Miner', 'TX')
        self.blocks_tree = ttk.Treeview(self.tab_blocks, columns=cols_b, show='headings')
        for col in cols_b:
            self.blocks_tree.heading(col, text=col)
            self.blocks_tree.column(col, anchor='center')
        self.blocks_tree.pack(fill="both", expand=True)
        
        # Hasil Pencarian
        self.tab_search_res = ttk.Frame(self.exp_notebook, padding=10)
        self.exp_notebook.add(self.tab_search_res, text=" Hasil Pencarian ")
        
        self.search_label = ttk.Label(self.tab_search_res, text="Masukkan alamat untuk melihat riwayat.", font=("Segoe UI", 10, "italic"))
        self.search_label.pack(pady=5)
        
        cols_s = ('Tipe', 'Jumlah', 'Partner', 'Blok')
        self.search_tree = ttk.Treeview(self.tab_search_res, columns=cols_s, show='headings')
        for col in cols_s:
            self.search_tree.heading(col, text=col)
            self.search_tree.column(col, anchor='center')
        self.search_tree.pack(fill="both", expand=True)

    def build_network(self):
        container = ttk.PanedWindow(self.tab_network, orient="horizontal")
        container.pack(fill="both", expand=True)
        
        # Peers
        p_frame = ttk.LabelFrame(container, text=" Peer Terhubung ", padding=10)
        self.peer_listbox = tk.Listbox(p_frame, font=("Consolas", 10), border=0)
        self.peer_listbox.pack(fill="both", expand=True)
        
        sync_btn = ttk.Button(p_frame, text="Sync Jaringan Paksa", command=self.force_resync)
        sync_btn.pack(fill="x", pady=5)
        container.add(p_frame, weight=1)
        
        # Mempool
        m_frame = ttk.LabelFrame(container, text=" Transaksi Tertunda (Mempool) ", padding=10)
        self.mempool_listbox = tk.Listbox(m_frame, font=("Consolas", 10), border=0)
        self.mempool_listbox.pack(fill="both", expand=True)
        container.add(m_frame, weight=1)

    def build_logs(self):
        self.log_display = tk.Text(self.tab_logs, bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9), state="disabled", wrap="word")
        self.log_display.pack(side="left", fill="both", expand=True)
        
        sb = ttk.Scrollbar(self.tab_logs, command=self.log_display.yview)
        self.log_display.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

    # --- LOGIC & UPDATES ---

    def update_gui_data(self):
        if not self.is_running or not all([self.wallet, self.blockchain, self.node]):
            self.after(2000, self.update_gui_data)
            return
        
        try:
            # 1. Update Saldo
            bal = self.blockchain.get_balance(self.wallet.get_public_address())
            self.balance_var.set(f"{bal:.8f}")
            
            # 2. Update Status Bar
            with self.node.lock:
                peers_count = len(self.node.peers)
            self.status_peers.config(text=f"Peers: {peers_count}")
            self.status_height.config(text=f"Tinggi Blok: {len(self.blockchain.chain) - 1}")
            
            # 3. Update Peer Listbox
            self.peer_listbox.delete(0, tk.END)
            with self.node.lock:
                for p in self.node.peers.keys():
                    self.peer_listbox.insert(tk.END, f"🟢 {p}")
            
            # 4. Update Mempool
            self.mempool_listbox.delete(0, tk.END)
            for tx in self.blockchain.pending_transactions:
                self.mempool_listbox.insert(tk.END, f"TX {tx['transaction_id'][:12]}... ({tx['amount']} ARTH)")
            
            # 5. Refresh Tabel-tabel
            self.refresh_transactions()
            self.refresh_blocks()
            
        except Exception as e:
            logging.error(f"Gagal memperbarui data GUI: {e}")
            
        self.after(5000, self.update_gui_data)

    def refresh_transactions(self):
        # Refresh Tabel Riwayat Utama
        self.trans_tree.delete(*self.trans_tree.get_children())
        self.recent_tree.delete(*self.recent_tree.get_children())
        
        my_addr = self.wallet.get_public_address()
        count = 0
        for block in reversed(self.blockchain.chain):
            for tx in reversed(block['transactions']):
                if tx['sender'] == my_addr or tx['recipient'] == my_addr:
                    waktu = time.strftime('%d/%m %H:%M', time.localtime(tx['timestamp']))
                    if tx['sender'] == my_addr:
                        tag, tipe, amt, partner = 'sent', 'KELUAR', f"-{tx['amount']}", tx['recipient']
                    elif tx['sender'] == '0':
                        tag, tipe, amt, partner = 'reward', 'MINING', f"+{tx['amount']}", 'System'
                    else:
                        tag, tipe, amt, partner = 'received', 'MASUK', f"+{tx['amount']}", tx['sender']
                    
                    # Insert ke Riwayat Utama
                    self.trans_tree.insert("", "end", values=(waktu, tipe, amt, partner, block['index']), tags=(tag,))
                    
                    # Insert ke Ikhtisar (maks 5)
                    if count < 5:
                        self.recent_tree.insert("", "end", values=(tipe, amt, "Terkonfirmasi"), tags=(tag,))
                    count += 1

    def refresh_blocks(self):
        self.blocks_tree.delete(*self.blocks_tree.get_children())
        for block in reversed(self.blockchain.chain[-15:]):
            b_hash = self.blockchain.hash_block(block)[:16] + "..."
            self.blocks_tree.insert("", "end", values=(block['index'], b_hash, block['miner_address'][:12]+"...", len(block['transactions'])))

    def process_send(self):
        to = self.send_to_var.get().strip()
        try:
            amount = Decimal(self.send_amount_var.get())
        except (InvalidOperation, ValueError):
            messagebox.showwarning("Error", "Jumlah tidak valid.")
            return
            
        if not to or len(to) < 10:
            messagebox.showwarning("Error", "Alamat penerima tidak valid.")
            return
            
        if self.blockchain.get_balance(self.wallet.get_public_address()) < amount:
            messagebox.showerror("Saldo Kurang", "Saldo Anda tidak mencukupi untuk transaksi ini.")
            return
            
        if messagebox.askyesno("Konfirmasi", f"Kirim {amount} ARTH ke {to}?\n\nTindakan ini tidak bisa dibatalkan."):
            tx_data = {
                'sender': self.wallet.get_public_address(), 
                'recipient': to, 
                'amount': "{:.8f}".format(amount)
            }
            sig = self.wallet.sign_transaction(tx_data)
            pk = self.wallet.public_key.export_key().decode('utf-8')
            
            added = self.blockchain.add_transaction(tx_data['sender'], to, amount, sig, pk)
            if added:
                self.node.broadcast_message('NEW_TRANSACTION', {'transaction': added, 'public_key_str': pk})
                messagebox.showinfo("Berhasil", "Transaksi telah dikirim ke jaringan.")
                self.send_to_var.set(""); self.send_amount_var.set("")
                self.update_gui_data()
            else:
                messagebox.showerror("Gagal", "Kesalahan saat memproses transaksi.")

    def search_explorer(self):
        term = self.explorer_search_var.get().strip()
        if not term: return
        
        self.search_tree.delete(*self.search_tree.get_children())
        balance = Decimal('0')
        found = False
        
        for block in self.blockchain.chain:
            for tx in block['transactions']:
                if tx['sender'] == term or tx['recipient'] == term:
                    found = True
                    amt = Decimal(tx['amount'])
                    if tx['sender'] == term:
                        balance -= amt; tipe, partner = "KELUAR", tx['recipient']
                    else:
                        balance += amt; tipe, partner = "MASUK", tx['sender'] if tx['sender'] != '0' else "Sistem"
                    
                    self.search_tree.insert("", 0, values=(tipe, f"{amt:.8f}", partner, block['index']))
        
        if found:
            self.search_label.config(text=f"Riwayat untuk: {term[:20]}... | Perkiraan Saldo: {balance:.8f} ARTH", font=("Segoe UI", 10, "bold"))
            self.btn_copy_searched.config(state="normal")
            self.exp_notebook.select(self.tab_search_res)
        else:
            self.btn_copy_searched.config(state="disabled")
            messagebox.showinfo("Explorer", "Data tidak ditemukan di blockchain.")

    def copy_searched_address(self):
        addr = self.explorer_search_var.get().strip()
        self.clipboard_clear()
        self.clipboard_append(addr)
        messagebox.showinfo("Disalin", "Alamat pencarian berhasil disalin ke clipboard.")

    def copy_address(self):
        addr = self.address_var.get()
        self.clipboard_clear()
        self.clipboard_append(addr)
        messagebox.showinfo("Berhasil", "Alamat dompet Anda berhasil disalin.")

    def force_resync(self):
        if self.node:
            self.status_text.set("Memaksa sinkronisasi ulang...")
            self.node.trigger_full_resync()
            logging.info("Sinkronisasi penuh dipicu oleh pengguna.")
            messagebox.showinfo("Sync", "Memulai pengambilan ulang rantai blok dari peers...")
            self.after(5000, lambda: self.status_text.set("Terhubung ke Jaringan"))

    def process_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_display.config(state="normal")
                self.log_display.insert(tk.END, f"{msg}\n")
                self.log_display.see(tk.END)
                self.log_display.config(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self.process_log_queue)

    def on_closing(self):
        if messagebox.askokcancel("Keluar", "Ingin menutup ArthaCore?\nIni akan menghentikan node blockchain."):
            self.is_running = False
            if self.node: self.node.stop()
            self.destroy()

if __name__ == "__main__":
    # Jalankan App
    try:
        app = ArthaCore()
        app.mainloop()
    except Exception as e:
        print(f"Error Fatal: {e}")