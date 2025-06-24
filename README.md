ArthaChain
Sebuah mata uang kripto sederhana dan terdesentralisasi yang dibuat dengan Python. ArthaChain memungkinkan pengguna untuk mengelola dompet mereka, mengirim transaksi, dan menambang blok baru di jaringan peer-to-peer (P2P). Proyek ini sekarang dilengkapi dengan GUI desktop dan dompet yang dienkripsi dengan kata sandi.

Daftar Isi
Tentang ArthaChain

Cara Kerjanya

Komponen Inti

Blockchain & Transaksi

Dompet & Alamat

Penambangan, Kesulitan & Pasokan

Jaringan Peer-to-Peer

Memulai

Prasyarat

Instalasi

Menjalankan ArthaChain

Penggunaan

Aplikasi GUI ArthaChain (artha_gui.py)

Penambang ArthaChain (artha_miner.py)

Struktur Proyek

Batasan & Penyederhanaan

Kontribusi

Lisensi

Tentang ArthaChain
ArthaChain adalah implementasi blockchain minimalis yang dirancang untuk mendemonstrasikan prinsip-prinsip dasar mata uang kripto terdesentralisasi. Fitur utamanya meliputi:

GUI Desktop: Antarmuka pengguna grafis yang ramah pengguna (Tkinter) untuk mengelola dompet dan memantau jaringan.

Dompet Terenkripsi: Kunci privat disimpan secara aman di file wallet.dat lokal yang dienkripsi dengan kata sandi pengguna (menggunakan scryptAndAES128-CBC), memberikan pengguna kontrol penuh atas dana mereka.

Jaringan Terdesentralisasi: Menggunakan jaringan P2P dasar untuk komunikasi node dan sinkronisasi data, memastikan tidak ada titik kontrol tunggal.

Transaksi Aman: Memungkinkan pengguna mengirim Artha (ARTH) dengan aman antar alamat, dengan transaksi yang ditandatangani secara digital untuk otentikasi.

Penambangan Proof-of-Work: Penambang bersaing untuk membuat blok baru dengan memecahkan teka-teki kriptografi, menambahkan transaksi, dan menerima ARTH yang baru dicetak sebagai imbalan blok.

Penyesuaian Kesulitan Dinamis: Kesulitan penambangan secara otomatis menyesuaikan setiap 10 blok untuk menargetkan waktu blok rata-rata 3 detik.

Pasokan Tetap: Total pasokan 30.000.000 ARTH yang telah ditentukan dan tidak dapat diubah, untuk memastikan kelangkaan.

Ini adalah alat edukasi yang sangat baik untuk memahami konsep inti blockchain seperti buku besar terdistribusi, kriptografi, dan mekanisme konsensus.

Cara Kerjanya
ArthaChain beroperasi pada beberapa modul Python yang saling berhubungan.

Komponen Inti
artha_gui.py: Aplikasi desktop utama berbasis Tkinter. Ini adalah titik masuk utama bagi pengguna untuk berinteraksi dengan dompet mereka, melihat status jaringan, dan mengirim transaksi.

artha_wallet.py: Modul ini bertanggung jawab atas manajemen dompet pengguna. Ini menangani pembuatan pasangan kunci RSA, enkripsi kunci privat dengan kata sandi, penandatanganan transaksi, dan verifikasi tanda tangan digital.

artha_blockchain.py: Sebagai inti ArthaChain, modul ini mendefinisikan struktur dan aturan dasar blockchain. Ini mengelola rantai blok, transaksi yang tertunda, menghitung saldo, dan melakukan validasi blok/transaksi yang krusial. Ini juga menetapkan total pasokan (30.000.000 ARTH) dan imbalan blok (50 ARTH).

artha_node.py: Modul ini mengimplementasikan logika jaringan Peer-to-Peer (P2P). Ini memungkinkan node yang berbeda untuk menemukan, terhubung, dan berkomunikasi satu sama lain untuk menyiarkan blok dan transaksi baru, serta menyinkronkan ledger.

artha_miner.py: Ini adalah aplikasi penambangan. Penambang menjalankan skrip ini untuk berpartisipasi dalam proses Proof-of-Work, memvalidasi transaksi, dan membuat blok baru.

artha_utils.py: Modul ini menyediakan fungsi utilitas penting seperti hashing kriptografi (SHA256) dan serialisasi JSON yang konsisten.

artha_app.py (Legacy): Antarmuka baris perintah (CLI) asli. Fungsinya telah digantikan oleh artha_gui.py yang lebih ramah pengguna, tetapi masih tersedia untuk penggunaan terminal.

Blockchain & Transaksi
Blockchain ArthaChain adalah rantai blok yang terhubung secara kronologis dan aman. Setiap blok berisi:

