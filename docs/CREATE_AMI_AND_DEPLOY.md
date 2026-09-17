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
- acesso à instância pelo Systems Manager;
- os valores de `$VpcId`, `$SubnetId`, `$InstanceType` e
  `$IntegrationSecurityGroupId` usados no guia principal.

Valores entre `<` e `>` precisam ser substituídos. Antes de executar um comando
que altera recursos, confira o perfil, a região, o ID da instância e o ID da AMI.

## 1. Identificar a instância de construção

No PowerShell:

```powershell
$StackName = "whatsapp-notify"
$AwsRegion = "sa-east-1"
$AwsProfile = "<perfil-aws>"
$ImageName = "whatsapp-notify-release-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

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

No computador Windows, abra uma sessão:

```powershell
aws ssm start-session `
  --target $InstanceId `
  --region $AwsRegion `
  --profile $AwsProfile
```

Quando o prompt da EC2 aparecer, execute o bloco Bash abaixo. Ele para a
aplicação, impede inicialização prematura nas cópias e remove dados que não
devem ser clonados:

```bash
sudo systemctl stop whatsapp-notify
sudo systemctl disable whatsapp-notify nginx
sudo find /opt/whatsapp-notify/data/.whatsapp-profile -mindepth 1 -delete
sudo rm -f /root/.bash_history /home/*/.bash_history
sudo find /root /home /opt/whatsapp-notify -type f \
  \( -name '.env' -o -name '*.pem' -o -name '*.key' \) -delete
sudo sync
exit
```

Não remova `/etc/whatsapp-notify.env`, pois o template original cria esse
arquivo apenas com valores não secretos. Revise-o antes de criar a imagem caso
tenha sido alterado manualmente.

> A limpeza do perfil encerra a sessão do WhatsApp nas futuras instâncias. Não
> grave uma sessão autenticada na AMI: qualquer instância criada a partir dela
> receberia uma cópia dessas credenciais.

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
  --tag-specifications "ResourceType=image,Tags=[{Key=Application,Value=whatsapp-notify},{Key=Name,Value=$ImageName}]" `
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
aws ssm send-command `
  --instance-ids $InstanceId `
  --document-name "AWS-RunShellScript" `
  --parameters 'commands=["sudo systemctl enable --now nginx whatsapp-notify"]' `
  --region $AwsRegion `
  --profile $AwsProfile
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
$AmiStackName = "whatsapp-notify-ami"

sam deploy `
  --template-file template-ami.yaml `
  --stack-name $AmiStackName `
  --region $AwsRegion `
  --profile $AwsProfile `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides `
    VpcId=$VpcId `
    SubnetId=$SubnetId `
    AmiId=$AmiId `
    InstanceType=$InstanceType `
    IntegrationSecurityGroupId=$IntegrationSecurityGroupId `
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
  --stack-name $AmiStackName `
  --region $AwsRegion `
  --profile $AwsProfile

aws cloudformation describe-stacks `
  --stack-name $AmiStackName `
  --query "Stacks[0].Outputs" `
  --output table `
  --region $AwsRegion `
  --profile $AwsProfile
```

O deploy está pronto para homologação quando a stack estiver em
`CREATE_COMPLETE` e os outputs `InstanceId` e `ApiUrl` tiverem sido criados.
Teste primeiro por Session Manager e confirme, a partir do `loto-bot`, que o
DNS privado responde por HTTP na porta 80. Não envie chave de API: a autorização
é feita pela referência ao Security Group consumidor.

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
  --stack-name $AmiStackName `
  --region $AwsRegion `
  --profile $AwsProfile `
  --capabilities CAPABILITY_IAM `
  --confirm-changeset `
  --parameter-overrides `
    VpcId=$VpcId `
    SubnetId=$SubnetId `
    AmiId=$PreviousAmiId `
    InstanceType=$InstanceType `
    IntegrationSecurityGroupId=$IntegrationSecurityGroupId `
    RootVolumeSize=16
```

Confirme no change set que `ApplicationInstance` será substituída. Aguarde
`UPDATE_COMPLETE`, conecte pelo Session Manager e execute o smoke test do guia
principal. Se não restaurar um backup do perfil, autentique o WhatsApp
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
  --prefix "whatsapp-notify/releases/" `
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
