# Criar uma AMI imutável e fazer deploy

Este guia começa depois que a primeira instância já foi criada com
`template.yaml` e testada com sucesso. Se isso ainda não foi feito, volte para
[`AWS_FREE_TIER_MIGRATION_STEP_BY_STEP.md`](AWS_FREE_TIER_MIGRATION_STEP_BY_STEP.md)
e conclua o primeiro deploy e a validação operacional.

Uma instância EC2 não é iniciada diretamente por um snapshot EBS. O procedimento
correto é criar uma AMI; durante essa operação, a AWS cria e associa
automaticamente o snapshot do volume raiz.

O template `template-ami.yaml` usa a AMI como uma release imutável. Ela deve
conter Python 3.12, AWS CLI, `cfn-signal`, nginx, Playwright/Chromium, o usuário
`whatsapp-notify`, a virtualenv, os serviços systemd e a versão já testada da
aplicação instalada pelo `template.yaml`. O primeiro boot apenas valida esse
conteúdo, inicia os serviços e executa o health check; não baixa nem reinstala
o código.

## Visão geral

O processo tem quatro partes:

1. identificar a instância de construção;
2. remover dados que não podem ser copiados;
3. criar e aguardar a AMI ficar disponível;
4. criar uma stack de teste usando `template-ami.yaml`.

Ao final, a AMI será a unidade da release. Para atualizar código ou
dependências, crie outra AMI; não altere o conteúdo de uma instância já criada.

## Antes de começar

Execute os comandos PowerShell a partir da raiz do projeto, onde estão
`template.yaml` e `template-ami.yaml`. Confirme que você possui:

- AWS CLI e SAM CLI instalados;
- um perfil AWS autenticado;
- a stack original criada com `template.yaml`;
- acesso à instância pelo SSH IPv6 restrito configurado no guia principal;
- os valores de `$VpcId`, `$SubnetId`, `$InstanceType` e
  `$SecurityGroupId` usados no guia principal; os três identificadores
  de rede devem ser os mesmos criados pelo procedimento do `loto-bot`.

O `template-ami.yaml` mantém a instância na subnet dual-stack compartilhada,
atribui um IPv6, aguarda o endereço global e a rota IPv6 default antes de
executar as verificações da AMI e sinalizar o CloudFormation, habilita endpoints
AWS dual-stack no bootstrap e não depende de IPv4 público.

Antes do deploy, confirme que o Interface VPC Endpoint compartilhado
`com.amazonaws.<regiao>.cloudformation`, criado pelo guia principal do
`loto-bot`, está `available` e com Private DNS habilitado. Tanto o template base
quanto o template de AMI dependem desse endpoint para entregar o `cfn-signal`
sem NAT ou IPv4 público.

Valores entre `<` e `>` precisam ser substituídos. Antes de executar um comando
que altera recursos, confira o perfil, a região, o ID da instância e o ID da AMI.

## 1. Identificar a instância de construção

No PowerShell:

```powershell
$AppName = "loto-bot"
$StackName = "whatsapp-notify"
$AwsRegion = "us-east-1"
$AwsProfile = "<perfil-aws>"
$ImageName = "$StackName-release-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$InstanceType = "t3.micro"
$RemoteUser = "ubuntu"
$KeyName = $StackName
$KeyFile = Join-Path $HOME ".ssh\$KeyName.pem"
$KnownHostsFile = Join-Path $HOME ".ssh\$KeyName-known-hosts"
$LocalPublicIpv6 = (curl.exe -6 -fsS https://api64.ipify.org).Trim()
$AllowedSshIpv6Cidr = "$LocalPublicIpv6/128"
$AwsCommon = @("--region", $AwsRegion, "--profile", $AwsProfile)
$VpcId = aws ec2 describe-vpcs `
    --filters "Name=tag:Name,Values=$AppName" `
              "Name=tag:Application,Values=$AppName" `
    --query "Vpcs[0].VpcId" `
    --region $AwsRegion `
    --profile $AwsProfile `
    --output text
$AvailabilityZone = aws ec2 describe-availability-zones `
  --filters "Name=state,Values=available" `
  --query "AvailabilityZones[0].ZoneName" `
  --region $AwsRegion `
  --profile $AwsProfile `
  --output text
