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

# Configuration
GIST_URL = "https://gist.githubusercontent.com/muhammadzili/19fbb07822977ada20ef98cd3e5638c4/raw/9ea6b8a0a0c2e16ca4083ab40175af9343ee13f8/node.json"
PEER_UPDATE_INTERVAL = 3600
PEER_TIMEOUT = 120
RECONNECT_INTERVAL = 30
HEARTBEAT_INTERVAL = 60

class ArthaNode:
    def __init__(self, host, port, blockchain_instance, is_miner=False, new_tx_event=None):
        self.host = host
        self.port = port
        self.blockchain = blockchain_instance
        self.peers = {}
        self.server_socket = None
        self.is_running = True
        self.is_miner = is_miner
        self.lock = threading.RLock()
        self.new_tx_event = new_tx_event
        self.message_queue = Queue()
        self.last_peer_update = 0
        self.bootstrap_peers = []
        
        self._fetch_peer_list()
        threading.Thread(target=self._peer_maintenance_loop, daemon=True).start()
        threading.Thread(target=self._message_processing_loop, daemon=True).start()
        threading.Thread(target=self._peer_update_loop, daemon=True).start()

    def _fetch_peer_list(self):
        try:
            with urllib.request.urlopen(GIST_URL, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                with self.lock:
                    self.bootstrap_peers = data.get('bootstrap_peers', [])
                    self.last_peer_update = time.time()
                logger.info(f"Updated peer list from Gist: {self.bootstrap_peers}")
                return True
        except (URLError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to fetch peer list: {e}")
            with self.lock:
                if not self.bootstrap_peers:
                    self.bootstrap_peers = ['127.0.0.1:5001', '47.237.125.206:5001']
            return False

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
                    try:
                        self.peers[peer]['socket'].close()
                    except:
                        pass
                    del self.peers[peer]
                    logger.warning(f"Peer {peer} timed out and was removed")
            
            if not self.peers and self.is_running:
                logger.info("No active peers, attempting to reconnect...")
                self.connect_and_sync_initial()
            
            time.sleep(RECONNECT_INTERVAL)

    def _message_processing_loop(self):
        while self.is_running:
            try:
                message, peer_address = self.message_queue.get(timeout=1)
                self._process_message(message, peer_address)
            except:
                continue

    def start(self):
        threading.Thread(target=self._start_server, daemon=True).start()
        logger.info(f"ArthaChain node started at {self.host}:{self.port}")
        self.connect_and_sync_initial()

    def stop(self):
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
        
        with self.lock:
            for peer_data in self.peers.values():
                try:
                    peer_data['socket'].close()
                except OSError:
                    pass
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
                    peer_address = f"{addr[0]}:{addr[1]}"
                    threading.Thread(
                        target=self._handle_client,
                        args=(conn, peer_address),
                        daemon=True
                    ).start()
                except OSError:
                    break
        except Exception as e:
            if self.is_running:
                logger.error(f"Server failed at {self.host}:{self.port}: {e}")
        finally:
            self.server_socket.close()

    def _handle_client(self, conn, peer_address):
        with self.lock:
            self.peers[peer_address] = {
                'socket': conn,
                'last_seen': time.time()
            }
        
        logger.info(f"Connection established with {peer_address}")
        buffer = b''
        
        try:
            while self.is_running:
                data = conn.recv(16384)
                if not data:
                    break
                
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
                        except json.JSONDecodeError:
                            logger.debug(f"Invalid JSON from {peer_address}")
        except ConnectionResetError:
            logger.info(f"Connection reset by {peer_address}")
        except Exception as e:
            logger.error(f"Error handling client {peer_address}: {e}")
        finally:
            with self.lock:
                if peer_address in self.peers:
                    del self.peers[peer_address]
            conn.close()
            logger.info(f"Connection to {peer_address} closed.")

    def _process_message(self, message, sender_peer_address):
        msg_type = message.get('type')
        if not msg_type:
            return

        try:
            if msg_type == 'PING':
                self.send_message(sender_peer_address, 'PONG', {})
            elif msg_type == 'PONG':
                pass
            elif msg_type == 'NEW_TRANSACTION':
                tx_data = message['data']
                tx = tx_data['transaction']
                pk = tx_data['public_key_str']
                
                if self.blockchain.add_transaction(
                    tx['sender'],
                    tx['recipient'],
                    Decimal(tx['amount']),
                    tx['signature'],
                    pk,
                    tx.get('timestamp')
                ):
                    if self.new_tx_event:
                        self.new_tx_event.set()
                    self.broadcast_message(
                        'NEW_TRANSACTION',
                        tx_data,
                        exclude_peer=sender_peer_address
                    )
            elif msg_type == 'NEW_BLOCK':
                if self.handle_new_block(message['data']['block']):
                    self.broadcast_message(
                        'NEW_BLOCK',
                        message['data'],
                        exclude_peer=sender_peer_address
                    )
            elif msg_type == 'REQUEST_CHAIN':
                self.send_message(
                    sender_peer_address,
                    'RESPOND_CHAIN',
                    {'chain': self.blockchain.chain}
                )
            elif msg_type == 'RESPOND_CHAIN':
                self.blockchain.replace_chain(message['data']['chain'])
        except Exception as e:
            logger.error(f"Error processing {msg_type} message: {e}")

    def send_message(self, peer_address, message_type, data):
        message = {
            'type': message_type,
            'data': data,
            'timestamp': time.time()
        }
        
        with self.lock:
            peer_data = self.peers.get(peer_address)
        
        if not peer_data:
            logger.debug(f"Attempted to send to unknown peer: {peer_address}")
            return False
        
        try:
            peer_data['socket'].sendall(
                (json.dumps(message) + '\n').encode('utf-8')
            )
            return True
        except OSError as e:
            logger.warning(f"Failed to send to {peer_address}: {e}")
            with self.lock:
                if peer_address in self.peers:
                    try:
                        self.peers[peer_address]['socket'].close()
                    except:
                        pass
                    del self.peers[peer_address]
            return False

    def broadcast_message(self, message_type, data, exclude_peer=None):
        with self.lock:
            peers_copy = list(self.peers.keys())
        
        for peer in peers_copy:
            if peer != exclude_peer:
                self.send_message(peer, message_type, data)

    def connect_to_peer(self, host, port):
        peer_address = f"{host}:{port}"
        
        if peer_address == f"{self.host}:{self.port}":
            return False
        
        with self.lock:
            if peer_address in self.peers:
                return True
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            sock.settimeout(None)
            
            threading.Thread(
                target=self._handle_client,
                args=(sock, peer_address),
                daemon=True
            ).start()
            return True
        except Exception as e:
            logger.debug(f"Failed to connect to {peer_address}: {e}")
            return False

    def connect_and_sync_initial(self):
        time.sleep(2)
        
        with self.lock:
            current_peers = self.bootstrap_peers.copy()
        
        for peer in current_peers:
            try:
                host, port_str = peer.split(':')
                if self.connect_to_peer(host, int(port_str)):
                    logger.info(f"Connected to bootstrap peer: {peer}")
            except ValueError:
                logger.warning(f"Invalid peer format: {peer}")
        
        time.sleep(5)
        
        if self.peers:
            self.trigger_full_resync()
        else:
            logger.warning("Could not connect to any bootstrap peers.")
            if self._fetch_peer_list():
                self.connect_and_sync_initial()

    def trigger_full_resync(self):
        self.broadcast_message('REQUEST_CHAIN', {})

    def handle_new_block(self, block):
        return self.blockchain.replace_chain(self.blockchain.chain + [block])
