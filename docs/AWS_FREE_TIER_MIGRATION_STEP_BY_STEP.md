# Migração do `whatsapp-notify` para AWS

Este guia corresponde ao [`template.yaml`](../template.yaml) vigente. O serviço usa uma única instância EC2 para preservar a sessão do WhatsApp Web e é acessível somente pelo `loto-bot` dentro da VPC.

## Arquitetura e segurança

Fluxo: `loto-bot` EC2 → HTTP privado porta 80 → Nginx → Uvicorn em `127.0.0.1:8000` → Playwright/WhatsApp Web.

- não há API Gateway, load balancer ou URL pública da aplicação;
- o Security Group aceita porta 80 somente do Security Group do `loto-bot`;
- não há `X-API-Key`, `API_AUTH_TOKEN`, `INTEGRATION_API_TOKEN` ou segredo compartilhado;
- o acesso local à instância é feito somente por SSH via IPv6, restrito ao IPv6 público `/128` autorizado;
- a instância recebe um IPv6 público para saída HTTPS/HTTP, mas não recebe IPv4 público;
- a comunicação com o `loto-bot` permanece privada por IPv4 dentro da mesma VPC.

O isolamento de rede substitui a autenticação por cabeçalho. Não compartilhe o Security Group do `loto-bot` com cargas não confiáveis e nunca abra a porta 80 para `0.0.0.0/0`.

## Pré-requisitos

- AWS CLI e SAM CLI;
- Python 3.12 para testes locais;
- a VPC e a subnet dual-stack criadas pelo guia do LotoBot, com DNS habilitado e rota `::/0`;
- o Interface VPC Endpoint compartilhado `com.amazonaws.<regiao>.cloudformation`, em estado `available` e com Private DNS habilitado;
- um Security Group de integração independente, criado antes das stacks EC2;
- bucket S3 privado para o artefato;
- AMI Ubuntu compatível com os comandos de bootstrap e Python 3.12;
- EC2 Key Pair existente e respectivo arquivo PEM protegido localmente;
- conectividade IPv6 pública na máquina autorizada a usar SSH;
- mesma região e VPC do `loto-bot`.

```powershell
$AppName = "loto-bot"
$AwsProfile = "<perfil>"
$AwsRegion = "us-east-1"
$RemoteUser = "ubuntu"
$StackName = "whatsapp-notify"
$InstanceType = "t3.micro"
$KeyName = $StackName
$KeyFile = Join-Path $HOME ".ssh\$KeyName.pem"
$KnownHostsFile = Join-Path $HOME ".ssh\$KeyName-known-hosts"
$LocalPublicIpv6 = (curl.exe -6 -fsS https://api64.ipify.org).Trim()
$AllowedSshIpv6Cidr = "$LocalPublicIpv6/128"
$AwsCommon = @("--region", $AwsRegion, "--profile", $AwsProfile)
$AmiId = aws ssm get-parameter --name "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id" --query "Parameter.Value" --output text --region $AwsRegion --profile $AwsProfile
$AccountId = aws sts get-caller-identity --query Account --output text --profile $AwsProfile
$ArtifactBucket = "$StackName-artifacts-$AccountId-$AwsRegion"
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
```

Crie o Key Pair que será associado à EC2 permanente e proteja o arquivo local:

```powershell
aws ec2 create-key-pair `
  --key-name $KeyName `
  --key-type ed25519 `
  --key-format pem `
  --tag-specifications "ResourceType=key-pair,Tags=[{Key=Name,Value=$KeyName},{Key=Application,Value=$AppName}]" `
  --query KeyMaterial --output text @AwsCommon |
  Out-File -FilePath $KeyFile -Encoding ascii

icacls.exe $KeyFile /inheritance:r | Out-Null
icacls.exe $KeyFile /grant:r "$($env:USERNAME):(R)" | Out-Null
```

Se o IPv6 público mudar, atualize `AllowedSshIpv6Cidr` na stack antes de tentar
nova conexão. Nunca use `::/0` para a porta 22.

Valide que a subnet pertence à VPC do `loto-bot`, possui IPv4 e IPv6 e não atribui IPv4 público automaticamente:

```powershell
aws ec2 describe-subnets --subnet-ids $SubnetId `
  --query "Subnets[0].{VpcId:VpcId,Ipv4:CidrBlock,Ipv6:Ipv6CidrBlockAssociationSet[0].Ipv6CidrBlock,MapPublicIp:MapPublicIpOnLaunch}" `
  --output table --region $AwsRegion --profile $AwsProfile
