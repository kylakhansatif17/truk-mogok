import networkx as nx
import pytest

from algorithms.registry import AlgorithmRegistry
from cases.scenario_loader import ScenarioLoader
from scripts.build_radar_auri import (
    BuildError,
    build_scenario,
    compute_capacity,
    fcuk_from_population,
    interpolate,
    FCLJ_2_2TT,
    read_csv_rows,
    write_yaml,
)


def _road(dari, ke, tipe="2/2TT", lebar="7", fchs="0.95", panjang="0.3", lokasi="", split="50-50", arah="2arah", lajur=""):
    return {
        "dari": dari, "ke": ke, "nama_jalan": f"Jalan Uji {dari}-{ke}", "arah": arah,
        "tipe_jalan": tipe, "lebar_m": lebar, "lajur_per_arah": lajur, "pemisahan_arah": split,
        "khs": "S", "lkp_m": "1.0", "fchs": fchs, "panjang_km": panjang, "lokasi_truk": lokasi,
        "c0": "", "fclj": "", "fcpa": "", "bukti": "", "catatan": "",
    }


def _virtual(dari, ke):
    row = _road(dari, ke, tipe="virtual", lebar="", fchs="", panjang="", arah="1arah")
    return row


def _synthetic_network(truck_row_lokasi="2arah"):
    """20 simpul: S, T, 1 titik masuk, 1 titik keluar, 16 persimpangan dalam 2 koridor paralel."""
    simpul = [{"kode": "S", "nama": "Super Source", "jenis": "super_source", "lat": "", "lng": "", "bukti": "", "catatan": ""}]
    simpul.append({"kode": "M1", "nama": "Uji Masuk", "jenis": "masuk", "lat": "-6.370", "lng": "106.860", "bukti": "", "catatan": ""})
    for i in range(1, 9):
        simpul.append({"kode": f"A{i}", "nama": f"Uji Simpang A{i}", "jenis": "persimpangan", "lat": "-6.365", "lng": f"{106.860 + 0.004 * i:.3f}", "bukti": "", "catatan": ""})
        simpul.append({"kode": f"B{i}", "nama": f"Uji Simpang B{i}", "jenis": "persimpangan", "lat": "-6.375", "lng": f"{106.860 + 0.004 * i:.3f}", "bukti": "", "catatan": ""})
    simpul.append({"kode": "K1", "nama": "Uji Keluar", "jenis": "keluar", "lat": "-6.370", "lng": "106.900", "bukti": "", "catatan": ""})
    simpul.append({"kode": "T", "nama": "Super Sink", "jenis": "super_sink", "lat": "", "lng": "", "bukti": "", "catatan": ""})

    ruas = [_virtual("S", "M1"), _virtual("K1", "T"), _road("M1", "A1", lebar="8"), _road("M1", "B1", lebar="6")]
    for i in range(1, 8):
        lokasi = truck_row_lokasi if i == 3 else ""
        ruas.append(_road(f"A{i}", f"A{i + 1}", lebar="7", lokasi=lokasi))
        ruas.append(_road(f"B{i}", f"B{i + 1}", lebar="5.5"))
    ruas.append(_road("A4", "B4", lebar="5"))
    ruas.append(_road("A8", "K1", lebar="8"))
    ruas.append(_road("B8", "K1", lebar="6"))
    return simpul, ruas


# ---------------------------------------------------------------------------
# Perhitungan PKJI
# ---------------------------------------------------------------------------
def test_capacity_2_2tt_matches_pkji_formula():
    cap = compute_capacity(_road("X", "Y", lebar="7", fchs="0.95"), fcuk=1.0, line="uji")
    assert cap["c_total"] == pytest.approx(2900 * 1.00 * 1.00 * 0.95 * 1.0, abs=0.1)
    assert cap["c_maju"] == pytest.approx(cap["c_total"] / 2, abs=0.1)
    assert cap["c_balik"] == pytest.approx(cap["c_total"] / 2, abs=0.1)


def test_capacity_2_2tt_directional_split_uses_fcpa_and_share():
    cap = compute_capacity(_road("X", "Y", lebar="6", fchs="0.9", split="60-40"), fcuk=1.0, line="uji")
    total = 2900 * 0.87 * 0.94 * 0.9
    assert cap["c_total"] == pytest.approx(total, abs=0.1)
    assert cap["c_maju"] == pytest.approx(total * 0.6, abs=0.1)
    assert cap["c_balik"] == pytest.approx(total * 0.4, abs=0.1)


def test_capacity_multilane_per_direction():
    row = _road("X", "Y", tipe="4/2T", lebar="3.5", lajur="2", fchs="1.0")
    cap = compute_capacity(row, fcuk=1.0, line="uji")
    assert cap["c_maju"] == pytest.approx(1650 * 2, abs=0.1)
    assert cap["c_balik"] == pytest.approx(1650 * 2, abs=0.1)


def test_fclj_interpolation_and_out_of_range():
    assert interpolate(FCLJ_2_2TT, 5.5) == pytest.approx((0.56 + 0.87) / 2, abs=1e-4)
    assert interpolate(FCLJ_2_2TT, 4.0) is None
    with pytest.raises(BuildError):
        compute_capacity(_road("X", "Y", lebar="4"), fcuk=1.0, line="uji")


def test_fclj_manual_override_allows_narrow_road():
    row = _road("X", "Y", lebar="4")
    row["fclj"] = "0.45"
    cap = compute_capacity(row, fcuk=1.0, line="uji")
    assert cap["fclj"] == 0.45


