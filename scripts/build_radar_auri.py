import argparse
import csv
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx
import yaml

from config.settings import BASE_DIR, CASES_DIR

DEFAULT_SIMPUL_CSV = BASE_DIR / "docs" / "data" / "simpul_radar_auri.csv"
DEFAULT_RUAS_CSV = BASE_DIR / "docs" / "data" / "ruas_radar_auri.csv"
DEFAULT_OUTPUT_YAML = CASES_DIR / "case_07_truk_mogok_radar_auri.yaml"
DEFAULT_TABLE_DIR = BASE_DIR / "docs" / "data"

CASE_ID = "case_07_truk_mogok_radar_auri"

# ---------------------------------------------------------------------------
# Tabel PKJI 2014 - Kapasitas Jalan Perkotaan
# ---------------------------------------------------------------------------
C0_2_2TT = 2900.0  # skr/jam, total dua arah (per jalur)
C0_PER_LAJUR = 1650.0  # skr/jam, per lajur satu arah (4/2T atau jalan satu arah)

# FCLJ 2/2TT: lebar jalur lalu lintas efektif total dua arah (m)
FCLJ_2_2TT = [(5.0, 0.56), (6.0, 0.87), (7.0, 1.00), (8.0, 1.14), (9.0, 1.25), (10.0, 1.29), (11.0, 1.34)]
# FCLJ 4/2T atau jalan satu arah: lebar per lajur (m)
FCLJ_PER_LAJUR = [(3.25, 0.96), (3.50, 1.00), (3.75, 1.04), (4.00, 1.08)]
# FCPA khusus 2/2TT, kunci = porsi arah dominan (%)
FCPA_2_2TT = {50: 1.00, 55: 0.97, 60: 0.94, 65: 0.91, 70: 0.88}
# FCUK: (batas atas juta penduduk, faktor)
FCUK_TABLE = [(0.1, 0.86), (0.5, 0.90), (1.0, 0.94), (3.0, 1.00), (math.inf, 1.04)]

VALID_JENIS = {"super_source", "super_sink", "masuk", "keluar", "persimpangan", "perubahan_kapasitas"}
VALID_TIPE = {"2/2TT", "4/2T", "1arah", "virtual"}
VALID_KHS = {"SR", "R", "S", "T", "ST"}

KM_PER_DEG_LAT = 110.574


