#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from kargo_backend.schemas import JobRequest, Stop, VehicleConfig
from kargo_backend.service import RoutingOrchestrator


def load_grouped_json(path: Path) -> list[Stop]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    stops: list[Stop] = []
    for center_name, items in raw.items():
        for item in items:
            payload = dict(item)
            payload["merkez"] = payload.get("merkez") or center_name
            payload["lat"] = float(payload["lat"])
            payload["lng"] = float(payload["lng"])
            stops.append(Stop(**payload))
    return stops


def load_vehicle_config(config_path: str | None, stops: list[Stop]) -> dict[str, VehicleConfig]:
    if config_path:
        raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
        return {center: VehicleConfig(**config) for center, config in raw.items()}

    grouped: dict[str, int] = {}
    for stop in stops:
        center_name = (stop.merkez or "Bilinmeyen").strip()
        grouped[center_name] = grouped.get(center_name, 0) + 1
    return {
        center: VehicleConfig(arac_sayisi=1, kapasite=max(1, count), kisi_sayisi=1)
        for center, count in grouped.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", default="dagitim_merkezi_isleme.json")
    parser.add_argument("--config", default=None)
    parser.add_argument("--output-html", default=None)
    parser.add_argument("--provider", choices=["local", "google", "auto"], default="local")
    args = parser.parse_args()

    input_json = Path(args.input_json)
    if not input_json.exists():
        raise SystemExit(f"Girdi JSON bulunamadı: {input_json}")

    stops = load_grouped_json(input_json)
    vehicle_config = load_vehicle_config(args.config, stops)
    orchestrator = RoutingOrchestrator()

    output_html = Path(args.output_html) if args.output_html else None
    job_dir = output_html.parent if output_html else orchestrator.settings.output_dir / f"vehicle_job_{os.getpid()}"
    summary, _ = orchestrator.run_job_sync(
        JobRequest(
            stops=stops,
            vehicle_config=vehicle_config,
            provider=args.provider,
            preserve_centers=True,
        ),
        job_dir=job_dir,
        output_html=output_html,
    )
    print(json.dumps(summary.model_dump() if hasattr(summary, "model_dump") else summary.dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
