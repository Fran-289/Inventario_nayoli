#!/bin/bash
# ==============================================================================
# Script de Despliegue Computacional y Base de Datos - Sistema Nayoli
# ==============================================================================

REGION="us-east-1"
DB_PASSWORD="SuperSecretPassword123!"

echo "Iniciando despliegue de Base de Datos y EC2..."

# Asumimos que los Security Groups y Subredes fueron exportados como variables
# SUBNET_PRIV_A, SUBNET_PRIV_B, RDS_SG, EC2_SG, ALB_SG, VPC_ID

# 1. Crear Subnet Group para RDS (Multi-AZ)
aws rds create-db-subnet-group \
    --db-subnet-group-name nayoli-db-subnet-group \
    --db-subnet-group-description "Subredes para alta disponibilidad RDS" \
    --subnet-ids $SUBNET_PRIV_A $SUBNET_PRIV_B

# 2. Desplegar Amazon RDS MySQL (Multi-AZ Activado)
aws rds create-db-instance \
    --db-instance-identifier nayoli-production-db \
    --db-instance-class db.t3.micro \
    --engine mysql \
    --master-username admin \
    --master-user-password $DB_PASSWORD \
    --allocated-storage 20 \
    --db-subnet-group-name nayoli-db-subnet-group \
    --vpc-security-group-ids $RDS_SG \
    --multi-az \
    --backup-retention-period 7 \
    --no-publicly-accessible

echo "RDS MySQL Creándose (Puede tardar hasta 15 minutos)..."

# 3. Crear Target Group para ALB
TARGET_GROUP_ARN=$(aws elbv2 create-target-group \
    --name nayoli-tg \
    --protocol HTTP \
    --port 5000 \
    --vpc-id $VPC_ID \
    --health-check-path "/" \
    --query 'TargetGroups[0].TargetGroupArn' --output text)

# 4. Crear Load Balancer
ALB_ARN=$(aws elbv2 create-load-balancer \
    --name nayoli-alb \
    --subnets $SUBNET_PUB_A $SUBNET_PUB_B \
    --security-groups $ALB_SG \
    --scheme internet-facing \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text)

# 5. Crear Listener del ALB
aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=$TARGET_GROUP_ARN

echo "ALB Creado y configurado."

# 6. Crear Launch Template para Auto Scaling Group (ASG)
# Incluimos los comandos de inicio de servidor en Base64 (UserData)
USER_DATA=$(base64 -w 0 <<EOF
#!/bin/bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv git
git clone https://github.com/tu-usuario/nayoli-inventory.git /var/www/nayoli
cd /var/www/nayoli
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export DB_HOST="nayoli-production-db.xxxxxxxx.us-east-1.rds.amazonaws.com"
export DB_USER="admin"
export DB_PASS="$DB_PASSWORD"
export DB_NAME="nayoli"
export S3_BUCKET="nayoli-assets-bucket"
gunicorn -w 4 -b 0.0.0.0:5000 app:app &
EOF
)

aws ec2 create-launch-template \
    --launch-template-name nayoli-lt \
    --version-description "V1" \
    --launch-template-data "{\"ImageId\":\"ami-0c7217cdde317cfec\",\"InstanceType\":\"t3.micro\",\"SecurityGroupIds\":[\"$EC2_SG\"],\"UserData\":\"$USER_DATA\"}"

# 7. Crear Auto Scaling Group
aws autoscaling create-auto-scaling-group \
    --auto-scaling-group-name nayoli-asg \
    --launch-template LaunchTemplateName=nayoli-lt,Version=1 \
    --min-size 2 \
    --max-size 4 \
    --desired-capacity 2 \
    --vpc-zone-identifier "$SUBNET_PRIV_A,$SUBNET_PRIV_B" \
    --target-group-arns $TARGET_GROUP_ARN

echo "Auto Scaling Group Creado con Éxito. Despliegue Computacional Finalizado."
