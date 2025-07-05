# artha_node_pos.py

import socket
import threading
import json
import time
import logging
from queue import Queue
import urllib.request
from urllib.error import URLError

from artha_utils import json_serialize

logger = logging.getLogger(__name__)

GIST_URL = "https://gist.githubusercontent.com/muhammadzili/19fbb07822977ada20ef98cd3e5638c4/raw/e2a2a002e0a2b26797f554a8e4099cf34e70b066/node.json"
PEER_UPDATE_INTERVAL = 3600
PEER_TIMEOUT = 120
RECONNECT_INTERVAL = 30
HEARTBEAT_INTERVAL = 60
MAX_BUFFER_SIZE = 65536

class ArthaNodePoS:
    def __init__(self, host, port, blockchain_instance):
        self.host = host
        self.port = port
        self.blockchain = blockchain_instance
        self.peers = {}
        self.server_socket = None
        self.is_running = True
        self.node_id = f"{host}:{port}"
        self.lock = threading.RLock()
        self.message_queue = Queue()
        
        self._fetch_peer_list()
        threading.Thread(target=self._peer_maintenance_loop, daemon=True).start()
        threading.Thread(target=self._message_processing_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def _fetch_peer_list(self):
        try:
            with urllib.request.urlopen(GIST_URL, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                with self.lock: self.bootstrap_peers = data.get('bootstrap_peers', [])
                logger.info(f"Updated peer list from Gist: {self.bootstrap_peers}")
        except Exception as e:
            logger.warning(f"Failed to fetch peer list: {e}. Using default.")
            with self.lock:
                if not self.bootstrap_peers: self.bootstrap_peers = ['127.0.0.1:5001']

    def _heartbeat_loop(self):
        while self.is_running:
            time.sleep(HEARTBEAT_INTERVAL)
            with self.lock:
                if not self.peers: continue
                self.broadcast_message('PING', {})

    def _peer_maintenance_loop(self):
        while self.is_running:
            time.sleep(RECONNECT_INTERVAL)
            self._check_dead_peers()
            if not self.peers and self.is_running:
                self.connect_and_sync_initial()

    def _check_dead_peers(self):
        current_time = time.time()
        dead_peers = []
        with self.lock:
            for peer, data in self.peers.items():
                if current_time - data.get('last_seen', 0) > PEER_TIMEOUT:
                    dead_peers.append(peer)
            for peer in dead_peers: self._close_peer_connection(peer)

    def _close_peer_connection(self, peer_address):
        with self.lock:
            if peer_address in self.peers:
                try: self.peers[peer_address]['socket'].close()
                except Exception: pass
                del self.peers[peer_address]
                logger.warning(f"Peer {peer_address} disconnected.")

    def _message_processing_loop(self):
        while self.is_running:
            try:
                message, peer_address = self.message_queue.get(timeout=1)
                self._process_message(message, peer_address)
            except: continue

    def start(self):
        threading.Thread(target=self._start_server, daemon=True).start()
        logger.info(f"PoS Node starting at {self.host}:{self.port}")
        time.sleep(1)
        self.connect_and_sync_initial()

    def stop(self):
        self.is_running = False
        if self.server_socket:
            try: self.server_socket.close()
            except OSError: pass
        with self.lock:
            peers_to_close = list(self.peers.keys())
        for peer in peers_to_close: self._close_peer_connection(peer)
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
            if self.is_running: logger.error(f"Server failed: {e}")
        finally:
            if self.server_socket: self.server_socket.close()

    def _handle_client(self, conn, peer_address):
        with self.lock: self.peers[peer_address] = {'socket': conn, 'last_seen': time.time()}
        logger.info(f"Connection from {peer_address}")
        buffer = b''
        try:
            while self.is_running:
                data = conn.recv(16384)
                if not data: break
                buffer += data
                if len(buffer) > MAX_BUFFER_SIZE: break
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line:
                        try:
                            message = json.loads(line.decode('utf-8'))
                            with self.lock:
                                if peer_address in self.peers: self.peers[peer_address]['last_seen'] = time.time()
                            self.message_queue.put((message, peer_address))
                        except json.JSONDecodeError: pass
        except (ConnectionResetError, ConnectionAbortedError): pass
        except Exception as e: logger.error(f"Error with {peer_address}: {e}")
        finally: self._close_peer_connection(peer_address)

    def _process_message(self, message, sender_peer_address):
        msg_type = message.get('type')
        data = message.get('data', {})

        try:
            if msg_type == 'PING':
                self.send_message(sender_peer_address, 'PONG', {})
                return
            elif msg_type == 'PONG':
                return

            elif msg_type == 'NEW_TRANSACTION':
                tx = data['transaction']
                if self.blockchain.add_transaction(
                    tx['sender'], tx['recipient'], tx['amount'],
                    tx['signature'], data['public_key_str'], tx.get('timestamp')
                ):
                    self.broadcast_message('NEW_TRANSACTION', data, exclude_peer=sender_peer_address)

            elif msg_type == 'NEW_BLOCK':
                block = self.blockchain._deserialize_chain([data['block']])[0]
                last_block = self.blockchain.last_block
                
                if block['index'] > last_block['index']:
                    if block['previous_hash'] == self.blockchain.hash_block(last_block) and \
                       block['validator'] == self.blockchain.get_next_validator():
                        self.blockchain.add_block(block)
                        self.broadcast_message('NEW_BLOCK', data, exclude_peer=sender_peer_address)
                    else:
                        logger.warning(f"Chain is behind or fork detected. Requesting sync from {sender_peer_address}.")
                        self.send_message(sender_peer_address, 'REQUEST_CHAIN', {})

            elif msg_type == 'REQUEST_CHAIN':
                chain_data = json.loads(json_serialize(self.blockchain.chain).decode('utf-8'))
                self.send_message(sender_peer_address, 'RESPOND_CHAIN', {'chain': chain_data})
            
            elif msg_type == 'RESPOND_CHAIN':
                self.blockchain.replace_chain(data['chain'])

        except Exception as e:
            logger.error(f"Error processing '{msg_type}': {e}", exc_info=True)

    def send_message(self, peer_address, message_type, data):
        message_bytes = json_serialize({'type': message_type, 'data': data, 'timestamp': time.time()})
        with self.lock: peer_data = self.peers.get(peer_address)
        if not peer_data: return False
        try:
            peer_data['socket'].sendall(message_bytes + b'\n')
            return True
        except (OSError, BrokenPipeError):
            self._close_peer_connection(peer_address)
            return False

    def broadcast_message(self, message_type, data, exclude_peer=None):
        with self.lock: peers_copy = list(self.peers.keys())
        for peer in peers_copy:
            if peer != exclude_peer: self.send_message(peer, message_type, data)

    def connect_to_peer(self, host, port):
        peer_address = f"{host}:{port}"
        if peer_address == self.node_id: return False
        with self.lock:
            if peer_address in self.peers: return True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            sock.settimeout(None)
            threading.Thread(target=self._handle_client, args=(sock, peer_address), daemon=True).start()
            return True
        except Exception: return False

    def connect_and_sync_initial(self):
        time.sleep(2)
        with self.lock: current_peers = self.bootstrap_peers.copy()
        connected_count = 0
        for peer in current_peers:
            try:
                host, port_str = peer.split(':')
                if self.connect_to_peer(host, int(port_str)):
                    connected_count += 1
            except ValueError: pass
        time.sleep(3)
        if connected_count > 0: self.trigger_full_resync()

    def trigger_full_resync(self):
        self.broadcast_message('REQUEST_CHAIN', {})