```

## Criar ou recuperar o Security Group de integração

Não adicione regras de entrada nem anexe esse grupo à EC2 do `whatsapp-notify`. Caso ele já exista, recupere-o pela VPC e pelo nome:

```powershell
$SecurityGroupId = aws ec2 describe-security-groups `
  --filters "Name=vpc-id,Values=$VpcId" "Name=group-name,Values=$AppName" `
  --query "SecurityGroups[0].GroupId" --output text `
  --region $AwsRegion --profile $AwsProfile
```

A consulta deve retornar exatamente um ID `sg-...`. Esse recurso tem ciclo de vida independente: não o exclua enquanto qualquer stack o referenciar.

## Testar, empacotar e publicar

```powershell
.venv\Scripts\python.exe -m pytest
sam validate --lint --template-file template.yaml

aws s3api create-bucket --bucket $ArtifactBucket --region $AwsRegion --profile $AwsProfile
aws s3api put-public-access-block --bucket $ArtifactBucket --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" --region $AwsRegion --profile $AwsProfile
aws s3api put-bucket-encryption --bucket $ArtifactBucket --server-side-encryption-configuration 'Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256}}]' --region $AwsRegion --profile $AwsProfile

$ArtifactVersion = Get-Date -Format "yyyyMMdd-HHmmss"
$ArtifactKey = "$StackName/releases/$ArtifactVersion/$StackName.zip"
$ArtifactFile = Join-Path $env:TEMP "$StackName-$ArtifactVersion.zip"

tar -a -c -f $ArtifactFile pyproject.toml README.md src
tar -tf $ArtifactFile | Sort-Object

$ArtifactSha256 = (Get-FileHash -Algorithm SHA256 $ArtifactFile).Hash.ToLower()

aws s3 cp $ArtifactFile "s3://$ArtifactBucket/$ArtifactKey" --sse AES256 --metadata "sha256=$ArtifactSha256" --region $AwsRegion --profile $AwsProfile
aws s3api head-object --bucket $ArtifactBucket --key $ArtifactKey --region $AwsRegion --profile $AwsProfile
```

O ZIP deve extrair `pyproject.toml` e `src/` na raiz. Não inclua `.env`, `.venv`, perfil do navegador ou QR code.

## Deploy

Antes do deploy, execute a validação do endpoint CloudFormation com
`loto-bot/scripts/test-shared-cloudformation-endpoint.ps1` usando o mesmo
perfil, região e VPC. O `cfn-signal` depende dele.

```powershell
sam deploy `
  --template-file template.yaml `
  --stack-name $StackName `
  --resolve-s3 `
  --capabilities CAPABILITY_IAM `
  --region $AwsRegion `
  --profile $AwsProfile `
  --parameter-overrides `
    VpcId=$VpcId SubnetId=$SubnetId AmiId=$AmiId `
    InstanceType=$InstanceType `
    KeyName=$KeyName AllowedSshIpv6Cidr=$AllowedSshIpv6Cidr `
    IntegrationSecurityGroupId=$SecurityGroupId `
    ArtifactBucket=$ArtifactBucket ArtifactKey=$ArtifactKey ArtifactSha256=$ArtifactSha256 `
    RootVolumeSize=16
