# artha_app.py

import time
import logging
import os
import sys
import getpass
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
    print("\n" + "="*40)
    print("          ARTHACHAIN MENU")
    print("="*40)
    print("1. Show Address & Balance")
    print("2. Send ARTH")
    print("3. Show Connected Peers")
    print("4. Show Blockchain")
    print("5. Show Pending Transactions")
    print("6. Force Re-sync with Peers")
    print("7. View Log File Path")
    print("8. Exit")
    print("="*40)

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
            choice = input("Pilih opsi: ")

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
                else:
                    logging.warning("Gagal membuat transaksi.")
            
            elif choice == '3':
                if not node.peers:
                    print("\nTidak ada peer yang terhubung.")
                else:
                    print("\nPeer yang Terhubung:")
                    with node.lock:
                        for peer in node.peers.keys():
                            print(f"- {peer}")

            elif choice == '4':
                print("\n--- Blockchain ---")
                for block in blockchain.chain:
                    print(f"Index: {block['index']}, Hash: {blockchain.hash_block(block)[:10]}...")

            elif choice == '5':
                print("\nTransaksi Tertunda:")
                if not blockchain.pending_transactions:
                    print("Tidak ada.")
                else:
                    for tx in blockchain.pending_transactions:
                        print(f"- Dari: {tx['sender'][:10]}... Jumlah: {tx['amount']}")
            
            elif choice == '6':
                print("Memaksa sinkronisasi ulang dengan semua peer...")
                node.trigger_full_resync()

            elif choice == '7':
                print(f"\nLokasi file log: {LOG_FILE_PATH}")

            elif choice == '8':
                break
            else:
                print("Pilihan tidak valid.")

    except KeyboardInterrupt:
        logging.info("\nAplikasi dihentikan oleh pengguna.")
    finally:
        node.stop()

if __name__ == '__main__':
    run_app()
