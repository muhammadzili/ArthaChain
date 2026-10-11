# artha_wallet.py

import os
import time
import logging
from decimal import Decimal
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import scrypt
from Crypto.Cipher import AES
import json

from artha_utils import hash_data, json_serialize, get_data_dir
import artha_protocol as P

logger = logging.getLogger(__name__)

# Tag algoritma yang disimpan di file dompet. Kalau nanti scrypt/AES dianggap
# lemah, kita bisa migrasi ke (mis. 'argon2id' / 'chacha20-poly1305') lewat
# versi baru tanpa mengubah format file untuk dompet lama.
WALLET_FILE_VERSION = 2
KDF_DEFAULT = 'scrypt'
CIPHER_DEFAULT = 'aes-256-gcm'


class ArthaWallet:
    def __init__(self, wallet_file='wallet.dat', password=None):
        self.wallet_file = wallet_file

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

                version = int(wallet_data.get('version', 1))
                kdf = wallet_data.get('kdf', KDF_DEFAULT)
                cipher_name = wallet_data.get('cipher', CIPHER_DEFAULT)

                if kdf != 'scrypt' or cipher_name != 'aes-256-gcm':
                    raise ValueError(f"Algoritma dompet tidak didukung: {kdf}/{cipher_name}")

                salt = bytes.fromhex(wallet_data['salt'])
                nonce = bytes.fromhex(wallet_data['nonce'])
                tag = bytes.fromhex(wallet_data.get('tag', ''))
                ciphertext = bytes.fromhex(wallet_data['ciphertext'])

                key = self._derive_key(password, salt, kdf)
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                private_key_pem = cipher.decrypt_and_verify(ciphertext, tag)

                self.private_key = RSA.import_key(private_key_pem)
                self.public_key = self.private_key.publickey()
                self.address = self._get_address_from_public_key(self.public_key.export_key().decode('utf-8'))
                logger.info(f"Wallet loaded successfully (v{version}) for address: {self.address}")
            except (ValueError, KeyError, TypeError) as e:
                logger.error(f"Failed to load wallet. Incorrect password or corrupted file: {e}")
                raise ValueError("Incorrect password or corrupted wallet file.")
        else:
            logger.info("Wallet file not found. Creating a new encrypted wallet...")
            self._generate_new_wallet(password)

    @staticmethod
    def _derive_key(password, salt, kdf='scrypt'):
        if kdf != 'scrypt':
            raise ValueError(f"KDF tidak didukung: {kdf}")
        return scrypt(password.encode('utf-8'), salt, 32, N=2**14, r=8, p=1)

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
        Menyimpan private key ke file, dienkripsi dengan password (AES-GCM + scrypt).
        Ditandai version/kdf/cipher agar bisa dimigrasi di masa depan.
        """
        private_key_pem = self.private_key.export_key('PEM')
        salt = os.urandom(16)
        key = self._derive_key(password, salt, KDF_DEFAULT)
        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(private_key_pem)

        wallet_data = {
            'version': WALLET_FILE_VERSION,
            'kdf': KDF_DEFAULT,
            'cipher': CIPHER_DEFAULT,
            'salt': salt.hex(),
            'nonce': cipher.nonce.hex(),
            'tag': tag.hex(),
            'ciphertext': ciphertext.hex()
        }

        filepath = os.path.join(get_data_dir(), self.wallet_file)
        with open(filepath, 'w') as f:
            json.dump(wallet_data, f, indent=4)
        logger.info("Wallet saved securely.")

    @staticmethod
    def _get_address_from_public_key(public_key_str):
        return hash_data(public_key_str.encode('utf-8'))

    @staticmethod
    def address_from_public_key(public_key_str):
        """Alamat = SHA256(PEM public key). Dipakai untuk cek sender == pubkey."""
        return hash_data(public_key_str.encode('utf-8'))

    def get_public_address(self):
        return self.address

    def sign_payload(self, payload):
        """Tanda tangani dict apa pun yang bisa diserialkan kanonik (v2)."""
        if not self.private_key:
            raise ValueError("Private key not available for signing.")
        tx_hash = SHA256.new(json_serialize(payload))
        signer = pkcs1_15.new(self.private_key)
        return signer.sign(tx_hash).hex()

    def sign_transaction(self, transaction_data):
        """Kompatibel dengan v1: tanda tangani dict transaksi apa adanya."""
        return self.sign_payload(transaction_data)

    @staticmethod
    def v2_signed_payload(tx):
        """
        Bentuk kanonik yang DITANDATANGANI pada v2. Harus identik antara
        penandatangan (wallet) dan pemverifikasi (blockchain) supaya tidak ada
        malleability. `timestamp`, `nonce`, `fee`, dan `chain_id` ikut ditutup
        tanda tangan -> replay/double-spend di jaringan tertutup.
        """
        return {
            'version': int(tx.get('version', 2)),
            'chain_id': tx.get('chain_id', P.CHAIN_ID),
            'sender': tx['sender'],
            'recipient': tx['recipient'],
            'amount': tx['amount'],
            'fee': tx.get('fee', '0.00000000'),
            'nonce': int(tx.get('nonce', 0)),
            'timestamp': tx.get('timestamp'),
        }

    def build_transaction(self, recipient, amount, fee, nonce, timestamp=None):
        """
        Bangun transaksi v2 yang sudah ditandatangani, siap disiarkan.
        `amount`/`fee` boleh Decimal/str; dikonversi ke string kanonik 8 desimal.
        """
        amount_str = "{:.8f}".format(Decimal(amount))
        fee_str = "{:.8f}".format(Decimal(fee))
        tx = {
            'version': 2,
            'chain_id': P.CHAIN_ID,
            'sender': self.address,
            'recipient': recipient,
            'amount': amount_str,
            'fee': fee_str,
            'nonce': int(nonce),
            'timestamp': time.time() if timestamp is None else timestamp,
            'sig_algo': P.SIG_ALGO_DEFAULT,
        }
        tx['signature'] = self.sign_payload(ArthaWallet.v2_signed_payload(tx))
        tx['public_key_str'] = self.public_key.export_key().decode('utf-8')
        return tx

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
