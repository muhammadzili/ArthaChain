# artha_node.py

import socket
import threading
import json
import time
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

BOOTSTRAP_PEERS = [
    '127.0.0.1:5001',
    '47.237.125.206:5001' # Pastikan IP ini benar dan port 5001 terbuka
]

class ArthaNode:
    # --- PERUBAHAN: Menambahkan new_tx_event untuk model miner hybrid ---
    def __init__(self, host, port, blockchain_instance, is_miner=False, new_tx_event=None):
        self.host = host
        self.port = port
        self.blockchain = blockchain_instance
        self.peers = {}
        self.server_socket = None
        self.is_running = True
        self.is_miner = is_miner
        self.lock = threading.RLock() # --- PERBAIKAN: Menggunakan RLock untuk mencegah deadlock ---
        self.new_tx_event = new_tx_event

    def start(self):
        threading.Thread(target=self._start_server, daemon=True).start()
        logger.info(f"ArthaChain node started at {self.host}:{self.port}")
        threading.Thread(target=self.connect_and_sync_initial, daemon=True).start()

    def stop(self):
        self.is_running = False
        if self.server_socket:
            try: self.server_socket.close()
            except OSError: pass
        with self.lock:
            for sock in self.peers.values():
                try: sock.close()
                except OSError: pass
            self.peers.clear()
        logger.info(f"Node at {self.host}:{self.port} stopped.")

    def _start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            while self.is_running:
                try:
                    conn, addr = self.server_socket.accept()
                    threading.Thread(target=self._handle_client, args=(conn, f"{addr[0]}:{addr[1]}"), daemon=True).start()
                except OSError: break
        except Exception as e:
            if self.is_running: logger.error(f"Server failed at {self.host}:{self.port}: {e}")

    def _handle_client(self, conn, peer_address):
        with self.lock: self.peers[peer_address] = conn
        logger.info(f"Connection established with {peer_address}")
        buffer = b''
        try:
            while self.is_running:
                data = conn.recv(16384) # Buffer lebih besar untuk blok
                if not data: break
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line:
                        try:
                            message = json.loads(line.decode('utf-8'))
                            self._process_message(message, sender_peer_address=peer_address)
                        except json.JSONDecodeError: pass
        finally:
            with self.lock:
                if peer_address in self.peers: del self.peers[peer_address]
            conn.close()
            logger.info(f"Connection to {peer_address} closed.")

    def _process_message(self, message, sender_peer_address):
        msg_type = message.get('type')
        if not msg_type: return

        if msg_type == 'NEW_TRANSACTION':
            tx, pk = message['data']['transaction'], message['data']['public_key_str']
            if self.blockchain.add_transaction(tx['sender'], tx['recipient'], Decimal(tx['amount']), tx['signature'], pk, tx['timestamp']):
                if self.new_tx_event: self.new_tx_event.set() # Bangunkan miner
                self.broadcast_message('NEW_TRANSACTION', message['data'], exclude_peer=sender_peer_address)
        elif msg_type == 'NEW_BLOCK':
            if self.handle_own_new_block(message['data']['block']):
                self.broadcast_message('NEW_BLOCK', message['data'], exclude_peer=sender_peer_address)
        elif msg_type == 'RESPOND_CHAIN':
            self.blockchain.replace_chain(message['data']['chain'])
        elif msg_type == 'REQUEST_CHAIN':
            self.send_message(sender_peer_address, 'RESPOND_CHAIN', {'chain': self.blockchain.chain})

    def send_message(self, peer_address, message_type, data):
        message = {'type': message_type, 'data': data}
        with self.lock: sock = self.peers.get(peer_address)
        if sock:
            try: sock.sendall((json.dumps(message) + '\n').encode('utf-8'))
            except OSError: pass

    def broadcast_message(self, message_type, data, exclude_peer=None):
        with self.lock:
            for peer in list(self.peers.keys()):
                if peer != exclude_peer: self.send_message(peer, message_type, data)

    def connect_to_peer(self, host, port):
        peer_address = f"{host}:{port}"
        if peer_address == f"{self.host}:{self.port}" or peer_address in self.peers: return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(5)
            s.connect((host, port)); s.settimeout(None)
            threading.Thread(target=self._handle_client, args=(s, peer_address), daemon=True).start()
        except Exception as e: logger.debug(f"Failed to connect to {peer_address}: {e}")

    def connect_and_sync_initial(self):
        time.sleep(2)
        for peer in BOOTSTRAP_PEERS:
            try: host, port_str = peer.split(':'); self.connect_to_peer(host, int(port_str))
            except ValueError: pass
        time.sleep(5)
        if self.peers: self.trigger_full_resync()
        else: logger.warning("Could not connect to any bootstrap peers.")

    def trigger_full_resync(self):
        with self.lock: self.broadcast_message('REQUEST_CHAIN', {})
        
    def handle_own_new_block(self, block):
        """Metode aman untuk memproses blok baru."""
        return self.blockchain.replace_chain(self.blockchain.chain + [block])
