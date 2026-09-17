# Migração do `whatsapp-notify` para AWS

Este guia corresponde ao [`template.yaml`](../template.yaml) vigente. O serviço usa uma única instância EC2 para preservar a sessão do WhatsApp Web e é acessível somente pelo `loto-bot` dentro da VPC.

## Arquitetura e segurança

Fluxo: `loto-bot` EC2 → HTTP privado porta 80 → Nginx → Uvicorn em `127.0.0.1:8000` → Playwright/WhatsApp Web.

- não há API Gateway, load balancer ou URL pública da aplicação;
- o Security Group aceita porta 80 somente do Security Group do `loto-bot`;
- não há `X-API-Key`, `API_AUTH_TOKEN`, `INTEGRATION_API_TOKEN` ou segredo compartilhado;
- SSM Session Manager é usado para administração, sem SSH;
- a instância precisa de saída HTTPS para AWS e WhatsApp Web e saída HTTP para instalação de pacotes;
- o output `PublicIp` é apenas informativo e não autoriza entrada pública.

O isolamento de rede substitui a autenticação por cabeçalho. Não compartilhe o Security Group do `loto-bot` com cargas não confiáveis e nunca abra a porta 80 para `0.0.0.0/0`.

## Pré-requisitos

- AWS CLI e SAM CLI;
- Python 3.12 para testes locais;
- VPC e subnet com DNS e saída para internet;
- um Security Group de integração independente, criado antes das stacks EC2;
- bucket S3 privado para o artefato;
- AMI Ubuntu compatível com os comandos de bootstrap e Python 3.12;
- mesma região e VPC do `loto-bot`.

```powershell
$AwsProfile = "<perfil>"
$AwsRegion = "sa-east-1"
$StackName = "whatsapp-notify"
$VpcId = "<vpc-id>"
$SubnetId = "<subnet-id>"
$AmiId = "<ami-ubuntu-compativel-com-python-3.12>"
$ArtifactBucket = "<bucket-privado>"
$Version = "0.1.0"
```

## Criar ou recuperar o Security Group de integração

Crie este recurso antes do `whatsapp-notify` e do `loto-bot`. Ele fica fora das duas stacks, eliminando dependência de ordem entre elas. O `loto-bot` o anexa à própria EC2 como identidade de origem; o `whatsapp-notify` apenas o referencia na regra de entrada da porta 80.

```powershell
$IntegrationSecurityGroupName = "lotobot-internal-integration"
$IntegrationSecurityGroupId = aws ec2 create-security-group `
  --group-name $IntegrationSecurityGroupName `
  --description "Shared source identity for LotoBot internal integrations" `
  --vpc-id $VpcId `
  --query GroupId --output text `
  --region $AwsRegion --profile $AwsProfile

aws ec2 create-tags `
  --resources $IntegrationSecurityGroupId `
  --tags Key=Application,Value=lotobot Key=Purpose,Value=internal-integration `
  --region $AwsRegion --profile $AwsProfile
```

Não adicione regras de entrada nem anexe esse grupo à EC2 do `whatsapp-notify`. Caso ele já exista, recupere-o pela VPC e pelo nome:

```powershell
$IntegrationSecurityGroupId = aws ec2 describe-security-groups `
  --filters "Name=vpc-id,Values=$VpcId" "Name=group-name,Values=$IntegrationSecurityGroupName" `
  --query "SecurityGroups[0].GroupId" --output text `
  --region $AwsRegion --profile $AwsProfile
```

A consulta deve retornar exatamente um ID `sg-...`. Esse recurso tem ciclo de vida independente: não o exclua enquanto qualquer stack o referenciar.

## Testar, empacotar e publicar

```powershell
.venv\Scripts\python.exe -m pytest
sam validate --lint --template-file template.yaml

