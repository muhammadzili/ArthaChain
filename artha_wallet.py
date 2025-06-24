# artha_wallet.py

from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
import os
import logging # Import logging
from artha_utils import hash_data, json_serialize, get_data_dir, save_json_file, load_json_file

logger = logging.getLogger(__name__) # Logger for this module

class ArthaWallet:
    def __init__(self, wallet_file='wallet.dat'):
        self.wallet_file = wallet_file
        self.private_key = None
        self.public_key = None
        self.address = None
        self._load_or_create_wallet()

    def _load_or_create_wallet(self):
        """
        Loads the wallet from a file or creates a new one if it doesn't exist.
        """
        wallet_data = load_json_file(self.wallet_file)
        if wallet_data:
            try:
                self.private_key = RSA.import_key(wallet_data['private_key'])
                self.public_key = RSA.import_key(wallet_data['public_key'])
                self.address = wallet_data['address']
                logger.info(f"Wallet loaded from '{self.wallet_file}'. Your address: {self.address}")
            except (ValueError, KeyError) as e:
                logger.warning(f"Error loading wallet: {e}. Creating a new wallet.")
                self._generate_new_wallet()
        else:
            logger.info("Wallet file not found. Creating a new wallet...")
            self._generate_new_wallet()

    def _generate_new_wallet(self):
        """
        Generates a new RSA key pair and saves it.
        """
        key = RSA.generate(2048) # Generate a 2048-bit key
        self.private_key = key
        self.public_key = key.publickey()
        self.address = self._get_address_from_public_key(self.public_key.export_key().decode('utf-8'))
        self._save_wallet()
        logger.info(f"New wallet successfully created! Your address: {self.address}")

    def _save_wallet(self):
        """
        Saves the private and public keys to the wallet file.
        """
        wallet_data = {
            'private_key': self.private_key.export_key().decode('utf-8'),
            'public_key': self.public_key.export_key().decode('utf-8'),
            'address': self.address
        }
        save_json_file(self.wallet_file, wallet_data)

    def _get_address_from_public_key(self, public_key_str):
        """
        Derives an address from a public key (SHA256 hash of the public key).
        """
        return hash_data(public_key_str.encode('utf-8'))

    def get_public_address(self):
        """
        Returns the public address of this wallet.
        """
        return self.address

    def sign_transaction(self, transaction_data):
        """
        Signs the transaction data using the private key.
        transaction_data is the transaction dictionary before hashing.
        """
        if not self.private_key:
            raise ValueError("Private key not available for signing.")

        # Hash the transaction before signing
        tx_hash = SHA256.new(json_serialize(transaction_data))
        signer = pkcs1_15.new(self.private_key)
        signature = signer.sign(tx_hash)
        return signature.hex() # Return the signature in hex format

    @staticmethod
    def verify_signature(transaction_data, public_key_str, signature_hex):
        """
        Verifies a transaction signature using the public key.
        transaction_data is the transaction dictionary before hashing.
        public_key_str is the sender's public key in string format.
        signature_hex is the signature in hex format.
        """
        try:
            public_key = RSA.import_key(public_key_str)
            tx_hash = SHA256.new(json_serialize(transaction_data))
            verifier = pkcs1_15.new(public_key)
            verifier.verify(tx_hash, bytes.fromhex(signature_hex))
            return True
        except (ValueError, TypeError):
            # Invalid signature or wrong key
            logger.debug("Signature verification failed: Invalid format or mismatch.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error verifying signature: {e}")
            return False

