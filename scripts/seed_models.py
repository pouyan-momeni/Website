#!/usr/bin/env python3
"""Seed script: inserts one complete example model with docker images, config, and input schema."""

import sys
import os
import uuid
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.database import Base
from backend.models.user import User
from backend.models.model import Model
from backend.models.run import Run
from backend.models.run_container import RunContainer
from backend.models.schedule import Schedule
from backend.models.notification import Notification
from backend.models.resource_alert import ResourceAlert


def seed():
    """Seed the database with an example model and admin user."""
    engine = create_engine(settings.DATABASE_URL_SYNC)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Check if already fully seeded
        existing_model = session.execute(
            text("SELECT id FROM models WHERE slug = 'interest-rate-model'")
        ).fetchone()

        if existing_model:
            print("Database already seeded (interest-rate-model exists). Skipping.")
            return

        # Create users if they don't exist
        for u in [
            User(id=uuid.UUID("00000000-0000-0000-0000-000000000001"), ldap_username="admin", email="admin@example.com", role="admin", is_active=True),
            User(id=uuid.UUID("00000000-0000-0000-0000-000000000002"), ldap_username="developer", email="developer@example.com", role="developer", is_active=True),
            User(id=uuid.UUID("00000000-0000-0000-0000-000000000003"), ldap_username="runner", email="runner@example.com", role="runner", is_active=True),
        ]:
            existing_user = session.execute(text(f"SELECT id FROM users WHERE ldap_username = '{u.ldap_username}'")).fetchone()
            if not existing_user:
                session.add(u)

        # Create example model: ALM Risk Model
        existing_alm = session.execute(text("SELECT id FROM models WHERE slug = 'alm-risk-model'")).fetchone()
        if not existing_alm:
            example_model = Model(
                id=uuid.uuid4(),
            name="ALM Risk Model",
            slug="alm-risk-model",
            description="Asset-Liability Management risk model that calculates VaR, "
                        "stress tests, and duration gap analysis across multiple scenarios.",
            docker_images=[
                {
                    "name": "data-loader",
                    "image": "almplatform/data-loader:latest",
                    "order": 1,
                    "env": {
                        "DB_CONNECTION": "postgresql://readonly:readonly@db:5432/market_data",
                    },
                },
                {
                    "name": "scenario-engine",
                    "image": "almplatform/scenario-engine:latest",
                    "order": 2,
                    "env": {
                        "NUM_SCENARIOS": "10000",
                        "RANDOM_SEED": "42",
                    },
                },
                {
                    "name": "risk-calculator",
                    "image": "almplatform/risk-calculator:latest",
                    "order": 3,
                    "env": {},
                },
                {
                    "name": "report-generator",
                    "image": "almplatform/report-generator:latest",
                    "order": 4,
                    "env": {
                        "REPORT_FORMAT": "csv",
                    },
                },
            ],
            default_config={
                "confidence_level": {
                    "value": 0.99,
                    "type": "float",
                    "description": "VaR confidence level (e.g., 0.99 for 99%)",
                },
                "time_horizon_days": {
                    "value": 10,
                    "type": "int",
                    "description": "Risk time horizon in trading days",
                },
                "num_scenarios": {
                    "value": 10000,
                    "type": "int",
                    "description": "Number of Monte Carlo scenarios to generate",
                },
                "include_stress_test": {
                    "value": True,
                    "type": "bool",
                    "description": "Include historical stress test scenarios",
                },
                "base_currency": {
                    "value": "USD",
                    "type": "string",
                    "description": "Base reporting currency",
                },
            },
            input_schema=[
                {
                    "name": "start_date",
                    "type": "date",
                    "required": True,
                    "source": "upload",
                },
                {
                    "name": "end_date",
                    "type": "date",
                    "required": True,
                    "source": "upload",
                },
                {
                    "name": "portfolio_file",
                    "type": "file",
                    "required": True,
                    "source": "server",
                },
                {
                    "name": "market_data_path",
                    "type": "text",
                    "required": False,
                    "source": "server",
                },
            ],
            )
            session.add(example_model)

        # Interest Rate Model
        ir_model = Model(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            name="Interest Rate Model",
            slug="interest-rate-model",
            description="Models interest rate scenarios, yield curve shifts, and duration risk across the portfolio.",
            docker_images=[
                {"name": "data-updater", "image": "alm/ir-data-updater:latest", "order": 1, "env": {"DATA_SOURCE": "bloomberg"}},
                {"name": "analyze", "image": "alm/ir-analyze:latest", "order": 2, "env": {"SCENARIOS": "1000"}},
                {"name": "backtest", "image": "alm/ir-backtest:latest", "order": 3, "env": {"LOOKBACK_YEARS": "5"}},
            ],
            default_config={
                "rate_shock_bps": {"value": 200, "type": "int", "description": "Parallel rate shock in basis points"},
                "curve_model": {"value": "nelson-siegel", "type": "string", "description": "Yield curve model"},
                "num_scenarios": {"value": 1000, "type": "int", "description": "Number of Monte Carlo scenarios"},
                "confidence_level": {"value": 0.99, "type": "float", "description": "VaR confidence level"},
            },
            input_schema=[
                {"name": "valuation_date", "type": "date", "required": True},
                {"name": "portfolio_file", "type": "file", "required": True, "source": "upload"},
                {"name": "curve_data_path", "type": "text", "required": False},
            ],
        )
        session.add(ir_model)

        # Credit Risk Model
        cr_model = Model(
            id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            name="Credit Risk Model",
            slug="credit-risk-model",
            description="Evaluates credit exposure, probability of default, and loss-given-default across counterparties.",
            docker_images=[
                {"name": "data-updater", "image": "alm/cr-data-updater:latest", "order": 1, "env": {"DATA_SOURCE": "internal_db"}},
                {"name": "analyze", "image": "alm/cr-analyze:latest", "order": 2, "env": {"PD_MODEL": "merton"}},
                {"name": "backtest", "image": "alm/cr-backtest:latest", "order": 3, "env": {"STRESS_SCENARIOS": "3"}},
            ],
            default_config={
                "lgd_assumption": {"value": 0.45, "type": "float", "description": "Loss given default assumption"},
                "pd_horizon_years": {"value": 1, "type": "int", "description": "PD estimation horizon in years"},
                "correlation_model": {"value": "gaussian-copula", "type": "string", "description": "Default correlation model"},
                "num_simulations": {"value": 5000, "type": "int", "description": "Number of Monte Carlo simulations"},
            },
            input_schema=[
                {"name": "reporting_date", "type": "date", "required": True},
                {"name": "exposures_file", "type": "file", "required": True, "source": "upload"},
                {"name": "ratings_file", "type": "file", "required": False, "source": "upload"},
                {"name": "macro_scenario", "type": "text", "required": False},
            ],
        )
        session.add(cr_model)

        # Liquidity Model
        liq_model = Model(
            id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            name="Liquidity Model",
            slug="liquidity-model",
            description="Assesses liquidity coverage ratio, net stable funding ratio, and cash flow projections under stress.",
            docker_images=[
                {"name": "data-updater", "image": "alm/liq-data-updater:latest", "order": 1, "env": {"DATA_SOURCE": "treasury_system"}},
                {"name": "analyze", "image": "alm/liq-analyze:latest", "order": 2, "env": {"PROJECTION_DAYS": "90"}},
                {"name": "backtest", "image": "alm/liq-backtest:latest", "order": 3, "env": {"STRESS_TYPE": "idiosyncratic"}},
            ],
            default_config={
                "lcr_threshold": {"value": 1.0, "type": "float", "description": "Minimum LCR threshold"},
                "nsfr_threshold": {"value": 1.0, "type": "float", "description": "Minimum NSFR threshold"},
                "projection_days": {"value": 90, "type": "int", "description": "Cash flow projection horizon in days"},
                "stress_severity": {"value": "moderate", "type": "string", "description": "Stress scenario severity level"},
            },
            input_schema=[
                {"name": "as_of_date", "type": "date", "required": True},
                {"name": "cash_flows_file", "type": "file", "required": True, "source": "upload"},
                {"name": "hqla_file", "type": "file", "required": False, "source": "upload"},
            ],
        )
        session.add(liq_model)

        session.commit()
        print("✓ Seeded successfully!")
        print(f"  Admin, Developer, and Runner users ensured.")
        print(f"  ALM Risk Model, Interest Rate Model, Credit Risk Model, and Liquidity Model ensured.")

    except Exception as exc:
        session.rollback()
        print(f"✗ Seed failed: {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
