# Criar uma AMI imutável e fazer deploy — Linux

Versão Bash/Linux de [CREATE_AMI_AND_DEPLOY.md](CREATE_AMI_AND_DEPLOY.md). Comece após criar e testar a primeira instância com [`template.yaml`](../template.yaml), seguindo [o guia de migração para Linux](AWS_FREE_TIER_MIGRATION_STEP_BY_STEP_LINUX.md). Execute os comandos locais a partir da raiz do repositório.

Uma EC2 não é iniciada diretamente por um snapshot EBS: `create-image` cria a AMI e o snapshot do volume raiz. A AMI deve incluir Python 3.12, AWS CLI, `cfn-signal`, Nginx, Chromium/Playwright, virtualenv, serviço systemd e a release testada. O [`template-ami.yaml`](../template-ami.yaml) valida esse conteúdo no primeiro boot e não reinstala a aplicação.

## Antes de começar

Tenha AWS CLI v2, SAM CLI, `curl`, OpenSSH e acesso SSH IPv6 restrito. Use a mesma região, VPC, subnet dual stack e Security Group de integração do deploy inicial. O endpoint de interface CloudFormation deve estar `available` e com Private DNS. Substitua os valores entre `<` e `>` e confira os IDs antes de alterar recursos.

Se continuar no mesmo Bash do guia de migração, as variáveis já existem. Em uma sessão nova, defina:

```bash
AWS_REGION_NAME='us-east-1'
AWS_PROFILE_NAME='<perfil-aws>'
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
IMAGE_NAME="$STACK_NAME-release-$(date -u +%Y%m%d-%H%M%S)"
VPC_ID="$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=$APP_NAME" "Name=tag:Application,Values=$APP_NAME" --query 'Vpcs[0].VpcId' --output text "${AWS_ARGS[@]}")"
AVAILABILITY_ZONE="$(aws ec2 describe-availability-zones --filters Name=state,Values=available --query 'AvailabilityZones[0].ZoneName' --output text "${AWS_ARGS[@]}")"
SUBNET_ID="$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" "Name=availability-zone,Values=$AVAILABILITY_ZONE" "Name=tag:Name,Values=$APP_NAME" "Name=tag:Application,Values=$APP_NAME" --query 'Subnets[0].SubnetId' --output text "${AWS_ARGS[@]}")"
SECURITY_GROUP_ID="$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=$APP_NAME" --query 'SecurityGroups[0].GroupId' --output text "${AWS_ARGS[@]}")"
INSTANCE_ID="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" --output text "${AWS_ARGS[@]}")"
printf 'Instance=%s VPC=%s Subnet=%s IntegrationSG=%s\n' "$INSTANCE_ID" "$VPC_ID" "$SUBNET_ID" "$SECURITY_GROUP_ID"
```

Confirme que `INSTANCE_ID` começa com `i-`, `VPC_ID` com `vpc-`, `SUBNET_ID` com `subnet-` e `SECURITY_GROUP_ID` com `sg-`. Se algum resultado for `None`, confira perfil, região, tags e outputs antes de continuar. Confirme também:

```bash
aws ec2 describe-subnets --subnet-ids "$SUBNET_ID" --query 'Subnets[0].{VpcId:VpcId,Ipv6:Ipv6CidrBlockAssociationSet[0].Ipv6CidrBlock,MapPublicIp:MapPublicIpOnLaunch}' --output table "${AWS_ARGS[@]}"
aws ec2 describe-security-groups --group-ids "$SECURITY_GROUP_ID" --query 'SecurityGroups[0].{GroupId:GroupId,VpcId:VpcId}' --output table "${AWS_ARGS[@]}"
aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.$AWS_REGION_NAME.cloudformation" --query 'VpcEndpoints[0].{State:State,PrivateDns:PrivateDnsEnabled}' --output table "${AWS_ARGS[@]}"
```

## 1. Testar e higienizar a instância de construção

Antes da limpeza, valide a aplicação e o navegador. A limpeza apaga a sessão do WhatsApp da instância original. Obtenha o IPv6 e conecte pelo Key Pair já associado à stack:

```bash
INSTANCE_IPV6="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].NetworkInterfaces[0].Ipv6Addresses[0].Ipv6Address' --output text "${AWS_ARGS[@]}")"
SSH_OPTS=(-6 -i "$KEY_FILE" -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE")
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$INSTANCE_IPV6"
```

