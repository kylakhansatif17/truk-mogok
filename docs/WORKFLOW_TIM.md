# Panduan Workflow & Spesifikasi Teknis Tim — Tubes Matdis Lanjut 2026

> **Catatan untuk Anggota Tim & AI Assistant:** Dokumen ini adalah *handoff specification* resmi kelompok untuk menyelaraskan pekerjaan kode, pemodelan graf, eksperimen, dokumentasi, dan presentasi video ETS. Pastikan seluruh kontribusi mengikuti kontrak kode dan rubrik di bawah ini.

---

## 1. Identitas & Ruang Lingkup Proyek

| Item | Keterangan |
| :--- | :--- |
| **Mata Kuliah** | Matematika Diskrit Lanjut (ETS 2026) |
| **Kelas & Anggota (4 Orang)** | **Kelas 2A D4** — NIM akhir: **`003`, `013`, `018`, `026`** *(Catatan: NIM `027` sudah tidak di kelompok — hapus dari dokumen Word/slide jika masih tercantum)* |
| **Isu Kontemporer Nyata** | Truk kontainer mogok tidak kuat menanjak di Pertigaan Jl. Radar Auri, Cimanggis, Depok — Senin, 17 Maret 2025 (±13.30–15.00 WIB, durasi ±90 menit, dampak kemacetan ±5,5 km hingga Jl. Putri Tunggal & Taman Wiladatika). Sumber: [detikNews (18 Maret 2025)](https://news.detik.com/berita/d-7828306/truk-kontainer-mogok-di-jalan-sempit-berujung-horor-macet-di-depok) |
| **Domain Graf** | **Maximum Flow / Bottleneck Analysis (Min-Cut)** (Kasus 7: `case_07_truk_mogok`) |
| **Algoritma Klasik (Basic)** | **Ford-Fulkerson (Varian Edmonds-Karp / BFS)** — $O(VE^2)$, *full re-computation* dari nol saat kapasitas berubah |
| **Algoritma Lanjut (Advance)** | **Dinic's Algorithm + Incremental Residual Repair** — $O(V^2E)$, Level Graph (BFS) + Blocking Flow (DFS + *current-arc pointer*) + perbaikan residual inkremental |
| **Repositori Tim** | `https://github.com/kylakhansatif17/truk-mogok` (wajib **Public**) |
| **Tenggat Pengumpulan** | **30 November 2026, 23:59 WIB** |

---

## 2. Arsitektur Kode yang Sudah Siap di Repo

Struktur kode mengikuti template dosen (`trisgelar/matdis-tubes-2026`) dengan prinsip **SOLID** dan **Data-Driven YAML**. Pipeline Max-Flow sudah selesai dibangun di branch `feat/maxflow-pipeline` (lulus **45/45 automated tests**):

- `core/graph_model.py` — `SpatialGraphModel` sudah mendukung atribut `capacity` & `update_edge_capacity()`.
- `cases/scenario_loader.py` — Otomatis membaca `weight` dan `capacity` dari file YAML.
- `algorithms/maxflow/ford_fulkerson.py` — Implementasi **Edmonds-Karp (BFS)**, mendukung jalan 2 arah (*antiparallel edges*), `DYNAMIC_EDGE_CAPACITY` (*full re-computation*), `get_flow_distribution()`, dan `get_min_cut()`. Terdaftar di `AlgorithmRegistry` dengan key `ford_fulkerson` (alias `edmonds_karp`, `maxflow`).
- `algorithms/maxflow/dinic.py` — `Dinic(FordFulkerson)` dengan **Level Graph + Blocking Flow** dan **Incremental Residual Repair** (0 komputasi ulang jika aliran $\le c_{\text{new}}$; *local reroute* $u \to v$ + pembatalan parsial jika kapasitas turun di bawah aliran aktif; langsung *augment* residual saat kapasitas dibuka kembali). Terdaftar dengan key `dinic`.
- `core/simulation_runner.py`, `core/simulation_observers.py`, `core/visualizer.py` — Mendukung `DYNAMIC_EDGE_CAPACITY`, mencetak Max Flow & Min-Cut, mengekspor JSON trace per algoritma (`output/output_<case_id>_<algo>.json`), serta menggambar plot Matplotlib lengkap dengan label `flow/capacity`, garis oranye putus-putus (**Min-Cut**), dan merah tebal (**edge gangguan**).
- `scripts/run_simulation.py` & `scripts/run_benchmark.py` — Mendukung ekspor plot PNG (`--save-plots --no-show`) dan komparasi tabel (`--compare ford_fulkerson dinic`).
- `tests/test_maxflow.py` — Unit test & stress test (termasuk jaringan 2 arah 20-simpul dan 15 graf acak 22-simpul yang diverifikasi terhadap `networkx.maximum_flow_value` & Teorema Max-Flow Min-Cut).

### Setup & Perintah CLI Siap Pakai
Jalankan dari root folder `truk-mogok/`:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Pastikan seluruh test lulus (WAJIB dijalankan sebelum commit/PR!)
python -m pytest -v

# 3. Jalankan simulasi + simpan PNG plot & JSON trace ke output/
python -m scripts.run_simulation cases/scenarios/<file_yaml_kalian>.yaml -a ford_fulkerson --save-plots --no-show
python -m scripts.run_simulation cases/scenarios/<file_yaml_kalian>.yaml -a dinic --save-plots --no-show

# 4. Bandingkan performa Basic vs Advance (Steps, InitVal, PostVal, Runtime ms, Min-Cut)
python -m scripts.run_benchmark cases/scenarios/<file_yaml_kalian>.yaml --compare ford_fulkerson dinic
```

---

## 3. Kontrak Format YAML Graf Nyata ($V \ge 20$) & Metodologi Kapasitas

> **PERINGATAN PENTING (UNTUK TIM & AI):**
> Rubrik Bagian 2 berbobot **25%**. **JANGAN biarkan AI mengarang nama persimpangan, posisi peta, atau angka kapasitas fiktif.** Data persimpangan, lebar jalan, dan kondisi lalu lintas **wajib diambil dari observasi Google Maps / Street View / Live Traffic nyata** di sekitar Jl. Radar Auri – Jl. Putri Tunggal – Taman Wiladatika dan dihitung memakai acuan resmi **PKJI 2014 / PKJI 2023 (Kementerian PUPR)**.

### A. Syarat Wajib File Skenario Baru
Simpan file graf utama tim di:
`cases/scenarios/case_07_truk_mogok_radar_auri.yaml`
*(Biarkan `cases/scenarios/case_07_truk_mogok.yaml` bawaan dosen tetap utuh agar tidak merusak test existing.)*

Kontrak agar otomatis lulus `tests/test_all_scenarios.py` dan berjalan mulus di `FordFulkerson` maupun `Dinic`:
1. **Jumlah simpul minimal 20 (`len(nodes) >= 20`)** — ID berurutan `0` sampai `N-1`.
2. **Koordinat `pos: [x, y]`** proporsional dengan tata letak peta Google Maps agar visualisasi Matplotlib rapi dan tidak bertumpuk.
3. **Setiap edge WAJIB punya `weight` (> 0) DAN `capacity` (>= 0):**
   - `weight`: jarak (km/meter) atau waktu tempuh normal (menit) — dibutuhkan agar kontrak `test_all_scenarios.py` (yang menguji seluruh YAML dengan baseline pathfinding) tetap lulus 100%.
   - `capacity`: kapasitas ruas jalan hasil rumus **PKJI** (konsisten dalam satu satuan, mis. `smp/jam` atau `smp/menit`).
   - Jika suatu ruas jalan **dua arah**, tulis **dua edge terpisah** (`from: u, to: v` dan `from: v, to: u`).
4. **Graf terhubung dari `start_node` ($s$) ke `goal_node` ($t$)** (gunakan Super-Source / Super-Sink jika ada lebih dari 1 jalur masuk/keluar kawasan).
5. **Minimal 2 event dinamis bertipe `DYNAMIC_EDGE_CAPACITY`** sesuai kondisi nyata:
   - **Event 1 ($t_1$):** Truk kontainer mogok di pertigaan Jl. Radar Auri → `new_capacity: 0.0` (tutup total).
   - **Event 2 ($t_2$):** Petugas membuka 1 lajur / contraflow parsial → `new_capacity` naik sebagian (mis. ~30–50% kapasitas normal ruas tersebut).

### B. Template Skema YAML Valid
```yaml
case_id: "case_07_truk_mogok_radar_auri"
title: "Analisis Maximum Flow Kemacetan Truk Kontainer Mogok Jl. Radar Auri Depok"
description: "Pemodelan jaringan jalan nyata (V>=20) koridor Jl. Radar Auri - Jl. Putri Tunggal - Taman Wiladatika."

nodes:
  - id: 0
    label: "Simpang Awal / Source (Jl. Radar Auri)"
    pos: [0.0, 5.0]
  # ... tambahkan minimal hingga id: 19 (total >= 20 vertex)
  - id: 19
    label: "Kawasan Taman Wiladatika (Sink)"
    pos: [24.0, 5.0]

edges:
  - from: 0
    to: 1
    weight: 0.4        # jarak (km) atau waktu tempuh normal (menit)
    capacity: 1450.0   # kapasitas PKJI (smp/jam)
  # ... semua ruas utama & alternatif (dua arah = 2 edge berarah)

execution_plan:
  start_node: 0
  goal_node: 19
  algorithm: "dinic"
  events:
    - step: 1
      type: "DYNAMIC_EDGE_CAPACITY"
      target_edge: [5, 6]       # ganti sesuai edge pertigaan lokasi truk mogok
      new_capacity: 0.0
      description: "Truk kontainer mogok di tanjakan Pertigaan Jl. Radar Auri (tutup total)."
    - step: 2
      type: "DYNAMIC_EDGE_CAPACITY"
      target_edge: [5, 6]
      new_capacity: 550.0       # ganti sesuai perhitungan kapasitas 1 lajur PKJI
      description: "Petugas membuka 1 lajur parsial di Pertigaan Jl. Radar Auri."
```

### C. Acuan Rumus Kapasitas Jalan (PKJI 2014/2023)
$$C = C_0 \times FC_{LJ} \times FC_{PA} \times FC_{HS} \times FC_{UK}$$
- $C_0$: Kapasitas dasar (mis. jalan perkotaan 2/2 TT = `2900 smp/jam` total 2 arah atau ~`1450 smp/jam` per arah; sesuaikan tipe ruas dari Street View).
- $FC_{LJ}$: Faktor penyesuaian lebar jalur lalu lintas (ukur/estimasi dari Google Maps / Street View).
- $FC_{PA}$: Faktor pemisahan arah.
- $FC_{HS}$: Faktor hambatan samping (aktivitas warung, parkir tepi jalan, keluar-masuk kendaraan — dokumentasikan lewat Street View / Live Traffic).
- $FC_{UK}$: Faktor ukuran kota (Kota Depok > 1 juta jiwa).
- **Simpan bukti empiris** (screenshot Google Maps rute, Street View lebar jalan, Live Traffic jam 13.30–15.00 WIB, tabel perhitungan PKJI) ke folder `docs/assets/` untuk ditampilkan di slide Bagian 2.

---

## 4. Pembagian Tugas, Branch Git, & Porsi Video (4 Anggota)

Target durasi video: **30–40 menit** (~8–10 menit per anggota, semua tampil on-cam/voice-over aktif).

| Peran | Branch Git | Ruang Lingkup File & Tugas | Bagian Video & Estimasi |
| :--- | :--- | :--- | :--- |
| **Anggota 1** | `docs/isu-dan-final` | - Validasi screenshot & tautan berita detikNews (`docs/assets/`)<br>- Ekspor `docs/fishbone_truk_mogok_radar_auri.drawio` ke PNG & sorot akar masalah yang dipetakan ke graf<br>- Lengkapi Bab 1, 4, 8, 9 di dokumen Word (pastikan hanya 4 NIM: `003, 013, 018, 026`)<br>- Update `README.md` (identitas 4 anggota + tutorial penggunaan aplikasi)<br>- Gabungkan slide presentasi final di `docs/` & siapkan timestamp YouTube | **Bagian 1** (Isu Nyata & Fishbone: 5–7 mnt) **+ Bagian 5** (Batasan, Temuan Utama, Future Works & Penutup: 3–5 mnt) → **Total 8–10 mnt** |
| **Anggota 2** | `feat/scenario-radar-auri` | - Pemetaan 20+ simpul nyata Jl. Radar Auri – Wiladatika dari Google Maps<br>- Hitung kapasitas setiap ruas dengan rumus PKJI + simpan bukti screenshot Google Maps / Live Traffic di `docs/assets/`<br>- Buat `cases/scenarios/case_07_truk_mogok_radar_auri.yaml`<br>- Pastikan `python -m pytest -v` lulus 100%<br>- Lengkapi Bab 5 (Pemodelan Graf & Justifikasi Bobot) di dokumen Word | **Bagian 2** (Pemodelan Graf $V \ge 20$, jenis graf, formula kapasitas PKJI & bukti empiris) → **8–10 mnt** |
| **Anggota 3 (Salman)** | `feat/maxflow-pipeline` *(DONE)* | - Pipeline `core/`, `ScenarioLoader`, `FordFulkerson` (Edmonds-Karp), `Dinic` (Level Graph + Incremental Residual Repair), `visualizer`, `scripts/`, `tests/test_maxflow.py`<br>- Lengkapi sub-bab abstraksi Dinic vs Edmonds-Karp di Bab 2 dokumen Word<br>- Siapkan diagram abstrak alur algoritma & diagram Pipeline Input–Proses–Output (tanpa menampilkan/membaca baris kode!) | **Bagian 3** (Abstraksi Edmonds-Karp vs Dinic's + Arsitektur Pipeline I-P-O — **DILARANG baca kode baris per baris!**) → **8–10 mnt** |
| **Anggota 4** | `feat/benchmark-analysis` | - Setelah YAML Anggota 2 masuk `main`, jalankan `run_simulation --save-plots --no-show` dan `run_benchmark --compare ford_fulkerson dinic`<br>- Simpan hasil JSON & PNG plot terbaik ke `output/`<br>- *(Sangat disarankan)* Buat uji skala tambahan (mis. graf sintetis $V=50$ atau $V=100$) untuk menajamkan analisis **Overkill vs Optimal**<br>- Hitung estimasi kendaraan tertahan selama 90 menit (Bab 6.5), analisis Min-Cut, *re-computation vs incremental*, *global optimum*, & usulan mitigasi graf lain (Bab 6 & 7) | **Bagian 4** (Eksperimen Komparasi Benchmark, Simulasi Graf Dinamis Normal → Mogok → 1 Lajur, Overkill vs Optimal, Global Optimum & Min-Cut) → **7–9 mnt** |

### Pertanyaan Kritis yang WAJIB Terjawab di Video (Sesuai Rubrik)
- **Bagian 2 (25%):** Mengapa entitas jadi Vertex/Edge? Bagaimana menghitung kapasitasnya dan mengapa formulanya demikian? Apa asumsi penyederhanaannya?
- **Bagian 3 (25%):** Apa beda mekanisme abstrak Edmonds-Karp (1 augmenting path/BFS, reset dari 0) vs Dinic's (Level Graph + Blocking Flow multi-jalur + Incremental Residual Repair)? Bagaimana alur Input (`.yaml`) → Proses → Output (Visualisasi + Metrik + JSON)? **Jangan baca sintaks kode!**
- **Bagian 4 (20%):** Mana yang lebih unggul pada graf $V \approx 20$ (apakah overhead Dinic terasa kecil/overkill pada graf kecil, dan bagaimana saat perubahan dinamis)? Apakah algoritma klasik harus menghitung ulang dari nol? Apakah solusi tetap **Global Optimum** (buktikan dengan Teorema Max-Flow Min-Cut) atau bisa menjadi *infeasible/zero-flow*?
- **Bagian 5 (15%):** Apa batasan model statis/single-commodity? Apa insight terpenting kembali ke kasus Jl. Radar Auri? Jika dilanjutkan ke TA/PKM, apa perbaikan paling mendesak (mis. *Time-Expanded Flow*, integrasi API Live Traffic / CCTV IoT)?

---

## 5. Alur Kerja Git untuk Setiap Anggota

> **Prasyarat:** Pastikan PR `feat/maxflow-pipeline` sudah di-merge ke `main` terlebih dahulu sebelum Anggota 2 & 4 mulai bekerja.

```bash
# 1. Clone repo (hanya pertama kali)
git clone https://github.com/kylakhansatif17/truk-mogok.git
cd truk-mogok

# 2. Selalu sinkronkan main terbaru sebelum buat branch
git checkout main
git pull origin main

# 3. Buat branch sesuai peran masing-masing
git checkout -b <nama-branch-anda>
# contoh: git checkout -b feat/scenario-radar-auri

# 4. Setelah selesai mengedit, WAJIB jalankan test
python -m pytest -v

# 5. Commit & push ke branch sendiri
git status
git add <file_yang_diubah>
git commit -m "<tipe>: <deskripsi singkat perubahan>"
git push -u origin <nama-branch-anda>
```

6. Buka GitHub (`https://github.com/kylakhansatif17/truk-mogok`) → klik **Compare & pull request** → minta 1 teman review → **Merge pull request** ke `main`.

---

## 6. Checklist Pengumpulan Final (Sebelum 30 November 2026, 23:59)

- [ ] Semua 4 branch anggota sudah di-merge rapi ke `main` dan `python -m pytest -v` lulus 100%.
- [ ] Repo GitHub diset **Public** dan sudah memuat: kode program, YAML graf $V \ge 20$, hasil output/plot, dokumen analisis, Fishbone, `README.md` identitas + tutorial, dan **file presentasi**.
- [ ] Video berdurasi **30–40 menit**, audio jernih, seluruh 4 anggota tampil seimbang, tanpa membaca kode baris demi baris, menampilkan bukti berita + Google Maps/PKJI, serta memiliki **timestamp/chapter** di deskripsi YouTube.
- [ ] Video diunggah ke playlist **`Matdis Lanjut D4 2026 ETS Graph Kelas A`** dengan judul:
  `[MDL2026_2A_D4_2025]_ETS_003_013_018_026 - <Judul Tubes Maks 10 Kata>`
- [ ] File pengumpulan `.txt` dibuat dengan nama:
  `[MDL2026_2A_D4_2025]_ETS_003_013_018_026.txt`
  berisi:
  1. `README` (identitas kelompok 4 anggota + tutorial cara penggunaan aplikasi tubes)
  2. `Link Github : https://github.com/kylakhansatif17/truk-mogok`
  3. `Link Youtube Video : <link_youtube>`
