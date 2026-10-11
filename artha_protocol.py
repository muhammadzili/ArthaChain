# artha_protocol.py
"""
Pusat parameter protokol, activation height, dan algorithm agility ArthaChain.

Prinsip "jangan hard fork lagi":
  Setiap perubahan aturan konsensus WAJIB di-gate oleh absolute block height
  (activation height). Blok di bawah activation divalidasi dengan aturan yang
  berlaku saat blok itu ditambang; blok >= activation memakai aturan baru.
  Jadi kita bisa upgrade block time, fee, replay protection, atau algoritma
  hash/tanda tangan TANPA membuang chain yang sudah ada.

  Cara menambah versi baru di masa depan:
    1. Tambah konstanta ACTIVATION_V3 = <height>.
    2. Tambah helper is_v3()/target_block_time()/dst.
    3. Tambah tag algoritma baru ke HASH_ALGOS/SIG_ALGOS.
    4. Update artha_blockchain._validate_chain untuk bercabang di is_v3().
  Blok lama tetap aman karena aturannya tidak berubah.
"""
from decimal import Decimal

# --- identitas jaringan & versi ---
CHAIN_ID = 'arthachain-1'
PROTOCOL_VERSION = 2
NODE_VERSION = '2.4'          # versi rilis perangkat lunak (bukan versi protokol)

# Absolute block height tempat aturan v2 mulai berlaku. SEMUA node wajib
# memakai nilai yang sama. Set = tinggi blok berikutnya saat upgrade.
# CATATAN: chain sudah melewati 19200 (tip saat upgrade = 21307) dan blok
# 19200..21307 ditambang dengan aturan v1. Karena itu aktivasi digeser ke
# atas tip agar blok historis tetap divalidasi dengan aturan v1.
ACTIVATION_V2 = 21350

# --- kebijakan moneter ---
DECIMALS = 8
QUANTUM = Decimal('0.00000001')
TOTAL_SUPPLY = Decimal('21000000')
BLOCK_REWARD_BASE = Decimal('50')
HALVING_INTERVAL = 210000
GENESIS_DIFFICULTY = 200000

# --- penjadwalan blok ---
TARGET_BLOCK_TIME_V1 = 60
TARGET_BLOCK_TIME_V2 = 180          # 3 menit per blok sejak v2
DIFFICULTY_ADJUSTMENT_INTERVAL = 10
MIN_DIFFICULTY_V2 = 100000          # lantai agar difficulty tidak jatuh ke 1
MAX_REORG_DEPTH = 100

# --- batas ukuran (v2) ---
MAX_TXS_PER_BLOCK = 2000
MAX_BLOCK_BYTES = 1_000_000
MAX_MEMPOOL_TXS = 10000
MAX_MESSAGE_BYTES = 9_000_000       # harus >= MAX_CHAIN_RESPONSE_BYTES + overhead
MAX_BUFFER_BYTES = 12_000_000
MAX_BLOCKS_PER_RESPONSE = 500
MAX_CHAIN_RESPONSE_BYTES = 8_000_000
MAX_TX_RELAY_BYTES = 100_000        # batas payload NEW_TRANSACTION yang direlai
MAX_FUTURE_DRIFT = 120              # detik; tx/blok maksimal di depan "sekarang"
MAX_PAST_DRIFT = 7 * 24 * 3600      # umur maksimal tx saat diterima

# --- fee (v2) ---
MIN_TX_FEE = Decimal('0.00010000')

# --- algorithm agility ---
# Nama algoritma yang DITERIMA pada blok/transaksi. Menambah nama baru di sini
# (bersamaan dengan aktivasi height) membuat swap algoritma di masa depan
# menjadi upgrade terjadwal, bukan bongkar ulang.
HASH_ALGO_DEFAULT = 'sha256'
SIG_ALGO_DEFAULT = 'rsa-pkcs1v15-sha256'
HASH_ALGOS = ('sha256', 'sha3_256')
SIG_ALGOS = ('rsa-pkcs1v15-sha256',)


def is_v2(height):
    """True bila aturan v2 berlaku untuk blok pada index `height`."""
    try:
        return int(height) >= ACTIVATION_V2
    except (TypeError, ValueError):
        return False


def target_block_time(height):
    return TARGET_BLOCK_TIME_V2 if is_v2(height) else TARGET_BLOCK_TIME_V1


def min_difficulty(height):
    return MIN_DIFFICULTY_V2 if is_v2(height) else 1


def hash_algo_for(height):
    return HASH_ALGO_DEFAULT


def sig_algo_for(height):
    return SIG_ALGO_DEFAULT
