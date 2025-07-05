# ArthaChain

![Blockchain](https://img.shields.io/badge/Blockchain-PoS-blueviolet)
![Status](https://img.shields.io/badge/Status-Stable-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow) 
![ArthaChain](https://img.shields.io/badge/Project-ArthaChain-blue)

> **Platform Blockchain Proof of Stake yang Cepat, Efisien, dan Modern**

**ArthaChain** adalah platform blockchain generasi baru yang mengadopsi mekanisme konsensus **Proof of Stake (PoS)**. Dirancang dengan fokus pada kecepatan transaksi, efisiensi energi, dan kemudahan penggunaan, ArthaChain siap menjadi fondasi untuk ekosistem DeFi dan aplikasi blockchain modern.

---

## ✨ Fitur Utama

- 🚀 **Blok Cepat & Konsisten**  
  Blok baru dibuat setiap **10 detik**, memastikan transaksi dikonfirmasi secara cepat dan dapat diprediksi.

- 🔒 **Konsensus Proof of Stake**  
  Mengganti sistem Proof of Work yang boros energi dengan PoS yang lebih efisien. Validator dipilih secara bergiliran untuk membuat blok.

- 🌱 **Ramah Lingkungan**  
  Konsumsi energi sangat rendah — hingga 99% lebih hemat dibanding PoW.

- 💻 **Antarmuka GUI Modern**  
  Dibangun dengan `customtkinter`, GUI ArthaChain mencakup:
  - Dashboard dompet pribadi.
  - Explorer jaringan dan histori transaksi.
  - Visualisasi real-time blok & mempool.

- 💰 **Ekonomi Token ARTH**  
  Validator mendapat reward dari blok baru, menjaga stabilitas ekonomi jaringan dan memotivasi partisipasi.

---

## 🧱 Struktur Proyek

```
arthachain/
├── arthacore_gui_pos.py     # GUI: Dompet & Explorer
├── artha_validator.py       # Validator: Pembuat blok
├── artha_app_pos.py         # CLI: Mode pengguna biasa (opsional)
├── artha_blockchain_pos.py  # Inti Blockchain PoS
├── artha_node_pos.py        # Komunikasi jaringan P2P
├── artha_wallet.py          # Dompet: kunci privat/publik
├── artha_utils.py           # Fungsi hashing, json, dsb.
└── requirements.txt         # Daftar dependensi
```

---

## 🚀 Cara Menjalankan

### 1. Persyaratan

- Python 3.8 atau lebih baru
- `pip`
- Git

### 2. Instalasi

```bash
git clone https://github.com/NAMA_USER_ANDA/ArthaChain.git
cd ArthaChain
pip install -r requirements.txt
```

### 3. Konfigurasi Validator

Jalankan validator untuk membuat dompet pertama Anda:

```bash
python3 artha_validator.py 5001
```

Program akan meminta password, lalu menghasilkan alamat validator. Salin alamat tersebut dan tambahkan ke daftar `self.validators` di file `artha_blockchain_pos.py`.

```python
class ArthaBlockchainPoS:
    def __init__(self, ...):
        self.validators = [
            'ALAMAT_VALIDATOR_ANDA'
        ]
```

### 4. Menjalankan Jaringan

**Terminal 1 - Validator:**

```bash
python3 artha_validator.py 5001
```

Biarkan berjalan untuk memvalidasi blok.

**Terminal 2 - GUI:**

```bash
python3 arthacore_gui_pos.py
```

Masukkan password dompet pengguna. Dompet akan dibuat jika belum ada.

---

## 📄 Lisensi

ArthaChain dilisensikan di bawah Lisensi MIT:

```
Copyright (c) 2025 Muhammad Zili

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---


## 👨‍💻 Pengembang

**Muhammad Zili**  
📧 Email: person@mzili.my.id  
🌐 GitHub: [github.com/muhammadzili](https://github.com/muhammadzili)  
🔗 Instagram: [https://www.instagram.com/mhmdszuli/](https://www.instagram.com/mhmdszuli/)

---

## 🤝 Berkontribusi

Kontribusi sangat diterima! Silakan buka issue atau pull request dengan:

1. Fork repository
2. Buat branch fitur (`git checkout -b fitur-baru`)
3. Commit perubahan (`git commit -am 'Tambahkan fitur baru'`)
4. Push ke branch (`git push origin fitur-baru`)
5. Buat Pull Request

---

## 💬 Dukungan

Untuk pertanyaan atau dukungan, silakan:

- Buat issue di GitHub
- Hubungi pengembang melalui email
- Bergabung dengan komunitas ArthaChain
