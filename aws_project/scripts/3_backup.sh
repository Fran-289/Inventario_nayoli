#!/bin/bash
# ==============================================================================
# Script de Continuidad de Negocio (Disaster Recovery) - Sistema Nayoli
# Toma Snapshots (respaldos) bajo demanda de la base de datos de producción.
# ==============================================================================

DB_INSTANCE="nayoli-production-db"
TIMESTAMP=$(date +"%Y-%m-%d-%H-%M")
SNAPSHOT_NAME="nayoli-backup-$TIMESTAMP"

echo "Iniciando respaldo manual para la base de datos: $DB_INSTANCE"

# Generar un Snapshot de Amazon RDS
aws rds create-db-snapshot \
    --db-instance-identifier $DB_INSTANCE \
    --db-snapshot-identifier $SNAPSHOT_NAME

echo "Snapshot '$SNAPSHOT_NAME' en proceso de creación."
echo "Puedes verificar el estado en la consola de AWS o usando:"
echo "aws rds describe-db-snapshots --db-snapshot-identifier $SNAPSHOT_NAME"

# (Opcional) Limpiar Snapshots viejos para ahorrar OPEX
# Se recomienda usar AWS Backup Plans automatizados, 
# pero este script cubre requerimientos CLI bajo demanda.
