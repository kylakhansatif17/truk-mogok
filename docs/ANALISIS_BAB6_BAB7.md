# Analisis Eksperimen, Benchmark, & Mitigasi Graf (Bab 6 & Bab 7)

Dokumen ini disusun oleh **Anggota 4** sebagai bahan lengkap untuk **Bab 6 (Hasil Simulasi, Benchmark, & Pembahasan)**, **Bab 7 (Usulan Mitigasi & Kesimpulan Analisis)**, serta **Bagian 4 Presentasi Video ETS**.

---

## 1. Hasil Eksperimen Graf Nyata Jl. Radar Auri ($V = 23, E = 41$)

Sumber skenario: `cases/scenarios/case_07_truk_mogok_radar_auri.yaml`  
Perintah eksekusi:
```bash
python -m scripts.run_simulation cases/scenarios/case_07_truk_mogok_radar_auri.yaml -a ford_fulkerson --save-plots --no-show
python -m scripts.run_simulation cases/scenarios/case_07_truk_mogok_radar_auri.yaml -a dinic --save-plots --no-show
python -m scripts.run_benchmark cases/scenarios/case_07_truk_mogok_radar_auri.yaml --compare ford_fulkerson dinic
```

### A. Ringkasan Transisi Graf Dinamis (Normal → Mogok → 1 Lajur)

| Fase Simulasi | Kondisi Ruas Gangguan `(10, 16)` & `(16, 10)` | Max Flow (`skr/jam`) | Min-Cut (Bottleneck) | Status Jaringan |
| :--- | :--- | :---: | :---: | :--- |
| **Fase 0 (Normal)** | Kapasitas normal `922.0 skr/jam` | **665.8** | `[(1, 2)]` | Optimal; bottleneck alami di ruas sempit `N01–N02` (Jl. Radar Auri, lebar 4,71 m) |
| **Fase 1 (Truk Mogok)** | Ditutup total (`0.0 skr/jam`) | **0.0** | `[(10, 16)]` | ***Zero-flow / Infeasible*** — seluruh aliran ke Taman Wiladatika terputus total |
| **Fase 2 (Buka 1 Lajur 40%)** | Dibuka parsial (`368.8 skr/jam`) | **368.8** | `[(10, 16)]` | Pulih parsial (**55,4%** dari Max Flow normal `665.8`; defisit **44,6%**) |

### B. Komparasi Performa `FordFulkerson` (Edmonds-Karp) vs `Dinic`

| Metrik | Ford-Fulkerson (Edmonds-Karp) | Dinic (+ Incremental Repair) | Analisis |
| :--- | :---: | :---: | :--- |
| **Steps** | 17 | 16 | Dinic melakukan lebih sedikit langkah log |
| **Initial Max Flow (`InitVal`)** | `665.8 skr/jam` | `665.8 skr/jam` | Identik (Global Optimum) |
| **Post-Event Max Flow (`PostVal`)** | `368.8 skr/jam` | `368.8 skr/jam` | Identik (Global Optimum) |
| **Initial Runtime (`Init(ms)`)** | `0.4272 ms` | `0.5925 ms` | Pada graf kecil & jarang ($V=23, E=41$), Dinic sedikit lebih lambat karena *overhead* membangun Level Graph & *pointer* |
| **Dynamic Runtime (`Dyn(ms)`)** | `1.5747 ms` | `0.6186 ms` | **Dinic ~2,55× lebih cepat** karena *Incremental Residual Repair* tidak membuang aliran lama dan tidak menghitung ulang dari nol |
| **Min-Cut Akhir** | `[(10, 16)]` | `[(10, 16)]` | Konsisten menunjuk ruas pertigaan Radar Auri × Putri Tunggal |

---

## 2. Bab 6.5 — Estimasi Kendaraan Tertahan Selama 90 Menit (13.30–15.00 WIB)

Berdasarkan berita detikNews (17 Maret 2025), truk kontainer mogok berlangsung selama **±90 menit ($T = 1{,}5\ \text{jam}$)** dan memicu kemacetan sepanjang **±5,5 km** hingga Jl. Putri Tunggal dan Taman Wiladatika.

