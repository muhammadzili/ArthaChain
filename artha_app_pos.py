# artha_app_pos.py

import time
import logging
import os
import sys
import getpass
import json 
from decimal import Decimal, InvalidOperation

from artha_blockchain_pos import ArthaBlockchainPoS
from artha_wallet import ArthaWallet
from artha_node_pos import ArthaNodePoS
from artha_utils import json_serialize 

logger = logging.getLogger(__name__)

APP_HOST = '0.0.0.0'
APP_PORT = 5002
LOG_FILE_PATH = ""

def setup_logging(port):
    global LOG_FILE_PATH
    log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
    os.makedirs(log_dir, exist_ok=True)
    LOG_FILE_PATH = os.path.join(log_dir, f"artha_app_pos_{port}.log")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if root_logger.handlers:
        for handler in root_logger.handlers[:]: root_logger.removeHandler(handler)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(LOG_FILE_PATH, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

def display_menu():
    print("\n" + "="*40)
    print("      ARTHACHAIN PoS - MENU PENGGUNA")
    print("="*40)
    print("1. Tampilkan Info Dompet (Alamat & Saldo)")
    print("2. Kirim ARTH")
    print("3. Tampilkan Peer Terhubung")
    print("4. Tampilkan Info Blockchain")
    print("5. Keluar")
    print("="*40)

def run_app():
    # Membaca argumen dari baris perintah
    # Argumen 1: Port (opsional)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else APP_PORT
    # Argumen 2: Nama file dompet (opsional)
    wallet_file = sys.argv[2] if len(sys.argv) > 2 else 'wallet.dat'
    
    setup_logging(port)

    try:
        password = getpass.getpass(f"Masukkan password untuk dompet '{wallet_file}': ")
        # Gunakan wallet_file yang ditentukan
        wallet = ArthaWallet(wallet_file=wallet_file, password=password)
    except Exception as e:
        logging.error(f"Gagal memuat dompet: {e}")
        return

    public_address = wallet.get_public_address()
    blockchain = ArthaBlockchainPoS()
    node = ArthaNodePoS(APP_HOST, port, blockchain)
    node.start()

    logger.info(f"\nBerhasil masuk ke dompet: {wallet_file}")
    logger.info(f"Alamat Dompet: {public_address}")
    logger.info(f"Node Pengguna Berjalan di: {APP_HOST}:{port}")

    try:
        while True:
            display_menu()
            choice = input("Pilih opsi (1-5): ")

            if choice == '1':
                balance = blockchain.get_balance(public_address)
                print(f"\nAlamat: {public_address}")
                print(f"Saldo  : {balance:.8f} ARTH")

            elif choice == '2':
                recipient = input("Alamat penerima: ")
                try:
                    amount = Decimal(input("Jumlah ARTH: "))
                    if amount <= 0: raise InvalidOperation
                except InvalidOperation:
                    print("Jumlah tidak valid.")
                    continue

                if blockchain.get_balance(public_address) < amount:
                    print("Saldo tidak mencukupi.")
                    continue
                
                tx_data_to_sign = {'sender': public_address, 'recipient': recipient, 'amount': "{:.8f}".format(amount)}
                signature = wallet.sign_transaction(tx_data_to_sign)
                
                added_tx = blockchain.add_transaction(
                    public_address, recipient, amount, signature, 
                    wallet.public_key.export_key().decode('utf-8')
                )
                
                if added_tx:
                    logger.info("Transaksi berhasil dibuat, menyiarkan ke jaringan...")
                    tx_for_broadcast = json.loads(json_serialize(added_tx).decode('utf-8'))
                    node.broadcast_message('NEW_TRANSACTION', {
                        'transaction': tx_for_broadcast,
                        'public_key_str': wallet.public_key.export_key().decode('utf-8')
                    })
                else:
                    logger.warning("Gagal membuat transaksi.")
            
            elif choice == '3':
                with node.lock: peers = list(node.peers.keys())
                print(f"\nPeer Terhubung ({len(peers)}):")
                for peer in peers: print(f"- {peer}")

            elif choice == '4':
                last_block = blockchain.last_block
                print("\n--- Info Blockchain (PoS) ---")
                print(f"Tinggi Blok   : {last_block['index']}")
                print(f"Hash Terakhir : {blockchain.hash_block(last_block)[:20]}...")
                print(f"Validator Blok: {last_block['validator'][:20]}...")

            elif choice == '5':
                break
            else:
                print("Pilihan tidak valid.")

    except KeyboardInterrupt:
        logger.info("\nAplikasi dihentikan.")
    finally:
        node.stop()

if __name__ == '__main__':
    run_app()