$SubnetId = aws ec2 describe-subnets `
    --filters "Name=vpc-id,Values=$VpcId" `
              "Name=availability-zone,Values=$AvailabilityZone" `
              "Name=tag:Name,Values=$AppName" `
              "Name=tag:Application,Values=$AppName" `
    --query "Subnets[0].SubnetId" `
    --region $AwsRegion `
    --profile $AwsProfile `
    --output text
$SecurityGroupId = aws ec2 describe-security-groups `
  --filters "Name=vpc-id,Values=$VpcId" "Name=group-name,Values=$AppName" `
  --query "SecurityGroups[0].GroupId" --output text `
  --region $AwsRegion --profile $AwsProfile

aws ec2 describe-subnets --subnet-ids $SubnetId `
  --query "Subnets[0].{VpcId:VpcId,Ipv6:Ipv6CidrBlockAssociationSet[0].Ipv6CidrBlock,MapPublicIp:MapPublicIpOnLaunch}" `
  --output table --region $AwsRegion --profile $AwsProfile
aws ec2 describe-security-groups --group-ids $SecurityGroupId `
  --query "SecurityGroups[0].{GroupId:GroupId,VpcId:VpcId}" `
  --output table --region $AwsRegion --profile $AwsProfile

$InstanceId = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --region $AwsRegion `
  --profile $AwsProfile `
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" `
  --output text
```

Confirme que `$InstanceId` começa com `i-` e corresponde à instância esperada:

```powershell
$InstanceId
```

Se o resultado estiver vazio ou contiver `None`, não continue. Confira o nome
da stack, a região, o perfil e se a stack possui o output `InstanceId`.

## 2. Testar e higienizar a instância

Antes da limpeza, confirme que a aplicação e o navegador funcionam e que esta é
a versão que deve entrar na AMI. Depois da limpeza, a sessão do WhatsApp será
apagada da instância de construção.

No computador Windows, use o SSH IPv6. O Key Pair e o `/128` autorizado devem
ser os mesmos informados no deploy da stack original:

```powershell
$InstanceIpv6 = aws ec2 describe-instances `
  --instance-ids $InstanceId `
  --query "Reservations[0].Instances[0].NetworkInterfaces[0].Ipv6Addresses[0].Ipv6Address" `
  --output text --region $AwsRegion --profile $AwsProfile

ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6"
```

Nunca amplie a regra SSH para `::/0`. Se o IPv6 público local mudar, atualize
`AllowedSshIpv6Cidr` na stack antes da conexão.

Na instância de construção, confira se a unidade systemd inicia por
`/opt/whatsapp-notify/app/.venv/bin/whatsapp-notify`, e não diretamente pelo
Uvicorn. Esse ponto de entrada aplica `LOG_LEVEL` e o formato de log da
aplicação. Se a unidade ainda for a antiga, encerre qualquer sessão em
andamento e crie um override com `sudo systemctl edit whatsapp-notify`:

```ini
[Service]
ExecStart=
ExecStart=/opt/whatsapp-notify/app/.venv/bin/whatsapp-notify
```

Execute `sudo systemctl daemon-reload`, reinicie o serviço e confira
`sudo systemctl cat whatsapp-notify` antes de higienizar a instância. O override
ficará na AMI. O `template-ami.yaml` não reescreve a unidade systemd nem corrige
uma AMI antiga; para esse fluxo permanente, gere uma nova AMI a partir da
instância corrigida. Mantenha `LOG_LEVEL=INFO` na imagem; use `DEBUG` apenas
temporariamente para diagnóstico e revise os logs antes de compartilhá-los.

Após essa verificação, execute o bloco Bash abaixo. Ele para a
aplicação, impede inicialização prematura nas cópias e remove dados que não
devem ser clonados:

```bash
sudo systemctl stop whatsapp-notify
sudo systemctl disable whatsapp-notify nginx
sudo find /opt/whatsapp-notify/data/.whatsapp-profile -mindepth 1 -delete
sudo rm -f /root/.bash_history /home/*/.bash_history
sudo find /root /home /opt/whatsapp-notify -type f \
  \( -name '.env' -o -name '*.pem' -o -name '*.key' \) -delete
sudo rm -f /etc/ssh/ssh_host_*
sudo sync
exit
```

