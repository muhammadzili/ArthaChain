# arthacore_gui.py

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
import queue
import logging
import os
import sys
from decimal import Decimal, InvalidOperation

# Import modul-modul ArthaChain Anda
from artha_wallet import ArthaWallet
from artha_blockchain import ArthaBlockchain
from artha_node import ArthaNode

# --- Konfigurasi Logging untuk GUI ---
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
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    file_handler = logging.FileHandler(log_file_path, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

# --- Kelas Utama Aplikasi GUI ---
class ArthaCore(tk.Tk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("ArthaCore Wallet")
        self.geometry("900x700")

        self.wallet = None
        self.blockchain = None
        self.node = None
        self.password = None
        self.is_running = True

        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.queue_handler.setFormatter(formatter)
        logging.getLogger().addHandler(self.queue_handler)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.create_widgets()
        self.after(100, self.initialize_app)

    def initialize_app(self):
        self.password = simpledialog.askstring("Password Dompet", "Masukkan password untuk membuka atau membuat dompet:", show='*')
        if not self.password:
            self.destroy()
            return

        self.initialize_backend()

    def initialize_backend(self):
        try:
            self.wallet = ArthaWallet(password=self.password)
        except ValueError as e:
            messagebox.showerror("Login Gagal", str(e))
            self.destroy()
            return

        self.address_var.set(self.wallet.get_public_address())
        self.blockchain = ArthaBlockchain()
        app_port = int(sys.argv[1]) if len(sys.argv) > 1 else 5002
        self.node = ArthaNode('0.0.0.0', app_port, self.blockchain)
        threading.Thread(target=self.node.start, daemon=True).start()
        logging.info("Backend berhasil diinisialisasi. Node sedang berjalan.")
        self.after(5000, self.update_gui_data)
        self.process_log_queue()

    def create_widgets(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        wallet_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(wallet_frame, text='Dompet')
        self.create_wallet_tab(wallet_frame)

        blockchain_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(blockchain_frame, text='Blockchain')
        self.create_blockchain_tab(blockchain_frame)

        network_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(network_frame, text='Jaringan')
        self.create_network_tab(network_frame)

        log_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_frame, text='Log Aktivitas')
        self.create_log_tab(log_frame)

    def create_wallet_tab(self, parent):
        ttk.Label(parent, text="Alamat Dompet Anda:", font=("Helvetica", 12, "bold")).pack(pady=5)
        self.address_var = tk.StringVar(value="Memuat...")
        address_entry = ttk.Entry(parent, textvariable=self.address_var, state="readonly", width=70, font=("Courier", 10))
        address_entry.pack(pady=5, padx=10, fill='x')

        ttk.Label(parent, text="Saldo Terkonfirmasi:", font=("Helvetica", 12, "bold")).pack(pady=(20, 5))
        self.balance_var = tk.StringVar(value="... ARTH")
        balance_label = ttk.Label(parent, textvariable=self.balance_var, font=("Helvetica", 24))
        balance_label.pack(pady=5)

        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=30)
        ttk.Button(button_frame, text="Kirim ARTH", command=self.open_send_dialog, width=20).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Refresh Data", command=self.update_gui_data_now, width=20).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="Paksa Sinkronisasi", command=self.force_resync, width=20).grid(row=0, column=2, padx=5)

    def create_blockchain_tab(self, parent):
        ttk.Label(parent, text="Tampilan Rantai Blok", font=("Helvetica", 14, "bold")).pack(pady=5)
        cols = ('Index', 'Timestamp', 'Miner', 'Tx Count', 'Hash')
        self.blockchain_tree = ttk.Treeview(parent, columns=cols, show='headings')
        for col in cols:
            self.blockchain_tree.heading(col, text=col)
            self.blockchain_tree.column(col, width=150, anchor='w')
        self.blockchain_tree.pack(expand=True, fill='both', pady=10)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.blockchain_tree.yview)
        self.blockchain_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

    def create_network_tab(self, parent):
        main_frame = ttk.Frame(parent)
        main_frame.pack(expand=True, fill='both')
        peers_frame = ttk.LabelFrame(main_frame, text="Peer Terhubung", padding="10")
        peers_frame.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        self.peers_list = tk.Listbox(peers_frame, height=15)
        self.peers_list.pack(expand=True, fill='both')

        pending_tx_frame = ttk.LabelFrame(main_frame, text="Transaksi Tertunda", padding="10")
        pending_tx_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        self.pending_tx_list = tk.Listbox(pending_tx_frame, height=15)
        self.pending_tx_list.pack(expand=True, fill='both')

    def create_log_tab(self, parent):
        ttk.Label(parent, text="Log Aktivitas Sistem", font=("Helvetica", 14, "bold")).pack(pady=5)
        self.log_text = tk.Text(parent, state='disabled', wrap='word', height=20, font=("Courier", 9))
        self.log_text.pack(expand=True, fill='both', pady=10)
        scrollbar = ttk.Scrollbar(parent, command=self.log_text.yview)
        self.log_text['yscrollcommand'] = scrollbar.set
        scrollbar.pack(side='right', fill='y')

    def update_gui_data_now(self):
        if not self.is_running:
            return
        self.update_gui_data(schedule_next=False)
        messagebox.showinfo("Refresh", "Data telah diperbarui.")

    def update_gui_data(self, schedule_next=True):
        if not self.is_running:
            return
        if not all([self.wallet, self.blockchain, self.node]):
            if schedule_next:
                self.after(5000, self.update_gui_data)
            return

        balance = self.blockchain.get_balance(self.wallet.get_public_address())
        self.balance_var.set(f"{balance:.8f} ARTH")
        self.update_blockchain_view()

        self.peers_list.delete(0, tk.END)
        with self.node.lock:
            for peer in self.node.peers.keys():
                self.peers_list.insert(tk.END, peer)

        self.pending_tx_list.delete(0, tk.END)
        pending_tx_copy = self.blockchain.pending_transactions[:]
        for tx in pending_tx_copy:
            self.pending_tx_list.insert(tk.END, f"Dari: {tx['sender'][:10]}... Jml: {tx['amount']}")

        if schedule_next:
            self.after(5000, self.update_gui_data)

    def update_blockchain_view(self):
        chain_copy = self.blockchain.chain[:]
        if len(chain_copy) != len(self.blockchain_tree.get_children()):
            self.blockchain_tree.delete(*self.blockchain_tree.get_children())
            for block in reversed(chain_copy):
                ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(block['timestamp']))
                miner = block['miner_address'][:20] + '...'
                tx_count = len(block['transactions'])
                block_hash = self.blockchain.hash_block(block)[:20] + '...'
                self.blockchain_tree.insert("", "end", values=(block['index'], ts, miner, tx_count, block_hash))

    def process_log_queue(self):
        if not self.is_running:
            return
        try:
            while True:
                record = self.log_queue.get_nowait()
                self.log_text.config(state='normal')
                self.log_text.insert(tk.END, record + '\n')
                self.log_text.config(state='disabled')
                self.log_text.yview(tk.END)
        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_log_queue)

    def open_send_dialog(self):
        dialog = SendDialog(self)
        recipient = getattr(dialog, "recipient", None)
        amount = getattr(dialog, "amount", None)

        if recipient and amount:
            if self.blockchain.get_balance(self.wallet.get_public_address()) < amount:
                messagebox.showerror("Gagal", "Saldo terkonfirmasi tidak mencukupi.")
                return

            canonical_amount_str = "{:.8f}".format(amount)
            tx_data = {
                'sender': self.wallet.get_public_address(),
                'recipient': recipient,
                'amount': canonical_amount_str
            }
            signature = self.wallet.sign_transaction(tx_data)

            added_tx = self.blockchain.add_transaction(
                self.wallet.get_public_address(),
                recipient,
                amount,
                signature,
                self.wallet.public_key.export_key().decode('utf-8')
            )

            if added_tx:
                self.node.broadcast_message('NEW_TRANSACTION', {
                    'transaction': added_tx,
                    'public_key_str': self.wallet.public_key.export_key().decode('utf-8')
                })
                messagebox.showinfo("Sukses", "Transaksi berhasil disiarkan.")
            else:
                messagebox.showerror("Gagal", "Gagal membuat transaksi.")

    def force_resync(self):
        if self.node:
            self.node.trigger_full_resync()
            messagebox.showinfo("Info", "Permintaan sinkronisasi dikirim.")

    def on_closing(self):
        if messagebox.askokcancel("Keluar", "Yakin ingin keluar?"):
            self.is_running = False
            if self.node:
                self.node.stop()
            self.destroy()

