# artha_blockchain.py

import time
from artha_utils import hash_data, json_serialize, load_json_file, save_json_file
from artha_wallet import ArthaWallet # For transaction signature verification

class ArthaBlockchain:
    TOTAL_SUPPLY = 30_000_000 # Permanent total supply of Artha
    BLOCK_REWARD = 50       # Mining reward per block
    MAX_BLOCKS = TOTAL_SUPPLY // BLOCK_REWARD # Maximum number of blocks that can be mined

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
            self.create_genesis_block()
            self.save_chain() # Save the genesis block

    def create_genesis_block(self):
        """
        Creates the very first block in the blockchain (the genesis block).
        """
        genesis_block = {
            'index': 0,
            'timestamp': time.time(),
            'transactions': [],
            'proof': 1, # Simple proof for the genesis block
            'previous_hash': '0', # Zero hash for the first block
            'miner_address': 'genesis_address' # Miner address for the genesis block
        }
        self.chain.append(genesis_block)

    def new_block(self, proof, previous_hash, miner_address):
        """
        Creates a new block and adds it to the chain.
        Includes pending transactions and the mining reward.
        """
        if self.get_current_block_height() >= self.MAX_BLOCKS:
            print("ArthaChain supply limit reached. No new blocks can be mined.")
            return None

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
            'proof': proof,
            'previous_hash': previous_hash or self.hash_block(self.chain[-1]),
            'miner_address': miner_address
        }
        self.chain.append(block)
        print(f"New block #{block['index']} mined by {miner_address}!")
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
        # This must be identical to the data used during signing
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
        """
        return hash_data(json_serialize(block))

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
        # Also account for pending transactions
        for tx in self.pending_transactions:
            if tx['recipient'] == address:
                balance += tx['amount']
            if tx['sender'] == address:
                balance -= tx['amount']
        return balance

    def is_chain_valid(self, chain):
        """
        Verifies the validity of the entire chain.
        Checks hashes, proof, and transaction signatures.
        """
        if not chain:
            return False # Empty chain is not valid

        current_balance = {} # Balance tracked during chain validation

        for i in range(1, len(chain)):
            block = chain[i]
            last_block = chain[i-1]

            # 1. Check previous block's hash
            if block['previous_hash'] != self.hash_block(last_block):
                print(f"Validation FAILED: Block #{block['index']} has an invalid previous_hash.")
                return False

            # 2. Check proof (simple) - For this example, just ensure it's not zero
            if block['proof'] <= 0:
                print(f"Validation FAILED: Block #{block['index']} has an invalid proof.")
                return False

            # 3. Validate transactions within the block
            coinbase_tx_found = False
            block_reward_total = 0

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
                    block_reward_total += tx['amount'] # Add to total reward
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

                # Check sender's balance
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