$ArtifactKey = "whatsapp-notify/releases/$Version/whatsapp-notify.zip"
$ArtifactFile = Join-Path $PWD "whatsapp-notify-$Version.zip"
git archive --format=zip --output=$ArtifactFile HEAD
$ArtifactSha256 = (Get-FileHash $ArtifactFile -Algorithm SHA256).Hash.ToLowerInvariant()
aws s3 cp $ArtifactFile "s3://$ArtifactBucket/$ArtifactKey" --region $AwsRegion --profile $AwsProfile
```

O ZIP deve extrair `pyproject.toml` e `src/` na raiz. Não inclua `.env`, `.venv`, perfil do navegador ou QR code.

## Deploy

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
    InstanceType=t3.micro `
    IntegrationSecurityGroupId=$IntegrationSecurityGroupId `
    ArtifactBucket=$ArtifactBucket ArtifactKey=$ArtifactKey ArtifactSha256=$ArtifactSha256 `
    RootVolumeSize=16
```

Não use o `parameter_overrides` antigo do `samconfig.toml` se ele mencionar `AllowedCidr`; esse parâmetro não existe no template vigente. Atualize o arquivo local com os parâmetros acima antes de usar apenas `sam deploy`.

O bootstrap instala a aplicação, Chromium, Nginx, serviço systemd e swap. A stack só conclui após o health check local e o `cfn-signal`.

## Configurar o `loto-bot`

```powershell
$WhatsAppNotifyUrl = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue | [0]" `
  --output text --region $AwsRegion --profile $AwsProfile
```

Passe `WhatsAppNotifyUrl=$WhatsAppNotifyUrl` e `IntegrationSecurityGroupId=$IntegrationSecurityGroupId` no deploy do `loto-bot`. O valor da URL usa `http://<private-dns>` sem barra final. Nenhum cabeçalho de autenticação deve ser enviado.

## Validação operacional e autenticação do WhatsApp

```powershell
$InstanceId = aws cloudformation describe-stacks --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" --output text --region $AwsRegion --profile $AwsProfile
aws ssm start-session --target $InstanceId --region $AwsRegion --profile $AwsProfile
```

Na instância:

```bash
sudo systemctl status whatsapp-notify nginx --no-pager
sudo journalctl -u whatsapp-notify -n 100 --no-pager
curl -fsS http://127.0.0.1:8000/whatsapp/session/status
```

Inicie a sessão e obtenha o QR code por meio do `loto-bot` ou de um túnel SSM controlado. O perfil fica em `/opt/whatsapp-notify/data/.whatsapp-profile`. Trate QR code e perfil como credenciais.

## Atualização e rollback

Gere uma chave S3 e SHA-256 novos a cada versão e revise o change set. O User Data só roda na criação da instância; para instalar novo código, substitua a EC2 de forma controlada. A substituição elimina o perfil do navegador armazenado no volume raiz e exige nova autenticação no WhatsApp.

Para rollback, reaplique o artefato anterior e substitua a instância. Não dependa do `PublicIp`, pois ele pode mudar após stop/start.

## Custos

Confira EC2, EBS gp3, IP público, S3, transferência e CloudWatch. `t3.micro` só é gratuita quando a conta e a região ainda atendem às regras vigentes do Free Tier. Configure AWS Budgets e monitore créditos de CPU e uso do volume.

## Checklist

- [ ] Mesma região e VPC do `loto-bot`.
- [ ] Security Group de integração criado antes das stacks e recuperável por nome/VPC.
- [ ] Mesmo `IntegrationSecurityGroupId` informado nos dois deploys.
- [ ] Porta 80 aceita somente esse Security Group.
- [ ] Artefato versionado e SHA-256 conferido.
- [ ] Nenhum segredo ou perfil no ZIP.
- [ ] Nenhuma chave de API configurada.
- [ ] `ApiUrl` privado entregue ao `loto-bot`.
- [ ] Serviços e health check validados via SSM.
- [ ] Processo de nova autenticação previsto para substituições.
- [ ] Orçamento e alertas configurados.
