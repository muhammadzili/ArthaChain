# artha_miner.py

import time
import hashlib
import logging
import os
import sys
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
from artha_node import ArthaNode
import threading

# Miner Node Configuration
MINER_HOST = '0.0.0.0'
MINER_PORT = 5001

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
    console_handler.setLevel(logging.INFO)
    formatter_console = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(formatter_console)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)
    formatter_file = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter_file)
    root_logger.addHandler(file_handler)

    logging.info(f"Logging configured. Console: INFO+, File ('{log_file_path}'): DEBUG+")


def proof_of_work(last_block, blockchain_instance, node_instance):
    """
    Simple Proof of Work algorithm:
    - Find a number 'nonce' such that hashing (last_block_hash + nonce) meets the difficulty target.
    """
    last_block_hash = blockchain_instance.hash_block(last_block)
    difficulty = blockchain_instance.get_current_difficulty()
    nonce = 0
    start_time = time.time()
    logging.info(f"Starting Proof of Work with difficulty: {hex(difficulty)}")

    while not blockchain_instance.is_valid_proof(last_block_hash, nonce, difficulty):
        nonce += 1
        
        if nonce % 100000 == 0:
            node_instance.sync_blockchain_from_known_peers()
            
            if blockchain_instance.last_block['index'] != last_block['index']:
                logging.info("New block received from network while mining. Stopping current PoW and restarting search.")
                return None

            logging.debug(f"  Miner working... tried {nonce} nonces. Time elapsed: {time.time() - start_time:.2f}s")
            
    end_time = time.time()
    logging.info(f"Proof of Work found: {nonce} (took {end_time - start_time:.2f} seconds)")
    return nonce


def run_miner():
    """
    Main function to run the ArthaChain miner.
    """
    setup_logging("artha_miner")

    wallet = ArthaWallet()
    miner_address = wallet.get_public_address()
    blockchain = ArthaBlockchain()
    node = ArthaNode(MINER_HOST, MINER_PORT, blockchain, is_miner=True)
    node.start()

    logging.info("\n" + "="*40)
    logging.info("      ARTHACHAIN MINER STARTED")
    logging.info("="*40)
    logging.info(f"Miner Address: {miner_address}")
    logging.info(f"Miner Node Running at: {MINER_HOST}:{MINER_PORT}")
    logging.info(f"Difficulty Adjustment Interval: {blockchain.DIFFICULTY_ADJUSTMENT_INTERVAL} blocks")
    logging.info(f"Target Block Time: {blockchain.TARGET_BLOCK_TIME_SECONDS} seconds")
    logging.info("Waiting for peers to synchronize blockchain...")

    time.sleep(10)

    logging.info("\nStarting Proof of Work mining process...")

    try:
        while True:
            last_block = blockchain.last_block
            
            if last_block is None:
                logging.warning("Blockchain is empty. Waiting for genesis block to be created or synced.")
                time.sleep(5)
                continue

            logging.info(f"\nLast block: #{last_block['index']} (Hash: {node.blockchain.hash_block(last_block)[:10]}...)")
            logging.info(f"Current Difficulty Target: {hex(blockchain.get_current_difficulty())}")
            logging.info(f"Pending transactions: {len(blockchain.pending_transactions)}")

            nonce = proof_of_work(last_block, blockchain, node) 
            
            if nonce is None:
                continue 

            node.sync_blockchain_from_known_peers()
            if blockchain.last_block['index'] != last_block['index']:
                logging.info("Blockchain updated by another peer while PoW was found. Discarding our found PoW and restarting mining.")
                continue

            previous_hash = blockchain.hash_block(last_block)
            
            new_block = blockchain.new_block(nonce, previous_hash, miner_address)
            
            if new_block:
                logging.info(f"Block #{new_block['index']} successfully mined and added!")
                node.broadcast_message('NEW_BLOCK', {'block': new_block})
                node.last_block_broadcast_time = time.time()
            else:
                logging.warning("Failed to add new block (perhaps supply limit reached or chain inconsistency).")

            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("\nMiner stopped by user.")
    finally:
        node.stop()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        try:
            MINER_PORT = int(sys.argv[1])
            if not (1024 <= MINER_PORT <= 65535):
                raise ValueError("Port must be between 1024 and 65535.")
        except ValueError as e:
            logging.error(f"Port error: {e}. Using default port {MINER_PORT}.")
    
    run_miner()
