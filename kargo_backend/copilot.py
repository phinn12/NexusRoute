from __future__ import annotations

import json
import time
from typing import Any, Dict

import httpx

from .config import Settings
from .schemas import (
    ExtractConstraintsResponse,
    FailureSummary,
    SummarizeFailuresResponse,
    DeliveryConstraints,
)


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _delivery_constraints_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "preferred_center": {"type": ["string", "null"]},
            "preserve_centers": {"type": ["boolean", "null"]},
            "max_stops_per_vehicle": {"type": ["integer", "null"]},
            "max_vehicle_capacity": {"type": ["integer", "null"]},
            "delivery_notes": {"type": "array", "items": {"type": "string"}},
            "risk_flags": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "preferred_center",
            "preserve_centers",
            "max_stops_per_vehicle",
            "max_vehicle_capacity",
            "delivery_notes",
            "risk_flags",
        ],
    }


def _failure_summary_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "priority_actions": {"type": "array", "items": {"type": "string"}},
            "warning_types": {"type": "array", "items": {"type": "string"}},
            "route_risks": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "priority_actions", "warning_types", "route_risks"],
    }


class OperationsCopilot:
    def __init__(self, settings: Settings):
        self.settings = settings

    def extract_constraints(
        self,
        text: str,
        known_centers: list[str],
        gemini_api_key: str | None = None,
    ) -> ExtractConstraintsResponse:
        if not text.strip():
            return ExtractConstraintsResponse(
                available=False,
                warnings=["Operasyon notu boş; Gemini çağrısı yapılmadı."],
            )

        api_key = self._resolve_api_key(gemini_api_key)
        if api_key is None:
            return ExtractConstraintsResponse(
                available=False,
                warnings=["Gemini API key tanımlı değil; copilot kullanılamıyor."],
            )

        try:
            result, model_used, warnings = self._generate_structured_output(
                api_key=api_key,
                system_prompt=(
                    "Kargo operasyon serbest metninden yapılandırılmış teslimat kısıtları çıkar. "
                    "Sadece metinde açıkça geçen sinyalleri kullan. Emin olmadığın alanları null bırak. "
                    "Bilinen merkez adları dışında merkez uydurma."
                ),
                user_payload={"text": text, "known_centers": known_centers},
                response_schema=_delivery_constraints_schema(),
            )
            return ExtractConstraintsResponse(
                available=True,
                model=model_used,
                warnings=warnings,
                constraints=DeliveryConstraints(**result),
            )
        except Exception as exc:
            return ExtractConstraintsResponse(
                available=False,
                warnings=[f"Gemini hata verdi: {exc}"],
            )

    def summarize_failures(
        self,
        warnings: list[str],
        failed_deliveries: list[str],
        metrics: Dict[str, Any],
        gemini_api_key: str | None = None,
    ) -> SummarizeFailuresResponse:
        api_key = self._resolve_api_key(gemini_api_key)
        if api_key is None:
            return SummarizeFailuresResponse(
                available=False,
                warnings=["Gemini API key tanımlı değil; copilot kullanılamıyor."],
            )

        try:
            result, model_used, warnings = self._generate_structured_output(
                api_key=api_key,
                system_prompt=(
                    "Rota uyarıları ve başarısız teslimatlardan kısa, net ve aksiyon odaklı bir operasyon özeti çıkar. "
                    "Abartı yapma. Önceliği operasyonel etkisi yüksek maddelere ver."
                ),
                user_payload={
                    "warnings": warnings,
                    "failed_deliveries": failed_deliveries,
                    "metrics": metrics,
                },
                response_schema=_failure_summary_schema(),
            )
            return SummarizeFailuresResponse(
                available=True,
                model=model_used,
                warnings=warnings,
                summary=FailureSummary(**result),
            )
        except Exception as exc:
            return SummarizeFailuresResponse(
                available=False,
                warnings=[f"Gemini hata verdi: {exc}"],
            )

    def _resolve_api_key(self, runtime_key: str | None) -> str | None:
        if runtime_key and runtime_key.strip():
            return runtime_key.strip()
        if self.settings.gemini_api_key and self.settings.gemini_api_key.strip():
            return self.settings.gemini_api_key.strip()
        return None

    def _generate_structured_output(
        self,
        api_key: str,
        system_prompt: str,
        user_payload: Dict[str, Any],
        response_schema: Dict[str, Any],
    ) -> tuple[Dict[str, Any], str, list[str]]:
        models_to_try = [self.settings.gemini_model]
        models_to_try.extend(
            model for model in self.settings.gemini_fallback_models if model != self.settings.gemini_model
        )

        attempt_plan = [models_to_try[0], models_to_try[0]]
        if len(models_to_try) > 1:
            attempt_plan.append(models_to_try[1])
        else:
            attempt_plan.append(models_to_try[0])

        warnings: list[str] = []
        last_error: Exception | None = None

        for attempt_index, model_name in enumerate(attempt_plan):
            if attempt_index > 0:
                time.sleep(float(2 ** (attempt_index - 1)))

            try:
                response = httpx.post(
                    GEMINI_API_URL.format(model=model_name),
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json={
                        "systemInstruction": {
                            "parts": [{"text": system_prompt}],
                        },
                        "contents": [
                            {
                                "role": "user",
                                "parts": [{"text": json.dumps(user_payload, ensure_ascii=False)}],
                            }
                        ],
                        "generationConfig": {
                            "temperature": 0.1,
                            "responseMimeType": "application/json",
                            "responseJsonSchema": response_schema,
                        },
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                payload = response.json()
                text = self._extract_text(payload)
                if model_name != self.settings.gemini_model:
                    warnings.append(
                        f"{self.settings.gemini_model} geçici olarak kullanılamadı; {model_name} ile devam edildi."
                    )
                return json.loads(text), model_name, warnings
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                if status_code not in {429, 500, 503} or attempt_index == len(attempt_plan) - 1:
                    break
                continue
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt_index == len(attempt_plan) - 1:
                    break
                continue

        assert last_error is not None
        raise RuntimeError(
            f"Gemini yanıt vermedi. 2 retry ve fallback denendi. Son hata: {last_error}"
        ) from last_error

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        for candidate in candidates:
            parts = (((candidate.get("content") or {}).get("parts")) or [])
            for part in parts:
                text = part.get("text")
                if text:
                    return text
        raise RuntimeError(f"Gemini boş veya parse edilemeyen yanıt döndü: {payload}")
