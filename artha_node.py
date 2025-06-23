# artha_node.py

import socket
import threading
import json
import time
from artha_utils import json_serialize
from artha_blockchain import ArthaBlockchain

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
        # Try to synchronize blockchain from existing peers
        threading.Thread(target=self.sync_blockchain_on_startup).start()

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
                    # print(f"Incoming connection from {addr}")
                    threading.Thread(target=self._handle_client, args=(conn, addr)).start()
                except OSError as e:
                    if self.is_running: # Only print if server is still supposed to be running
                        print(f"Error accepting connection: {e}")
                    break # Exit loop if socket is closed
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
                        break # Skip this part and continue
        except Exception as e:
            # print(f"Connection with {peer_address} disconnected: {e}")
            pass # Don't print normal disconnection errors
        finally:
            self.peers.discard(peer_address) # Remove disconnected peer
            conn.close()

    def connect_to_peer(self, peer_host, peer_port):
        """
        Attempts to connect to another peer.
        """
        peer_address = f"{peer_host}:{peer_port}"
        if peer_address == f"{self.host}:{self.port}":
            print("Cannot connect to self.")
            return

        if peer_address in self.peers:
            print(f"Already connected to {peer_address}.")
            return

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
        except Exception as e:
            print(f"Failed to connect to peer {peer_address}: {e}")

    def send_message(self, target_socket_or_address, message_type, data):
        """
        Sends a message to a specific socket or peer address.
        If target is a string address, it will attempt to make a new connection.
        """
        message = {'type': message_type, 'data': data}
        message_str = json.dumps(message) + '\n'
        
        if isinstance(target_socket_or_address, socket.socket):
            try:
                target_socket_or_address.sendall(message_str.encode('utf-8'))
            except Exception as e:
                print(f"Failed to send message to socket: {e}")
        elif isinstance(target_socket_or_address, str):
            # Try to connect and send message if target is a peer address
            host, port = target_socket_or_address.split(':')
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((host, int(port)))
                s.sendall(message_str.encode('utf-8'))
                s.close()
            except Exception as e:
                print(f"Failed to send message to {target_socket_or_address}: {e}")
        else:
            print("Invalid message target.")

    def broadcast_message(self, message_type, data, exclude_peer=None):
        """
        Broadcasts a message to all connected peers.
        """
        for peer_address in list(self.peers): # Use list to avoid issues when modifying set during iteration
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
            # Only add the block if it's the next block and valid
            if block['index'] == self.blockchain.last_block['index'] + 1 and \
               self.blockchain.hash_block(self.blockchain.last_block) == block['previous_hash'] and \
               self.blockchain.is_chain_valid(self.blockchain.chain + [block]): # Verify new block
                self.blockchain.chain.append(block)
                self.blockchain.pending_transactions = [] # Clear pending transactions
                self.blockchain.save_chain()
                print(f"Block #{block['index']} added to local chain.")
                # Broadcast the block to other peers (excluding sender)
                # self.broadcast_message('NEW_BLOCK', {'block': block}, exclude_peer=f"{conn.getpeername()[0]}:{conn.getpeername()[1]}")
                # Limit block broadcast frequency to prevent infinite loops
                if time.time() - self.last_block_broadcast_time > 5: # Limit broadcast to every 5 seconds
                    self.broadcast_message('NEW_BLOCK', {'block': block})
                    self.last_block_broadcast_time = time.time()
            else:
                print(f"New block #{block['index']} rejected (invalid or not the next block). Requesting full chain...")
                if conn: # Request full chain from peer if block is invalid
                    self.request_chain(conn)
                else: # If no specific connection (e.g. from broadcast), request from any peer
                    threading.Thread(target=self.sync_blockchain_on_startup).start() # Trigger sync

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
                # Request chain from new peer
                host, port = peer_address.split(':')
                self.connect_to_peer(host, int(port))
                # Inform other peers about this new peer
                self.broadcast_message('NEW_PEER', {'address': peer_address}, exclude_peer=f"{conn.getpeername()[0]}:{conn.getpeername()[1]}" if conn else None)

    def request_chain(self, conn):
        """
        Sends a request for the full blockchain to a specific peer.
        """
        self.send_message(conn, 'REQUEST_CHAIN', {})

    def sync_blockchain_on_startup(self):
        """
        Attempts to synchronize the blockchain from existing peers on startup.
        """
        print("Attempting to synchronize blockchain from peers...")
        # Give a little time for peer connections to establish
        time.sleep(2)
        if not self.peers:
            print("No known peers for synchronization. Starting with local chain.")
            return

        for peer_address in list(self.peers):
            host, port = peer_address.split(':')
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((host, int(port)))
                self.request_chain(s)
                s.close()
                time.sleep(0.5) # Give time to receive response
            except Exception as e:
                # print(f"Failed to sync from {peer_address}: {e}")
                self.peers.discard(peer_address)
            if len(self.blockchain.chain) > 1: # If already synced (more than genesis block)
                print("Initial blockchain synchronization complete.")
                return

        if len(self.blockchain.chain) == 1:
            print("Failed to synchronize blockchain from known peers. Starting with genesis block.")

