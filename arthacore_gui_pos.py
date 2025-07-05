# arthacore_gui_pos.py

import customtkinter as ctk
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
import threading
import queue
import logging
import os
import sys
import time
from decimal import Decimal, InvalidOperation
import json

# Import modul-modul ArthaChain PoS
from artha_blockchain_pos import ArthaBlockchainPoS
from artha_wallet import ArthaWallet
from artha_node_pos import ArthaNodePoS
from artha_utils import json_serialize

# --- Konfigurasi Logging untuk GUI ---
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        self.log_queue.put(self.format(record))

class ArthaCoreGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Konfigurasi Window Utama ---
        self.title("ArthaCore - PoS Explorer")
        self.geometry("1280x800")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # --- Inisialisasi Backend ---
        self.wallet = None
        self.blockchain = None
        self.node = None
        self.is_running = True
        self.log_queue = queue.Queue()
        
        # --- State untuk mencegah flickering ---
        self.displayed_history_ids = set()
        self.displayed_mempool_ids = set()

        # --- Setup UI ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.create_sidebar()
        self.create_main_view()

        self.after(100, self.initialize_backend)

    # --- Bagian Inisialisasi & Backend ---
    def initialize_backend(self):
        password_dialog = ctk.CTkInputDialog(text="Masukkan password untuk dompet utama:", title="Login Dompet")
        password = password_dialog.get_input()

        if not password:
            self.destroy()
            return

        self.setup_gui_logging(5002)
        backend_thread = threading.Thread(target=self.run_backend_services, args=(password,), daemon=True)
        backend_thread.start()

        self.process_log_queue()
        self.update_ui_loop()

    def run_backend_services(self, password):
        try:
            self.wallet = ArthaWallet(password=password)
            self.blockchain = ArthaBlockchainPoS()
            self.node = ArthaNodePoS('0.0.0.0', 5002, self.blockchain)
            self.node.start()
            logging.info("Backend services started successfully.")
        except Exception as e:
            logging.critical(f"Failed to initialize backend: {e}")
            messagebox.showerror("Error Backend", f"Gagal memulai layanan backend: {e}")
            self.is_running = False

    def setup_gui_logging(self, port):
        log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, f"arthacore_gui_{port}.log")
        
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        if root_logger.handlers:
            for handler in root_logger.handlers[:]: root_logger.removeHandler(handler)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler = logging.FileHandler(log_file_path, mode='w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setLevel(logging.INFO)
        root_logger.addHandler(queue_handler)

    # --- Bagian Pembuatan UI ---
    def create_sidebar(self):
        sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        sidebar_frame.grid(row=0, column=0, rowspan=4, sticky="nsew")
        sidebar_frame.grid_rowconfigure(5, weight=1)

        logo_label = ctk.CTkLabel(sidebar_frame, text="ArthaCore", font=ctk.CTkFont(size=20, weight="bold"))
        logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.dashboard_button = ctk.CTkButton(sidebar_frame, text="Dompet Saya", command=lambda: self.select_frame_by_name("dashboard"))
        self.dashboard_button.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.explorer_button = ctk.CTkButton(sidebar_frame, text="Explorer", command=lambda: self.select_frame_by_name("explorer"))
        self.explorer_button.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.mempool_button = ctk.CTkButton(sidebar_frame, text="Mempool & Blok", command=lambda: self.select_frame_by_name("mempool"))
        self.mempool_button.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        self.log_button = ctk.CTkButton(sidebar_frame, text="Log Sistem", command=lambda: self.select_frame_by_name("log"))
        self.log_button.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

    def create_main_view(self):
        self.dashboard_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.explorer_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.mempool_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.log_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")

        self.create_dashboard_content(self.dashboard_frame)
        self.create_explorer_content(self.explorer_frame)
        self.create_mempool_content(self.mempool_frame)
        self.create_log_content(self.log_frame)

        self.select_frame_by_name("dashboard")

    def create_dashboard_content(self, parent_frame):
        parent_frame.grid_columnconfigure(0, weight=1)
        balance_frame = ctk.CTkFrame(parent_frame); balance_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=20, sticky="ew")
        balance_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(balance_frame, text="SALDO DOMPET SAYA", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray50").pack(pady=(10,0))
        self.balance_label = ctk.CTkLabel(balance_frame, text="0.00000000 ARTH", font=ctk.CTkFont(size=40, weight="bold")); self.balance_label.pack(pady=(0,10))
        address_frame = ctk.CTkFrame(parent_frame); address_frame.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        ctk.CTkLabel(address_frame, text="Alamat Dompet Saya:", anchor="w").pack(fill="x", padx=15, pady=(10,0))
        self.address_entry = ctk.CTkEntry(address_frame, placeholder_text="Memuat alamat...", font=ctk.CTkFont(family="Courier"), justify="center"); self.address_entry.pack(fill="x", padx=15, pady=(0,15), ipady=5)
        send_button = ctk.CTkButton(parent_frame, text="Kirim ARTH", height=40, command=self.open_send_dialog); send_button.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        refresh_button = ctk.CTkButton(parent_frame, text="Refresh Data", height=40, fg_color="gray50", hover_color="gray60", command=self.update_ui_loop); refresh_button.grid(row=2, column=1, padx=20, pady=10, sticky="ew")
        history_frame = ctk.CTkFrame(parent_frame); history_frame.grid(row=3, column=0, columnspan=2, padx=20, pady=20, sticky="nsew")
        parent_frame.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(history_frame, text="Histori Transaksi Saya", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10, padx=15, anchor="w")
        self.history_scroll_frame = ctk.CTkScrollableFrame(history_frame, label_text=""); self.history_scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def create_explorer_content(self, parent_frame):
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(2, weight=1)
        
        search_frame = ctk.CTkFrame(parent_frame)
        search_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="Cari berdasarkan alamat...", height=40)
        self.search_entry.grid(row=0, column=0, padx=(10,10), pady=10, sticky="ew")
        self.search_button = ctk.CTkButton(search_frame, text="Cari", width=100, height=40, command=self.search_address)
        self.search_button.grid(row=0, column=1, padx=(0,10), pady=10)

        result_frame = ctk.CTkFrame(parent_frame)
        result_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.searched_balance_label = ctk.CTkLabel(result_frame, text="Saldo Alamat: -", font=ctk.CTkFont(size=16, weight="bold"))
        self.searched_balance_label.pack(pady=10)

        searched_history_frame = ctk.CTkFrame(parent_frame)
        searched_history_frame.grid(row=2, column=0, padx=20, pady=20, sticky="nsew")
        ctk.CTkLabel(searched_history_frame, text="Histori Alamat yang Dicari", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10, padx=15, anchor="w")
        self.searched_history_scroll_frame = ctk.CTkScrollableFrame(searched_history_frame, label_text="")
        self.searched_history_scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def create_mempool_content(self, parent_frame):
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(0, weight=1)
        
        main_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        main_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        main_frame.grid_columnconfigure(0, weight=1); main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        
        blocks_frame = ctk.CTkFrame(main_frame); blocks_frame.grid(row=0, column=0, padx=(0,10), sticky="nsew")
        blocks_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(blocks_frame, text="Aliran Blok Global", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10, padx=15, anchor="w")
        self.blocks_scroll_frame = ctk.CTkScrollableFrame(blocks_frame, label_text=""); self.blocks_scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # --- FITUR BARU: Tombol di bawah daftar blok ---
        blocks_action_frame = ctk.CTkFrame(blocks_frame, fg_color="transparent")
        blocks_action_frame.pack(fill="x", padx=10, pady=10)
        blocks_action_frame.grid_columnconfigure((0,1), weight=1)
        ctk.CTkLabel(blocks_action_frame, text="Menampilkan 10 blok terakhir.", text_color="gray50", font=ctk.CTkFont(size=12)).grid(row=0, column=0, columnspan=2, pady=(0,5))
        ctk.CTkButton(blocks_action_frame, text="Download Blockchain Lengkap", command=self.download_full_blockchain).grid(row=1, column=0, padx=(0,5), sticky="ew")
        ctk.CTkButton(blocks_action_frame, text="Paksa Sinkronisasi Ulang", command=self.force_resync).grid(row=1, column=1, padx=(5,0), sticky="ew")

        mempool_frame = ctk.CTkFrame(main_frame); mempool_frame.grid(row=0, column=1, padx=(10,0), sticky="nsew")
        ctk.CTkLabel(mempool_frame, text="Mempool Global", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10, padx=15, anchor="w")
        self.mempool_scroll_frame = ctk.CTkScrollableFrame(mempool_frame, label_text=""); self.mempool_scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def create_log_content(self, parent_frame):
        parent_frame.grid_rowconfigure(0, weight=1); parent_frame.grid_columnconfigure(0, weight=1)
        self.log_textbox = ctk.CTkTextbox(parent_frame, font=ctk.CTkFont(family="Courier", size=12)); self.log_textbox.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.log_textbox.configure(state="disabled")

    # --- Logika Navigasi & Update UI ---
    def select_frame_by_name(self, name):
        buttons = {"dashboard": self.dashboard_button, "explorer": self.explorer_button, "mempool": self.mempool_button, "log": self.log_button}
        frames = {"dashboard": self.dashboard_frame, "explorer": self.explorer_frame, "mempool": self.mempool_frame, "log": self.log_frame}
        
        for btn in buttons.values():
            btn.configure(fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"])
        for frm in frames.values():
            frm.grid_forget()

        buttons[name].configure(fg_color=ctk.ThemeManager.theme["CTkButton"]["hover_color"])
        frames[name].grid(row=0, column=1, sticky="nsew")
    
    def update_ui_loop(self):
        if self.is_running and self.wallet and self.blockchain:
            self.update_dashboard_data()
            self.update_network_data()
        self.after(3000, self.update_ui_loop)

    def update_dashboard_data(self):
        balance = self.blockchain.get_balance(self.wallet.get_public_address())
        self.balance_label.configure(text=f"{balance:.8f} ARTH")
        
        # --- PERBAIKAN: Selalu update alamat jika belum ada ---
        addr = self.wallet.get_public_address()
        if self.address_entry.get() != addr:
            self.address_entry.delete(0, tk.END); self.address_entry.insert(0, addr)
            
        self.update_history_view()

    def update_network_data(self):
        self.update_blocks_view()
        self.update_mempool_view()

    def update_history_view(self):
        my_address = self.wallet.get_public_address()
        all_txs = [(tx, block['index']) for block in self.blockchain.chain for tx in block['transactions']]
        
        for tx, block_index in reversed(all_txs):
            if tx['sender'] == my_address or tx['recipient'] == my_address:
                tx_id = tx['transaction_id']
                if tx_id not in self.displayed_history_ids:
                    self.displayed_history_ids.add(tx_id)
                    tx_frame = self.create_transaction_widget(self.history_scroll_frame, tx, my_address)
                    tx_frame.pack(fill="x", pady=5, padx=5)

    def update_blocks_view(self):
        # --- PERBAIKAN: Hanya menampilkan 10 blok terakhir ---
        for widget in self.blocks_scroll_frame.winfo_children():
            widget.destroy()
        
        for block in reversed(self.blockchain.chain[-10:]):
            block_frame = ctk.CTkFrame(self.blocks_scroll_frame, fg_color="gray20")
            label_text = f"Blok #{block['index']} | Tx: {len(block['transactions'])}"
            ctk.CTkLabel(block_frame, text=label_text, font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,0))
            
            # --- PERBAIKAN: Alamat validator bisa diklik ---
            validator_address = block['validator']
            validator_button = ctk.CTkButton(block_frame, text=f"Validator: {validator_address[:25]}...",
                                             fg_color="transparent", text_color="gray50", hover=False,
                                             command=lambda addr=validator_address: self.click_and_search_address(addr))
            validator_button.pack(anchor="w", padx=5)
            
            block_frame.pack(fill="x", pady=5, padx=5)

    def update_mempool_view(self):
        current_mempool_ids = {tx['transaction_id'] for tx in self.blockchain.pending_transactions}
        
        ids_to_remove = self.displayed_mempool_ids - current_mempool_ids
        for widget in self.mempool_scroll_frame.winfo_children():
            if hasattr(widget, 'tx_id') and widget.tx_id in ids_to_remove:
                widget.destroy()
        self.displayed_mempool_ids -= ids_to_remove

        for tx in self.blockchain.pending_transactions:
            if tx['transaction_id'] not in self.displayed_mempool_ids:
                self.displayed_mempool_ids.add(tx['transaction_id'])
                tx_frame = ctk.CTkFrame(self.mempool_scroll_frame, fg_color="gray20")
                tx_frame.tx_id = tx['transaction_id']
                amount_text = f"Jumlah: {tx['amount']} ARTH"
                ctk.CTkLabel(tx_frame, text=amount_text, font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,0))
                
                # --- PERBAIKAN: Alamat pengirim bisa diklik ---
                sender_address = tx['sender']
                sender_button = ctk.CTkButton(tx_frame, text=f"Dari: {sender_address[:25]}...",
                                              fg_color="transparent", text_color="gray50", hover=False,
                                              command=lambda addr=sender_address: self.click_and_search_address(addr))
                sender_button.pack(anchor="w", padx=5)
                
                tx_frame.pack(fill="x", pady=5, padx=5)

    def process_log_queue(self):
        try:
            while True:
                record = self.log_queue.get_nowait()
                self.log_textbox.configure(state="normal"); self.log_textbox.insert("end", record + "\n")
                self.log_textbox.configure(state="disabled"); self.log_textbox.yview_moveto(1.0)
        except queue.Empty: pass
        finally:
            if self.is_running: self.after(200, self.process_log_queue)

    # --- Aksi Pengguna & Logika Explorer ---
    def search_address(self):
        address_to_search = self.search_entry.get().strip()
        if not address_to_search or len(address_to_search) != 64:
            messagebox.showerror("Error", "Alamat tidak valid. Harap masukkan 64 karakter.")
            return

        if not self.blockchain: return

        balance = self.blockchain.get_balance(address_to_search)
        self.searched_balance_label.configure(text=f"Saldo Alamat: {balance:.8f} ARTH")

        for widget in self.searched_history_scroll_frame.winfo_children():
            widget.destroy()

        all_txs = [(tx, block['index']) for block in self.blockchain.chain for tx in block['transactions']]
        found_tx = False
        for tx, block_index in reversed(all_txs):
            if tx['sender'] == address_to_search or tx['recipient'] == address_to_search:
                found_tx = True
                tx_frame = self.create_transaction_widget(self.searched_history_scroll_frame, tx, address_to_search)
                tx_frame.pack(fill="x", pady=5, padx=5)
        
        if not found_tx:
            ctk.CTkLabel(self.searched_history_scroll_frame, text="Tidak ada riwayat transaksi untuk alamat ini.", text_color="gray50").pack()

    def create_transaction_widget(self, parent, tx, perspective_address):
        tx_frame = ctk.CTkFrame(parent, fg_color="gray20")
        
        if tx['sender'] == perspective_address:
            tipe, color, amount_str, other_party = "KELUAR", "#E74C3C", f"- {tx['amount']}", tx['recipient']
        elif tx['recipient'] == perspective_address and tx['sender'] == "0":
            tipe, color, amount_str, other_party = "REWARD", "#3498DB", f"+ {tx['amount']}", "Coinbase"
        else:
            tipe, color, amount_str, other_party = "MASUK", "#2ECC71", f"+ {tx['amount']}", tx['sender']
        
        ctk.CTkLabel(tx_frame, text=tipe, font=ctk.CTkFont(weight="bold"), text_color=color).pack(side="left", padx=10)
        ctk.CTkLabel(tx_frame, text=amount_str, anchor="w").pack(side="left", padx=10, expand=True, fill="x")
        
        # --- PERBAIKAN: Alamat pihak lain bisa diklik ---
        if other_party != "Coinbase":
            other_party_button = ctk.CTkButton(tx_frame, text=f"Ke/Dari: {other_party[:15]}...", 
                                               fg_color="transparent", text_color="gray50", hover=False,
                                               command=lambda addr=other_party: self.click_and_search_address(addr))
            other_party_button.pack(side="right", padx=5)
        else:
            ctk.CTkLabel(tx_frame, text="Dari: Coinbase", text_color="gray50", anchor="e").pack(side="right", padx=10)
        
        return tx_frame

    def click_and_search_address(self, address):
        """Fungsi helper untuk membuat alamat bisa diklik."""
        self.select_frame_by_name("explorer")
        self.search_entry.delete(0, tk.END)
        self.search_entry.insert(0, address)
        self.search_address()

    def open_send_dialog(self):
        if not self.wallet: return
        dialog = ctk.CTkInputDialog(text="Masukkan alamat penerima:", title="Kirim ARTH - Langkah 1/2"); recipient = dialog.get_input()
        if not recipient: return
        dialog = ctk.CTkInputDialog(text=f"Jumlah ARTH yang akan dikirim ke:\n{recipient[:30]}...", title="Kirim ARTH - Langkah 2/2"); amount_str = dialog.get_input()
        if not amount_str: return
        try:
            amount = Decimal(amount_str)
            if amount <= 0: raise ValueError("Jumlah harus positif")
        except (InvalidOperation, ValueError) as e:
            messagebox.showerror("Error", f"Jumlah tidak valid: {e}"); return
        self.send_transaction(recipient, amount)

    def send_transaction(self, recipient, amount):
        try:
            if self.blockchain.get_balance(self.wallet.get_public_address()) < amount:
                messagebox.showerror("Gagal", "Saldo tidak mencukupi."); return
            
            tx_data_to_sign = {'sender': self.wallet.get_public_address(), 'recipient': recipient, 'amount': "{:.8f}".format(amount)}
            signature = self.wallet.sign_transaction(tx_data_to_sign)
            
            added_tx = self.blockchain.add_transaction(self.wallet.get_public_address(), recipient, amount, signature, self.wallet.public_key.export_key().decode('utf-8'))
            
            if added_tx:
                logging.info("Transaksi berhasil dibuat, menyiarkan ke jaringan...")
                tx_for_broadcast = json.loads(json_serialize(added_tx).decode('utf-8'))
                self.node.broadcast_message('NEW_TRANSACTION', {'transaction': tx_for_broadcast, 'public_key_str': self.wallet.public_key.export_key().decode('utf-8')})
                messagebox.showinfo("Sukses", f"Transaksi sebesar {amount} ARTH ke {recipient[:15]}... berhasil disiarkan.")
            else:
                messagebox.showerror("Gagal", "Gagal membuat transaksi. Mungkin sudah ada di mempool.")
        except Exception as e:
            messagebox.showerror("Error Transaksi", f"Terjadi kesalahan: {e}")
            logging.error(f"Transaction error: {e}", exc_info=True)

    def download_full_blockchain(self):
        """Menyimpan seluruh chain ke file JSON."""
        if not self.blockchain: return
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            title="Simpan Blockchain Lengkap"
        )
        if not filepath: return
        
        try:
            with open(filepath, 'w') as f:
                # Gunakan json_serialize untuk menangani Decimal
                chain_data = json.loads(json_serialize(self.blockchain.chain).decode('utf-8'))
                json.dump(chain_data, f, indent=4)
            messagebox.showinfo("Sukses", f"Blockchain berhasil disimpan di:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Gagal menyimpan file: {e}")

    def force_resync(self):
        """Memaksa sinkronisasi ulang dengan jaringan."""
        if not self.node: return
        self.node.trigger_full_resync()
        messagebox.showinfo("Info", "Permintaan sinkronisasi ulang telah dikirim ke semua peer.")

    def on_closing(self):
        if messagebox.askokcancel("Keluar", "Yakin ingin keluar dari ArthaCore?"):
            self.is_running = False
            if self.node: self.node.stop()
            self.destroy()

if __name__ == "__main__":
    app = ArthaCoreGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
