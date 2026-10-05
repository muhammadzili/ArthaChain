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
MAX_PEERS = 50  # max total peers to connect to
PEER_DISCOVERY_INTERVAL = 30  # share peers periodically
MIN_PEER_SHARE_INTERVAL = 10  # throttle peer sharing
DISCOVERY_START_DELAY = 5  # first gossip goes out soon after start, not 30s in
MAX_SHARED_PEERS = 20  # cap one gossip message
SOCKET_RECV_TIMEOUT = 30  # recv timeout so a dead TCP link frees its reader thread
CONNECT_TIMEOUT = 10  # outbound connect timeout

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
        # What each peer told us to dial it on, keyed by our connection key. An
        # inbound socket arrives from an ephemeral port, which nobody can dial.
        self._peer_advertised = {}
        # The address other nodes should use for us. Resolved once, it never moves.
        self.advertised_address = self._resolve_advertised_address()
        # Peers added by the user at runtime; persisted so they survive restarts.
        self.manual_peers = []
        self.discovered_peers = []
        # Cache of block hashes we already hold, to ignore blocks we already have.
        self._known_block_hashes = set()
        # Highest height any peer has told us about, used to notice we fell behind.
        self.best_known_height = 0
        self._sync_lock = threading.Lock()
        self._last_block_request = 0.0
        self._last_escalation = 0.0
        self._last_peer_share = 0.0

        self._index_known_blocks()

        # Peer list: locally added peers take priority over the remote list.
        self._load_manual_peers()

        # Start maintenance threads
        threading.Thread(target=self._peer_maintenance_loop, daemon=True).start()
        threading.Thread(target=self._message_processing_loop, daemon=True).start()
        threading.Thread(target=self._peer_update_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        threading.Thread(target=self._peer_discovery_loop, daemon=True).start()

    # ------------------------------------------------------------------
    # Peer list management
    # ------------------------------------------------------------------

    def _load_manual_peers(self):
        saved = load_json_file(PEERS_FILE) or {}
        peers = saved.get('peers', []) if isinstance(saved, dict) else saved if isinstance(saved, list) else []
        discovered = saved.get('discovered_peers', []) if isinstance(saved, dict) else []
        with self.lock:
            if isinstance(saved, dict):
                self.manual_peers = list(peers)
                self.discovered_peers = list(discovered)
            else:
                self.manual_peers = list(peers) if peers else []
                self.discovered_peers = []

    def _save_manual_peers(self):
        with self.lock:
            save_json_file(PEERS_FILE, {
                'peers': list(self.manual_peers),
                'discovered_peers': list(self.discovered_peers)
            })

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
                'discovered': list(self.discovered_peers),
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

    def _normalize_peer(self, peer):
        parsed = self._parse_peer(peer)
        if parsed is None:
            return None
        host, port = parsed
        if self._is_self(host, port):
            return None
        return f'{host}:{port}'

    def _add_discovered_peer(self, peer):
        addr = self._normalize_peer(peer)
        if addr is None:
            return
        with self.lock:
            known = (
                self.manual_peers + self.discovered_peers + self.bootstrap_peers
                + list(self.peers.keys())
            )
            if addr in known:
                return
            # An inbound link is keyed by an ephemeral port, so the same node
            # reached through its advertised address looks new. Match on the
            # address the peer gave us to avoid dialling a peer we hold.
            if addr in self._peer_advertised.values():
                return
            if len(self.discovered_peers) >= MAX_PEERS:
                self.discovered_peers.pop(0)
            self.discovered_peers.append(addr)
            at_capacity = len(self.peers) >= MAX_PEERS
        self._save_manual_peers()
        # Try connect immediately, but not when already saturated: a single
        # gossip reply can name 20 peers, and dialing all of them blind turns
        # discovery into a connect storm.
        if not at_capacity:
            parsed = self._parse_peer(addr)
            if parsed:
                self.connect_to_peer(parsed[0], parsed[1])

    def _collect_shareable_peers(self):
        """
        Dialable addresses worth passing on.

        Connected peers contribute the address they advertised over HELLO. Without
        that we would gossip the ephemeral port their socket arrived on, and every
        node we told would try to dial a closed port.
        """
        peers = set()
        with self.lock:
            advertised = dict(self._peer_advertised)
            for connection_key in self.peers.keys():
                candidate = advertised.get(connection_key) or connection_key
                normalized = self._normalize_peer(candidate)
                if normalized:
                    peers.add(normalized)
            for group in (self.manual_peers, self.bootstrap_peers, self.discovered_peers):
                for peer in group:
                    normalized = self._normalize_peer(peer)
                    if normalized:
                        peers.add(normalized)
        return sorted(peers)[:MAX_SHARED_PEERS]

    def _share_peers(self, target_peer):
        """
        Offer our peer list to one peer.

        Throttled globally: unsolicited gossip is fire-and-forget, so without
        this every heartbeat on every link turns into a peer-list broadcast.
        """
        now = time.time()
        with self.lock:
            if now - self._last_peer_share < MIN_PEER_SHARE_INTERVAL:
                return False
            self._last_peer_share = now
        try:
            self.send_message(
                target_peer, 'PEERS', {'peers': self._collect_shareable_peers()}
            )
            return True
        except Exception as e:
            logger.debug(f'Could not share peers with {target_peer}: {e}')
            return False

    def _all_candidate_peers(self):
        """Peers worth connecting to, manual ones first, without duplicates."""
        candidates = []
        with self.lock:
            ordered = list(self.manual_peers) + list(self.discovered_peers) + list(self.bootstrap_peers)
        for peer in ordered:
            if peer not in candidates and len(candidates) < MAX_PEERS:
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
        """
        Keep the bootstrap list fresh.

        Fetches before the first sleep, not after: sleeping first left the node
        with an empty bootstrap list for a whole hour, so a fresh node could not
        discover anybody until a peer had been typed in by hand.
        """
        while self.is_running:
            self._fetch_peer_list()
            time.sleep(PEER_UPDATE_INTERVAL)

    def _peer_discovery_loop(self):
        """Walk our links and offer our peer list onward."""
        delay = DISCOVERY_START_DELAY
        while self.is_running:
            time.sleep(delay)
            delay = PEER_DISCOVERY_INTERVAL
            if not self.is_running:
                break
            with self.lock:
                peers = list(self.peers.keys())
            for peer in peers:
                # _share_peers keeps its own global interval, so this settles
                # into roughly one gossip message per PEER_DISCOVERY_INTERVAL.
                self._share_peers(peer)

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
                # _share_peers is globally throttled, so this stays quiet on
                # most ticks and only fires when the interval has elapsed.
                self._share_peers(peer)

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
        self._peer_advertised.pop(peer_address, None)
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
        # Both sides announce the address they can be dialled on, so neither has
        # to guess the other's port from the ephemeral one the socket arrived on.
        self._send_hello(peer_address)
        self._reader_loop(conn, peer_address)

    def _reader_loop(self, conn, peer_address):
        """
        Read newline-delimited JSON messages off one link until it closes.

        Every link owns one of these threads, so the socket carries a recv
        timeout: without it a peer that vanishes without a FIN pins a thread and
        keeps a dead entry alive until PEER_TIMEOUT fires.
        """
        buffer = b''
        conn.settimeout(SOCKET_RECV_TIMEOUT)
        try:
            while self.is_running:
                try:
                    data = conn.recv(65536)
                except socket.timeout:
                    # Silence is fine: the heartbeat loop and PEER_TIMEOUT judge
                    # liveness, not this thread.
                    continue
                except OSError as e:
                    logger.debug(f"Read error on {peer_address}: {e}")
                    break

                if not data:
                    break  # peer closed its end

                buffer += data
                # One TCP read can carry several messages, or half of one.
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if not line.strip():
                        continue
                    try:
                        message = json.loads(line.decode('utf-8'))
                    except (UnicodeDecodeError, ValueError):
                        logger.debug(f'Discarded malformed frame from {peer_address}.')
                        continue
                    with self.lock:
                        current = self.peers.get(peer_address)
                        # Only refresh the entry that still owns this socket.
                        if current is not None and current['socket'] is conn:
                            current['last_seen'] = time.time()
                    self.message_queue.put((message, peer_address))
        finally:
            self._retire_connection(peer_address, conn)

    def _retire_connection(self, peer_address, conn):
        """
        Drop a link and close its socket.

        The identity check matters: if this socket was already replaced by a
        reconnect, the live link must survive.
        """
        with self.lock:
            current = self.peers.get(peer_address)
            if current is not None and current['socket'] is conn:
                self._drop_peer(peer_address)
        try:
            conn.close()
        except OSError:
            pass
        logger.debug(f'Connection to {peer_address} closed.')

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
                # A PING carries the same height/tip as a PONG. Reading it too
                # means a node that only ever dials out still learns where the
                # network is, instead of reporting itself in sync at height 0.
                self._handle_pong(message.get('data', {}), sender_peer_address)
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

            elif msg_type == 'GET_PEERS':
                self.send_message(sender_peer_address, 'PEERS', {'peers': self._collect_shareable_peers()})

            elif msg_type == 'PEERS':
                self._handle_peers_message(message.get('data', {}))

            elif msg_type == 'HELLO':
                self._handle_hello(message.get('data', {}), sender_peer_address)

        except Exception as e:
            logger.error(f"Error processing {msg_type} message: {e}")

    def _resolve_advertised_address(self):
        """
        The address other nodes should dial us on.

        The listener is usually bound to 0.0.0.0, which is not routable, so ask
        the OS which local interface it would use to reach the internet. A
        connected UDP socket sends no packets.
        """
        host = self.host
        if host.lower() in _LOCAL_HOSTS:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(('8.8.8.8', 53))
                host = probe.getsockname()[0]
            except OSError:
                host = '127.0.0.1'
            finally:
                probe.close()
        return f'{host}:{self.port}'

    def _send_hello(self, peer_address):
        """Tell a peer the address it can reach us on."""
        try:
            self.send_message(peer_address, 'HELLO', {
                'address': self.advertised_address,
                'height': self.blockchain.get_current_block_height(),
            })
        except Exception as e:
            logger.debug(f'Could not send HELLO to {peer_address}: {e}')

    def _handle_hello(self, data, sender_peer_address):
        """
        Record the address a peer asked to be dialled on.

        Kept beside the connection rather than used as its key: the reader
        thread looks itself up by that key, so re-keying mid-flight would strand
        the link.
        """
        advertised = self._normalize_peer(data.get('address'))
        if not advertised or advertised == sender_peer_address:
            return
        with self.lock:
            if sender_peer_address not in self.peers:
                return
            # Is any live link already pointing at this same node? Our own
            # manual entry may say 127.0.0.1:5001 while the link we hold is
            # keyed that way but advertises the routable address, so both the
            # keys and the advertised values have to be checked. When a
            # duplicate turns up the older link wins: it is the one already
            # proven alive, and dropping the new socket makes its reader thread
            # stop on its own.
            if advertised in self.peers or advertised in self._peer_advertised.values():
                logger.debug(f'Dropping duplicate link {sender_peer_address} -> {advertised}.')
                self._drop_peer(sender_peer_address)
                return
            self._peer_advertised[sender_peer_address] = advertised
        logger.debug(f'Peer {sender_peer_address} is reachable at {advertised}.')

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
        """
        Open an outbound link to a peer.

        The socket is always cleaned up on failure. Registering the peer before
        the reader thread starts means a later failure has to undo that too,
        otherwise we leak a socket and leave a phantom entry that the
        maintenance loop waits PEER_TIMEOUT to notice.
        """
        if self._is_self(host, port):
            logger.debug(f'Skipping self-connection to {host}:{port}')
            return False

        peer_address = f"{host}:{port}"
        with self.lock:
            if peer_address in self.peers:
                return True
            # Already linked to this node under a different key: our own manual
            # or bootstrap entry says 127.0.0.1:5001 while the link we hold is
            # keyed by that node's real address. Dialling again would pile up a
            # duplicate connection every reconnect cycle.
            if peer_address in self._peer_advertised.values():
                logger.debug(f'Already linked to {peer_address} under another key.')
                return True

        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect((host, port))
            sock.settimeout(SOCKET_RECV_TIMEOUT)

            with self.lock:
                if peer_address in self.peers:
                    sock.close()
                    return True
                self.peers[peer_address] = {
                    'socket': sock,
                    'last_seen': time.time()
                }

            logger.debug(f"Connected to peer: {peer_address}")
            threading.Thread(
                target=self._reader_loop,
                args=(sock, peer_address),
                daemon=True
            ).start()
            threading.Thread(
                target=self._sync_with_peer,
                args=(peer_address,),
                daemon=True
            ).start()
            self._send_hello(peer_address)
            self.send_message(peer_address, 'GET_PEERS', {})
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to {peer_address}: {e}")
            if sock is not None:
                self._retire_connection(peer_address, sock)
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
        try:
            self.send_message(peer_address, 'GET_PEERS', {})
        except Exception:
            pass

    def connect_to_bootstraps(self):
        """
        Try every known peer once. Never recurses.

        Dials run in parallel: each has to wait out CONNECT_TIMEOUT, so trying
        them in series means a handful of dead addresses can block the live ones
        for minutes.
        """
        candidates = []
        for peer in self._all_candidate_peers():
            parsed = self._parse_peer(peer)
            if parsed is None:
                logger.warning(f"Invalid peer format, skipping: {peer}")
                continue
            if parsed not in candidates:
                candidates.append(parsed)

        results = {}

        def dial(parsed):
            host, port = parsed
            results[parsed] = self.connect_to_peer(host, port)

        workers = []
        for parsed in candidates:
            worker = threading.Thread(target=dial, args=(parsed,), daemon=True)
            worker.start()
            workers.append(worker)
        for worker in workers:
            worker.join(timeout=CONNECT_TIMEOUT + 5)

        connected = sum(1 for value in results.values() if value)
        self._prune_dead_discovered(results)
        if connected:
            # Let the handshake settle, then ask peers where they're at.
            threading.Thread(target=self._initial_sync, daemon=True).start()
        else:
            logger.warning("Could not connect to any known peers.")
        return connected

    def _prune_dead_discovered(self, results):
        """
        Forget discovered peers we just failed to reach.

        Learned addresses pile up and are never cleared, so a node that has been
        up for a while fills its peer list with dead entries. They then cost a
        dial on every reconnect and take up the gossip slots that live peers
        should be using. Manual and bootstrap entries are left alone: those were
        put there by the user or by the published list.
        """
        dead = [
            f'{host}:{port}' for (host, port), ok in results.items()
            if not ok and self._normalize_peer(f'{host}:{port}')
        ]
        if not dead:
            return
        with self.lock:
            before = len(self.discovered_peers)
            self.discovered_peers = [p for p in self.discovered_peers if p not in dead]
            changed = len(self.discovered_peers) != before
        if changed:
            self._save_manual_peers()
            logger.debug(f'Dropped {len(dead)} unreachable discovered peer(s).')

    def connect_and_sync_initial(self):
        """Connect to peers and request the chain. Runs on its own thread."""
        time.sleep(2)  # Give the server socket time to bind
        # Make sure the bootstrap list exists before the first dial attempt,
        # otherwise a slow network leaves us with nothing to try.
        self._fetch_peer_list()
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

    def _handle_peers_message(self, data):
        peers = data.get('peers') or []
        for p in peers:
            self._add_discovered_peer(p)

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