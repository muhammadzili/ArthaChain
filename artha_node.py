# artha_node.py

import socket
import threading
import json
import time
from artha_utils import json_serialize
from artha_blockchain import ArthaBlockchain

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
        self.peers = set() # Set to store peer addresses (host:port)
        self.server_socket = None
        self.is_running = False
        self.is_miner = is_miner # Flag to differentiate miner or app nodes
        self.last_block_broadcast_time = time.time() # To prevent excessive broadcasting

    def start(self):
        """
        Starts the node server and attempts to synchronize the blockchain.
        """
        self.is_running = True
        self.server_thread = threading.Thread(target=self._start_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        print(f"ArthaChain node started at {self.host}:{self.port}")
        
        # --- Modified: Automatically connect to bootstrap peers and then sync ---
        threading.Thread(target=self.connect_and_sync_initial).start()

    def stop(self):
        """
        Stops the node server.
        """
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        print(f"ArthaChain node at {self.host}:{self.port} stopped.")

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
                    peer_address = f"{addr[0]}:{addr[1]}" # Use actual connected peer address
                    # print(f"Incoming connection from {peer_address}")
                    threading.Thread(target=self._handle_client, args=(conn, addr)).start()
                except OSError as e:
                    if self.is_running:
                        print(f"Error accepting connection: {e}")
                    break
        except Exception as e:
            print(f"Failed to start server at {self.host}:{self.port}: {e}")
            self.is_running = False

    def _handle_client(self, conn, addr):
        """
        Handles communication with a connected client.
        """
        peer_address = f"{addr[0]}:{addr[1]}"
        self.peers.add(peer_address) # Add the connected peer
        buffer = b''
        try:
            while self.is_running:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    try:
                        message = json.loads(line.decode('utf-8'))
                        self._process_message(message, conn)
                    except json.JSONDecodeError:
                        print(f"Invalid JSON message from {peer_address}: {line}")
                        break
        except Exception as e:
            # print(f"Connection with {peer_address} disconnected: {e}")
            pass
        finally:
            self.peers.discard(peer_address) # Remove disconnected peer
            conn.close()

    def connect_to_peer(self, peer_host, peer_port):
        """
        Attempts to connect to another peer.
        """
        peer_address = f"{peer_host}:{peer_port}"
        if peer_address == f"{self.host}:{self.port}":
            # print("Cannot connect to self.") # Commented out to avoid clutter when connecting to self.
            return False # Return False if trying to connect to self

        if peer_address in self.peers:
            # print(f"Already connected to {peer_address}.")
            return False # Return False if already connected

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((peer_host, peer_port))
            self.peers.add(peer_address)
            print(f"Successfully connected to peer: {peer_address}")
            # Send a message to tell the peer our address
            self.send_message(s, 'NEW_PEER', {'address': f"{self.host}:{self.port}"})
            # Start a thread to handle messages from this peer
            threading.Thread(target=self._handle_client, args=(s, (peer_host, peer_port))).start()
            # Request chain from the newly connected peer
            self.request_chain(s)
            return True
        except Exception as e:
            # print(f"Failed to connect to peer {peer_address}: {e}")
            return False

    def send_message(self, target_socket_or_address, message_type, data):
        """
        Sends a message to a specific socket or peer address.
        If target is a string address, it will try to make a new connection.
        """
        message = {'type': message_type, 'data': data}
        message_str = json.dumps(message) + '\n'
        
        if isinstance(target_socket_or_address, socket.socket):
            try:
                target_socket_or_address.sendall(message_str.encode('utf-8'))
            except Exception as e:
                # print(f"Failed to send message to socket: {e}")
                pass # Suppress common socket errors for cleaner output
        elif isinstance(target_socket_or_address, str):
            # Try to connect and send message if target is a peer address
            host, port = target_socket_or_address.split(':')
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((host, int(port)))
                s.sendall(message_str.encode('utf-8'))
                s.close()
            except Exception as e:
                # print(f"Failed to send message to {target_socket_or_address}: {e}")
                pass # Suppress common socket errors
        else:
            print("Invalid message target.")

    def broadcast_message(self, message_type, data, exclude_peer=None):
        """
        Broadcasts a message to all connected peers.
        """
        # Create a copy of the set to iterate, as self.peers might change if connections drop
        current_peers = list(self.peers) 
        for peer_address in current_peers:
            if peer_address == exclude_peer:
                continue
            host, port = peer_address.split(':')
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((host, int(port)))
                self.send_message(s, message_type, data)
                s.close()
            except Exception as e:
                # print(f"Failed to broadcast message to {peer_address}: {e}")
                self.peers.discard(peer_address) # Remove peer that failed

    def _process_message(self, message, conn=None):
        """
        Processes a message received from a peer.
        """
        msg_type = message.get('type')
        msg_data = message.get('data')

        if msg_type == 'NEW_BLOCK':
            block = msg_data['block']
            print(f"\nReceived new block #{block['index']} from peer.")
            # Check if received block is valid and extends our chain
            if block['index'] == self.blockchain.last_block['index'] + 1 and \
               self.blockchain.hash_block(self.blockchain.last_block) == block['previous_hash'] and \
               self.blockchain.is_chain_valid(self.blockchain.chain + [block]):
                
                self.blockchain.chain.append(block)
                self.blockchain.pending_transactions = [] # Clear pending transactions
                self.blockchain.save_chain()
                print(f"Block #{block['index']} added to local chain.")
                
                # --- NEW: Propagate received block to other peers ---
                # Only broadcast if it's new and valid, and not immediately after receiving
                # to prevent broadcast storms.
                if time.time() - self.last_block_broadcast_time > 5:
                    self.broadcast_message('NEW_BLOCK', {'block': block})
                    self.last_block_broadcast_time = time.time()
            else:
                print(f"Block new #{block['index']} rejected (invalid or not the next block). Requesting full chain...")
                # If block is invalid, request the full chain from the sender peer (if known)
                if conn:
                    self.request_chain(conn)
                # Also try to sync from any other known peers if direct request fails or conn is None
                threading.Thread(target=self.sync_blockchain_on_startup).start() 

        elif msg_type == 'NEW_TRANSACTION':
            tx = msg_data['transaction']
            sender_pk = msg_data['public_key_str'] # Get public key from message
            # Add transaction to pending list if valid
            if self.blockchain.add_transaction(tx['sender'], tx['recipient'], tx['amount'], tx['signature'], sender_pk):
                print(f"Received new transaction from {tx['sender']} to {tx['recipient']} for {tx['amount']} ARTH.")
                # Broadcast the transaction to other peers (excluding sender)
                if conn:
                    self.broadcast_message('NEW_TRANSACTION', {'transaction': tx, 'public_key_str': sender_pk}, exclude_peer=f"{conn.getpeername()[0]}:{conn.getpeername()[1]}")
                else:
                    self.broadcast_message('NEW_TRANSACTION', {'transaction': tx, 'public_key_str': sender_pk})


        elif msg_type == 'REQUEST_CHAIN':
            print("Received full chain request. Sending chain...")
            self.send_message(conn, 'RESPOND_CHAIN', {'chain': self.blockchain.chain})

        elif msg_type == 'RESPOND_CHAIN':
            received_chain = msg_data['chain']
            print(f"Received chain from peer. Length: {len(received_chain)}")
            self.blockchain.replace_chain(received_chain)

        elif msg_type == 'NEW_PEER':
            peer_address = msg_data['address']
            if peer_address not in self.peers and peer_address != f"{self.host}:{self.port}":
                self.peers.add(peer_address)
                print(f"Added new discovered peer: {peer_address}. Total peers: {len(self.peers)}")
                # Attempt to connect to the newly discovered peer
                host, port = peer_address.split(':')
                self.connect_to_peer(host, int(port))
                # --- NEW: Broadcast this new peer to other peers ---
                # This helps propagate peer lists across the network
                if conn:
                    self.broadcast_message('NEW_PEER', {'address': peer_address}, exclude_peer=f"{conn.getpeername()[0]}:{conn.getpeername()[1]}")
                else:
                    self.broadcast_message('NEW_PEER', {'address': peer_address})

    def request_chain(self, conn):
        """
        Sends a request for the full blockchain to a specific peer.
        """
        self.send_message(conn, 'REQUEST_CHAIN', {})

    def connect_and_sync_initial(self):
        """
        Attempts to connect to bootstrap peers and then synchronize the blockchain.
        This runs in a separate thread.
        """
        print("Attempting to connect to bootstrap peers and synchronize blockchain...")
        
        # Give a very short moment for server socket to bind
        time.sleep(1) 

        connected_to_any_peer = False
        for peer_address in BOOTSTRAP_PEERS:
            host, port_str = peer_address.split(':')
            port = int(port_str)
            if self.connect_to_peer(host, port): # connect_to_peer now returns True/False
                connected_to_any_peer = True
                # Request chain immediately from bootstrap peer after connecting
                # self.request_chain(s) - This is already handled inside connect_to_peer._handle_client
                time.sleep(1) # Small delay between connecting to different bootstrap peers

        if not connected_to_any_peer:
            print("Failed to connect to any bootstrap peers. Starting with local chain.")
        else:
            # Give a bit more time for initial chain sync if a connection was made
            print("Connected to bootstrap peers. Giving time for chain synchronization.")
            time.sleep(5) # Allow some time for initial chain sync from bootstrap
            if len(self.blockchain.chain) > 1: # If successfully synced more than just genesis
                print("Initial blockchain synchronization from bootstrap peers complete.")
            else:
                print("Initial bootstrap connection made, but chain sync might be pending.")
        
        # After bootstrap, continue typical sync if needed (e.g., if chain is still short)
        self.sync_blockchain_from_known_peers()


    def sync_blockchain_from_known_peers(self):
        """
        Requests chain from all currently known peers to ensure latest chain.
        This is called periodically or when a block is rejected.
        """
        if not self.peers:
            # print("No known peers for active synchronization.")
            return

        print("Triggering active blockchain synchronization from known peers...")
        current_longest_chain = list(self.blockchain.chain) # Get current chain
        chain_replaced = False

        for peer_address in list(self.peers): # Iterate over a copy of the set
            host, port = peer_address.split(':')
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((host, int(port)))
                self.send_message(s, 'REQUEST_CHAIN', {})
                # Wait for response (in _handle_client thread, will call replace_chain)
                time.sleep(0.5) # Give some time for response to arrive and be processed
                s.close()
            except Exception as e:
                # print(f"Failed to sync from {peer_address} during active sync: {e}")
                self.peers.discard(peer_address) # Remove unresponsive peer
            
            # If the chain was replaced, we can stop trying other peers for this sync round
            if len(self.blockchain.chain) > len(current_longest_chain):
                chain_replaced = True
                break
        
        if chain_replaced:
            print("Blockchain updated during active sync.")
        else:
            print("Active blockchain synchronization finished. Local chain is likely up-to-date or no longer peers responded with a longer chain.")


    # Replace sync_blockchain_on_startup with the new comprehensive method
    sync_blockchain_on_startup = sync_blockchain_from_known_peers