Se o IPv6 local mudou, atualize `AllowedSshIpv6Cidr` na stack antes da conexão; nunca amplie SSH para `::/0`. Na EC2, confirme que `sudo systemctl cat whatsapp-notify` inicia por `/opt/whatsapp-notify/app/.venv/bin/whatsapp-notify`. Se a unidade ainda inicia o Uvicorn diretamente, encerre a sessão em andamento e crie um override com `sudo systemctl edit whatsapp-notify`:

```ini
[Service]
ExecStart=
ExecStart=/opt/whatsapp-notify/app/.venv/bin/whatsapp-notify
```

Execute `sudo systemctl daemon-reload`, `sudo systemctl restart whatsapp-notify` e `sudo systemctl cat whatsapp-notify` para conferir. O override será copiado para a AMI. Mantenha `LOG_LEVEL=INFO` em `/etc/whatsapp-notify.env` e revise qualquer alteração manual nesse arquivo.

**Na EC2**, pare os serviços, remova credenciais e saia:

```bash
sudo systemctl stop whatsapp-notify
sudo systemctl disable whatsapp-notify nginx
sudo find /opt/whatsapp-notify/data/.whatsapp-profile -mindepth 1 -delete
sudo find /root /home /opt/whatsapp-notify -type f \
  \( -name '.env' -o -name '*.pem' -o -name '*.key' \) -delete
sudo rm -f /root/.bash_history /home/*/.bash_history
sudo rm -f /etc/ssh/ssh_host_*
sudo sync
exit
```

Não grave perfil autenticado ou segredos na AMI. Preserve `/etc/whatsapp-notify.env` apenas se contiver os valores não secretos esperados. As chaves de host SSH são recriadas no primeiro boot das instâncias novas. Após `exit`, volte ao Bash local.

## 2. Criar e verificar a AMI

Não use `--no-reboot`: o reboot padrão garante a consistência do sistema de arquivos.

```bash
AMI_ID="$(aws ec2 create-image --instance-id "$INSTANCE_ID" --name "$IMAGE_NAME" --description 'Immutable WhatsApp Notify application release' --tag-specifications "ResourceType=image,Tags=[{Key=Application,Value=$STACK_NAME},{Key=Name,Value=$IMAGE_NAME}]" --query ImageId --output text "${AWS_ARGS[@]}")"
printf 'AMI=%s\n' "$AMI_ID"
aws ec2 wait image-available --image-ids "$AMI_ID" "${AWS_ARGS[@]}"
aws ec2 describe-images --image-ids "$AMI_ID" --query 'Images[0].{AmiId:ImageId,State:State,Snapshots:BlockDeviceMappings[].Ebs.SnapshotId}' --output table "${AWS_ARGS[@]}"
```

Se a espera falhar, consulte o estado com `describe-images` antes do deploy. O volume raiz do template original é criptografado; a AMI e seu snapshot permanecem criptografados.

## 3. Restaurar a instância original, se continuar em uso

O `create-image` reinicia a EC2. Se ela continuará em uso, habilite novamente os serviços:

```bash
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$INSTANCE_IPV6" 'sudo systemctl enable --now nginx whatsapp-notify'
```

Será necessário autenticar o WhatsApp novamente. Se a instância original será aposentada, mantenha-a parada até decidir sobre a remoção.

## 4. Validar e implantar a AMI em uma stack de teste

```bash
sam validate --template-file template-ami.yaml --lint --region "$AWS_REGION_NAME" --profile "$AWS_PROFILE_NAME"
AMI_TEST_STACK_NAME="$STACK_NAME-ami-test"
sam deploy \
  --template-file template-ami.yaml \
  --stack-name "$AMI_TEST_STACK_NAME" \
  --region "$AWS_REGION_NAME" --profile "$AWS_PROFILE_NAME" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    "VpcId=$VPC_ID" "SubnetId=$SUBNET_ID" "AmiId=$AMI_ID" \
    "InstanceType=$INSTANCE_TYPE" "KeyName=$KEY_NAME" \
    "AllowedSshIpv6Cidr=$ALLOWED_SSH_IPV6_CIDR" \
    "IntegrationSecurityGroupId=$SECURITY_GROUP_ID" RootVolumeSize=16
aws cloudformation wait stack-create-complete --stack-name "$AMI_TEST_STACK_NAME" "${AWS_ARGS[@]}"
aws cloudformation describe-stacks --stack-name "$AMI_TEST_STACK_NAME" --query 'Stacks[0].Outputs' --output table "${AWS_ARGS[@]}"
```