Sebuah index: Posisinya dalam rantai.

Sebuah timestamp: Waktu pembuatan blok.

Daftar transactions: Catatan transfer ARTH.

Sebuah nonce: Angka yang ditemukan oleh penambang selama proses Proof-of-Work, yang membuktikan pekerjaan komputasi telah dilakukan.

Sebuah difficulty: Nilai yang merepresentasikan kesulitan target penambangan pada saat itu.

Sebuah previous_hash: Hash kriptografis dari blok sebelumnya, yang mengikat rantai menjadi satu dan memastikan integritasnya.

Transaksi adalah operasi dasar di blockchain. Untuk memastikan keaslian, setiap transaksi ditandatangani secara digital menggunakan kunci privat pengirim. Tanda tangan ini dapat diverifikasi oleh siapa saja menggunakan kunci publik pengirim.

Dompet & Alamat
Setiap peserta di jaringan ArthaChain mengelola file wallet.dat lokal di komputer mereka. File ini sangat penting dan sekarang dienkripsi dengan kata sandi:

Kunci Privat: Data rahasia yang digunakan untuk menghasilkan tanda tangan digital untuk setiap transaksi yang Anda kirim. Kunci ini dienkripsi di dalam wallet.dat dan hanya dapat diakses dengan kata sandi Anda.

Kunci Publik: Kunci ini diturunkan secara matematis dari kunci privat Anda dan dapat dibagikan secara terbuka. Ini digunakan oleh orang lain untuk memverifikasi tanda tangan digital pada transaksi Anda.

Alamat ArthaChain: Ini adalah pengidentifikasi unik yang diturunkan dari hash kunci publik Anda. Anda membagikan alamat ini untuk menerima ARTH.

Penambangan, Kesulitan & Pasokan
Penambangan adalah proses di mana blok-blok baru ditambahkan ke blockchain:

Penambang menjalankan aplikasi artha_miner.py dan bersaing untuk menjadi yang pertama menemukan nonce yang valid. Nonce adalah angka yang, ketika digabungkan dengan data blok lainnya dan di-hash, menghasilkan hash yang lebih rendah dari target kesulitan saat ini.

Penyesuaian Kesulitan: Untuk menjaga waktu pembuatan blok tetap stabil (sekitar 3 detik), kesulitan penambangan secara otomatis disesuaikan setiap 10 blok. Jika blok ditemukan terlalu cepat, kesulitan meningkat; jika terlalu lambat, kesulitan menurun.

Sebagai imbalan atas upaya komputasi mereka, penambang yang berhasil menerima imbalan blok sebesar 50 ARTH. Imbalan ini disertakan dalam transaksi coinbase.

Total Pasokan Artha (ARTH) dibatasi secara permanen pada 30.000.000 ARTH. Ini berarti imbalan penambangan pada akhirnya akan berhenti setelah 600.000 blok ditambang (30.000.000 ARTH / 50 ARTH per blok).

Jaringan Peer-to-Peer
Fondasi desentralisasi ArthaChain terletak pada jaringan Peer-to-Peer (P2P)-nya.

Komunikasi Terdesentralisasi: Tidak ada server pusat. Setiap node terhubung langsung ke node lain.

Penemuan & Sinkronisasi Node: Node baru secara otomatis mencoba terhubung ke daftar bootstrap peers yang telah ditentukan untuk bergabung dengan jaringan. Ketika sebuah node menerima rantai yang lebih panjang dan valid dari peer, ia akan mengganti rantai lokalnya untuk mempertahankan konsensus.

Propagasi Informasi: Node terus menyiarkan transaksi baru yang dimulai pengguna dan blok baru yang ditemukan penambang ke seluruh jaringan.

Memulai
Ikuti langkah-langkah ini untuk menyiapkan dan menjalankan node ArthaChain Anda sendiri.

Prasyarat
Python 3.x terinstal di sistem Anda.

Pustaka pycryptodome untuk fungsi kriptografi.

Instalasi
Clone atau Unduh Proyek:

git clone https://github.com/muhammadzili/ArthaChain.git
cd ArthaChain

Atau, unduh semua file Python dan letakkan di folder yang sama.

Instal Dependensi:
Buka terminal di direktori ArthaChain dan jalankan:

pip install pycryptodome

Menjalankan ArthaChain
Untuk pengalaman penuh, Anda biasanya akan menjalankan setidaknya dua instance terpisah: satu artha_miner.py untuk menghasilkan blok dan satu artha_gui.py untuk bertindak sebagai dompet pengguna.

