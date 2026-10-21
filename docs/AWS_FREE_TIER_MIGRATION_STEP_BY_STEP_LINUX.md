# Migração do `whatsapp-notify` para AWS — Linux

Versão Bash/Linux de [AWS_FREE_TIER_MIGRATION_STEP_BY_STEP.md](AWS_FREE_TIER_MIGRATION_STEP_BY_STEP.md), baseada no [`template.yaml`](../template.yaml). Execute os comandos locais a partir da raiz do repositório. Os blocos marcados **na EC2** devem ser executados somente após entrar na instância por SSH.

## Arquitetura e pré-requisitos

`loto-bot` EC2 → HTTP privado porta 80 → Nginx → Uvicorn em `127.0.0.1:8000` → Playwright/WhatsApp Web. A porta 80 aceita apenas o Security Group do `loto-bot`; SSH aceita apenas o IPv6 público `/128` autorizado. A instância tem IPv6 para saída e não recebe IPv4 público. Não abra as portas 22 ou 80 para a Internet.

Tenha AWS CLI v2, SAM CLI, Python 3.12, `curl`, `zip`, `unzip`, `sha256sum` e OpenSSH (`ssh` e `scp`) no Linux local. Configure um perfil AWS autenticado. A VPC e a subnet dual stack devem ser as mesmas do `loto-bot`, com DNS e rota `::/0`; o endpoint de interface `com.amazonaws.<regiao>.cloudformation` deve estar `available` e com Private DNS. Tenha um Security Group de integração independente e acesso IPv6 público da máquina local. A AMI Ubuntu 24.04 usada abaixo deve corresponder à arquitetura da instância e ao bootstrap do template.

Defina as variáveis nesta sessão do Bash; substitua o perfil antes de executar:

```bash
AWS_PROFILE_NAME='<perfil>'
AWS_REGION_NAME='us-east-1'
APP_NAME='loto-bot'
STACK_NAME='whatsapp-notify'
INSTANCE_TYPE='t3.micro'
REMOTE_USER='ubuntu'
KEY_NAME="$STACK_NAME"
KEY_FILE="$HOME/.ssh/$KEY_NAME.pem"
KNOWN_HOSTS_FILE="$HOME/.ssh/$KEY_NAME-known-hosts"
AWS_ARGS=(--region "$AWS_REGION_NAME" --profile "$AWS_PROFILE_NAME")
LOCAL_PUBLIC_IPV6="$(curl -6 -fsS https://api64.ipify.org)"
ALLOWED_SSH_IPV6_CIDR="$LOCAL_PUBLIC_IPV6/128"
AMI_ID="$(aws ssm get-parameter --name '/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id' --query Parameter.Value --output text "${AWS_ARGS[@]}")"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --profile "$AWS_PROFILE_NAME")"
ARTIFACT_BUCKET="$STACK_NAME-artifacts-$ACCOUNT_ID-$AWS_REGION_NAME"
VPC_ID="$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=$APP_NAME" "Name=tag:Application,Values=$APP_NAME" --query 'Vpcs[0].VpcId' --output text "${AWS_ARGS[@]}")"
AVAILABILITY_ZONE="$(aws ec2 describe-availability-zones --filters Name=state,Values=available --query 'AvailabilityZones[0].ZoneName' --output text "${AWS_ARGS[@]}")"
SUBNET_ID="$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" "Name=availability-zone,Values=$AVAILABILITY_ZONE" "Name=tag:Name,Values=$APP_NAME" "Name=tag:Application,Values=$APP_NAME" --query 'Subnets[0].SubnetId' --output text "${AWS_ARGS[@]}")"
printf 'VPC=%s Subnet=%s AMI=%s SSH=%s\n' "$VPC_ID" "$SUBNET_ID" "$AMI_ID" "$ALLOWED_SSH_IPV6_CIDR"
```