```

Não use o `parameter_overrides` antigo do `samconfig.toml` se ele mencionar `AllowedCidr`; esse parâmetro não existe no template vigente. Atualize o arquivo local com os parâmetros acima antes de usar apenas `sam deploy`.

O bootstrap aguarda por até 120 segundos até que a instância tenha um endereço
IPv6 global e uma rota IPv6 default. Em seguida, instala a aplicação, Chromium,
Nginx, OpenSSH Server, serviço systemd e swap. O pacote `aws-cfn-bootstrap` é
baixado pelo endpoint regional S3 dual-stack
`s3.dualstack.<regiao>.amazonaws.com`, sem depender de NAT ou IPv4 público. A
stack só conclui após o health check local e o `cfn-signal`.

O `cfn-signal` acessa o hostname regional padrão do CloudFormation pelo
Interface VPC Endpoint criado no procedimento do `loto-bot`. A variável
`AWS_USE_DUALSTACK_ENDPOINT` não torna esse endpoint público acessível por IPv6;
o Private DNS precisa estar habilitado para resolver o hostname para o IPv4
privado do endpoint.

O template atribui exatamente um IPv6 à instância, usa regras de egress IPv6 e
habilita endpoints AWS dual-stack no bootstrap; não adicione rota IPv4 pública
nem habilite `MapPublicIpOnLaunch`.

Se o evento de criação da EC2 terminar por timeout e o log contiver
`ConnectTimeoutError` para `s3.amazonaws.com` ou `cfn-signal: No such file or
directory`, a instância foi criada com uma versão anterior do template. Confirme
que o change set usa o endpoint `s3.dualstack` e substitua a instância. Verifique
o bootstrap por SSH com:

```bash
sudo cloud-init status --long
sudo tail -n 200 /var/log/whatsapp-notify-bootstrap.log
ip -6 addr show scope global
ip -6 route show default
```

Se a aplicação estiver ativa e o log terminar com `Unknown error signaling
ApplicationInstance`, confirme o endpoint privado antes de repetir o deploy:

```powershell
aws ec2 describe-vpc-endpoints `
  --filters "Name=vpc-id,Values=$VpcId" `
            "Name=service-name,Values=com.amazonaws.$AwsRegion.cloudformation" `
  --query "VpcEndpoints[0].{State:State,PrivateDns:PrivateDnsEnabled,SubnetIds:SubnetIds}" `
  --output table --region $AwsRegion --profile $AwsProfile
```

Uma stack que já alcançou `CREATE_FAILED` não é recuperada apenas repetindo o
sinal. Como o deploy foi feito com `--disable-rollback`, remova ou reverta a
stack com falha conforme seu estado e faça um novo deploy depois que o endpoint
estiver `available`.

## Configurar o `loto-bot`

```powershell
$WhatsAppNotifyUrl = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue | [0]" `
  --output text --region $AwsRegion --profile $AwsProfile
```

Passe `WhatsAppNotifyUrl=$WhatsAppNotifyUrl` e `IntegrationSecurityGroupId=$SecurityGroupId` no deploy do `loto-bot`. O valor da URL usa `http://<private-dns>` sem barra final. Nenhum cabeçalho de autenticação deve ser enviado.

## Validação operacional e autenticação do WhatsApp

```powershell
$InstanceId = aws cloudformation describe-stack-resource --stack-name $StackName --logical-resource-id ApplicationInstance --query "StackResourceDetail.PhysicalResourceId" --output text --region $AwsRegion --profile $AwsProfile
```

Obtenha o IPv6 atual e conecte-se por SSH:

```powershell
$InstanceIpv6 = aws ec2 describe-instances `
  --instance-ids $InstanceId `
  --query "Reservations[0].Instances[0].NetworkInterfaces[0].Ipv6Addresses[0].Ipv6Address" `
  --output text --region $AwsRegion --profile $AwsProfile

ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6"
```

O usuário `ubuntu` corresponde à AMI Canonical Ubuntu usada neste guia. Se outra
AMI for utilizada, confirme seu usuário padrão. O SSH via IPv6 é o único acesso
local à instância e deve permanecer restrito ao `/128` autorizado.

Para validar o ciclo completo da sessão do WhatsApp e baixar o QR code, execute
os comandos abaixo no PowerShell local:

```powershell
$InstanceId = aws cloudformation describe-stack-resource --stack-name $StackName --logical-resource-id ApplicationInstance --query "StackResourceDetail.PhysicalResourceId" --output text --region $AwsRegion --profile $AwsProfile