Dengan kapasitas aliran maksimum normal koridor sebesar **$F_{\text{normal}} = 665{,}8\ \text{skr/jam}$**, kita dapat menghitung estimasi jumlah kendaraan (*satuan kendaraan ringan*, `skr`) yang tertahan:

1. **Skenario A — Penutupan Total Penuh 90 Menit ($F_{\text{mogok}} = 0\ \text{skr/jam}$):**
   $$\text{Defisit Aliran} = 665{,}8 - 0 = 665{,}8\ \text{skr/jam}$$
   $$\text{Kendaraan Tertahan} = 665{,}8 \times 1{,}5\ \text{jam} = \mathbf{998{,}7 \approx 999\ \text{skr}}$$

2. **Skenario B — Bertahap (45 Menit Tutup Total + 45 Menit Buka 1 Lajur $368{,}8\ \text{skr/jam}$):**
   - 45 menit pertama ($0{,}75\ \text{jam}$): $(665{,}8 - 0) \times 0{,}75 = 499{,}35\ \text{skr}$
   - 45 menit kedua ($0{,}75\ \text{jam}$): $(665{,}8 - 368{,}8) \times 0{,}75 = 297{,}0 \times 0{,}75 = 222{,}75\ \text{skr}$
   - **Total tertahan** $= 499{,}35 + 222{,}75 = \mathbf{722{,}1 \approx 722\ \text{skr}}$

3. **Skenario C — 1 Lajur Parsial Penuh 90 Menit ($F_{\text{1-lajur}} = 368{,}8\ \text{skr/jam}$):**
   $$\text{Kendaraan Tertahan} = (665{,}8 - 368{,}8) \times 1{,}5 = 297{,}0 \times 1{,}5 = \mathbf{445{,}5 \approx 446\ \text{skr}}$$

**Validasi Empiris terhadap Panjang Antrean (±5,5 km):**  
Jika 1 `skr` (mobil pribadi + jarak antar kendaraan saat macet merayap) menempati sekitar **5,5–6,0 meter** pada 1 lajur efektif, maka akumulasi **722–999 skr** menghasilkan panjang antrean sekitar **4,0–6,0 km**. Angka ini sangat konsisten dengan laporan lapangan **±5,5 km**.

---

## 3. Uji Skala Sintetis ($V = 20, 50, 100, 200$) — Analisis Overkill vs Optimal

Untuk menguji batas di mana Dinic menjadi jauh lebih unggul dibanding Edmonds-Karp, dijalankan `scripts/run_scale_benchmark.py` (5 seed per ukuran, median runtime, dengan 2 event dinamis: tutup total `0.0` lalu buka `40%`):

```bash
python -m scripts.run_scale_benchmark --save
```

| $V$ | $E$ | FF Init (ms) | Dinic Init (ms) | FF Dyn (ms) | Dinic Dyn (ms) | Speedup Dinamis | Speedup Total |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **20** | 102 | `2.8156` | `1.9370` | `5.9483` | `0.9031` | **6,59×** | **3,09×** |
| **50** | 294 | `6.8298` | `2.6720` | `15.6496` | `0.5050` | **30,99×** | **7,08×** |
| **100** | 622 | `6.8114` | `3.7382` | `19.5156` | `0.9561` | **20,41×** | **5,61×** |
| **200** | 1272 | `15.5697` | `8.7513` | `38.4856` | `1.6280` | **23,64×** | **5,21×** |

Visualisasi tersimpan di `output/plot_scale_benchmark.png` dan data mentah di `output/scale_benchmark_results.json`.

### Kesimpulan Overkill vs Optimal
- **Kapan Dinic terasa *Overkill*?**  
  Pada graf kecil dan jarang ($V = 23, E = 41$) dengan **hanya 1× komputasi statis**, *Edmonds-Karp* (`0.4272 ms`) sedikit lebih cepat daripada *Dinic* (`0.5925 ms`) karena Dinic harus mengalokasikan tabel `level`, `adj`, dan `ptr` (*current-arc pointer*).