Use um nome de stack diferente no primeiro teste. O bootstrap da AMI valida a release, habilita os serviços, aguarda a API e envia `cfn-signal`. Se falhar, consulte `/var/log/whatsapp-notify-bootstrap.log` e `journalctl -u whatsapp-notify` por SSH. Só considere concluído quando a stack estiver `CREATE_COMPLETE` e tiver outputs `InstanceId` e `ApiUrl`.

Homologue a instância nova no Linux local:

```bash
TEST_INSTANCE_ID="$(aws cloudformation describe-stack-resource --stack-name "$AMI_TEST_STACK_NAME" --logical-resource-id ApplicationInstance --query StackResourceDetail.PhysicalResourceId --output text "${AWS_ARGS[@]}")"
TEST_INSTANCE_IPV6="$(aws ec2 describe-instances --instance-ids "$TEST_INSTANCE_ID" --query 'Reservations[0].Instances[0].NetworkInterfaces[0].Ipv6Addresses[0].Ipv6Address' --output text "${AWS_ARGS[@]}")"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$TEST_INSTANCE_IPV6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/status'"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$TEST_INSTANCE_IPV6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/start?headless=true&timeoutInSeconds=60'"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$TEST_INSTANCE_IPV6" "curl -fL 'http://127.0.0.1:8000/whatsapp/session/qrcode' -o /home/ubuntu/whatsapp-qr.png"
QR_CODE_FILE="$(mktemp --suffix=.png)"
scp -6 -i "$KEY_FILE" -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE" "$REMOTE_USER@[$TEST_INSTANCE_IPV6]:/home/ubuntu/whatsapp-qr.png" "$QR_CODE_FILE"
printf 'QR code: %s\n' "$QR_CODE_FILE"
```

Escaneie o QR code, confirme `SESSAO_ABERTA` e ajuste o contato de teste antes do envio:

```bash
TEST_CONTACT='Notificação via App'
TEST_MESSAGE="Mensagem de homologação em $(date '+%Y-%m-%d %H:%M:%S')"
TEST_JSON="$(TEST_CONTACT="$TEST_CONTACT" TEST_MESSAGE="$TEST_MESSAGE" python3 -c 'import json, os; print(json.dumps({"contact": os.environ["TEST_CONTACT"], "message": os.environ["TEST_MESSAGE"]}, ensure_ascii=False))')"
printf '%s' "$TEST_JSON" | ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$TEST_INSTANCE_IPV6" "curl -i -sSL -X POST 'http://127.0.0.1:8000/whatsapp/messages/send' -H 'Content-Type: application/json; charset=utf-8' --data-binary @-"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$TEST_INSTANCE_IPV6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/stop'"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$TEST_INSTANCE_IPV6" 'rm -f /home/ubuntu/whatsapp-qr.png'
rm -f "$QR_CODE_FILE"
```

Confirme ainda que o `loto-bot` acessa o DNS privado do output `ApiUrl` na porta 80. Não envie chave de API: a regra de entrada usa o Security Group consumidor.

## 5. Atualizar e fazer rollback

Para uma nova release, atualize a instância de construção, teste, higienize-a e crie outra AMI. Alterar `AmiId` substitui a EC2 e pode excluir seu volume raiz; preserve separadamente qualquer perfil de WhatsApp que precise sobreviver. Mantenha a AMI anterior para rollback.

Confira a AMI anterior:

```bash
PREVIOUS_AMI_ID='ami-<id-anterior>'
aws ec2 describe-images --image-ids "$PREVIOUS_AMI_ID" --include-disabled --query 'Images[0].{ImageId:ImageId,Name:Name,State:State}' --output table "${AWS_ARGS[@]}"
```

Se estiver desabilitada, reabilite-a com `aws ec2 enable-image --image-id "$PREVIOUS_AMI_ID" "${AWS_ARGS[@]}"`. Interrompa envios e faça snapshot do volume se precisar preservar o perfil. Para voltar à AMI anterior, atualize a stack efetivamente em uso (defina `DEPLOY_STACK_NAME` para ela):

