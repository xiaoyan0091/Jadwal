# Cara Deploy Bot Jadwal Donghua ke VPS Ubuntu 22.04

Panduan ini menjelaskan cara melakukan deploy bot Telegram Jadwal Donghua ke server VPS yang menggunakan sistem operasi Ubuntu 22.04.

**Create by @PlaeaseNotPM**

---

### **Prasyarat**

1.  Server VPS dengan Ubuntu 22.04.
2.  Akses SSH ke server Anda.
3.  Domain atau Subdomain (Opsional, jika Anda ingin menggunakan webhook).

---

### **Langkah 1: Update Sistem**

Pertama, pastikan semua paket di server Anda sudah diperbarui.

```bash
sudo apt update && sudo apt upgrade -y
```

### **Langkah 2: Install Python, PIP, dan Git**

Bot ini dibuat dengan Python. Install Python, manajer paket `pip`, `venv` untuk virtual environment, dan `git` untuk mengambil kode dari repository.

```bash
sudo apt install python3 python3-pip python3-venv git -y
```

### **Langkah 3: Clone Repository**

Ambil kode bot dari repository GitHub. Ganti `<URL_REPO_ANDA>` dengan URL repository Anda.

```bash
git clone <URL_REPO_ANDA>
cd <NAMA_DIREKTORI_REPO>
```

### **Langkah 4: Setup Virtual Environment**

Sangat disarankan untuk menggunakan virtual environment agar dependensi bot tidak tercampur dengan paket Python sistem.

```bash
# Buat virtual environment
python3 -m venv venv

# Aktifkan virtual environment
source venv/bin/activate
```
*Setelah aktif, Anda akan melihat `(venv)` di awal baris terminal Anda.*

### **Langkah 5: Install Dependensi**

Install semua library Python yang dibutuhkan oleh bot menggunakan file `requirements.txt`.

```bash
pip install -r requirements.txt
```

### **Langkah 6: Konfigurasi Bot**

Buka file konfigurasi untuk memasukkan Token Bot dan ID Owner Anda.

```bash
nano jadwalbot/config.py
```

Ubah baris berikut dengan data Anda:
```python
BOT_TOKEN = "ISI_DENGAN_TOKEN_BOT_ANDA"
OWNER_ID = ISI_DENGAN_USER_ID_TELEGRAM_ANDA
```
Simpan file dengan menekan `Ctrl + X`, lalu `Y`, dan `Enter`.

### **Langkah 7: Jalankan Bot (Tes Manual)**

Sebelum membuat service, coba jalankan bot secara manual untuk memastikan tidak ada error.

```bash
python3 jadwalbot.py
```

Jika bot berjalan tanpa error, hentikan dengan menekan `Ctrl + C`.

### **Langkah 8: Buat Service (systemd)**

Agar bot tetap berjalan bahkan setelah Anda menutup koneksi SSH, kita akan menjalankannya sebagai service menggunakan `systemd`.

1.  **Dapatkan path absolut direktori kerja Anda.**
    Pastikan Anda berada di direktori utama bot, lalu jalankan:
    ```bash
    pwd
    ```
    Salin path yang muncul (contoh: `/root/jadwalbot`).

2.  **Buat file service baru.**
    ```bash
    sudo nano /etc/systemd/system/jadwalbot.service
    ```

3.  **Isi file service.**
    Salin konfigurasi di bawah ini, dan **ganti `<PATH_DIREKTORI_ANDA>`** dengan path yang Anda dapatkan dari perintah `pwd`.

    ```ini
    [Unit]
    Description=Jadwal Donghua Telegram Bot
    After=network.target

    [Service]
    User=root
    WorkingDirectory=<PATH_DIREKTORI_ANDA>
    ExecStart=<PATH_DIREKTORI_ANDA>/venv/bin/python3 <PATH_DIREKTORI_ANDA>/jadwalbot.py
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

4.  **Reload, Enable, dan Start Service.**
    ```bash
    # Reload systemd untuk membaca file service baru
    sudo systemctl daemon-reload

    # Enable service agar otomatis berjalan saat server reboot
    sudo systemctl enable jadwalbot.service

    # Start service sekarang juga
    sudo systemctl start jadwalbot.service
    ```

### **Langkah 9: Cek Status Service**

Untuk memastikan bot berjalan dengan baik, cek statusnya.

```bash
sudo systemctl status jadwalbot.service
```

Jika statusnya `active (running)`, maka bot Anda telah berhasil di-deploy dan berjalan sebagai service.

---

**Selesai!** Bot Anda sekarang sudah online.
