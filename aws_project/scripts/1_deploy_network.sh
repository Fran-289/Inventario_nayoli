#!/bin/bash
# ==============================================================================
# Script de Despliegue de Infraestructura AWS - Sistema Nayoli
# Este script utiliza AWS CLI para provisionar la red y los componentes.
# ==============================================================================

# Variables Globales
REGION="us-east-1"
VPC_CIDR="10.0.0.0/16"

echo "Iniciando despliegue de Arquitectura Nayoli en AWS..."

# 1. Crear VPC
VPC_ID=$(aws ec2 create-vpc --cidr-block $VPC_CIDR --region $REGION --query 'Vpc.VpcId' --output text)
aws ec2 create-tags --resources $VPC_ID --tags Key=Name,Value=Nayoli-VPC
echo "VPC Creada: $VPC_ID"

# 2. Crear Subredes Públicas (Multi-AZ)
SUBNET_PUB_A=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.1.0/24 --availability-zone ${REGION}a --query 'Subnet.SubnetId' --output text)
SUBNET_PUB_B=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.2.0/24 --availability-zone ${REGION}b --query 'Subnet.SubnetId' --output text)

# 3. Crear Subredes Privadas (Multi-AZ)
SUBNET_PRIV_A=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.3.0/24 --availability-zone ${REGION}a --query 'Subnet.SubnetId' --output text)
SUBNET_PRIV_B=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.4.0/24 --availability-zone ${REGION}b --query 'Subnet.SubnetId' --output text)
echo "Subredes creadas en dos Zonas de Disponibilidad distintas."

# 4. Crear Internet Gateway y adjuntar a la VPC
IGW_ID=$(aws ec2 create-internet-gateway --query 'InternetGateway.InternetGatewayId' --output text)
aws ec2 attach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID

# 5. Configurar Rutas Públicas
ROUTE_TABLE_PUB=$(aws ec2 create-route-table --vpc-id $VPC_ID --query 'RouteTable.RouteTableId' --output text)
aws ec2 create-route --route-table-id $ROUTE_TABLE_PUB --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID
aws ec2 associate-route-table --subnet-id $SUBNET_PUB_A --route-table-id $ROUTE_TABLE_PUB
aws ec2 associate-route-table --subnet-id $SUBNET_PUB_B --route-table-id $ROUTE_TABLE_PUB

# 6. Crear Security Groups
# SG para el Balanceador (ALB)
ALB_SG=$(aws ec2 create-security-group --group-name NayoliALBSG --description "Permitir HTTP/HTTPS al ALB" --vpc-id $VPC_ID --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0

# SG para EC2 (Solo desde ALB)
EC2_SG=$(aws ec2 create-security-group --group-name NayoliEC2SG --description "Permitir trafico solo desde ALB" --vpc-id $VPC_ID --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $EC2_SG --protocol tcp --port 5000 --source-group $ALB_SG

# SG para RDS (Solo desde EC2)
RDS_SG=$(aws ec2 create-security-group --group-name NayoliRDSSG --description "Permitir trafico solo desde EC2" --vpc-id $VPC_ID --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $RDS_SG --protocol tcp --port 3306 --source-group $EC2_SG

echo "Redes y Security Groups configurados correctamente."
echo "Paso Siguiente: Desplegar RDS y crear Launch Template para el ASG usando la consola o scripts avanzados."
