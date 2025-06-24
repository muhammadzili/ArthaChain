# artha_app.py
# CATATAN: File ini adalah aplikasi CLI yang fungsional.
# GUI direkomendasikan, tetapi ini bekerja dengan baik untuk penggunaan terminal/server.

import time
import logging
import os
import sys
import getpass
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
from artha_node import ArthaNode

# App Node Configuration
APP_HOST = '0.0.0.0'
APP_PORT = 5000

def setup_logging(app_name):
    """Sets up logging to console and a file."""
    log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"{app_name}.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO) # Set to INFO for a bit more detail
    formatter_console = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(formatter_console)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)
    formatter_file = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter_file)
    root_logger.addHandler(file_handler)

    logging.info(f"Logging configured. Console: INFO+, File ('{log_file_path}'): DEBUG+")


def display_menu():
    """
    Displays the menu options for the user.
    """
    print("\n" + "="*40)
    print("      ARTHACHAIN TERMINAL")
    print("="*40)
    print("1. Show Address & Balance")
    print("2. Send ARTH")
    print("3. Show Connected Peers")
    print("4. Show Blockchain")
    print("5. Show Pending Transactions")
    print("6. Exit")
    print("="*40)

def run_app():
    """
    Main function to run the ArthaChain application.
    """
    setup_logging("artha_app_cli")

    # PERUBAHAN KRITIS: Meminta password untuk membuka dompet
    try:
        password = getpass.getpass("Masukkan password dompet Anda: ")
        if not password:
            print("Password tidak boleh kosong.")
            return
        wallet = ArthaWallet(password=password)
    except ValueError as e:
        print(f"Gagal memuat dompet: {e}")
        return
    except (ImportError, EOFError, KeyboardInterrupt):
        print("\nOperasi dibatalkan.")
        return


    public_address = wallet.get_public_address()
    blockchain = ArthaBlockchain()
    node = ArthaNode(APP_HOST, APP_PORT, blockchain, is_miner=False)
    node.start()

    logging.info(f"\nYour Wallet Address: {public_address}")
    logging.info(f"App Node Running at: {APP_HOST}:{APP_PORT}")
    logging.info("Waiting for peers to synchronize...")
    
    time.sleep(10)

    try:
        while True:
            display_menu()
            choice = input("Select an option: ")

            if choice == '1':
                balance = blockchain.get_balance(public_address)
                print(f"\nYour Address: {public_address}")
                print(f"Your Balance: {balance} ARTH")

            elif choice == '2':
                recipient = input("Enter recipient address: ")
                try:
                    amount = float(input("Enter amount of ARTH to send: "))
                    if amount <= 0:
                        print("Amount must be greater than zero.")
                        continue
                except ValueError:
                    print("Invalid amount.")
                    continue

                if blockchain.get_balance(public_address) < amount:
                    print("Insufficient balance.")
                    continue
                
                # Meminta password lagi untuk konfirmasi pengiriman
                tx_password = getpass.getpass("Konfirmasi password dompet untuk mengirim: ")
                if tx_password != password:
                    print("Password salah. Transaksi dibatalkan.")
                    continue

                transaction_data = {'sender': public_address, 'recipient': recipient, 'amount': amount}
                signature = wallet.sign_transaction(transaction_data, tx_password)
                
                added_tx = blockchain.add_transaction(public_address, recipient, amount, signature, wallet.public_key.export_key().decode('utf-8'))
                
                if added_tx:
                    logging.info("Transaction successfully created. Broadcasting...")
                    node.broadcast_message('NEW_TRANSACTION', {
                        'transaction': added_tx,
                        'public_key_str': wallet.public_key.export_key().decode('utf-8')
                    })
                else:
                    logging.warning("Failed to create transaction.")

            elif choice == '3':
                if not node.peers:
                    print("\nNo connected peers.")
                else:
                    print("\nConnected Peers:")
                    with node.lock:
                        for peer in node.peers.keys(): print(f"- {peer}")

            elif choice == '4':
                print("\n--- Blockchain ---")
                for block in blockchain.chain:
                    print(f"Index: {block['index']}, Hash: {blockchain.hash_block(block)[:10]}..., Txs: {len(block['transactions'])}")

            elif choice == '5':
                print("\nPending Transactions:")
                if not node.blockchain.pending_transactions:
                    print("No pending transactions.")
                else:
                    for tx in node.blockchain.pending_transactions:
                        print(f"- From: {tx['sender'][:10]}... To: {tx['recipient'][:10]}... Amount: {tx['amount']} ARTH")

            elif choice == '6':
                logging.info("Exiting ArthaChain application.")
                break

            else:
                print("Invalid choice.")

    except KeyboardInterrupt:
        logging.info("\nApplication stopped by user.")
    finally:
        node.stop()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        try:
            APP_PORT = int(sys.argv[1])
        except ValueError:
            logging.error(f"Invalid port. Using default {APP_PORT}.")

    run_app()
