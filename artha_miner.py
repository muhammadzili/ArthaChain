# artha_miner.py

import time
import logging
import os
import sys
import getpass
import threading
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
from artha_node import ArthaNode

MINER_HOST = '0.0.0.0'
MINER_PORT = 5001

def setup_logging(port):
    log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"artha_miner_{port}.log")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if root_logger.handlers: [h.close() for h in root_logger.handlers[:]]; root_logger.handlers = []
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler(sys.stdout); console_handler.setLevel(logging.INFO); console_handler.setFormatter(formatter); root_logger.addHandler(console_handler)
    file_handler = logging.FileHandler(log_file_path, mode='w'); file_handler.setLevel(logging.DEBUG); file_handler.setFormatter(formatter); root_logger.addHandler(file_handler)

def mine_a_block(blockchain, miner_address):
    last_block = blockchain.last_block
    if not last_block: return None
    previous_hash = blockchain.hash_block(last_block)
    nonce = 0
    while not blockchain.is_valid_proof(previous_hash, nonce, blockchain.get_current_difficulty()):
        nonce += 1
        if blockchain.last_block.get('index') > last_block.get('index'):
            logging.info("Mining interrupted by new block from network.")
            return None
    if blockchain.last_block and blockchain.hash_block(blockchain.last_block) != previous_hash:
        logging.warning("Mined a block for an orphaned chain. Discarding.")
        return None
    return blockchain.new_block(nonce, previous_hash, miner_address)

def mining_worker(blockchain, node, miner_address, new_tx_event):
    while True:
        triggered = new_tx_event.wait(timeout=blockchain.TARGET_BLOCK_TIME_SECONDS)
        if triggered: logging.info("New transaction detected! Triggering mining...")
        else: logging.info("Timeout reached. Mining a block...")
        
        new_block = mine_a_block(blockchain, miner_address)
        if new_block:
            if node.handle_own_new_block(new_block):
                 logging.info(f"Successfully mined and broadcasting block #{new_block['index']}")
                 node.broadcast_message('NEW_BLOCK', {'block': new_block})
        
        if new_tx_event.is_set(): new_tx_event.clear()
        time.sleep(1)

def run_miner():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else MINER_PORT
    setup_logging(port)
    try:
        password = getpass.getpass("Masukkan password dompet Miner: ")
        wallet = ArthaWallet(password=password)
    except Exception as e:
        print(f"Gagal memuat dompet: {e}"); return
        
    miner_address = wallet.get_public_address()
    blockchain = ArthaBlockchain()
    new_tx_event = threading.Event()
    node = ArthaNode(MINER_HOST, port, blockchain, is_miner=True, new_tx_event=new_tx_event)
    node.start()
    
    logging.info(f"\nPENAMBANG HYBRID DIMULAI\nAlamat: {miner_address}\nNode di: {MINER_HOST}:{port}")
    logging.info(f"Menambang setiap ada transaksi ATAU setiap ~{blockchain.TARGET_BLOCK_TIME_SECONDS} detik.")
    
    miner_thread = threading.Thread(target=mining_worker, args=(blockchain, node, miner_address, new_tx_event), daemon=True)
    miner_thread.start()
    
    try:
        while True: time.sleep(60)
    except KeyboardInterrupt:
        logging.info("\nPenambang dihentikan.")
    finally: node.stop()

if __name__ == '__main__':
    run_miner()
