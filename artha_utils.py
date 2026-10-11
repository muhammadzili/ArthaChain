# artha_utils.py

import hashlib
import json
import os
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# --- PERBAIKAN: Menambahkan custom JSON encoder untuk tipe Decimal ---
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super(DecimalEncoder, self).default(obj)

# Registry algoritma hash. Menambah entri di sini (plus aktivasi height di
# artha_protocol.py) adalah cara mengganti hash tanpa bongkar arsitektur.
_HASHERS = {
    'sha256': hashlib.sha256,
    'sha3_256': hashlib.sha3_256,
}


def hash_data(data, algo='sha256'):
    """
    Hash `data` (bytes atau str) dengan algoritma yang dipilih.

    Default sha256 agar seluruh chain lama dan pemanggil lama tetap kompatibel.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    hasher = _HASHERS.get(algo)
    if hasher is None:
        raise ValueError(f"Algoritma hash tidak dikenal: {algo}")
    return hasher(data).hexdigest()

def json_serialize(data):
    """
    Converts a Python object into a consistent JSON string, handling Decimals.
    """
    return json.dumps(data, sort_keys=True, cls=DecimalEncoder).encode('utf-8')

def get_data_dir():
    """
    Returns the data directory path for ArthaChain.
    """
    home_dir = os.path.expanduser("~")
    artha_dir = os.path.join(home_dir, ".artha_chain")
    os.makedirs(artha_dir, exist_ok=True)
    return artha_dir

def save_json_file(filename, data):
    """
    Saves Python data to a JSON file.
    """
    filepath = os.path.join(get_data_dir(), filename)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4, cls=DecimalEncoder)
    logger.debug(f"File '{filename}' successfully saved.") 

def load_json_file(filename):
    """
    Loads JSON data from a file.
    """
    filepath = os.path.join(get_data_dir(), filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load or parse JSON file {filename}: {e}")
            return None
    return None