Não remova `/etc/whatsapp-notify.env`, pois o template original cria esse
arquivo apenas com valores não secretos. Revise-o antes de criar a imagem caso
tenha sido alterado manualmente.

> A limpeza do perfil encerra a sessão do WhatsApp nas futuras instâncias. Não
> grave uma sessão autenticada na AMI: qualquer instância criada a partir dela
> receberia uma cópia dessas credenciais.

As chaves de host SSH também são removidas para que o `cloud-init` gere uma
identidade nova no primeiro boot de cada instância criada a partir da AMI.

Ao executar `exit`, você volta ao PowerShell do computador local. Os próximos
comandos não devem ser executados dentro da EC2.

## 3. Criar e verificar a AMI

No PowerShell local, crie a imagem sem usar `--no-reboot`. O reboot padrão
garante consistência do sistema de arquivos. A espera pode levar alguns
minutos:

```powershell
$AmiId = aws ec2 create-image `
  --instance-id $InstanceId `
  --name $ImageName `
  --description "Immutable WhatsApp Notify application release" `
  --tag-specifications "ResourceType=image,Tags=[{Key=Application,Value=$StackName},{Key=Name,Value=$ImageName}]" `
  --region $AwsRegion `
  --profile $AwsProfile `
  --query ImageId `
  --output text

aws ec2 wait image-available `
  --image-ids $AmiId `
  --region $AwsRegion `
  --profile $AwsProfile
```

O comando `wait` termina sem saída quando a AMI fica disponível. Se ele retornar
erro, não faça o deploy antes de consultar o estado com `describe-images`.

Consulte a AMI e o snapshot EBS criado:

```powershell
aws ec2 describe-images `
  --image-ids $AmiId `
  --region $AwsRegion `
  --profile $AwsProfile `
  --query "Images[0].{AmiId:ImageId,State:State,Snapshots:BlockDeviceMappings[].Ebs.SnapshotId}" `
  --output table
```

Como o volume raiz do template original é criptografado, o snapshot e a AMI
também permanecem criptografados.

## 4. Restaurar a instância de construção

O `create-image` reinicia a EC2. Como os serviços foram desabilitados antes da
captura para impedir que a aplicação inicie antes da validação do novo boot,
habilite-os novamente caso a instância original continue em uso:

```powershell
ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "sudo systemctl enable --now nginx whatsapp-notify"
```

Será necessário autenticar novamente o WhatsApp porque o perfil foi removido.

Se a instância original não será mais usada, pule esta etapa e mantenha-a parada
até decidir se ela pode ser removida.

## 5. Validar e fazer o deploy de teste

Primeiro valide o template no PowerShell local:

```powershell
sam validate --template-file template-ami.yaml `
  --lint `
  --region $AwsRegion `
  --profile $AwsProfile
```

Depois use outro nome de stack no primeiro teste para não substituir
imediatamente a instância atual:

```powershell
sam deploy `
  --template-file template-ami.yaml `
  --stack-name $StackName `
  --region $AwsRegion `
  --profile $AwsProfile `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides `
    VpcId=$VpcId `
    SubnetId=$SubnetId `
    AmiId=$AmiId `
    InstanceType=$InstanceType `
    KeyName=$KeyName `
    AllowedSshIpv6Cidr=$AllowedSshIpv6Cidr `
    IntegrationSecurityGroupId=$SecurityGroupId `
    RootVolumeSize=16
```

O bootstrap não baixa artefatos nem executa `pip install`: ele valida a release
contida na AMI, habilita os serviços, aguarda a API responder e envia o
`cfn-signal` ao CloudFormation. O health check faz até 20 tentativas com
intervalo de três segundos, pois o `systemctl` pode retornar antes de o Uvicorn
começar a aceitar conexões.

Se o deploy receber um sinal de falha, consulte
`/var/log/whatsapp-notify-bootstrap.log` e
`journalctl -u whatsapp-notify`. Uma aplicação que fica ativa alguns segundos
depois de uma primeira conexão recusada indica que foi usado um template antigo,
sem o loop de espera.

Espere a conclusão e consulte os outputs:

```powershell
aws cloudformation wait stack-create-complete `
  --stack-name $StackName `
  --region $AwsRegion `
  --profile $AwsProfile

aws cloudformation describe-stacks `
  --stack-name $StackName `
  --query "Stacks[0].Outputs" `
  --output table `
  --region $AwsRegion `
  --profile $AwsProfile
```

