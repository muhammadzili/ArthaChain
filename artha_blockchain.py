# artha_blockchain.py

import time
import hashlib
from decimal import Decimal, getcontext
from artha_utils import hash_data, json_serialize, load_json_file, save_json_file
from artha_wallet import ArthaWallet
import logging

getcontext().prec = 28
logger = logging.getLogger(__name__)

class ArthaBlockchain:
    TOTAL_SUPPLY = Decimal('30000000')
    BLOCK_REWARD = Decimal('50')
    MAX_BLOCKS = int(TOTAL_SUPPLY // BLOCK_REWARD)
    TARGET_BLOCK_TIME_SECONDS = 60
    DIFFICULTY_ADJUSTMENT_INTERVAL = 10

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
            logger.info(f"Blockchain loaded. Height: {len(self.chain) - 1}")
        else:
            if loaded_chain:
                logger.warning("Loaded blockchain is invalid. Creating new one.")
            else:
                logger.info("Blockchain file not found. Creating genesis block.")
            self.create_genesis_block(200000)

    def create_genesis_block(self, initial_difficulty):
        self.chain = []
        genesis_block = {
            'index': 0, 'timestamp': time.time(), 'transactions': [],
            'nonce': 0, 'previous_hash': '0', 'miner_address': 'genesis_address',
            'difficulty': initial_difficulty
        }
        self.chain.append(genesis_block)
        self.save_chain()
        logger.info("Genesis block created.")

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
        included_tx_ids = set()
        
        temp_balances[miner_address] = temp_balances.get(miner_address, Decimal('0')) + self.BLOCK_REWARD
        
        for tx in sorted(self.pending_transactions, key=lambda t: t['timestamp']):
            sender, recipient, amount = tx['sender'], tx['recipient'], Decimal(tx['amount'])
            sender_balance = temp_balances.get(sender, Decimal('0'))
            
            tx_data = {'sender': sender, 'recipient': recipient, 'amount': tx['amount']}
            if sender_balance >= amount and ArthaWallet.verify_signature(tx_data, tx['public_key_str'], tx['signature']):
                transactions_for_block.append(tx)
                included_tx_ids.add(self._calculate_transaction_id(tx))
                temp_balances[sender] -= amount
                temp_balances[recipient] = temp_balances.get(recipient, Decimal('0')) + amount
        
        return {
            'index': len(self.chain), 'timestamp': time.time(), 'transactions': transactions_for_block,
            'nonce': nonce, 'previous_hash': previous_hash, 'miner_address': miner_address,
            'difficulty': self.get_current_difficulty()
        }

    def _calculate_transaction_id(self, tx):
        keys = ['sender', 'recipient', 'amount', 'timestamp', 'signature']
        unique_data = {k: tx.get(k) for k in keys}
        return hash_data(json_serialize(unique_data))

    def add_transaction(self, sender, recipient, amount, signature, public_key_str, timestamp=None):
        try:
            amount_decimal = Decimal(amount)
        except: return None
        
        if self.get_balance(sender) < amount_decimal: return None
        
        canonical_amount_str = "{:.8f}".format(amount_decimal)
        tx_data = {'sender': sender, 'recipient': recipient, 'amount': canonical_amount_str}
        
        if not ArthaWallet.verify_signature(tx_data, public_key_str, signature): return None
        
        transaction = {'sender': sender, 'recipient': recipient, 'amount': canonical_amount_str, 
                       'timestamp': timestamp or time.time(), 'signature': signature, 'public_key_str': public_key_str}
        
        tx_id = self._calculate_transaction_id(transaction)
        if tx_id in self.known_pending_tx_hashes: return None
        
        transaction['transaction_id'] = tx_id
        self.pending_transactions.append(transaction)
        self.known_pending_tx_hashes.add(tx_id)
        return transaction

    @property
    def last_block(self):
        return self.chain[-1] if self.chain else None

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
        if not self.chain or self.last_block['index'] < self.DIFFICULTY_ADJUSTMENT_INTERVAL: 
            return 200000
        last_block = self.last_block
        if (last_block['index'] % self.DIFFICULTY_ADJUSTMENT_INTERVAL == 0):
            return self.calculate_difficulty(last_block)
        return last_block['difficulty']

    def calculate_difficulty(self, last_block):
        first_block = self.chain[-(self.DIFFICULTY_ADJUSTMENT_INTERVAL)]
        time_taken = last_block['timestamp'] - first_block['timestamp']
        expected_time = self.DIFFICULTY_ADJUSTMENT_INTERVAL * self.TARGET_BLOCK_TIME_SECONDS
        if time_taken <= 0: time_taken = 1
        ratio = max(0.25, min(4.0, expected_time / time_taken))
        return max(1, int(last_block['difficulty'] / ratio))

    def is_valid_proof(self, last_block_hash, nonce, difficulty):
        guess = f'{last_block_hash}{nonce}'.encode('utf-8')
        guess_hash = hashlib.sha256(guess).hexdigest()
        target = (2**256 - 1) // (difficulty if difficulty > 0 else 1)
        return int(guess_hash, 16) <= target

    def is_chain_valid(self, chain_to_validate):
        if not chain_to_validate or chain_to_validate[0]['index'] != 0 or chain_to_validate[0]['previous_hash'] != '0':
             return False
        
        current_balances = {}
        for i, block in enumerate(chain_to_validate):
            if i > 0:
                last_block = chain_to_validate[i-1]
                if block['previous_hash'] != self.hash_block(last_block) or \
                   not self.is_valid_proof(block['previous_hash'], block['nonce'], block['difficulty']):
                    return False

            for tx in block['transactions']:
                amount = Decimal(tx['amount'])
                if tx['sender'] == '0':
                    current_balances.setdefault(tx['recipient'], Decimal('0'))
                    current_balances[tx['recipient']] += amount
                    continue
                
                current_balances.setdefault(tx['sender'], Decimal('0'))
                if current_balances[tx['sender']] < amount: return False
                
                tx_data = {'sender': tx['sender'], 'recipient': tx['recipient'], 'amount': tx['amount']}
                if not ArthaWallet.verify_signature(tx_data, tx['public_key_str'], tx['signature']): return False
                
                current_balances[tx['sender']] -= amount
                current_balances.setdefault(tx['recipient'], Decimal('0'))
                current_balances[tx['recipient']] += amount

        return True

    def replace_chain(self, new_chain):
        if len(new_chain) > len(self.chain) and self.is_chain_valid(new_chain):
            self.chain = new_chain
            all_tx_ids = {self._calculate_transaction_id(tx) for block in self.chain for tx in block['transactions']}
            self.pending_transactions = [tx for tx in self.pending_transactions if self._calculate_transaction_id(tx) not in all_tx_ids]
            self.known_pending_tx_hashes = {self._calculate_transaction_id(tx) for tx in self.pending_transactions}
            self.save_chain()
            logger.info(f"Chain updated to block #{self.last_block['index']}.")
            return True
        return False

    def save_chain(self):
        save_json_file(self.blockchain_file, self.chain)
