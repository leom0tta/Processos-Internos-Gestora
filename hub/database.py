#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modelos do banco de dados - Hub de Processos
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class AssetTypeMapping(db.Model):
    """Mapeamento de tipos de ativos Gorila → classes de ativos"""
    __tablename__ = 'asset_type_mappings'

    security_type = db.Column(db.String(100), primary_key=True)
    asset_class   = db.Column(db.String(255), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'security_type': self.security_type,
            'asset_class':   self.asset_class,
        }


class AssetNameMapping(db.Model):
    """Mapeamento de nome de ativo → classe de ativo (prioridade sobre security_type)"""
    __tablename__ = 'asset_name_mappings'

    asset_name  = db.Column(db.String(255), primary_key=True)
    asset_class = db.Column(db.String(255), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'asset_name':  self.asset_name,
            'asset_class': self.asset_class,
        }


class Cliente(db.Model):
    """Cadastro de clientes da gestora"""
    __tablename__ = 'clientes'

    id                    = db.Column(db.Integer, primary_key=True)
    nome                  = db.Column(db.String(255), nullable=False)
    cpf                   = db.Column(db.String(14),  unique=True, nullable=True)
    email                 = db.Column(db.String(255), nullable=True)
    perfil                = db.Column(db.String(20),  nullable=True)   # Conservador | Moderado | Agressivo
    portfolio_id          = db.Column(db.String(100), nullable=True)   # ID no Gorila
    gorila_portfolio_name = db.Column(db.String(255), nullable=True)
    ativo                 = db.Column(db.Boolean, default=True)
    created_at            = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at            = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':                    self.id,
            'nome':                  self.nome,
            'cpf':                   self.cpf,
            'email':                 self.email,
            'perfil':                self.perfil,
            'portfolio_id':          self.portfolio_id,
            'gorila_portfolio_name': self.gorila_portfolio_name,
            'ativo':                 self.ativo,
            'created_at':            self.created_at.isoformat() if self.created_at else None,
            'updated_at':            self.updated_at.isoformat() if self.updated_at else None,
        }
