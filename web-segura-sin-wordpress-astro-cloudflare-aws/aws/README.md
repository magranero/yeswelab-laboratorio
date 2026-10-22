# Desplegar la API y PostgreSQL en AWS

> Comandos comprobados con la documentación oficial de AWS en octubre de 2026, pero **no ejecutados por nosotros** en una cuenta real. Revisa cada paso en la consola antes de dar la web por buena.

Arquitectura:

```
Navegador ──► Cloudflare (WAF + CDN) ──► web estática (Astro, Workers static assets)
    │
    └── fetch ──► AWS WAF ──► Balanceador (ALB, HTTPS) ──► API en ECS Express Mode (Fargate)
                                                              │  usuario app_web: solo INSERT
                                                              ▼
                                                  RDS PostgreSQL 18 (sin IP pública, cifrada)
```

Variables que usan los comandos (cámbialas):

```bash
export AWS_REGION=eu-south-2          # España (Aragón)
export CUENTA=$(aws sts get-caller-identity --query Account --output text)
export VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
export SUBREDES=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC --query 'Subnets[].SubnetId' --output text | tr '\t' ',')
```

## 1. Grupos de seguridad: la base de datos solo habla con la API

```bash
SG_API=$(aws ec2 create-security-group --group-name web-api --description "Tareas de la API" --vpc-id $VPC --query GroupId --output text)
SG_DB=$(aws ec2 create-security-group --group-name web-db --description "PostgreSQL: solo desde la API" --vpc-id $VPC --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_DB --protocol tcp --port 5432 --source-group $SG_API
```

`web-db` no acepta nada de internet: solo el puerto 5432 desde las tareas de la API.

## 2. PostgreSQL en RDS: privada, cifrada y con copias

```bash
aws rds create-db-subnet-group --db-subnet-group-name web-db --db-subnet-group-description "Subredes de la base de datos" \
  --subnet-ids $(echo $SUBREDES | tr ',' ' ')

aws rds create-db-instance --db-instance-identifier web-db \
  --engine postgres --engine-version 18.4 --db-instance-class db.t4g.micro \
  --allocated-storage 20 --storage-type gp3 --storage-encrypted \
  --db-name web --master-username propietario --manage-master-user-password \
  --no-publicly-accessible --vpc-security-group-ids $SG_DB --db-subnet-group-name web-db \
  --backup-retention-period 7 --deletion-protection --auto-minor-version-upgrade
```

- `--manage-master-user-password`: la contraseña del administrador la genera y guarda Secrets Manager; nadie la ve en un fichero.
- `--no-publicly-accessible`: sin IP pública. Ni con la contraseña se puede entrar desde internet.
- `--auto-minor-version-upgrade`: los parches de seguridad de PostgreSQL se aplican solos en la ventana de mantenimiento.

Para crear la tabla y el usuario de la API, abre **AWS CloudShell en un entorno de VPC** (misma VPC, grupo `web-api`) y ejecuta `sql/esquema.sql` con `psql`, cambiando antes la contraseña de `app_web`.

## 3. Secretos en Secrets Manager, nunca en el código

```bash
DB_HOST=$(aws rds describe-db-instances --db-instance-identifier web-db --query 'DBInstances[0].Endpoint.Address' --output text)
aws secretsmanager create-secret --name web/database-url \
  --secret-string "postgresql+psycopg://app_web:LA-CONTRASEÑA-DE-APP_WEB@$DB_HOST:5432/web?sslmode=require"
aws secretsmanager create-secret --name web/turnstile-secret --secret-string "TU-SECRETO-DE-TURNSTILE"
aws secretsmanager create-secret --name web/ip-salt --secret-string "$(openssl rand -hex 32)"
```

`sslmode=require`: la conexión entre la API y la base de datos va cifrada.

## 4. La imagen de la API en ECR

```bash
aws ecr create-repository --repository-name web-api --image-scanning-configuration scanOnPush=true
aws ecr get-login-password | docker login --username AWS --password-stdin $CUENTA.dkr.ecr.$AWS_REGION.amazonaws.com
docker buildx build --platform linux/arm64 -t $CUENTA.dkr.ecr.$AWS_REGION.amazonaws.com/web-api:1 --push ../api
```

