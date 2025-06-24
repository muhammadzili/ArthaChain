# --- File: artha_blockchain.py (Tidak ada perubahan signifikan, kode Anda sudah solid) ---
# artha_blockchain.py

import time
import hashlib
from artha_utils import hash_data, json_serialize, load_json_file, save_json_file
from artha_wallet import ArthaWallet
import logging # Import logging module here as well

logger = logging.getLogger(__name__) # Get logger for this module

class ArthaBlockchain:
    TOTAL_SUPPLY = 30_000_000
    BLOCK_REWARD = 50
    MAX_BLOCKS = TOTAL_SUPPLY // BLOCK_REWARD

    # --- New PoW and Difficulty Adjustment Constants ---
    # Target 1 block every 3 seconds
    TARGET_BLOCK_TIME_SECONDS = 3
    DIFFICULTY_ADJUSTMENT_INTERVAL = 10 # Adjust difficulty every 10 blocks
    MAX_DIFFICULTY = 2**256 - 1

    def __init__(self, blockchain_file='blockchain.json'):
        self.blockchain_file = blockchain_file
        self.chain = []
        self.pending_transactions = []
        self.known_pending_tx_hashes = set()
        self._load_or_create_chain()

    def _load_or_create_chain(self):
        loaded_chain = load_json_file(self.blockchain_file)
        if loaded_chain:
            self.chain = loaded_chain
            logger.info(f"Blockchain loaded from '{self.blockchain_file}'. Total blocks: {len(self.chain)}")
            self.pending_transactions = []
            self.known_pending_tx_hashes.clear()
        else:
            logger.info("Blockchain file not found. Creating genesis block...")
            genesis_difficulty = 200000 
            self.create_genesis_block(genesis_difficulty)
            self.save_chain()

    def create_genesis_block(self, initial_difficulty):
        genesis_block = {
            'index': 0,
            'timestamp': time.time(),
            'transactions': [],
            'nonce': 0,
            'previous_hash': '0',
            'miner_address': 'genesis_address',
            'difficulty': initial_difficulty
        }
        self.chain.append(genesis_block)
        logger.info("Genesis block created!")

    def new_block(self, nonce, previous_hash, miner_address):
        if self.get_current_block_height() >= self.MAX_BLOCKS:
            logger.warning("ArthaChain supply limit reached. No new blocks can be mined.")
            return None

        current_difficulty = self.get_current_difficulty()

        coinbase_tx = {
            'sender': '0',
            'recipient': miner_address,
            'amount': self.BLOCK_REWARD,
            'timestamp': time.time(),
            'signature': 'coinbase_signature'
        }
        
        transactions_for_block = []
        
        temp_current_balances = self._get_balances_at_block_height(len(self.chain))
        
        sorted_pending = sorted(self.pending_transactions, key=lambda tx: tx['timestamp'])

        for tx in sorted_pending:
            tx_id = self._calculate_transaction_id(tx)

            tx_data_for_verification = {
                'sender': tx['sender'],
                'recipient': tx['recipient'],
                'amount': tx['amount']
            }

            if tx['sender'] != '0' and not ArthaWallet.verify_signature(tx_data_for_verification, tx['public_key_str'], tx['signature']):
                logger.warning(f"Pending transaction {tx_id[:10]}... has invalid signature during block creation. Discarding.")
                continue
            
            sender_balance_in_block = temp_current_balances.get(tx['sender'], 0)
            if tx['sender'] != '0' and sender_balance_in_block < tx['amount']:
                logger.warning(f"Pending transaction {tx_id[:10]}... has insufficient sender balance ({sender_balance_in_block} ARTH). Discarding.")
                continue
            
            if tx_id not in [self._calculate_transaction_id(t) for t in transactions_for_block]:
                transactions_for_block.append(tx)
                temp_current_balances[tx['sender']] = sender_balance_in_block - tx['amount']
                temp_current_balances[tx['recipient']] = temp_current_balances.get(tx['recipient'], 0) + tx['amount']
            else:
                logger.debug(f"Duplicate pending transaction {tx_id[:10]}... found while building block. Skipping.")
        
        transactions_for_block.append(coinbase_tx)

        included_tx_ids = {self._calculate_transaction_id(tx) for tx in transactions_for_block if 'signature' in tx and tx['signature'] != 'coinbase_signature'}

        self.pending_transactions = [
            tx for tx in self.pending_transactions
            if self._calculate_transaction_id(tx) not in included_tx_ids
        ]

        self.known_pending_tx_hashes = {self._calculate_transaction_id(tx) for tx in self.pending_transactions}

        block = {
            'index': len(self.chain),
            'timestamp': time.time(),
            'transactions': transactions_for_block,
            'nonce': nonce,
            'previous_hash': previous_hash or self.hash_block(self.chain[-1]),
            'miner_address': miner_address,
            'difficulty': current_difficulty
        }
        self.chain.append(block)
        logger.info(f"New block #{block['index']} mined by {miner_address} with difficulty {hex(current_difficulty)}!")
        self.save_chain()
        return block

    def _calculate_transaction_id(self, tx):
        unique_data = {
            'sender': tx.get('sender'),
            'recipient': tx.get('recipient'),
            'amount': tx.get('amount'),
            'timestamp': tx.get('timestamp'),
            'signature': tx.get('signature')
        }
        return hash_data(json_serialize(unique_data))

    def add_transaction(self, sender, recipient, amount, signature, public_key_str, timestamp=None):
        if sender == '0':
            logger.warning("Attempted to add coinbase transaction via add_transaction. This should be handled internally by new_block.")
            return None

        if not sender or not recipient or amount <= 0:
            logger.warning("Invalid transaction: Sender, recipient, or amount is incorrect.")
            return None

        tx_data_for_verification = { 'sender': sender, 'recipient': recipient, 'amount': amount }
        current_tx_timestamp = timestamp if timestamp is not None else time.time()
        
        temp_transaction_for_hash = {
            'sender': sender, 'recipient': recipient, 'amount': amount,
            'timestamp': current_tx_timestamp, 'signature': signature,
            'public_key_str': public_key_str
        }
        tx_id = self._calculate_transaction_id(temp_transaction_for_hash)

        if tx_id in self.known_pending_tx_hashes:
            logger.debug(f"Transaction {tx_id[:10]}... already in pending queue. Ignoring duplicate.")
            return None

        if not ArthaWallet.verify_signature(tx_data_for_verification, public_key_str, signature):
            logger.warning("Invalid transaction: Signature does not match.")
            return None

        if self.get_balance(sender) < amount:
            logger.warning(f"Invalid transaction: Sender's balance ({self.get_balance(sender)} ARTH) is insufficient for {amount} ARTH.")
            return None

        transaction = {
            'sender': sender, 'recipient': recipient, 'amount': amount,
            'timestamp': current_tx_timestamp, 'signature': signature,
            'public_key_str': public_key_str
        }
        self.pending_transactions.append(transaction)
        self.known_pending_tx_hashes.add(tx_id)
        logger.info(f"Transaction {tx_id[:10]}... from {sender[:8]}... to {recipient[:8]}... for {amount} ARTH added to queue.")
        return transaction

    @property
    def last_block(self):
        if not self.chain:
            logger.error("Attempted to get last_block from an empty chain.")
            return None
        return self.chain[-1]

    def hash_block(self, block):
        block_copy = dict(block)
        return hash_data(json_serialize(block_copy))

    def get_current_block_height(self):
        return len(self.chain) - 1

    def _get_balances_at_block_height(self, height):
        balances = {}
        for i in range(min(height, len(self.chain))):
            block = self.chain[i]
            for tx in block['transactions']:
                balances.setdefault(tx['recipient'], 0)
                balances.setdefault(tx['sender'], 0)
                if tx['sender'] == '0':
                    balances[tx['recipient']] += tx['amount']
                else:
                    balances[tx['sender']] -= tx['amount']
                    balances[tx['recipient']] += tx['amount']
        return balances

    def get_balance(self, address):
        balance = self._get_balances_at_block_height(len(self.chain)).get(address, 0)
        for tx in self.pending_transactions:
            if tx['recipient'] == address:
                balance += tx['amount']
            if tx['sender'] == address:
                balance -= tx['amount']
        return balance

    def calculate_difficulty(self, last_block, chain):
        if last_block['index'] == 0: return last_block['difficulty']
        if last_block['index'] % self.DIFFICULTY_ADJUSTMENT_INTERVAL != 0: return last_block['difficulty']
        if last_block['index'] < self.DIFFICULTY_ADJUSTMENT_INTERVAL: return last_block['difficulty']

        first_block_in_interval = chain[max(0, last_block['index'] - self.DIFFICULTY_ADJUSTMENT_INTERVAL)]
        actual_time_taken = last_block['timestamp'] - first_block_in_interval['timestamp']
        expected_time = self.DIFFICULTY_ADJUSTMENT_INTERVAL * self.TARGET_BLOCK_TIME_SECONDS
        new_difficulty = last_block['difficulty']

        if actual_time_taken < expected_time / 2: new_difficulty //= 2
        elif actual_time_taken > expected_time * 2: new_difficulty *= 2
        elif actual_time_taken < expected_time: new_difficulty = int(new_difficulty * 0.9)
        elif actual_time_taken > expected_time: new_difficulty = int(new_difficulty * 1.1)
        
        new_difficulty = max(1, min(new_difficulty, self.MAX_DIFFICULTY))
        logger.info(f"--- Difficulty Adjusted at block #{last_block['index']}: Old {hex(last_block['difficulty'])}, New {hex(new_difficulty)} ---")
        return new_difficulty

    def get_current_difficulty(self):
        if not self.chain: return self.MAX_DIFFICULTY // (1000 * 1000)
        last_block = self.last_block
        if (last_block['index'] != 0) and (last_block['index'] % self.DIFFICULTY_ADJUSTMENT_INTERVAL == 0):
            return self.calculate_difficulty(last_block, self.chain)
        else:
            return last_block['difficulty']

    def is_valid_proof(self, last_block_hash, nonce, difficulty):
        guess = f'{last_block_hash}{nonce}'.encode('utf-8')
        guess_hash = hashlib.sha256(guess).hexdigest()
        target = self.MAX_DIFFICULTY // difficulty
        return int(guess_hash, 16) <= target

    def is_chain_valid(self, chain):
        if not chain: return False
        current_balance = {}
        for i in range(len(chain)):
            block = chain[i]
            for tx in block['transactions']:
                current_balance.setdefault(tx['recipient'], 0)
                current_balance.setdefault(tx['sender'], 0)
            if block['index'] > 0:
                last_block_of_validation_pair = chain[i-1]
                if block['previous_hash'] != self.hash_block(last_block_of_validation_pair):
                    logger.error(f"Validation FAILED: Block #{block['index']} invalid previous_hash.")
                    return False
                if not self.is_valid_proof(block['previous_hash'], block['nonce'], block['difficulty']):
                    logger.error(f"Validation FAILED: Block #{block['index']} invalid PoW.")
                    return False
            coinbase_tx_found = False
            for tx in block['transactions']:
                if tx['sender'] == '0':
                    if coinbase_tx_found: return False # More than one coinbase
                    if tx['amount'] != self.BLOCK_REWARD: return False # Incorrect reward
                    coinbase_tx_found = True
                    current_balance[tx['recipient']] = current_balance.get(tx['recipient'], 0) + tx['amount']
                    continue
                
                tx_data_for_verification = { 'sender': tx['sender'], 'recipient': tx['recipient'], 'amount': tx['amount'] }
                if 'public_key_str' not in tx or not ArthaWallet.verify_signature(tx_data_for_verification, tx['public_key_str'], tx['signature']):
                    logger.error(f"Validation FAILED: Block #{block['index']}, tx from {tx['sender'][:8]}... invalid signature.")
                    return False
                
                sender_balance = current_balance.get(tx['sender'], 0)
                if sender_balance < tx['amount']:
                    logger.error(f"Validation FAILED: Block #{block['index']}, sender {tx['sender'][:8]}... insufficient balance.")
                    return False
                current_balance[tx['sender']] -= tx['amount']
                current_balance[tx['recipient']] += tx['amount']
            
            if not coinbase_tx_found and block['index'] <= self.MAX_BLOCKS and block['index'] != 0:
                logger.error(f"Validation FAILED: Block #{block['index']} no coinbase tx.")
                return False
        logger.info("Blockchain chain is valid.")
        return True

    def replace_chain(self, new_chain):
        if len(new_chain) > len(self.chain) and self.is_chain_valid(new_chain):
            logger.info("Chain replaced with a longer and valid chain.")
            self.chain = new_chain
            self.pending_transactions = []
            self.known_pending_tx_hashes.clear()
            self.save_chain()
            return True
        return False

    def save_chain(self):
        save_json_file(self.blockchain_file, self.chain)
