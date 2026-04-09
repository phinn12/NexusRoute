from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1

from kargo_backend.client import BackendClient
from kargo_backend.config import load_settings
from kargo_backend.schemas import (
    ExtractConstraintsRequest,
    JobRequest,
    Stop,
    SummarizeFailuresRequest,
    VehicleConfig,
)
from normalize_addresses import EXPECTED_COLUMNS, detect_and_load, normalize_record


st.set_page_config(page_title="Kargo Optimizasyon Merkezi", layout="wide")
st.title("Kargo Optimizasyon Merkezi")

SETTINGS = load_settings()
CLIENT = BackendClient(SETTINGS)
INBOX_DIR = Path("yerelden_gelen")
INBOX_DIR.mkdir(parents=True, exist_ok=True)


def build_csv_bytes_from_records(records: list[dict]) -> bytes:
    csv_io = io.StringIO()
    writer = csv.DictWriter(csv_io, fieldnames=EXPECTED_COLUMNS)
    writer.writeheader()
    for record in records:
        writer.writerow(record)
    return csv_io.getvalue().encode("utf-8")


def load_uploaded_file(uploaded):
    filename = uploaded.name
    lower_name = filename.lower()
    used_csv_as_is = False
    raw_rows = []
    csv_bytes = None

    if lower_name.endswith(".csv"):
        try:
            uploaded.seek(0)
            dataframe = pd.read_csv(uploaded)
            raw_rows = dataframe.to_dict(orient="records")
            csv_bytes = uploaded.getvalue()
            used_csv_as_is = True
        except Exception:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = tmp.name
            try:
                raw_rows = detect_and_load(tmp_path)
            finally:
                os.unlink(tmp_path)
    elif lower_name.endswith((".xlsx", ".xls")):
        dataframe = pd.read_excel(uploaded)
        raw_rows = dataframe.to_dict(orient="records")
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        try:
            raw_rows = detect_and_load(tmp_path)
        finally:
            os.unlink(tmp_path)

    return used_csv_as_is, raw_rows, csv_bytes


def detect_centers(records: list[dict]) -> list[str]:
    seen = []
    for record in records:
        center_name = str(record.get("merkez") or "").strip()
        if center_name and center_name not in seen:
            seen.append(center_name)
    return seen


