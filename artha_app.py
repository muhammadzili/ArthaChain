# artha_app.py

import time
import logging
import os
import sys
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

    # Console Handler: Only show WARNING and above to keep console clean
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING) # Changed to WARNING
    formatter_console = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(formatter_console)
    root_logger.addHandler(console_handler)

    # File Handler: For DEBUG and above (all messages)
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)
    formatter_file = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter_file)
    root_logger.addHandler(file_handler)

    logging.info(f"Logging configured. Console: WARNING+, File ('{log_file_path}'): DEBUG+")


def display_menu():
    """
    Displays the menu options for the user.
    """
    print("\n" + "="*40)
    print("          ARTHACHAIN MENU")
    print("="*40)
    print("1. Show Address & Balance")
    print("2. Send ARTH")
    print("3. Connect to Peer (Manual - Not needed with Bootstrap)")
    print("4. Show Connected Peers")
    print("5. Show Blockchain")
    print("6. Show Pending Transactions")
    print("7. Synchronize Blockchain (Manual Trigger)")
    print("8. Show Log") # New option
    print("9. Exit") # Changed to 9
    print("="*40)

def run_app():
    """
    Main function to run the ArthaChain application.
    """
    setup_logging("artha_app")

    wallet = ArthaWallet()
    public_address = wallet.get_public_address()
    blockchain = ArthaBlockchain()
    node = ArthaNode(APP_HOST, APP_PORT, blockchain, is_miner=False)
    node.start()

    logging.info(f"\nYour Wallet Address: {public_address}")
    logging.info(f"App Node Running at: {APP_HOST}:{APP_PORT}")
    logging.info("Waiting for peers to synchronize blockchain (automatic bootstrap connecting)...")
    
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

                transaction_data = {
                    'sender': public_address,
                    'recipient': recipient,
                    'amount': amount
                }
                
                signature = wallet.sign_transaction(transaction_data)
                
                added_transaction_obj = blockchain.add_transaction(public_address, recipient, amount, signature, wallet.public_key.export_key().decode('utf-8'))
                
                if added_transaction_obj:
                    logging.info("Transaction successfully created and added to queue. Waiting to be included in a block.")
                    node.broadcast_message('NEW_TRANSACTION', {
                        'transaction': added_transaction_obj,
                        'public_key_str': wallet.public_key.export_key().decode('utf-8')
                    })
                else:
                    logging.warning("Failed to create transaction.")

            elif choice == '3':
                peer_address = input("Enter peer address (e.g., 127.0.0.1:5001): ")
                try:
                    host, port_str = peer_address.split(':')
                    port = int(port_str)
                    node.connect_to_peer(host, port)
                except ValueError:
                    print("Invalid peer address format. Use HOST:PORT.")

            elif choice == '4':
                if node.peers:
                    print("\nConnected Peers:")
                    with node.lock:
                        for peer in node.peers.keys():
                            print(f"- {peer}")
                else:
                    print("\nNo connected peers.")

            elif choice == '5':
                print("\n" + "="*40)
                print("          ARTHACHAIN BLOCKCHAIN")
                print("="*40)
                if not blockchain.chain:
                    print("Blockchain is empty.")
                else:
                    for block in blockchain.chain:
                        print(f"--- Block #{block['index']} ---")
                        print(f"  Timestamp: {time.ctime(block['timestamp'])}")
                        print(f"  Miner: {block['miner_address'][:10]}...")
                        print(f"  Previous Hash: {block['previous_hash'][:10]}...")
                        print(f"  Block Hash: {blockchain.hash_block(block)[:10]}...")
                        print(f"  Difficulty: {hex(block['difficulty'])}")
                        print(f"  Nonce: {block['nonce']}")
                        print(f"  Transaction Count: {len(block['transactions'])}")
                        if block['transactions']:
                            print("  Transactions:")
                            for tx in block['transactions']:
                                if tx['sender'] != '0':
                                    print(f"    - From: {tx['sender'][:10]}... To: {tx['recipient'][:10]}... Amount: {tx['amount']}")
                                else:
                                    print(f"    - Coinbase: To: {tx['recipient'][:10]}... Amount: {tx['amount']}")
                        print("-" * 30)
                print("="*40)

            elif choice == '6':
                print("\nPending Transactions:")
                if node.blockchain.pending_transactions:
                    for tx in node.blockchain.pending_transactions:
                        print(f"- From: {tx['sender'][:10]}... To: {tx['recipient'][:10]}... Amount: {tx['amount']} ARTH")
                else:
                    print("No pending transactions.")

            elif choice == '7':
                logging.info("Manually triggering blockchain synchronization...")
                node.sync_blockchain_from_known_peers()

            elif choice == '8': # New: Show Log
                log_file_path = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs", "artha_app.log")
                print(f"\n--- Log File ({log_file_path}) ---")
                try:
                    with open(log_file_path, 'r') as f:
                        for line in f:
                            print(line.strip())
                except FileNotFoundError:
                    print("Log file not found. Run the app to generate logs.")
                print("--- End of Log ---")
                input("\nPress Enter to return to menu...") # Pause to allow user to read log

            elif choice == '9': # Changed from 8 to 9
                logging.info("Exiting ArthaChain application. Goodbye!")
                break

            else:
                print("Invalid choice. Please try again.")

    except KeyboardInterrupt:
        logging.info("\nApplication stopped by user.")
    finally:
        node.stop()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        try:
            APP_PORT = int(sys.argv[1])
            if not (1024 <= APP_PORT <= 65535):
                raise ValueError("Port must be between 1024 and 65535.")
        except ValueError as e:
            logging.error(f"Port error: {e}. Using default port {APP_PORT}.")

    run_app()
