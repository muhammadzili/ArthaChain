# artha_miner.py

import time
import hashlib
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
from artha_node import ArthaNode # Make sure this is the updated artha_node.py
import threading
import sys

# Miner Node Configuration
MINER_HOST = '0.0.0.0' # Listen on all interfaces for external connections
MINER_PORT = 5001 # Default port for the miner

def proof_of_work(last_block, blockchain_instance, node_instance): # Added node_instance to pass through
    """
    Simple Proof of Work algorithm:
    - Find a number 'nonce' such that hashing (last_block_hash + nonce) meets the difficulty target.
    """
    last_block_hash = blockchain_instance.hash_block(last_block)
    difficulty = blockchain_instance.get_current_difficulty()
    nonce = 0
    start_time = time.time()
    print(f"Starting Proof of Work with difficulty: {hex(difficulty)}")

    while not blockchain_instance.is_valid_proof(last_block_hash, nonce, difficulty):
        nonce += 1
        
        # Check periodically if a new block has arrived from the network
        # This prevents wasting work if someone else found a block.
        # Check every 100,000 nonces to avoid too much overhead.
        if nonce % 100000 == 0:
            # Trigger a quick sync to see if the chain has changed
            node_instance.sync_blockchain_from_known_peers() # Use the correct method name!
            
            # If the blockchain's last block has changed, our current PoW is outdated
            if blockchain_instance.last_block['index'] != last_block['index']:
                print("New block received from network while mining. Stopping current PoW and restarting search.")
                return None # Indicate that mining should stop and restart from fresh block

            print(f"  Miner working... tried {nonce} nonces. Time elapsed: {time.time() - start_time:.2f}s")
            
    end_time = time.time()
    print(f"Proof of Work found: {nonce} (took {end_time - start_time:.2f} seconds)")
    return nonce


def run_miner():
    """
    Main function to run the ArthaChain miner.
    """
    wallet = ArthaWallet()
    miner_address = wallet.get_public_address()
    blockchain = ArthaBlockchain()
    node = ArthaNode(MINER_HOST, MINER_PORT, blockchain, is_miner=True)
    node.start() # This call now handles initial bootstrap and sync

    print("\n" + "="*40)
    print("      ARTHACHAIN MINER STARTED")
    print("="*40)
    print(f"Miner Address: {miner_address}")
    print(f"Miner Node Running at: {MINER_HOST}:{MINER_PORT}")
    print(f"Difficulty Adjustment Interval: {blockchain.DIFFICULTY_ADJUSTMENT_INTERVAL} blocks")
    print(f"Target Block Time: {blockchain.TARGET_BLOCK_TIME_SECONDS} seconds")
    print("Waiting for peers to synchronize blockchain...")

    # Give the node time to connect to bootstrap peers and synchronize blockchain
    # The node.start() method already kicks off connect_and_sync_initial.
    # We'll wait a bit here to ensure some initial sync happens before mining starts.
    time.sleep(10) # Give more time for initial sync to happen

    print("\nStarting Proof of Work mining process...")

    try:
        while True:
            # We don't need to call sync_blockchain_from_known_peers() here
            # at the beginning of *every* loop iteration, as the node's
            # internal threads handle passive sync and the PoW loop
            # now calls it periodically itself.
            
            last_block = blockchain.last_block
            print(f"\nLast block: #{last_block['index']} (Hash: {node.blockchain.hash_block(last_block)[:10]}...)")
            print(f"Current Difficulty Target: {hex(blockchain.get_current_difficulty())}")
            print(f"Pending transactions: {len(blockchain.pending_transactions)}")

            # --- Perform Proof of Work ---
            # Pass the node instance to proof_of_work so it can trigger syncs
            nonce = proof_of_work(last_block, blockchain, node) 
            
            # If nonce is None, it means a new block was found by someone else
            # while we were mining. So, we restart the mining loop immediately.
            if nonce is None:
                continue 

            # After finding PoW, ensure our chain is still the longest before creating a block
            # Another node might have mined a block while we were calculating our nonce.
            # This is a critical check for preventing stale blocks.
            node.sync_blockchain_from_known_peers() # Resync again just before adding
            if blockchain.last_block['index'] != last_block['index']:
                print("Blockchain updated by another peer while PoW was found. Discarding our found PoW and restarting mining.")
                continue # Restart mining loop

            previous_hash = blockchain.hash_block(last_block)
            
            # Create the new block
            new_block = blockchain.new_block(nonce, previous_hash, miner_address)
            
            if new_block:
                print(f"Block #{new_block['index']} successfully mined and added!")
                # Broadcast the new block to the network
                node.broadcast_message('NEW_BLOCK', {'block': new_block})
                node.last_block_broadcast_time = time.time() # Update broadcast time
            else:
                print("Failed to add new block (perhaps supply limit reached or chain inconsistency).")

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
