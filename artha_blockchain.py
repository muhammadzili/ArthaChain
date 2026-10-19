# artha_blockchain.py

import time
import hashlib
import shutil
import os
import threading
from decimal import Decimal, getcontext
from artha_utils import hash_data, json_serialize, load_json_file, save_json_file, get_data_dir
from artha_wallet import ArthaWallet
import artha_protocol as P
import logging

getcontext().prec = 28
logger = logging.getLogger(__name__)

# Batas atas nilai Decimal yang valid tanpa memicu InvalidOperation.
_POS_INF = Decimal('Infinity')
_NEG_INF = Decimal('-Infinity')


def _finite(amount):
    """True bila `amount` bilangan berhingga (bukan NaN/Infinity)."""
    return amount == amount and amount not in (_POS_INF, _NEG_INF)


class ArthaBlockchain:
    # Nilai lama tetap diekspos untuk kompatibilitas pemanggil; sumber
    # kebenarannya sekarang di artha_protocol.
    TOTAL_SUPPLY = P.TOTAL_SUPPLY
    BLOCK_REWARD_BASE = P.BLOCK_REWARD_BASE
    HALVING_INTERVAL = P.HALVING_INTERVAL
    TARGET_BLOCK_TIME_SECONDS = P.TARGET_BLOCK_TIME_V2
    DIFFICULTY_ADJUSTMENT_INTERVAL = P.DIFFICULTY_ADJUSTMENT_INTERVAL

    def __init__(self, blockchain_file='blockchain.json', max_reorg_depth=P.MAX_REORG_DEPTH):
        self.blockchain_file = blockchain_file
        self.chain = []
        self.pending_transactions = []
        self.known_pending_tx_hashes = set()
        # Guards chain mutations. The miner thread and the network message
        # thread both write to self.chain, so without this they interleave.
        self.chain_lock = threading.RLock()
        # Cached (balances, total_issued, total_work, nonces) folded over
        # self.chain so lookups do not rescan every block.
        self._state_cache = None
        # id transaksi non-coinbase yang sudah confirmed, agar submit_transaction
        # tidak menghash ulang seluruh chain setiap ada tx baru masuk mempool.
        self._confirmed_tx_ids = set()
        self.max_reorg_depth = max_reorg_depth
        self._load_or_create_chain()

    def _invalidate_cache(self):
        self._state_cache = None

    @staticmethod
    def _backup_file(path):
        backup = path + '.bak-' + time.strftime('%Y%m%d%H%M%S')
        try:
            shutil.copy2(path, backup)
            return backup
        except OSError:
            return None

    def _load_or_create_chain(self):
        path = os.path.join(get_data_dir(), self.blockchain_file)
        if os.path.exists(path):
            loaded = load_json_file(self.blockchain_file)
            if loaded and self.is_chain_valid(loaded):
                self.chain = loaded
                self._warm_cache()
                logger.info(f"Blockchain loaded. Height: {len(self.chain) - 1}")
                return
            # Jangan pernah menimpa chain yang ada hanya karena gagal validasi.
            # Backup dulu lalu berhenti supaya data tidak hilang diam-diam.
            backup = self._backup_file(path)
            logger.critical(f"blockchain.json ada tetapi INVALID. Tidak ditimpa. Backup: {backup}")
            raise RuntimeError(
                "Blockchain file invalid; refusing to overwrite to avoid data loss. "
                f"Backup kept at: {backup}"
            )
        logger.info("Blockchain file not found. Creating genesis block.")
        self.create_genesis_block(P.GENESIS_DIFFICULTY)

    # ------------------------------------------------------------------
    # Work / state cache
    # ------------------------------------------------------------------

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
        """Fold the whole chain into (balances, total_issued, total_work, nonces)."""
        balances, total_issued, total_work, nonces = {}, Decimal('0'), 0, {}
        confirmed_ids = set()
        for block in self.chain:
            total_work += self._block_work(block)
            for tx in block.get('transactions', []):
                try:
                    amount = Decimal(tx['amount'])
                except Exception:
                    continue
                sender = tx.get('sender')
                recipient = tx.get('recipient')
                if sender != '0':
                    confirmed_ids.add(self._calculate_transaction_id(tx))
                    fee = Decimal(tx['fee']) if 'fee' in tx else Decimal('0')
                    balances[sender] = balances.get(sender, Decimal('0')) - amount - fee
                    balances[recipient] = balances.get(recipient, Decimal('0')) + amount
                    if 'nonce' in tx:
                        try:
                            n = int(tx['nonce'])
                        except (TypeError, ValueError):
                            n = None
                        if n is not None:
                            nonces[sender] = max(nonces.get(sender, 0), n + 1)
                else:
                    balances[recipient] = balances.get(recipient, Decimal('0')) + amount
                    reported = tx.get('block_reward')
                    total_issued += Decimal(reported) if reported is not None else amount
        self._state_cache = (balances, total_issued, total_work, nonces)
        self._confirmed_tx_ids = confirmed_ids

    def _reindex_confirmed_tx_ids(self):
        self._confirmed_tx_ids = {
            self._calculate_transaction_id(tx)
            for block in self.chain
            for tx in block.get('transactions', [])
            if tx.get('sender') != '0'
        }

    def get_total_issued(self):
        with self.chain_lock:
            if self._state_cache is None:
                self._warm_cache()
            return self._state_cache[1]

    def get_total_work(self):
        with self.chain_lock:
            if self._state_cache is None:
                self._warm_cache()
            return self._state_cache[2]

    def get_balance_snapshot(self):
        with self.chain_lock:
            if self._state_cache is None:
                self._warm_cache()
            return dict(self._state_cache[0])

    def get_nonce_snapshot(self):
        with self.chain_lock:
            if self._state_cache is None:
                self._warm_cache()
            return dict(self._state_cache[3])

    def get_balance(self, address) -> Decimal:
        return self.get_balance_snapshot().get(address, Decimal('0'))

    def get_nonce(self, address):
        return self.get_nonce_snapshot().get(address, 0)

    def get_next_nonce(self, address):
        """Nonce berikutnya yang harus dipakai sender: confirmed + pending v2."""
        base = self.get_nonce(address)
        pending = sum(
            1 for t in self.pending_transactions
            if int(t.get('version', 1)) == 2 and t.get('sender') == address
        )
        return base + pending

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
        if reward < P.QUANTUM:
            reward = Decimal('0')
        remaining = self.TOTAL_SUPPLY - issued_so_far
        if reward > remaining:
            reward = remaining
        if reward < Decimal('0'):
            reward = Decimal('0')
        return reward

    # ------------------------------------------------------------------
    # Difficulty
    # ------------------------------------------------------------------

    @staticmethod
    def _adjust_difficulty(chain, parent_index):
        interval = P.DIFFICULTY_ADJUSTMENT_INTERVAL
        last = chain[parent_index]
        first = chain[parent_index - (interval - 1)]
        time_taken = last['timestamp'] - first['timestamp']
        if time_taken <= 0:
            time_taken = 1
        expected_time = interval * P.target_block_time(parent_index + 1)
        ratio = max(0.25, min(4.0, expected_time / time_taken))
        return max(1, int(last['difficulty'] / ratio))

    @staticmethod
    def _expected_difficulty(chain, index):
        """
        Difficulty yang WAJIB dibawa blok pada index `index`, dihitung dari
        konteks chain. Direplikasi persis dari algoritma yang dipakai miner,
        jadi chain historis tetap lolos. Lantai (min_difficulty) aktif sejak v2.
        """
        if index <= 0:
            return None
        parent_index = index - 1
        if parent_index < P.DIFFICULTY_ADJUSTMENT_INTERVAL:
            base = P.GENESIS_DIFFICULTY
        elif parent_index % P.DIFFICULTY_ADJUSTMENT_INTERVAL == 0:
            base = ArthaBlockchain._adjust_difficulty(chain, parent_index)
        else:
            base = chain[parent_index]['difficulty']
        return max(P.min_difficulty(index), base)

    def get_current_difficulty(self, height=None):
        with self.chain_lock:
            if not self.chain:
                return P.GENESIS_DIFFICULTY
            if height is None:
                height = len(self.chain)
            expected = self._expected_difficulty(self.chain, height)
            return expected if expected is not None else P.GENESIS_DIFFICULTY

    def is_valid_proof(self, last_block_hash, nonce, difficulty):
        guess = f'{last_block_hash}{nonce}'.encode('utf-8')
        guess_hash = hashlib.sha256(guess).hexdigest()
        target = (2**256 - 1) // (difficulty if difficulty > 0 else 1)
        return int(guess_hash, 16) <= target

    def hash_block(self, block):
        algo = block.get('hash_algo', P.HASH_ALGO_DEFAULT)
        return hash_data(json_serialize({k: v for k, v in block.items() if k != 'hash'}), algo)

    # ------------------------------------------------------------------
    # Genesis & block production
    # ------------------------------------------------------------------

    def create_genesis_block(self, initial_difficulty):
        self.chain = []
        genesis_block = {
            'index': 0,
            'timestamp': 0,
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
        with self.chain_lock:
            block_index = len(self.chain)
            issued_now = self.get_total_issued()
            if issued_now >= self.TOTAL_SUPPLY:
                logger.info("Maximum supply already reached. Cannot create new block.")
                return None
            reward = self.get_block_reward(block_index - 1, issued_now)
            if reward <= Decimal('0'):
                logger.info("Maximum supply reached. Cannot mint new block reward.")
                return None

            v2 = P.is_v2(block_index)
            temp_balances = self.get_balance_snapshot()
            temp_nonce = self.get_nonce_snapshot()
            selected = []
            total_fees = Decimal('0')
            size = 0

            if v2:
                pending = sorted(
                    self.pending_transactions,
                    key=lambda t: (-Decimal(t.get('fee', '0')), t.get('timestamp', 0))
                )
            else:
                pending = sorted(self.pending_transactions, key=lambda t: t['timestamp'])

            for tx in pending:
                if v2:
                    if tx.get('version') != 2:
                        continue
                    try:
                        amount = Decimal(tx['amount'])
                        fee = Decimal(tx.get('fee', '0'))
                    except Exception:
                        continue
                    if fee < P.MIN_TX_FEE:
                        continue
                    sender = tx['sender']
                    if temp_balances.get(sender, Decimal('0')) < amount + fee:
                        continue
                    if int(tx.get('nonce', -1)) != temp_nonce.get(sender, 0):
                        continue
                    if not self._verify_tx_v2(tx):
                        continue
                    tx_size = len(json_serialize(tx))
                    if len(selected) >= P.MAX_TXS_PER_BLOCK or size + tx_size > P.MAX_BLOCK_BYTES:
                        break
                    selected.append(tx)
                    size += tx_size
                    temp_balances[sender] = temp_balances.get(sender, Decimal('0')) - amount - fee
                    temp_balances[tx['recipient']] = temp_balances.get(tx['recipient'], Decimal('0')) + amount
                    temp_nonce[sender] = temp_nonce.get(sender, 0) + 1
                    total_fees += fee
                else:
                    sender, recipient = tx['sender'], tx['recipient']
                    try:
                        amount = Decimal(tx['amount'])
                    except Exception:
                        continue
                    sender_balance = temp_balances.get(sender, Decimal('0'))
                    tx_data = {'sender': sender, 'recipient': recipient, 'amount': tx['amount']}
                    if sender_balance >= amount and ArthaWallet.verify_signature(tx_data, tx['public_key_str'], tx['signature']):
                        selected.append(tx)
                        temp_balances[sender] = sender_balance - amount
                        temp_balances[recipient] = temp_balances.get(recipient, Decimal('0')) + amount

            if v2:
                coinbase_tx = {
                    'sender': '0', 'recipient': miner_address,
                    'amount': "{:.8f}".format(reward + total_fees),
                    'block_reward': "{:.8f}".format(reward),
                    'fees': "{:.8f}".format(total_fees),
                    'timestamp': time.time(), 'signature': 'coinbase', 'public_key_str': 'coinbase'
                }
            else:
                coinbase_tx = {
                    'sender': '0', 'recipient': miner_address,
                    'amount': "{:.8f}".format(reward),
                    'timestamp': time.time(), 'signature': 'coinbase', 'public_key_str': 'coinbase'
                }

            block = {
                'index': block_index, 'timestamp': time.time(),
                'transactions': [coinbase_tx] + selected, 'nonce': nonce,
                'previous_hash': previous_hash, 'miner_address': miner_address,
                'difficulty': difficulty if difficulty is not None else self.get_current_difficulty(),
            }
            if v2:
                block['version'] = P.PROTOCOL_VERSION
                block['hash_algo'] = P.hash_algo_for(block_index)
            return block

    def _verify_tx_v2(self, tx):
        try:
            if ArthaWallet.address_from_public_key(tx['public_key_str']) != tx['sender']:
                return False
            return ArthaWallet.verify_signature(
                ArthaWallet.v2_signed_payload(tx), tx['public_key_str'], tx['signature']
            )
        except Exception:
            return False

    def _calculate_transaction_id(self, tx):
        keys = ['sender', 'recipient', 'amount', 'timestamp', 'signature', 'fee', 'nonce', 'version']
        unique_data = {k: tx.get(k) for k in keys}
        return hash_data(json_serialize(unique_data))

    # ------------------------------------------------------------------
    # Mempool
    # ------------------------------------------------------------------

    def add_transaction(self, sender, recipient, amount, signature, public_key_str,
                        timestamp=None, fee=None, nonce=None, version=1, chain_id=None):
        """
        Bangun transaksi (v1 atau v2) lalu submit. `version=2` atau `nonce`
        diberikan akan memakai format v2 (timestamp/nonce/fee ditandatangani).
        """
        try:
            amount_decimal = Decimal(amount)
        except Exception:
            return None

        if version == 2 or nonce is not None:
            tx = {
                'version': 2, 'chain_id': chain_id or P.CHAIN_ID,
                'sender': sender, 'recipient': recipient,
                'amount': "{:.8f}".format(amount_decimal),
                'fee': "{:.8f}".format(Decimal(fee if fee is not None else P.MIN_TX_FEE)),
                'nonce': int(nonce if nonce is not None else 0),
                'timestamp': timestamp if timestamp is not None else time.time(),
                'signature': signature, 'public_key_str': public_key_str,
                'sig_algo': P.SIG_ALGO_DEFAULT,
            }
        else:
            tx = {
                'sender': sender, 'recipient': recipient,
                'amount': "{:.8f}".format(amount_decimal),
                'timestamp': timestamp if timestamp is not None else time.time(),
                'signature': signature, 'public_key_str': public_key_str,
            }
        return self.submit_transaction(tx)

    def submit_transaction(self, tx):
        """Validasi + dedupe + masukkan ke mempool. Return tx atau None."""
        with self.chain_lock:
            height = self.get_current_block_height() + 1
            v2_required = P.is_v2(height)
            version = int(tx.get('version', 1))

            try:
                amount = Decimal(tx['amount'])
            except Exception:
                return None
            if not _finite(amount) or amount <= 0:
                return None

            sender = tx.get('sender')
            recipient = tx.get('recipient')
            public_key_str = tx.get('public_key_str')
            if not sender or not recipient or not public_key_str:
                return None

            # Ikatan sender <-> public key. Ini menutup pencurian saldo: tanpa
            # ini siapa pun bisa menandatangani tx dengan kunci sendiri sambil
            # menulis sender = alamat korban.
            if ArthaWallet.address_from_public_key(public_key_str) != sender:
                return None

            if v2_required and version != 2:
                return None

            if version == 2:
                if tx.get('sig_algo', P.SIG_ALGO_DEFAULT) not in P.SIG_ALGOS:
                    return None
                try:
                    fee = Decimal(tx.get('fee', '0'))
                except Exception:
                    return None
                if not _finite(fee) or fee < P.MIN_TX_FEE:
                    return None
                ts = tx.get('timestamp', 0)
                now = time.time()
                if ts > now + P.MAX_FUTURE_DRIFT or ts < now - P.MAX_PAST_DRIFT:
                    return None
                if self.get_balance(sender) < amount + fee:
                    return None
                if int(tx.get('nonce', -1)) != self.get_next_nonce(sender):
                    return None
                if not self._verify_tx_v2(tx):
                    return None
            else:
                if self.get_balance(sender) < amount:
                    return None
                tx_data = {'sender': sender, 'recipient': recipient, 'amount': tx['amount']}
                if not ArthaWallet.verify_signature(tx_data, public_key_str, tx.get('signature')):
                    return None

            tx_id = self._calculate_transaction_id(tx)
            tx['transaction_id'] = tx_id
            self.known_pending_tx_hashes = {
                self._calculate_transaction_id(t) for t in self.pending_transactions
            }
            if tx_id in self.known_pending_tx_hashes:
                return None

            if tx_id in self._confirmed_tx_ids:
                return None

            if len(self.pending_transactions) >= P.MAX_MEMPOOL_TXS:
                return None

            self.pending_transactions.append(tx)
            self.known_pending_tx_hashes.add(tx_id)
            return tx

    # ------------------------------------------------------------------
    # Chain views
    # ------------------------------------------------------------------

    @property
    def last_block(self):
        return self.chain[-1] if self.chain else None

    def get_current_block_height(self):
        return len(self.chain) - 1

    def get_confirmations(self, block_height):
        if block_height < 0:
            return 0
        return max(0, self.get_current_block_height() - block_height)

    def is_transaction_finalized(self, tx_id, min_confirmations=6):
        with self.chain_lock:
            cur = self.get_current_block_height()
            for block in reversed(self.chain):
                for tx in block.get('transactions', []):
                    if tx.get('sender') == '0':
                        continue
                    if self._calculate_transaction_id(tx) == tx_id:
                        height = block['index']
                        return (cur - height + 1) >= min_confirmations
            return False

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

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def is_chain_valid(self, chain_to_validate):
        ok, _reason, _state = self._validate_chain(chain_to_validate)
        return ok

    def _validate_chain(self, chain_to_validate, base_state=None, start_index=0):
        """
        Validate a chain, optionally only the part that follows an accepted
        prefix (cheap catch-up). Activation-aware: blocks below ACTIVATION_V2
        use the original rules (so history stays valid), blocks at/after it
        use the v2 rules (difficulty schedule enforced, sender<->pubkey bound,
        nonce replay protection, fees, size caps).
        """
        if not chain_to_validate:
            return False, 'empty chain', None
        if chain_to_validate[0].get('index') != 0 or chain_to_validate[0].get('previous_hash') != '0':
            return False, 'invalid genesis block', None

        if base_state is None:
            current_balances, total_issued, total_work, nonces = {}, Decimal('0'), 0, {}
        else:
            current_balances = dict(base_state[0])
            total_issued, total_work = base_state[1], base_state[2]
            nonces = dict(base_state[3])

        now = time.time()
        for i in range(start_index, len(chain_to_validate)):
            block = chain_to_validate[i]
            total_work += self._block_work(block)

            if block.get('index') != i:
                return False, f'index mismatch at position {i} (block says {block.get("index")})', None

            if i > 0:
                last_block = chain_to_validate[i - 1]
                if block.get('previous_hash') != self.hash_block(last_block):
                    return False, f'previous_hash mismatch at block {i}', None
                if not self.is_valid_proof(block['previous_hash'], block.get('nonce'), block.get('difficulty')):
                    return False, f'invalid proof of work at block {i}', None
                expected_diff = self._expected_difficulty(chain_to_validate, i)
                if expected_diff is not None and block.get('difficulty') != expected_diff:
                    return False, (
                        f'invalid difficulty at block {i}: '
                        f'{block.get("difficulty")} != {expected_diff}'
                    ), None

            v2 = P.is_v2(i)
            if v2:
                ts = block.get('timestamp', 0)
                if i > 0 and ts < chain_to_validate[i - 1].get('timestamp', 0):
                    return False, f'non-monotonic timestamp at block {i}', None
                if ts > now + P.MAX_FUTURE_DRIFT:
                    return False, f'block {i} timestamp too far in future', None
                txs = block.get('transactions', [])
                if len(txs) > P.MAX_TXS_PER_BLOCK:
                    return False, f'too many transactions at block {i}', None
                if len(json_serialize(block)) > P.MAX_BLOCK_BYTES:
                    return False, f'block {i} too large', None

            coinbase_count = 0
            coinbase_amount = Decimal('0')
            coinbase_reward = Decimal('0')
            fees_sum = Decimal('0')
            seen_tx_in_block = set()

            for tx in block.get('transactions', []):
                try:
                    amount = Decimal(tx['amount'])
                except Exception:
                    return False, f'unparseable amount at block {i}', None
                if not _finite(amount):
                    return False, f'non-finite amount at block {i}', None

                if tx['sender'] == '0':
                    coinbase_count += 1
                    coinbase_amount += amount
                    reported = tx.get('block_reward')
                    coinbase_reward += Decimal(reported) if reported is not None else amount
                    current_balances[tx['recipient']] = current_balances.get(tx['recipient'], Decimal('0')) + amount
                    continue

                if v2:
                    if tx.get('version') != 2:
                        return False, f'v1 transaction in v2 block {i}', None
                    if tx.get('sig_algo', P.SIG_ALGO_DEFAULT) not in P.SIG_ALGOS:
                        return False, f'unknown signature algorithm at block {i}', None
                    if amount <= 0:
                        return False, f'non-positive amount at block {i}', None
                    try:
                        fee = Decimal(tx.get('fee', '0'))
                    except Exception:
                        return False, f'unparseable fee at block {i}', None
                    if not _finite(fee) or fee < P.MIN_TX_FEE:
                        return False, f'fee below minimum at block {i}', None
                    if ArthaWallet.address_from_public_key(tx['public_key_str']) != tx['sender']:
                        return False, f'sender/public-key mismatch at block {i}', None
                    sender = tx['sender']
                    if int(tx.get('nonce', -1)) != nonces.get(sender, 0):
                        return False, f'bad nonce at block {i}', None
                    if current_balances.get(sender, Decimal('0')) < amount + fee:
                        return False, f'insufficient balance at block {i}', None
                    if not ArthaWallet.verify_signature(
                        ArthaWallet.v2_signed_payload(tx), tx['public_key_str'], tx['signature']
                    ):
                        return False, f'invalid transaction signature at block {i}', None
                    tx_ts = tx.get('timestamp', 0)
                    # Hanya cek future-drift di sini. Cek past-drift (umur tx)
                    # boleh dilakukan saat tx MASUK mempool (submit_transaction),
                    # tetapi TIDAK boleh di validasi historis: kalau tidak, chain
                    # yang berisi tx tua (> MAX_PAST_DRIFT) jadi "invalid" begitu
                    # file di-copy ke VPS lain atau node di-restart setelah seminggu.
                    if tx_ts > now + P.MAX_FUTURE_DRIFT:
                        return False, f'transaction timestamp too far in future at block {i}', None

                    txid = self._calculate_transaction_id(tx)
                    if txid in seen_tx_in_block:
                        return False, f'double spend in same block {i}', None
                    seen_tx_in_block.add(txid)

                    current_balances[sender] = current_balances.get(sender, Decimal('0')) - amount - fee
                    current_balances[tx['recipient']] = current_balances.get(tx['recipient'], Decimal('0')) + amount
                    nonces[sender] = nonces.get(sender, 0) + 1
                    fees_sum += fee
                else:
                    # Aturan v1: historis, tanpa nonce/fee/binding.
                    sender = tx['sender']
                    current_balances.setdefault(sender, Decimal('0'))
                    if current_balances[sender] < amount:
                        return False, f'insufficient balance at block {i}', None
                    tx_data = {'sender': sender, 'recipient': tx['recipient'], 'amount': tx['amount']}
                    if not ArthaWallet.verify_signature(tx_data, tx['public_key_str'], tx['signature']):
                        return False, f'invalid transaction signature at block {i}', None
                    txid = self._calculate_transaction_id(tx)
                    if txid in seen_tx_in_block:
                        return False, f'double spend in same block {i}', None
                    seen_tx_in_block.add(txid)
                    current_balances[sender] -= amount
                    current_balances[tx['recipient']] = current_balances.get(tx['recipient'], Decimal('0')) + amount

            if coinbase_count > 1:
                return False, f'multiple coinbase transactions at block {i}', None
            if block['index'] > 0:
                expected_reward = self.get_block_reward(block['index'] - 1, total_issued)
                if v2:
                    if abs(coinbase_reward - expected_reward) > P.QUANTUM:
                        return False, f'incorrect coinbase reward at block {i}', None
                    if abs(coinbase_amount - (expected_reward + fees_sum)) > P.QUANTUM:
                        return False, f'incorrect coinbase+fees at block {i}', None
                else:
                    if abs(coinbase_amount - expected_reward) > P.QUANTUM:
                        return False, f'incorrect coinbase reward at block {i}', None
            total_issued += coinbase_reward
            if total_issued > self.TOTAL_SUPPLY + P.QUANTUM:
                return False, f'supply cap exceeded at block {i}', None

        return True, None, (current_balances, total_issued, total_work, nonces)

    # ------------------------------------------------------------------
    # Chain mutation
    # ------------------------------------------------------------------

    def add_block(self, block, persist=True):
        """
        Validate and append a single block that extends the tip.

        persist=False dipakai catch-up batch: caller yang menyimpan chain
        sekali di akhir batch, supaya sinkronisasi tidak menulis ulang seluruh
        file chain untuk tiap blok yang diterima.
        """
        with self.chain_lock:
            last_block = self.last_block
            if not last_block or block.get('previous_hash') != self.hash_block(last_block):
                logger.warning(
                    f'Rejected block #{block.get("index")}: previous_hash tidak cocok '
                    f'(local tip #{self.get_current_block_height()}, '
                    f'block.previous_hash={str(block.get("previous_hash"))[:16]}..., '
                    f'local_tip_hash={self.hash_block(last_block)[:16]}...)'
                    if last_block else 'Rejected block: no local tip'
                )
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
            for tx in block.get('transactions', []):
                if tx.get('sender') != '0':
                    self._confirmed_tx_ids.add(self._calculate_transaction_id(tx))
            self._drop_confirmed_transactions([block])
            if persist:
                self.save_chain()
            logger.debug(f'Block #{block["index"]} appended. Height: {len(self.chain) - 1}')
            return True

    def _drop_confirmed_transactions(self, new_blocks=None):
        """
        Buang tx dari mempool yang sudah masuk chain.

        new_blocks=None : scan seluruh chain (dipakai replace/reorg, jarang).
        new_blocks=[b]  : cukup blok yang baru masuk (dipakai add_block).
        """
        blocks = self.chain if new_blocks is None else new_blocks
        confirmed_ids = set()
        for block in blocks:
            for tx in block.get('transactions', []):
                if tx.get('sender') != '0':
                    confirmed_ids.add(self._calculate_transaction_id(tx))
        if not confirmed_ids:
            return
        remaining = [
            tx for tx in self.pending_transactions
            if self._calculate_transaction_id(tx) not in confirmed_ids
        ]
        if len(remaining) != len(self.pending_transactions):
            self.pending_transactions = remaining
            self.known_pending_tx_hashes = {
                self._calculate_transaction_id(tx) for tx in remaining
            }

    def _outranks_current(self, new_chain):
        """Longer wins; ties broken by total work, then tip hash (deterministic)."""
        new_len, cur_len = len(new_chain), len(self.chain)
        if new_len != cur_len:
            return new_len > cur_len

        new_tip = self.hash_block(new_chain[-1])
        cur_tip = self.hash_block(self.chain[-1])
        if new_tip == cur_tip:
            return False

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
            confirmed_in_new = set()
            for block in new_chain:
                for tx in block.get('transactions', []):
                    if tx.get('sender') != '0':
                        confirmed_in_new.add(self._calculate_transaction_id(tx))

            orphan_txs = []
            for block in old_chain:
                for tx in block.get('transactions', []):
                    if tx.get('sender') != '0':
                        tx_id = self._calculate_transaction_id(tx)
                        if tx_id not in confirmed_in_new:
                            orphan_txs.append(tx)

            if not orphan_txs:
                return

            existing_ids = set(self.known_pending_tx_hashes)
            added = 0
            for tx in orphan_txs:
                tx_id = self._calculate_transaction_id(tx)
                if tx_id not in existing_ids and len(self.pending_transactions) < P.MAX_MEMPOOL_TXS:
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

    def replace_chain(self, new_chain, force=False):
        """
        Adopt a chain received from a peer when it outranks ours.

        force=True dipakai saat mengadopsi genesis peer pada node fresh
        (height 0, genesis lokal buatan sendiri yang ternyata beda dengan
        jaringan). Saat itu chain lokal tidak "kalah" secara panjang, tapi
        tetap harus diganti supaya blok berikutnya bisa nyambung.
        """
        with self.chain_lock:
            if not new_chain:
                return False

            old_height = self.get_current_block_height()
            new_height = len(new_chain) - 1
            reorg_depth = old_height - new_height if new_height < old_height else 0
            if reorg_depth > self.max_reorg_depth:
                logger.warning(f'Rejecting deep reorg attempt: depth {reorg_depth} > max {self.max_reorg_depth}')
                return False

            if not force and not self._outranks_current(new_chain):
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
            self._reindex_confirmed_tx_ids()
            self._drop_confirmed_transactions()
            self._restore_orphaned_transactions(old_chain, self.chain)
            self.save_chain()
            logger.info(f'Chain reorg completed: new tip #{self.last_block["index"]} (old {old_height})')
            return True

    def invalidate_last_blocks(self, n=1):
        """Rewind chain by n blocks, restoring orphaned txs to mempool."""
        if n < 1:
            return False
        with self.chain_lock:
            if len(self.chain) <= 1:
                return False
            n = min(n, len(self.chain) - 1)
            old_chain = list(self.chain)
            new_chain = old_chain[:-n]
            ok, reason, state = self._validate_chain(new_chain)
            if not ok:
                logger.warning(f'Cannot invalidate last {n} blocks: {reason}')
                return False
            self.chain = new_chain
            self._state_cache = state
            self._reindex_confirmed_tx_ids()
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
