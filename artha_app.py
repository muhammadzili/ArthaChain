# artha_app.py

import time
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
from artha_node import ArthaNode
import threading
import sys

# App Node Configuration
APP_HOST = '127.0.0.1'
APP_PORT = 5000 # Default port for the app

def display_menu():
    """
    Displays the menu options for the user.
    """
    print("\n" + "="*40)
    print("          ARTHACHAIN MENU")
    print("="*40)
    print("1. Show Address & Balance")
    print("2. Send ARTH")
    print("3. Connect to Peer")
    print("4. Show Connected Peers")
    print("5. Show Blockchain")
    print("6. Show Pending Transactions")
    print("7. Synchronize Blockchain")
    print("8. Exit")
    print("="*40)

def run_app():
    """
    Main function to run the ArthaChain application.
    """
    wallet = ArthaWallet()
    public_address = wallet.get_public_address()
    blockchain = ArthaBlockchain()
    node = ArthaNode(APP_HOST, APP_PORT, blockchain, is_miner=False)
    node.start()

    print(f"\nYour Wallet Address: {public_address}")
    print(f"App Node Running at: {APP_HOST}:{APP_PORT}")
    print("Waiting for peers to synchronize blockchain...")
    
    # Give the node time to connect to peers and synchronize blockchain
    time.sleep(5) # Give time for initial synchronization

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

                # Create transaction data to be signed
                transaction_data = {
                    'sender': public_address,
                    'recipient': recipient,
                    'amount': amount
                }
                
                # Sign the transaction
                signature = wallet.sign_transaction(transaction_data)
                
                # Add the transaction to the local pending list
                # and broadcast it to the network.
                # Note: add_transaction in blockchain will verify
                # the signature again upon receiving a broadcast.
                if blockchain.add_transaction(public_address, recipient, amount, signature, wallet.public_key.export_key().decode('utf-8')):
                    print("Transaction successfully created and added to queue. Waiting to be included in a block.")
                    node.broadcast_message('NEW_TRANSACTION', {
                        'transaction': {
                            'sender': public_address,
                            'recipient': recipient,
                            'amount': amount,
                            'signature': signature,
                            'timestamp': time.time() # Same timestamp for broadcast
                        },
                        'public_key_str': wallet.public_key.export_key().decode('utf-8')
                    })
                else:
                    print("Failed to create transaction.")

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
                    for peer in node.peers:
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
                        print(f"  Miner: {block['miner_address']}")
                        print(f"  Previous Hash: {block['previous_hash'][:10]}...")
                        print(f"  Block Hash: {blockchain.hash_block(block)[:10]}...")
                        print(f"  Transaction Count: {len(block['transactions'])}")
                        if block['transactions']:
                            print("  Transactions:")
                            for tx in block['transactions']:
                                print(f"    - From: {tx['sender'][:10]}... To: {tx['recipient'][:10]}... Amount: {tx['amount']}")
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
                print("Triggering blockchain synchronization...")
                node.sync_blockchain_on_startup()

            elif choice == '8':
                print("Exiting ArthaChain application. Goodbye!")
                break

            else:
                print("Invalid choice. Please try again.")

    except KeyboardInterrupt:
        print("\nApplication stopped by user.")
    finally:
        node.stop()

if __name__ == '__main__':
    # Allow user to specify port from command line arguments
    if len(sys.argv) > 1:
        try:
            APP_PORT = int(sys.argv[1])
            if not (1024 <= APP_PORT <= 65535):
                raise ValueError("Port must be between 1024 and 65535.")
        except ValueError as e:
            print(f"Port error: {e}. Using default port {APP_PORT}.")

    run_app()

