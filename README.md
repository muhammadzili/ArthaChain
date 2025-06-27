# ArthaChain

![ArthaChain Logo](assets/logo.png)

> **Platform Blockchain Keuangan Terdesentralisasi Modern**

ArthaChain adalah platform blockchain generasi baru yang dirancang untuk aplikasi keuangan terdesentralisasi (DeFi) dengan fokus pada **kecepatan**, **keamanan**, dan **keberlanjutan**.

---

## ✨ Fitur Utama

- 🚀 **Transaksi Cepat**: 2500+ TPS dengan finalitas hanya 2 detik
- 🔒 **Keamanan Tinggi**: Menggunakan kriptografi modern dan konsensus hybrid
- 🌱 **Ramah Lingkungan**: 99% lebih hemat energi dibanding PoW tradisional
- 💰 **Ekonomi Token ARTH**: Total supply 30 juta token dengan distribusi adil
- ⚡ **Smart Contracts**: Dukungan kontrak pintar dengan bahasa pemrograman yang mudah digunakan

---

## 🚀 Cara Penggunaan

### Persyaratan Sistem

- Python 3.8+
- pip
- Git

### Instalasi

1. Clone repository:
   ```bash
   git clone https://github.com/muhammadzili/ArthaChain.git
   cd ArthaChain
   ```

2. Buat virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate      # Linux/MacOS
   venv\Scripts\activate       # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🧱 Menjalankan Node

### Node Reguler
```bash
python artha_app.py [PORT]
```

### Node Miner
```bash
python artha_miner.py [PORT]
```

### GUI Wallet
```bash
python arthacore_gui.py [PORT]
```

### Opsi Command Line

| Parameter | Deskripsi                    | Default |
|----------|-------------------------------|---------|
| `PORT`   | Port untuk menjalankan node   | `5000`  |

---

## 📁 Struktur Direktori

```
arthachain/
├── artha_app.py         # Aplikasi CLI utama
├── artha_miner.py       # Node penambang
├── arthacore_gui.py     # Antarmuka GUI
├── artha_blockchain.py  # Implementasi blockchain
├── artha_wallet.py      # Manajemen wallet
├── artha_node.py        # Jaringan P2P
├── artha_utils.py       # Fungsi utilitas
├── requirements.txt     # Dependensi
└── README.md            # Dokumentasi
```

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

## 📦 Status Proyek

**Status Release: v1.7**

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
