# artha_blockchain.py

import time
import hashlib
import threading
from decimal import Decimal, getcontext
from artha_utils import hash_data, json_serialize, load_json_file, save_json_file
from artha_wallet import ArthaWallet
import logging

getcontext().prec = 28
logger = logging.getLogger(__name__)

class ArthaBlockchain:
    # Constants for ARTH blockchain parameters
    TOTAL_SUPPLY = Decimal('21000000')  # Total ARTH supply cap
    BLOCK_REWARD_BASE = Decimal('50')  # Initial block reward
    HALVING_INTERVAL = 210000  # Number of blocks before reward halves
    TARGET_BLOCK_TIME_SECONDS = 60
    DIFFICULTY_ADJUSTMENT_INTERVAL = 10

    def __init__(self, blockchain_file='blockchain.json'):
        self.blockchain_file = blockchain_file
        self.chain = []
        self.pending_transactions = []
        self.known_pending_tx_hashes = set()
        # Guards chain mutations. The miner thread and the network message
        # thread both write to self.chain, so without this they interleave.
        self.chain_lock = threading.RLock()
        # Cached (balances, total_issued, total_work) folded over self.chain so
        # that balance lookups and incremental validation do not rescan every
        # block. total_work is what decides which competing branch wins.
        self._state_cache = None
        self._load_or_create_chain()

    def _invalidate_cache(self):
        self._state_cache = None

    def _load_or_create_chain(self):
        loaded_chain = load_json_file(self.blockchain_file)
        if loaded_chain and self.is_chain_valid(loaded_chain):
            self.chain = loaded_chain
            self._warm_cache()
            logger.info(f"Blockchain loaded. Height: {len(self.chain) - 1}")
        else:
            if loaded_chain:
                logger.warning("Loaded blockchain is invalid. Creating new one.")
            else:
                logger.info("Blockchain file not found. Creating genesis block.")
            self.create_genesis_block(200000)

    @staticmethod
    def _block_work(block):
        """Proof-of-work contributed by one block. Genesis does not count."""
        if block.get('index', 0) <= 0:
            return 0
        difficulty = block.get('difficulty') or 1
        return (2**256) // (difficulty if difficulty > 0 else 1)

    def _compute_work(self, chain):
        return sum(self._block_work(b) for b in chain)

    def _warm_cache(self):
        """Fold the whole chain into (balances, total_issued, total_work) without re-validating."""
        balances, total_issued, total_work = {}, Decimal('0'), 0
        for block in self.chain:
            total_work += self._block_work(block)
            for tx in block.get('transactions', []):
                try:
                    amount = Decimal(tx['amount'])
                except Exception:
                    continue
                if tx['sender'] != '0':
                    balances[tx['sender']] = balances.get(tx['sender'], Decimal('0')) - amount
                balances[tx['recipient']] = balances.get(tx['recipient'], Decimal('0')) + amount
                if tx['sender'] == '0':
                    total_issued += amount
        self._state_cache = (balances, total_issued, total_work)

    def get_total_issued(self):
        """Total ARTH issued from coinbase transactions across chain."""
        with self.chain_lock:
            if self._state_cache is None:
                self._warm_cache()
            return self._state_cache[1]

    def get_total_work(self):
        """Cumulative proof-of-work in the current chain."""
        with self.chain_lock:
            if self._state_cache is None:
                self._warm_cache()
            return self._state_cache[2]

    def get_block_reward(self, height, issued_so_far=None):
        """Calculate block reward at given height with halving + hard cap remainder."""
        if issued_so_far is None:
            issued_so_far = self.get_total_issued()
        if issued_so_far >= self.TOTAL_SUPPLY:
            return Decimal('0')
        reward = self.BLOCK_REWARD_BASE
        if self.HALVING_INTERVAL > 0:
            halvings = height // self.HALVING_INTERVAL
            if halvings >= 1:
                reward = self.BLOCK_REWARD_BASE / (Decimal(2) ** Decimal(halvings))
        if reward < Decimal('0.00000001'):
            reward = Decimal('0')
        remaining = self.TOTAL_SUPPLY - issued_so_far
        if reward > remaining:
            reward = remaining
        if reward < Decimal('0'):
            reward = Decimal('0')
        return reward

    def create_genesis_block(self, initial_difficulty):
        self.chain = []
        genesis_block = {
            'index': 0,
            'timestamp': 0,  # deterministic genesis for P2P sync
            'transactions': [],
            'nonce': 0,
            'previous_hash': '0',
            'miner_address': 'genesis_address',
            'difficulty': initial_difficulty
        }
        self.chain.append(genesis_block)
        self._invalidate_cache()
        self.save_chain()
        logger.info("Genesis block created.")

    def new_block(self, nonce, previous_hash, miner_address, difficulty=None):
        issued_now = self.get_total_issued()
        if issued_now >= self.TOTAL_SUPPLY:
            logger.info("Maximum supply already reached. Cannot create new block.")
            return None
        reward = self.get_block_reward(self.get_current_block_height(), issued_now)
        if reward <= Decimal('0'):
            logger.info("Maximum supply reached. Cannot mint new block reward.")
            return None

        canonical_reward = "{:.8f}".format(reward)
        coinbase_tx = {
            'sender': '0', 'recipient': miner_address, 'amount': canonical_reward,
            'timestamp': time.time(), 'signature': 'coinbase', 'public_key_str': 'coinbase'
        }
        
        temp_balances = self.get_balance_snapshot()
        transactions_for_block = [coinbase_tx]
        included_tx_ids = set()
        
        temp_balances[miner_address] = temp_balances.get(miner_address, Decimal('0')) + reward
        
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
            'difficulty': difficulty if difficulty is not None else self.get_current_difficulty()
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
        transaction['transaction_id'] = tx_id

        # Clean stale known entries (tx not pending anymore)
        if self.known_pending_tx_hashes:
            # Rebuild known from current pending to avoid stale
            current_known = {self._calculate_transaction_id(t) for t in self.pending_transactions}
            self.known_pending_tx_hashes = current_known

        # Check if already pending
        if tx_id in self.known_pending_tx_hashes:
            return None

        # Check if already confirmed in chain
        confirmed_ids = {
            self._calculate_transaction_id(tx)
            for block in self.chain for tx in block.get('transactions', [])
            if tx.get('sender') != '0'
        }
        if tx_id in confirmed_ids:
            return None

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
        with self.chain_lock:
            if self._state_cache is None:
                self._warm_cache()
            return dict(self._state_cache[0])

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
        """Validate a chain from genesis. Returns True/False."""
        ok, _reason, _state = self._validate_chain(chain_to_validate)
        return ok

    def _validate_chain(self, chain_to_validate, base_state=None, start_index=0):
        """
        Validate a chain, optionally only the part that follows an already
        accepted prefix. This is what makes catching up cheap: syncing 2 missing
        blocks validates 2 blocks instead of re-verifying every RSA signature
        in the whole chain.

        Returns (ok, reason, final_state) where final_state is
        (balances, total_issued) folded over the validated chain.
        """
        if not chain_to_validate:
            return False, 'empty chain', None
        if chain_to_validate[0].get('index') != 0 or chain_to_validate[0].get('previous_hash') != '0':
            return False, 'invalid genesis block', None

        if base_state is None:
            current_balances, total_issued, total_work = {}, Decimal('0'), 0
        else:
            current_balances = dict(base_state[0])
            total_issued, total_work = base_state[1], base_state[2]

        for i in range(start_index, len(chain_to_validate)):
            block = chain_to_validate[i]
            total_work += self._block_work(block)

            # Guards against duplicate / out-of-order indexes, which is exactly
            # what a node sees when it is sent a block it already has.
            if block.get('index') != i:
                return False, f'index mismatch at position {i} (block says {block.get("index")})', None

            if i > 0:
                last_block = chain_to_validate[i - 1]
                if block.get('previous_hash') != self.hash_block(last_block):
                    return False, f'previous_hash mismatch at block {i}', None
                if not self.is_valid_proof(block['previous_hash'], block.get('nonce'), block.get('difficulty')):
                    return False, f'invalid proof of work at block {i}', None

            coinbase_count = 0
            coinbase_amount = Decimal('0')
            for tx in block.get('transactions', []):
                amount = Decimal(tx['amount'])
                if tx['sender'] == '0':
                    coinbase_count += 1
                    coinbase_amount += amount
                    current_balances[tx['recipient']] = current_balances.get(tx['recipient'], Decimal('0')) + amount
                    continue

                current_balances.setdefault(tx['sender'], Decimal('0'))
                if current_balances[tx['sender']] < amount:
                    return False, f'insufficient balance at block {i}', None

                tx_data = {'sender': tx['sender'], 'recipient': tx['recipient'], 'amount': tx['amount']}
                if not ArthaWallet.verify_signature(tx_data, tx['public_key_str'], tx['signature']):
                    return False, f'invalid transaction signature at block {i}', None

                current_balances[tx['sender']] -= amount
                current_balances[tx['recipient']] = current_balances.get(tx['recipient'], Decimal('0')) + amount

            if coinbase_count > 1:
                return False, f'multiple coinbase transactions at block {i}', None
            if block['index'] > 0:
                expected_reward = self.get_block_reward(block['index'] - 1, total_issued)
                if abs(coinbase_amount - expected_reward) > Decimal('0.00000001'):
                    return False, f'incorrect coinbase reward at block {i}', None
            total_issued += coinbase_amount
            if total_issued > self.TOTAL_SUPPLY + Decimal('0.00000001'):
                return False, f'supply cap exceeded at block {i}', None

        return True, None, (current_balances, total_issued, total_work)

    def add_block(self, block):
        """
        Validate and append a single block that extends the current tip.
        Returns True only when the block was actually stored.
        """
        with self.chain_lock:
            last_block = self.last_block
            if not last_block or block.get('previous_hash') != self.hash_block(last_block):
                return False

            if self._state_cache is None:
                self._warm_cache()

            candidate = self.chain + [block]
            ok, reason, state = self._validate_chain(
                candidate, base_state=self._state_cache, start_index=len(self.chain)
            )
            if not ok:
                logger.warning(f'Rejected block #{block.get("index")}: {reason}')
                return False

            self.chain = candidate
            self._state_cache = state
            self._drop_confirmed_transactions()
            self.save_chain()
            logger.debug(f'Block #{block["index"]} appended. Height: {len(self.chain) - 1}')
            return True

    def _drop_confirmed_transactions(self):
        """Remove pending transactions that are already confirmed in the chain."""
        confirmed_ids = {
            self._calculate_transaction_id(tx)
            for block in self.chain for tx in block.get('transactions', [])
            if tx.get('sender') != '0'
        }
        self.pending_transactions = [
            tx for tx in self.pending_transactions
            if self._calculate_transaction_id(tx) not in confirmed_ids
        ]
        self.known_pending_tx_hashes = {
            self._calculate_transaction_id(tx) for tx in self.pending_transactions
        }

    def _outranks_current(self, new_chain):
        """
        Decide whether an incoming chain should replace ours.

        Longer always wins. When two branches are the same length the old code
        refused both, which meant a fork between two miners could never resolve
        and the losing node asked for the same block forever. So ties are broken
        by total proof-of-work, then by tip hash. Every node applies the same
        rule to the same pair of chains, so the network converges on one branch
        instead of deadlocking.
        """
        new_len, cur_len = len(new_chain), len(self.chain)
        if new_len != cur_len:
            return new_len > cur_len

        new_tip = self.hash_block(new_chain[-1])
        cur_tip = self.hash_block(self.chain[-1])
        if new_tip == cur_tip:
            return False  # identical tip, nothing to do

        if self._state_cache is None:
            self._warm_cache()
        new_work = self._compute_work(new_chain)
        cur_work = self._state_cache[2]
        if new_work != cur_work:
            return new_work > cur_work
        return new_tip > cur_tip

    def _restore_orphaned_transactions(self, old_chain, new_chain):
        """Restore non-coinbase transactions from orphaned blocks back to mempool."""
        try:
            # Get confirmed tx_ids in new chain
            confirmed_in_new = set()
            for block in new_chain:
                for tx in block.get('transactions', []):
                    if tx.get('sender') != '0':
                        confirmed_in_new.add(self._calculate_transaction_id(tx))

            # Collect orphaned txs from old chain (not confirmed in new)
            orphan_txs = []
            for block in old_chain:
                for tx in block.get('transactions', []):
                    if tx.get('sender') != '0':
                        tx_id = self._calculate_transaction_id(tx)
                        if tx_id not in confirmed_in_new:
                            orphan_txs.append(tx)

            if not orphan_txs:
                return

            # Merge into pending, avoid duplicates
            existing_ids = set(self.known_pending_tx_hashes)
            added = 0
            for tx in orphan_txs:
                tx_id = self._calculate_transaction_id(tx)
                if tx_id not in existing_ids:
                    # Ensure tx has tx_id
                    if 'transaction_id' not in tx:
                        tx['transaction_id'] = tx_id
                    self.pending_transactions.append(tx)
                    self.known_pending_tx_hashes.add(tx_id)
                    existing_ids.add(tx_id)
                    added += 1
            if added:
                logger.info(f'Restored {added} orphaned transaction(s) to mempool')
        except Exception as e:
            logger.warning(f'Failed to restore orphaned transactions: {e}')

    def replace_chain(self, new_chain):
        """
        Adopt a chain received from a peer when it outranks ours.
        Returns True only when the chain was actually replaced, so callers never
        announce a sync that did not happen.
        """
        with self.chain_lock:
            if not new_chain:
                return False

            if not self._outranks_current(new_chain):
                logger.debug(
                    f'Ignored non-winning chain from peer: '
                    f'{len(new_chain) - 1} blocks, work {self._compute_work(new_chain)}'
                )
                return False

            old_chain = list(self.chain)
            ok, reason, state = self._validate_chain(new_chain)
            if not ok:
                logger.warning(f'Rejected chain from peer: {reason}')
                return False

            self.chain = new_chain
            self._state_cache = state
            self._drop_confirmed_transactions()
            # Restore orphaned txs from old chain
            self._restore_orphaned_transactions(old_chain, self.chain)
            self.save_chain()
            logger.info(f'Chain updated to block #{self.last_block["index"]}.')
            return True

    def get_chain(self):
        return list(self.chain)

    def get_pending_transactions(self):
        return list(self.pending_transactions)

    def get_pending_tx_count(self):
        return len(self.pending_transactions)

    def remove_pending_transactions(self, tx_ids):
        if not tx_ids:
            return
        tx_ids_set = set(tx_ids)
        self.pending_transactions = [
            tx for tx in self.pending_transactions
            if self._calculate_transaction_id(tx) not in tx_ids_set
        ]
        self.known_pending_tx_hashes = {
            self._calculate_transaction_id(tx) for tx in self.pending_transactions
        }

    def invalidate_last_blocks(self, n=1):
        """
        BTC-style: Unvalidate/invalidate last n blocks from tip.
        Rewinds chain by n blocks. Restores orphaned transactions back to mempool.
        Backward compatible method name (also add aliases: unvalidate_last_blocks, pop_last_blocks)
        """
        if n < 1:
            return False
        with self.chain_lock:
            if len(self.chain) <= 1:  # cannot invalidate genesis
                return False
            n = min(n, len(self.chain) - 1)
            old_chain = list(self.chain)
            # New chain = old chain without last n blocks
            new_chain = old_chain[:-n]
            # Validate the new prefix
            ok, reason, state = self._validate_chain(new_chain)
            if not ok:
                logger.warning(f'Cannot invalidate last {n} blocks: {reason}')
                return False
            self.chain = new_chain
            self._state_cache = state
            self._drop_confirmed_transactions()
            self._restore_orphaned_transactions(old_chain, self.chain)
            self.save_chain()
            logger.info(f'Invalidated last {n} block(s). New height: {self.get_current_block_height()}')
            return True

    # Aliases for compatibility
    unvalidate_last_blocks = invalidate_last_blocks
    pop_last_blocks = invalidate_last_blocks
    rewind_to_height = lambda self, height: self.invalidate_last_blocks(self.get_current_block_height() - height) if height >= 0 else False

    def save_chain(self):
        save_json_file(self.blockchain_file, self.chain)