O deploy está pronto para homologação quando a stack estiver em
`CREATE_COMPLETE` e os outputs `InstanceId` e `ApiUrl` tiverem sido criados.
Valide pelo SSH IPv6 restrito. Confirme, a partir do `loto-bot`, que o
DNS privado responde por HTTP na porta 80. Não envie chave de API: a autorização
é feita pela referência ao Security Group consumidor.

Para executar a homologação completa pelo SSH IPv6, incluindo a captura do QR
code e o envio de uma mensagem de teste, use no PowerShell local:

```powershell
$InstanceId = aws cloudformation describe-stack-resource --stack-name $StackName --logical-resource-id ApplicationInstance --query "StackResourceDetail.PhysicalResourceId" --output text --region $AwsRegion --profile $AwsProfile

$InstanceIpv6 = aws ec2 describe-instances `
  --instance-ids $InstanceId `
  --query "Reservations[0].Instances[0].NetworkInterfaces[0].Ipv6Addresses[0].Ipv6Address" `
  --output text --region $AwsRegion --profile $AwsProfile

ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/status'"
ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/start?headless=true&timeoutInSecounds=60'"
ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/status'"
ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "curl -fL http://127.0.0.1:8000/whatsapp/session/qrcode -o whatsapp-qr.png"

$QRCodeFile = Join-Path $env:TEMP "whatsapp-qr.png"
scp @SshOptions -- "$RemoteUser@[${InstanceIpv6}]:/home/ubuntu/whatsapp-qr.png" $QRCodeFile

ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/status'"

$DateTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$Json = @{
    contact = "Notificação via App"
    message = "Mensagem de homologação executado em $DateTime"
} | ConvertTo-Json -Compress
$JsonBase64 = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($Json)
)
ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" `
    "echo '$JsonBase64' | base64 -d | curl -i -sSL -X POST 'http://127.0.0.1:8000/whatsapp/messages/send' -H 'Content-Type: application/json; charset=utf-8' --data-binary @-"

ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/stop'"

ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "sudo journalctl -u whatsapp-notify -n 200 -f"
```

## 6. Atualizar, fazer rollback ou remover

Quando o código da aplicação ou suas dependências mudarem, atualize primeiro a
instância de construção, execute testes e smoke test, higienize-a, gere uma nova
AMI e altere `AmiId` no próximo deploy. A alteração de `AmiId` substitui a EC2;
por isso preserve a AMI anterior para rollback e proteja separadamente qualquer
perfil do WhatsApp que precise sobreviver à substituição.

### 6.1 Fazer rollback para a AMI anterior

Defina e confira a imagem anterior:

```powershell
$PreviousAmiId = "ami-<id-anterior>"

aws ec2 describe-images `
  --image-ids $PreviousAmiId `
  --include-disabled `
  --query "Images[0].{ImageId:ImageId,Name:Name,State:State}" `
  --output table `
  --region $AwsRegion `
  --profile $AwsProfile
```

Se ela estiver desabilitada, restaure sua capacidade de lançamento:

```powershell
aws ec2 enable-image `
  --image-id $PreviousAmiId `
  --region $AwsRegion `
  --profile $AwsProfile
```

Antes de continuar, interrompa envios. Se precisar preservar o perfil do
WhatsApp, crie um snapshot de backup; a substituição da EC2 pode excluir o
volume raiz atual. Depois atualize a stack com todos os parâmetros obrigatórios:

```powershell
sam deploy `
  --template-file template-ami.yaml `
  --stack-name $StackName `
  --region $AwsRegion `
  --profile $AwsProfile `
  --capabilities CAPABILITY_IAM `
  --confirm-changeset `
  --parameter-overrides `
    VpcId=$VpcId `
    SubnetId=$SubnetId `
    AmiId=$PreviousAmiId `
    InstanceType=$InstanceType `
    KeyName=$KeyName `
    AllowedSshIpv6Cidr=$AllowedSshIpv6Cidr `
    IntegrationSecurityGroupId=$SecurityGroupId `
    RootVolumeSize=16
