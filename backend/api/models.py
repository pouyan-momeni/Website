"""Models API routes."""

import copy
import uuid as uuid_mod
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, require_role, require_develop_mode
from backend.config import settings
from backend.database import get_db
from backend.models.model import Model
from backend.models.user import User
from backend.schemas.schemas import (
    ModelCreate, ModelResponse, ConfigUpdate, InputSchemaUpdate, ContainersUpdate,
)

router = APIRouter(prefix="/api/models", tags=["models"])

# ─── Dev-mode mock models (mutable in-memory store) ───
_DEV_MODELS: dict[str, dict] = {
    "11111111-1111-1111-1111-111111111111": {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Interest Rate Model",
        "slug": "interest-rate-model",
        "description": "Models interest rate scenarios, yield curve shifts, and duration risk across the portfolio.",
        "docker_images": [
            {"name": "data-updater", "image": "alm/ir-data-updater:latest", "order": 1, "extra_args": "-e DATA_SOURCE=bloomberg"},
            {"name": "analyze", "image": "alm/ir-analyze:latest", "order": 2, "extra_args": "-e SCENARIOS=1000"},
            {"name": "backtest", "image": "alm/ir-backtest:latest", "order": 3, "extra_args": "-e LOOKBACK_YEARS=5"},
        ],
        "default_config": {
            "rate_shock_bps": {"value": 200, "type": "int", "description": "Parallel rate shock in basis points"},
            "curve_model": {"value": "nelson-siegel", "type": "string", "description": "Yield curve model"},
            "num_scenarios": {"value": 1000, "type": "int", "description": "Number of Monte Carlo scenarios"},
            "confidence_level": {"value": 0.99, "type": "float", "description": "VaR confidence level"},
        },
        "input_schema": [
            {"name": "valuation_date", "type": "date", "required": True},
            {"name": "portfolio_file", "type": "file", "required": True, "source": "upload"},
            {"name": "curve_data_path", "type": "text", "required": False},
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
    "22222222-2222-2222-2222-222222222222": {
        "id": "22222222-2222-2222-2222-222222222222",
        "name": "Credit Risk Model",
        "slug": "credit-risk-model",
        "description": "Evaluates credit exposure, probability of default, and loss-given-default across counterparties.",
        "docker_images": [
            {"name": "data-updater", "image": "alm/cr-data-updater:latest", "order": 1, "extra_args": "-e DATA_SOURCE=internal_db"},
            {"name": "analyze", "image": "alm/cr-analyze:latest", "order": 2, "extra_args": "-e PD_MODEL=merton"},
            {"name": "backtest", "image": "alm/cr-backtest:latest", "order": 3, "extra_args": "-e STRESS_SCENARIOS=3"},
        ],
        "default_config": {
            "lgd_assumption": {"value": 0.45, "type": "float", "description": "Loss given default assumption"},
            "pd_horizon_years": {"value": 1, "type": "int", "description": "PD estimation horizon in years"},
            "correlation_model": {"value": "gaussian-copula", "type": "string", "description": "Default correlation model"},
            "num_simulations": {"value": 5000, "type": "int", "description": "Number of Monte Carlo simulations"},
        },
        "input_schema": [
            {"name": "reporting_date", "type": "date", "required": True},
            {"name": "exposures_file", "type": "file", "required": True, "source": "upload"},
            {"name": "ratings_file", "type": "file", "required": False, "source": "upload"},
            {"name": "macro_scenario", "type": "text", "required": False},
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
    "33333333-3333-3333-3333-333333333333": {
        "id": "33333333-3333-3333-3333-333333333333",
        "name": "Liquidity Model",
        "slug": "liquidity-model",
        "description": "Assesses liquidity coverage ratio, net stable funding ratio, and cash flow projections under stress.",
        "docker_images": [
            {"name": "data-updater", "image": "alm/liq-data-updater:latest", "order": 1, "extra_args": "-e DATA_SOURCE=treasury_system"},
            {"name": "analyze", "image": "alm/liq-analyze:latest", "order": 2, "extra_args": "-e PROJECTION_DAYS=90"},
            {"name": "backtest", "image": "alm/liq-backtest:latest", "order": 3, "extra_args": "-e STRESS_TYPE=idiosyncratic"},
        ],
        "default_config": {
            "lcr_threshold": {"value": 1.0, "type": "float", "description": "Minimum LCR threshold"},
            "nsfr_threshold": {"value": 1.0, "type": "float", "description": "Minimum NSFR threshold"},
            "projection_days": {"value": 90, "type": "int", "description": "Cash flow projection horizon in days"},
            "stress_severity": {"value": "moderate", "type": "string", "description": "Stress scenario severity level"},
        },
        "input_schema": [
            {"name": "as_of_date", "type": "date", "required": True},
            {"name": "cash_flows_file", "type": "file", "required": True, "source": "upload"},
            {"name": "hqla_file", "type": "file", "required": False, "source": "upload"},
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    },
}


@router.get("", response_model=list[ModelResponse])
async def list_models(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all models. Available to all authenticated users."""
    if settings.is_develop:
        return list(_DEV_MODELS.values())
    result = await db.execute(select(Model).order_by(Model.name))
    return result.scalars().all()


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single model by ID. Available to all authenticated users."""
    if settings.is_develop:
        model_data = _DEV_MODELS.get(str(model_id))
        if model_data:
            return model_data
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model


@router.post("", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    body: ModelCreate,
    current_user: User = Depends(require_role(["admin"])),
    _: None = Depends(require_develop_mode()),
    db: AsyncSession = Depends(get_db),
):
    """Create a new model. Admin only, develop mode only."""
    # Dev mode: write to in-memory store
    if settings.is_develop:
        for m in _DEV_MODELS.values():
            if m["slug"] == body.slug:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Model with slug '{body.slug}' already exists",
                )
        model_id = str(uuid_mod.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        model_data = {
            "id": model_id,
            "name": body.name,
            "slug": body.slug,
            "description": body.description,
            "docker_images": [img.model_dump() for img in body.docker_images],
            "default_config": {k: v.model_dump() for k, v in body.default_config.items()},
            "input_schema": [inp.model_dump() for inp in body.input_schema],
            "created_at": now,
            "updated_at": now,
        }
        _DEV_MODELS[model_id] = model_data
        return model_data

    # Production: write to DB
    existing = await db.execute(select(Model).where(Model.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model with slug '{body.slug}' already exists",
        )

    model = Model(
        name=body.name,
        slug=body.slug,
        description=body.description,
        docker_images=[img.model_dump() for img in body.docker_images],
        default_config={k: v.model_dump() for k, v in body.default_config.items()},
        input_schema=[inp.model_dump() for inp in body.input_schema],
    )
    db.add(model)
    await db.flush()
    return model


@router.get("/{model_id}/export")
async def export_model(
    model_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export a model's full settings as JSON. Available to all authenticated users."""
    if settings.is_develop:
        model_data = _DEV_MODELS.get(str(model_id))
        if not model_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        export = {
            "name": model_data["name"],
            "slug": model_data["slug"],
            "description": model_data.get("description"),
            "input_schema": model_data.get("input_schema", []),
            "default_config": model_data.get("default_config", {}),
            "docker_images": model_data.get("docker_images", []),
        }
        from backend.api.audit import log_action
        await log_action(
            username=getattr(current_user, 'ldap_username', 'admin'),
            user_id=str(getattr(current_user, 'id', '')),
            action="export_model", resource_type="model", resource_id=str(model_id),
            details={"model_name": model_data["name"]},
            db=None,
        )
        return export

    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    from backend.api.audit import log_action
    await log_action(
        username=current_user.ldap_username,
        user_id=str(current_user.id),
        action="export_model", resource_type="model", resource_id=str(model_id),
        details={"model_name": model.name},
        db=db,
    )

    return {
        "name": model.name,
        "slug": model.slug,
        "description": model.description,
        "input_schema": model.input_schema,
        "default_config": model.default_config,
        "docker_images": model.docker_images,
    }


@router.post("/import", response_model=ModelResponse)
async def import_model(
    body: ModelCreate,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Import a model from JSON. Creates or updates by slug. Admin only."""
    # Dev mode: create or update in-memory
    if settings.is_develop:
        existing_id = None
        for mid, m in _DEV_MODELS.items():
            if m["slug"] == body.slug:
                existing_id = mid
                break

        now = datetime.now(timezone.utc).isoformat()
        if existing_id:
            _DEV_MODELS[existing_id].update({
                "name": body.name,
                "slug": body.slug,
                "description": body.description,
                "docker_images": [img.model_dump() for img in body.docker_images],
                "default_config": {k: v.model_dump() for k, v in body.default_config.items()},
                "input_schema": [inp.model_dump() for inp in body.input_schema],
                "updated_at": now,
            })
            return _DEV_MODELS[existing_id]
        else:
            model_id = str(uuid_mod.uuid4())
            model_data = {
                "id": model_id,
                "name": body.name,
                "slug": body.slug,
                "description": body.description,
                "docker_images": [img.model_dump() for img in body.docker_images],
                "default_config": {k: v.model_dump() for k, v in body.default_config.items()},
                "input_schema": [inp.model_dump() for inp in body.input_schema],
                "created_at": now,
                "updated_at": now,
            }
            _DEV_MODELS[model_id] = model_data
            return model_data

    # Production: upsert by slug
    result = await db.execute(select(Model).where(Model.slug == body.slug))
    existing_model = result.scalar_one_or_none()

    if existing_model:
        existing_model.name = body.name
        existing_model.description = body.description
        existing_model.docker_images = [img.model_dump() for img in body.docker_images]
        existing_model.default_config = {k: v.model_dump() for k, v in body.default_config.items()}
        existing_model.input_schema = [inp.model_dump() for inp in body.input_schema]
        await db.flush()

        from backend.api.audit import log_action
        await log_action(
            username=current_user.ldap_username,
            user_id=str(current_user.id),
            action="import_model", resource_type="model", resource_id=str(existing_model.id),
            details={"model_name": body.name, "action": "updated"},
            db=db,
        )

        return existing_model
    else:
        model = Model(
            name=body.name,
            slug=body.slug,
            description=body.description,
            docker_images=[img.model_dump() for img in body.docker_images],
            default_config={k: v.model_dump() for k, v in body.default_config.items()},
            input_schema=[inp.model_dump() for inp in body.input_schema],
        )
        db.add(model)
        await db.flush()

        from backend.api.audit import log_action
        await log_action(
            username=current_user.ldap_username,
            user_id=str(current_user.id),
            action="import_model", resource_type="model", resource_id=str(model.id),
            details={"model_name": body.name, "action": "created"},
            db=db,
        )

        return model


@router.put("/{model_id}/config", response_model=ModelResponse)
async def update_config(
    model_id: UUID,
    body: ConfigUpdate,
    current_user: User = Depends(require_role(["admin"])),
    _: None = Depends(require_develop_mode()),
    db: AsyncSession = Depends(get_db),
):
    """Update model default config. Admin only, develop mode only."""
    if settings.is_develop:
        model_data = _DEV_MODELS.get(str(model_id))
        if not model_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        model_data["default_config"] = body.default_config
        model_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return model_data

    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    model.default_config = body.default_config
    await db.flush()
    return model


@router.put("/{model_id}/input-schema", response_model=ModelResponse)
async def update_input_schema(
    model_id: UUID,
    body: InputSchemaUpdate,
    current_user: User = Depends(require_role(["admin"])),
    _: None = Depends(require_develop_mode()),
    db: AsyncSession = Depends(get_db),
):
    """Update model input schema. Admin only, develop mode only."""
    if settings.is_develop:
        model_data = _DEV_MODELS.get(str(model_id))
        if not model_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        model_data["input_schema"] = body.input_schema
        model_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return model_data

    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    model.input_schema = body.input_schema
    await db.flush()
    return model


@router.put("/{model_id}/containers", response_model=ModelResponse)
async def update_containers(
    model_id: UUID,
    body: ContainersUpdate,
    current_user: User = Depends(require_role(["admin"])),
    _: None = Depends(require_develop_mode()),
    db: AsyncSession = Depends(get_db),
):
    """Update model container images and order. Admin only, develop mode only."""
    if settings.is_develop:
        model_data = _DEV_MODELS.get(str(model_id))
        if not model_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        model_data["docker_images"] = [img.model_dump() for img in body.docker_images]
        model_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return model_data

    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    model.docker_images = [img.model_dump() for img in body.docker_images]
    await db.flush()
    return model


@router.delete("/{model_id}")
async def delete_model(
    model_id: UUID,
    current_user: User = Depends(require_role(["admin"])),
    _: None = Depends(require_develop_mode()),
    db: AsyncSession = Depends(get_db),
):
    """Delete a model. Admin only, develop mode only."""
    if settings.is_develop:
        model_data = _DEV_MODELS.pop(str(model_id), None)
        if not model_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

        from backend.api.audit import log_action
        await log_action(
            username=getattr(current_user, 'ldap_username', 'admin'),
            user_id=str(getattr(current_user, 'id', '')),
            action="delete_model", resource_type="model", resource_id=str(model_id),
            details={"model_name": model_data["name"]},
            db=None,
        )
        return {"detail": f"Model '{model_data['name']}' deleted"}

    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    model_name = model.name
    await db.delete(model)
    await db.flush()

    from backend.api.audit import log_action
    await log_action(
        username=current_user.ldap_username,
        user_id=str(current_user.id),
        action="delete_model", resource_type="model", resource_id=str(model_id),
        details={"model_name": model_name},
        db=db,
    )

    return {"detail": f"Model '{model_name}' deleted"}
