# artha_utils.py

import hashlib
import json
import os

def hash_data(data):
    """
    Generates a SHA256 hash of the given data.
    Used for hashing blocks and transactions.
    """
    return hashlib.sha256(data).hexdigest()

def json_serialize(data):
    """
    Converts a Python object into a consistent JSON string.
    Ensures that the same data always produces the same hash.
    """
    # Using sort_keys=True for consistent key ordering
    return json.dumps(data, sort_keys=True).encode('utf-8')

def get_data_dir():
    """
    Returns the data directory path for ArthaChain.
    This is where wallet.dat and blockchain.json files will be stored.
    """
    home_dir = os.path.expanduser("~")
    artha_dir = os.path.join(home_dir, ".artha_chain")
    os.makedirs(artha_dir, exist_ok=True)
    return artha_dir

# Functions to save and load JSON data to/from files
def save_json_file(filename, data):
    """
    Saves Python data to a JSON file.
    """
    filepath = os.path.join(get_data_dir(), filename)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)
    # Changed to debug level to reduce clutter
    logging.debug(f"File '{filename}' successfully saved in {get_data_dir()}") 

def load_json_file(filename):
    """
    Loads JSON data from a file.
    Returns None if the file is not found.
    """
    filepath = os.path.join(get_data_dir(), filename)
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return None