class SendDialog(simpledialog.Dialog):
    def __init__(self, parent):
        self.recipient = None
        self.amount = None
        super().__init__(parent)

    def body(self, master):
        self.title("Kirim ARTH")

        ttk.Label(master, text="Alamat Penerima:").grid(row=0, sticky=tk.W, padx=5, pady=2)
        self.recipient_entry = ttk.Entry(master, width=60)
        self.recipient_entry.grid(row=1, padx=5, pady=5)

        ttk.Label(master, text="Jumlah ARTH:").grid(row=2, sticky=tk.W, padx=5, pady=2)
        self.amount_entry = ttk.Entry(master, width=30)
        self.amount_entry.grid(row=3, padx=5, pady=5)

        return self.recipient_entry

    def apply(self):
        try:
            recipient = self.recipient_entry.get().strip()
            amount = Decimal(self.amount_entry.get())

            if not recipient or amount <= 0 or len(recipient) < 64:
                raise ValueError("Input tidak valid")

            self.recipient = recipient
            self.amount = amount

        except (ValueError, TypeError, InvalidOperation):
            self.recipient = None
            self.amount = None
            messagebox.showerror("Error", "Alamat atau jumlah tidak valid.")

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5002
    setup_gui_logging(port)
    app = ArthaCore()
    app.mainloop()
