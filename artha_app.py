# artha_app.py

import time
import logging
import os
import sys
import getpass
import threading
from decimal import Decimal, InvalidOperation
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
from artha_node import ArthaNode

APP_HOST = '0.0.0.0'
APP_PORT = 5000

def setup_logging(port):
    """Sets up logging to console and a file with a unique name."""
    log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"artha_app_{port}.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # Console handler for important messages only
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    root_logger.addHandler(console_handler)

    # File handler for all debug messages
    file_handler = logging.FileHandler(log_file_path, mode='w')
    file_handler.setLevel(logging.DEBUG)
    formatter_file = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter_file)
    root_logger.addHandler(file_handler)
    
    global LOG_FILE_PATH
    LOG_FILE_PATH = log_file_path

def display_menu():
    """Displays the menu options for the user."""
    print("\n" + "="*46)
    print("            ARTHACHAIN MENU")
    print("="*46)
    print("1.  Alamat & Saldo")
    print("2.  Kirim ARTH")
    print("3.  Peer Terhubung")
    print("4.  Tambah Peer Baru")
    print("5.  Hapus Peer")
    print("6.  Daftar Peer Tersimpan")
    print("7.  Status Sinkronisasi")
    print("8.  Lihat Blockchain")
    print("9.  Transaksi Tertunda")
    print("10. Paksa Sinkronisasi Ulang")
    print("11. Lokasi File Log")
    print("12. Keluar")
    print("="*46)

def show_connected_peers(node):
    """Print the peers this node currently has an open connection to."""
    peers = node.get_peer_list()
    if not peers['connected']:
        print("\nTidak ada peer yang terhubung (masih mencoba konek / remote offline).")
        print("Cek menu 'Daftar Peer Tersimpan' (6) untuk melihat peer yang disimpan.")
        print("Gunakan menu 'Tambah Peer Baru' atau tunggu sinkronisasi otomatis.")
        return
    print("\nPeer yang Terhubung:")
    for peer in peers['connected']:
        print(f"- {peer}")

def add_new_peer(node):
    """Prompt for a peer address and register it."""
    print("\nMasukkan alamat peer dengan format host:port")
    print("Contoh: 127.0.0.1:5001  atau  203.0.113.10:5001")
    peer = input("Alamat peer: ").strip()
    if not peer:
        print("Alamat peer tidak boleh kosong.")
        return

    ok, message = node.add_peer(peer)
    if ok:
        print(message)
        print("Periksa 'Peer Terhubung' (menu 3) dalam beberapa detik...")
        # Ask right away so a fresh peer catches up immediately.
        sync_after_delay(node)
    else:
        print(f"Gagal: {message}")

def sync_after_delay(node, seconds=2):
    """Give a freshly added peer a moment, then pull whatever chain we lack."""
    def delayed():
        time.sleep(seconds)
        node.trigger_full_resync()
    threading.Thread(target=delayed, daemon=True).start()

def remove_peer(node):
    """Remove a manually added peer."""
    peers = node.get_peer_list()
    if not peers['manual']:
        print("\nBelum ada peer manual yang disimpan.")
        return
    print("\nPeer manual tersimpan:")
    for i, peer in enumerate(peers['manual'], 1):
        print(f"{i}. {peer}")
    target = input("Hapus peer (nomor atau host:port): ").strip()
    if target.isdigit() and 1 <= int(target) <= len(peers['manual']):
        target = peers['manual'][int(target) - 1]
    ok, message = node.remove_peer(target)
    print(message if ok else f"Gagal: {message}")

def show_peer_list(node):
    """Print every peer the node knows about, grouped by source."""
    peers = node.get_peer_list()
    print("\n--- Daftar Peer ---")
    print(f"Terhubung  ({len(peers['connected'])}):")
    for peer in peers['connected'] or ['-']:
        print(f"  - {peer}")
    print(f"Manual     ({len(peers['manual'])}):")
    for peer in peers['manual'] or ['-']:
        print(f"  - {peer}")
    print(f"Bootstrap  ({len(peers['bootstrap'])}):")
    for peer in peers['bootstrap'] or ['-']:
        print(f"  - {peer}")

