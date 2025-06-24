# artha_node.py

import socket
import threading
import json
import time
import logging
from artha_utils import json_serialize

logger = logging.getLogger(__name__)

BOOTSTRAP_PEERS = [
    '127.0.0.1:5001',
    '47.237.125.206:5001' 
]

class ArthaNode:
    def __init__(self, host, port, blockchain_instance, is_miner=False):
        self.host = host
        self.port = port
        self.blockchain = blockchain_instance
        self.peers = {} 
        self.server_socket = None
        self.is_running = False
        self.is_miner = is_miner
        self.last_block_broadcast_time = time.time()
        self.lock = threading.Lock()

    def start(self):
        self.is_running = True
        self.server_thread = threading.Thread(target=self._start_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        logger.info(f"ArthaChain node started at {self.host}:{self.port}")
        threading.Thread(target=self.connect_and_sync_initial, daemon=True).start()

    def stop(self):
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
                self.server_socket.close()
            except OSError: pass
        
        with self.lock:
            for sock in self.peers.values():
                try: sock.close()
                except OSError: pass
            self.peers.clear()
        logger.info(f"ArthaChain node at {self.host}:{self.port} stopped.")

    def _start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            while self.is_running:
                try:
                    conn, addr = self.server_socket.accept()
                    peer_address = f"{addr[0]}:{addr[1]}"
                    logger.info(f"Incoming connection from {peer_address}")
                    with self.lock:
                        self.peers[peer_address] = conn
                    threading.Thread(target=self._handle_client, args=(conn, peer_address), daemon=True).start()
                except OSError:
                    if self.is_running: logger.error(f"Error accepting connection")
                    break
        except Exception as e:
            logger.error(f"Server failed at {self.host}:{self.port}: {e}")
            self.is_running = False

    def _handle_client(self, conn, peer_address):
        buffer = b''
        try:
            while self.is_running:
                data = conn.recv(8192) # Increased buffer size
                if not data: break
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if not line: continue
                    try:
                        message = json.loads(line.decode('utf-8'))
                        self._process_message(message, peer_address)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from {peer_address}: {line[:100]}")
        except Exception:
            pass # Connection lost is expected
        finally:
            with self.lock:
                if peer_address in self.peers:
                    del self.peers[peer_address]
            conn.close()
            logger.info(f"Connection to {peer_address} closed.")

    def connect_to_peer(self, peer_host, peer_port):
        peer_address = f"{peer_host}:{peer_port}"
        if peer_address == f"{self.host}:{self.port}": return False
        with self.lock:
            if peer_address in self.peers: return False

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((peer_host, peer_port))
            s.settimeout(None)
            with self.lock:
                self.peers[peer_address] = s
            logger.info(f"Connected to peer: {peer_address}")
            threading.Thread(target=self._handle_client, args=(s, peer_address), daemon=True).start()
            self.send_message(peer_address, 'NEW_PEER', {'address': f"{self.host}:{self.port}"})
            self.request_chain_from_specific_peer(peer_address)
            return True
        except Exception as e:
            logger.debug(f"Failed to connect to peer {peer_address}: {e}")
            return False

    def send_message(self, peer_address, message_type, data):
        message = {'type': message_type, 'data': data}
        message_str = json.dumps(message) + '\n'
        with self.lock:
            sock = self.peers.get(peer_address)
        if sock:
            try:
                sock.sendall(message_str.encode('utf-8'))
            except OSError:
                with self.lock:
                    if peer_address in self.peers: del self.peers[peer_address]
                sock.close()

    def broadcast_message(self, message_type, data, exclude_peer=None):
        with self.lock:
            peers_to_broadcast = list(self.peers.keys())
        for peer_address in peers_to_broadcast:
            if peer_address != exclude_peer:
                self.send_message(peer_address, message_type, data)

    def _process_message(self, message, sender_peer_address):
        msg_type = message.get('type')
        msg_data = message.get('data')

        if msg_type == 'NEW_BLOCK':
            block = msg_data['block']
            logger.info(f"Received new block #{block['index']} from {sender_peer_address}.")
            if block['index'] == self.blockchain.last_block['index'] + 1 and \
               self.blockchain.hash_block(self.blockchain.last_block) == block['previous_hash'] and \
               self.blockchain.is_chain_valid(self.blockchain.chain + [block]):
                
                self.blockchain.chain.append(block)
                self.blockchain.pending_transactions = []
                self.blockchain.known_pending_tx_hashes.clear()
                self.blockchain.save_chain()
                logger.info(f"Block #{block['index']} added to local chain.")
                if time.time() - self.last_block_broadcast_time > 5:
                    self.broadcast_message('NEW_BLOCK', {'block': block}, exclude_peer=sender_peer_address)
                    self.last_block_broadcast_time = time.time()
            else:
                logger.warning(f"Block #{block['index']} from {sender_peer_address} rejected. Requesting full chain...")
                self.sync_blockchain_from_known_peers()

        elif msg_type == 'NEW_TRANSACTION':
            tx = msg_data['transaction']
            sender_pk = msg_data['public_key_str']
            tx_timestamp = tx.get('timestamp')
            if self.blockchain.add_transaction(tx['sender'], tx['recipient'], tx['amount'], tx['signature'], sender_pk, timestamp=tx_timestamp):
                logger.info(f"Received and validated new tx {self.blockchain._calculate_transaction_id(tx)[:10]}...")
                self.broadcast_message('NEW_TRANSACTION', {'transaction': tx, 'public_key_str': sender_pk}, exclude_peer=sender_peer_address)

        elif msg_type == 'REQUEST_CHAIN':
            logger.debug(f"Received chain request from {sender_peer_address}. Sending chain...")
            self.send_message(sender_peer_address, 'RESPOND_CHAIN', {'chain': self.blockchain.chain})

        elif msg_type == 'RESPOND_CHAIN':
            received_chain = msg_data['chain']
            logger.info(f"Received chain (len: {len(received_chain)}) from {sender_peer_address}.")
            self.blockchain.replace_chain(received_chain)

        elif msg_type == 'NEW_PEER':
            peer_address = msg_data['address']
            if peer_address != f"{self.host}:{self.port}":
                host, port_str = peer_address.split(':')
                if self.connect_to_peer(host, int(port_str)):
                    logger.info(f"Added new discovered peer: {peer_address}.")
                    self.broadcast_message('NEW_PEER', {'address': peer_address}, exclude_peer=sender_peer_address)

    def request_chain_from_specific_peer(self, peer_address):
        logger.debug(f"Requesting chain from {peer_address}...")
        self.send_message(peer_address, 'REQUEST_CHAIN', {})

    def connect_and_sync_initial(self):
        logger.info("Connecting to bootstrap peers...")
        time.sleep(1)
        connected = any(self.connect_to_peer(*peer.split(':')) for peer in BOOTSTRAP_PEERS)
        if not connected:
            logger.warning("Could not connect to any bootstrap peers. Starting with local chain.")
        else:
            logger.info("Connected to bootstrap peers. Initial sync initiated.")
            time.sleep(5) # Give time for chain responses
            self.sync_blockchain_from_known_peers()

    def sync_blockchain_from_known_peers(self):
        with self.lock:
            peers_to_sync_from = list(self.peers.keys())
        if not peers_to_sync_from: return
        logger.info("Triggering active sync from known peers...")
        for peer_address in peers_to_sync_from:
            self.request_chain_from_specific_peer(peer_address)
            time.sleep(0.5)