class BuildError(Exception):
    """Kesalahan data CSV yang harus diperbaiki sebelum YAML bisa dibuat."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("\n".join(f"- {e}" for e in errors))


@dataclass
class BuildResult:
    scenario: Dict
    capacity_rows: List[Dict]
    analysis: Dict
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------
def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    """Baca CSV, abaikan baris kosong dan baris komentar '#'."""
    with open(path, "r", encoding="utf-8-sig") as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    # Excel berbahasa Indonesia menyimpan CSV dengan pemisah ';' (dan desimal ',')
    delimiter = ";" if lines and lines[0].count(";") > lines[0].count(",") else ","
    reader = csv.DictReader(lines, delimiter=delimiter)
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def _to_float(value: str) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value.replace(",", "."))


def interpolate(table: List[Tuple[float, float]], x: float) -> Optional[float]:
    """Interpolasi linier pada tabel (x, faktor). None jika di luar rentang tabel."""
    if x < table[0][0] or x > table[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            return round(y0 + (y1 - y0) * (x - x0) / (x1 - x0), 4)
    return table[-1][1]


def fcuk_from_population(juta: float) -> float:
    for upper, factor in FCUK_TABLE:
        if juta <= upper:
            return factor
    return FCUK_TABLE[-1][1]


def parse_split(text: str) -> Tuple[float, float]:
    """'60-40' -> (60, 40). Default 50-50 jika kosong."""
    if not text:
        return 50.0, 50.0
    a, b = text.replace(" ", "").split("-")
    a, b = float(a), float(b)
    if abs(a + b - 100.0) > 1e-6:
        raise ValueError(f"pemisahan_arah '{text}' tidak berjumlah 100")
    return a, b


# ---------------------------------------------------------------------------
# Perhitungan kapasitas PKJI per ruas
# ---------------------------------------------------------------------------
def compute_capacity(row: Dict[str, str], fcuk: float, line: str) -> Dict:
    """Hitung kapasitas satu ruas. Mengembalikan faktor-faktor + kapasitas per arah (skr/jam)."""
    tipe = row["tipe_jalan"]
    arah = row["arah"]
    errors: List[str] = []

    if tipe == "virtual":
        return {"tipe": tipe, "virtual": True}

    fchs = _to_float(row.get("fchs", ""))
    if fchs is None:
        errors.append(f"{line}: kolom fchs wajib diisi dari tabel FCHS PKJI (KHS={row.get('khs') or '?'}, lkp_m={row.get('lkp_m') or '?'})")
    khs = row.get("khs", "")
    if khs and khs not in VALID_KHS:
        errors.append(f"{line}: khs '{khs}' harus salah satu dari {sorted(VALID_KHS)}")

    lebar = _to_float(row.get("lebar_m", ""))
    c0_override = _to_float(row.get("c0", ""))
    fclj_override = _to_float(row.get("fclj", ""))
    fcpa_override = _to_float(row.get("fcpa", ""))

    result = {"tipe": tipe, "virtual": False, "fcuk": fcuk, "fchs": fchs, "catatan_hitung": []}

    if tipe == "2/2TT":
        if arah != "2arah":
            errors.append(f"{line}: tipe 2/2TT harus arah=2arah")
        c0 = c0_override if c0_override is not None else C0_2_2TT
        if fclj_override is not None:
            fclj = fclj_override
            result["catatan_hitung"].append("FCLJ diisi manual")
        elif lebar is None:
            fclj = None
            errors.append(f"{line}: lebar_m (lebar jalur total 2 arah) wajib diisi")
        else:
            fclj = interpolate(FCLJ_2_2TT, lebar)
            if fclj is None:
                errors.append(
                    f"{line}: lebar {lebar} m di luar tabel FCLJ 2/2TT (5-11 m). "
                    "Isi kolom fclj manual + jelaskan asumsinya di catatan."
                )
            elif lebar not in dict(FCLJ_2_2TT):
                result["catatan_hitung"].append(f"FCLJ interpolasi linier untuk {lebar} m")
        try:
            share_a, share_b = parse_split(row.get("pemisahan_arah", ""))
        except ValueError as exc:
            errors.append(f"{line}: {exc}")
            share_a, share_b = 50.0, 50.0
        if fcpa_override is not None:
            fcpa = fcpa_override
        else:
            dominant = int(round(max(share_a, share_b)))
            fcpa = FCPA_2_2TT.get(dominant)
            if fcpa is None:
                errors.append(
                    f"{line}: pemisahan_arah {row.get('pemisahan_arah')} tidak ada di tabel FCPA "
                    "(50-50, 55-45, 60-40, 65-35, 70-30). Pakai nilai tabel atau isi kolom fcpa."
                )
        if errors:
            raise BuildError(errors)
        total = c0 * fclj * fcpa * fchs * fcuk
        result.update(
            c0=c0, fclj=fclj, fcpa=fcpa, lajur=None,
            c_total=round(total, 1),
            c_maju=round(total * share_a / 100.0, 1),
            c_balik=round(total * share_b / 100.0, 1),
            share=(share_a, share_b),
        )
        return result

    if tipe in ("4/2T", "1arah"):
        if tipe == "1arah" and arah != "1arah":
            errors.append(f"{line}: tipe 1arah harus arah=1arah")
        lajur = _to_float(row.get("lajur_per_arah", ""))
        if lajur is None or lajur <= 0:
            errors.append(f"{line}: lajur_per_arah wajib diisi (> 0) untuk tipe {tipe}")
        c0 = c0_override if c0_override is not None else C0_PER_LAJUR
        if fclj_override is not None:
            fclj = fclj_override
            result["catatan_hitung"].append("FCLJ diisi manual")
        elif lebar is None:
            fclj = None
            errors.append(f"{line}: lebar_m (lebar per lajur) wajib diisi")
        else:
            fclj = interpolate(FCLJ_PER_LAJUR, lebar)
            if fclj is None:
                errors.append(
                    f"{line}: lebar lajur {lebar} m di luar tabel FCLJ per lajur (3,25-4,00 m). "
                    "Isi kolom fclj manual + jelaskan asumsinya di catatan."
                )
        fcpa = fcpa_override if fcpa_override is not None else 1.0
        if errors:
            raise BuildError(errors)
        per_arah = c0 * fclj * fcpa * fchs * fcuk * lajur
        result.update(
            c0=c0, fclj=fclj, fcpa=fcpa, lajur=lajur,
            c_total=round(per_arah * (2 if arah == "2arah" else 1), 1),
            c_maju=round(per_arah, 1),
            c_balik=round(per_arah, 1) if arah == "2arah" else None,
            share=None,
        )
        return result

    raise BuildError([f"{line}: tipe_jalan '{tipe}' tidak dikenal ({sorted(VALID_TIPE)})"])


# ---------------------------------------------------------------------------
# Pembangun skenario
# ---------------------------------------------------------------------------
def _project_positions(nodes: List[Dict[str, str]]) -> Dict[str, Tuple[float, float]]:
    """Proyeksi lat/lng -> koordinat lokal km (equirectangular), relatif ke titik barat-daya."""
    geo = {n["kode"]: (_to_float(n["lat"]), _to_float(n["lng"])) for n in nodes if n["lat"] and n["lng"]}
    if not geo:
        return {}
    lat0 = min(lat for lat, _ in geo.values())
    lng0 = min(lng for _, lng in geo.values())
    lat_mid = sum(lat for lat, _ in geo.values()) / len(geo)
    km_per_deg_lng = 111.320 * math.cos(math.radians(lat_mid))
    return {
        kode: (round((lng - lng0) * km_per_deg_lng, 3), round((lat - lat0) * KM_PER_DEG_LAT, 3))
        for kode, (lat, lng) in geo.items()
    }


def build_scenario(
    simpul_rows: List[Dict[str, str]],
    ruas_rows: List[Dict[str, str]],
    penduduk_juta: float,
    faktor_satu_lajur: float,
    min_simpul: int = 20,
) -> BuildResult:
    errors: List[str] = []
    warnings: List[str] = []

    if not 0 < faktor_satu_lajur < 1:
        errors.append("--faktor-satu-lajur harus di antara 0 dan 1 (mis. 0.3-0.5 sesuai WORKFLOW_TIM)")

    # ---- simpul ----
    kode_seen = set()
    for i, n in enumerate(simpul_rows, start=1):
        line = f"simpul baris {i} ({n.get('kode') or '?'})"
        if not n.get("kode"):
            errors.append(f"{line}: kode kosong")
            continue
        if n["kode"] in kode_seen:
            errors.append(f"{line}: kode duplikat")
        kode_seen.add(n["kode"])
        if n.get("jenis") not in VALID_JENIS:
            errors.append(f"{line}: jenis '{n.get('jenis')}' harus salah satu dari {sorted(VALID_JENIS)}")
        if n.get("jenis") not in ("super_source", "super_sink"):
            if not n.get("lat") or not n.get("lng"):
                errors.append(f"{line}: lat/lng wajib diisi dari Google Maps")
            else:
                try:
                    lat, lng = _to_float(n["lat"]), _to_float(n["lng"])
                    if not (-7.0 < lat < -6.0 and 106.0 < lng < 107.5):
                        warnings.append(f"{line}: koordinat ({lat}, {lng}) di luar area Depok, cek tertukar lat/lng?")
                except ValueError:
                    errors.append(f"{line}: lat/lng bukan angka")

    sources = [n for n in simpul_rows if n.get("jenis") == "super_source"]
    sinks = [n for n in simpul_rows if n.get("jenis") == "super_sink"]
    if len(sources) != 1 or len(sinks) != 1:
        errors.append("harus ada tepat 1 simpul super_source dan 1 simpul super_sink")
    if len(simpul_rows) < min_simpul:
        errors.append(f"jumlah simpul baru {len(simpul_rows)}, minimal {min_simpul} (syarat dosen V >= {min_simpul})")
    if errors:
        raise BuildError(errors)

    ordered = sources + [n for n in simpul_rows if n["jenis"] not in ("super_source", "super_sink")] + sinks
    kode_to_id = {n["kode"]: idx for idx, n in enumerate(ordered)}

    positions = _project_positions(ordered)
    if positions:
        xs = [p[0] for p in positions.values()]
        ys = [p[1] for p in positions.values()]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)

        def _mean_y(jenis: str) -> float:
            vals = [positions[n["kode"]][1] for n in ordered if n["jenis"] == jenis and n["kode"] in positions]
            return round(sum(vals) / len(vals), 3) if vals else round(sum(ys) / len(ys), 3)

        positions[sources[0]["kode"]] = (round(min(xs) - 0.12 * span, 3), _mean_y("masuk"))
        positions[sinks[0]["kode"]] = (round(max(xs) + 0.12 * span, 3), _mean_y("keluar"))

    # ---- ruas ----
    fcuk = fcuk_from_population(penduduk_juta)
    edges: List[Dict] = []
    edge_index: Dict[Tuple[int, int], Dict] = {}
    capacity_rows: List[Dict] = []
    truck_edges: List[Tuple[int, int, float]] = []
    virtual_edges: List[Tuple[int, int]] = []

    if not ruas_rows:
        raise BuildError(["tabel ruas masih kosong"])

    for i, r in enumerate(ruas_rows, start=1):
        line = f"ruas baris {i} ({r.get('dari') or '?'}->{r.get('ke') or '?'})"
        try:
            for key in ("dari", "ke"):
                if r.get(key) not in kode_to_id:
                    raise BuildError([f"{line}: kode simpul '{r.get(key)}' tidak ada di tabel simpul"])
            if r.get("dari") == r.get("ke"):
                raise BuildError([f"{line}: dari dan ke tidak boleh sama"])
            if r.get("arah") not in ("2arah", "1arah"):
                raise BuildError([f"{line}: arah harus 2arah atau 1arah"])
            if r.get("tipe_jalan") not in VALID_TIPE:
                raise BuildError([f"{line}: tipe_jalan '{r.get('tipe_jalan')}' tidak dikenal ({sorted(VALID_TIPE)})"])
            cap = compute_capacity(r, fcuk, line)
            panjang = _to_float(r.get("panjang_km", ""))
            if cap["virtual"]:
                panjang = panjang if panjang and panjang > 0 else 0.001
            elif panjang is None or panjang <= 0:
                raise BuildError([f"{line}: panjang_km wajib > 0 (ukur di Google Maps)"])
        except BuildError as exc:
            errors.extend(exc.errors)
            continue
        except ValueError as exc:
            errors.append(f"{line}: nilai angka tidak valid ({exc})")
            continue

        u, v = kode_to_id[r["dari"]], kode_to_id[r["ke"]]
        directions = [(u, v, cap.get("c_maju"))]
        if r["arah"] == "2arah":
            directions.append((v, u, cap.get("c_balik")))

        for a, b, c in directions:
            if (a, b) in edge_index:
                errors.append(f"{line}: edge {a}->{b} sudah ada (ruas ditulis dua kali?)")
                continue
            edge = {"from": a, "to": b, "weight": round(panjang, 3), "capacity": c}
            edges.append(edge)
            edge_index[(a, b)] = edge
            if cap["virtual"]:
                virtual_edges.append((a, b))

        lokasi = r.get("lokasi_truk", "")
        if lokasi:
            if cap["virtual"]:
                errors.append(f"{line}: lokasi_truk tidak boleh di ruas virtual")
            elif lokasi == "2arah":
                truck_edges.extend((a, b, c) for a, b, c in directions)
            elif lokasi == "searah":
                truck_edges.append(directions[0])
            else:
                errors.append(f"{line}: lokasi_truk harus kosong, '2arah', atau 'searah'")

        if not cap["virtual"]:
            capacity_rows.append(
                {
                    "ruas": f"{r['dari']}-{r['ke']}",
                    "nama_jalan": r.get("nama_jalan", ""),
                    "tipe": cap["tipe"],
                    "arah": r["arah"],
                    "lebar_m": r.get("lebar_m", ""),
                    "lajur_per_arah": cap.get("lajur") or "",
                    "khs": r.get("khs", ""),
                    "C0": cap["c0"],
                    "FCLJ": cap["fclj"],
                    "FCPA": cap["fcpa"],
                    "FCHS": cap["fchs"],
                    "FCUK": cap["fcuk"],
                    "C_total": cap["c_total"],
                    "C_dari_ke": cap["c_maju"],
                    "C_ke_dari": cap["c_balik"] if cap["c_balik"] is not None else "",
                    "panjang_km": panjang,
                    "lokasi_truk": lokasi,
                    "catatan_hitung": "; ".join(cap["catatan_hitung"]),
                    "bukti": r.get("bukti", ""),
                }
            )

    if errors:
        raise BuildError(errors)

    # Kapasitas virtual = "tak hingga" praktis: jumlah seluruh kapasitas ruas nyata
    real_total = sum(e["capacity"] for e in edges if (e["from"], e["to"]) not in set(virtual_edges))
    big_m = float(math.ceil(real_total + 1))
    for a, b in virtual_edges:
        edge_index[(a, b)]["capacity"] = big_m

    s_id, t_id = 0, len(ordered) - 1
    if not truck_edges:
        errors.append("belum ada ruas dengan kolom lokasi_truk (lokasi truk mogok wajib ditandai)")

    G = nx.DiGraph()
    G.add_nodes_from(range(len(ordered)))
    for e in edges:
        G.add_edge(e["from"], e["to"], capacity=e["capacity"], weight=e["weight"])

    if not nx.has_path(G, s_id, t_id):
        errors.append("tidak ada jalur dari super_source ke super_sink, cek sambungan virtual dan ruas")
    for n in ordered:
        nid = kode_to_id[n["kode"]]
        if G.degree(nid) == 0:
            errors.append(f"simpul {n['kode']} ({n['nama']}) tidak terhubung ke ruas mana pun")
        if n["jenis"] == "masuk" and not G.has_edge(s_id, nid):
            warnings.append(f"simpul masuk {n['kode']} belum disambung dari {sources[0]['kode']} (ruas virtual)")
        if n["jenis"] == "keluar" and not G.has_edge(nid, t_id):
            warnings.append(f"simpul keluar {n['kode']} belum disambung ke {sinks[0]['kode']} (ruas virtual)")
    if errors:
        raise BuildError(errors)

    # ---- analisis cepat (networkx sebagai pembanding independen) ----
    def _flow_and_cut(graph: nx.DiGraph) -> Tuple[float, List[Tuple[int, int]]]:
        value, (side_s, side_t) = nx.minimum_cut(graph, s_id, t_id, capacity="capacity")
        cut = sorted((a, b) for a in side_s for b in graph.successors(a) if b in side_t)
        return round(value, 1), cut

    def _with_caps(new_caps: Dict[Tuple[int, int], float]) -> nx.DiGraph:
        H = G.copy()
        for (a, b), c in new_caps.items():
            H[a][b]["capacity"] = c
        return H

    ev1_caps = {(a, b): 0.0 for a, b, _ in truck_edges}
    ev2_caps = {(a, b): round(c * faktor_satu_lajur, 1) for a, b, c in truck_edges}
    normal_flow, normal_cut = _flow_and_cut(G)
    ev1_flow, ev1_cut = _flow_and_cut(_with_caps(ev1_caps))
    ev2_flow, ev2_cut = _flow_and_cut(_with_caps(ev2_caps))

    if ev1_flow == normal_flow:
        warnings.append(
            "max flow tidak berubah saat truk menutup jalan: ruas truk bukan bottleneck di model ini. "
            "Wajar jika rute alternatif lebar, tapi cek lagi kapasitas & arah ruas sekitar lokasi truk."
        )
    if any(c in virtual_edges for c in normal_cut):
        warnings.append("min-cut normal melewati ruas virtual, cek kapasitas virtual / sambungan S-T")

    # ---- susun YAML ----
    id_to_label = {kode_to_id[n["kode"]]: n["nama"] for n in ordered}
    yaml_nodes = []
    for n in ordered:
        x, y = positions.get(n["kode"], (0.0, 0.0))
        yaml_nodes.append({"id": kode_to_id[n["kode"]], "label": f"{n['kode']} - {n['nama']}", "pos": [x, y]})

    truck_names = sorted({f"{id_to_label[a]} -> {id_to_label[b]}" for a, b, _ in truck_edges})
    events = []
    for a, b, _ in truck_edges:
        events.append(
            {
                "step": 1,
                "type": "DYNAMIC_EDGE_CAPACITY",
                "target_edge": [a, b],
                "new_capacity": 0.0,
                "description": (
                    f"Truk kontainer mogok tidak kuat menanjak di pertigaan Jl. Radar Auri: "
                    f"ruas {id_to_label[a]} -> {id_to_label[b]} tertutup total (kapasitas turun ke 0 skr/jam)."
                ),
            }
        )
    for a, b, c in truck_edges:
        events.append(
            {
                "step": 2,
                "type": "DYNAMIC_EDGE_CAPACITY",
                "target_edge": [a, b],
                "new_capacity": ev2_caps[(a, b)],
                "description": (
                    f"Petugas membuka 1 lajur: ruas {id_to_label[a]} -> {id_to_label[b]} naik dari 0 menjadi "
                    f"{ev2_caps[(a, b)]} skr/jam ({int(round(faktor_satu_lajur * 100))}% dari kapasitas normal {c})."
                ),
            }
        )

    scenario = {
        "case_id": CASE_ID,
        "title": "Analisis Maximum Flow Kemacetan Truk Kontainer Mogok Jl. Radar Auri Depok",
        "description": (
            f"Pemodelan jaringan jalan nyata (V={len(ordered)}, E={len(edges)}) koridor Jl. Radar Auri - "
            "Jl. Putri Tunggal - Taman Wiladatika. Kapasitas ruas dihitung dengan PKJI 2014 "
            "(C = C0 x FCLJ x FCPA x FCHS x FCUK, satuan skr/jam)."
        ),
        "nodes": yaml_nodes,
        "edges": edges,
        "execution_plan": {
            "start_node": s_id,
            "goal_node": t_id,
            "algorithm": "dinic",
            "events": events,
        },
    }

    analysis = {
        "jumlah_simpul": len(ordered),
        "jumlah_edge": len(edges),
        "fcuk": fcuk,
        "kapasitas_virtual": big_m,
        "ruas_truk": truck_names,
        "normal": {"max_flow": normal_flow, "min_cut": [f"{id_to_label[a]} -> {id_to_label[b]}" for a, b in normal_cut]},
        "tutup_total": {"max_flow": ev1_flow, "min_cut": [f"{id_to_label[a]} -> {id_to_label[b]}" for a, b in ev1_cut]},
        "satu_lajur": {"max_flow": ev2_flow, "min_cut": [f"{id_to_label[a]} -> {id_to_label[b]}" for a, b in ev2_cut]},
    }
    return BuildResult(scenario=scenario, capacity_rows=capacity_rows, analysis=analysis, warnings=warnings)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def write_yaml(scenario: Dict, path: Path, penduduk_juta: float, faktor: float) -> None:
    header = (
        "# FILE INI DIBUAT OTOMATIS oleh scripts/build_radar_auri.py - jangan edit manual.\n"
        "# Edit docs/data/simpul_radar_auri.csv & docs/data/ruas_radar_auri.csv lalu jalankan ulang script.\n"
        f"# Parameter: penduduk Kota Depok = {penduduk_juta} juta jiwa; faktor 1 lajur dibuka = {faktor}\n"
    )
    body = yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True, default_flow_style=None, width=120)
    path.write_text(header + body, encoding="utf-8")


def write_capacity_tables(rows: List[Dict], table_dir: Path) -> Tuple[Path, Path]:
    csv_path = table_dir / "tabel_kapasitas_pkji.csv"
    md_path = table_dir / "tabel_kapasitas_pkji.md"
    fieldnames = list(rows[0].keys())
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    cols = ["ruas", "nama_jalan", "tipe", "lebar_m", "khs", "C0", "FCLJ", "FCPA", "FCHS", "FCUK", "C_total", "C_dari_ke", "C_ke_dari"]
    lines = [
        "# Tabel Perhitungan Kapasitas Ruas (PKJI 2014)",
        "",
        "Rumus: C = C0 x FCLJ x FCPA x FCHS x FCUK (skr/jam). Dibuat otomatis oleh `scripts/build_radar_auri.py`.",
        "",
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, md_path


def print_report(result: BuildResult) -> None:
    a = result.analysis
    print("=== RINGKASAN GRAF ===")
    print(f"Simpul (V)          : {a['jumlah_simpul']}")
    print(f"Edge berarah (E)    : {a['jumlah_edge']}")
    print(f"FCUK                : {a['fcuk']}")
    print(f"Kapasitas virtual   : {a['kapasitas_virtual']} skr/jam (pengganti tak hingga)")
    print("Ruas lokasi truk    :")
    for name in a["ruas_truk"]:
        print(f"  - {name}")
    print("\n=== CEK CEPAT MAX FLOW (networkx, pembanding independen) ===")
    for key, title in (("normal", "Normal"), ("tutup_total", "Truk mogok (tutup total)"), ("satu_lajur", "1 lajur dibuka")):
        print(f"{title:26s}: {a[key]['max_flow']} skr/jam")
        for edge in a[key]["min_cut"]:
            print(f"    min-cut: {edge}")
    if result.warnings:
        print("\n=== PERINGATAN (cek lagi, bukan error) ===")
        for w in result.warnings:
            print(f"- {w}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scripts.build_radar_auri", description=(__doc__ or "Generator skenario YAML Radar Auri").split("\n")[0])
    p.add_argument("--simpul", type=Path, default=DEFAULT_SIMPUL_CSV, help="CSV tabel simpul")
    p.add_argument("--ruas", type=Path, default=DEFAULT_RUAS_CSV, help="CSV tabel ruas")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_YAML, help="path YAML keluaran")
    p.add_argument("--tabel-dir", type=Path, default=DEFAULT_TABLE_DIR, help="folder tabel kapasitas keluaran")
    p.add_argument("--penduduk-juta", type=float, required=True, help="jumlah penduduk Kota Depok (juta jiwa, dari BPS) untuk FCUK")
    p.add_argument("--faktor-satu-lajur", type=float, required=True, help="porsi kapasitas saat 1 lajur dibuka (0-1), asumsi tim")
    p.add_argument("--min-simpul", type=int, default=20, help="jumlah simpul minimal (default 20)")
    p.add_argument("--dry-run", action="store_true", help="validasi & tampilkan ringkasan tanpa menulis file")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_scenario(
            read_csv_rows(args.simpul),
            read_csv_rows(args.ruas),
            penduduk_juta=args.penduduk_juta,
            faktor_satu_lajur=args.faktor_satu_lajur,
            min_simpul=args.min_simpul,
        )
    except BuildError as exc:
        print("[GAGAL] Data CSV perlu diperbaiki dulu:")
        for e in exc.errors:
            print(f"- {e}")
        return 1

    print_report(result)
    if args.dry_run:
        print("\n[DRY RUN] Tidak ada file yang ditulis.")
        return 0

    write_yaml(result.scenario, args.output, args.penduduk_juta, args.faktor_satu_lajur)
    csv_path, md_path = write_capacity_tables(result.capacity_rows, args.tabel_dir)
    print(f"\n[OK] YAML      : {args.output}")
    print(f"[OK] Tabel CSV : {csv_path}")
    print(f"[OK] Tabel MD  : {md_path}")
    print("Lanjut: python -m pytest -v")
    return 0


if __name__ == "__main__":
    sys.exit(main())