```bash
DEPLOY_STACK_NAME="$AMI_TEST_STACK_NAME"
sam deploy \
  --template-file template-ami.yaml \
  --stack-name "$DEPLOY_STACK_NAME" \
  --region "$AWS_REGION_NAME" --profile "$AWS_PROFILE_NAME" \
  --capabilities CAPABILITY_IAM --confirm-changeset \
  --parameter-overrides \
    "VpcId=$VPC_ID" "SubnetId=$SUBNET_ID" "AmiId=$PREVIOUS_AMI_ID" \
    "InstanceType=$INSTANCE_TYPE" "KeyName=$KEY_NAME" \
    "AllowedSshIpv6Cidr=$ALLOWED_SSH_IPV6_CIDR" \
    "IntegrationSecurityGroupId=$SECURITY_GROUP_ID" RootVolumeSize=16
```

Confirme no change set que `ApplicationInstance` será substituída. Aguarde `UPDATE_COMPLETE`, consulte o novo IPv6 e repita a homologação. Se não restaurar o perfil, autentique o WhatsApp novamente. Confirme que o `ApiUrl` ainda está configurado como `WhatsAppNotifyUrl` no `loto-bot`. Não desabilite a AMI anterior antes desse teste.

## 6. Desabilitar ou remover uma AMI antiga

Desabilitar impede novos lançamentos e é reversível, mas remove permissões de compartilhamento:

```bash
aws ec2 disable-image --image-id "$AMI_ID" "${AWS_ARGS[@]}"
```

Antes da remoção definitiva, confira instâncias dependentes e anote os snapshots associados:

```bash
RETIRED_AMI_ID='ami-<id-confirmado>'
aws ec2 describe-instances --filters "Name=image-id,Values=$RETIRED_AMI_ID" 'Name=instance-state-name,Values=pending,running,stopping,stopped' --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name}' --output table "${AWS_ARGS[@]}"
aws ec2 describe-images --image-ids "$RETIRED_AMI_ID" --query 'Images[0].BlockDeviceMappings[].Ebs.SnapshotId' --output table "${AWS_ARGS[@]}"
```

Se aparecer uma instância ou a AMI ainda for necessária para rollback, pare. Após confirmar a retirada, desregistre a imagem e apague somente os snapshots anotados:

```bash
aws ec2 deregister-image --image-id "$RETIRED_AMI_ID" "${AWS_ARGS[@]}"
AMI_SNAPSHOT_IDS=('snap-<id-confirmado>')
for SNAPSHOT_ID in "${AMI_SNAPSHOT_IDS[@]}"; do
  aws ec2 delete-snapshot --snapshot-id "$SNAPSHOT_ID" "${AWS_ARGS[@]}"
done
```

Desregistrar a AMI não exclui automaticamente seus snapshots. Sem regra prévia de Recycle Bin, trate essa remoção como permanente.

## 7. Recursos fora do SAM

Depois de `sam delete` da stack correta, revise releases S3, bucket, AMIs, snapshots, Elastic IP, DNS e Budget. Não remova recursos compartilhados com o `loto-bot` ou necessários para rollback. Para listar releases:

```bash
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --profile "$AWS_PROFILE_NAME")"
ARTIFACT_BUCKET="$STACK_NAME-artifacts-$ACCOUNT_ID-$AWS_REGION_NAME"
aws s3api list-objects-v2 --bucket "$ARTIFACT_BUCKET" --prefix "$STACK_NAME/releases/" --query 'Contents[].{Key:Key,Modified:LastModified,Size:Size}' --output table "${AWS_ARGS[@]}"
```

Remova uma única release somente depois de confirmar sua chave e ausência de dependências:

```bash
ARTIFACT_KEY_TO_DELETE='whatsapp-notify/releases/<versao-confirmada>/whatsapp-notify.zip'
aws s3api head-object --bucket "$ARTIFACT_BUCKET" --key "$ARTIFACT_KEY_TO_DELETE" "${AWS_ARGS[@]}"
aws s3api delete-object --bucket "$ARTIFACT_BUCKET" --key "$ARTIFACT_KEY_TO_DELETE" "${AWS_ARGS[@]}"
```

Não use remoção recursiva em bucket compartilhado. Buckets versionados exigem tratar versões e delete markers antes da exclusão do bucket.
