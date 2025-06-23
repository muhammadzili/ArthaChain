# ArthaChain

A simplified, decentralized cryptocurrency built with Python, inspired by the early days of Bitcoin. ArthaChain allows users to manage their wallets, send transactions, and mine new blocks on a peer-to-peer (P2P) network.

---

## Table of Contents

* [About ArthaChain](#about-arthachain)
* [How It Works](#how-it-works)
    * [Core Components](#core-components)
    * [Blockchain & Transactions](#blockchain--transactions)
    * [Wallet & Addresses](#wallet--addresses)
    * [Mining & Supply](#mining--supply)
    * [Peer-to-Peer Network](#peer-to-peer-network)
* [Getting Started](#getting-started)
    * [Prerequisites](#prerequisites)
    * [Installation](#installation)
    * [Running ArthaChain](#running-arthachain)
* [Usage](#usage)
    * [ArthaChain App (`artha_app.py`)](#arthachain-app-artha_apppy)
    * [ArthaChain Miner (`artha_miner.py`)](#arthachain-miner-artha_minerpy)
* [Project Structure](#project-structure)
* [Limitations & Simplifications](#limitations--simplifications)
* [Contributing](#contributing)
* [License](#license)

---

## About ArthaChain

ArthaChain is a minimalistic blockchain implementation designed to demonstrate the fundamental principles of a decentralized cryptocurrency. It features:

* **Decentralized Network:** Uses a basic P2P network for node communication and data synchronization, ensuring no single point of control.
* **Wallet Management:** Securely stores private and public keys locally in a `wallet.dat` file, giving users full control over their funds.
* **Transactions:** Allows users to send Artha (ARTH) securely between addresses, with transactions digitally signed for authenticity.
* **Mining:** Miners create new blocks approximately every minute, adding transactions and receiving newly minted ARTH as a block reward.
* **Fixed Supply:** A predefined and immutable total supply of 30,000,000 ARTH, ensuring scarcity.

It's an excellent educational tool for understanding core blockchain concepts like distributed ledgers, cryptography, and consensus mechanisms without the overwhelming complexity of a full-scale production system.

---

## How It Works

ArthaChain operates on several interconnected Python modules, each playing a crucial role in maintaining the distributed ledger.

### Core Components

* **`artha_utils.py`**: This module provides essential utility functions. It handles **cryptographic hashing** (using SHA256) for ensuring the integrity of blocks and transactions, and **consistent JSON serialization** to guarantee that the same data always produces the same unique hash.
* **`artha_wallet.py`**: This module is responsible for user wallet management. It handles the **generation of RSA key pairs** (a secure method for public and private keys), **signing of transactions** with the user's private key (proving ownership), and **verification of these digital signatures** using the public key. All wallet data, including keys, is securely stored locally in a `wallet.dat` file.
* **`artha_blockchain.py`**: As the core of ArthaChain, this module defines the **blockchain's fundamental structure and rules**. It manages the ordered **chain of blocks**, keeps track of **pending transactions** waiting to be included in a block, calculates **user balances** across the entire chain, and performs crucial **block and transaction validation** to ensure network integrity. Critically, it also sets the **immutable total supply (30,000,000 ARTH)** and the **block reward (50 ARTH)** for miners.
* **`artha_node.py`**: This module implements the **Peer-to-Peer (P2P) networking logic**. It enables different ArthaChain applications (apps and miners) to **discover, connect, and communicate with each other**. Through this network, nodes **broadcast new blocks** that have been mined and **new transactions** initiated by users. It also facilitates **blockchain synchronization**, ensuring all participating nodes have the most up-to-date and valid copy of the ledger.
* **`artha_app.py`**: This is the **primary user application**, providing a simple command-line interface. Users can **view their wallet address and balance**, **send ARTH** to other addresses, **connect to other nodes (peers)** to join the network, and **inspect the full blockchain** or pending transactions.
* **`artha_miner.py`**: This is the **mining application**. It constantly monitors the network and, approximately **every minute**, attempts to **create a new block**. When a block is successfully mined, it includes any pending transactions and adds a **coinbase transaction** (the 50 ARTH block reward) to the miner's address. The miner then broadcasts this newly found block to the entire P2P network.

### Blockchain & Transactions

ArthaChain's blockchain is a **secure, chronological, and tamper-resistant linked list of blocks**. Each block is a data container holding:

* An **`index`**: Its sequential position in the chain.
* A **`timestamp`**: The exact time the block was created.
* A list of **`transactions`**: Records of ARTH transfers between users.
* A **`proof`**: A simplified value (for this example, a timestamp) used in the "mining" process. In real blockchains, this would be the solution to a complex cryptographic puzzle (Proof of Work).
* A **`previous_hash`**: The cryptographic hash of the block immediately preceding it. This crucial link ensures the chain's integrity; any alteration to an earlier block would change its hash, breaking the chain.
* The **`miner_address`**: The public address of the node that successfully mined this block.

**Transactions** are the fundamental operations on the blockchain. Each transaction records the movement of ARTH from a `sender`'s address to a `recipient`'s address, along with the `amount` transferred and a `timestamp`. To ensure authenticity and prevent fraud, every transaction is secured with a **digital signature**, created using the sender's **private key**. This signature can then be verified by anyone using the sender's **public key** to confirm the transaction's legitimacy and that the funds were genuinely authorized by the owner. Before any transaction is added to a block, it is rigorously **verified for valid signatures and sufficient funds** from the sender's balance.

### Wallet & Addresses

Every participant in the ArthaChain network maintains a personal **`wallet.dat` file** locally on their computer. This file is critical as it securely stores their **cryptographic key pair**:

* The **private key**: This is a highly sensitive, secret string of data. It is used to generate **digital signatures** for every transaction you send, proving your ownership of the ARTH. **It must be kept absolutely confidential and secure.** If your private key is compromised, your funds can be stolen.
* The **public key**: This key is mathematically derived from your private key but cannot be used to recreate the private key. It can be shared openly and is used by others to **verify the digital signatures** on your transactions.
* Your **ArthaChain address**: This is a shortened, unique identifier derived by cryptographically hashing your public key. This is the string you share with others when you want to **receive ARTH** from them. It acts like your bank account number in the ArthaChain ecosystem.

### Mining & Supply

Mining in ArthaChain is the process by which new blocks are added to the blockchain and new ARTH coins are introduced into circulation:

* Miners run the **`artha_miner.py` application**, which constantly monitors the network for pending transactions and the last mined block.
* Approximately **every 1 minute**, a miner attempts to "mine" a new block. In this simplified model, this involves waiting for the elapsed time; in real blockchains, it involves solving a complex computational puzzle (Proof of Work).
* When a miner successfully creates a valid block that adheres to all the blockchain's rules, they **broadcast this new block** to the entire network.
* As a reward for their computational effort and for securing the network, the successful miner receives a **block reward of 50 ARTH**. This reward is included in a special transaction within the new block, known as a "**coinbase transaction**." This is how new ARTH coins are initially created and enter the ecosystem.
* The **total supply of Artha (ARTH) is permanently capped at 30,000,000 ARTH**. This hard cap is enforced by the `artha_blockchain.py` rules. This means that mining rewards will eventually cease once 600,000 blocks have been mined (calculated as 30,000,000 ARTH total supply / 50 ARTH per block = 600,000 blocks). This mechanism ensures a finite and predictable supply, mirroring the scarcity principle seen in cryptocurrencies like Bitcoin.

**Note on Simultaneous Mining:** In this simplified implementation, if multiple miners happen to find a valid block for the same block height at nearly the same time, the network will generally **accept the first valid block it receives and successfully propagates**. Only the miner of that accepted block will receive the block reward. This highlights the "winner-takes-all" nature of simplified mining.

### Peer-to-Peer Network

The foundation of ArthaChain's decentralization lies in its **Peer-to-Peer (P2P) network**. This network consists of all active `artha_app.py` and `artha_miner.py` instances connected to each other.

* **Decentralized Communication**: There is no central server or authority. Every participating computer (node) connects directly to other nodes.
* **Node Discovery and Connection**: Nodes can discover and connect to other nodes by knowing their IP address and port number. This is how the network expands.
* **Information Propagation**: Once connected, nodes continuously **broadcast new transactions** that users initiate and **new blocks** that miners successfully find. This ensures that information is rapidly disseminated across the entire network.
* **Blockchain Synchronization**: When a new node (or a node that was offline for a while) joins the network, it **requests the entire blockchain history** from its connected peers. If it receives a longer and valid chain from a peer (indicating a more up-to-date or canonical version), it will **replace its current local chain** with the new one. This synchronization process is vital for maintaining a consistent and accurate distributed ledger across all participants.

This P2P architecture is fundamental to ensuring that ArthaChain is truly decentralized and resilient, as there is no single point of failure or control.

## Getting Started

Follow these steps to set up and run your own ArthaChain nodes.

### Prerequisites

* **Python 3.x** installed on your system. You can download it from [python.org](https://www.python.org/downloads/).
* The `pycryptodome` library, which provides the necessary cryptographic functions for wallet and transaction security.

### Installation

1. **Clone the Repository (or download the files):**

   If you're using Git, open your terminal or command prompt and run:

git clone https://github.com/your-username/ArthaChain.git
cd ArthaChain


*(Replace `your-username` with your actual GitHub username once you've forked/uploaded the project.)*

Alternatively, you can download all the Python files directly from the GitHub repository and place them into a new folder named `ArthaChain` on your computer.

2. **Install Dependencies:**

With your terminal or command prompt navigated into the `ArthaChain` directory, install the required `pycryptodome` library:

pip install pycryptodome


### Running ArthaChain

To experience ArthaChain, you will typically run at least two separate instances: one `artha_miner.py` to produce blocks and one `artha_app.py` to act as a user wallet. You can run multiple application instances on different ports on the same machine to simulate interactions between multiple users.

**Important Note on Ports:** When running multiple instances of `artha_app.py` or `artha_miner.py` on the **same computer**, you **must provide a unique port number** for each instance.

1. **Start the ArthaChain Miner:**

Open a **new terminal** window (or command prompt), navigate to your `ArthaChain` directory, and execute the miner script:

python artha_miner.py 5001


* This command starts the miner node, listening for connections and operating on TCP port `5001`.

* **First Run:** If this is your very first time running ArthaChain, the miner will automatically create a new `wallet.dat` file for itself and initialize the `blockchain.json` file (starting with the genesis block) in a hidden directory named `.artha_chain` within your user's home folder (e.g., `C:\Users\YourUser\.artha_chain` on Windows, or `~/.artha_chain` on Linux/macOS).

* The miner will immediately begin attempting to mine new blocks approximately every minute. You'll see messages indicating its progress.

2. **Start the ArthaChain App (User Application):**

Open **another new terminal** window (separate from the miner's), navigate to your `ArthaChain` directory, and execute the application script:

python artha_app.py 5000


* This command starts your user application node, listening for connections on TCP port `5000`.

* It will also create a new `wallet.dat` for this application instance if one doesn't already exist.

* Once running, the command-line menu (`MENU ARTHACHAIN`) will appear, ready for your input.

3. **Connect Your App to the Miner (or other peers):**

This step is crucial for your application to join the ArthaChain network and synchronize its blockchain. In the terminal running `artha_app.py`, choose option `3` (Connect to Peer) from the menu. When prompted, enter the IP address and port of your running miner (or any other known peer):

127.0.0.1:5001


After entering, your `artha_app.py` instance will connect to the miner. This connection allows your application to start synchronizing the blockchain from the miner and enables you to broadcast your own transactions to the network.

## Usage

The `artha_app.py` provides a simple, interactive command-line interface for users to interact with the ArthaChain network.

======================================== MENU ARTHACHAIN
Show Address & Balance
Send ARTH
Connect to Peer
Show Connected Peers
Show Blockchain
Show Pending Transactions
Synchronize Blockchain
Exit ========================================
<!-- end list -->


* ### 1. Show Address & Balance

  This option displays your unique ArthaChain wallet address and your current ARTH balance. The balance is dynamically calculated by traversing all transactions in the entire blockchain history that are associated with your address.

* ### 2. Send ARTH

  This allows you to initiate a transfer of ARTH to another ArthaChain address. You will be prompted to enter the `recipient`'s address and the `amount` of ARTH you wish to send. The application will then:

  1. Verify if you have sufficient funds.

  2. Create the transaction data.

  3. **Digitally sign** the transaction using your local private key (stored in `wallet.dat`).

  4. Add the transaction to your node's list of pending transactions.

  5. **Broadcast** this signed transaction to all connected peers in the network. This transaction will then wait for a miner to include it in a new block.

* ### 3. Connect to Peer

  Use this option to establish a connection between your current node and another ArthaChain node (e.g., your miner, or another `artha_app.py` instance running on a different port/machine). You'll need to provide the `IP_ADDRESS:PORT` of the target peer (e.g., `127.0.0.1:5001`). Establishing peer connections is essential for your node to synchronize its blockchain and participate actively in the network.

* ### 4. Show Connected Peers

  This option simply displays a list of all the other ArthaChain nodes (peers) that your current application instance is actively connected to. This helps visualize your node's current network reach.

* ### 5. Show Blockchain

  Selecting this option will print the entire ArthaChain blockchain to your console, block by block. For each block, you will see its `index`, `timestamp`, `miner_address`, `previous_hash`, its own `hash`, and a list of all `transactions` included within that block. This provides a full, transparent view of the ledger.

* ### 6. Show Pending Transactions

  This displays a list of all transactions that have been broadcast to your node but have not yet been included (confirmed) in a mined block. These transactions are waiting in the "mempool" to be picked up by a miner.

* ### 7. Synchronize Blockchain

  This option allows you to manually trigger a blockchain synchronization process. Your node will request the latest blockchain copy from its connected peers. If a longer and valid chain is received, your local blockchain copy will be updated to match the most current and recognized version of the ledger across the network. This is useful to ensure you always have the most up-to-date view of the chain.

* ### 8. Exit

  Gracefully shuts down the ArthaChain application, closing all network connections.

## Project Structure

The project is organized into modular Python files, each handling specific functionalities:

ArthaChain/
├── artha_app.py         # The main command-line interface for user interaction.
├── artha_miner.py       # The application responsible for creating and broadcasting new blocks.
├── artha_node.py        # Implements the core peer-to-peer networking logic for communication between nodes.
├── artha_blockchain.py  # Defines the blockchain data structure, validation rules, and manages the chain itself.
├── artha_wallet.py      # Handles cryptographic key generation, transaction signing, and secure wallet data storage.
└── artha_utils.py       # Provides general utility functions like hashing and JSON serialization used across the project.


**Local Data Files:**

When you run any ArthaChain application (either `artha_app.py` or `artha_miner.py`), it creates a hidden directory in your user's home folder to store persistent data:

* `~/.artha_chain/wallet.dat`: This file securely stores your generated private and public keys. **It is crucial to back up this file and keep it secure, as it controls access to your ARTH.**
* `~/.artha_chain/blockchain.json`: This file stores your local copy of the entire ArthaChain blockchain. It allows your node to quickly load the chain without redownloading everything on startup (unless it needs to sync with a longer chain from peers).

## Limitations & Simplifications

This project is primarily designed for educational purposes and includes several significant simplifications compared to real-world, production-grade cryptocurrencies. These simplifications allow for easier understanding of core concepts but mean it is **not suitable for real-world financial transactions or high-security applications.**

* **Simplified "Proof of Work" (Mining Logic)**:
  Instead of implementing a complex, computationally intensive cryptographic puzzle (like Bitcoin's SHA256 hashing race), ArthaChain's mining is simplified. A new block is merely attempted after a set time interval (approximately 1 minute). This demonstrates the concept of block creation but does not provide real-world cryptographic security against malicious actors trying to "fake" blocks.

* **Basic Peer-to-Peer Network**:
  The networking layer is fundamental, supporting direct connections between known IP addresses and ports. It lacks advanced features found in robust networks, such as:

  * **NAT Traversal**: The ability for nodes behind routers (Network Address Translation) to easily connect to each other.

  * **Robust Peer Discovery**: Automatic discovery of new nodes without manual input.

  * **Sophisticated Network Topology**: Optimization for efficient data propagation across a large, dynamic network.

* **Single Miner Reward (Simplified Fork Resolution)**:
  In the event that multiple miners find a valid block for the same block height at nearly the same time, the network's behavior is simplified. Generally, the first valid block that successfully propagates and is received by the majority of nodes will be accepted, and only the miner of that specific block will receive the reward. There isn't a complex, deterministic algorithm for resolving simultaneous findings or for splitting rewards among multiple concurrent miners.

* **No Difficulty Adjustment**:
  The mining interval (approximately 1 minute per block) is fixed. In real blockchains, the "mining difficulty" dynamically adjusts based on the total computational power (hash rate) of the network. This ensures that new blocks are found at a consistent rate, regardless of how many miners join or leave the network. ArthaChain does not implement this dynamic adjustment.

* **Limited Security Features**:
  While ArthaChain utilizes basic cryptographic principles for transaction signing, a full-scale, secure blockchain requires a much more extensive suite of security measures. This includes:

  * **Rigorous Security Audits**: Professional review of the code to identify vulnerabilities.

  * **Byzantine Fault Tolerance (BFT) Mechanisms**: Protocols that allow the network to function correctly even if some nodes are malicious or fail.

  * **Robust Attack Prevention**: Defenses against various attacks beyond simple invalid transactions, such as Sybil attacks, 51% attacks, and more sophisticated network-level exploits.

  * **Smart Contract Vulnerability Mitigation**: (Not applicable directly here as no smart contracts, but crucial for platforms that do).

* **No Smart Contracts**:
  This implementation focuses purely on demonstrating a fungible cryptocurrency (like Bitcoin). It does not include functionality for programmable smart contracts, which allow for complex, self-executing agreements on the blockchain (like those found on Ethereum).

## Contributing

ArthaChain is an open-source project, and contributions are highly welcome! Whether you want to fix a bug, improve existing features, add new functionalities, or simply refine the documentation, your input is valuable.

1. **Fork the repository** on GitHub.

2. **Create your feature branch**: `git checkout -b feature/YourAwesomeFeature`.

3. **Commit your changes**: `git commit -m 'Add a short description of your feature'`.

4. **Push to the branch**: `git push origin feature/YourAwesomeFeature`.

5. **Open a Pull Request** on the main ArthaChain repository. Please provide a clear description of your changes and why they are beneficial.

## License

This project is open-source and available under the **MIT License**. This means you are free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the software, subject to the conditions outlined in the license.