Confirme que as consultas retornaram IDs reais, e que o IPv6 local é o endereço autorizado. Se o IPv6 mudar, atualize `AllowedSshIpv6Cidr` na stack antes de se conectar. Nunca use `::/0` para a porta 22.

Se o Key Pair já existir e você tiver o PEM correspondente, use-o. Para criar um novo par:

```bash
install -d -m 700 "$HOME/.ssh"
(umask 077; aws ec2 create-key-pair --key-name "$KEY_NAME" --key-type ed25519 --key-format pem --tag-specifications "ResourceType=key-pair,Tags=[{Key=Name,Value=$KEY_NAME},{Key=Application,Value=$APP_NAME}]" --query KeyMaterial --output text "${AWS_ARGS[@]}" > "$KEY_FILE")
chmod 600 "$KEY_FILE"
```

Confira a subnet e o endpoint compartilhado:

```bash
aws ec2 describe-subnets --subnet-ids "$SUBNET_ID" --query 'Subnets[0].{VpcId:VpcId,Ipv4:CidrBlock,Ipv6:Ipv6CidrBlockAssociationSet[0].Ipv6CidrBlock,MapPublicIp:MapPublicIpOnLaunch}' --output table "${AWS_ARGS[@]}"
aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION_NAME.cloudformation" --query 'VpcEndpoints[0].{State:State,PrivateDns:PrivateDnsEnabled,SubnetIds:SubnetIds}' --output table "${AWS_ARGS[@]}"
```

O Security Group de integração deve existir antes das stacks, sem regras de entrada e sem ser anexado à EC2 do `whatsapp-notify`. Recupere o ID criado no procedimento do `loto-bot`:

```bash
SECURITY_GROUP_ID="$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=$APP_NAME" --query 'SecurityGroups[0].GroupId' --output text "${AWS_ARGS[@]}")"
printf 'IntegrationSecurityGroupId=%s\n' "$SECURITY_GROUP_ID"
```

O resultado deve ser um único `sg-...`. Não exclua esse grupo enquanto alguma stack o referenciar.

## Testar, empacotar e publicar

```bash
./.venv/bin/python -m pytest
sam validate --lint --template-file template.yaml --region "$AWS_REGION_NAME" --profile "$AWS_PROFILE_NAME"

aws s3api create-bucket --bucket "$ARTIFACT_BUCKET" "${AWS_ARGS[@]}"
aws s3api put-public-access-block --bucket "$ARTIFACT_BUCKET" --public-access-block-configuration 'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true' "${AWS_ARGS[@]}"
aws s3api put-bucket-encryption --bucket "$ARTIFACT_BUCKET" --server-side-encryption-configuration 'Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256}}]' "${AWS_ARGS[@]}"

ARTIFACT_VERSION="$(date -u +%Y%m%d-%H%M%S)"
ARTIFACT_KEY="$STACK_NAME/releases/$ARTIFACT_VERSION/$STACK_NAME.zip"
ARTIFACT_FILE="$(mktemp --suffix=.zip)"
zip -q -r "$ARTIFACT_FILE" pyproject.toml README.md src
unzip -l "$ARTIFACT_FILE"
ARTIFACT_SHA256="$(sha256sum "$ARTIFACT_FILE" | cut -d ' ' -f 1)"
aws s3 cp "$ARTIFACT_FILE" "s3://$ARTIFACT_BUCKET/$ARTIFACT_KEY" --sse AES256 --metadata "sha256=$ARTIFACT_SHA256" "${AWS_ARGS[@]}"
aws s3api head-object --bucket "$ARTIFACT_BUCKET" --key "$ARTIFACT_KEY" "${AWS_ARGS[@]}"
```

Em `us-east-1`, `create-bucket` não usa `LocationConstraint`. Para outra região, acrescente `--create-bucket-configuration "LocationConstraint=$AWS_REGION_NAME"`. Se o bucket já existir e pertencer à sua conta, pule apenas a criação. O ZIP deve conter `pyproject.toml` e `src/` na raiz, sem `.env`, `.venv`, perfil do navegador ou QR code.

