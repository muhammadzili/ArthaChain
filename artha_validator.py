# artha_validator.py

import time
import logging
import os
import sys
import getpass
import threading
import json # --- PERBAIKAN: Menambahkan import json ---

from artha_blockchain_pos import ArthaBlockchainPoS
from artha_wallet import ArthaWallet
from artha_node_pos import ArthaNodePoS
from artha_utils import json_serialize # Impor json_serialize untuk digunakan

logger = logging.getLogger(__name__)

VALIDATOR_HOST = '0.0.0.0'
VALIDATOR_PORT = 5001

def setup_logging(port):
    log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"artha_validator_{port}.log")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if root_logger.handlers:
        for handler in root_logger.handlers[:]: root_logger.removeHandler(handler)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(log_file_path, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

def block_production_loop(blockchain, node, wallet):
    my_address = wallet.get_public_address()
    logger.info(f"Validator loop started for address: {my_address[:10]}...")
    
    while True:
        try:
            time.sleep(blockchain.BLOCK_TIME)
            next_validator = blockchain.get_next_validator()
            
            if next_validator == my_address:
                logger.info("It's our turn to create a block!")
                new_block = blockchain.new_block(wallet)
                
                if new_block:
                    blockchain.add_block(new_block)
                    # Siarkan blok yang sudah di-serialize dengan benar
                    block_for_broadcast = json.loads(json_serialize(new_block).decode('utf-8'))
                    node.broadcast_message('NEW_BLOCK', {'block': block_for_broadcast})
                    logger.info(f"Successfully created and broadcasted block #{new_block['index']}")
                else:
                    logger.warning("Failed to create a new block.")
            else:
                logger.debug(f"Not our turn. Next validator: {next_validator[:10]}...")

        except Exception as e:
            logger.error(f"An error occurred in the validator loop: {e}", exc_info=True)
            time.sleep(blockchain.BLOCK_TIME)

def run_validator():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else VALIDATOR_PORT
    setup_logging(port)
    
    try:
        password = getpass.getpass("Masukkan password dompet Validator: ")
        wallet = ArthaWallet(wallet_file=f"validator_{port}.dat", password=password)
    except Exception as e:
        logging.error(f"Gagal memuat dompet: {e}")
        return
        
    my_address = wallet.get_public_address()
    blockchain = ArthaBlockchainPoS()
    
    if my_address not in blockchain.validators:
        logger.error("FATAL: This address is not in the hardcoded validator list.")
        logger.error("Please add your address to `artha_blockchain_pos.py` to run a validator.")
        print(f"Your address is: {my_address}")
        return

    node = ArthaNodePoS(VALIDATOR_HOST, port, blockchain)
    node.start()
    
    logger.info(f"\n>> VALIDATOR ARTHACHAIN (PoS) DIMULAI <<\nAlamat: {my_address}\nNode berjalan di: {VALIDATOR_HOST}:{port}")
    
    producer_thread = threading.Thread(
        target=block_production_loop,
        args=(blockchain, node, wallet),
        daemon=True
    )
    producer_thread.start()
    
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("\nMenutup validator...")
    finally:
        node.stop()

if __name__ == '__main__':
    run_validator()
