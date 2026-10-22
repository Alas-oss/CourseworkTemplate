import os
import sqlite3
from contextlib import contextmanager

DB = os.getenv("DATABASE_PATH", "/data/cloud_ai.db")


@contextmanager
def connection():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def initialise_database():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)

    with connection() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS microservice_costs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            cost_per_hour REAL NOT NULL CHECK(cost_per_hour>=0),
            currency TEXT NOT NULL DEFAULT 'GBP',
            enabled_by_default INTEGER NOT NULL DEFAULT 1 CHECK(enabled_by_default IN(0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS carbon_profiles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT UNIQUE NOT NULL,
            energy_kwh REAL NOT NULL CHECK(energy_kwh>=0),
            carbon_intensity_gco2e_per_kwh REAL NOT NULL CHECK(carbon_intensity_gco2e_per_kwh>=0),
            embodied_emissions_gco2e REAL NOT NULL CHECK(embodied_emissions_gco2e>=0),
            functional_unit REAL NOT NULL CHECK(functional_unit>0),
            functional_unit_name TEXT NOT NULL DEFAULT 'request',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        costs = [
            ('api', 'FastAPI gateway and game engine', 0.030),
            ('semantic-worker', 'Semantic action service', 0.045),
            ('llm-worker', 'Ollama guide worker', 0.060),
            ('ollama', 'CPU model server', 0.120),
            ('rabbitmq', 'Message broker', 0.025),
            ('firebase', 'Authentication', 0.001),
            ('redis', 'State and request cache', 0.020),
            ('frontend', 'Nginx frontend', 0.010),
            ('prometheus', 'Metrics collector', 0.015),
            ('grafana', 'Dashboard', 0.015),
        ]

        c.executemany(
            """
            INSERT OR IGNORE INTO microservice_costs(
                service_name,
                description,
                cost_per_hour
            ) VALUES(?,?,?)
            """,
            costs
        )

        carbon = [
            ('api', 0.020, 180.0, 0.45, 1000, 'request'),
            ('semantic-worker', 0.035, 180.0, 0.70, 1000, 'request'),
            ('llm-worker', 0.055, 180.0, 1.10, 1000, 'request'),
            ('ollama', 0.120, 180.0, 2.40, 1000, 'request'),
            ('rabbitmq', 0.018, 180.0, 0.35, 1000, 'request'),
            ('redis', 0.018, 180.0, 0.35, 1000, 'request'),
            ('firebase', 0.012, 180.0, 0.20, 1000, 'request'),
            ('frontend', 0.008, 180.0, 0.15, 1000, 'request'),
        ]

        c.executemany(
            """
            INSERT OR IGNORE INTO carbon_profiles(
                service_name,
                energy_kwh,
                carbon_intensity_gco2e_per_kwh,
                embodied_emissions_gco2e,
                functional_unit,
                functional_unit_name
            ) VALUES(?,?,?,?,?,?)
            """,
            carbon
        )