```

Confirme no change set que `ApplicationInstance` será substituída. Aguarde
`UPDATE_COMPLETE`, conecte pelo SSH IPv6 restrito e execute o smoke test do
guia principal. Se não restaurar um backup do perfil, autentique o WhatsApp
novamente. Confirme também que o output `ApiUrl` continua configurado como
`WhatsAppNotifyUrl` no deploy do `loto-bot`.

Não desabilite nem remova a AMI anterior antes de concluir esse teste.

### 6.2 Desabilitar uma AMI sem apagá-la

Para impedir novos usos de uma imagem antiga sem apagá-la:

```powershell
aws ec2 disable-image `
  --image-id $AmiId `
  --region $AwsRegion `
  --profile $AwsProfile
```

Desabilitar é reversível, mas remove permissões de compartilhamento. Use
`enable-image` para permitir lançamentos novamente; compartilhamentos anteriores
precisam ser concedidos outra vez.

### 6.3 Remover definitivamente uma AMI

Primeiro confirme que nenhuma instância usa a imagem e registre os snapshots
associados **antes** do deregistro:

```powershell
$RetiredAmiId = "ami-<id-confirmado>"

aws ec2 describe-instances `
  --filters "Name=image-id,Values=$RetiredAmiId" `
            "Name=instance-state-name,Values=pending,running,stopping,stopped" `
  --query "Reservations[].Instances[].{Id:InstanceId,State:State.Name}" `
  --output table `
  --region $AwsRegion `
  --profile $AwsProfile

aws ec2 describe-images `
  --image-ids $RetiredAmiId `
  --query "Images[0].BlockDeviceMappings[].Ebs.SnapshotId" `
  --output table `
  --region $AwsRegion `
  --profile $AwsProfile
```

Se aparecer uma instância, pare: ela ainda depende da AMI. Anote todos os IDs
`snap-...`. Somente quando a imagem não for necessária para execução nem
rollback, desregistre-a e apague os snapshots anotados:

```powershell
aws ec2 deregister-image `
  --image-id $RetiredAmiId `
  --region $AwsRegion `
  --profile $AwsProfile

$AmiSnapshotIds = @("snap-<id-confirmado>")
foreach ($AmiSnapshotId in $AmiSnapshotIds) {
  aws ec2 delete-snapshot `
    --snapshot-id $AmiSnapshotId `
    --region $AwsRegion `
    --profile $AwsProfile
}
```

Desregistrar não exclui os snapshots automaticamente. Sem uma regra prévia do
Recycle Bin, considere essa remoção permanente.

## 7. Limpar recursos criados fora do SAM

Depois de `sam delete`, confira os recursos que não pertencem à stack:

| Recurso | Ação segura |
| --- | --- |
| Releases no S3 | Liste o prefixo e remova somente chaves que não são mais necessárias |
| Bucket S3 | Remova apenas se for exclusivo do projeto e estiver sem releases de rollback |
| AMIs e snapshots | Siga as seções 6.2 e 6.3 |
| Snapshot de backup do perfil | Preserve até validar recuperação, mensagens e reboot |
| Elastic IP | Desassocie e libere somente após conferir os IDs |
| DNS e Budget | Remova manualmente somente se não forem compartilhados ou úteis |

Para listar os artefatos sem removê-los:

```powershell
aws s3api list-objects-v2 `
  --bucket $ArtifactBucket `
  --prefix "$StackName/releases/" `
  --query "Contents[].{Key:Key,Modified:LastModified,Size:Size}" `
  --output table `
  --region $AwsRegion `
  --profile $AwsProfile
```

Para remover uma única release já confirmada:

```powershell
$ArtifactKeyToDelete = "whatsapp-notify/releases/<versao-confirmada>/whatsapp-notify.zip"

aws s3api head-object `
  --bucket $ArtifactBucket `
  --key $ArtifactKeyToDelete `
  --region $AwsRegion `
  --profile $AwsProfile

aws s3api delete-object `
  --bucket $ArtifactBucket `
  --key $ArtifactKeyToDelete `
  --region $AwsRegion `
  --profile $AwsProfile
```

Não use remoção recursiva em bucket compartilhado. Para excluir o bucket
inteiro, confira antes o conteúdo e o versionamento. Buckets com versionamento
`Enabled` ou `Suspended` exigem também a remoção das versões e delete markers.

Antes de remover recursos, confirme que eles não são utilizados pela stack do
`loto-bot`, pela stack baseada em AMI ou por uma release de rollback.