def count_stops_by_center(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        center_name = str(record.get("merkez") or "").strip() or "Merkezsiz"
        counts[center_name] = counts.get(center_name, 0) + 1
    return counts


def to_stops(records: list[dict]) -> list[Stop]:
    stops = []
    for record in records:
        payload = dict(record)
        payload["lat"] = float(payload["lat"])
        payload["lng"] = float(payload["lng"])
        stops.append(Stop(**payload))
    return stops


def render_artifacts(job_summary) -> None:
    artifacts = job_summary.artifact_paths
    job_id = job_summary.job_id
    route_map_path = Path(artifacts.route_map_html or "")
    if route_map_path.exists():
        html_data = route_map_path.read_bytes()
        st.download_button("Ana Harita İndir", data=html_data, file_name=route_map_path.name, mime="text/html")

    if artifacts.vehicle_maps:
        st.write("**Araç Haritaları**")
        for vehicle_name, vehicle_path in artifacts.vehicle_maps.items():
            path = Path(vehicle_path)
            if not path.exists():
                continue
            toggle_key = f"show_vehicle_map_{job_id}_{vehicle_name}"
            if st.button(f"{vehicle_name} Haritasını Göster", key=f"toggle_{toggle_key}"):
                st.session_state[toggle_key] = not st.session_state.get(toggle_key, False)

            if st.session_state.get(toggle_key):
                st.caption(f"{vehicle_name} rotası")
                st.components.v1.html(path.read_text(encoding="utf-8"), height=500, scrolling=True)

    main_map_toggle_key = f"show_main_map_{job_id}"
    if route_map_path.exists() and st.button("Haritayı Göster", key=f"toggle_{main_map_toggle_key}"):
        st.session_state[main_map_toggle_key] = not st.session_state.get(main_map_toggle_key, False)

    if route_map_path.exists() and st.session_state.get(main_map_toggle_key):
        html_content = route_map_path.read_text(encoding="utf-8")
        st.components.v1.html(html_content, height=650, scrolling=True)

        if artifacts.vehicle_maps:
            st.write("**Araç Rotaları**")
            for vehicle_name, vehicle_path in artifacts.vehicle_maps.items():
                path = Path(vehicle_path)
                if not path.exists():
                    continue
                with st.expander(f"{vehicle_name} rotasını göster", expanded=False):
                    st.components.v1.html(path.read_text(encoding="utf-8"), height=500, scrolling=True)

    route_plan_path = Path(artifacts.route_plan_json or "")
    if route_plan_path.exists():
        route_plan = json.loads(route_plan_path.read_text(encoding="utf-8"))
        routes = route_plan.get("routes") or []
        if routes:
            st.write("**Rota Sıraları**")
            for route in routes:
                with st.expander(f"{route.get('vehicle_id')} / {route.get('center_name')}"):
                    if route.get("google_maps_url"):
                        st.markdown(f"[Google Maps rota linki]({route['google_maps_url']})")
                    ordered_stops = route.get("ordered_stops") or []
                    if ordered_stops:
                        stop_rows = [
                            {
                                "Sıra": stop.get("sequence"),
                                "Durak ID": stop.get("id"),
                                "Adres": stop.get("formatted_address"),
                                "Mahalle": stop.get("mahalle"),
                                "Google Maps": stop.get("google_maps_url"),
                            }
                            for stop in ordered_stops
                        ]
                        st.dataframe(pd.DataFrame(stop_rows), use_container_width=True)


st.caption(f"Backend: {SETTINGS.backend_base_url}")

with st.sidebar:
    st.subheader("Google Rota")
    google_api_key = st.text_input(
        "Google Maps API Key",
        type="password",
        value=st.session_state.get("google_api_key", ""),
        help="Google provider seçildiğinde sunucuya bu anahtar ile istek atılır. Boş bırakırsan sunucu tarafı env anahtarı kullanılır.",
    )
    st.session_state.google_api_key = google_api_key
    st.subheader("Gemini Copilot")
    gemini_api_key = st.text_input(
        "Gemini API Key",
        type="password",
        value=st.session_state.get("gemini_api_key", ""),
        help="Operasyon notu ve uyarı özetleri bu anahtar ile Gemini üzerinden çalışır.",
    )
    st.session_state.gemini_api_key = gemini_api_key
    st.caption(f"Model: {SETTINGS.gemini_model}")

uploaded = st.file_uploader("Dosya seçin (.csv, .json, .geojson, .ndjson, .xlsx, .xls, .txt)", type=["csv", "json", "geojson", "ndjson", "xlsx", "xls", "txt"])

if uploaded is not None:
    used_csv_as_is, raw_rows, csv_bytes = load_uploaded_file(uploaded)
    st.info(f"Bu iş, yüklediğiniz dosyadan üretilecek: {uploaded.name}")
    st.success(f"Ham kayıt sayısı: {len(raw_rows)}")

    if not used_csv_as_is:
        normalized = []
        next_id = 1
        for raw in raw_rows:
            record = normalize_record(raw, next_id)
            normalized.append(record)
            try:
                next_id = max(next_id, int(record.get("id", next_id)) + 1)
            except Exception:
                next_id += 1
        csv_bytes = build_csv_bytes_from_records(normalized)
    else:
        normalized = raw_rows

    centers = detect_centers(normalized)
    center_stop_counts = count_stops_by_center(normalized)
    st.subheader("Önizleme")
    st.dataframe(pd.DataFrame(normalized[:200]))
    st.caption("Rota hesabında bu önizlemedeki adresler kullanılacak. Inbox klasöründeki başka dosyalar bu işte kullanılmaz.")
    st.download_button("Normalize CSV indir", data=csv_bytes, file_name="normalized_addresses.csv", mime="text/csv")

    st.markdown("---")
    st.subheader("Rota İşi Oluştur")

    provider = st.selectbox("Provider", options=["local", "auto", "google"], index=0)
    preserve_centers = st.checkbox("Mevcut merkez atamalarını koru", value=True)

    recommendation_rows = [
        {
            "Merkez": center_name,
            "Durak Sayısı": stop_count,
            "150 Kapasite ile Önerilen Min Araç": max(1, math.ceil(stop_count / 150)),
        }
        for center_name, stop_count in center_stop_counts.items()
    ]
    if recommendation_rows:
        st.write("**Yük Dağılımı ve İlk Öneri**")
        st.dataframe(pd.DataFrame(recommendation_rows), use_container_width=True)

    vehicle_config: dict[str, VehicleConfig] = {}
    live_summary_rows: list[dict[str, object]] = []
    for center_name in centers:
        cols = st.columns([2, 1, 1])
        stop_count = center_stop_counts.get(center_name, 0)
        default_vehicle_count = max(1, math.ceil(stop_count / 150))
        with cols[0]:
            st.write(f"**{center_name}**")
        with cols[1]:
            vehicle_count = st.number_input(
                f"{center_name} araç sayısı",
                min_value=1,
                value=default_vehicle_count,
                key=f"count_{center_name}",
            )
        with cols[2]:
            capacity = st.number_input(f"{center_name} kapasite", min_value=1, value=150, key=f"cap_{center_name}")
        total_capacity = int(vehicle_count) * int(capacity)
        min_vehicle_needed = max(1, math.ceil(stop_count / int(capacity)))
        min_capacity_needed = max(1, math.ceil(stop_count / int(vehicle_count)))
        status_label = "Yeterli" if total_capacity >= stop_count else "Yetersiz"
        st.caption(
            f"Durak: {stop_count} | Bu kapasite ile önerilen min araç: {min_vehicle_needed} | "
            f"Bu araç sayısı ile gereken min kapasite: {min_capacity_needed} | "
            f"Toplam kapasite: {total_capacity} ({status_label})"
        )
        vehicle_config[center_name] = VehicleConfig(arac_sayisi=int(vehicle_count), kapasite=int(capacity), kisi_sayisi=1)
        live_summary_rows.append(
            {
                "Merkez": center_name,
                "Durak Sayısı": stop_count,
                "Araç Sayısı": int(vehicle_count),
                "Araç Kapasitesi": int(capacity),
                "Toplam Kapasite": total_capacity,
                "Önerilen Min Araç": min_vehicle_needed,
                "Gereken Min Kapasite": min_capacity_needed,
                "Durum": status_label,
            }
        )

    if live_summary_rows:
        st.write("**Canlı Kapasite Özeti**")
        st.dataframe(pd.DataFrame(live_summary_rows), use_container_width=True)
        insufficient_centers = [row["Merkez"] for row in live_summary_rows if row["Durum"] == "Yetersiz"]
        if insufficient_centers:
            st.warning(
                "Bu merkezlerde toplam kapasite yetersiz: " + ", ".join(insufficient_centers)
            )

    copilot_input = st.text_area("Operasyon notu / teslimat kısıtı", placeholder="Örn: Esenler durakları merkezlerinde kalsın, araç başına en fazla 80 teslimat olsun.")
    if st.button("Copilot ile Kısıt Çıkar"):
        try:
            constraints = CLIENT.extract_constraints(
                ExtractConstraintsRequest(text=copilot_input, known_centers=centers),
                gemini_api_key=st.session_state.get("gemini_api_key"),
            )
            st.json(constraints.model_dump() if hasattr(constraints, "model_dump") else constraints.dict())
        except Exception as exc:
            st.error(f"Copilot çağrısı başarısız oldu: {exc}")

    if st.button("Rota İşini Başlat"):
        try:
            job_summary = CLIENT.create_job(
                JobRequest(
                    stops=to_stops(normalized),
                    vehicle_config=vehicle_config,
                    provider=provider,
                    preserve_centers=preserve_centers,
                ),
                google_api_key=st.session_state.get("google_api_key"),
            )
            st.session_state.current_job_id = job_summary.job_id
            st.session_state.job_submitted_at = time.time()
        except Exception as exc:
            st.error(f"Job oluşturulamadı: {exc}")

if st.session_state.get("current_job_id"):
    st.markdown("---")
    st.subheader("Job Durumu")
    try:
        job_summary = CLIENT.get_job(st.session_state.current_job_id)
        st.json(job_summary.model_dump() if hasattr(job_summary, "model_dump") else job_summary.dict())

        if job_summary.status in {"pending", "running"}:
            st.info("Job arka planda çalışıyor. Durum otomatik yenilenecek.")
            time.sleep(2)
            st.rerun()

        if job_summary.status == "completed":
            render_artifacts(job_summary)
            if st.button("Uyarıları Copilot ile Özetle"):
                summary = CLIENT.summarize_failures(
                    SummarizeFailuresRequest(
                        warnings=job_summary.warnings,
                        metrics={
                            "total_distance_km": job_summary.total_distance_km,
                            "vehicle_count": job_summary.vehicle_count,
                            "stop_count": job_summary.stop_count,
                        },
                    ),
                    gemini_api_key=st.session_state.get("gemini_api_key"),
                )
                st.json(summary.model_dump() if hasattr(summary, "model_dump") else summary.dict())
    except Exception as exc:
        st.error(f"Job durumu alınamadı: {exc}")

st.markdown("---")
st.header("Yerelden gelen klasörü")
files = sorted(INBOX_DIR.iterdir(), key=lambda path: path.name) if INBOX_DIR.exists() else []
if not files:
    st.info("Inbox boş.")
else:
    for file_path in files:
        st.write(file_path.name)
