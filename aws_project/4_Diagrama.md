# Diseño Técnico y Diagrama de Arquitectura
**Proyecto**: Sistema de Inventario Nayoli

## Abstracción Lógica del Entorno AWS
El siguiente esquema representa visualmente el flujo de datos y la división de redes del sistema. Cumple con la regla estricta de segmentación: la base de datos (RDS) y los servidores de aplicación (EC2) nunca están expuestos a internet directamente.

```mermaid
graph TD
    User([Usuario/Cliente]) --> |Tráfico HTTP/HTTPS| IGW[Internet Gateway]
    
    subgraph "Amazon Web Services Cloud"
        IGW --> ALB[Application Load Balancer]
        
        subgraph "VPC (Red Privada Virtual)"
            
            subgraph "Availability Zone A (ej. us-east-1a)"
                PublicSubnetA[Subred Pública A]
                PrivateSubnetA[Subred Privada A]
                
                PublicSubnetA -.-> ALB
                PrivateSubnetA --> EC2_A[Servidor App 1 - EC2]
                PrivateSubnetA --> RDS_Primary[(RDS MySQL - Master)]
            end
            
            subgraph "Availability Zone B (ej. us-east-1b)"
                PublicSubnetB[Subred Pública B]
                PrivateSubnetB[Subred Privada B]
                
                PublicSubnetB -.-> ALB
                PrivateSubnetB --> EC2_B[Servidor App 2 - EC2]
                PrivateSubnetB --> RDS_Standby[(RDS MySQL - Réplica)]
            end
            
            %% Flujo de Load Balancing
            ALB --> |Distribución de Carga| EC2_A
            ALB --> |Distribución de Carga| EC2_B
            
            %% Flujo de Base de datos
            EC2_A --> |Lectura/Escritura| RDS_Primary
            EC2_B --> |Lectura/Escritura| RDS_Primary
            RDS_Primary -.-> |Replicación Síncrona Continua| RDS_Standby
        end
        
        %% Flujo de S3
        EC2_A --> |Guardar imágenes vía Boto3| S3[(Amazon S3 Bucket)]
        EC2_B --> |Guardar imágenes vía Boto3| S3
        S3 -.-> |Archivos estáticos| User
    end

    classDef aws fill:#FF9900,stroke:#232F3E,stroke-width:2px,color:black;
    classDef vpc fill:#E8F5E9,stroke:#4CAF50,stroke-width:2px,color:black;
    classDef private fill:#FFE0B2,stroke:#FF9800,stroke-width:2px,color:black;
    classDef public fill:#B3E5FC,stroke:#03A9F4,stroke-width:2px,color:black;
    
    class ALB,IGW public;
    class EC2_A,EC2_B,RDS_Primary,RDS_Standby private;
    class S3 aws;
```

### Notas sobre el Diagrama:
1. **Application Load Balancer**: Actúa como un proxy inverso. Si la "Availability Zone A" entera sufre un apagón eléctrico en el datacenter de Amazon, el ALB dirige todo el tráfico automáticamente al Servidor App 2 en la Zona B.
2. **Replicación Síncrona**: Cada transacción guardada en RDS Master (ej. Una salida de inventario) es escrita simultáneamente en el RDS Standby antes de confirmar el éxito. Si el Master falla, AWS promueve automáticamente el Standby a Master en unos 60 segundos (Failover).
