# artha_app.py

import time
import logging
import os
import sys
import getpass
import threading
from decimal import Decimal, InvalidOperation
from artha_blockchain import ArthaBlockchain
from artha_wallet import ArthaWallet
from artha_node import ArthaNode
import artha_protocol as P

APP_HOST = '0.0.0.0'
APP_PORT = 5000

def setup_logging(port):
    """Sets up logging to console and a file with a unique name."""
    log_dir = os.path.join(os.path.expanduser("~"), ".artha_chain", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"artha_app_{port}.log")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # Console handler for important messages only
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    root_logger.addHandler(console_handler)

    # File handler for all debug messages
    file_handler = logging.FileHandler(log_file_path, mode='w')
    file_handler.setLevel(logging.DEBUG)
    formatter_file = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter_file)
    root_logger.addHandler(file_handler)
    
    global LOG_FILE_PATH
    LOG_FILE_PATH = log_file_path

def display_menu():
    """Displays the menu options for the user."""
    print("\n" + "="*46)
    print("            ARTHACHAIN MENU")
    print("="*46)
    print("1.  Alamat & Saldo")
    print("2.  Kirim ARTH")
    print("3.  Peer Terhubung")
    print("4.  Tambah Peer Baru")
    print("5.  Hapus Peer")
    print("6.  Daftar Peer Tersimpan")
    print("7.  Status Sinkronisasi")
    print("8.  Lihat Blockchain")
    print("9.  Transaksi Tertunda")
    print("10. Paksa Sinkronisasi Ulang")
    print("11. Lokasi File Log")
    print("12. Keluar")
    print("="*46)

def show_connected_peers(node):
    """Print the peers this node currently has an open connection to."""
    peers = node.get_peer_list()
    if not peers['connected']:
        print("\nTidak ada peer yang terhubung (masih mencoba konek / remote offline).")
        print("Cek menu 'Daftar Peer Tersimpan' (6) untuk melihat peer yang disimpan.")
        print("Gunakan menu 'Tambah Peer Baru' atau tunggu sinkronisasi otomatis.")
        return
    print("\nPeer yang Terhubung:")
    for peer in peers['connected']:
        print(f"- {peer}")

def add_new_peer(node, blockchain=None):
    """Prompt for a peer address and register it."""
    print("\nMasukkan alamat peer dengan format host:port")
    print("Contoh: 127.0.0.1:5001  atau  203.0.113.10:5001")
    peer = input("Alamat peer: ").strip()
    if not peer:
        print("Alamat peer tidak boleh kosong.")
        return

    ok, message = node.add_peer(peer)
    if ok:
        print(message)
        if blockchain is not None:
            sync_blockchain_with_animation(node, blockchain, min_wait=2)
    else:
        print(f"Gagal: {message}")