## Deploy da primeira instância

Valide antes o endpoint CloudFormation com o teste do projeto `loto-bot`, usando o mesmo perfil, região e VPC. O script de referência `loto-bot/scripts/test-shared-cloudformation-endpoint.ps1` é PowerShell; em Linux, confirme pelo menos o estado e o Private DNS com a consulta acima e execute o teste equivalente disponível no projeto `loto-bot`.

```bash
sam deploy \
  --template-file template.yaml \
  --stack-name "$STACK_NAME" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --region "$AWS_REGION_NAME" --profile "$AWS_PROFILE_NAME" \
  --parameter-overrides \
    "VpcId=$VPC_ID" "SubnetId=$SUBNET_ID" "AmiId=$AMI_ID" \
    "InstanceType=$INSTANCE_TYPE" "KeyName=$KEY_NAME" \
    "AllowedSshIpv6Cidr=$ALLOWED_SSH_IPV6_CIDR" \
    "IntegrationSecurityGroupId=$SECURITY_GROUP_ID" \
    "ArtifactBucket=$ARTIFACT_BUCKET" "ArtifactKey=$ARTIFACT_KEY" \
    "ArtifactSha256=$ARTIFACT_SHA256" RootVolumeSize=16
```

Não reutilize um `samconfig.toml` antigo que contenha `AllowedCidr`. O bootstrap espera IPv6 global e rota default, instala a aplicação e sinaliza o CloudFormation pelo endpoint privado. Não habilite IPv4 público na subnet. Se o sinal falhar, consulte via SSH `sudo cloud-init status --long`, `sudo tail -n 200 /var/log/whatsapp-notify-bootstrap.log`, `ip -6 addr show scope global` e `ip -6 route show default`. Uma stack em `CREATE_FAILED` exige tratamento do estado antes de novo deploy; confirme o endpoint antes de repetir.

## Integrar ao `loto-bot`

```bash
WHATSAPP_NOTIFY_URL="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue | [0]" --output text "${AWS_ARGS[@]}")"
printf 'WhatsAppNotifyUrl=%s IntegrationSecurityGroupId=%s\n' "$WHATSAPP_NOTIFY_URL" "$SECURITY_GROUP_ID"
```

Passe os dois valores no deploy do `loto-bot`. A URL é `http://<private-dns>`, sem barra final. O acesso é controlado pelo Security Group; não envie chave de API.

## Validar operação e autenticar o WhatsApp

```bash
INSTANCE_ID="$(aws cloudformation describe-stack-resource --stack-name "$STACK_NAME" --logical-resource-id ApplicationInstance --query StackResourceDetail.PhysicalResourceId --output text "${AWS_ARGS[@]}")"
INSTANCE_IPV6="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].NetworkInterfaces[0].Ipv6Addresses[0].Ipv6Address' --output text "${AWS_ARGS[@]}")"
SSH_OPTS=(-6 -i "$KEY_FILE" -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE")
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$INSTANCE_IPV6"
```

O usuário `ubuntu` corresponde à AMI Canonical. Verifique o usuário padrão se usar outra AMI. Após sair da sessão SSH, execute os próximos comandos no Linux local:

```bash
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$INSTANCE_IPV6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/status'"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$INSTANCE_IPV6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/start?headless=true&timeoutInSeconds=60'"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$INSTANCE_IPV6" "curl -fL 'http://127.0.0.1:8000/whatsapp/session/qrcode' -o /home/ubuntu/whatsapp-qr.png"
QR_CODE_FILE="$(mktemp --suffix=.png)"
scp -6 -i "$KEY_FILE" -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE" "$REMOTE_USER@[$INSTANCE_IPV6]:/home/ubuntu/whatsapp-qr.png" "$QR_CODE_FILE"
printf 'QR code: %s\n' "$QR_CODE_FILE"
```

