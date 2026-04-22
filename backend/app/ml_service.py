from dataclasses import dataclass
from statistics import mean

from app.forecast_service import ForecastService, WeatherSnapshot
from app.ml_repository import MlRepository
from app.settings import Settings


@dataclass
class RetrainResult:
    status: str
    reason: str | None = None
    model: dict | None = None


@dataclass
class PublishResult:
    status: str
    reason: str | None = None
    model: dict | None = None


class MlService:
    def __init__(self, settings: Settings, ml_repository: MlRepository, forecast_service: ForecastService) -> None:
        self._settings = settings
        self._ml_repository = ml_repository
        self._forecast_service = forecast_service

    def retrain(self) -> RetrainResult:
        records = self._ml_repository.list_catch_records()
        if len(records) < self._settings.ml_retrain_min_records:
            return RetrainResult(
                status="skipped",
                reason=f"not enough records: {len(records)} < {self._settings.ml_retrain_min_records}",
            )

        by_species: dict[str, list] = {"pike": [], "perch": []}
        for row in records:
            if row.species in by_species:
                by_species[row.species].append(row)

        species_bias: dict[str, float] = {}
        metrics: dict[str, dict] = {}

        for species, rows in by_species.items():
            if not rows:
                species_bias[species] = 0.0
                metrics[species] = {"rows": 0, "mae": None, "rmse": None, "spearman": None}
                continue

            base_predictions: list[float] = []
            actual_scores: list[float] = []
            for row in rows:
                snapshot = WeatherSnapshot(
                    day=row.linked_weather_date,
                    air_temp_c=row.linked_air_temp_c,
                    pressure_hpa=row.linked_pressure_hpa,
                    water_temp_c=row.linked_water_temp_c,
                    wind_speed_m_s=row.linked_wind_speed_m_s,
                    wind_direction_deg=row.linked_wind_direction_deg,
                    moon_phase=row.linked_moon_phase,
                )
                base_score, _ = self._forecast_service.score_species(species, snapshot, bias=0.0)
                base_predictions.append(base_score)
                actual_scores.append(row.score)

            residuals = [actual - pred for actual, pred in zip(actual_scores, base_predictions)]
            bias = mean(residuals) if residuals else 0.0
            species_bias[species] = round(bias, 4)

            adjusted_preds = [max(0.0, min(5.0, pred + bias)) for pred in base_predictions]
            errors = [abs(a - p) for a, p in zip(actual_scores, adjusted_preds)]
            sq_errors = [(a - p) ** 2 for a, p in zip(actual_scores, adjusted_preds)]

            mae = mean(errors) if errors else 0.0
            rmse = (mean(sq_errors) ** 0.5) if sq_errors else 0.0
            spearman = self._spearman(actual_scores, adjusted_preds)
            metrics[species] = {
                "rows": len(rows),
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "spearman": round(spearman, 4),
                "top_day_hit_rate": round(self._top_day_hit_rate(rows, adjusted_preds), 4),
            }

        model = self._ml_repository.save_model_version(
            train_rows=len(records),
            species_bias=species_bias,
            metrics=metrics,
            smoke_passed=False,
            smoke_report={},
        )
        smoke_report = self._evaluate_smoke_report(metrics)
        smoke_passed = bool(smoke_report["passed"])
        model = self._ml_repository.get_model_by_id(model["id"]) or model
        if model and model.get("id"):
            # Re-save smoke flags through repository update path by activating candidate state via direct row access.
            self._ml_repository.update_smoke_result(
                model_id=model["id"],
                smoke_passed=smoke_passed,
                smoke_report=smoke_report,
            )
            model = self._ml_repository.get_model_by_id(model["id"])
        return RetrainResult(status="ok", model=model)

    def latest_model(self) -> dict | None:
        return self._ml_repository.get_latest_model()

    def active_model(self) -> dict | None:
        return self._ml_repository.get_active_model()

    def publish_model(self, model_id: str | None = None) -> PublishResult:
        candidate = self._ml_repository.get_model_by_id(model_id) if model_id else self._ml_repository.get_latest_model()
        if candidate is None:
            return PublishResult(status="skipped", reason="no model found")
        if not candidate.get("smoke_passed"):
            return PublishResult(status="rejected", reason="smoke checks failed", model=candidate)

        activated = self._ml_repository.activate_model(candidate["id"])
        if activated is None:
            return PublishResult(status="skipped", reason="model not found")
        return PublishResult(status="ok", model=activated)

    def _spearman(self, xs: list[float], ys: list[float]) -> float:
        if len(xs) < 2 or len(xs) != len(ys):
            return 0.0
        rx = self._ranks(xs)
        ry = self._ranks(ys)
        mx = mean(rx)
        my = mean(ry)
        cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
        sx = (sum((a - mx) ** 2 for a in rx)) ** 0.5
        sy = (sum((b - my) ** 2 for b in ry)) ** 0.5
        if sx == 0 or sy == 0:
            return 0.0
        return cov / (sx * sy)

    def _ranks(self, values: list[float]) -> list[float]:
        indexed = sorted(enumerate(values), key=lambda item: item[1])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(indexed):
            j = i
            while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
                j += 1
            avg_rank = (i + j + 2) / 2.0
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    def _top_day_hit_rate(self, rows: list, adjusted_preds: list[float]) -> float:
        if not rows or len(rows) != len(adjusted_preds):
            return 0.0

        daily_actual: dict = {}
        daily_pred: dict = {}
        for row, pred in zip(rows, adjusted_preds):
            day = row.linked_weather_date
            daily_actual.setdefault(day, []).append(float(row.score))
            daily_pred.setdefault(day, []).append(float(pred))

        if not daily_actual:
            return 0.0

        best_actual_day = max(daily_actual.keys(), key=lambda d: mean(daily_actual[d]))
        best_pred_day = max(daily_pred.keys(), key=lambda d: mean(daily_pred[d]))
        return 1.0 if best_actual_day == best_pred_day else 0.0

    def _evaluate_smoke_report(self, metrics: dict[str, dict]) -> dict:
        species_checks: dict[str, dict] = {}
        for species, item in metrics.items():
            rows = int(item.get("rows") or 0)
            mae = float(item.get("mae") or 0.0)
            rmse = float(item.get("rmse") or 0.0)
            top_day_hit_rate = float(item.get("top_day_hit_rate") or 0.0)
            if rows == 0:
                species_checks[species] = {
                    "rows": rows,
                    "passed": True,
                    "reason": "no_data",
                }
                continue

            passed = (
                mae <= self._settings.ml_smoke_max_mae
                and rmse <= self._settings.ml_smoke_max_rmse
                and top_day_hit_rate >= self._settings.ml_smoke_min_top_day_hit_rate
            )
            species_checks[species] = {
                "rows": rows,
                "passed": passed,
                "mae": mae,
                "rmse": rmse,
                "top_day_hit_rate": top_day_hit_rate,
                "thresholds": {
                    "max_mae": self._settings.ml_smoke_max_mae,
                    "max_rmse": self._settings.ml_smoke_max_rmse,
                    "min_top_day_hit_rate": self._settings.ml_smoke_min_top_day_hit_rate,
                },
            }

        overall_passed = all(v["passed"] for v in species_checks.values()) if species_checks else False
        return {
            "passed": overall_passed,
            "species": species_checks,
        }
