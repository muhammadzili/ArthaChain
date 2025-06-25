# ArthaChain: Blockchain & Mata Uang Kripto dengan Python

## Deskripsi Proyek

**ArthaChain** adalah sebuah implementasi proyek blockchain yang dibangun dari dasar menggunakan Python. Proyek ini mensimulasikan fungsionalitas inti dari mata uang kripto seperti Bitcoin, mencakup dompet digital, transaksi peer-to-peer, proses penambangan (*mining*), dan mekanisme konsensus sederhana.

Dibuat sebagai alat pembelajaran yang mendalam, ArthaChain bertujuan untuk mendemistifikasi teknologi di balik blockchain. Proyek ini dilengkapi dengan antarmuka pengguna grafis (GUI) **ArthaCore** yang intuitif, dompet yang dienkripsi dengan password, dan kemampuan untuk menjalankan beberapa node yang saling terhubung dalam jaringan terdesentralisasi.

---

## 🎯 Tujuan & Filosofi

Tujuan utama dari ArthaChain adalah sebagai **platform edukasi** bagi siapa saja yang ingin memahami _bagaimana cara kerja blockchain_ secara **praktis**, bukan hanya teori. Dengan melihat dan menjalankan kode ini, pengguna dapat belajar tentang:

- **🔐 Kriptografi Kunci Publik**  
  Bagaimana pasangan kunci privat dan publik digunakan untuk mengamankan kepemilikan aset digital dan mengotorisasi transaksi.

- **📦 Struktur Data Blockchain**  
  Konsep rantai blok yang saling terhubung secara kriptografis (`previous_hash`) yang membuatnya sangat sulit untuk dimodifikasi.

- **⛏️ Mekanisme Konsensus**  
  Simulasi sederhana dari *Proof-of-Work (PoW)* di mana para penambang bersaing untuk menambahkan blok baru ke blockchain.

- **🌐 Jaringan P2P**  
  Bagaimana node dalam jaringan terdesentralisasi berkomunikasi untuk menyebarkan transaksi, menyiarkan blok baru, dan menjaga sinkronisasi buku besar (*ledger*).

---

## ⚙️ Fitur Utama

- **🔐 Dompet Terenkripsi Kuat**  
  Kunci privat tidak pernah disimpan sebagai teks biasa. `wallet.dat` dienkripsi menggunakan AES-GCM + Scrypt, hanya dapat dibuka dengan password.

- **🌐 Jaringan Peer-to-Peer (P2P)**  
  Node dapat menemukan dan berkomunikasi melalui mekanisme bootstrap peer tanpa server pusat.

- **⛏️ Penambangan Proof-of-Work (PoW)**  
  Miner bersaing untuk menemukan `nonce` yang valid untuk sebuah blok, menjaga keamanan jaringan.

- **📈 Penyesuaian Kesulitan Otomatis**  
  Setiap 10 blok, sistem menyesuaikan kesulitan agar waktu rata-rata blok tetap ~60 detik.

- **💰 Pasokan Terbatas**  
  Total suplai ARTH dibatasi hingga 30.000.000 koin dengan reward 50 ARTH per blok.

- **🖥️ GUI ArthaCore (Tkinter Desktop App)**  
  - Melihat saldo & alamat wallet  
  - Mengirim ARTH  
  - Melihat riwayat transaksi  
  - Mengecek blok terbaru & transaksi tertunda  
  - Menelusuri data wallet lain di jaringan

- **📟 CLI App (artha_app.py)**  
  Alternatif antarmuka baris perintah untuk pengguna tingkat lanjut atau server headless.

---

## 🚀 Cara Menjalankan

### 1. Prasyarat

- Python `3.7+`
- PIP (Package Installer for Python)

### 2. Instalasi Dependensi

#### pip install pycryptodome ttkthemes

### 3. Menjalankan Jaringan

🔁 Skenario A: Simulasi Lokal
Jalankan semua node di satu komputer untuk pengujian cepat.

Terminal 1 - Jalankan Miner:

`python3 artha_miner.py 5001`

Terminal 2 - Jalankan GUI:

'python3 arthacore_gui.py 5002'
GUI akan terhubung otomatis ke miner di port 5001.

🌐 Skenario B: Miner di Server/VPS
Langkah di Server:

`sudo ufw allow 5001/tcp`
`python3 artha_miner.py 5001`

Langkah di Klien Lokal:

Edit file artha_node.py, ubah bagian BOOTSTRAP_PEERS:

BOOTSTRAP_PEERS = [
    'IP_PUBLIK_VPS_ANDA:5001',
    '127.0.0.1:5001',
]

Lalu jalankan GUI:

`python3 arthacore_gui.py 5002`

### 4. 💸 Melakukan Transaksi
Setelah miner menambang blok dan mendapat reward:

Gunakan GUI untuk mengirim ARTH dari dompet miner ke dompet klien.

Transaksi akan muncul di daftar Transaksi Tertunda.

Setelah blok berikutnya ditambang, transaksi akan terkonfirmasi.

### 📂 Struktur Proyek

ArthaChain/
├── artha_blockchain.py      # Struktur Blockchain & Blok
├── artha_wallet.py          # Wallet dan enkripsi
├── artha_node.py            # Logika jaringan P2P
├── artha_miner.py           # Penambangan PoW
├── arthacore_gui.py         # Aplikasi GUI
├── artha_app.py             # CLI App
├── wallet.dat               # File dompet terenkripsi
├── README.md                # Dokumen ini

📄 Lisensi
Proyek ini bersifat open-source dan dapat digunakan bebas untuk tujuan edukasi atau pengembangan lebih lanjut. Atau bahkan digunakan untuk transaksi riil
Lisensi MIT © 2025 by Muhammad Zili.

❤️ Kontribusi
Kontribusi sangat terbuka! Silakan fork, buat pull request, atau laporkan masalah melalui Issue Tracker.

### 📫 Kontak
Untuk kolaborasi atau pertanyaan, hubungi:
📧 person@mzili.my.id

---

Jika kamu butuh dalam bentuk file `README.md`, tinggal minta, nanti saya buatkan dan kirimkan
