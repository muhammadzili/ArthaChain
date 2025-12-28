# artha_blockchain.py (Updated to v2.0)

import time
import hashlib
import logging
from decimal import Decimal, getcontext
from artha_utils import hash_data, json_serialize, load_json_file, save_json_file
from artha_wallet import ArthaWallet

getcontext().prec = 28
logger = logging.getLogger(__name__)

class ArthaBlockchain:
    TOTAL_SUPPLY = Decimal('30000000')
    BLOCK_REWARD = Decimal('50')
    MAX_BLOCKS = int(TOTAL_SUPPLY // BLOCK_REWARD)
    TARGET_BLOCK_TIME_SECONDS = 60
    DIFFICULTY_ADJUSTMENT_INTERVAL = 10
    
    # --- STABILITY v2.0 ---
    MAX_MEMPOOL_SIZE = 500 # Batasi transaksi tertunda untuk stabilitas memori
    TX_EXPIRY_SECONDS = 86400 # Transaksi di mempool hapus otomatis jika tidak ditambang dalam 24 jam

    def __init__(self, blockchain_file='blockchain.json'):
        self.blockchain_file = blockchain_file
        self.chain = []
        self.pending_transactions = []
        self.known_pending_tx_hashes = set()
        self._load_or_create_chain()

    def _load_or_create_chain(self):
        loaded_chain = load_json_file(self.blockchain_file)
        if loaded_chain and self.is_chain_valid(loaded_chain):
            self.chain = loaded_chain
            logger.info(f"Blockchain 2.0 Loaded. Height: {len(self.chain) - 1}")
        else:
            logger.info("Initializing new ArthaChain v2.0...")
            self.create_genesis_block(200000)

    def create_genesis_block(self, initial_difficulty):
        self.chain = []
        genesis_block = {
            'index': 0, 'timestamp': 1700000000.0, 'transactions': [],
            'nonce': 100, 'previous_hash': '0', 'miner_address': 'genesis_node',
            'difficulty': initial_difficulty
        }
        self.chain.append(genesis_block)
        self.save_chain()

    def add_transaction(self, sender, recipient, amount, signature, public_key_str, timestamp=None):
        # 1. Cek Kapasitas Mempool (Feature 2.0)
        if len(self.pending_transactions) >= self.MAX_MEMPOOL_SIZE:
            logger.warning("Mempool full. Dropping transaction.")
            return None

        try:
            amount_decimal = Decimal(amount)
        except: return None
        
        # 2. Validasi Saldo & Struktur
        if amount_decimal <= 0: return None
        if self.get_balance(sender) < amount_decimal: return None
        
        canonical_amount_str = "{:.8f}".format(amount_decimal)
        tx_data = {'sender': sender, 'recipient': recipient, 'amount': canonical_amount_str}
        
        if not ArthaWallet.verify_signature(tx_data, public_key_str, signature): 
            return None
        
        timestamp = timestamp or time.time()
        transaction = {
            'sender': sender, 'recipient': recipient, 'amount': canonical_amount_str, 
            'timestamp': timestamp, 'signature': signature, 'public_key_str': public_key_str
        }
        
        tx_id = self._calculate_transaction_id(transaction)
        if tx_id in self.known_pending_tx_hashes: return None
        
        transaction['transaction_id'] = tx_id
        self.pending_transactions.append(transaction)
        self.known_pending_tx_hashes.add(tx_id)
        
        # 3. Cleanup transaksi lama di mempool secara berkala
        self._prune_mempool()
        
        return transaction

    def _prune_mempool(self):
        """Menghapus transaksi kadaluarsa agar mempool tetap bersih."""
        now = time.time()
        original_count = len(self.pending_transactions)
        self.pending_transactions = [
            tx for tx in self.pending_transactions 
            if (now - tx.get('timestamp', 0)) < self.TX_EXPIRY_SECONDS
        ]
        if len(self.pending_transactions) < original_count:
            self.known_pending_tx_hashes = {self._calculate_transaction_id(tx) for tx in self.pending_transactions}
            logger.info(f"Pruned {original_count - len(self.pending_transactions)} expired transactions.")

    def new_block(self, nonce, previous_hash, miner_address):
        if self.get_current_block_height() >= self.MAX_BLOCKS:
            return None

        canonical_reward = "{:.8f}".format(self.BLOCK_REWARD)
        coinbase_tx = {
            'sender': '0', 'recipient': miner_address, 'amount': canonical_reward,
            'timestamp': time.time(), 'signature': 'coinbase', 'public_key_str': 'coinbase'
        }
        
        temp_balances = self.get_balance_snapshot()
        transactions_for_block = [coinbase_tx]
        temp_balances[miner_address] = temp_balances.get(miner_address, Decimal('0')) + self.BLOCK_REWARD
        
        # Ambil max 50 transaksi per blok untuk stabilitas jaringan
        txs_to_process = sorted(self.pending_transactions, key=lambda t: t['timestamp'])[:50]
        
        for tx in txs_to_process:
            sender, amount = tx['sender'], Decimal(tx['amount'])
            if temp_balances.get(sender, Decimal('0')) >= amount:
                transactions_for_block.append(tx)
                temp_balances[sender] -= amount
                temp_balances[tx['recipient']] = temp_balances.get(tx['recipient'], Decimal('0')) + amount
        
        return {
            'index': len(self.chain), 'timestamp': time.time(), 'transactions': transactions_for_block,
            'nonce': nonce, 'previous_hash': previous_hash, 'miner_address': miner_address,
            'difficulty': self.get_current_difficulty()
        }

    def _calculate_transaction_id(self, tx):
        keys = ['sender', 'recipient', 'amount', 'timestamp', 'signature']
        unique_data = {k: tx.get(k) for k in keys}
        return hash_data(json_serialize(unique_data))

    def hash_block(self, block):
        return hash_data(json_serialize({k: v for k, v in block.items() if k != 'hash'}))

    def get_current_block_height(self):
        return len(self.chain) - 1

    def get_balance_snapshot(self):
        balances = {}
        for block in self.chain:
            for tx in block['transactions']:
                amount = Decimal(tx['amount'])
                if tx['sender'] != '0':
                    balances[tx['sender']] = balances.get(tx['sender'], Decimal('0')) - amount
                balances[tx['recipient']] = balances.get(tx['recipient'], Decimal('0')) + amount
        return balances

    def get_balance(self, address) -> Decimal:
        return self.get_balance_snapshot().get(address, Decimal('0'))

    def get_current_difficulty(self):
        if not self.chain or len(self.chain) <= self.DIFFICULTY_ADJUSTMENT_INTERVAL: 
            return 200000
        last_block = self.chain[-1]
        if (last_block['index'] % self.DIFFICULTY_ADJUSTMENT_INTERVAL == 0):
            return self.calculate_difficulty(last_block)
        return last_block['difficulty']

    def calculate_difficulty(self, last_block):
        first_block = self.chain[-(self.DIFFICULTY_ADJUSTMENT_INTERVAL)]
        time_taken = last_block['timestamp'] - first_block['timestamp']
        expected_time = self.DIFFICULTY_ADJUSTMENT_INTERVAL * self.TARGET_BLOCK_TIME_SECONDS
        ratio = max(0.25, min(4.0, expected_time / (time_taken if time_taken > 0 else 1)))
        return max(1000, int(last_block['difficulty'] / ratio))

    def is_valid_proof(self, last_block_hash, nonce, difficulty):
        guess = f'{last_block_hash}{nonce}'.encode('utf-8')
        guess_hash = hashlib.sha256(guess).hexdigest()
        target = (2**256 - 1) // (difficulty if difficulty > 0 else 1)
        return int(guess_hash, 16) <= target

    def is_chain_valid(self, chain_to_validate):
        if not chain_to_validate or chain_to_validate[0]['index'] != 0: return False
        
        for i in range(1, len(chain_to_validate)):
            block = chain_to_validate[i]
            prev = chain_to_validate[i-1]
            if block['previous_hash'] != self.hash_block(prev): return False
            if not self.is_valid_proof(block['previous_hash'], block['nonce'], block['difficulty']): return False
        return True

    def replace_chain(self, new_chain):
        if len(new_chain) > len(self.chain) and self.is_chain_valid(new_chain):
            self.chain = new_chain
            # Update mempool: hapus tx yang sudah masuk blok
            all_tx_ids = {self._calculate_transaction_id(tx) for b in self.chain for tx in b['transactions']}
            self.pending_transactions = [tx for tx in self.pending_transactions if self._calculate_transaction_id(tx) not in all_tx_ids]
            self.known_pending_tx_hashes = {self._calculate_transaction_id(tx) for tx in self.pending_transactions}
            self.save_chain()
            return True
        return False

    def save_chain(self):
        save_json_file(self.blockchain_file, self.chain)