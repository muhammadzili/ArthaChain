# artha_miner.py

import time
import hashlib # Make sure hashlib is imported for PoW mining
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
from artha_node import ArthaNode
import threading
import sys

# Miner Node Configuration
MINER_HOST = '0.0.0.0' # Listen on all interfaces for external connections
MINER_PORT = 5001 # Default port for the miner

def proof_of_work(last_block, blockchain_instance):
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
        # Add a small delay for demo purposes to not burn CPU too fast on easy difficulties
        # Or remove this if you want it to run as fast as possible.
        # if nonce % 100000 == 0: # Check every X nonces
        #     time.sleep(0.001) # Small pause

        # Add a check to stop if a new block is received from the network
        # This prevents wasting work if someone else found a block.
        # This requires communication between mining loop and network listener.
        # For simplicity in this demo, we'll let it finish or rely on sync.
        
        # If mining takes too long, give feedback
        if nonce % 1000000 == 0:
            print(f"  Miner working... tried {nonce} nonces. Time elapsed: {time.time() - start_time:.2f}s")
            
        # Very important: check if chain has been updated by other nodes
        # If blockchain instance's last block has changed, we should stop current PoW
        if blockchain_instance.last_block['index'] != last_block['index']:
            print("New block received from network while mining. Stopping current PoW.")
            return None # Indicate that mining should stop and restart

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
    node.start()

    print("\n" + "="*40)
    print("      ARTHACHAIN MINER STARTED")
    print("="*40)
    print(f"Miner Address: {miner_address}")
    print(f"Miner Node Running at: {MINER_HOST}:{MINER_PORT}")
    print(f"Difficulty Adjustment Interval: {blockchain.DIFFICULTY_ADJUSTMENT_INTERVAL} blocks")
    print(f"Target Block Time: {blockchain.TARGET_BLOCK_TIME_SECONDS} seconds")
    print("Waiting for peers to synchronize blockchain...")

    # Give the node time to connect to peers and synchronize blockchain
    time.sleep(5) # Give time for initial synchronization

    print("\nStarting Proof of Work mining process...")

    try:
        while True:
            # Ensure the chain is up-to-date before starting new PoW attempt
            node.sync_blockchain_on_startup() 

            # Check if supply limit has been reached
            if blockchain.get_current_block_height() >= ArthaBlockchain.MAX_BLOCKS:
                print("ArthaChain supply limit reached. Mining stopped.")
                break

            last_block = blockchain.last_block
            print(f"\nLast block: #{last_block['index']} (Hash: {node.blockchain.hash_block(last_block)[:10]}...)")
            print(f"Current Difficulty Target: {hex(blockchain.get_current_difficulty())}")
            print(f"Pending transactions: {len(blockchain.pending_transactions)}")

            # --- Perform Proof of Work ---
            nonce = proof_of_work(last_block, blockchain)
            
            # If nonce is None, it means a new block was found by someone else
            # while we were mining. So, we restart the mining loop.
            if nonce is None:
                continue 

            previous_hash = blockchain.hash_block(last_block)
            
            # Create block only if previous_hash still matches the current last block's hash
            # This is important to avoid adding blocks to an outdated chain if another block was received
            node.sync_blockchain_on_startup() # Resync again just before adding
            if blockchain.last_block['index'] != last_block['index']:
                print("Blockchain updated while waiting for block creation. Discarding found PoW.")
                continue # Restart mining loop

            # Create the new block
            new_block = blockchain.new_block(nonce, previous_hash, miner_address)
            
            if new_block:
                print(f"Block #{new_block['index']} successfully mined and added!")
                # Siarkan blok baru ke jaringan
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

