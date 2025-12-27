# artha_wallet.py

import os
import logging
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import scrypt
from Crypto.Cipher import AES
import json

from artha_utils import hash_data, json_serialize, get_data_dir

logger = logging.getLogger(__name__)

class ArthaWallet:
    def __init__(self, wallet_file='wallet.dat', password=None):
        self.wallet_file = wallet_file
        self.private_key = None
        self.public_key = None
        self.address = None

        if not password:
            raise ValueError("Password is required to load or create a wallet.")

        self._load_or_create_wallet(password)

    def _load_or_create_wallet(self, password):
        """
        Memuat dompet dari file terenkripsi atau membuat yang baru.
        """
        wallet_path = os.path.join(get_data_dir(), self.wallet_file)
        if os.path.exists(wallet_path):
            try:
                with open(wallet_path, 'r') as f:
                    wallet_data = json.load(f)
                
                # Dekripsi private key
                salt = bytes.fromhex(wallet_data['salt'])
                nonce = bytes.fromhex(wallet_data['nonce'])
                tag = bytes.fromhex(wallet_data['tag'])
                ciphertext = bytes.fromhex(wallet_data['ciphertext'])

                key = scrypt(password.encode('utf-8'), salt, 32, N=2**14, r=8, p=1)
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                private_key_pem = cipher.decrypt_and_verify(ciphertext, tag)
                
                self.private_key = RSA.import_key(private_key_pem)
                self.public_key = self.private_key.publickey()
                self.address = self._get_address_from_public_key(self.public_key.export_key().decode('utf-8'))
                logger.info(f"Wallet loaded successfully for address: {self.address}")
            except (ValueError, KeyError, TypeError) as e:
                logger.error(f"Failed to load wallet. Incorrect password or corrupted file: {e}")
                raise ValueError("Incorrect password or corrupted wallet file.")
        else:
            logger.info("Wallet file not found. Creating a new encrypted wallet...")
            self._generate_new_wallet(password)

    def _generate_new_wallet(self, password):
        """
        Membuat pasangan kunci baru dan menyimpannya dalam format terenkripsi.
        """
        key = RSA.generate(2048)
        self.private_key = key
        self.public_key = key.publickey()
        self.address = self._get_address_from_public_key(self.public_key.export_key().decode('utf-8'))
        self._save_wallet(password)
        logger.info(f"New wallet created! Your address: {self.address}")

    def _save_wallet(self, password):
        """
        Menyimpan private key ke file, dienkripsi dengan password menggunakan AES-GCM.
        """
        private_key_pem = self.private_key.export_key('PEM')
        salt = os.urandom(16)
        key = scrypt(password.encode('utf-8'), salt, 32, N=2**14, r=8, p=1)
        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(private_key_pem)

        wallet_data = {
            'salt': salt.hex(),
            'nonce': cipher.nonce.hex(),
            'tag': tag.hex(),
            'ciphertext': ciphertext.hex()
        }
        
        filepath = os.path.join(get_data_dir(), self.wallet_file)
        with open(filepath, 'w') as f:
            json.dump(wallet_data, f, indent=4)
        logger.info("Wallet saved securely.")

    def _get_address_from_public_key(self, public_key_str):
        return hash_data(public_key_str.encode('utf-8'))

    def get_public_address(self):
        return self.address

    def sign_transaction(self, transaction_data):
        if not self.private_key:
            raise ValueError("Private key not available for signing.")
        
        tx_hash = SHA256.new(json_serialize(transaction_data))
        signer = pkcs1_15.new(self.private_key)
        return signer.sign(tx_hash).hex()

    @staticmethod
    def verify_signature(transaction_data, public_key_str, signature_hex):
        try:
            public_key = RSA.import_key(public_key_str)
            tx_hash = SHA256.new(json_serialize(transaction_data))
            pkcs1_15.new(public_key).verify(tx_hash, bytes.fromhex(signature_hex))
            return True
        except (ValueError, TypeError):
            logger.debug("Signature verification failed.")
            return False
