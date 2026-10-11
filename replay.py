import time
import unittest
from decimal import Decimal
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
import artha_protocol as P


class TestArthaChainSecurity(unittest.TestCase):

    def setUp(self):
        self.blockchain = ArthaBlockchain(blockchain_file='test_blockchain.json')
        self.wallet_sender = ArthaWallet(password='testpass123', wallet_file='test_wallet_sender.dat')
        self.wallet_recipient = ArthaWallet(password='testpass123', wallet_file='test_wallet_recipient.dat')

        # Berikan saldo awal ke pengirim untuk keperluan testing.
        # _state_cache sekarang 4-tuple: (balances, total_issued, total_work, nonces)
        sender_addr = self.wallet_sender.get_public_address()
        if self.blockchain._state_cache is None:
            self.blockchain._warm_cache()
        balances = self.blockchain._state_cache[0]
        balances[sender_addr] = Decimal('50.00000000')

    def test_transaction_replay_vulnerability(self):
        sender_addr = self.wallet_sender.get_public_address()
        recipient_addr = self.wallet_recipient.get_public_address()

        amount = Decimal('1.00000000')
        canonical_amount_str = "{:.8f}".format(amount)

        transaction_data = {
            'sender': sender_addr,
            'recipient': recipient_addr,
            'amount': canonical_amount_str
        }

        signature = self.wallet_sender.sign_transaction(transaction_data)
        pub_key_str = self.wallet_sender.public_key.export_key().decode('utf-8')

        # Timestamp dipatok agar kedua transaksi benar-benar byte-identik
        # (pada v1 timestamp tidak ditandatangani; lihat catatan di bawah).
        tx = {
            'sender': sender_addr,
            'recipient': recipient_addr,
            'amount': canonical_amount_str,
            'timestamp': time.time(),
            'signature': signature,
            'public_key_str': pub_key_str,
        }

        tx1 = self.blockchain.submit_transaction(dict(tx))
        self.assertIsNotNone(tx1, "Transaksi pertama harus berhasil.")

        # Duplikasi / replay byte-identik harus ditolak (dedupe transaction_id).
        tx_replay = self.blockchain.submit_transaction(dict(tx))
        self.assertIsNone(tx_replay, "Replay transaksi identik harus ditolak.")

        # Catatan: pada wilayah v1 timestamp tidak ikut ditandatangani, sehingga
        # penyerang bisa mengubah timestamp untuk lolos dedupe. Itulah alasannya
        # aturan v2 (nonce + timestamp tertandatangani) diaktifkan di height v2;
        # lihat test_v2_nonce_replay_rejected.

    def test_v2_nonce_replay_rejected(self):
        """Nonce membuat dua transaksi berbeda tidak bisa saling menggantikan."""
        recipient_addr = self.wallet_recipient.get_public_address()

        tx1 = self.wallet_sender.build_transaction(
            recipient_addr, Decimal('1.0'), P.MIN_TX_FEE, nonce=0
        )
        self.assertIsNotNone(
            self.blockchain.submit_transaction(tx1),
            "Transaksi v2 pertama (nonce 0) harus masuk mempool."
        )

        # Nonce harus naik menjadi 1 setelah tx tertunda di mempool.
        self.assertEqual(self.blockchain.get_next_nonce(self.wallet_sender.address), 1)

        # Transaksi berbeda dengan nonce lama (0) harus ditolak.
        tx_stale = self.wallet_sender.build_transaction(
            recipient_addr, Decimal('2.0'), P.MIN_TX_FEE, nonce=0
        )
        self.assertIsNone(
            self.blockchain.submit_transaction(tx_stale),
            "Transaksi dengan nonce yang sudah terpakai harus ditolak."
        )

    def tearDown(self):
        for f in ['test_blockchain.json', 'test_wallet_sender.dat', 'test_wallet_recipient.dat']:
            try:
                import os
                os.remove(os.path.join(os.path.expanduser("~"), ".artha_chain", f))
            except OSError:
                pass


if __name__ == '__main__':
    unittest.main()
