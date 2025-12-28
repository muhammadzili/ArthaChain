import socket
import threading
import json
import time
import logging
from decimal import Decimal
from queue import Queue
import urllib.request
from urllib.error import URLError

logger = logging.getLogger(__name__)

VERSION = "2.0.0"
GIST_URL = "https://gist.githubusercontent.com/muhammadzili/19fbb07822977ada20ef98cd3e5638c4/raw/28236276c04401e0ff83e4cdf3af8dd7064b59ca/node.json"
PEER_UPDATE_INTERVAL = 3600
PEER_TIMEOUT = 180  # Ditambah untuk stabilitas lebih lama
RECONNECT_INTERVAL = 30
MAX_RECONNECT_DELAY = 300 # Maksimal 5 menit backoff
HEARTBEAT_INTERVAL = 45

class ArthaNode:
    def __init__(self, host, port, blockchain_instance, is_miner=False, new_tx_event=None):
        self.host = host
        self.port = port
        self.blockchain = blockchain_instance
        self.peers = {} # {address: {socket, last_seen, version, reconnect_delay}}
        self.server_socket = None
        self.is_running = True
        self.is_miner = is_miner
        self.lock = threading.RLock()
        self.new_tx_event = new_tx_event
        self.message_queue = Queue()
        self.last_peer_update = 0
        self.bootstrap_peers = []
        
        self._fetch_peer_list()
        
        # Threading Management
        threading.Thread(target=self._peer_maintenance_loop, daemon=True).start()
        threading.Thread(target=self._message_processing_loop, daemon=True).start()
        threading.Thread(target=self._peer_update_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def _fetch_peer_list(self):
        try:
            with urllib.request.urlopen(GIST_URL, timeout=8) as response:
                data = json.loads(response.read().decode('utf-8'))
                with self.lock:
                    self.bootstrap_peers = data.get('bootstrap_peers', [])
                    self.last_peer_update = time.time()
                logger.info(f"Node v{VERSION}: Peer list updated.")
                return True
        except Exception as e:
            logger.warning(f"Fetch peer failed: {e}. Using local cache.")
            with self.lock:
                if not self.bootstrap_peers:
                    self.bootstrap_peers = ['127.0.0.1:5001']
            return False

    def _heartbeat_loop(self):
        """Fitur Baru v2.0: Mengirim PING secara periodik untuk menjaga koneksi tetap hidup."""
        while self.is_running:
            time.sleep(HEARTBEAT_INTERVAL)
            self.broadcast_message('PING', {'version': VERSION})

    def _peer_update_loop(self):
        while self.is_running:
            time.sleep(PEER_UPDATE_INTERVAL)
            self._fetch_peer_list()

    def _peer_maintenance_loop(self):
        while self.is_running:
            current_time = time.time()
            dead_peers = []
            
            with self.lock:
                for peer, data in self.peers.items():
                    if current_time - data['last_seen'] > PEER_TIMEOUT:
                        dead_peers.append(peer)
                
                for peer in dead_peers:
                    self._close_peer_connection(peer)
                    logger.warning(f"Peer {peer} timed out. Removed for stability.")
            
            if not self.peers and self.is_running:
                logger.info("Lost all connections. Re-syncing...")
                self.connect_and_sync_initial()
            
            time.sleep(RECONNECT_INTERVAL)

    def _close_peer_connection(self, peer_address):
        if peer_address in self.peers:
            try:
                self.peers[peer_address]['socket'].close()
            except:
                pass
            del self.peers[peer_address]

    def _message_processing_loop(self):
        while self.is_running:
            try:
                message, peer_address = self.message_queue.get(timeout=1)
                self._process_message(message, peer_address)
            except:
                continue

    def start(self):
        threading.Thread(target=self._start_server, daemon=True).start()
        logger.info(f"ArthaChain Node v{VERSION} active on {self.host}:{self.port}")
        self.connect_and_sync_initial()

    def stop(self):
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        with self.lock:
            peers_list = list(self.peers.keys())
            for peer in peers_list:
                self._close_peer_connection(peer)
        
        logger.info("Node shutdown complete.")

    def _start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(15)
            while self.is_running:
                try:
                    conn, addr = self.server_socket.accept()
                    peer_addr = f"{addr[0]}:{addr[1]}"
                    threading.Thread(target=self._handle_client, args=(conn, peer_addr), daemon=True).start()
                except OSError:
                    break
        except Exception as e:
            if self.is_running: logger.error(f"Server Error: {e}")
        finally:
            self.server_socket.close()

    def _handle_client(self, conn, peer_address):
        # Initial handshake info
        with self.lock:
            self.peers[peer_address] = {'socket': conn, 'last_seen': time.time(), 'version': 'unknown'}
        
        buffer = b''
        try:
            # Kirim info versi kita dulu (Handshake v2.0)
            self.send_message(peer_address, 'HANDSHAKE', {'version': VERSION})
            
            while self.is_running:
                data = conn.recv(32768) # Ukuran buffer lebih besar untuk stabilitas sinkronisasi
                if not data: break
                
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line:
                        try:
                            message = json.loads(line.decode('utf-8'))
                            with self.lock:
                                if peer_address in self.peers:
                                    self.peers[peer_address]['last_seen'] = time.time()
                            self.message_queue.put((message, peer_address))
                        except:
                            continue
        except:
            pass
        finally:
            with self.lock:
                self._close_peer_connection(peer_address)

    def _process_message(self, message, sender_peer_address):
        msg_type = message.get('type')
        data = message.get('data', {})

        try:
            if msg_type == 'HANDSHAKE':
                remote_version = data.get('version', '1.0.0')
                with self.lock:
                    if sender_peer_address in self.peers:
                        self.peers[sender_peer_address]['version'] = remote_version
                logger.debug(f"Peer {sender_peer_address} is running version {remote_version}")

            elif msg_type == 'PING':
                self.send_message(sender_peer_address, 'PONG', {'version': VERSION})
                
            elif msg_type == 'NEW_TRANSACTION':
                tx_data = data['transaction']
                if self.blockchain.add_transaction(
                    tx_data['sender'], tx_data['recipient'], Decimal(tx_data['amount']),
                    tx_data['signature'], data['public_key_str'], tx_data.get('timestamp')
                ):
                    if self.new_tx_event: self.new_tx_event.set()
                    self.broadcast_message('NEW_TRANSACTION', data, exclude_peer=sender_peer_address)

            elif msg_type == 'NEW_BLOCK':
                if self.blockchain.replace_chain(self.blockchain.chain + [data['block']]):
                    self.broadcast_message('NEW_BLOCK', data, exclude_peer=sender_peer_address)

            elif msg_type == 'REQUEST_CHAIN':
                self.send_message(sender_peer_address, 'RESPOND_CHAIN', {'chain': self.blockchain.chain})

            elif msg_type == 'RESPOND_CHAIN':
                self.blockchain.replace_chain(data['chain'])
                
        except Exception as e:
            logger.error(f"Error processing {msg_type}: {e}")

    def send_message(self, peer_address, message_type, data):
        message = {'type': message_type, 'data': data, 'timestamp': time.time(), 'sender_version': VERSION}
        with self.lock:
            peer_data = self.peers.get(peer_address)
        if not peer_data: return False
        try:
            peer_data['socket'].sendall((json.dumps(message) + '\n').encode('utf-8'))
            return True
        except:
            with self.lock: self._close_peer_connection(peer_address)
            return False

    def broadcast_message(self, message_type, data, exclude_peer=None):
        with self.lock:
            peers_copy = list(self.peers.keys())
        for peer in peers_copy:
            if peer != exclude_peer:
                self.send_message(peer, message_type, data)

    def connect_to_peer(self, host, port):
        peer_addr = f"{host}:{port}"
        if peer_addr == f"{self.host}:{self.port}": return False
        with self.lock:
            if peer_addr in self.peers: return True
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.settimeout(None)
            threading.Thread(target=self._handle_client, args=(sock, peer_addr), daemon=True).start()
            return True
        except:
            return False

    def connect_and_sync_initial(self):
        """Fitur Re-koneksi Otomatis v2.0."""
        with self.lock:
            targets = self.bootstrap_peers.copy()
        
        for peer in targets:
            try:
                h, p = peer.split(':')
                if self.connect_to_peer(h, int(p)):
                    logger.info(f"Connected to {peer}")
            except:
                continue
        
        time.sleep(3)
        if self.peers:
            self.trigger_full_resync()

    def trigger_full_resync(self):
        self.broadcast_message('REQUEST_CHAIN', {})

    def handle_new_block(self, block):
        return self.blockchain.replace_chain(self.blockchain.chain + [block])