- **Kapan Dinic menjadi *Optimal*?**  
  1. **Saat terjadi perubahan kapasitas dinamis**: Pada skenario Radar Auri ($V=23$), Dinic **2,55× lebih cepat** (`0.6186 ms` vs `1.5747 ms`) karena *Incremental Residual Repair* mempertahankan aliran yang sudah ada dan hanya memperbaiki/membatalkan aliran yang terdampak secara lokal.
  2. **Saat skala jaringan membesar ($V \ge 50$ atau graf padat)**: Dinic unggul **~2×** pada inisialisasi dan **20–31× lebih cepat** pada evaluasi dinamis.

---

## 4. Pembuktian Global Optimum & Analisis Min-Cut

Berdasarkan **Teorema Max-Flow Min-Cut** (*Ford–Fulkerson Theorem*), untuk setiap jaringan aliran $(G, s, t)$, nilai aliran maksimum (*Max Flow*) **selalu sama dengan** kapasitas minimum dari partisi $(S, T)$ (*Min-Cut*):
$$|f^*| = \min_{(S, T)} \sum_{u \in S, v \in T} c(u, v)$$

Pada seluruh fase simulasi `case_07_truk_mogok_radar_auri`:
1. **Fase Normal**: Max Flow = `665.8`, dan kapasitas edge Min-Cut `[(1, 2)]` = `665.8` (**Global Optimum tercapai**).
2. **Fase Truk Mogok**: Edge `(10, 16)` menjadi `0.0`. Karena `(10, 16)` adalah satu-satunya *bridge / cut-edge* yang menghubungkan klaster Radar Auri–Putri Tunggal ke klaster `N16–N17` (Buperta / Taman Wiladatika), kapasitas Min-Cut menjadi `0.0` dan jaringan menjadi ***zero-flow / infeasible***.
3. **Fase Buka 1 Lajur**: Kapasitas `(10, 16)` naik ke `368.8`. Karena `368.8 < 665.8`, Min-Cut tetap berada di `[(10, 16)]` dengan kapasitas `368.8` (**Global Optimum baru tercapai**).

Kedua algoritma (`FordFulkerson` maupun `Dinic` inkremental) menghasilkan nilai Max Flow dan Min-Cut yang **identik 100%** di setiap fase, membuktikan bahwa *Incremental Residual Repair* tetap menjaga sifat **Global Optimum**.

---

## 5. Bab 7 — Usulan Mitigasi Berbasis Graf

1. **Penambahan Edge Alternatif (*Bypass* / Menghilangkan *Cut-Edge*)**:  
   Titik kritis utama adalah `(10, 16)` yang berperan sebagai *single point of failure* (saat ditutup, Max Flow langsung jatuh ke `0.0`). Penambahan jalur alternatif/penghubung dari koridor selatan (`N12` / `N21` Jl. Ramitor–Telkom) atau jalur lokal menuju `N16`/`N17` akan memecah ketergantungan tunggal sehingga saat `(10, 16)` tertutup total, Max Flow tidak menjadi nol.
2. **Pelebaran / Manajemen Hambatan Samping pada Bottleneck Normal `(1, 2)`**:  
   Dalam kondisi normal, kapasitas seluruh koridor tertahan di `665.8 skr/jam` hanya karena segmen `N01–N02` (lebar 4,71 m, hambatan samping tinggi `FCHS = 0.82`), padahal segmen lain memiliki kapasitas `831–1313 skr/jam`. Penertiban parkir/aktivitas tepi jalan di `N01–N02` dapat menaikkan kapasitas dasar koridor secara signifikan.
3. **Rekayasa *Contraflow* Cepat Berbasis Deteksi Bottleneck Dinamis**:  
   Saat gangguan terjadi di pertigaan `N10 → N16`, pembukaan 1 lajur (`368.8 skr/jam`) langsung memulihkan **55,4%** aliran maksimum normal. Implementasi skema *contraflow* cepat pada arah berlawanan (`(16, 10)`) dapat memaksimalkan kapasitas sisa sambil menunggu evakuasi truk.