def sync_blockchain_with_animation(node, blockchain, min_wait=3):
    """
    Checks network height against local height across all connected peers.
    If behind, displays a dynamic progress bar animation with speed & ETA
    until sync is 100% completed and saved to blockchain.json.
    """
    print("\n" + "="*46)
    print("      SINKRONISASI BLOCKCHAIN ARTHACHAIN")
    print("="*46)
    print("[+] Memeriksa height blockchain dengan semua peer...")
    
    # Broadcast PING to all connected peers right away to fetch their true heights
    node.broadcast_message('PING', node._chain_summary())
    # Ask all peers for blocks directly - GET_BLOCKS works for small gaps;
    # we'll escalate to REQUEST_CHAIN only if stuck.
    _height_now = blockchain.get_current_block_height()
    node.request_blocks_from_all_peers(_height_now + 1)
    
    start_check = time.time()
    while time.time() - start_check < min_wait:
        status = node.get_sync_status()
        if status['peers'] > 0 and status['best_known_height'] > status['height']:
            break
        time.sleep(0.5)

    status = node.get_sync_status()
    height = status['height']
    best = status['best_known_height']
    peers_count = status['peers']

    if peers_count == 0:
        print(f"[!] Tidak ada peer yang terhubung saat ini.")
        print(f"    Melanjutkan dengan height lokal (Height: {height}).")
        print("    (Tips: Tambahkan peer di menu 4 jika ingin terhubung ke jaringan).")
        print("="*46 + "\n")
        return True

    if status['in_sync'] and height >= best:
        print(f"[✓] Blockchain Anda sudah SINKRON dengan jaringan! (Height: {height} | Peer: {peers_count})")
        print("="*46 + "\n")
        return True

    total_blocks_to_sync = best - height
    print(f"[⚡] Height lokal: {height} | Target Jaringan: {best} ({total_blocks_to_sync} blok tertinggal)")
    print("[🔄] Mengunduh dan memvalidasi blok...")

    # Matikan sementara console logging agar tidak tercampur dengan animasi
    root_logger = logging.getLogger()
    console_handlers = [
        h for h in root_logger.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]
    for h in console_handlers:
        h.setLevel(logging.CRITICAL)

    initial_height = height
    last_height = height
    last_progress_time = time.time()
    stall_count = 0
    spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    spin_idx = 0
    # Rolling speed window: list of (timestamp, height)
    speed_samples = [(time.time(), initial_height)]
    SPEED_WINDOW = 5.0

    try:
        while True:
            cur_status = node.get_sync_status()
            cur_height = cur_status['height']
            target_height = max(cur_status['best_known_height'], best)
            best = target_height
            now_t = time.time()

            if cur_height > last_height:
                last_height = cur_height
                last_progress_time = now_t
                stall_count = 0
                speed_samples.append((now_t, cur_height))

            # Trim samples di luar window
            speed_samples = [(t, h) for t, h in speed_samples if now_t - t <= SPEED_WINDOW]
            if not speed_samples:
                speed_samples = [(now_t, cur_height)]

            # Hitung speed dari rolling window
            if len(speed_samples) >= 2:
                t0, h0 = speed_samples[0]
                t1, h1 = speed_samples[-1]
                dt = t1 - t0
                speed = (h1 - h0) / dt if dt > 0.1 else 0.0
            else:
                speed = 0.0

            blocks_synced = cur_height - initial_height
            total_target = target_height - initial_height

            if total_target <= 0:
                pct = 100.0
            else:
                pct = min(100.0, max(0.0, (blocks_synced / total_target) * 100.0))

            bar_len = 20
            filled_len = int(bar_len * pct // 100)
            bar = '█' * filled_len + '░' * (bar_len - filled_len)

            remaining_blocks = target_height - cur_height
            if speed > 0.01 and remaining_blocks > 0:
                eta_sec = int(remaining_blocks / speed)
                m, s = divmod(eta_sec, 60)
                eta_str = f"{m:02d}:{s:02d}"
            else:
                eta_str = "--:--"

            sym = spinner[spin_idx % len(spinner)]
            spin_idx += 1

            sys.stdout.write(
                f"\r{sym} Sync: [{bar}] {pct:5.1f}% | "
                f"Blok: {cur_height}/{target_height} | "
                f"Spd: {speed:5.1f} blk/s | "
                f"ETA: {eta_str} | Peer: {cur_status['peers']}  "
            )
            sys.stdout.flush()

            if cur_height >= target_height and cur_status['in_sync']:
                break

            stall_sec = now_t - last_progress_time
            if stall_sec > 2.0 and cur_height < target_height:
                stall_count += 1
                if stall_count % 5 == 0:
                    # Escalate ke full resync setelah ~10 detik stuck
                    node.trigger_full_resync()
                else:
                    node.request_blocks_from_all_peers(cur_height + 1)
                last_progress_time = now_t

            time.sleep(0.15)

        sys.stdout.write(f"\r[✓] Sync: [{'█'*bar_len}] 100.0% | Blok: {cur_height}/{best} | Selesai!                          \n")
        sys.stdout.flush()
        print(f"[✓] Sinkronisasi Berhasil! Height saat ini: {cur_height} (Tersimpan di blockchain.json)")
        print("="*46 + "\n")
        return True
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        sys.stdout.flush()
        print("[!] Sinkronisasi diinterupsi oleh pengguna.")
        print("="*46 + "\n")
        return False
    finally:
        # Kembalikan level logging console ke INFO
        for h in console_handlers:
            h.setLevel(logging.INFO)

def remove_peer(node):
    """Remove a manually added peer."""
    peers = node.get_peer_list()
    if not peers['manual']:
        print("\nBelum ada peer manual yang disimpan.")
        return
    print("\nPeer manual tersimpan:")
    for i, peer in enumerate(peers['manual'], 1):
        print(f"{i}. {peer}")
    target = input("Hapus peer (nomor atau host:port): ").strip()
    if target.isdigit() and 1 <= int(target) <= len(peers['manual']):
        target = peers['manual'][int(target) - 1]
    ok, message = node.remove_peer(target)
    print(message if ok else f"Gagal: {message}")

def show_peer_list(node):
    """Print every peer the node knows about, grouped by source."""
    peers = node.get_peer_list()
    print("\n--- Daftar Peer ---")
    print(f"Terhubung  ({len(peers['connected'])}):")
    for peer in peers['connected'] or ['-']:
        print(f"  - {peer}")
    print(f"Manual     ({len(peers['manual'])}):")
    for peer in peers['manual'] or ['-']:
        print(f"  - {peer}")
    print(f"Bootstrap  ({len(peers['bootstrap'])}):")
    for peer in peers['bootstrap'] or ['-']:
        print(f"  - {peer}")

def show_sync_status(node, blockchain):
    """Compare this node's height against the best height peers reported."""
    status = node.get_sync_status()
    height = status['height']
    best = status['best_known_height']

    print("\n--- Status Sinkronisasi ---")
    print(f"Node ini        : 0.0.0.0:{node.port}")
    print(f"Height lokal    : {height}")
    print(f"Height jaringan : {best}")
    print(f"Peer terhubung  : {status['peers']}")
    if status['in_sync']:
        print("Status          : SINKRON dengan jaringan")
    else:
        behind = best - height
        print(f"Status          : TERTINGGAL {behind} blok, sinkronisasi berjalan...")

def run_app():
    """Main function to run the ArthaChain application."""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else APP_PORT
    setup_logging(port)

    try:
        # --- PERBAIKAN: Meminta password sebelum membuat wallet ---
        password = getpass.getpass("Masukkan password dompet Anda: ")
        if not password:
            print("Password tidak boleh kosong.")
            return
        wallet = ArthaWallet(password=password)
    except ValueError as e:
        print(f"Gagal memuat dompet: {e}")
        return
    except (EOFError, KeyboardInterrupt):
        print("\nOperasi dibatalkan.")
        return

    public_address = wallet.get_public_address()
    blockchain = ArthaBlockchain()
    node = ArthaNode(APP_HOST, port, blockchain)
    node.start()

    logging.info(f"\nAlamat Dompet: {public_address}")
    logging.info(f"Node Aplikasi Berjalan di: {APP_HOST}:{port}")

    # Auto sync on startup without user typing anything!
    sync_blockchain_with_animation(node, blockchain, min_wait=3)

    try:
        while True:
            display_menu()
            choice = input("Pilih opsi: ").strip()

            if choice == '1':
                balance = blockchain.get_balance(public_address)
                print(f"\nAlamat: {public_address}")
                print(f"Saldo: {balance:.8f} ARTH")

            elif choice == '2':
                # Check sync status before creating transaction
                sync_st = node.get_sync_status()
                if not sync_st['in_sync']:
                    print("\n[!] Blockchain belum sinkron dengan jaringan. Memulai sinkronisasi...")
                    if not sync_blockchain_with_animation(node, blockchain, min_wait=1):
                        print("Transaksi dibatalkan karena sinkronisasi diinterupsi.")
                        continue

                recipient = input("Alamat penerima: ")
                try:
                    amount_str = input("Jumlah ARTH: ")
                    amount = Decimal(amount_str)
                except InvalidOperation:
                    print("Jumlah tidak valid.")
                    continue

                fee = P.MIN_TX_FEE
                if blockchain.get_balance(public_address) < amount + fee:
                    print(f"Saldo tidak mencukupi (butuh {amount:.8f} + fee {fee:.8f}).")
                    continue

                # v2: timestamp/nonce/fee ikut ditandatangani, nonce mencegah replay.
                nonce = blockchain.get_next_nonce(public_address)
                signed_tx = wallet.build_transaction(recipient, amount, fee, nonce)
                added_tx = blockchain.submit_transaction(signed_tx)

                if added_tx:
                    logging.info(f"Transaksi {added_tx['transaction_id'][:10]}... berhasil disiarkan.")
                    node.broadcast_message('NEW_TRANSACTION', {
                        'transaction': added_tx,
                        'public_key_str': added_tx['public_key_str']
                    })
                    # Tell the network we are behind so peers push their tip to us.
                    node.trigger_full_resync()
                else:
                    logging.warning("Gagal membuat transaksi.")
            
            elif choice == '3':
                show_connected_peers(node)

            elif choice == '4':
                add_new_peer(node, blockchain)

            elif choice == '5':
                remove_peer(node)

            elif choice == '6':
                show_peer_list(node)

            elif choice == '7':
                show_sync_status(node, blockchain)

            elif choice == '8':
                print("\n--- Blockchain ---")
                last = blockchain.last_block
                if not last:
                    print("Chain kosong.")
                else:
                    for block in blockchain.chain[-20:]:
                        print(f"Index: {block['index']}, Hash: {blockchain.hash_block(block)[:10]}...")
                    print(f"... total {len(blockchain.chain)} blok, tinggi saat ini {last['index']}")

            elif choice == '9':
                print("\nTransaksi Tertunda:")
                if not blockchain.pending_transactions:
                    print("Tidak ada.")
                else:
                    v2_active = P.is_v2(blockchain.get_current_block_height() + 1)
                    for tx in blockchain.pending_transactions:
                        sender = tx['sender']
                        ver = int(tx.get('version', 1))
                        print(
                            f"- Dari: {sender[:10]}... Jumlah: {tx['amount']} | "
                            f"ver: {ver} | fee: {tx.get('fee', '-')} | nonce: {tx.get('nonce', '-')}"
                        )
                        print(
                            f"    saldo terkonfirmasi: {blockchain.get_balance(sender):.8f} | "
                            f"nonce berikutnya: {blockchain.get_next_nonce(sender)}"
                        )
                        if v2_active and ver != 2:
                            print("    [!] Tx format v1 (lama). Blok sekarang v2 -> TIDAK akan "
                                  "diproses. Kirim ulang transaksi (pastikan node pakai kode terbaru).")
                    print("\n(Catatan: tx akan diproses miner hanya jika nonce berurutan, "
                          "saldo cukup, dan format v2 saat blok sudah v2.)")

            elif choice == '10':
                sync_blockchain_with_animation(node, blockchain, min_wait=1)

            elif choice == '11':
                print(f"\nLokasi file log: {LOG_FILE_PATH}")

            elif choice == '12':
                break
            else:
                print("Pilihan tidak valid.")

    except KeyboardInterrupt:
        logging.info("\nAplikasi dihentikan oleh pengguna.")
    finally:
        node.stop()

if __name__ == '__main__':
    run_app()