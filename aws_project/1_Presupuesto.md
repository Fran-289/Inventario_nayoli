# Análisis de Presupuesto y Costos Operativos (OPEX)
**Proyecto**: Sistema de Inventario Nayoli
**Proveedor Cloud**: Amazon Web Services (AWS)

## 1. Estimación de Costos (Mensual)
La siguiente tabla muestra el costo estimado de la arquitectura asumiendo un tráfico moderado de una Pyme (Tienda Nayoli).

| Recurso AWS | Propósito | Cantidad | Costo Mensual Estimado (USD) |
|-------------|-----------|----------|------------------------------|
| **VPC & Subnets** | Red Privada Virtual | 1 | $0.00 |
| **NAT Gateway** | Salida a internet para EC2 en subredes privadas | 1 | ~$32.00 |
| **ALB (Load Balancer)** | Distribución de tráfico | 1 | ~$16.00 |
| **EC2 (t3.micro)** | Servidores Web (Auto Scaling) | 2 (Base) | ~$15.00 |
| **RDS (db.t3.micro)** | Base de Datos MySQL Multi-AZ | 1 | ~$34.00 |
| **Amazon S3** | Almacenamiento de avatares e imágenes | 5 GB | ~$0.15 |
| **EBS (GP3)** | Almacenamiento raíz para EC2 | 2x 8GB | ~$1.28 |
| **Data Transfer** | Transferencia de datos de salida | 10 GB | $0.00 (Gratis 100GB/mes) |
| **Total Estimado** | | | **~$98.43 USD / mes** |

## 2. Justificación de Recursos
- **Instancias EC2 (t3.micro)**: Se seleccionaron debido a que la aplicación está escrita en Flask (Python) de manera ligera. Las instancias "T" acumulan créditos de CPU, ideales para sistemas de inventario que tienen picos de tráfico cortos al registrar ventas, y largos periodos de inactividad.
- **RDS MySQL (db.t3.micro) Multi-AZ**: Es mandatorio para garantizar Alta Disponibilidad (HA). Si una zona de disponibilidad cae, AWS automáticamente conmuta (failover) a la réplica en la segunda zona sin intervención humana.
- **NAT Gateway**: Requerido por seguridad. Nuestras máquinas EC2 no tienen IP Pública; el NAT les permite descargar actualizaciones de Ubuntu y librerías de Python sin exponerlas a Internet.

## 3. Estrategias de Ahorro
Dado que la optimización de costos es un pilar del *Well-Architected Framework*, proponemos lo siguiente:
1. **Auto-Scaling en Horas Valle**: El negocio (Nayoli) no opera de madrugada. Se puede configurar una política de Auto Scaling programada (Scheduled Action) para reducir la capacidad mínima de instancias a 1 (o incluso apagar el ambiente de QA si existiera) durante la noche.
2. **Ciclo de Vida en S3**: Los comprobantes de auditoría antiguos no se consultan frecuentemente. Implementamos una política en S3 que mueve los archivos mayores a 90 días a **S3 Glacier Instant Retrieval**, reduciendo el costo de almacenamiento en un 68%.
3. **Savings Plans**: Si el proyecto demuestra estabilidad tras 3 meses, se adquirirá un *Compute Savings Plan* a 1 año sin pago inicial, reduciendo el costo del cómputo EC2 hasta en un 30%.
