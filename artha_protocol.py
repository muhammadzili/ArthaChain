# artha_protocol.py
"""
Pusat parameter protokol, activation height, algorithm agility, dan PROFIL
JARINGAN ArthaChain.

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

PROFIL JARINGAN:
  Pilih lewat environment variable ARTHA_NETWORK = mainnet | devnet | localnet
  (default: mainnet). Setiap profil punya chain_id, folder data, port, dan
  parameter konsensus sendiri sehingga tidak pernah saling silang.

    mainnet  -> chain produksi (arthachain-1), data di ~/.artha_chain
    devnet   -> chain uji, data di ~/.artha_chain/devnet
    localnet -> simulasi kilat isolasi total, data di ~/.artha_chain/localnet

  Untuk menjalankan BANYAK wallet di satu PC, pilih network lalu override
  folder data tiap instance lewat ARTHA_DATADIR, contoh:

    ARTHA_NETWORK=devnet ARTHA_DATADIR=~/.artha_dev/w1 python3 artha_miner.py 6001
    ARTHA_NETWORK=devnet ARTHA_DATADIR=~/.artha_dev/w2 python3 artha_app.py 6002
"""
import os
from decimal import Decimal

# --- pemilihan jaringan (profil) ---
NETWORK = os.environ.get('ARTHA_NETWORK', 'mainnet').strip().lower()

# Parameter konsensus per jaringan. `activation_v2 = 0` berarti aturan v2 aktif
# sejak blok pertama (chain dev bisa langsung pakai fee/nonce). `min_difficulty`
# kecil supaya mining devnet/localnet cepat.
NETWORKS = {
    'mainnet': {
        'chain_id': 'arthachain-1',
        'data_subdir': '',
        'activation_v2': 21350,
        'target_block_time_v1': 60,
        'target_block_time_v2': 180,
        'min_difficulty_v2': 100000,
        'genesis_difficulty': 200000,
        'default_miner_port': 5001,
        'default_app_port': 5000,
        'default_gui_port': 5002,
        'bootstrap_peers': [],
        'discovery_enabled': True,
        'gist_url': "https://gist.githubusercontent.com/muhammadzili/19fbb07822977ada20ef98cd3e5638c4/raw/c2e47995f7867427bf46a1bb1a3494ebea27a450/node.json",
    },
    'devnet': {
        'chain_id': 'arthachain-devnet',
        'data_subdir': 'devnet',
        'activation_v2': 0,
        'target_block_time_v1': 15,
        'target_block_time_v2': 15,
        'min_difficulty_v2': 1000,
        'genesis_difficulty': 1000,
        'default_miner_port': 6001,
        'default_app_port': 6000,
        'default_gui_port': 6002,
        'bootstrap_peers': ['127.0.0.1:6001'],
        'discovery_enabled': False,
        'gist_url': None,
    },
    'localnet': {
        'chain_id': 'arthachain-local',
        'data_subdir': 'localnet',
        'activation_v2': 0,
        'target_block_time_v1': 5,
        'target_block_time_v2': 5,
        'min_difficulty_v2': 1,
        'genesis_difficulty': 1,
        'default_miner_port': 7001,
        'default_app_port': 7000,
        'default_gui_port': 7002,
        'bootstrap_peers': ['127.0.0.1:7001'],
        'discovery_enabled': False,
        'gist_url': None,
    },
}

if NETWORK not in NETWORKS:
    NETWORK = 'mainnet'
_PROFILE = NETWORKS[NETWORK]

# --- identitas jaringan & versi ---
CHAIN_ID = _PROFILE['chain_id']
PROTOCOL_VERSION = 2
NODE_VERSION = '2.4'          # versi rilis perangkat lunak (bukan versi protokol)

# Folder data relatif terhadap ~/.artha_chain (kosong = root mainnet).
DATA_SUBDIR = _PROFILE['data_subdir']

# Absolute block height tempat aturan v2 mulai berlaku. SEMUA node dalam satu
# jaringan wajib memakai nilai yang sama.
# CATATAN mainnet: chain sudah melewati 19200 (tip saat upgrade = 21307) dan
# blok 19200..21307 ditambang dengan aturan v1, karena itu aktivasi digeser ke
# atas tip agar blok historis tetap divalidasi dengan aturan v1.
ACTIVATION_V2 = _PROFILE['activation_v2']

# --- kebijakan moneter ---
DECIMALS = 8
QUANTUM = Decimal('0.00000001')
TOTAL_SUPPLY = Decimal('21000000')
BLOCK_REWARD_BASE = Decimal('50')
HALVING_INTERVAL = 210000
GENESIS_DIFFICULTY = _PROFILE['genesis_difficulty']

# --- penjadwalan blok ---
TARGET_BLOCK_TIME_V1 = _PROFILE['target_block_time_v1']
TARGET_BLOCK_TIME_V2 = _PROFILE['target_block_time_v2']
DIFFICULTY_ADJUSTMENT_INTERVAL = 10
MIN_DIFFICULTY_V2 = _PROFILE['min_difficulty_v2']
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

# --- jaringan / peer ---
DEFAULT_MINER_PORT = _PROFILE['default_miner_port']
DEFAULT_APP_PORT = _PROFILE['default_app_port']
DEFAULT_GUI_PORT = _PROFILE['default_gui_port']
BOOTSTRAP_PEERS = list(_PROFILE['bootstrap_peers'])
DISCOVERY_ENABLED = _PROFILE['discovery_enabled']
GIST_URL = _PROFILE['gist_url']

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
