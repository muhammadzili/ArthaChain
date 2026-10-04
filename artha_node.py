# artha_node.py

import socket
import threading
import json
import time
import logging
from decimal import Decimal
from queue import Queue
import urllib.request

from artha_utils import load_json_file, save_json_file

logger = logging.getLogger(__name__)

# Configuration
GIST_URL = "https://gist.githubusercontent.com/muhammadzili/19fbb07822977ada20ef98cd3e5638c4/raw/c2e47995f7867427bf46a1bb1a3494ebea27a450/node.json"
PEER_UPDATE_INTERVAL = 3600  # 1 hour in seconds
HEARTBEAT_INTERVAL = 20  # send a PING this often to keep links alive
PEER_TIMEOUT = 75  # drop a peer after 3 missed heartbeats
RECONNECT_INTERVAL = 15  # retry bootstrap peers this often when disconnected
MAX_BLOCKS_PER_RESPONSE = 500  # cap a catch-up response so one reply cannot flood us
REQUEST_MIN_INTERVAL = 1.0  # minimum gap between catch-up requests
SYNC_ESCALATE_COOLDOWN = 20  # minimum gap between fork-resolution attempts
PEERS_FILE = 'peers.json'

# Addresses that mean "this machine", used to reject self-connections.
_LOCAL_HOSTS = {'127.0.0.1', 'localhost', '0.0.0.0', '::1', ''}


