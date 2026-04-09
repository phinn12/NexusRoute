from pathlib import Path

from kargo_backend.config import load_settings
from kargo_backend.schemas import JobRequest, Stop, VehicleConfig
from kargo_backend.storage import FileJobStore


def test_job_store_marks_interrupted_running_jobs_failed(tmp_path):
    settings = load_settings(tmp_path)
    first_store = FileJobStore(settings)
    summary = first_store.create_job(
        JobRequest(
            stops=[Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.0, lng=28.8)],
            vehicle_config={"Merter Merkez": VehicleConfig(arac_sayisi=1, kapasite=10, kisi_sayisi=1)},
            provider="local",
            preserve_centers=True,
        )
    )
    first_store.mark_running(summary.job_id)

    recovered_store = FileJobStore(settings)
    recovered = recovered_store.get_summary(summary.job_id)

    assert recovered.status == "failed"
    assert "servis yeniden başladı" in (recovered.error or "")


def test_job_store_does_not_persist_runtime_google_api_key(tmp_path):
    settings = load_settings(tmp_path)
    store = FileJobStore(settings)
    summary = store.create_job(
        JobRequest(
            stops=[Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.0, lng=28.8)],
            vehicle_config={"Merter Merkez": VehicleConfig(arac_sayisi=1, kapasite=10, kisi_sayisi=1)},
            provider="google",
            preserve_centers=True,
            google_api_key="secret-google-key",
        )
    )

    request_payload = Path(summary.artifact_paths.request_json).read_text(encoding="utf-8")

    assert "secret-google-key" not in request_payload
    assert "google_api_key" not in request_payload
