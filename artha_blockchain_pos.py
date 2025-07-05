# artha_blockchain_pos.py

import time
import hashlib
import logging
import threading
from decimal import Decimal, getcontext, InvalidOperation

from artha_utils import hash_data, json_serialize, load_json_file, save_json_file
from artha_wallet import ArthaWallet

getcontext().prec = 28
logger = logging.getLogger(__name__)

class ArthaBlockchainPoS:
    BLOCK_REWARD = Decimal('5')
    BLOCK_TIME = 10

    def __init__(self, blockchain_file='blockchain_pos.json'):
        self.blockchain_file = blockchain_file
        self.chain = []
        self.pending_transactions = []
        self.known_pending_tx_hashes = set()

        self.validators = [
            'e5c4aba2078eaf36dc11c2e7a00dafa8e02bc39d690b1f063807d99033982590'
        ]

        self.lock = threading.RLock()
        self._load_or_create_chain()

    def _load_or_create_chain(self):
        with self.lock:
            loaded_chain_data = load_json_file(self.blockchain_file)
            if loaded_chain_data:
                loaded_chain = self._deserialize_chain(loaded_chain_data)
                if self.is_chain_valid(loaded_chain):
                    self.chain = loaded_chain
                    self._update_pending_transactions()
                    logger.info(f"PoS Blockchain loaded. Height: {len(self.chain) - 1}")
                else:
                    logger.warning("Loaded PoS blockchain is invalid. Creating new one.")
                    self._create_genesis_block()
            else:
                logger.info("PoS Blockchain file not found. Creating genesis block.")
                self._create_genesis_block()

    def _create_genesis_block(self):
        self.chain = []
        genesis_block = {
            'index': 0, 'timestamp': time.time(), 'transactions': [],
            'validator': 'genesis_address', 'previous_hash': '0',
            'validator_public_key': 'genesis_pub_key', # Field placeholder untuk konsistensi
            'signature': 'genesis_signature'
        }
        self.chain.append(genesis_block)
        self.save_chain()
        logger.info("PoS Genesis block created.")

    def new_block(self, validator_wallet):
        with self.lock:
            validator_address = validator_wallet.get_public_address()
            # --- PERBAIKAN: Sertakan public key di dalam blok ---
            validator_public_key = validator_wallet.public_key.export_key().decode('utf-8')

            coinbase_tx = self._create_transaction_object('0', validator_address, self.BLOCK_REWARD, 'coinbase', 'coinbase')
            transactions_for_block = [coinbase_tx] + self.pending_transactions
            
            block_data = {
                'index': len(self.chain), 'timestamp': time.time(),
                'transactions': transactions_for_block, 'validator': validator_address,
                'validator_public_key': validator_public_key, # <-- KUNCI PUBLIK DITAMBAHKAN
                'previous_hash': self.hash_block(self.last_block)
            }
            
            # Validator menandatangani data blok (tanpa signature)
            signature = validator_wallet.sign_transaction(block_data)
            block_data['signature'] = signature
            return block_data

    def add_block(self, block):
        with self.lock:
            tx_ids_in_block = {tx['transaction_id'] for tx in block['transactions']}
            self.pending_transactions = [tx for tx in self.pending_transactions if tx['transaction_id'] not in tx_ids_in_block]
            self.known_pending_tx_hashes -= tx_ids_in_block
            self.chain.append(block)
            self.save_chain()
            logger.info(f"PoS Block #{block['index']} by {block['validator'][:10]}... added to the chain.")
            return True

    def add_transaction(self, sender, recipient, amount, signature, public_key_str, timestamp=None):
        with self.lock:
            try:
                amount_decimal = Decimal(amount)
                if amount_decimal <= 0: return None
            except InvalidOperation: return None
            if self.get_balance(sender) < amount_decimal: return None
            
            tx_data_to_verify = {'sender': sender, 'recipient': recipient, 'amount': "{:.8f}".format(amount_decimal)}
            if not ArthaWallet.verify_signature(tx_data_to_verify, public_key_str, signature): return None
            
            transaction = self._create_transaction_object(sender, recipient, amount_decimal, signature, public_key_str, timestamp)
            if transaction['transaction_id'] in self.known_pending_tx_hashes: return None
            
            self.pending_transactions.append(transaction)
            self.known_pending_tx_hashes.add(transaction['transaction_id'])
            return transaction

    @property
    def last_block(self):
        with self.lock:
            return self.chain[-1] if self.chain else None

    def hash_block(self, block):
        block_data_to_hash = block.copy()
        block_data_to_hash.pop('signature', None)
        return hash_data(json_serialize(block_data_to_hash))

    def get_next_validator(self):
        with self.lock:
            if not self.chain: return None
            last_block_index = self.last_block['index']
            validator_index = (last_block_index + 1) % len(self.validators)
            return self.validators[validator_index]

    def is_chain_valid(self, chain_to_validate):
        logger.debug(f"Validating chain of length {len(chain_to_validate)}")
        try:
            if not chain_to_validate: 
                logger.error("Validation failed: Chain is empty.")
                return False
            
            genesis_block = chain_to_validate[0]
            if genesis_block['index'] != 0 or genesis_block['previous_hash'] != '0':
                logger.error("Validation failed: Genesis block is corrupted.")
                return False

            temp_balances = {}

            for i in range(len(chain_to_validate)):
                block = chain_to_validate[i]
                
                if i > 0:
                    last_block = chain_to_validate[i-1]
                    if block['previous_hash'] != self.hash_block(last_block):
                        logger.error(f"Validation failed: Hash mismatch at block {block['index']}.")
                        return False
                    
                    expected_validator = self.validators[(block['index']) % len(self.validators)]
                    if block['validator'] != expected_validator:
                        logger.error(f"Validation failed: Wrong validator for block {block['index']}.")
                        return False

                    # --- PERBAIKAN: Verifikasi signature blok ---
                    block_to_verify = block.copy()
                    signature = block_to_verify.pop('signature', None)
                    validator_public_key = block_to_verify.get('validator_public_key')

                    if not validator_public_key or not signature:
                        logger.error(f"Validation failed: Block {block['index']} is missing public key or signature.")
                        return False

                    if not ArthaWallet.verify_signature(block_to_verify, validator_public_key, signature):
                        logger.error(f"Validation failed: Invalid block signature for block {block['index']}.")
                        return False
                
                for tx in block['transactions']:
                    if tx['sender'] == '0': # Coinbase transaction
                        temp_balances[tx['recipient']] = temp_balances.get(tx['recipient'], Decimal('0')) + tx['amount']
                        continue

                    sender, recipient, amount = tx['sender'], tx['recipient'], tx['amount']
                    
                    if temp_balances.get(sender, Decimal('0')) < amount:
                        logger.error(f"Validation failed: Insufficient balance for tx {tx['transaction_id'][:10]} in block {block['index']}.")
                        return False
                    
                    tx_data = {'sender': sender, 'recipient': recipient, 'amount': "{:.8f}".format(amount)}
                    if not ArthaWallet.verify_signature(tx_data, tx['public_key_str'], tx['signature']):
                        logger.error(f"Validation failed: Invalid signature for tx {tx['transaction_id'][:10]} in block {block['index']}.")
                        return False
                    
                    temp_balances[sender] -= amount
                    temp_balances[recipient] = temp_balances.get(recipient, Decimal('0')) + amount

            logger.debug("Chain validation successful.")
            return True
        except Exception as e:
            logger.error(f"CRITICAL ERROR during chain validation: {e}", exc_info=True)
            return False

    def get_balance(self, address) -> Decimal:
        with self.lock:
            balances = {}
            for block in self.chain:
                for tx in block['transactions']:
                    amount = tx['amount']
                    if tx['sender'] != '0':
                        balances[tx['sender']] = balances.get(tx['sender'], Decimal('0')) - amount
                    balances[tx['recipient']] = balances.get(tx['recipient'], Decimal('0')) + amount
            return balances.get(address, Decimal('0'))

    def replace_chain(self, new_chain_data):
        with self.lock:
            new_chain = self._deserialize_chain(new_chain_data)
            if len(new_chain) > len(self.chain) and self.is_chain_valid(new_chain):
                self.chain = new_chain
                self._update_pending_transactions()
                self.save_chain()
                logger.info(f"Chain successfully replaced. New height: {self.last_block['index']}.")
                return True
        return False

    def _update_pending_transactions(self):
        all_tx_ids = {tx['transaction_id'] for block in self.chain for tx in block['transactions']}
        self.pending_transactions = [tx for tx in self.pending_transactions if tx['transaction_id'] not in all_tx_ids]
        self.known_pending_tx_hashes = {tx['transaction_id'] for tx in self.pending_transactions}

    def save_chain(self):
        save_json_file(self.blockchain_file, self.chain)

    def _deserialize_chain(self, chain_data):
        deserialized_chain = []
        for block_data in chain_data:
            block = block_data.copy()
            deserialized_transactions = []
            for tx_data in block.get('transactions', []):
                tx = tx_data.copy()
                try: tx['amount'] = Decimal(tx['amount'])
                except (InvalidOperation, TypeError): continue
                deserialized_transactions.append(tx)
            block['transactions'] = deserialized_transactions
            deserialized_chain.append(block)
        return deserialized_chain

    def _create_transaction_object(self, sender, recipient, amount, signature, public_key_str, timestamp=None):
        tx = {
            'sender': sender, 'recipient': recipient, 'amount': Decimal(amount),
            'timestamp': timestamp or time.time(), 'signature': signature,
            'public_key_str': public_key_str
        }
        keys = ['sender', 'recipient', 'amount', 'timestamp', 'signature']
        tx_copy = tx.copy()
        tx_copy['amount'] = "{:.8f}".format(tx['amount'])
        unique_data = {k: tx_copy.get(k) for k in keys}
        tx['transaction_id'] = hash_data(json_serialize(unique_data))
        return tx
