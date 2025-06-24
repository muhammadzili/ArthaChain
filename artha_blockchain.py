# artha_blockchain.py

import time
import hashlib
from artha_utils import hash_data, json_serialize, load_json_file, save_json_file
from artha_wallet import ArthaWallet

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
        self._load_or_create_chain()

    def _load_or_create_chain(self):
        """
        Loads the blockchain from a file or creates the genesis block if none exists.
        """
        loaded_chain = load_json_file(self.blockchain_file)
        if loaded_chain:
            self.chain = loaded_chain
            print(f"Blockchain loaded from '{self.blockchain_file}'. Total blocks: {len(self.chain)}")
        else:
            print("Blockchain file not found. Creating genesis block...")
            # For genesis block, we'll give it a very easy starting difficulty for testing.
            # A SMALLER 'difficulty' number means an EASIER target (larger target hash number).
            # This makes the first block very fast to mine.
            genesis_difficulty = 1000 # Changed from 2**256 // (1000 * 1000) to a smaller, easier value
            # You can make it even smaller, like 10, for almost instant mining,
            # or larger (e.g., 100000) for a few seconds if you want more "work".
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
        print("Genesis block created!")


    def new_block(self, nonce, previous_hash, miner_address):
        """
        Creates a new block and adds it to the chain.
        Includes pending transactions and the mining reward.
        """
        if self.get_current_block_height() >= self.MAX_BLOCKS:
            print("ArthaChain supply limit reached. No new blocks can be mined.")
            return None

        # Determine current difficulty
        current_difficulty = self.get_current_difficulty()

        # Add the mining reward transaction (coinbase transaction)
        coinbase_tx = {
            'sender': '0', # '0' denotes a coinbase transaction
            'recipient': miner_address,
            'amount': self.BLOCK_REWARD,
            'timestamp': time.time(),
            'signature': 'coinbase_signature' # Special signature for coinbase
        }
        transactions_for_block = self.pending_transactions + [coinbase_tx]
        self.pending_transactions = [] # Clear pending transactions

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
        print(f"New block #{block['index']} mined by {miner_address} with difficulty {hex(current_difficulty)}!")
        self.save_chain()
        return block

    def add_transaction(self, sender, recipient, amount, signature, public_key_str):
        """
        Adds a new transaction to the list of pending transactions.
        Verifies the transaction signature.
        """
        if sender == '0': # Coinbase transactions are handled internally
            self.pending_transactions.append({
                'sender': sender,
                'recipient': recipient,
                'amount': amount,
                'timestamp': time.time(),
                'signature': signature
            })
            return True

        if not sender or not recipient or amount <= 0:
            print("Invalid transaction: Sender, recipient, or amount is incorrect.")
            return False

        # Create dummy transaction_data for signature verification
        # This must be identical to the data used when signing
        tx_data_for_verification = {
            'sender': sender,
            'recipient': recipient,
            'amount': amount
        }

        if not ArthaWallet.verify_signature(tx_data_for_verification, public_key_str, signature):
            print("Invalid transaction: Signature does not match.")
            return False

        if self.get_balance(sender) < amount:
            print(f"Invalid transaction: Sender's balance ({self.get_balance(sender)} ARTH) is insufficient for {amount} ARTH.")
            return False

        transaction = {
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
            'timestamp': time.time(),
            'signature': signature,
            'public_key_str': public_key_str # Store public key for future verification
        }
        self.pending_transactions.append(transaction)
        print(f"Transaction from {sender} to {recipient} for {amount} ARTH added to queue.")
        return True

    @property
    def last_block(self):
        """
        Returns the last block in the chain.
        """
        return self.chain[-1]

    def hash_block(self, block):
        """
        Generates a SHA256 hash for a block.
        The 'difficulty' field is included in the hash,
        but 'proof' (nonce) is replaced by the actual 'nonce' in the block.
        """
        # Create a copy to modify for hashing, removing sensitive/dynamic fields if any
        # For hashing, we need consistent JSON serialization.
        # Ensure only deterministic fields are hashed.
        block_copy = dict(block)
        # We don't hash the actual 'hash' field itself, as it's the result
        # 'proof' was removed, now 'nonce' is the dynamic part to find.
        # 'difficulty' is part of the block data and should be hashed.
        return hash_data(json_serialize(block_copy))

    def get_current_block_height(self):
        """
        Returns the current block height (index of the last block).
        """
        return len(self.chain) - 1

    def get_balance(self, address):
        """
        Calculates the ARTH balance for a specific address.
        """
        balance = 0
        for block in self.chain:
            for tx in block['transactions']:
                if tx['recipient'] == address:
                    balance += tx['amount']
                if tx['sender'] == address:
                    balance -= tx['amount']
        # Also account for pending transactions (funds are "spent" when added to pending)
        for tx in self.pending_transactions:
            if tx['recipient'] == address:
                balance += tx['amount']
            if tx['sender'] == address:
                balance -= tx['amount']
        return balance

    # --- New PoW and Difficulty Methods ---

    def calculate_difficulty(self, last_block, chain):
        """
        Calculates the new difficulty based on the time it took to mine the last DIFFICULTY_ADJUSTMENT_INTERVAL blocks.
        """
        # Only adjust difficulty at defined intervals (e.g., every 10 blocks)
        if last_block['index'] == 0: # No adjustment for genesis block
            return last_block['difficulty']
        
        if last_block['index'] % self.DIFFICULTY_ADJUSTMENT_INTERVAL != 0:
            return last_block['difficulty'] # Return current difficulty if not an adjustment block

        # Get the first block of the current adjustment interval
        first_block_in_interval = chain[max(0, last_block['index'] - self.DIFFICULTY_ADJUSTMENT_INTERVAL)]

        # Calculate the actual time taken to mine these blocks
        actual_time_taken = last_block['timestamp'] - first_block_in_interval['timestamp']
        
        # Calculate the expected time for these blocks
        expected_time = self.DIFFICULTY_ADJUSTMENT_INTERVAL * self.TARGET_BLOCK_TIME_SECONDS

        new_difficulty = last_block['difficulty']

        # Adjust difficulty:
        # If actual_time_taken is too fast, increase difficulty (target hash becomes smaller)
        # If actual_time_taken is too slow, decrease difficulty (target hash becomes larger)
        # We want to multiply difficulty by expected_time / actual_time_taken
        # For simplicity, we use factors of 0.9 and 1.1 for slight adjustments,
        # and 0.5 (//2) and 2 for major adjustments.
        if actual_time_taken < expected_time / 2: # Much faster than expected
            new_difficulty = new_difficulty // 2 # Halve the target, i.e., double the actual difficulty
        elif actual_time_taken > expected_time * 2: # Much slower than expected
            new_difficulty = new_difficulty * 2 # Double the target, i.e., halve the actual difficulty
        elif actual_time_taken < expected_time: # Slightly faster
            new_difficulty = int(new_difficulty * 0.9) # Slightly increase difficulty
        elif actual_time_taken > expected_time: # Slightly slower
            new_difficulty = int(new_difficulty * 1.1) # Slightly decrease difficulty
        
        # Ensure difficulty doesn't go below 1 (no division by zero or negative target)
        # And ensure it doesn't exceed MAX_DIFFICULTY (target becomes too easy)
        new_difficulty = max(1, min(new_difficulty, self.MAX_DIFFICULTY))

        print(f"--- Difficulty Adjusted at block #{last_block['index']} ---")
        print(f"  Actual Time: {actual_time_taken:.2f}s, Expected Time: {expected_time}s")
        print(f"  Old Difficulty: {hex(last_block['difficulty'])}, New Difficulty: {hex(new_difficulty)}")
        
        return new_difficulty


    def get_current_difficulty(self):
        """
        Returns the current mining difficulty.
        """
        # If blockchain is empty (e.g., first run before genesis block is created)
        if not self.chain:
            # Return a default starting difficulty. This is typically set during genesis block creation.
            # This part should ideally only be hit before the genesis block is appended.
            # The initial genesis_difficulty is passed to create_genesis_block.
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
        
        # Convert hash to integer to compare with difficulty target
        guess_hash_int = int(guess_hash, 16)
        
        # The target is MAX_DIFFICULTY / difficulty.
        # A higher 'difficulty' number means an easier target hash (larger number)
        # A lower 'difficulty' number means a harder target hash (smaller number, more leading zeros)
        # So, we check if the guess_hash_int is LESS THAN or EQUAL TO the target.
        target = self.MAX_DIFFICULTY // difficulty # This is the numerical target
        
        is_valid = guess_hash_int <= target
        
        # Uncomment for debugging PoW
        # print(f"  Guess Hash: {guess_hash} (int: {guess_hash_int})")
        # print(f"  Target: {hex(target)} (int: {target})")
        # print(f"  Valid PoW: {is_valid}")
        
        return is_valid


    def is_chain_valid(self, chain):
        """
        Verifies the validity of the entire chain.
        Checks hashes, proof of work, and transaction signatures.
        """
        if not chain:
            return False # Empty chain is not valid

        current_balance = {} # Balance tracked during chain validation

        for i in range(1, len(chain)):
            block = chain[i]
            last_block_of_validation_pair = chain[i-1] # The block *before* the current one being validated

            # 1. Check previous block's hash
            # The 'previous_hash' in the current block must match the hash of the block before it.
            if block['previous_hash'] != self.hash_block(last_block_of_validation_pair):
                print(f"Validation FAILED: Block #{block['index']} has an invalid previous_hash.")
                return False

            # 2. Check Proof of Work
            # The difficulty used for validation is the one stored in the current block.
            # We verify the nonce against the hash of the *previous block* and the stored difficulty.
            if not self.is_valid_proof(block['previous_hash'], block['nonce'], block['difficulty']):
                print(f"Validation FAILED: Block #{block['index']} has an invalid Proof of Work.")
                return False

            # 3. Validate transactions within the block
            coinbase_tx_found = False
            
            for tx in block['transactions']:
                if tx['sender'] == '0': # Coinbase transaction
                    if coinbase_tx_found:
                        print(f"Validation FAILED: Block #{block['index']} has more than one coinbase transaction.")
                        return False
                    if tx['amount'] != self.BLOCK_REWARD:
                        print(f"Validation FAILED: Block #{block['index']} coinbase reward is incorrect: {tx['amount']} (should be {self.BLOCK_REWARD}).")
                        return False
                    if block['index'] > self.MAX_BLOCKS and tx['amount'] > 0:
                        print(f"Validation FAILED: Block #{block['index']} mined after max supply reached.")
                        return False
                    coinbase_tx_found = True
                    # Update balance for coinbase, as there's no sender
                    current_balance[tx['recipient']] = current_balance.get(tx['recipient'], 0) + tx['amount']
                    continue

                # Verify regular transaction signature
                tx_data_for_verification = {
                    'sender': tx['sender'],
                    'recipient': tx['recipient'],
                    'amount': tx['amount']
                }
                if not ArthaWallet.verify_signature(tx_data_for_verification, tx['public_key_str'], tx['signature']):
                    print(f"Validation FAILED: Block #{block['index']}, transaction from {tx['sender']} has an invalid signature.")
                    return False

                # Periksa saldo pengirim (check sender's balance)
                sender_balance_before_tx = current_balance.get(tx['sender'], 0)
                if sender_balance_before_tx < tx['amount']:
                    print(f"Validation FAILED: Block #{block['index']}, sender's balance ({tx['sender']}) is insufficient.")
                    return False

                # Update tracked balances
                current_balance[tx['sender']] = sender_balance_before_tx - tx['amount']
                current_balance[tx['recipient']] = current_balance.get(tx['recipient'], 0) + tx['amount']

            if not coinbase_tx_found and block['index'] <= self.MAX_BLOCKS:
                 print(f"Validation FAILED: Block #{block['index']} does not have a coinbase transaction.")
                 return False


        print("Blockchain chain is valid.")
        return True


    def replace_chain(self, new_chain):
        """
        Replaces the current chain with a new chain if it's longer and valid.
        Returns True if the chain was replaced, False otherwise.
        """
        if len(new_chain) > len(self.chain) and self.is_chain_valid(new_chain):
            print("Chain replaced with a longer and valid chain.")
            self.chain = new_chain
            self.pending_transactions = [] # Clear pending transactions after sync
            self.save_chain()
            return True
        elif len(new_chain) <= len(self.chain):
            print("New chain is not longer.")
        else:
            print("New chain is not valid.")
        return False

    def save_chain(self):
        """
        Saves the current blockchain to a file.
        """
        save_json_file(self.blockchain_file, self.chain)


