# artha_blockchain.py

import time
import hashlib
import logging # Import logging module
from artha_utils import hash_data, json_serialize, load_json_file, save_json_file
from artha_wallet import ArthaWallet

logger = logging.getLogger(__name__) # Logger for this module

class ArthaBlockchain:
    TOTAL_SUPPLY = 30_000_000 # Permanent total supply of Artha
    BLOCK_REWARD = 50       # Mining reward per block
    MAX_BLOCKS = TOTAL_SUPPLY // BLOCK_REWARD # Maximum number of blocks that can be mined

    # --- New PoW and Difficulty Adjustment Constants ---
    TARGET_BLOCK_TIME_SECONDS = 60 # Target 1 block every 60 seconds (1 minute)
    DIFFICULTY_ADJUSTMENT_INTERVAL = 10 # Adjust difficulty every 10 blocks
    MAX_DIFFICULTY = 2**256 - 1 # Represents target 0x0...0 (largest possible target)

    def __init__(self, blockchain_file='blockchain.json'):
        self.blockchain_file = blockchain_file
        self.chain = []
        self.pending_transactions = []
        self.known_pending_tx_hashes = set() # NEW: To quickly check for duplicate pending transactions
        self._load_or_create_chain()

    def _load_or_create_chain(self):
        """
        Loads the blockchain from a file or creates the genesis block if none exists.
        """
        loaded_chain = load_json_file(self.blockchain_file)
        if loaded_chain:
            self.chain = loaded_chain
            logger.info(f"Blockchain loaded from '{self.blockchain_file}'. Total blocks: {len(self.chain)}")
            # IMPORTANT: In a real system, pending transactions would be persisted and re-validated.
            # For simplicity in this demo, pending_transactions is reset on load.
            self.pending_transactions = []
            self.known_pending_tx_hashes.clear()
        else:
            logger.info("Blockchain file not found. Creating genesis block...")
            # Set genesis difficulty to a more reasonable number for testing (seconds to find first block)
            # A value like 10 was too fast and caused forks. 5000 is a good starting point for a few seconds.
            genesis_difficulty = 5000 # Adjusted for more stable initial mining
            self.create_genesis_block(genesis_difficulty)
            self.save_chain() # Save the genesis block

    def create_genesis_block(self, initial_difficulty):
        """
        Creates the very first block in the blockchain (the genesis block).
        """
        genesis_block = {
            'index': 0,
            'timestamp': time.time(),
            'transactions': [],
            'nonce': 0, # Nonce for PoW
            'previous_hash': '0', # Zero hash for the first block
            'miner_address': 'genesis_address', # Miner address for the genesis block
            'difficulty': initial_difficulty # Starting difficulty
        }
        self.chain.append(genesis_block)
        logger.info("Genesis block created!")


    def new_block(self, nonce, previous_hash, miner_address):
        """
        Creates a new block and adds it to the chain.
        Includes pending transactions and the mining reward.
        """
        if self.get_current_block_height() >= self.MAX_BLOCKS:
            logger.warning("ArthaChain supply limit reached. No new blocks can be mined.")
            return None

        current_difficulty = self.get_current_difficulty()

        coinbase_tx = {
            'sender': '0',
            'recipient': miner_address,
            'amount': self.BLOCK_REWARD,
            'timestamp': time.time(), # New timestamp for coinbase
            'signature': 'coinbase_signature'
        }
        
        transactions_for_block = []
        
        # Create a temporary balance snapshot up to the previous block.
        # This is crucial for correctly validating transaction balances
        # as if they were applied sequentially within this new block.
        temp_current_balances = self._get_balances_at_block_height(len(self.chain))
        
        # Sort pending transactions by timestamp to process oldest first (optional, but good practice)
        sorted_pending = sorted(self.pending_transactions, key=lambda tx: tx['timestamp'])

        for tx in sorted_pending:
            tx_id = self._calculate_transaction_id(tx) # Use the new method for unique ID

            tx_data_for_verification = {
                'sender': tx['sender'],
                'recipient': tx['recipient'],
                'amount': tx['amount']
            }

            # 1. Verify signature (only for non-coinbase transactions)
            if tx['sender'] != '0' and not ArthaWallet.verify_signature(tx_data_for_verification, tx['public_key_str'], tx['signature']):
                logger.warning(f"Pending transaction {tx_id[:10]}... has invalid signature during block creation. Discarding.")
                continue
            
            # 2. Check balance before this transaction is applied within this block
            sender_balance_in_block = temp_current_balances.get(tx['sender'], 0)
            if tx['sender'] != '0' and sender_balance_in_block < tx['amount']:
                logger.warning(f"Pending transaction {tx_id[:10]}... has insufficient sender balance ({sender_balance_in_block} ARTH). Discarding.")
                continue
            
            # 3. Deduplicate within this block's collected transactions
            # This is to ensure no two identical transactions (by tx_id) are added to the same block
            if tx_id not in [self._calculate_transaction_id(t) for t in transactions_for_block]:
                transactions_for_block.append(tx)
                # Apply transaction impact to temp_current_balances for subsequent transactions in *this* block
                temp_current_balances[tx['sender']] = sender_balance_in_block - tx['amount']
                temp_current_balances[tx['recipient']] = temp_current_balances.get(tx['recipient'], 0) + tx['amount']
            else:
                logger.debug(f"Duplicate pending transaction {tx_id[:10]}... found while building block. Skipping.")
        
        transactions_for_block.append(coinbase_tx) # Coinbase transaction is always added last

        self.pending_transactions = [] # Clear pending transactions queue
        self.known_pending_tx_hashes.clear() # Clear the set of known pending hashes

        block = {
            'index': len(self.chain),
            'timestamp': time.time(),
            'transactions': transactions_for_block,
            'nonce': nonce, # The nonce found by the miner
            'previous_hash': previous_hash or self.hash_block(self.chain[-1]),
            'miner_address': miner_address,
            'difficulty': current_difficulty # Store difficulty in the block
        }
        self.chain.append(block)
        logger.info(f"New block #{block['index']} mined by {miner_address} with difficulty {hex(current_difficulty)}!")
        self.save_chain()
        return block

    def _calculate_transaction_id(self, tx):
        """
        Calculates a unique and stable ID for a transaction.
        This ID is used for deduplication in pending_transactions.
        It should use all fields that define the transaction's uniqueness and do not change.
        """
        # CRITICAL: Include sender, recipient, amount, original timestamp, and signature
        # as these uniquely define a transaction. The timestamp MUST be the one from the tx object.
        unique_data = {
            'sender': tx.get('sender'),
            'recipient': tx.get('recipient'),
            'amount': tx.get('amount'),
            'timestamp': tx.get('timestamp'), # Use the timestamp from the transaction object for its ID
            'signature': tx.get('signature')
        }
        return hash_data(json_serialize(unique_data))

    def add_transaction(self, sender, recipient, amount, signature, public_key_str, timestamp=None):
        """
        Adds a new transaction to the list of pending transactions.
        Verifies the transaction signature and deduplicates.
        'timestamp' parameter is used when receiving transactions from network peers to preserve original timestamp.
        """
        # Coinbase transactions are generated internally by new_block, not added via this method.
        if sender == '0':
            logger.warning("Attempted to add coinbase transaction via add_transaction. This should be handled internally by new_block.")
            return False

        if not sender or not recipient or amount <= 0:
            logger.warning("Invalid transaction: Sender, recipient, or amount is incorrect.")
            return False

        # Data for signature verification MUST be exactly what was signed
        tx_data_for_verification = {
            'sender': sender,
            'recipient': recipient,
            'amount': amount
        }

        # Use provided timestamp (from network broadcast) or generate new one (for local new tx)
        current_tx_timestamp = timestamp if timestamp is not None else time.time()
        
        # Create a temporary transaction dict that is IDENTICAL to what will be added to pending_transactions
        # This is hashed to get the unique tx_id for deduplication.
        temp_transaction_for_hash = {
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
            'timestamp': current_tx_timestamp, # Use this timestamp for the transaction's unique hash
            'signature': signature,
            'public_key_str': public_key_str # Included for hash consistency if needed, but not strictly part of core signed data
        }

        tx_id = self._calculate_transaction_id(temp_transaction_for_hash)

        if tx_id in self.known_pending_tx_hashes:
            logger.debug(f"Transaction {tx_id[:10]}... already in pending queue. Ignoring duplicate.")
            return False # Already pending, ignore

        if not ArthaWallet.verify_signature(tx_data_for_verification, public_key_str, signature):
            logger.warning("Invalid transaction: Signature does not match.")
            return False

        # Check balance BEFORE adding to pending, based on confirmed funds + already pending funds
        if self.get_balance(sender) < amount:
            logger.warning(f"Invalid transaction: Sender's balance ({self.get_balance(sender)} ARTH) is insufficient for {amount} ARTH.")
            return False

        # If all checks pass, add the transaction to pending list
        transaction = {
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
            'timestamp': current_tx_timestamp, # Store the consistent timestamp for the transaction itself
            'signature': signature,
            'public_key_str': public_key_str # Store public key for future verification
        }
        self.pending_transactions.append(transaction)
        self.known_pending_tx_hashes.add(tx_id) # Add tx_id to known set for quick lookup
        logger.info(f"Transaction {tx_id[:10]}... from {sender[:8]}... to {recipient[:8]}... for {amount} ARTH added to queue.")
        return transaction # IMPORTANT: Return the created transaction object on success

    @property
    def last_block(self):
        """
        Returns the last block in the chain.
        """
        if not self.chain:
            logger.error("Attempted to get last_block from an empty chain. This should not happen after genesis creation.")
            return None # Should be handled by initial chain creation.
        return self.chain[-1]

    def hash_block(self, block):
        """
        Generates a SHA256 hash for a block.
        Ensure all block fields are deterministic for consistent hashing.
        """
        block_copy = dict(block)
        return hash_data(json_serialize(block_copy))

    def get_current_block_height(self):
        """
        Returns the current block height (index of the last block).
        """
        return len(self.chain) - 1

    def _get_balances_at_block_height(self, height):
        """
        Calculates balances up to a specific block height (exclusive of pending transactions).
        This provides the confirmed balance at a specific point in the chain's history.
        """
        balances = {}
        # Iterate through blocks up to the specified height
        for i in range(min(height, len(self.chain))):
            block = self.chain[i]
            for tx in block['transactions']:
                # Ensure recipient/sender are initialized in balances
                balances.setdefault(tx['recipient'], 0)
                balances.setdefault(tx['sender'], 0) 

                if tx['sender'] == '0': # This is a Coinbase transaction
                    balances[tx['recipient']] += tx['amount']
                else: # Regular transaction
                    balances[tx['sender']] -= tx['amount']
                    balances[tx['recipient']] += tx['amount']
        return balances


    def get_balance(self, address):
        """
        Calculates the ARTH balance for a specific address.
        Includes confirmed transactions (from the chain) and pending transactions (in mempool).
        """
        # Get confirmed balance up to the last block
        balance = self._get_balances_at_block_height(len(self.chain)).get(address, 0)
        
        # Account for pending transactions that *this node* knows about
        # This includes transactions initiated by this node, or received from peers.
        # These are funds that are "locked" waiting for confirmation.
        for tx in self.pending_transactions:
            if tx['recipient'] == address:
                balance += tx['amount']
            if tx['sender'] == address:
                balance -= tx['amount']
        return balance

    # --- PoW and Difficulty Methods ---

    def calculate_difficulty(self, last_block, chain):
        """
        Calculates the new difficulty based on the time it took to mine the last DIFFICULTY_ADJUSTMENT_INTERVAL blocks.
        """
        if last_block['index'] == 0: # No adjustment for genesis block
            return last_block['difficulty']
        
        # Only adjust difficulty at defined intervals (e.g., every 10 blocks)
        if last_block['index'] % self.DIFFICULTY_ADJUSTMENT_INTERVAL != 0:
            return last_block['difficulty']

        # Ensure we have enough blocks for the interval before attempting calculation
        if last_block['index'] < self.DIFFICULTY_ADJUSTMENT_INTERVAL:
            return last_block['difficulty']

        # Get the first block of the current adjustment interval
        first_block_in_interval = chain[max(0, last_block['index'] - self.DIFFICULTY_ADJUSTMENT_INTERVAL)]

        actual_time_taken = last_block['timestamp'] - first_block_in_interval['timestamp']
        expected_time = self.DIFFICULTY_ADJUSTMENT_INTERVAL * self.TARGET_BLOCK_TIME_SECONDS

        new_difficulty = last_block['difficulty']

        # Adjust difficulty:
        # If actual_time_taken is too fast, increase difficulty (target hash becomes smaller)
        # If actual_time_taken is too slow, decrease difficulty (target hash becomes larger)
        if actual_time_taken < expected_time / 2: # Much faster than expected (e.g., 5 seconds for 10 blocks instead of 10 minutes)
            new_difficulty = new_difficulty // 2 # Halve the target, i.e., double the actual difficulty
        elif actual_time_taken > expected_time * 2: # Much slower than expected
            new_difficulty = new_difficulty * 2 # Double the target, i.e., halve the actual difficulty
        elif actual_time_taken < expected_time: # Slightly faster
            new_difficulty = int(new_difficulty * 0.9) # Slightly increase difficulty
        elif actual_time_taken > expected_time: # Slightly slower
            new_difficulty = int(new_difficulty * 1.1) # Slightly decrease difficulty
        
        # Ensure difficulty doesn't go below 1 (no division by zero or negative target)
        # And ensure it doesn't exceed MAX_DIFFICULTY (target becomes too easy, effectively no work)
        new_difficulty = max(1, min(new_difficulty, self.MAX_DIFFICULTY))

        logger.info(f"--- Difficulty Adjusted at block #{last_block['index']} ---")
        logger.info(f"  Actual Time: {actual_time_taken:.2f}s, Expected Time: {expected_time}s")
        logger.info(f"  Old Difficulty: {hex(last_block['difficulty'])}, New Difficulty: {hex(new_difficulty)}")
        
        return new_difficulty


    def get_current_difficulty(self):
        """
        Returns the current mining difficulty.
        """
        if not self.chain:
            # This case should only be hit before the genesis block is created.
            return self.MAX_DIFFICULTY // (1000 * 1000) # This value should match initial_difficulty in create_genesis_block call.

        last_block = self.last_block
        
        # Check if it's time for difficulty adjustment and it's not the genesis block
        if (last_block['index'] != 0) and (last_block['index'] % self.DIFFICULTY_ADJUSTMENT_INTERVAL == 0):
            # This means the difficulty stored in the *last_block* is the difficulty that was
            # active *before* this block was mined. We need to calculate the *new* difficulty
            # for the *next* block to be mined.
            return self.calculate_difficulty(last_block, self.chain)
        else:
            # If it's not an adjustment block, or it's the genesis block,
            # difficulty remains the same as the last block's recorded difficulty.
            return last_block['difficulty']


    def is_valid_proof(self, last_block_hash, nonce, difficulty):
        """
        Validates the Proof of Work.
        Checks if the hash of (last_block_hash + nonce) meets the difficulty target.
        """
        guess = f'{last_block_hash}{nonce}'.encode('utf-8')
        guess_hash = hashlib.sha256(guess).hexdigest()
        
        guess_hash_int = int(guess_hash, 16)
        # Calculate target based on current difficulty
        target = self.MAX_DIFFICULTY // difficulty
        
        is_valid = guess_hash_int <= target
        
        # Uncomment for debugging PoW
        # logging.debug(f"  PoW Check - Guess Hash: {guess_hash} (int: {guess_hash_int})")
        # logging.debug(f"  PoW Check - Target: {hex(target)} (int: {target})")
        # logging.debug(f"  PoW Check - Valid PoW: {is_valid}")
        
        return is_valid


    def is_chain_valid(self, chain):
        """
        Verifies the validity of the entire chain.
        Checks hashes, proof of work, and transaction signatures.
        """
        if not chain:
            logger.error("Chain is empty. Cannot validate.")
            return False

        current_balance = {} # Track balances during validation process

        for i in range(len(chain)): # Iterate through all blocks including genesis
            block = chain[i]
            
            # Initialize balances for all addresses encountered so far
            # This ensures any address in a transaction is present in balances dict before use
            for tx in block['transactions']:
                current_balance.setdefault(tx['recipient'], 0)
                current_balance.setdefault(tx['sender'], 0)

            # For blocks after genesis, validate previous_hash and PoW
            if block['index'] > 0:
                last_block_of_validation_pair = chain[i-1]

                if block['previous_hash'] != self.hash_block(last_block_of_validation_pair):
                    logger.error(f"Validation FAILED: Block #{block['index']} has an invalid previous_hash.")
                    return False

                # Ensure difficulty is valid and not zero or negative for PoW check
                if 'difficulty' not in block or block['difficulty'] <= 0:
                     logger.error(f"Validation FAILED: Block #{block['index']} has missing or invalid (<=0) difficulty.")
                     return False

                if not self.is_valid_proof(block['previous_hash'], block['nonce'], block['difficulty']):
                    logger.error(f"Validation FAILED: Block #{block['index']} has an invalid Proof of Work (nonce: {block['nonce']}, difficulty: {hex(block['difficulty'])}).")
                    return False

            coinbase_tx_found = False
            
            for tx in block['transactions']:
                if tx['sender'] == '0': # Coinbase transaction
                    if coinbase_tx_found:
                        logger.error(f"Validation FAILED: Block #{block['index']} has more than one coinbase transaction.")
                        return False
                    if tx['amount'] != self.BLOCK_REWARD:
                        logger.error(f"Validation FAILED: Block #{block['index']} coinbase reward is incorrect: {tx['amount']} (should be {self.BLOCK_REWARD}).")
                        return False
                    if block['index'] > self.MAX_BLOCKS and tx['amount'] > 0:
                        logger.error(f"Validation FAILED: Block #{block['index']} mined after max supply reached.")
                        return False
                    coinbase_tx_found = True
                    current_balance[tx['recipient']] = current_balance.get(tx['recipient'], 0) + tx['amount']
                    continue

                tx_data_for_verification = {
                    'sender': tx['sender'],
                    'recipient': tx['recipient'],
                    'amount': tx['amount']
                }
                # Check for public_key_str presence before verification
                if 'public_key_str' not in tx or not ArthaWallet.verify_signature(tx_data_for_verification, tx['public_key_str'], tx['signature']):
                    logger.error(f"Validation FAILED: Block #{block['index']}, transaction from {tx['sender'][:8]}... has invalid or missing signature/public key.")
                    return False

                # Check sender's balance against current_balance during validation
                sender_balance_at_point_of_tx = current_balance.get(tx['sender'], 0)
                if sender_balance_at_point_of_tx < tx['amount']:
                    logger.error(f"Validation FAILED: Block #{block['index']}, sender's balance ({tx['sender'][:8]}...) is insufficient ({sender_balance_at_point_of_tx} < {tx['amount']}).")
                    return False

                current_balance[tx['sender']] = sender_balance_at_point_of_tx - tx['amount']
                current_balance[tx['recipient']] = current_balance.get(tx['recipient'], 0) + tx['amount']

            # Ensure every non-genesis block has a coinbase transaction if supply limit not reached
            if not coinbase_tx_found and block['index'] <= self.MAX_BLOCKS and block['index'] != 0:
                 logger.error(f"Validation FAILED: Block #{block['index']} does not have a coinbase transaction.")
                 return False


        logger.info("Blockchain chain is valid.")
        return True


    def replace_chain(self, new_chain):
        if len(new_chain) > len(self.chain) and self.is_chain_valid(new_chain):
            logger.info("Chain replaced with a longer and valid chain.")
            self.chain = new_chain
            self.pending_transactions = []
            self.known_pending_tx_hashes.clear() # Clear pending hashes
            self.save_chain()
            return True
        elif len(new_chain) <= len(self.chain):
            logger.debug("New chain is not longer.")
        else:
            logger.warning("New chain is not valid.")
        return False

    def save_chain(self):
        save_json_file(self.blockchain_file, self.chain)