Abra o PNG localmente, escaneie o QR code e confirme `SESSAO_ABERTA`. Trate o PNG como credencial: remova as cópias local e remota depois da autenticação. Para homologar o envio, ajuste o contato e execute:

```bash
TEST_CONTACT='Notificação via App'
TEST_MESSAGE="Mensagem de homologação em $(date '+%Y-%m-%d %H:%M:%S')"
TEST_JSON="$(TEST_CONTACT="$TEST_CONTACT" TEST_MESSAGE="$TEST_MESSAGE" python3 -c 'import json, os; print(json.dumps({"contact": os.environ["TEST_CONTACT"], "message": os.environ["TEST_MESSAGE"]}, ensure_ascii=False))')"
printf '%s' "$TEST_JSON" | ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$INSTANCE_IPV6" "curl -i -sSL -X POST 'http://127.0.0.1:8000/whatsapp/messages/send' -H 'Content-Type: application/json; charset=utf-8' --data-binary @-"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$INSTANCE_IPV6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/stop'"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$INSTANCE_IPV6" 'rm -f /home/ubuntu/whatsapp-qr.png'
rm -f "$QR_CODE_FILE"
```

**Na EC2**, inspecione os serviços e logs:

```bash
sudo systemctl status whatsapp-notify nginx --no-pager
sudo journalctl -u whatsapp-notify -n 100 --no-pager
curl -fsS http://127.0.0.1:8000/whatsapp/session/status
```

O serviço deve iniciar por `/opt/whatsapp-notify/app/.venv/bin/whatsapp-notify`. Para diagnóstico temporário, altere `LOG_LEVEL` em `/etc/whatsapp-notify.env`, reinicie o serviço e use `journalctl`; depois retorne para `INFO`. Reiniciar interrompe a sessão ativa, e logs DEBUG podem conter dados sensíveis. Em uma instância com unidade antiga que executa Uvicorn diretamente, crie um override com `sudo systemctl edit whatsapp-notify`:

```ini
[Service]
ExecStart=
ExecStart=/opt/whatsapp-notify/app/.venv/bin/whatsapp-notify
```

Execute `sudo systemctl daemon-reload`, `sudo systemctl restart whatsapp-notify` e `sudo systemctl cat whatsapp-notify` para confirmar. O perfil fica em `/opt/whatsapp-notify/data/.whatsapp-profile` e deve ser tratado como credencial.

## Atualização, rollback e custos

Para atualizar, publique outro ZIP e SHA-256, revise o change set e substitua a EC2 de forma controlada: User Data roda apenas na criação. A substituição do volume raiz apaga o perfil e exige nova autenticação. Trocar `KeyName` também substitui a EC2. Para rollback, reaplique o artefato anterior com substituição da instância e consulte o IPv6 atual; não presuma que o endereço antigo continue válido. Para releases por AMI, siga [CREATE_AMI_AND_DEPLOY_LINUX.md](CREATE_AMI_AND_DEPLOY_LINUX.md).

Confira EC2, EBS gp3, transferência IPv6, S3, snapshots e CloudWatch. A elegibilidade do Free Tier depende da conta, da região e das regras vigentes. Configure AWS Budgets e monitore créditos de CPU e uso do volume.

## Checklist

- [ ] Mesma região, VPC e subnet dual stack do `loto-bot`, sem IPv4 público automático.
- [ ] Endpoint compartilhado CloudFormation `available` com Private DNS.
- [ ] PEM protegido com modo `600`; SSH limitado ao IPv6 público `/128`.
- [ ] Security Group de integração independente e mesmo ID nos dois deploys.
- [ ] Porta 80 aceita somente o Security Group de integração.
- [ ] ZIP versionado, SHA-256 conferido e sem segredos ou perfil.
- [ ] `ApiUrl` privado configurado no `loto-bot`.
- [ ] Serviço, health check e envio validados por SSH IPv6.
- [ ] Nova autenticação planejada para substituições e orçamento monitorado.