Catatan Penting tentang Dompet: Saat pertama kali menjalankan artha_gui.py atau artha_miner.py, Anda akan diminta untuk membuat kata sandi. Kata sandi ini akan digunakan untuk mengenkripsi file wallet.dat Anda. JANGAN LUPA KATA SANDI INI! Tidak ada cara untuk memulihkannya.

Mulai Penambang ArthaChain:
Buka terminal baru, navigasikan ke direktori ArthaChain, dan jalankan skrip miner:

python artha_miner.py 5001

Ini memulai node miner di port 5001.

Anda akan diminta untuk memasukkan kata sandi untuk dompet miner. Jika wallet.dat tidak ada, dompet baru akan dibuat dengan kata sandi ini.

Miner akan mulai mencoba menambang blok baru.

Mulai Aplikasi GUI ArthaChain:
Buka terminal baru lainnya, navigasikan ke direktori ArthaChain, dan jalankan skrip GUI:

python artha_gui.py 5000

Ini memulai aplikasi GUI pengguna di port 5000.

Anda akan diminta memasukkan kata sandi untuk dompet pengguna Anda.

Aplikasi akan secara otomatis mencoba terhubung ke jaringan melalui bootstrap peers dan menyinkronkan blockchain.

Penggunaan
Aplikasi GUI ArthaChain (artha_gui.py)
Aplikasi GUI adalah cara utama untuk berinteraksi dengan ArthaChain. Ini memiliki beberapa tab:

Tab Dompet: Menampilkan alamat dompet Anda, saldo ARTH saat ini, dan tombol untuk mengirim ARTH atau me-refresh data.

Tab Blockchain: Menampilkan daftar semua blok di rantai, termasuk indeks, timestamp, miner, dan jumlah transaksi.

Tab Jaringan: Menampilkan daftar peer yang saat ini terhubung dan daftar transaksi yang tertunda (di mempool).

Tab Log Aktivitas: Menampilkan log sistem real-time dari aktivitas node, sangat berguna untuk debugging.

Penambang ArthaChain (artha_miner.py)
Aplikasi ini berjalan di terminal dan tidak memerlukan interaksi setelah dimulai. Cukup masukkan kata sandi dompet Anda saat diminta, dan ia akan mulai bekerja untuk mengamankan jaringan dan menambang blok baru.

Struktur Proyek
ArthaChain/
├── artha_gui.py         # Aplikasi GUI utama berbasis Tkinter untuk pengguna.
├── artha_miner.py       # Aplikasi untuk menambang blok baru (Proof-of-Work).
├── artha_node.py        # Logika jaringan P2P untuk komunikasi antar node.
├── artha_blockchain.py  # Mendefinisikan struktur dan aturan blockchain.
├── artha_wallet.py      # Mengelola pembuatan kunci, enkripsi, dan penandatanganan transaksi.
└── artha_utils.py       # Fungsi utilitas umum seperti hashing.

File Data Lokal:
Aplikasi membuat direktori tersembunyi (~/.artha_chain/) untuk menyimpan:

~/.artha_chain/wallet.dat: File ini menyimpan kunci privat dan publik Anda yang dienkripsi dengan kata sandi. Sangat penting untuk mencadangkan file ini dan menjaga kerahasiaan kata sandi Anda.

~/.artha_chain/blockchain.json: Salinan lokal Anda dari seluruh blockchain ArthaChain.

~/.artha_chain/logs/: File log untuk debugging.

Batasan & Penyederhanaan
Proyek ini dirancang untuk tujuan pendidikan dan tidak cocok untuk transaksi keuangan di dunia nyata.

Jaringan P2P Dasar: Jaringan ini mendukung koneksi langsung tetapi tidak memiliki fitur canggih seperti NAT Traversal atau penemuan peer yang sepenuhnya otomatis.

Resolusi Fork Sederhana: Menggunakan aturan "rantai terpanjang" sederhana. Jika terjadi fork (dua miner menemukan blok pada ketinggian yang sama), rantai yang pertama kali menjadi lebih panjang akan diadopsi oleh jaringan.

Fitur Keamanan Terbatas: Meskipun menggunakan prinsip-prinsip kriptografi dasar, ia tidak memiliki pertahanan yang kuat terhadap serangan tingkat lanjut seperti serangan 51% atau Sybil.

Tidak Ada Kontrak Pintar: Implementasi ini berfokus murni pada mata uang kripto yang dapat dipertukarkan (seperti Bitcoin) dan tidak menyertakan fungsionalitas untuk kontrak pintar.

Kontribusi
Kontribusi sangat diterima! Silakan fork repositori, buat perubahan Anda di cabang fitur, dan buka Pull Request.

Lisensi
Proyek ini bersifat open-source dan tersedia di bawah Lisensi MIT.