def test_missing_fchs_is_rejected():
    with pytest.raises(BuildError, match="fchs"):
        compute_capacity(_road("X", "Y", fchs=""), fcuk=1.0, line="uji")


@pytest.mark.parametrize("juta, expected", [(0.05, 0.86), (0.3, 0.90), (0.8, 0.94), (2.0, 1.00), (3.5, 1.04)])
def test_fcuk_table(juta, expected):
    assert fcuk_from_population(juta) == expected


# ---------------------------------------------------------------------------
# Pembangunan skenario
# ---------------------------------------------------------------------------
def test_build_scenario_contract():
    simpul, ruas = _synthetic_network()
    result = build_scenario(simpul, ruas, penduduk_juta=2.0, faktor_satu_lajur=0.4)
    sc = result.scenario

    ids = [n["id"] for n in sc["nodes"]]
    assert ids == list(range(len(ids))) and len(ids) >= 20
    assert sc["execution_plan"]["start_node"] == 0
    assert sc["execution_plan"]["goal_node"] == len(ids) - 1
    assert all(e["weight"] > 0 and e["capacity"] >= 0 for e in sc["edges"])

    events = sc["execution_plan"]["events"]
    assert len(events) == 4  # 2 arah x (tutup total + 1 lajur)
    assert {e["new_capacity"] for e in events if e["step"] == 1} == {0.0}
    step2 = [e for e in events if e["step"] == 2]
    for e in step2:
        u, v = e["target_edge"]
        normal = next(x["capacity"] for x in sc["edges"] if (x["from"], x["to"]) == (u, v))
        assert e["new_capacity"] == pytest.approx(normal * 0.4, abs=0.1)


def test_max_flow_drops_when_truck_blocks_and_matches_repo_algorithms():
    simpul, ruas = _synthetic_network()
    result = build_scenario(simpul, ruas, penduduk_juta=2.0, faktor_satu_lajur=0.4)
    a = result.analysis
    assert a["tutup_total"]["max_flow"] < a["normal"]["max_flow"]
    assert a["tutup_total"]["max_flow"] <= a["satu_lajur"]["max_flow"] <= a["normal"]["max_flow"]
    assert a["tutup_total"]["max_flow"] > 0  # koridor B masih terbuka


@pytest.mark.parametrize("algo_key", ["ford_fulkerson", "dinic"])
def test_generated_yaml_runs_in_repo_pipeline(tmp_path, algo_key):
    simpul, ruas = _synthetic_network()
    result = build_scenario(simpul, ruas, penduduk_juta=2.0, faktor_satu_lajur=0.4)
    path = tmp_path / "case_uji.yaml"
    write_yaml(result.scenario, path, 2.0, 0.4)

    loader = ScenarioLoader(path)
    model = loader.build_graph_model()
    plan = loader.get_execution_plan()
    solver = AlgorithmRegistry.create(algo_key, model)

    flow = solver.run(plan["start_node"], plan["goal_node"])
    flow = flow[1] if isinstance(flow, tuple) else flow
    assert flow == pytest.approx(result.analysis["normal"]["max_flow"], abs=0.5)

    for event in plan["events"]:
        out = solver.handle_dynamic_event(
            {"type": event["type"], "edge": tuple(event["target_edge"]), "new_capacity": event["new_capacity"],
             "source": plan["start_node"], "sink": plan["goal_node"]}
        )
    out = out[1] if isinstance(out, tuple) else out
    assert out == pytest.approx(result.analysis["satu_lajur"]["max_flow"], abs=0.5)


def test_rejects_fewer_than_20_nodes():
    simpul, ruas = _synthetic_network()
    with pytest.raises(BuildError, match="minimal 20"):
        build_scenario(simpul[:10] + simpul[-1:], ruas, penduduk_juta=2.0, faktor_satu_lajur=0.4)


def test_rejects_missing_truck_location():
    simpul, ruas = _synthetic_network(truck_row_lokasi="")
    with pytest.raises(BuildError, match="lokasi_truk"):
        build_scenario(simpul, ruas, penduduk_juta=2.0, faktor_satu_lajur=0.4)


def test_rejects_unknown_node_code():
    simpul, ruas = _synthetic_network()
    ruas.append(_road("A1", "TIDAKADA"))
    with pytest.raises(BuildError, match="TIDAKADA"):
        build_scenario(simpul, ruas, penduduk_juta=2.0, faktor_satu_lajur=0.4)


def test_csv_semicolon_and_decimal_comma_from_excel(tmp_path):
    path = tmp_path / "ruas_excel.csv"
    path.write_text("# komentar\ndari;ke;lebar_m;fchs\nA;B;5,5;0,92\n", encoding="utf-8")
    rows = read_csv_rows(path)
    assert rows == [{"dari": "A", "ke": "B", "lebar_m": "5,5", "fchs": "0,92"}]
    cap = compute_capacity(_road("A", "B", lebar=rows[0]["lebar_m"], fchs=rows[0]["fchs"]), fcuk=1.0, line="uji")
    assert cap["fclj"] == pytest.approx(0.715, abs=1e-4) and cap["fchs"] == 0.92


def test_csv_templates_parse_with_comments():
    simpul = read_csv_rows(__import__("config.settings", fromlist=["BASE_DIR"]).BASE_DIR / "docs" / "data" / "simpul_radar_auri.csv")
    assert {r["jenis"] for r in simpul} >= {"super_source", "super_sink"}
