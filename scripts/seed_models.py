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


def seed():
    """Seed the database with an example model and admin user."""
    engine = create_engine(settings.DATABASE_URL_SYNC)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Check if already seeded
        existing_model = session.execute(
            text("SELECT id FROM models WHERE slug = 'alm-risk-model'")
        ).fetchone()

        if existing_model:
            print("Database already seeded (alm-risk-model exists). Skipping.")
            return

        # Create an admin user
        admin_user = User(
            id=uuid.uuid4(),
            ldap_username="admin",
            email="admin@example.com",
            role="admin",
            is_active=True,
        )
        session.add(admin_user)

        # Create a developer user
        dev_user = User(
            id=uuid.uuid4(),
            ldap_username="developer",
            email="developer@example.com",
            role="developer",
            is_active=True,
        )
        session.add(dev_user)

        # Create a runner user
        runner_user = User(
            id=uuid.uuid4(),
            ldap_username="runner",
            email="runner@example.com",
            role="runner",
            is_active=True,
        )
        session.add(runner_user)

        # Create example model: ALM Risk Model
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

        session.commit()
        print("✓ Seeded successfully!")
        print(f"  Admin user:     admin (role: admin)")
        print(f"  Developer user: developer (role: developer)")
        print(f"  Runner user:    runner (role: runner)")
        print(f"  Model:          {example_model.name} (slug: {example_model.slug})")
        print(f"  Model ID:       {example_model.id}")

    except Exception as exc:
        session.rollback()
        print(f"✗ Seed failed: {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