def show_sync_status(node, blockchain):
    """Compare this node's height against the best height peers reported."""
    status = node.get_sync_status()
    height = status['height']
    best = status['best_known_height']

    print("\n--- Status Sinkronisasi ---")
    print(f"Node ini        : 0.0.0.0:{node.port}")
    print(f"Height lokal    : {height}")
    print(f"Height jaringan : {best}")
    print(f"Peer terhubung  : {status['peers']}")
    if status['in_sync']:
        print("Status          : SINKRON dengan jaringan")
    else:
        behind = best - height
        print(f"Status          : TERTINGGAL {behind} blok, sinkronisasi berjalan...")

def run_app():
    """Main function to run the ArthaChain application."""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else APP_PORT
    setup_logging(port)

    try:
        # --- PERBAIKAN: Meminta password sebelum membuat wallet ---
        password = getpass.getpass("Masukkan password dompet Anda: ")
        if not password:
            print("Password tidak boleh kosong.")
            return
        wallet = ArthaWallet(password=password)
    except ValueError as e:
        print(f"Gagal memuat dompet: {e}")
        return
    except (EOFError, KeyboardInterrupt):
        print("\nOperasi dibatalkan.")
        return

    public_address = wallet.get_public_address()
    blockchain = ArthaBlockchain()
    node = ArthaNode(APP_HOST, port, blockchain)
    node.start()

    logging.info(f"\nAlamat Dompet: {public_address}")
    logging.info(f"Node Aplikasi Berjalan di: {APP_HOST}:{port}")

    try:
        while True:
            display_menu()
            choice = input("Pilih opsi: ").strip()

            if choice == '1':
                balance = blockchain.get_balance(public_address)
                print(f"\nAlamat: {public_address}")
                print(f"Saldo: {balance:.8f} ARTH")

            elif choice == '2':
                recipient = input("Alamat penerima: ")
                try:
                    amount_str = input("Jumlah ARTH: ")
                    amount = Decimal(amount_str)
                except InvalidOperation:
                    print("Jumlah tidak valid.")
                    continue

                if blockchain.get_balance(public_address) < amount:
                    print("Saldo tidak mencukupi.")
                    continue

                canonical_amount_str = "{:.8f}".format(amount)
                transaction_data = {
                    'sender': public_address,
                    'recipient': recipient,
                    'amount': canonical_amount_str
                }
                
                signature = wallet.sign_transaction(transaction_data)
                
                added_tx = blockchain.add_transaction(
                    public_address, recipient, amount, signature, 
                    wallet.public_key.export_key().decode('utf-8')
                )
                
                if added_tx:
                    logging.info(f"Transaksi {added_tx['transaction_id'][:10]}... berhasil disiarkan.")
                    node.broadcast_message('NEW_TRANSACTION', {
                        'transaction': added_tx,
                        'public_key_str': wallet.public_key.export_key().decode('utf-8')
                    })
                    # Tell the network we are behind so peers push their tip to us.
                    node.trigger_full_resync()
                else:
                    logging.warning("Gagal membuat transaksi.")
            
            elif choice == '3':
                show_connected_peers(node)

            elif choice == '4':
                add_new_peer(node)

            elif choice == '5':
                remove_peer(node)

            elif choice == '6':
                show_peer_list(node)

            elif choice == '7':
                show_sync_status(node, blockchain)

            elif choice == '8':
                print("\n--- Blockchain ---")
                last = blockchain.last_block
                if not last:
                    print("Chain kosong.")
                else:
                    for block in blockchain.chain[-20:]:
                        print(f"Index: {block['index']}, Hash: {blockchain.hash_block(block)[:10]}...")
                    print(f"... total {len(blockchain.chain)} blok, tinggi saat ini {last['index']}")

            elif choice == '9':
                print("\nTransaksi Tertunda:")
                if not blockchain.pending_transactions:
                    print("Tidak ada.")
                else:
                    for tx in blockchain.pending_transactions:
                        print(f"- Dari: {tx['sender'][:10]}... Jumlah: {tx['amount']}")

            elif choice == '10':
                print("Memaksa sinkronisasi ulang dengan semua peer...")
                node.trigger_full_resync()
                time.sleep(2)
                show_sync_status(node, blockchain)

            elif choice == '11':
                print(f"\nLokasi file log: {LOG_FILE_PATH}")

            elif choice == '12':
                break
            else:
                print("Pilihan tidak valid.")

    except KeyboardInterrupt:
        logging.info("\nAplikasi dihentikan oleh pengguna.")
    finally:
        node.stop()

if __name__ == '__main__':
    run_app()