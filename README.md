
# 🚀 ArthaChain: Blockchain & Mata Uang Kripto dengan Python

![Python](https://img.shields.io/badge/Python-3.7%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-Beta-orange)

---

## 📘 Deskripsi Proyek

**ArthaChain** adalah implementasi nyata dari sistem **blockchain** dan **mata uang kripto** yang dibangun sepenuhnya dari dasar menggunakan bahasa pemrograman Python. Proyek ini bukan hanya simulasi, tapi didesain dengan standar keamanan tinggi dan struktur modular, sehingga **dapat dikembangkan untuk penggunaan transaksi nyata (real-world transactions)** di lingkungan terkontrol.

Fitur-fitur inti seperti dompet terenkripsi, transaksi P2P, penambangan blok melalui mekanisme *Proof-of-Work*, dan sinkronisasi jaringan P2P menjadikan ArthaChain sebagai solusi edukatif sekaligus dasar potensial untuk sistem blockchain ringan dan terdesentralisasi.

---

## 🎯 Tujuan & Filosofi

ArthaChain dibuat dengan dua semangat utama:

1. **Edukasi Praktis:** Menyediakan alat pembelajaran untuk memahami cara kerja blockchain secara end-to-end.
2. **Penggunaan Nyata:** Membangun pondasi teknologi yang dapat digunakan untuk sistem transaksi digital privat atau komunitas tertutup secara riil dan aman.

---

## 🔐 Teknologi Inti

- **Dompet Digital Aman:** Menggunakan AES-GCM dan Scrypt untuk enkripsi kunci privat.
- **Transaksi Peer-to-Peer:** Antar dompet langsung tanpa perantara.
- **Proof-of-Work:** Penambangan blok dilakukan berdasarkan tingkat kesulitan otomatis.
- **Jaringan Terdesentralisasi:** Node-node bekerja mandiri, saling sinkronisasi tanpa server pusat.
- **Supply Terbatas:** Total 21.000.000 ARTH, reward 50 ARTH per blok dengan *halving* setiap 210.000 blok.
- **Real-Time GUI:** Antarmuka desktop interaktif dan CLI untuk keperluan server/headless.

---

## ⚙️ Fitur Utama

- 🔐 Dompet digital dengan password dan enkripsi kuat  
- 🧠 Konsensus Proof-of-Work (PoW)  
- 🌐 Jaringan P2P tanpa pusat  
- ⏱ Penyesuaian otomatis kesulitan setiap 10 blok  
- 📦 Transaksi riil antar dompet  
- 💼 GUI dan CLI untuk fleksibilitas penggunaan  
- 🔍 Eksplorasi alamat dan blok secara lokal  
- 🧾 Riwayat transaksi yang transparan  
- 🧰 Dukungan multi-node untuk simulasi atau produksi kecil

---

## 🚀 Cara Menjalankan

### 1. Prasyarat

- Python `3.7+`
- PIP (Package Installer for Python)

### 2. Instalasi Dependensi

```bash
pip install pycryptodome ttkthemes
```

### 3. Simulasi Lokal (Testing)

Terminal 1 - Jalankan Miner:
```bash
python3 artha_miner.py 5001
```

Terminal 2 - Jalankan GUI:
```bash
python3 arthacore_gui.py 5002
```

> GUI akan otomatis terhubung ke miner dan mulai menyinkronkan blok.

### 4. Jalankan di VPS (Penggunaan Semi-Produksi)

**Di server/VPS:**
```bash
sudo ufw allow 5001/tcp
python3 artha_miner.py 5001
```

**Di komputer lokal:**
Ubah `BOOTSTRAP_PEERS` di `artha_node.py`:
```python
BOOTSTRAP_PEERS = [
    'IP_PUBLIK_VPS_ANDA:5001',
    '127.0.0.1:5001',
]
```

Lalu jalankan GUI:
```bash
python3 arthacore_gui.py 5002
```

---

## 🌐 Jaringan: mainnet / devnet / localnet

Pilih jaringan lewat env `ARTHA_NETWORK` (default: `mainnet`). Setiap jaringan
punya `chain_id`, folder data, port, dan parameter konsensus sendiri sehingga
tidak saling silang antar jaringan.

| Jaringan  | chain_id          | Data dir (di `~/.artha_chain`) | Port default (miner/app/gui) |
|-----------|-------------------|--------------------------------|------------------------------|
| mainnet   | arthachain-1      | `(root)`                       | 5001 / 5000 / 5002           |
| devnet    | arthachain-devnet | `devnet/`                      | 6001 / 6000 / 6002           |
| localnet  | arthachain-local  | `localnet/`                    | 7001 / 7000 / 7002           |

`devnet` = blok ~15 detik, `localnet` = ~5 detik (untuk simulasi kilat).
`devnet`/`localnet` memakai bootstrap lokal, bukan discovery publik mainnet.

Contoh menjalankan 5 node/wallet di 1 PC (devnet) — tiap instance pakai
`ARTHA_DATADIR` sendiri supaya bisa saling sinkron via P2P:

```bash
# Terminal 1 - Miner (penghasil blok)
ARTHA_NETWORK=devnet ARTHA_DATADIR=~/.artha_dev/1 python3 artha_miner.py 6001

# Terminal 2-5 - Wallet/node, hubungkan ke miner lewat menu "Tambah Peer"
ARTHA_NETWORK=devnet ARTHA_DATADIR=~/.artha_dev/2 python3 artha_app.py 6101
ARTHA_NETWORK=devnet ARTHA_DATADIR=~/.artha_dev/3 python3 artha_app.py 6102
# dst...
```

PowerShell (Windows):
```powershell
$env:ARTHA_NETWORK="devnet"; $env:ARTHA_DATADIR="$HOME\.artha_dev\1"; python artha_miner.py 6001
```

---

## 💸 Transaksi Real-Time

1. Setelah penambangan berjalan, wallet miner akan menerima reward ARTH.
2. Kirim ARTH ke dompet klien lain via GUI.
3. Transaksi akan masuk ke antrean dan dikonfirmasi saat blok baru ditambang.
4. Riwayat transaksi, saldo, dan detail blok bisa dilihat langsung dari GUI.

> **Catatan:** Semua transaksi diproses secara lokal dan peer-to-peer. Tidak ada penyimpanan cloud atau pihak ketiga yang terlibat.

---

## 📁 Struktur Proyek

```text
ArthaChain/
├── artha_blockchain.py      # Struktur Blockchain & Blok
├── artha_wallet.py          # Wallet dan enkripsi
├── artha_node.py            # Logika jaringan P2P
├── artha_miner.py           # Penambangan PoW
├── arthacore_gui.py         # Aplikasi GUI (Tkinter)
├── artha_app.py             # CLI untuk pengguna teknis
├── wallet.dat               # File dompet terenkripsi
├── README.md                # Dokumentasi
```

---

## 📄 Lisensi

Proyek ini menggunakan **Lisensi MIT** dan bersifat open-source.  
Dapat digunakan bebas untuk tujuan edukasi, pengembangan lanjutan, atau sistem blockchain internal komunitas.

---

## ❤️ Kontribusi

Kami sangat terbuka untuk kontribusi dari siapa saja!

- Fork proyek ini
- Buat *pull request*
- Atau laporkan bug melalui [Issue Tracker](https://github.com/muhammadzili/ArthaChain/issues)

---

## 📫 Kontak

Untuk kolaborasi, masukan, atau kerja sama:

📧 zilizero0@gmail.com
---

> ⚠️ **Disclaimer:** Walaupun proyek ini telah dirancang dengan prinsip keamanan, ArthaChain belum melalui audit keamanan resmi. Untuk penggunaan pada skala besar atau transaksi bernilai tinggi, sangat disarankan dilakukan peninjauan lanjutan.
