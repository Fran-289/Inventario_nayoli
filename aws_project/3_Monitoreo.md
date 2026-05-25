# Estrategia de Monitoreo y Observabilidad
**Proyecto**: Sistema de Inventario Nayoli

Para garantizar la disponibilidad y un tiempo medio de recuperación (MTTR) cercano a cero, se ha configurado un entorno de observabilidad integrado en **Amazon CloudWatch**.

## 1. Métricas de Salud Monitoreadas (Dashboard)
Se ha creado un CloudWatch Dashboard unificado que muestra en tiempo real:
1. **CPU Utilization (EC2 ASG)**: Promedio de uso de procesador del clúster. Vital para el escalado.
2. **TargetResponseTime (ALB)**: Latencia (en milisegundos) que le toma a nuestra aplicación Python procesar una vista o petición.
3. **HTTPCode_Target_5XX_Count (ALB)**: Conteo de errores de servidor devueltos por nuestra aplicación. Si sube de 0, hay un problema grave en el código.
4. **DatabaseConnections (RDS)**: Monitoreo de posibles fugas de conexiones o cuellos de botella en la base de datos MySQL.

## 2. Matriz de Alarmas y Flujo de Notificación
Las alarmas están configuradas mediante CloudWatch Alarms y conectadas a un tópico de **Amazon SNS (Simple Notification Service)** para el envío inmediato de correos electrónicos al equipo de soporte.

| Componente | Métrica Condición (Umbral) | Acción Automática | Acción de Notificación (SNS) |
|------------|----------------------------|-------------------|------------------------------|
| **Auto Scaling** | `CPUUtilization > 70%` por 2 min consecutivos | Dispara la política "Scale Out": Añade +1 instancia EC2. | Correo: "Escalado vertical activado por alta carga". |
| **Auto Scaling** | `CPUUtilization < 30%` por 5 min consecutivos | Dispara la política "Scale In": Remueve -1 instancia EC2. | N/A (Solo logs de actividad). |
| **ALB (Web)** | `HTTPCode_5XX > 5` en periodo de 1 minuto | N/A | Correo Crítico: "Errores 5xx detectados en producción". |
| **RDS (DB)** | `FreeStorageSpace < 2GB` | N/A | Correo Preventivo: "Aviso de Base de Datos Llena inminente". |

## 3. Health Checks
El Balanceador de Carga (ALB) ejecuta peticiones a la ruta raíz `/` (o `/login`) del servidor Flask cada 30 segundos. Si no recibe un HTTP 200 OK durante 2 intentos seguidos, marca la máquina virtual como `Unhealthy`, deja de mandarle tráfico, y ordena al Auto Scaling Group que destruya esa máquina y cree una nueva sana automáticamente.
