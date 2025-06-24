# artha_node.py

import socket
import threading
import json
import time
import logging # Import logging module
from artha_utils import json_serialize
from artha_blockchain import ArthaBlockchain

# Configure logger for this module
logger = logging.getLogger(__name__)
# By default, logs will go to the root logger which is configured in app/miner scripts

# --- New: Bootstrap Peers Configuration ---
# These are known, stable peer addresses that new nodes will try to connect to initially.
# Replace 'YOUR_VPS_PUBLIC_IP' with your actual VPS public IP address.
# It's good practice to have multiple stable bootstrap nodes if possible.
BOOTSTRAP_PEERS = [
    '127.0.0.1:5001',             # For local testing (connecting to a miner on the same machine)
    '47.237.125.206:5001'         # Your VPS miner node (ensure this is its public IP and open port)
    # Add more bootstrap peers here if you have them, e.g., 'another_vps_ip:5001'
]

class ArthaNode:
    def __init__(self, host, port, blockchain_instance, is_miner=False):
        self.host = host
        self.port = port
        self.blockchain = blockchain_instance
        self.peers = {} # Changed from set to dict: {address: socket_object} for persistent connections
        self.server_socket = None
        self.is_running = False
        self.is_miner = is_miner # Flag to differentiate miner or app nodes
        self.last_block_broadcast_time = time.time() # To prevent excessive broadcasting
        self.lock = threading.Lock() # Lock to protect self.peers dictionary

    def start(self):
        """
        Starts the node server and attempts to synchronize the blockchain.
        """
        self.is_running = True
        self.server_thread = threading.Thread(target=self._start_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        logger.info(f"ArthaChain node started at {self.host}:{self.port}")
        
        # --- Modified: Automatically connect to bootstrap peers and then sync ---
        threading.Thread(target=self.connect_and_sync_initial).start()

    def stop(self):
        """
        Stops the node server.
        """
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
                self.server_socket.close()
            except OSError:
                pass # Already closed
        
        # Close all active peer connections
        with self.lock:
            for addr, sock in list(self.peers.items()):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                    sock.close()
                except OSError as e:
                    logger.debug(f"Error closing socket for {addr}: {e}") # Log error, but don't stop
            self.peers.clear()

        logger.info(f"ArthaChain node at {self.host}:{self.port} stopped.")

    def _start_server(self):
        """
        Server logic for listening for incoming connections.
        """
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            while self.is_running:
                try:
                    conn, addr = self.server_socket.accept()
                    peer_address = f"{addr[0]}:{addr[1]}"
                    logger.info(f"Incoming connection from {peer_address}") # Log incoming connections
                    
                    # Store the socket for this incoming connection
                    with self.lock:
                        self.peers[peer_address] = conn
                    
                    threading.Thread(target=self._handle_client, args=(conn, peer_address)).start()
                except OSError as e:
                    if self.is_running:
                        logger.error(f"Error accepting connection: {e}")
                    break
        except Exception as e:
            logger.error(f"Failed to start server at {self.host}:{self.port}: {e}")
            self.is_running = False

    def _handle_client(self, conn, peer_address): # peer_address is now passed directly
        """
        Handles communication with a connected client (for both incoming and outgoing connections).
        """
        buffer = b''
        try:
            while self.is_running:
                data = conn.recv(4096)
                if not data:
                    break # Connection closed by peer
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    try:
                        message = json.loads(line.decode('utf-8'))
                        self._process_message(message, peer_address) # Pass peer_address instead of conn
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON message from {peer_address}: {line}")
                        break # Skip malformed part and continue
        except Exception as e:
            logger.debug(f"Connection with {peer_address} lost or error: {e}") # Debug level for common disconnects
        finally:
            with self.lock:
                if peer_address in self.peers:
                    del self.peers[peer_address] # Remove disconnected peer
            try:
                conn.close()
            except OSError:
                pass # Already closed
            logger.info(f"Connection to {peer_address} closed.") # Inform when connection closes

    def connect_to_peer(self, peer_host, peer_port):
        """
        Attempts to connect to another peer and establish a persistent connection.
        Returns True on success, False on failure or if already connected.
        """
        peer_address = f"{peer_host}:{peer_port}"
        if peer_address == f"{self.host}:{self.port}":
            # logger.debug("Cannot connect to self.") # More appropriate for debug
            return False

        with self.lock:
            if peer_address in self.peers:
                # logger.debug(f"Already connected to {peer_address}.")
                return False

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5) # Set a timeout for connection
            s.connect((peer_host, peer_port))
            s.settimeout(None) # Remove timeout after connection
            
            with self.lock:
                self.peers[peer_address] = s # Store the socket
            
            logger.info(f"Successfully connected to peer: {peer_address}")
            # Start a thread to handle messages from this outgoing peer
            threading.Thread(target=self._handle_client, args=(s, peer_address)).start()
            
            # Send a message to tell the peer our address immediately after connecting
            threading.Thread(target=self.send_message, args=(peer_address, 'NEW_PEER', {'address': f"{self.host}:{self.port}"})).start()

            # Request chain from the newly connected peer (will be handled by _process_message's specific logic)
            threading.Thread(target=self.request_chain_from_specific_peer, args=(peer_address,)).start()
            return True
        except Exception as e:
            logger.debug(f"Failed to connect to peer {peer_address}: {e}") # Debug level for failed connections
            return False

    def send_message(self, peer_address, message_type, data):
        """
        Sends a message to a specific connected peer using its persistent socket.
        """
        message = {'type': message_type, 'data': data}
        message_str = json.dumps(message) + '\n'
        
        with self.lock:
            sock = self.peers.get(peer_address)

        if sock:
            try:
                sock.sendall(message_str.encode('utf-8'))
            except OSError as e: # Handle socket errors during send
                logger.debug(f"Error sending message to {peer_address}: {e}. Closing socket.")
                with self.lock:
                    if peer_address in self.peers:
                        del self.peers[peer_address] # Remove peer if send fails
                try:
                    sock.close()
                except OSError:
                    pass
        else:
            # This path handles cases where we don't have a persistent connection yet,
            # for example, broadcasting to new peers we haven't connected to yet,
            # or if the connection dropped just before this call.
            # For these cases, we open a temporary socket.
            host, port = peer_address.split(':')
            try:
                temp_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                temp_s.settimeout(2) # Short timeout for temporary connection
                temp_s.connect((host, int(port)))
                temp_s.sendall(message_str.encode('utf-8'))
                temp_s.close()
                logger.debug(f"Sent temp message to {peer_address}.")
            except Exception as e:
                logger.debug(f"Failed to send temp message to {peer_address}: {e}")
                pass


    def broadcast_message(self, message_type, data, exclude_peer=None):
        """
        Broadcasts a message to all connected peers using their persistent sockets.
        """
        # Create a copy of the peer addresses to iterate, as self.peers might change
        peers_to_broadcast = []
        with self.lock:
            peers_to_broadcast = list(self.peers.keys()) # Only get addresses

        for peer_address in peers_to_broadcast:
            if peer_address == exclude_peer:
                continue
            
            self.send_message(peer_address, message_type, data)


    def _process_message(self, message, sender_peer_address):
        """
        Processes a message received from a peer.
        """
        msg_type = message.get('type')
        msg_data = message.get('data')

        if msg_type == 'NEW_BLOCK':
            block = msg_data['block']
            logger.info(f"Received new block #{block['index']} from peer {sender_peer_address}.")
            # Check if received block is valid and extends our chain
            if block['index'] == self.blockchain.last_block['index'] + 1 and \
               self.blockchain.hash_block(self.blockchain.last_block) == block['previous_hash'] and \
               self.blockchain.is_chain_valid(self.blockchain.chain + [block]):
                
                self.blockchain.chain.append(block)
                self.blockchain.pending_transactions = [] # Clear pending transactions
                self.blockchain.save_chain()
                logger.info(f"Block #{block['index']} added to local chain.")
                
                # Propagate received block to other peers (excluding sender)
                if time.time() - self.last_block_broadcast_time > 5: # Rate limit
                    self.broadcast_message('NEW_BLOCK', {'block': block}, exclude_peer=sender_peer_address)
                    self.last_block_broadcast_time = time.time()
            else:
                logger.warning(f"Block #{block['index']} rejected (invalid or not the next block) from {sender_peer_address}. Requesting full chain...")
                # If block is invalid, request the full chain from the sender peer
                threading.Thread(target=self.request_chain_from_specific_peer, args=(sender_peer_address,)).start()
                # Also try to sync from any other known peers if direct request fails
                threading.Thread(target=self.sync_blockchain_from_known_peers).start() 

        elif msg_type == 'NEW_TRANSACTION':
            tx = msg_data['transaction']
            sender_pk = msg_data['public_key_str'] # Get public key from message
            # Add transaction to pending list if valid
            if self.blockchain.add_transaction(tx['sender'], tx['recipient'], tx['amount'], tx['signature'], sender_pk):
                logger.info(f"Received new transaction from {tx['sender'][:8]}... to {tx['recipient'][:8]}... for {tx['amount']} ARTH.")
                # Broadcast the transaction to other peers (excluding sender)
                self.broadcast_message('NEW_TRANSACTION', {'transaction': tx, 'public_key_str': sender_pk}, exclude_peer=sender_peer_address)


        elif msg_type == 'REQUEST_CHAIN':
            logger.debug(f"Received full chain request from {sender_peer_address}. Sending chain...") # Changed to debug level
            self.send_message(sender_peer_address, 'RESPOND_CHAIN', {'chain': self.blockchain.chain})

        elif msg_type == 'RESPOND_CHAIN':
            received_chain = msg_data['chain']
            logger.info(f"Received chain from peer {sender_peer_address}. Length: {len(received_chain)}")
            self.blockchain.replace_chain(received_chain)

        elif msg_type == 'NEW_PEER':
            peer_address = msg_data['address']
            if peer_address != f"{self.host}:{self.port}": # Don't try to connect to self
                if self.connect_to_peer(peer_address.split(':')[0], int(peer_address.split(':')[1])):
                    logger.info(f"Added and connected to new discovered peer: {peer_address}.")
                    # Broadcast this new peer to other peers (excluding sender)
                    self.broadcast_message('NEW_PEER', {'address': peer_address}, exclude_peer=sender_peer_address)


    def request_chain_from_specific_peer(self, peer_address):
        """
        Sends a request for the full blockchain to a specific peer using its persistent socket.
        """
        logger.debug(f"Requesting chain from {peer_address}...") # Changed to debug level
        self.send_message(peer_address, 'REQUEST_CHAIN', {})


    def connect_and_sync_initial(self):
        """
        Attempts to connect to bootstrap peers and then synchronize the blockchain.
        This runs in a separate thread.
        """
        logger.info("Attempting to connect to bootstrap peers and synchronize blockchain...")
        
        time.sleep(1) # Give a very short moment for server socket to bind

        connected_to_any_peer = False
        for peer_address in BOOTSTRAP_PEERS:
            host, port_str = peer_address.split(':')
            port = int(port_str)
            if self.connect_to_peer(host, port): # connect_to_peer returns True/False
                connected_to_any_peer = True
                time.sleep(1) # Small delay between connecting to different bootstrap peers

        if not connected_to_any_peer:
            logger.warning("Failed to connect to any bootstrap peers. Starting with local chain.")
        else:
            logger.info("Connected to bootstrap peers. Giving time for initial chain synchronization.")
            time.sleep(5) # Allow some time for initial chain sync from bootstrap
            
            # After initial bootstrap connections, trigger a comprehensive sync
            threading.Thread(target=self.sync_blockchain_from_known_peers).start()

    def sync_blockchain_from_known_peers(self):
        """
        Requests chain from all currently known peers to ensure latest chain.
        This is called periodically or when a block is rejected.
        """
        with self.lock: # Acquire lock before accessing self.peers
            if not self.peers:
                # logger.debug("No known peers for active synchronization.")
                return

            peers_to_sync_from = list(self.peers.keys()) # Get a copy of peer addresses

        logger.info("Triggering active blockchain synchronization from known peers...")
        current_longest_chain_len = len(self.blockchain.chain) 
        
        for peer_address in peers_to_sync_from:
            # Send request using the persistent send_message
            self.send_message(peer_address, 'REQUEST_CHAIN', {})
            time.sleep(0.5) # Give some time for response to potentially arrive and be processed

            # If the chain was replaced by a longer one, we can stop trying other peers for this sync round
            if len(self.blockchain.chain) > current_longest_chain_len:
                logger.info(f"Blockchain updated during active sync from {peer_address}.")
                return # Chain was replaced, no need to query other peers in this round
        
        logger.info("Active blockchain synchronization finished. Local chain is likely up-to-date or no longer peers responded with a longer chain.")

