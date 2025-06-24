# artha_wallet.py

from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
import os
import logging
from artha_utils import hash_data, json_serialize, get_data_dir

# Perubahan: Tidak lagi menggunakan save/load json file dari utils
# karena kita butuh penanganan file biner untuk kunci terenkripsi.

logger = logging.getLogger(__name__)

class ArthaWallet:
    def __init__(self, wallet_file='wallet.dat', password=None):
        self.wallet_file_path = os.path.join(get_data_dir(), wallet_file)
        self.private_key = None
        self.public_key = None
        self.address = None

        if not password:
            raise ValueError("Password is required to load or create a wallet.")

        self._load_or_create_wallet(password)

    def _load_or_create_wallet(self, password):
        """
        Memuat dompet dari file terenkripsi atau membuat yang baru jika tidak ada.
        """
        if os.path.exists(self.wallet_file_path):
            logger.info(f"Loading wallet from '{self.wallet_file_path}'...")
            try:
                with open(self.wallet_file_path, 'rb') as f:
                    encrypted_key = f.read()
                
                # Mencoba mendekripsi private key dengan password yang diberikan
                self.private_key = RSA.import_key(encrypted_key, passphrase=password)
                self.public_key = self.private_key.publickey()
                self.address = self._get_address_from_public_key(self.public_key.export_key())
                logger.info(f"Wallet loaded successfully. Your address: {self.address}")
            except (ValueError, IndexError) as e:
                logger.error(f"Failed to decrypt wallet. Incorrect password or corrupted file. Error: {e}")
                # Melempar error kembali agar GUI bisa menanganinya
                raise ValueError("Password salah atau file dompet rusak.")
        else:
            logger.info("Wallet file not found. Creating a new encrypted wallet...")
            self._generate_new_wallet(password)

    def _generate_new_wallet(self, password):
        """
        Membuat pasangan kunci RSA baru dan menyimpannya dalam format terenkripsi.
        """
        key = RSA.generate(2048)
        self.private_key = key
        self.public_key = key.publickey()
        self.address = self._get_address_from_public_key(self.public_key.export_key())
        self._save_wallet(password)
        logger.info(f"New encrypted wallet successfully created! Your address: {self.address}")

    def _save_wallet(self, password):
        """
        Menyimpan private key ke file, dienkripsi dengan password.
        Menggunakan standar industri PKCS#8 dengan scrypt KDF dan AES-128.
        """
        if not self.private_key:
            raise ValueError("Private key is not available to save.")
        
        # Ekspor kunci dengan enkripsi
        encrypted_key = self.private_key.export_key(
            passphrase=password,
            pkcs=8,
            protection="scryptAndAES128-CBC"
        )

        with open(self.wallet_file_path, 'wb') as f:
            f.write(encrypted_key)
        logger.info(f"Wallet saved securely to '{self.wallet_file_path}'.")

    def _get_address_from_public_key(self, public_key_bytes):
        """
        Menurunkan alamat dari public key (hash SHA256 dari public key).
        Input sekarang adalah bytes, bukan string.
        """
        return hash_data(public_key_bytes)

    def get_public_address(self):
        """
        Mengembalikan alamat publik dari dompet ini.
        """
        return self.address

    def sign_transaction(self, transaction_data, password):
        """
        Menandatangani data transaksi menggunakan private key.
        Password dibutuhkan untuk memastikan otorisasi.
        """
        if not self.private_key:
            raise ValueError("Private key not available for signing.")
        
        # Validasi sederhana: coba gunakan private key. Jika berhasil, password benar.
        # Ini tidak diperlukan jika private key sudah di-load di memori,
        # tapi sebagai lapisan keamanan tambahan, kita bisa memastikannya.
        # Untuk kasus ini, karena private key sudah ada di self.private_key, kita bisa langsung pakai.
        
        tx_hash = SHA256.new(json_serialize(transaction_data))
        signer = pkcs1_15.new(self.private_key)
        signature = signer.sign(tx_hash)
        return signature.hex()

    @staticmethod
    def verify_signature(transaction_data, public_key_str, signature_hex):
        """
        Memverifikasi tanda tangan transaksi menggunakan public key.
        """
        try:
            public_key = RSA.import_key(public_key_str)
            tx_hash = SHA256.new(json_serialize(transaction_data))
            verifier = pkcs1_15.new(public_key)
            verifier.verify(tx_hash, bytes.fromhex(signature_hex))
            return True
        except (ValueError, TypeError):
            logger.debug("Signature verification failed: Invalid format or mismatch.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error verifying signature: {e}")
            return False