$InstanceIpv6 = aws ec2 describe-instances `
  --instance-ids $InstanceId `
  --query "Reservations[0].Instances[0].NetworkInterfaces[0].Ipv6Addresses[0].Ipv6Address" `
  --output text --region $AwsRegion --profile $AwsProfile

ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/status'"
ssh -6 -i $KeyFile "$RemoteUser@$InstanceIpv6" "curl -i -sSL 'http://127.0.0.1:8000/whatsapp/session/start?headless=true&timeoutInSeconds=60'"
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

Na instância:

```bash
sudo systemctl status whatsapp-notify nginx --no-pager
sudo journalctl -u whatsapp-notify -n 100 --no-pager
curl -fsS http://127.0.0.1:8000/whatsapp/session/status
```

O serviço criado pelo template inicia pelo comando `whatsapp-notify`, que chama
`configure_logging()` e respeita `LOG_LEVEL` em `/etc/whatsapp-notify.env`.
O bootstrap mantém `LOG_LEVEL=INFO`. Para um diagnóstico temporário, altere
apenas essa variável para `DEBUG`, reinicie o serviço e acompanhe os registros:

```bash
sudo sed -i 's/^LOG_LEVEL=.*/LOG_LEVEL=DEBUG/' /etc/whatsapp-notify.env
sudo systemctl restart whatsapp-notify
sudo journalctl -u whatsapp-notify -f --full -o short-iso-precise
```

Depois, volte para `INFO` e reinicie o serviço. O reinício interrompe a sessão
em andamento; logs DEBUG podem conter dados da sessão e de mensagens. Revise e
oculte informações sensíveis antes de compartilhá-los.

Na EC2 já criada com a unidade antiga, `LOG_LEVEL=DEBUG` sozinho não ativa os
logs da aplicação. Após encerrar a sessão em andamento, execute
`sudo systemctl edit whatsapp-notify` e salve o override abaixo:

```ini
[Service]
ExecStart=
ExecStart=/opt/whatsapp-notify/app/.venv/bin/whatsapp-notify
```

Em seguida, execute `sudo systemctl daemon-reload`,
`sudo systemctl restart whatsapp-notify` e `sudo systemctl cat whatsapp-notify`
para confirmar o comando efetivo. O override corrige a instância atual; mudar
o User Data do template não reescreve sua unidade systemd.

Inicie a sessão e obtenha o QR code pelo SSH IPv6. O perfil fica em `/opt/whatsapp-notify/data/.whatsapp-profile`. Trate QR code e perfil como credenciais.

## Atualização e rollback

Gere uma chave S3 e SHA-256 novos a cada versão e revise o change set. O User Data só roda na criação da instância; para instalar novo código, substitua a EC2 de forma controlada. A substituição elimina o perfil do navegador armazenado no volume raiz e exige nova autenticação no WhatsApp.

Adicionar ou trocar `KeyName` também substitui a EC2. Antes de aplicar o change
set, preserve o que for necessário e planeje nova autenticação do WhatsApp.

Para rollback, reaplique o artefato anterior e substitua a instância. Consulte o IPv6 atual com o output `Ipv6LookupCommand`, pois o endereço pode mudar após a substituição.

## Custos

Confira EC2, EBS gp3, transferência IPv6, S3 e CloudWatch. `t3.micro` só é gratuita quando a conta e a região ainda atendem às regras vigentes do Free Tier. Configure AWS Budgets e monitore créditos de CPU e uso do volume.

## Checklist

- [ ] Mesma região e VPC do `loto-bot`.
- [ ] Mesma subnet dual-stack do `loto-bot`, sem IPv4 público automático e com rota `::/0`.
- [ ] VPC Endpoint compartilhado do CloudFormation disponível e com Private DNS habilitado.
- [ ] Key Pair associado à EC2 e PEM protegido localmente.
- [ ] Porta 22 liberada somente para o IPv6 público autorizado com prefixo `/128`.
- [ ] Security Group de integração criado antes das stacks e recuperável por nome/VPC.
- [ ] Mesmo `IntegrationSecurityGroupId` informado nos dois deploys.
- [ ] Porta 80 aceita somente esse Security Group.
- [ ] Artefato versionado e SHA-256 conferido.
- [ ] Nenhum segredo ou perfil no ZIP.
- [ ] Nenhuma chave de API configurada.
- [ ] `ApiUrl` privado entregue ao `loto-bot`.
- [ ] Serviços e health check validados via SSH IPv6 restrito.
- [ ] Processo de nova autenticação previsto para substituições.
- [ ] Orçamento e alertas configurados.
