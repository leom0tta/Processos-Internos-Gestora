#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migração inicial: popula asset_type_mappings a partir do asset_type_mapping.json
Execute UMA vez após criar o banco: python seed_db.py
"""

import json
import sys
from pathlib import Path

# Garante imports corretos
sys.path.insert(0, str(Path(__file__).parent))

from app import app
from database import db, AssetTypeMapping

JSON_PATH = Path(__file__).parent.parent / "asset_type_mapping.json"


def seed():
    with app.app_context():
        db.create_all()

        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)

        mappings = data.get('mappings', {})
        inserted = 0
        skipped  = 0

        for security_type, asset_class in mappings.items():
            existing = AssetTypeMapping.query.get(security_type)
            if existing:
                skipped += 1
                continue
            db.session.add(AssetTypeMapping(
                security_type=security_type,
                asset_class=asset_class,
            ))
            inserted += 1

        db.session.commit()
        print(f"✅ Migração concluída: {inserted} inseridos, {skipped} já existiam.")


if __name__ == '__main__':
    seed()
