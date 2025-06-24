# artha_gui.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
import queue
import logging
import os
import sys

# Import modul-modul ArthaChain Anda
from artha_wallet import ArthaWallet
from artha_blockchain import ArthaBlockchain
from artha_node import ArthaNode

# --- Konfigurasi Logging untuk GUI ---
class QueueHandler(logging.Handler):
    """
    Class to send logging records to a queue
    It can be used from different threads
    """
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

def setup_logging():
    """Sets up logging to console, a file, and the GUI."""
    log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "artha_gui.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Hapus handler yang ada untuk menghindari duplikasi
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # File Handler
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console Handler (opsional, bisa dimatikan jika GUI sudah cukup)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    return log_file_path

# --- Kelas Utama Aplikasi GUI ---
class ArthaGUI(tk.Tk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("ArthaChain Wallet & Node")
        self.geometry("800x650")
        
        # Inisialisasi komponen backend
        self.wallet = None
        self.blockchain = None
        self.node = None
        self.password = None # Akan menyimpan password selama sesi berjalan

        # Setup logging
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.queue_handler.setFormatter(formatter)
        logging.getLogger().addHandler(self.queue_handler)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.create_widgets()
        self.after(100, self.ask_for_password)

    def ask_for_password(self):
        """Meminta password untuk membuka dompet."""
        self.password = simpledialog.askstring("Password Dompet", "Masukkan password untuk membuka atau membuat dompet:", show='*')
        if not self.password:
            messagebox.showerror("Error", "Password dibutuhkan untuk melanjutkan.")
            self.destroy()
            return
        
        # Setelah mendapatkan password, inisialisasi semua komponen
        self.initialize_backend()

    def initialize_backend(self):
        """Inisialisasi Wallet, Blockchain, dan Node setelah password didapat."""
        try:
            self.wallet = ArthaWallet(password=self.password)
        except ValueError as e:
            messagebox.showerror("Login Gagal", str(e))
            self.destroy()
            return

        public_address = self.wallet.get_public_address()
        self.address_var.set(public_address)
        
        self.blockchain = ArthaBlockchain()
        
        # Konfigurasi port dari argumen command line jika ada
        app_port = 5000
        if len(sys.argv) > 1:
            try:
                app_port = int(sys.argv[1])
            except ValueError:
                logging.warning(f"Invalid port provided, using default {app_port}")

        self.node = ArthaNode('0.0.0.0', app_port, self.blockchain, is_miner=False)
        
        # Jalankan node di thread terpisah agar tidak memblokir GUI
        self.node_thread = threading.Thread(target=self.node.start, daemon=True)
        self.node_thread.start()
        
        logging.info("Backend berhasil diinisialisasi. Node sedang berjalan.")

        # Mulai loop pembaruan GUI
        self.update_gui_data()
        self.process_log_queue()

    def create_widgets(self):
        """Membangun semua elemen UI."""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        # Tab 1: Wallet
        wallet_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(wallet_frame, text='Dompet')
        self.create_wallet_tab(wallet_frame)

        # Tab 2: Blockchain
        blockchain_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(blockchain_frame, text='Blockchain')
        self.create_blockchain_tab(blockchain_frame)
        
        # Tab 3: Jaringan
        network_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(network_frame, text='Jaringan')
        self.create_network_tab(network_frame)

        # Tab 4: Log
        log_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_frame, text='Log Aktivitas')
        self.create_log_tab(log_frame)

    def create_wallet_tab(self, parent):
        """Membuat konten untuk tab Dompet."""
        # Info Alamat
        ttk.Label(parent, text="Alamat Dompet Anda:", font=("Helvetica", 12, "bold")).pack(pady=5)
        self.address_var = tk.StringVar(value="...")
        address_entry = ttk.Entry(parent, textvariable=self.address_var, state="readonly", width=70, font=("Courier", 10))
        address_entry.pack(pady=5, padx=10, fill='x')

        # Info Saldo
        ttk.Label(parent, text="Saldo:", font=("Helvetica", 12, "bold")).pack(pady=(20, 5))
        self.balance_var = tk.StringVar(value="... ARTH")
        balance_label = ttk.Label(parent, textvariable=self.balance_var, font=("Helvetica", 24))
        balance_label.pack(pady=5)

        # Tombol Aksi
        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=30)
        
        send_button = ttk.Button(button_frame, text="Kirim ARTH", command=self.open_send_dialog, width=20)
        send_button.grid(row=0, column=0, padx=10)
        
        refresh_button = ttk.Button(button_frame, text="Refresh Data", command=self.update_gui_data, width=20)
        refresh_button.grid(row=0, column=1, padx=10)

    def create_blockchain_tab(self, parent):
        """Membuat konten untuk tab Blockchain."""
        ttk.Label(parent, text="Tampilan Rantai Blok", font=("Helvetica", 14, "bold")).pack(pady=5)

        cols = ('Index', 'Timestamp', 'Miner', 'Tx Count', 'Hash')
        self.blockchain_tree = ttk.Treeview(parent, columns=cols, show='headings')
        for col in cols:
            self.blockchain_tree.heading(col, text=col)
            self.blockchain_tree.column(col, width=140, anchor='center')
        
        self.blockchain_tree.pack(expand=True, fill='both', pady=10)
        
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.blockchain_tree.yview)
        self.blockchain_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

    def create_network_tab(self, parent):
        """Membuat konten untuk tab Jaringan."""
        main_frame = ttk.Frame(parent)
        main_frame.pack(expand=True, fill='both')

        # Frame Kiri: Peers
        peers_frame = ttk.LabelFrame(main_frame, text="Peer Terhubung", padding="10")
        peers_frame.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        self.peers_list = tk.Listbox(peers_frame, height=15)
        self.peers_list.pack(expand=True, fill='both')

        # Frame Kanan: Transaksi Tertunda
        pending_tx_frame = ttk.LabelFrame(main_frame, text="Transaksi Tertunda", padding="10")
        pending_tx_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        self.pending_tx_list = tk.Listbox(pending_tx_frame, height=15)
        self.pending_tx_list.pack(expand=True, fill='both')

    def create_log_tab(self, parent):
        """Membuat konten untuk tab Log."""
        ttk.Label(parent, text="Log Aktivitas Sistem", font=("Helvetica", 14, "bold")).pack(pady=5)
        self.log_text = tk.Text(parent, state='disabled', wrap='word', height=20, font=("Courier", 9))
        self.log_text.pack(expand=True, fill='both', pady=10)
        
        scrollbar = ttk.Scrollbar(parent, command=self.log_text.yview)
        self.log_text['yscrollcommand'] = scrollbar.set
        scrollbar.pack(side='right', fill='y')

    def update_gui_data(self):
        """Fungsi utama untuk me-refresh semua data di GUI."""
        if not self.wallet or not self.blockchain:
            # Backend belum siap, coba lagi nanti
            self.after(1000, self.update_gui_data)
            return

        # Update Saldo
        balance = self.blockchain.get_balance(self.wallet.get_public_address())
        self.balance_var.set(f"{balance:.8f} ARTH")
        
        # Update Blockchain Tree
        self.blockchain_tree.delete(*self.blockchain_tree.get_children())
        chain_copy = self.blockchain.chain[:] # Salin rantai untuk keamanan thread
        for block in reversed(chain_copy):
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(block['timestamp']))
            miner = block['miner_address'][:15] + '...' if len(block['miner_address']) > 15 else block['miner_address']
            tx_count = len(block['transactions'])
            block_hash = self.blockchain.hash_block(block)[:15] + '...'
            self.blockchain_tree.insert("", "end", values=(block['index'], ts, miner, tx_count, block_hash))

        # Update Peer List
        self.peers_list.delete(0, tk.END)
        if self.node:
            with self.node.lock:
                peers_copy = list(self.node.peers.keys())
            for peer in peers_copy:
                self.peers_list.insert(tk.END, peer)

        # Update Pending Transactions
        self.pending_tx_list.delete(0, tk.END)
        pending_tx_copy = self.blockchain.pending_transactions[:]
        for tx in pending_tx_copy:
            tx_str = f"From: {tx['sender'][:10]}... To: {tx['recipient'][:10]}... Amt: {tx['amount']}"
            self.pending_tx_list.insert(tk.END, tx_str)

        # Jadwalkan pembaruan berikutnya
        self.after(5000, self.update_gui_data)

    def process_log_queue(self):
        """Memproses antrian log dan menampilkannya di Text widget."""
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
        """Membuka dialog untuk mengirim ARTH."""
        dialog = SendDialog(self)
        self.wait_window(dialog)
        
        if dialog.recipient and dialog.amount:
            recipient = dialog.recipient
            amount = dialog.amount
            
            # Verifikasi password sebelum mengirim
            current_password = simpledialog.askstring("Konfirmasi Password", "Masukkan password dompet Anda untuk menandatangani transaksi:", show='*')
            
            if not current_password or current_password != self.password:
                messagebox.showerror("Gagal", "Password salah. Transaksi dibatalkan.")
                return

            try:
                # Periksa saldo
                if self.blockchain.get_balance(self.wallet.get_public_address()) < amount:
                    messagebox.showerror("Gagal", "Saldo tidak mencukupi.")
                    return

                # Buat transaksi
                transaction_data = {
                    'sender': self.wallet.get_public_address(),
                    'recipient': recipient,
                    'amount': amount
                }
                
                # Gunakan password yang dikonfirmasi untuk sign
                signature = self.wallet.sign_transaction(transaction_data, current_password)
                
                # Tambah dan siarkan transaksi
                added_tx = self.blockchain.add_transaction(
                    self.wallet.get_public_address(), recipient, amount, signature, 
                    self.wallet.public_key.export_key().decode('utf-8')
                )
                
                if added_tx:
                    self.node.broadcast_message('NEW_TRANSACTION', {
                        'transaction': added_tx,
                        'public_key_str': self.wallet.public_key.export_key().decode('utf-8')
                    })
                    messagebox.showinfo("Sukses", "Transaksi berhasil dibuat dan disiarkan ke jaringan.")
                else:
                    messagebox.showerror("Gagal", "Gagal membuat transaksi. Cek log untuk detail.")

            except Exception as e:
                logging.error(f"Error saat mengirim transaksi: {e}")
                messagebox.showerror("Error", f"Terjadi kesalahan: {e}")


    def on_closing(self):
        """Handler saat jendela aplikasi ditutup."""
        if messagebox.askokcancel("Keluar", "Apakah Anda yakin ingin keluar dari ArthaChain?"):
            if self.node:
                logging.info("Menghentikan node...")
                self.node.stop()
            self.destroy()

class SendDialog(simpledialog.Dialog):
    """Dialog kustom untuk input pengiriman ARTH."""
    def body(self, master):
        self.title("Kirim ARTH")
        
        ttk.Label(master, text="Alamat Penerima:").grid(row=0, sticky=tk.W)
        self.recipient_entry = ttk.Entry(master, width=50)
        self.recipient_entry.grid(row=1, padx=5, pady=5)

        ttk.Label(master, text="Jumlah ARTH:").grid(row=2, sticky=tk.W)
        self.amount_entry = ttk.Entry(master, width=20)
        self.amount_entry.grid(row=3, padx=5, pady=5)
        
        return self.recipient_entry # initial focus

    def apply(self):
        try:
            recipient = self.recipient_entry.get()
            amount = float(self.amount_entry.get())
            if not recipient or amount <= 0:
                raise ValueError("Input tidak valid")
            self.recipient = recipient
            self.amount = amount
        except ValueError:
            messagebox.showerror("Error", "Alamat penerima atau jumlah tidak valid.")
            self.recipient = None
            self.amount = None

# --- Main execution ---
if __name__ == "__main__":
    setup_logging()
    app = ArthaGUI()
    app.mainloop()

