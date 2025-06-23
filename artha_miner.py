# artha_miner.py

import time
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
from artha_node import ArthaNode
import threading
import sys

# Miner Node Configuration
MINER_HOST = '127.0.0.1'
MINER_PORT = 5001 # Default port for the miner
MINING_INTERVAL = 60 # Seconds (1 minute)

def run_miner():
    """
    Main function to run the ArthaChain miner.
    """
    wallet = ArthaWallet()
    miner_address = wallet.get_public_address()
    blockchain = ArthaBlockchain()
    node = ArthaNode(MINER_HOST, MINER_PORT, blockchain, is_miner=True)
    node.start()

    print("\n" + "="*40)
    print("      ARTHACHAIN MINER STARTED")
    print("="*40)
    print(f"Miner Address: {miner_address}")
    print(f"Miner Node Running at: {MINER_HOST}:{MINER_PORT}")
    print(f"Mining Interval: {MINING_INTERVAL} seconds")
    print("Waiting for peers to synchronize blockchain...")

    # Give the node time to connect to peers and synchronize blockchain
    time.sleep(5) # Give time for initial synchronization

    print("\nStarting mining process...")

    try:
        while True:
            # Ensure the chain is up-to-date before mining
            node.sync_blockchain_on_startup() # Request the latest chain from peers

            # Check if supply limit has been reached
            if blockchain.get_current_block_height() >= ArthaBlockchain.MAX_BLOCKS:
                print("ArthaChain supply limit reached. Mining stopped.")
                break

            last_block = blockchain.last_block
            print(f"\nLast block: #{last_block['index']} (Hash: {node.blockchain.hash_block(last_block)[:10]}...)")
            print(f"Pending transactions: {len(blockchain.pending_transactions)}")

            # Simulate simple proof-of-work/elapsed-time
            # Just wait for 1 minute after the last block.
            time_since_last_block = time.time() - last_block['timestamp']
            if time_since_last_block < MINING_INTERVAL:
                wait_time = MINING_INTERVAL - time_since_last_block
                print(f"Waiting {int(wait_time)} seconds before attempting to mine next block...")
                time.sleep(wait_time)
            
            # Attempt to mine a new block
            proof = int(time.time() * 1000) # Simple proof (milliseconds timestamp)
            previous_hash = blockchain.hash_block(last_block)
            
            # Create the new block
            new_block = blockchain.new_block(proof, previous_hash, miner_address)
            
            if new_block:
                print(f"Block #{new_block['index']} successfully mined!")
                # Broadcast the new block to the network
                node.broadcast_message('NEW_BLOCK', {'block': new_block})
                node.last_block_broadcast_time = time.time() # Update broadcast time
            else:
                print("Failed to mine a new block (perhaps supply limit reached or other issue).")

            time.sleep(1) # Small pause before next iteration

    except KeyboardInterrupt:
        print("\nMiner stopped by user.")
    finally:
        node.stop()

if __name__ == '__main__':
    # Allow user to specify port from command line arguments
    if len(sys.argv) > 1:
        try:
            MINER_PORT = int(sys.argv[1])
            if not (1024 <= MINER_PORT <= 65535):
                raise ValueError("Port must be between 1024 and 65535.")
        except ValueError as e:
            print(f"Port error: {e}. Using default port {MINER_PORT}.")
    
    run_miner()

