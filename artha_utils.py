# artha_utils.py

import hashlib
import json
import os
import logging

logger = logging.getLogger(__name__)

def hash_data(data):
    return hashlib.sha256(data).hexdigest()

def json_serialize(data):
    return json.dumps(data, sort_keys=True).encode('utf-8')

def get_data_dir():
    home_dir = os.path.expanduser("~")
    artha_dir = os.path.join(home_dir, ".artha_chain")
    os.makedirs(artha_dir, exist_ok=True)
    return artha_dir

def save_json_file(filename, data):
    filepath = os.path.join(get_data_dir(), filename)
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)
        logger.debug(f"File '{filename}' saved in {get_data_dir()}") 
    except Exception as e:
        logger.error(f"Failed to save JSON file {filename}: {e}")

def load_json_file(filename):
    filepath = os.path.join(get_data_dir(), filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load or parse JSON file {filename}: {e}")
            return None
    return None