class ArthaNode:
    def __init__(self, host, port, blockchain_instance, is_miner=False, new_tx_event=None):
        self.host = host
        self.port = port
        self.blockchain = blockchain_instance
        self.peers = {}  # {peer_address: {'socket': socket, 'last_seen': timestamp}}
        self.server_socket = None
        self.is_running = True
        self.is_miner = is_miner
        self.lock = threading.RLock()
        self.new_tx_event = new_tx_event
        self.message_queue = Queue()
        self.last_peer_update = 0
        self.bootstrap_peers = []
        # Peers added by the user at runtime; persisted so they survive restarts.
        self.manual_peers = []
        # Cache of block hashes we already hold, to ignore blocks we already have.
        self._known_block_hashes = set()
        # Highest height any peer has told us about, used to notice we fell behind.
        self.best_known_height = 0
        self._sync_lock = threading.Lock()
        self._last_block_request = 0.0
        self._last_escalation = 0.0

        self._index_known_blocks()

        # Peer list: locally added peers take priority over the remote list.
        self._load_manual_peers()

        # Start maintenance threads
        threading.Thread(target=self._peer_maintenance_loop, daemon=True).start()
        threading.Thread(target=self._message_processing_loop, daemon=True).start()
        threading.Thread(target=self._peer_update_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    # ------------------------------------------------------------------
    # Peer list management
    # ------------------------------------------------------------------

    def _load_manual_peers(self):
        saved = load_json_file(PEERS_FILE) or {}
        peers = saved.get('peers', []) if isinstance(saved, dict) else []
        with self.lock:
            self.manual_peers = list(peers)

    def _save_manual_peers(self):
        with self.lock:
            save_json_file(PEERS_FILE, {'peers': list(self.manual_peers)})

    def add_peer(self, peer):
        """
        Add a peer given as "host:port". Returns (ok, message).
        The peer is remembered across restarts and connected to right away.
        """
        parsed = self._parse_peer(peer)
        if parsed is None:
            return False, "Format peer tidak valid. Gunakan host:port (contoh 127.0.0.1:5001)."

        host, port = parsed
        address = f'{host}:{port}'

        if self._is_self(host, port):
            return False, "Peer tersebut adalah node ini sendiri."

        with self.lock:
            if address in self.manual_peers:
                return False, f"Peer {address} sudah ada di daftar."
            self.manual_peers.append(address)
        self._save_manual_peers()

        if self.connect_to_peer(host, port):
            return True, f"Peer {address} ditambahkan dan terhubung."
        # Keep it in the list; the reconnect loop will retry it later.
        return True, f"Peer {address} disimpan. Akan dicoba koneksi ulang otomatis."

    def remove_peer(self, peer):
        """Remove a manually added peer. Returns (ok, message)."""
        with self.lock:
            normalized = [
                p for p in self.manual_peers
                if p != peer and p != peer.strip()
            ]
            removed = len(normalized) != len(self.manual_peers)
            self.manual_peers = normalized
        if removed:
            self._save_manual_peers()
            return True, f"Peer {peer} dihapus."
        return False, f"Peer {peer} tidak ada di daftar."

    def get_peer_list(self):
        """All known peers: connected, manually added, and from the remote list."""
        with self.lock:
            return {
                'connected': list(self.peers.keys()),
                'manual': list(self.manual_peers),
                'bootstrap': list(self.bootstrap_peers),
            }

    @staticmethod
    def _parse_peer(peer):
        """Parse "host:port" into (host, int port), or None if malformed."""
        if not peer or not isinstance(peer, str):
            return None
        peer = peer.strip().replace(' ', '')
        if peer.count(':') != 1:
            return None
        host, port_str = peer.split(':')
        if not host or not port_str.isdigit():
            return None
        port = int(port_str)
        if not 1 <= port <= 65535:
            return None
        return host, port

    def _is_self(self, host, port):
        """True when host:port points at this very node."""
        if port != self.port:
            return False
        return host.lower() in _LOCAL_HOSTS or host == self.host

    def _all_candidate_peers(self):
        """Peers worth connecting to, manual ones first, without duplicates."""
        candidates = []
        with self.lock:
            ordered = list(self.manual_peers) + list(self.bootstrap_peers)
        for peer in ordered:
            if peer not in candidates:
                candidates.append(peer)
        return candidates

    def _fetch_peer_list(self):
        """Fetch the latest peer list from GitHub Gist"""
        try:
            with urllib.request.urlopen(GIST_URL, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                with self.lock:
                    remote_peers = data.get('bootstrap_peers', []) or []
                    # Never let the remote list drop peers the user added by hand.
                    self.bootstrap_peers = [
                        p for p in remote_peers if p not in self.manual_peers
                    ]
                    self.last_peer_update = time.time()
                logger.debug(f"Updated peer list from Gist: {self.bootstrap_peers}")
                return True
        except Exception as e:
            logger.warning(f"Failed to fetch peer list: {e}")
            with self.lock:
                if not self.bootstrap_peers:
                    self.bootstrap_peers = ['127.0.0.1:5001']
            return False

    def _peer_update_loop(self):
        """Periodically update the peer list from Gist"""
        while self.is_running:
            time.sleep(PEER_UPDATE_INTERVAL)
            if self.is_running:
                self._fetch_peer_list()

    # ------------------------------------------------------------------
    # Heartbeat & maintenance
    # ------------------------------------------------------------------

    def _heartbeat_loop(self):
        """
        Ping peers proactively. Without this, an idle connection sees no inbound
        traffic, gets reaped as a dead peer, and the node silently stops hearing
        about new blocks.
        """
        while self.is_running:
            time.sleep(HEARTBEAT_INTERVAL)
            if not self.is_running:
                break
            with self.lock:
                peers = list(self.peers.keys())
            for peer in peers:
                self.send_message(peer, 'PING', self._chain_summary())

    def _peer_maintenance_loop(self):
        """Handle peer health checks and reconnections"""
        while self.is_running:
            time.sleep(RECONNECT_INTERVAL)
            if not self.is_running:
                break

            current_time = time.time()
            dead_peers = []
            with self.lock:
                for peer, data in self.peers.items():
                    if current_time - data['last_seen'] > PEER_TIMEOUT:
                        dead_peers.append(peer)
                for peer in dead_peers:
                    self._drop_peer(peer)
                    logger.warning(f"Peer {peer} timed out and was removed")

            # Reconnect if we have no peers. This never recurses, it just retries
            # on the next tick of this loop.
            with self.lock:
                have_peers = bool(self.peers)
            if not have_peers and self.is_running:
                logger.info("No active peers, attempting to reconnect...")
                self.connect_to_bootstraps()

    def _drop_peer(self, peer_address):
        """Close and forget a peer. Caller must hold self.lock."""
        peer_data = self.peers.pop(peer_address, None)
        if peer_data:
            try:
                peer_data['socket'].close()
            except OSError:
                pass

    def _message_processing_loop(self):
        """Process incoming messages from the queue"""
        while self.is_running:
            try:
                message, peer_address = self.message_queue.get(timeout=1)
                self._process_message(message, peer_address)
            except Exception:
                continue

    # ------------------------------------------------------------------
    # Server
    # ------------------------------------------------------------------

    def start(self):
        """Start the node server"""
        threading.Thread(target=self._start_server, daemon=True).start()
        logger.info(f"ArthaChain node started at {self.host}:{self.port}")
        threading.Thread(target=self.connect_and_sync_initial, daemon=True).start()

    def stop(self):
        """Stop the node gracefully"""
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass

        with self.lock:
            for peer in list(self.peers.keys()):
                self._drop_peer(peer)
            self.peers.clear()

        logger.info(f"Node at {self.host}:{self.port} stopped.")

    def _start_server(self):
        """Start the TCP server"""
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
            try:
                self.server_socket.close()
            except OSError:
                pass

    def _handle_client(self, conn, peer_address):
        """Handle incoming client connections"""
        with self.lock:
            if peer_address in self.peers:
                # Duplicate connection to a peer we already track.
                try:
                    conn.close()
                except OSError:
                    pass
                return
            self.peers[peer_address] = {
                'socket': conn,
                'last_seen': time.time()
            }

        logger.debug(f"Connection established with {peer_address}")
        # Greet inbound peers immediately so both sides learn each other's height
        # and whoever is behind can start pulling blocks.
        threading.Thread(
            target=self._sync_with_peer,
            args=(peer_address,),
            daemon=True
        ).start()
        buffer = b''

        try:
            while self.is_running:
                data = conn.recv(65536)
                if not data:
                    break

                buffer += data

                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line:
                        try:
                            message = json.loads(line.decode('utf-8'))
                        except json.JSONDecodeError:
                            logger.debug(f"Invalid JSON from {peer_address}")
                            continue
                        with self.lock:
                            if peer_address in self.peers:
                                self.peers[peer_address]['last_seen'] = time.time()
                        self.message_queue.put((message, peer_address))
        except ConnectionResetError:
            logger.info(f"Connection reset by {peer_address}")
        except Exception as e:
            logger.error(f"Error handling client {peer_address}: {e}")
        finally:
            with self.lock:
                if self.peers.get(peer_address, {}).get('socket') is conn:
                    self._drop_peer(peer_address)
            try:
                conn.close()
            except OSError:
                pass
            logger.info(f"Connection to {peer_address} closed.")

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    def _process_message(self, message, sender_peer_address):
        """Process incoming messages"""
        msg_type = message.get('type')
        if not msg_type:
            return

        try:
            if msg_type == 'PING':
                self.send_message(sender_peer_address, 'PONG', self._chain_summary())

            elif msg_type == 'PONG':
                self._handle_pong(message.get('data', {}), sender_peer_address)

            elif msg_type == 'NEW_TRANSACTION':
                self._handle_new_transaction(message['data'], sender_peer_address)

            elif msg_type == 'NEW_BLOCK':
                self._handle_new_block_message(message['data'], sender_peer_address)

            elif msg_type == 'GET_BLOCKS':
                self._serve_blocks_request(message['data'], sender_peer_address)

            elif msg_type == 'BLOCKS':
                self._handle_blocks_response(message['data'])

            elif msg_type == 'REQUEST_CHAIN':
                self.send_message(sender_peer_address, 'RESPOND_CHAIN', {
                    'height': self.blockchain.get_current_block_height(),
                    'chain': self.blockchain.chain,
                })

            elif msg_type == 'RESPOND_CHAIN':
                self._handle_chain_response(message['data'])

        except Exception as e:
            logger.error(f"Error processing {msg_type} message: {e}")

    def _chain_summary(self):
        """Height plus tip hash, so peers can spot lag and forks from a heartbeat."""
        with self.blockchain.chain_lock:
            last = self.blockchain.last_block
            height = self.blockchain.get_current_block_height()
            tip = self.blockchain.hash_block(last) if last else None
        return {'height': height, 'tip': tip}

    def _handle_pong(self, data, sender_peer_address):
        """React to a heartbeat: catch up if the peer is ahead, fork-check if not."""
        peer_height = data.get('height')
        height = self.blockchain.get_current_block_height()

        if isinstance(peer_height, int):
            if peer_height > self.best_known_height:
                self.best_known_height = peer_height
            if peer_height > height:
                # Peer is ahead: pull the blocks we are missing.
                self.request_blocks(height + 1, exclude_peer=sender_peer_address)
                return

        peer_tip = data.get('tip')
        last = self.blockchain.last_block
        if peer_tip and last and peer_height == height:
            if peer_tip != self.blockchain.hash_block(last):
                # Same height, different tip: we are on competing branches.
                logger.debug(
                    f'PeerReports a different tip at height {height} (fork). Comparing chains.'
                )
                self._escalate_sync(sender_peer_address)

    def _handle_new_transaction(self, tx_data, sender_peer_address):
        tx = tx_data['transaction']
        pk = tx_data['public_key_str']
        if self.blockchain.add_transaction(
            tx['sender'], tx['recipient'], Decimal(tx['amount']),
            tx['signature'], pk, tx.get('timestamp')
        ):
            if self.new_tx_event:
                self.new_tx_event.set()
            self.broadcast_message('NEW_TRANSACTION', tx_data, exclude_peer=sender_peer_address)

    def _handle_new_block_message(self, data, sender_peer_address):
        """Accept a block, then relay it only if we truly stored it."""
        block = data['block']
        if self.handle_new_block(block):
            self.broadcast_message('NEW_BLOCK', data, exclude_peer=sender_peer_address)
        return

    def _serve_blocks_request(self, data, sender_peer_address):
        """Answer GET_BLOCKS with the requested slice of our chain."""
        try:
            start = int(data.get('from_index', 0))
        except (TypeError, ValueError):
            return

        with self.blockchain.chain_lock:
            chain_copy = list(self.blockchain.chain)

        if start < 0 or start >= len(chain_copy):
            self.send_message(sender_peer_address, 'BLOCKS', {
                'from_index': start,
                'blocks': [],
                'height': len(chain_copy) - 1,
                'to': sender_peer_address,
            })
            return

        blocks = chain_copy[start:start + MAX_BLOCKS_PER_RESPONSE]
        self.send_message(sender_peer_address, 'BLOCKS', {
            'from_index': start,
            'blocks': blocks,
            'height': len(chain_copy) - 1,
            # Echo the requester so it can skip re-broadcasting back to us.
            'to': sender_peer_address,
        })

    def _handle_blocks_response(self, data):
        """
        Apply a batch of blocks that should extend our tip.

        Blocks we already hold are skipped, not treated as a failure. The same
        block reaches us twice in a normal network: once through catch-up and
        once through gossip. Aborting on the first duplicate used to re-request
        from a cursor that was already behind our tip, which looped forever.
        """
        blocks = data.get('blocks') or []
        if not blocks:
            return

        sender = data.get('to')
        added = 0
        for block in blocks:
            if self._has_block(block):
                continue
            if not self.handle_new_block(block):
                # This block does not extend our tip: our branch and the peer's
                # genuinely differ, so compare whole chains instead of looping.
                self._escalate_sync(sender)
                return
            added += 1
            self.broadcast_message('NEW_BLOCK', {'block': block}, exclude_peer=sender)

            if added:
                height = self.blockchain.get_current_block_height()
                logger.debug(f'Catch-up applied {added} block(s). Height: {height}')
                # Still behind? Keep pulling until caught up.
                if self.best_known_height > height:
                    self.request_blocks(height + 1)

    def _handle_chain_response(self, data):
        chain = data.get('chain')
        if not chain:
            return
        if self.blockchain.replace_chain(chain):
            logger.debug(
                f'Synced from peer up to block #{self.blockchain.get_current_block_height()}'
            )
            # Fork resolved: pull anything newer the winner already has.
            self.request_blocks(self.blockchain.get_current_block_height() + 1)

    # ------------------------------------------------------------------
    # Networking
    # ------------------------------------------------------------------

    def send_message(self, peer_address, message_type, data):
        """Send a message to a specific peer"""
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
                if self.peers.get(peer_address, {}).get('socket') is peer_data['socket']:
                    self._drop_peer(peer_address)
            return False

    def broadcast_message(self, message_type, data, exclude_peer=None):
        """Broadcast a message to all peers except the excluded one"""
        with self.lock:
            peers_copy = list(self.peers.keys())

        for peer in peers_copy:
            if peer != exclude_peer:
                self.send_message(peer, message_type, data)

    def connect_to_peer(self, host, port):
        """Connect to a peer node"""
        if self._is_self(host, port):
            logger.debug(f'Skipping self-connection to {host}:{port}')
            return False

        peer_address = f"{host}:{port}"
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
            logger.debug(f"Connected to peer: {peer_address}")
            # A fresh link is the moment to reconcile: ask right away instead of
            # waiting for the next block to be broadcast.
            threading.Thread(
                target=self._sync_with_peer,
                args=(peer_address,),
                daemon=True
            ).start()
            return True
        except Exception as e:
            logger.debug(f"Failed to connect to {peer_address}: {e}")
            return False

    def _sync_with_peer(self, peer_address, delay=1.5):
        """Once a new link is live, ask that peer for the blocks we lack."""
        time.sleep(delay)
        if not self.is_running:
            return
        with self.lock:
            if peer_address not in self.peers:
                return
        height = self.blockchain.get_current_block_height()
        self.send_message(peer_address, 'PING', self._chain_summary())
        self.send_message(peer_address, 'GET_BLOCKS', {'from_index': height + 1})

    def connect_to_bootstraps(self):
        """Try every known peer once. Never recurses."""
        connected = 0
        for peer in self._all_candidate_peers():
            if not self.is_running:
                break
            parsed = self._parse_peer(peer)
            if parsed is None:
                logger.warning(f"Invalid peer format, skipping: {peer}")
                continue
            host, port = parsed
            if self.connect_to_peer(host, port):
                connected += 1

        if connected:
            # Let the handshake settle, then ask peers where they're at.
            threading.Thread(target=self._initial_sync, daemon=True).start()
        else:
            logger.warning("Could not connect to any known peers.")
        return connected

    def connect_and_sync_initial(self):
        """Connect to peers and request the chain. Runs on its own thread."""
        time.sleep(2)  # Give the server socket time to bind
        self.connect_to_bootstraps()

    def _initial_sync(self):
        """Ask peers for their height, then pull whatever we are missing."""
        time.sleep(1)
        self.broadcast_message('PING', self._chain_summary())
        self.trigger_full_resync()

    def request_blocks(self, from_index, exclude_peer=None, force=False):
        """
        Ask a peer to send us blocks starting at from_index.

        Throttled, because several paths (heartbeat, new block, catch-up) can
        want the same blocks at once and an unthrottled version turns a slow
        link into a request storm.
        """
        if not force:
            now = time.time()
            with self.lock:
                if now - self._last_block_request < REQUEST_MIN_INTERVAL:
                    return False
                self._last_block_request = now

        with self.lock:
            peers = [p for p in self.peers.keys() if p != exclude_peer]
        if not peers:
            return False
        # One peer is enough and avoids N duplicate catch-up batches.
        self.send_message(peers[0], 'GET_BLOCKS', {'from_index': from_index})
        return True

    def _escalate_sync(self, peer=None, cooldown=SYNC_ESCALATE_COOLDOWN):
        """
        Our tip does not line up with a peer's branch. Compare whole chains so
        the fork can actually be resolved, instead of re-requesting the one
        block we keep rejecting. Rate limited so it cannot become a loop.
        """
        now = time.time()
        with self.lock:
            if now - self._last_escalation < cooldown:
                return False
            self._last_escalation = now

        logger.debug(
            'Blok dari peer tidak menyambung ke chain lokal, '
            'meminta chain penuh untuk resolusi fork.'
        )
        height = self.blockchain.get_current_block_height()
        self.request_blocks(height + 1, exclude_peer=peer, force=True)
        if peer:
            self.send_message(peer, 'REQUEST_CHAIN', {})
        else:
            self.trigger_full_resync()
        return True

    def trigger_full_resync(self):
        """Request the blockchain from peers."""
        self.request_blocks(self.blockchain.get_current_block_height() + 1, force=True)
        # Also ask for a full chain so we can recover from a fork.
        with self.lock:
            peers = list(self.peers.keys())
        for peer in peers:
            self.send_message(peer, 'REQUEST_CHAIN', {})

    # ------------------------------------------------------------------
    # Chain logic
    # ------------------------------------------------------------------

    def _index_known_blocks(self):
        """Cache the hashes of blocks we already hold, to detect duplicates."""
        try:
            with self.blockchain.chain_lock:
                self._known_block_hashes = {
                    self.blockchain.hash_block(b) for b in self.blockchain.chain
                }
        except Exception as e:
            logger.warning(f'Could not index known blocks: {e}')
            self._known_block_hashes = set()

    def _has_block(self, block):
        try:
            return self.blockchain.hash_block(block) in self._known_block_hashes
        except Exception:
            return False

    def _remember_block(self, block):
        try:
            self._known_block_hashes.add(self.blockchain.hash_block(block))
        except Exception:
            pass

    def handle_new_block(self, block):
        """
        Process a block from the network. Returns True only when the block was
        actually appended, so callers never relay a block we did not store.
        """
        try:
            if self._has_block(block):
                return False

            height = self.blockchain.get_current_block_height()
            if block.get('index') != height + 1:
                if block.get('index', 0) > height + 1:
                    logger.debug(
                        f'Gap detected: have #{height}, got #{block.get("index")}. Requesting catch-up.'
                    )
                    self.request_blocks(height + 1)
                else:
                    # A block at a height we already have, with a hash we do not
                    # have: the peer is mining on a competing branch. Comparing
                    # whole chains is the only way to settle that.
                    logger.debug(
                        f'Block #{block.get("index")} from a competing branch '
                        f'(local tip #{height}). Resolving fork.'
                    )
                    self._escalate_sync()
                return False

            if self.blockchain.add_block(block):
                self._remember_block(block)
                if self.best_known_height < self.blockchain.get_current_block_height():
                    self.best_known_height = self.blockchain.get_current_block_height()
                return True
            return False
        except Exception as e:
            logger.error(f"Error handling new block: {e}")
            return False

    def handle_own_new_block(self, block):
        """Handle a block mined by this node. Returns True if it was stored."""
        stored = self.blockchain.add_block(block)
        if stored:
            self._remember_block(block)
            if self.best_known_height < self.blockchain.get_current_block_height():
                self.best_known_height = self.blockchain.get_current_block_height()
        return stored

    def invalidate_last_blocks(self, n=1):
        """Expose blockchain unvalidate/invalidate for RPC/admin usage."""
        try:
            return self.blockchain.invalidate_last_blocks(n)
        except Exception as e:
            logger.error(f"Error invalidating blocks: {e}")
            return False

    def unvalidate_last_blocks(self, n=1):
        return self.invalidate_last_blocks(n)

    def get_pending_transactions(self):
        try:
            return self.blockchain.get_pending_transactions()
        except Exception:
            return []

    def get_sync_status(self):
        """Snapshot of how this node compares to the network."""
        height = self.blockchain.get_current_block_height()
        with self.lock:
            connected = len(self.peers)
        return {
            'height': height,
            'peers': connected,
            'best_known_height': max(self.best_known_height, height),
            'in_sync': height >= self.best_known_height,
        }