`scanOnPush`: ECR busca vulnerabilidades conocidas en cada imagen que subes.

## 5. Roles de IAM

```bash
aws iam create-role --role-name ecsTaskExecutionRole --assume-role-policy-document \
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam create-role --role-name ecsInfrastructureRoleForExpressServices --assume-role-policy-document \
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name ecsInfrastructureRoleForExpressServices \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices

# Solo puede leer SUS tres secretos, nada más
aws iam put-role-policy --role-name ecsTaskExecutionRole --policy-name leer-secretos-web --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",\"Resource\":\"arn:aws:secretsmanager:$AWS_REGION:$CUENTA:secret:web/*\"}]}"
```

## 6. La API en ECS Express Mode

App Runner ya no admite clientes nuevos desde el 30 de abril de 2026; AWS recomienda ECS Express Mode. Crea el balanceador con HTTPS, el escalado y los registros.

```bash
# contenedor.json lleva la imagen, el puerto, los dominios de CORS y las referencias a los secretos (no sus valores)
envsubst < contenedor.json > contenedor.generado.json
aws ecs create-express-gateway-service \
  --service-name web-api \
  --execution-role-arn arn:aws:iam::$CUENTA:role/ecsTaskExecutionRole \
  --infrastructure-role-arn arn:aws:iam::$CUENTA:role/ecsInfrastructureRoleForExpressServices \
  --primary-container file://contenedor.generado.json \
  --network-configuration "securityGroups=$SG_API,subnets=$SUBREDES" \
  --cpu-architecture ARM64 --cpu 256 --memory 512 \
  --health-check-path /health \
  --scaling-target 'minTaskCount=1,maxTaskCount=3,autoScalingMetric=AVERAGE_CPU,autoScalingTargetValue=60' \
  --monitor-resources
```

La API queda en `https://web-api.ecs.eu-south-2.on.aws/`. Pon esa URL en `PUBLIC_API_URL` y en el `connect-src` de `web/public/_headers`.

Revisa en la consola de EC2 que el grupo `web-api` solo acepta tráfico desde el grupo del balanceador.

## 7. AWS WAF delante del balanceador

```bash
ACL=$(aws wafv2 create-web-acl --name web-api --scope REGIONAL --default-action Allow={} \
  --rules file://waf-reglas.json \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=web-api \
  --query Summary.ARN --output text)
ALB=$(aws elbv2 describe-load-balancers --query 'LoadBalancers[?contains(LoadBalancerName, `ecs-express`)].LoadBalancerArn | [0]' --output text)
aws wafv2 associate-web-acl --web-acl-arn $ACL --resource-arn $ALB
```

`waf-reglas.json` trae cinco reglas:

1. **Solo rutas de la API:** bloquea todo lo que no sea `/v1/…` o `/health`. Quien busque `/wp-admin` o `/.env` se queda fuera.
2. **Límite por IP:** más de 100 peticiones en 5 minutos desde la misma IP, bloqueada.
3. **IP con mala reputación:** la lista de Amazon de IP que usan bots y atacantes.
4. **Ataques comunes:** reglas gestionadas de AWS contra el Top 10 de OWASP (inyecciones, XSS, cuerpos enormes).
5. **Entradas maliciosas conocidas:** patrones de exploits conocidos (como Log4j).

Si el nombre del balanceador no coincide, búscalo en la consola de EC2 → Balanceadores de carga. Recuerda que Express Mode comparte el mismo balanceador entre hasta 25 servicios: el WAF los protege a todos.

## 8. Comprobar

```bash
API=https://web-api.ecs.eu-south-2.on.aws
curl -s $API/health                                                   # {"ok":true}
curl -s -o /dev/null -w '%{http_code}\n' $API/wp-admin                # 403 (WAF)
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/v1/contacto \
  -H 'Origin: https://otra-web.com' -H 'Content-Type: application/json' -d '{}'   # 403 (origen)
curl -s -D - -o /dev/null -X OPTIONS $API/v1/contacto -H 'Origin: https://otra-web.com' \
  -H 'Access-Control-Request-Method: POST' | grep -i access-control-allow-origin   # nada: CORS cerrado
```
