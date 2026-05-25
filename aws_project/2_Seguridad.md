# Seguridad y Gobernanza
**Proyecto**: Sistema de Inventario Nayoli

Este apartado detalla el endurecimiento (hardening) de la plataforma siguiendo los pilares de seguridad del proveedor en la nube.

## 1. Matriz de Responsabilidad Compartida
De acuerdo al modelo de responsabilidad compartida de AWS:
- **AWS gestiona "La seguridad DE la nube"**: Infraestructura física, red física, hipervisores (virtualización) y la infraestructura del servicio gestionado RDS (parches de SO del motor de base de datos).
- **El Grupo de Trabajo gestiona "La seguridad EN la nube"**:
  - Código de la aplicación Flask.
  - Actualización y parches de seguridad del sistema operativo invitado (Ubuntu) en las EC2.
  - Configuración del firewall de red (Security Groups).
  - Cifrado de datos en reposo y tránsito.

## 2. Políticas IAM (Mínimo Privilegio)
Se han diseñado roles específicos en lugar de usar usuarios administradores:
- **Rol EC2-AppRole**: 
  - Permiso: `AmazonS3FullAccess` limitado estrictamente al bucket `nayoli-assets-bucket`.
  - Propósito: Permitir a la aplicación Flask subir y leer imágenes desde código sin tener que incrustar contraseñas (Access Keys) en el código fuente.
- **Usuario DBA-Admin**:
  - Permiso: `AmazonRDSFullAccess`.
  - Propósito: Gestión exclusiva del motor de base de datos para operaciones de mantenimiento.

## 3. Seguridad Perimetral y Firewalls
Segmentamos el tráfico utilizando **Grupos de Seguridad (Security Groups - SG)**, aplicando una arquitectura de "Defensa en Profundidad":
1. **ALB-SG**: Acepta tráfico de Internet `0.0.0.0/0` en el puerto `80` (HTTP) y `443` (HTTPS).
2. **EC2-App-SG**: Bloquea todo el acceso público. Solo acepta tráfico en el puerto `5000` proveniente exclusivamente del `ALB-SG`. No se permite acceso SSH directo desde internet.
3. **RDS-DB-SG**: Completamente aislado. Solo acepta peticiones en el puerto `3306` (MySQL) provenientes exclusivamente del `EC2-App-SG`.

## 4. Cifrado
- **Datos en Tránsito**: Se utiliza un certificado TLS provisionado gratuitamente a través de **AWS Certificate Manager (ACM)** e instalado en el Application Load Balancer. La comunicación entre el usuario y el balanceador está cifrada.
- **Datos en Reposo**: 
  - Amazon S3: Se activa el cifrado predeterminado SSE-S3.
  - Amazon RDS: Se habilita el cifrado de la instancia de base de datos utilizando claves gestionadas por AWS KMS (Key Management Service).
  - Amazon EBS: Los volúmenes raíz de las instancias EC2 se despliegan cifrados de forma nativa.
