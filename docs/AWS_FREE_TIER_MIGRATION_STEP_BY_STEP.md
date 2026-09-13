# Passo a passo para migrar o `whatsapp-notify` para o AWS Free Tier

Este roteiro foi elaborado a partir da lógica e da documentação atuais do
`whatsapp-notify` e usa como referência estrutural o guia
`AWS_SAM_MIGRATION_STEP_BY_STEP.md` do projeto `gmail-reader-aws`.

O projeto de referência pode usar Lambda porque cada requisição é independente.
O `whatsapp-notify`, por outro lado, mantém um processo Chromium aberto, estado
em memória e um perfil persistente em disco entre várias chamadas HTTP. Por
isso, a arquitetura recomendada é uma única instância EC2.

O AWS SAM será usado para gerenciar a stack inteira. Um template SAM aceita
todos os recursos nativos do CloudFormation, portanto pode provisionar EC2,
EBS, Security Group, IAM e Systems Manager mesmo sem criar funções Lambda. O
runtime da aplicação continua na EC2; o SAM atua como ferramenta de
infraestrutura como código, implantação, atualização e remoção.

## Como usar este guia

Este documento contém o primeiro provisionamento e também procedimentos de
operação. Para uma primeira implantação, siga esta ordem:

| Fase | Seções | Resultado esperado |
| --- | --- | --- |
| Entender e preparar | 1 a 6 | Arquitetura compreendida, ferramentas instaladas e custos avaliados |
| Preparar os parâmetros | 7 | VPC, subnet, AMI Ubuntu, tipo EC2, CIDR e artefato definidos |
| Criar a primeira instância | 8 a 11 | Stack criada com `template.yaml` e aplicação instalada |
| Testar sem exposição pública | 12 e 13 | API acessível somente pelo túnel do Session Manager |
| Criar a AMI da aplicação | 11.1 | Release testada e registrada em uma AMI imutável |
| Operar com a AMI | `CREATE_AMI_AND_DEPLOY.md` | Nova stack criada com `template-ami.yaml` |
| Produção e manutenção | 14 a 31 | HTTPS, segurança, backup, atualização e remoção planejados |

As seções 19 a 23 são referências para manutenção ou diagnóstico. Elas não
precisam ser repetidas depois de cada deploy bem-sucedido.

### Dois templates, duas finalidades

| Arquivo | Quando usar | O que acontece no primeiro boot |
| --- | --- | --- |
| `template.yaml` | Primeira instalação ou construção de uma nova release | Instala dependências, baixa o ZIP do S3, configura e inicia a aplicação |
| `template-ami.yaml` | Implantar uma AMI já preparada e testada | Valida o conteúdo da AMI e inicia os serviços; não baixa nem reinstala a aplicação |

Neste guia:

- blocos marcados como `powershell` são executados no computador Windows;
- blocos marcados como `bash` são executados dentro da EC2, por uma sessão SSM;
- valores entre `<` e `>` são exemplos que precisam ser substituídos;
- comandos `aws` não mostram confirmação antes de alterar recursos: confira
  perfil, região, stack e IDs antes de executá-los.

> **Atenção:** criar uma stack, uma instância, volumes ou snapshots pode gerar
> cobrança. O Free Tier e créditos reduzem custos, mas não funcionam como um
> limite automático de gastos.

> **Importante (validado em 11/09/2026):** "AWS Free Tier" não significa que
> uma EC2 seja gratuita indefinidamente. Para contas abertas a partir de
> 15/07/2025, a AWS concede USD 100 ao abrir a conta e permite ganhar até mais
> USD 100 em atividades elegíveis. O **Free Plan** termina após 6 meses ou
> quando os créditos acabarem, o que ocorrer primeiro; os créditos ganhos
> expiram 12 meses após a abertura da conta. Confira no console os valores e as
> datas efetivamente aplicáveis à sua conta antes de criar recursos.

## 1. Resumo da análise do projeto

### 1.1 Fluxos que precisam ser preservados

| Método | Rota | Estado necessário |
| --- | --- | --- |
| `GET` | `/whatsapp/session/start` | Cria Playwright, contexto persistente e página |
| `GET` | `/whatsapp/session/qrcode` | Usa a página já aberta e retorna PNG |
| `GET` | `/whatsapp/session/status` | Consulta a sessão mantida em memória |
| `POST` | `/whatsapp/messages/send` | Usa o mesmo navegador autenticado |
| `GET` | `/whatsapp/session/stop` | Fecha página, contexto e Playwright |

O singleton `notification_handler` mantém uma instância de
`WhatsAppSessionService`. Ela mantém `PersistentWhatsAppSession`, que, por sua
vez, mantém `_playwright`, `_context` e `_page`. Um `asyncio.Lock` serializa
operações no processo. O perfil do Chromium fica em `WHATSAPP_PROFILE_DIR`.

### 1.2 Requisitos derivados da implementação

- um processo de aplicação de longa duração;
- exatamente um worker por perfil do WhatsApp;
- Chromium e bibliotecas Linux instalados;
- pelo menos 1 GiB de memória, com swap para reduzir risco de OOM;
- disco persistente para `.whatsapp-profile`;
- saída HTTPS para `web.whatsapp.com` e serviços relacionados;
- reinício automático da API após reboot ou falha;
- acesso ao QR Code durante a primeira autenticação;
- nenhuma substituição automática ou balanceamento entre instâncias.
- AWS CLI v2 instalado pelo pacote oficial, pois o Ubuntu 24.04 não oferece
  `awscli` nos repositórios APT padrão;
- `aws-cfn-bootstrap` instalado em ambiente virtual próprio para que
  `cfn-signal` conclua a `CreationPolicy` da instância.

### 1.3 Papel de cada serviço

| Opção | Decisão | Motivo |
| --- | --- | --- |
| AWS SAM/CloudFormation | **Usar** | Gerencia declarativamente toda a infraestrutura da aplicação |
| Lambda + API Gateway | Não usar como runtime | Ambiente efêmero, sem afinidade entre chamadas, limite de 15 minutos e HTTP API com integração de até 30 segundos |
| Lambda com imagem | Não usar | A imagem resolve empacotamento, mas não persistência do processo nem roteamento para o mesmo ambiente |
| ECS/Fargate | Não usar no Free Tier | Executa contêiner longo, mas cobra CPU/memória continuamente e exige persistência externa |
| App Runner | Não usar no Free Tier | Pode reiniciar/escalar instâncias e cobra capacidade provisionada |
| EC2 única | **Recomendado** | Preserva processo, memória, disco e navegador; é a alternativa mais simples e econômica |

### 1.4 Por que EC2, e quando considerar Lightsail

Para a migração durante o Free Tier, use EC2: os tipos marcados como elegíveis
podem consumir os créditos da conta nova, a instância aceita IAM/SSM e toda a
configuração pode ser reproduzida por CloudFormation. Isso não transforma o
tipo escolhido em uma franquia mensal permanente.

Depois dos créditos, compare o custo total da EC2 (compute, EBS, IPv4 público
e eventual tráfego) com o Amazon Lightsail. O Lightsail inclui compute, SSD,
transferência e endereçamento em um preço mensal; na tabela pública consultada
em 11/09/2026, os bundles Linux com IPv4 custavam USD 7/mês com 1 GiB e USD
12/mês com 2 GiB. Ele pode ser mais barato depois do Free Tier, mas exigiria um
roteiro/IaC diferente e oferece integração administrativa menos direta que a
role EC2 + Session Manager usada aqui.

Esta decisão significa que `template.yaml` faz parte da migração, mas não cria
handler Lambda, Mangum ou Lambda Web Adapter.

## 2. Arquitetura alvo

```text
Cliente autorizado
       |
       | HTTPS 443 (ou túnel SSM durante homologação)
       v
Stack AWS SAM/CloudFormation
`-- EC2 Ubuntu, uma única instância
|-- Nginx: TLS, limite de corpo e proxy reverso
|-- systemd: reinício e inicialização automática
|-- Uvicorn/FastAPI: um processo e um worker
|-- Playwright + Chromium headless
`-- EBS gp3 criptografado
    `-- /opt/whatsapp-notify/data/.whatsapp-profile

Saída TCP 443 -> WhatsApp Web, repositórios de pacotes e serviços AWS
Operação -> AWS Systems Manager Session Manager
Métricas básicas -> CloudWatch/EC2
```

Para homologação, prefira Session Manager com encaminhamento de porta e não
publique a API. Para uso remoto contínuo, use Nginx com HTTPS e restrinja a
origem no Security Group. A instância ainda precisa de saída para a internet;
sem IPv4 público seria necessário garantir conectividade IPv6 ponta a ponta ou
pagar NAT/VPC endpoints. Não adicione NAT Gateway, Application Load Balancer
ou banco de dados: todos aumentariam o custo sem resolver uma necessidade atual.

## 3. Estrutura do projeto de infraestrutura

Use o diretório informado para a infraestrutura:

```text
$YourDir\whatsapp-notify\
|-- docs\
|   |-- AWS_FREE_TIER_MIGRATION_STEP_BY_STEP.md
|   `-- CREATE_AMI_AND_DEPLOY.md
|-- dist\
|   `-- whatsapp-notify-<versao>.zip
|-- samconfig.local.toml
|-- template.yaml
`-- template-ami.yaml
```

O código-fonte da aplicação permanece em:

```text
$YourDir\whatsapp-notify
```

Empacote somente os arquivos necessários para instalar e executar a aplicação.
Não compacte o diretório inteiro para depois tentar excluir todos os arquivos
indesejados: novos diretórios locais poderiam entrar no artefato sem que você
percebesse. Envie o ZIP para um bucket S3 privado e permita que apenas a role da
EC2 leia o prefixo de releases desse projeto.

```text
projeto local -> ZIP versionado -> S3 privado -> EC2
```

O artefato de produção contém somente `pyproject.toml`, `README.md` e `src/`.
O `README.md` é necessário porque está declarado como metadata do pacote em
`pyproject.toml`. Não inclua `.env`, `.whatsapp-profile`, logs, caches, testes,
documentação operacional, templates de infraestrutura ou credenciais. O
download usa a instance role; não coloque access keys, URL pré-assinada ou
token no template, no `UserData` ou no ZIP.

## 4. Instalar e validar as ferramentas

No Windows/PowerShell:

```powershell
$AwsProfile = "<perfil-aws>"
$AwsRegion = "us-east-1"
$StackName = "whatsapp-notify"

python --version
aws --version
sam --version
docker --version
aws sts get-caller-identity --profile $AwsProfile
```

Requisitos:

- AWS CLI v2;
- AWS SAM CLI;
- credenciais configuradas;
- permissão para CloudFormation, EC2, IAM e SSM;
- ferramenta `tar` disponível no Windows;
- Docker Desktop apenas se futuramente houver builds SAM em contêiner. O
  template EC2 abaixo não precisa de Docker para `sam build`.

## 5. Entender a modalidade do Free Tier

Em 11/09/2026 há dois cenários:

1. Contas criadas antes de 15 de julho de 2025 seguem as condições legadas,
   mas seu benefício inicial de 12 meses já expirou. Trate EC2, EBS e IPv4 como
   pagos, salvo se o painel mostrar outro crédito promocional válido.
2. Contas criadas a partir de 15 de julho de 2025 usam o novo programa baseado
   em créditos. O Free Plan dura até 6 meses ou até os créditos acabarem; os
   recursos ficam inacessíveis quando a conta é fechada ao fim do plano se ela
   não migrar para Paid Plan. Não use a retenção temporária como backup.

Antes de provisionar:

```powershell
$AwsProfile = "<perfil-aws>"
$AwsRegion = "us-east-1"

aws sts get-caller-identity --profile $AwsProfile
aws configure get region --profile $AwsProfile
aws freetier get-account-plan-state --profile $AwsProfile
aws freetier get-free-tier-usage --profile $AwsProfile
```

No console AWS:

1. Abra **Billing and Cost Management > Free Tier**.
2. Confirme o plano, saldo de créditos e data de expiração.
3. Confirme quais tipos a API marca como `free-tier-eligible` na região.
4. Se desejar alertas de custo, crie um AWS Budget separadamente antes da instância.

```powershell
aws ec2 describe-instance-types `
  --filters "Name=free-tier-eligible,Values=true" `
  --query "InstanceTypes[].{Type:InstanceType,Architecture:ProcessorInfo.SupportedArchitectures,MemoryMiB:MemoryInfo.SizeInMiB}" `
  --output table `
  --region $AwsRegion `
  --profile $AwsProfile
```

Não fixe um tipo apenas porque ele já foi elegível no passado. Para este
workload, use a menor opção elegível com **2 GiB de RAM** se houver. Se somente
uma instância de 1 GiB for elegível, comece com ela e configure swap.

### Dimensionamento inicial

| Opção | Uso |
| --- | --- |
| `t3.micro` x86, 1 GiB | Ponto de partida de menor custo deste roteiro; requer swap e teste de carga |
| `t3.small` x86, 2 GiB | Preferível se o Chromium sofrer OOM/swap; consome créditos mais rápido |
| `t4g.micro`/`t4g.small` Arm64 | Pode custar menos, mas exige AMI e validação ponta a ponta Arm64; não use com o template x86 abaixo |
| `c7i-flex.large`/`m7i-flex.large` | Podem aparecer como elegíveis em contas novas, mas são superdimensionadas e queimam créditos mais rápido |

Este roteiro limita o template a `t3.micro` e `t3.small`. Use modo de créditos
de CPU `standard` nessas instâncias. `unlimited` pode gerar cobrança de
créditos excedentes em uso sustentado.

## 6. Configurar proteção de custo fora da stack

O `template.yaml` e o `template-ami.yaml` não criam nem gerenciam AWS Budgets.
Se desejar essa proteção adicional, crie manualmente um budget mensal pequeno,
por exemplo USD 5, para detectar qualquer uso
inesperado, com alertas em 50%, 80% e 100%. O budget alerta, mas não interrompe
recursos automaticamente, e créditos podem fazer a fatura líquida diferir do
custo de uso mostrado. Acompanhe também o saldo de créditos.

No console:

1. Acesse **Billing and Cost Management > Budgets**.
2. Crie **Cost budget** mensal de USD 5.
3. Informe um e-mail monitorado.
4. Adicione alertas em USD 2,50, USD 4 e USD 5.

Ative também os alertas de uso do Free Tier em **Billing preferences**. Um
budget não é um teto rígido. Se precisar de corte automático, crie uma ação de
Budget específica para parar a instância, depois de testar permissões e o risco
de interromper uma mensagem em andamento.

Custos que exigem atenção:

- IPv4 público, inclusive quando associado à instância;
- EBS acima da franquia/créditos e snapshots;
- tráfego de saída para a internet;
- métricas detalhadas e logs do CloudWatch;
- CPU excedente em instâncias T no modo `unlimited`;
- instância esquecida ligada após o fim do Free Tier.

## 7. Descobrir VPC, subnet, AMI Ubuntu inicial e tipo elegível

O template recebe VPC, subnet, AMI e tipo como parâmetros para não assumir
valores que mudam por conta e região.

Liste a VPC padrão e uma subnet pública:

```powershell
$VpcId = aws ec2 describe-vpcs `
  --filters "Name=is-default,Values=true" `
  --query "Vpcs[0].VpcId" `
  --output text `
  --region $AwsRegion `
  --profile $AwsProfile

$SubnetId = aws ec2 describe-subnets `
  --filters "Name=vpc-id,Values=$VpcId" `
            "Name=map-public-ip-on-launch,Values=true" `
  --query "Subnets[0].SubnetId" `
  --output text `
  --region $AwsRegion `
  --profile $AwsProfile
```

Para criar a primeira instância, obtenha a AMI Ubuntu Server 24.04 LTS x86_64
publicada pela Canonical. Esta é apenas a imagem inicial do sistema operacional,
informada ao `template.yaml`; ela ainda não contém o `whatsapp-notify`:

```powershell
$AmiId = aws ssm get-parameter `
  --name "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id" `
  --query "Parameter.Value" `
  --output text `
  --region $AwsRegion `
  --profile $AwsProfile
```

Não selecione `t4g.*` com essa AMI `amd64`. Para testar Graviton, crie uma
variante separada com AMI `arm64`, ajuste os tipos permitidos no template e
execute os testes mais um smoke test real do Playwright/Chromium.

Confirme no painel **Billing > Free Tier** qual tipo é elegível. Depois verifique
se ele existe na região:

```powershell
$InstanceType = "t3.micro"

aws ec2 describe-instance-type-offerings `
  --location-type region `
  --filters "Name=instance-type,Values=$InstanceType" `
  --region $AwsRegion `
  --profile $AwsProfile
```

Obtenha o IPv4 público do cliente que poderá acessar a API:

```powershell
$AllowedCidr = ((Invoke-RestMethod https://checkip.amazonaws.com).Trim()) + "/32"
```

Para homologar somente por Session Manager, informe `0.0.0.0/32`; essa rede não
autoriza nenhum host real. Nunca use `0.0.0.0/0` para a API atual.

### 7.1 Criar o bucket privado e empacotar o código local

Crie uma vez um bucket de artefatos na mesma região. O nome de bucket é global,
por isso o exemplo inclui o ID da conta:

```powershell
$AccountId = aws sts get-caller-identity `
  --query Account `
  --output text `
  --profile $AwsProfile

$ArtifactBucket = "whatsapp-notify-artifacts-$AccountId-$AwsRegion"

aws s3api create-bucket `
  --bucket $ArtifactBucket `
  --region $AwsRegion `
  --profile $AwsProfile

aws s3api put-public-access-block `
  --bucket $ArtifactBucket `
  --public-access-block-configuration `
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" `
  --region $AwsRegion `
  --profile $AwsProfile

aws s3api put-bucket-encryption `
  --bucket $ArtifactBucket `
  --server-side-encryption-configuration 'Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256}}]' `
  --region $AwsRegion `
  --profile $AwsProfile
```

O comando `create-bucket` acima é próprio para `us-east-1`. Se escolher outra
região, acrescente
`--create-bucket-configuration LocationConstraint=$AwsRegion`.

Empacote a aplicação a partir da raiz do projeto. O comando usa uma lista
explícita de entradas: apenas `pyproject.toml`, `README.md` e `src` podem entrar.
As exclusões adicionais protegem contra caches, metadata de builds anteriores e
um perfil do navegador criado acidentalmente dentro de `src`. O ZIP é criado
fora da árvore para não incluir a si próprio:

```powershell
$ArtifactVersion = Get-Date -Format "yyyyMMdd-HHmmss"
$ArtifactKey = "whatsapp-notify/releases/$ArtifactVersion/whatsapp-notify.zip"
$ArtifactPath = Join-Path $env:TEMP "whatsapp-notify-$ArtifactVersion.zip"

tar -a -c -f $ArtifactPath `
  --exclude='*/__pycache__' `
  --exclude='*/__pycache__/*' `
  --exclude='*.py[cod]' `
  --exclude='*.egg-info' `
  --exclude='*.egg-info/*' `
  --exclude='*/.whatsapp-profile' `
  --exclude='*/.whatsapp-profile/*' `
  pyproject.toml README.md src

if ($LASTEXITCODE -ne 0) {
  throw "Falha ao criar o artefato ZIP."
}

tar -tf $ArtifactPath | Sort-Object

if ($LASTEXITCODE -ne 0) {
  throw "Falha ao listar o conteúdo do artefato ZIP."
}

$ArtifactSha256 = (Get-FileHash -Algorithm SHA256 $ArtifactPath).Hash.ToLower()
```

Antes do upload, revise a saída de `tar -tf`. Ela deve mostrar apenas os dois
arquivos da raiz e arquivos Python dentro de `src/`. Se aparecer `.env`,
`.whatsapp-profile`, `__pycache__`, `*.egg-info`, `tests`, `docs`, `RF`,
`.aws-sam`, `samconfig`, `template*.yaml` ou qualquer arquivo desconhecido,
apague o ZIP local, corrija o comando e gere o artefato novamente.

Depois da conferência, envie o ZIP e consulte o objeto criado:

```powershell
aws s3 cp $ArtifactPath "s3://$ArtifactBucket/$ArtifactKey" `
  --sse AES256 `
  --metadata "sha256=$ArtifactSha256" `
  --region $AwsRegion `
  --profile $AwsProfile

aws s3api head-object `
  --bucket $ArtifactBucket `
  --key $ArtifactKey `
  --region $AwsRegion `
  --profile $AwsProfile
```

Não habilite acesso público. SSE-S3 não tem custo de chave KMS e é suficiente
para este artefato sem segredos. S3 cobra armazenamento e requisições; mantenha
somente as versões necessárias para rollback. CloudTrail Data Events ou access
logging melhoram a auditoria de downloads, mas também podem gerar custo; avalie
habilitá-los em produção e inclua-os no budget.

## 8. Criar o template SAM

Crie
`$YourDir\whatsapp-notify\template.yaml`:

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31
Description: WhatsApp Notify on one persistent EC2 instance - preserves browser session state

Metadata:
  AWSToolsMetrics:
    AWSAgentToolkit: aws-cloudformation@2
  com.aws.cloudformation.Context:
    ref:
      - at: docs/AWS_FREE_TIER_MIGRATION_STEP_BY_STEP.md
        has: EC2 architecture and bootstrap constraints
        scope: stack

Parameters:
  VpcId:
    Type: AWS::EC2::VPC::Id
  SubnetId:
    Type: AWS::EC2::Subnet::Id
  AmiId:
    Type: AWS::EC2::Image::Id
  InstanceType:
    Type: String
    Default: t3.micro
    AllowedValues:
      - t3.micro
      - t3.small
  AllowedCidr:
    Type: String
    AllowedPattern: ^(\d{1,3}\.){3}\d{1,3}/(3[0-2]|[12]?\d)$
  ArtifactBucket:
    Type: String
    AllowedPattern: ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$
  ArtifactKey:
    Type: String
    AllowedPattern: ^whatsapp-notify/releases/[^\\]+\.zip$
  ArtifactSha256:
    Type: String
    AllowedPattern: ^[a-fA-F0-9]{64}$
  RootVolumeSize:
    Type: Number
    Default: 16
    MinValue: 12
    MaxValue: 30
Resources:
  InstanceRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: ec2.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
      Policies:
        - PolicyName: DownloadApplicationArtifact
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action: s3:GetObject
                Resource: !Sub "arn:${AWS::Partition}:s3:::${ArtifactBucket}/whatsapp-notify/releases/*"
      Tags:
        - Key: Application
          Value: whatsapp-notify

  InstanceProfile:
    Type: AWS::IAM::InstanceProfile
    Properties:
      Roles:
        - !Ref InstanceRole

  ApplicationSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Restricted HTTPS access for WhatsApp Notify
      VpcId: !Ref VpcId
      SecurityGroupIngress:
        - Description: HTTPS from the authorized client
          IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: !Ref AllowedCidr
      SecurityGroupEgress:
        - Description: HTTP outbound for Ubuntu package repositories
          IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0
        - Description: HTTPS outbound
          IpProtocol: tcp
          FromPort: 443
          ToPort: 443
          CidrIp: 0.0.0.0/0
        - Description: DNS UDP
          IpProtocol: udp
          FromPort: 53
          ToPort: 53
          CidrIp: 0.0.0.0/0
        - Description: DNS TCP
          IpProtocol: tcp
          FromPort: 53
          ToPort: 53
          CidrIp: 0.0.0.0/0
      Tags:
        - Key: Application
          Value: whatsapp-notify

  ApplicationInstance:
    Type: AWS::EC2::Instance
    CreationPolicy:
      ResourceSignal:
        Count: 1
        Timeout: PT30M
    Properties:
      ImageId: !Ref AmiId
      InstanceType: !Ref InstanceType
      IamInstanceProfile: !Ref InstanceProfile
      SubnetId: !Ref SubnetId
      SecurityGroupIds:
        - !Ref ApplicationSecurityGroup
      CreditSpecification:
        CPUCredits: standard
      MetadataOptions:
        HttpEndpoint: enabled
        HttpTokens: required
        HttpPutResponseHopLimit: 1
      Monitoring: false
      BlockDeviceMappings:
        - DeviceName: /dev/sda1
          Ebs:
            DeleteOnTermination: true
            Encrypted: true
            VolumeSize: !Ref RootVolumeSize
            VolumeType: gp3
      Tags:
        - Key: Name
          Value: whatsapp-notify
        - Key: Application
          Value: whatsapp-notify
        - Key: Environment
          Value: free-tier
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          set -euo pipefail
          exec > >(tee /var/log/whatsapp-notify-bootstrap.log | logger -t user-data -s 2>/dev/console) 2>&1

          signal_failure() {
            /opt/cfn-bootstrap/bin/cfn-signal --exit-code 1 \
              --stack "${AWS::StackName}" \
              --resource ApplicationInstance \
              --region "${AWS::Region}" || true
          }
          trap signal_failure ERR

          apt-get update
          apt-get install -y curl nginx python3.12 python3.12-venv python3-pip unzip

          python3.12 -m venv /opt/cfn-bootstrap
          /opt/cfn-bootstrap/bin/pip install \
            https://s3.amazonaws.com/cloudformation-examples/aws-cfn-bootstrap-py3-latest.tar.gz

          curl --fail --location --retry 3 \
            https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip \
            --output /tmp/awscliv2.zip
          unzip -q /tmp/awscliv2.zip -d /tmp
          /tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli
          rm -rf /tmp/aws /tmp/awscliv2.zip
          aws --version

          id whatsapp-notify >/dev/null 2>&1 || \
            useradd --system --create-home --home-dir /opt/whatsapp-notify \
              --shell /usr/sbin/nologin whatsapp-notify
          install -d -m 755 -o whatsapp-notify -g whatsapp-notify \
            /opt/whatsapp-notify/app /opt/whatsapp-notify/data
          install -d -m 700 -o whatsapp-notify -g whatsapp-notify \
            /opt/whatsapp-notify/data/.whatsapp-profile

          if [ ! -f /swapfile ]; then
            fallocate -l 2G /swapfile
            chmod 600 /swapfile
            mkswap /swapfile
            swapon /swapfile
            echo '/swapfile none swap sw 0 0' >> /etc/fstab
          fi

          aws s3 cp \
            's3://${ArtifactBucket}/${ArtifactKey}' \
            /tmp/whatsapp-notify.zip
          echo '${ArtifactSha256}  /tmp/whatsapp-notify.zip' | sha256sum -c -
          unzip -q /tmp/whatsapp-notify.zip -d /opt/whatsapp-notify/app
          rm -f /tmp/whatsapp-notify.zip
          chown -R whatsapp-notify:whatsapp-notify /opt/whatsapp-notify/app
          cd /opt/whatsapp-notify/app
          sudo -u whatsapp-notify python3.12 -m venv .venv
          sudo -u whatsapp-notify .venv/bin/python -m pip install --upgrade pip
          sudo -u whatsapp-notify .venv/bin/pip install .
          .venv/bin/playwright install-deps chromium
          sudo -u whatsapp-notify .venv/bin/playwright install chromium

          cat >/etc/whatsapp-notify.env <<'EOF'
          WHATSAPP_TARGET_NAME=
          WHATSAPP_MESSAGE=
          WHATSAPP_HEADLESS=true
          WHATSAPP_PROFILE_DIR=/opt/whatsapp-notify/data/.whatsapp-profile
          WHATSAPP_TIMEOUT_SECONDS=60
          API_HOST=127.0.0.1
          API_PORT=8000
          LOG_LEVEL=INFO
          EOF
          chown root:root /etc/whatsapp-notify.env
          chmod 600 /etc/whatsapp-notify.env

          cat >/etc/systemd/system/whatsapp-notify.service <<'EOF'
          [Unit]
          Description=WhatsApp Notify API
          After=network-online.target
          Wants=network-online.target

          [Service]
          Type=simple
          User=whatsapp-notify
          Group=whatsapp-notify
          WorkingDirectory=/opt/whatsapp-notify/app
          EnvironmentFile=/etc/whatsapp-notify.env
          Environment=PYTHONPATH=/opt/whatsapp-notify/app/src
          ExecStart=/opt/whatsapp-notify/app/.venv/bin/uvicorn api.server:app --host 127.0.0.1 --port 8000 --workers 1
          Restart=on-failure
          RestartSec=5
          TimeoutStopSec=30
          KillSignal=SIGTERM
          NoNewPrivileges=true
          PrivateTmp=true
          ProtectSystem=strict
          ProtectHome=true
          ReadWritePaths=/opt/whatsapp-notify/data

          [Install]
          WantedBy=multi-user.target
          EOF

          cat >/etc/nginx/sites-available/whatsapp-notify <<'EOF'
          server {
              listen 80 default_server;
              server_name _;
              client_max_body_size 64k;
              location / {
                  proxy_pass http://127.0.0.1:8000;
                  proxy_http_version 1.1;
                  proxy_set_header Host $host;
                  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                  proxy_set_header X-Forwarded-Proto $scheme;
                  proxy_connect_timeout 5s;
                  proxy_read_timeout 90s;
                  proxy_send_timeout 90s;
              }
          }
          EOF
          rm -f /etc/nginx/sites-enabled/default
          ln -sf /etc/nginx/sites-available/whatsapp-notify \
            /etc/nginx/sites-enabled/whatsapp-notify

          systemctl daemon-reload
          systemctl enable --now whatsapp-notify
          nginx -t
          systemctl enable --now nginx
          for attempt in {1..20}; do
            if curl --fail --silent --show-error --max-time 5 \
              http://127.0.0.1:8000/whatsapp/session/status; then
              echo "WhatsApp Notify health check succeeded."
              break
            fi

            if [ "$attempt" -eq 20 ]; then
              echo "WhatsApp Notify health check failed after 20 attempts."
              systemctl status whatsapp-notify --no-pager || true
              journalctl -u whatsapp-notify -n 100 --no-pager || true
              exit 1
            fi

            sleep 3
          done

          /opt/cfn-bootstrap/bin/cfn-signal --exit-code 0 \
            --stack "${AWS::StackName}" \
            --resource ApplicationInstance \
            --region "${AWS::Region}"
          trap - ERR

Outputs:
  InstanceId:
    Description: EC2 instance managed by the stack
    Value: !Ref ApplicationInstance
  PublicIp:
    Description: Auto-assigned public IPv4; changes after stop/start
    Value: !GetAtt ApplicationInstance.PublicIp
  SessionManagerCommand:
    Description: Command to open an SSM shell
    Value: !Sub "aws ssm start-session --target ${ApplicationInstance} --region ${AWS::Region}"
```

Observações sobre o template:

- `template.yaml` é o template de inicialização completa e deve ser usado para
  criar a primeira instância ou reconstruir a imagem-base;
- a aplicação é baixada de uma chave S3 privada no primeiro boot;
- a role só pode executar `s3:GetObject` no prefixo privado de releases desse
  projeto, permitindo atualização por novas chaves sem ampliar para o bucket;
- o bootstrap instala apenas os pacotes necessários; faça upgrades de segurança
  em uma janela de manutenção, evitando um upgrade completo imprevisível no
  primeiro deploy;
- no Ubuntu 24.04, o AWS CLI v2 vem do instalador oficial porque `awscli` não
  possui candidato nos repositórios APT padrão;
- `aws-cfn-bootstrap` é instalado antes do AWS CLI para que falhas posteriores
  sejam reportadas imediatamente à `CreationPolicy`;
- `CreationPolicy` só conclui a stack após a API responder localmente;
- o volume raiz guarda o perfil e é criptografado;
- a instância é única e usa um worker;
- a porta 22 não existe no Security Group;
- o Nginx inicialmente escuta porta 80 apenas dentro da instância. O Security
  Group não libera a porta 80; HTTPS será configurado depois;
- `DeleteOnTermination: true` evita EBS órfão, mas exige snapshot antes de
  remover a stack se o perfil precisar ser preservado;
- budgets e alertas de cobrança são administrados separadamente no Billing e
  não pertencem à stack da aplicação.

## 9. Criar a configuração local do SAM

Crie `samconfig.local.toml`:

```toml
version = 0.1

[default.validate.parameters]
lint = true

[default.deploy.parameters]
stack_name = "whatsapp-notify"
region = "us-east-1"
capabilities = "CAPABILITY_IAM"
confirm_changeset = true
```

Copie para `samconfig.toml`, que deve ficar fora do controle de versão:

```powershell
Copy-Item samconfig.local.toml samconfig.toml
```

Acrescente em `[default.deploy.parameters]`:

```toml
profile = "<perfil-aws>"
parameter_overrides = "VpcId=<vpc-id> SubnetId=<subnet-id> AmiId=<ami-id> InstanceType=t3.micro AllowedCidr=<ip/32> ArtifactBucket=<bucket> ArtifactKey=whatsapp-notify/releases/<versao>/whatsapp-notify.zip ArtifactSha256=<sha256> RootVolumeSize=16"
```

Inclua no `.gitignore` do projeto de infraestrutura:

```gitignore
.aws-sam/
samconfig.toml
```

## 10. Validar o template e a aplicação

No projeto da aplicação:

```powershell
Set-Location $YourDir\whatsapp-notify
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest --cov=src --cov-report=term-missing -q
```

No projeto de infraestrutura:

```powershell
Set-Location $YourDir\whatsapp-notify
sam validate --template-file template.yaml `
  --lint --region $AwsRegion --profile $AwsProfile
sam validate --template-file template-ami.yaml `
  --lint --region $AwsRegion --profile $AwsProfile
sam build
```

`sam build` pode informar que não há recursos serverless para construir. Isso é
esperado: a stack usa recursos CloudFormation nativos e o deploy continua sendo
feito pelo SAM.

## 11. Implantar a stack

Primeiro deploy:

```powershell
sam deploy --guided `
  --stack-name $StackName `
  --region $AwsRegion `
  --profile $AwsProfile `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides `
    VpcId=$VpcId `
    SubnetId=$SubnetId `
    AmiId=$AmiId `
    InstanceType=$InstanceType `
    AllowedCidr=$AllowedCidr `
    ArtifactBucket=$ArtifactBucket `
    ArtifactKey=$ArtifactKey `
    ArtifactSha256=$ArtifactSha256 `
    RootVolumeSize=16
```

Nos próximos deploys:

```powershell
sam validate --lint
sam deploy
```

Acompanhe o bootstrap:

```powershell
aws cloudformation describe-events `
  --stack-name $StackName `
  --filters FailedEvents=true `
  --region $AwsRegion `
  --profile $AwsProfile
```

Se `ApplicationInstance` falhar ou o sinal expirar, abra a instância por SSM e
consulte:

```bash
sudo tail -n 300 /var/log/cloud-init-output.log
sudo tail -n 300 /var/log/whatsapp-notify-bootstrap.log
sudo systemctl status cloud-final.service --no-pager
sudo systemctl status whatsapp-notify --no-pager
sudo journalctl -u whatsapp-notify -n 200 --no-pager
```

O health check tenta a conexão até 20 vezes, aguardando três segundos entre
tentativas. Isso evita sinalizar falha apenas porque o `systemctl` terminou antes
de o Uvicorn começar a aceitar conexões. Se todas as tentativas falharem, o
bootstrap grava o estado e as últimas linhas do journal antes de enviar o
`cfn-signal` de falha.

Se o log mostrar uma única conexão recusada seguida pela inicialização normal do
Uvicorn, confirme que a stack foi implantada com a versão atual deste template.
Versões antigas usavam apenas `curl --retry`, que não repetia esse erro local de
conexão.

Se o log contiver `Package 'awscli' has no installation candidate`, a instância
foi criada com uma versão anterior deste template. Não basta reiniciá-la:
o cloud-init normalmente executa o `UserData` somente no primeiro boot.
Atualize a stack com o template corrigido e substitua `ApplicationInstance` (ou
recrie a stack se o primeiro deploy tiver revertido). A ausência de
`/opt/cfn-bootstrap/bin/cfn-signal` e de `whatsapp-notify.service` é consequência
da interrupção prematura do bootstrap, não uma falha independente.

### 11.1 Criar uma AMI imutável da aplicação

O primeiro deploy pode levar vários minutos porque a `CreationPolicy` aguarda o
`cfn-signal` enviado somente depois de instalar pacotes do Ubuntu, AWS CLI,
dependências Python, Playwright e Chromium, configurar os serviços e concluir o
health check. O limite `PT30M` é o tempo máximo de espera, não uma pausa fixa.

Depois de homologar a primeira instância, crie uma AMI privada a partir dela. Uma
instância EC2 não usa diretamente um snapshot como `ImageId`: `create-image`
registra a AMI e cria automaticamente o snapshot EBS associado.

Antes de criar a imagem, pare a aplicação e remova o perfil do WhatsApp,
históricos, chaves e outros segredos. Não grave uma sessão autenticada na AMI,
pois todas as instâncias derivadas receberiam uma cópia das credenciais.

O procedimento completo, incluindo higienização, criação, espera, consulta do
snapshot e descarte da imagem, está em
[`CREATE_AMI_AND_DEPLOY.md`](CREATE_AMI_AND_DEPLOY.md).

Resumo da criação:

```powershell
$InstanceId = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" `
  --output text `
  --region $AwsRegion `
  --profile $AwsProfile

$ImageName = "whatsapp-notify-release-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

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

Para a criação completa, limpeza e implantação dessa AMI, siga
[`CREATE_AMI_AND_DEPLOY.md`](CREATE_AMI_AND_DEPLOY.md). O resumo abaixo serve
somente como referência rápida.

Faça o primeiro teste com outra stack e o template otimizado:

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
    AllowedCidr=$AllowedCidr `
    RootVolumeSize=16
```

O `template-ami.yaml` usa a AMI como uma release imutável: verifica se a
aplicação, a virtualenv e as ferramentas pré-instaladas existem, inicia os
serviços, executa o health check e envia o `cfn-signal`. Ele não baixa o ZIP nem
executa `pip install`. Sua `CreationPolicy` usa `PT10M`. Quando o código ou as
dependências mudarem, atualize e teste a instância de construção e gere uma nova
AMI pelo fluxo completo; não reutilize indefinidamente uma imagem sem
atualizações de segurança.

## 12. Obter os outputs e conectar

```powershell
$InstanceId = aws cloudformation describe-stacks `
  --stack-name $StackName `
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" `
  --output text `
  --region $AwsRegion `
  --profile $AwsProfile

aws ssm start-session `
  --target $InstanceId `
  --region $AwsRegion `
  --profile $AwsProfile
```

## 13. Homologar por túnel SSM

Não publique a API no primeiro teste:

```powershell
aws ssm start-session `
  --target $InstanceId `
  --document-name AWS-StartPortForwardingSession `
  --parameters '{"portNumber":["8000"],"localPortNumber":["8000"]}' `
  --region $AwsRegion `
  --profile $AwsProfile
```

Em outro terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/whatsapp/session/status
Invoke-RestMethod "http://127.0.0.1:8000/whatsapp/session/start?headless=true&timeoutInSecounds=60"
Invoke-WebRequest http://127.0.0.1:8000/whatsapp/session/qrcode `
  -OutFile whatsapp-qr.png
```

Escaneie o QR Code e aguarde `SESSAO_ABERTA`:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/whatsapp/session/status

$Body = @{
  contact = "Grupo Teste"
  message = "Mensagem de homologação"
} | ConvertTo-Json -Compress

# A conversão explícita evita erro de leitura do JSON com acentos no
# Windows PowerShell 5.1. A API espera que o corpo esteja em UTF-8.
$BodyUtf8 = [System.Text.Encoding]::UTF8.GetBytes($Body)

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/whatsapp/messages/send `
  -ContentType "application/json; charset=utf-8" `
  -Body $BodyUtf8
  
Invoke-RestMethod http://127.0.0.1:8000/whatsapp/session/stop
```

## 14. Preparar HTTPS

O template não libera HTTP porque a API não deve trafegar sem TLS. Para usar
Certbot HTTP-01 temporariamente:

1. adicione temporariamente ingress TCP 80 para `0.0.0.0/0`, pois os
   validadores da autoridade certificadora não partem do `AllowedCidr` do
   consumidor;
2. execute Certbot;
3. remova imediatamente a regra ampla de porta 80 após emitir o certificado;
4. altere Nginx para HTTPS;
5. faça `sam deploy` para que a configuração declarativa reflita a regra final.

Prefira DNS-01 se puder automatizar o provedor DNS; ele evita abrir porta 80 e
funciona com 443 restrita. Outra opção é acesso permanente somente por túnel
SSM/VPN. Não use ALB ou NAT Gateway nesta arquitetura Free Tier.

## 15. Preparar o acesso administrativo

Use Systems Manager Session Manager em vez de SSH:

1. Crie uma role EC2 com trust policy para `ec2.amazonaws.com`.
2. Anexe `AmazonSSMManagedInstanceCore`.
3. Crie um instance profile contendo essa role.
4. Não crie key pair e não abra a porta 22.

O agente SSM já vem instalado nas AMIs Ubuntu e Amazon Linux suportadas, mas
deve ser validado depois do boot. A instância precisa de saída HTTPS para os
endpoints do SSM. Uma VPC privada exigiria NAT ou VPC endpoints cobrados; para
esta implantação econômica, use subnet pública, sem entrada SSH, e restrinja a
entrada da API.

## 16. Revisar rede e Security Group

É aceitável usar a VPC padrão para uma primeira implantação controlada.

Security Group recomendado:

| Direção | Protocolo/porta | Origem/destino | Motivo |
| --- | --- | --- | --- |
| Entrada | TCP 443 | IP público fixo do cliente `/32` | API HTTPS |
| Entrada | TCP 80 | `0.0.0.0/0`, temporário | Somente durante HTTP-01; remova após emissão |
| Entrada | TCP 22 | Nenhuma | Administração via SSM |
| Saída | TCP 443 | `0.0.0.0/0` | WhatsApp Web, pacotes e APIs AWS |
| Saída | DNS | resolvedor da VPC | Resolução de nomes |

Durante a homologação via túnel SSM, não crie regras de entrada. Se o cliente
não possuir IP fixo, não exponha diretamente a API sem antes implementar
autenticação. O sistema atual não possui autenticação nem autorização.

## 17. Revisar a instância EC2

Use uma AMI oficial Ubuntu Server 24.04 LTS x86_64 e um volume raiz EBS `gp3`
criptografado de 12 a 16 GiB. Não use instance store para o perfil do WhatsApp.

Configuração mínima:

- tipo elegível confirmado no painel Free Tier;
- subnet pública;
- atribuição de IPv4 público somente se necessária;
- Security Group da seção anterior;
- instance profile do SSM;
- EBS criptografado;
- IMDSv2 obrigatório;
- tags `Application=whatsapp-notify` e `Environment=dev`;
- sem detailed monitoring para evitar cobrança desnecessária nesta fase.

Se criar um Launch Template, configure:

```json
{
  "MetadataOptions": {
    "HttpEndpoint": "enabled",
    "HttpTokens": "required",
    "HttpPutResponseHopLimit": 1
  },
  "CreditSpecification": {
    "CpuCredits": "standard"
  }
}
```

Não associe Elastic IP automaticamente. Um endereço estável facilita DNS, mas
o IP automático e o Elastic IP têm a mesma cobrança horária enquanto alocados.
O IP automático muda após stop/start; se usar DNS público, automatize sua
atualização ou associe um Elastic IP e lembre-se de liberá-lo ao excluir a
stack. Para o menor custo e menor superfície de ataque, use somente o túnel SSM
e não exponha a API; isso ainda não elimina a necessidade de saída IPv4 deste
desenho.

## 18. Conectar por Session Manager manualmente

Obtenha o ID:

```powershell
$InstanceId = aws ec2 describe-instances `
  --filters "Name=tag:Application,Values=whatsapp-notify" `
            "Name=instance-state-name,Values=running" `
  --query "Reservations[0].Instances[0].InstanceId" `
  --output text `
  --region $AwsRegion `
  --profile $AwsProfile

aws ssm describe-instance-information `
  --filters "Key=InstanceIds,Values=$InstanceId" `
  --region $AwsRegion `
  --profile $AwsProfile

aws ssm start-session `
  --target $InstanceId `
  --region $AwsRegion `
  --profile $AwsProfile
```

Se a instância não aparecer como `Online`, confirme role, SSM Agent, região,
DNS e saída TCP 443.

## 19. Manutenção manual do sistema

Na sessão SSM:

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo apt-get install -y git python3.12 python3.12-venv nginx
sudo useradd --system --create-home --home-dir /opt/whatsapp-notify \
  --shell /usr/sbin/nologin whatsapp-notify
sudo install -d -o whatsapp-notify -g whatsapp-notify \
  /opt/whatsapp-notify/app /opt/whatsapp-notify/data
```

Em uma instância com 1 GiB, crie swap de 2 GiB:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Swap reduz falhas por falta de memória, mas não substitui RAM. Monitore uso e
migre para 2 GiB se o Chromium usar swap continuamente.

## 20. Atualizar o código da aplicação

Crie e envie um novo ZIP repetindo a seção 7.1. Depois, na sessão SSM, baixe a
nova chave para um diretório separado. Informe valores já conferidos; não use
curingas:

```bash
ARTIFACT_BUCKET='<bucket>'
ARTIFACT_KEY='whatsapp-notify/releases/<versao>/whatsapp-notify.zip'
ARTIFACT_SHA256='<sha256>'
RELEASE_DIR='/opt/whatsapp-notify/app-next'

sudo systemctl stop whatsapp-notify
sudo rm -rf "$RELEASE_DIR"
sudo install -d -o whatsapp-notify -g whatsapp-notify "$RELEASE_DIR"
aws s3 cp "s3://$ARTIFACT_BUCKET/$ARTIFACT_KEY" /tmp/whatsapp-notify.zip
echo "$ARTIFACT_SHA256  /tmp/whatsapp-notify.zip" | sha256sum -c -
sudo -u whatsapp-notify unzip -q /tmp/whatsapp-notify.zip -d "$RELEASE_DIR"
sudo -u whatsapp-notify python3.12 -m venv "$RELEASE_DIR/.venv"
sudo -u whatsapp-notify "$RELEASE_DIR/.venv/bin/pip" install "$RELEASE_DIR"
sudo "$RELEASE_DIR/.venv/bin/playwright" install-deps chromium
sudo -u whatsapp-notify "$RELEASE_DIR/.venv/bin/playwright" install chromium
sudo -u whatsapp-notify "$RELEASE_DIR/.venv/bin/python" -m pytest -q
sudo mv /opt/whatsapp-notify/app /opt/whatsapp-notify/app-previous
sudo mv "$RELEASE_DIR" /opt/whatsapp-notify/app
sudo rm -f /tmp/whatsapp-notify.zip
sudo systemctl start whatsapp-notify
```

Só remova `app-previous` depois do smoke test. No `template.yaml`, o parâmetro
`ArtifactKey` representa o artefato de bootstrap. Alterá-lo em `sam deploy` não
é um procedimento de atualização in-place: a alteração modifica o `UserData` e
pode reiniciar a instância EBS, mas o cloud-init normalmente não reexecuta o
script. No fluxo imutável de `template-ami.yaml`, uma release nova exige uma
nova AMI e a atualização de `AmiId`, que substitui a EC2.

## 21. Configurar as variáveis de ambiente

Crie `/etc/whatsapp-notify.env`:

```bash
sudo install -m 600 -o root -g root /dev/null /etc/whatsapp-notify.env
sudoedit /etc/whatsapp-notify.env
```

Conteúdo:

```env
WHATSAPP_TARGET_NAME=
WHATSAPP_MESSAGE=
WHATSAPP_HEADLESS=true
WHATSAPP_PROFILE_DIR=/opt/whatsapp-notify/data/.whatsapp-profile
WHATSAPP_TIMEOUT_SECONDS=60
API_HOST=127.0.0.1
API_PORT=8000
LOG_LEVEL=INFO
```

Deixe contato e mensagem vazios para exigir esses valores na requisição. O
arquivo não contém credenciais do WhatsApp: a autenticação fica no perfil do
Chromium, que deve ter acesso restrito:

```bash
sudo install -d -m 700 -o whatsapp-notify -g whatsapp-notify \
  /opt/whatsapp-notify/data/.whatsapp-profile
```

Não copie um perfil do Windows para Linux. Faça a primeira autenticação no
Chromium da própria instância usando o endpoint de QR Code.

## 22. Revisar o serviço systemd

Crie `/etc/systemd/system/whatsapp-notify.service`:

```ini
[Unit]
Description=WhatsApp Notify API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=whatsapp-notify
Group=whatsapp-notify
WorkingDirectory=/opt/whatsapp-notify/app
EnvironmentFile=/etc/whatsapp-notify.env
Environment=PYTHONPATH=/opt/whatsapp-notify/app/src
ExecStart=/opt/whatsapp-notify/app/.venv/bin/uvicorn api.server:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/whatsapp-notify/data

[Install]
WantedBy=multi-user.target
```

O parâmetro `--workers 1` é obrigatório: workers diferentes não compartilham
`WhatsAppSessionService`, lock, página nem perfil. Não configure Auto Scaling
Group com mais de uma instância para esta versão da aplicação.

Ative:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now whatsapp-notify
sudo systemctl status whatsapp-notify --no-pager
sudo journalctl -u whatsapp-notify -n 100 --no-pager
curl -i http://127.0.0.1:8000/whatsapp/session/status
```

## 23. Repetir a homologação

Instale localmente o plugin do Session Manager e abra um túnel:

```powershell
aws ssm start-session `
  --target $InstanceId `
  --document-name AWS-StartPortForwardingSession `
  --parameters "portNumber=8000,localPortNumber=8000" `
  --region $AwsRegion `
  --profile $AwsProfile
```

Em outro terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/whatsapp/session/status
Invoke-RestMethod "http://127.0.0.1:8000/whatsapp/session/start?headless=true&timeoutInSecounds=60"
Invoke-WebRequest http://127.0.0.1:8000/whatsapp/session/qrcode `
  -OutFile whatsapp-qr.png
```

Abra `whatsapp-qr.png`, escaneie no celular e consulte o status até obter
`SESSAO_ABERTA`. Depois:

```powershell
$Body = @{
  contact = "Grupo Teste"
  message = "Mensagem de homologação"
} | ConvertTo-Json -Compress

# A conversão explícita evita erro de leitura do JSON com acentos no
# Windows PowerShell 5.1. A API espera que o corpo esteja em UTF-8.
$BodyUtf8 = [System.Text.Encoding]::UTF8.GetBytes($Body)

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/whatsapp/messages/send `
  -ContentType "application/json; charset=utf-8" `
  -Body $BodyUtf8
  
Invoke-RestMethod http://127.0.0.1:8000/whatsapp/session/stop
```

Não registre o PNG do QR Code, o perfil ou artefatos de falha no Git.

## 24. Publicar com Nginx e HTTPS

Esta etapa é opcional se o túnel SSM atende ao consumidor. Para HTTPS público:

1. Registre ou reutilize um domínio.
2. Aponte um registro `A` para o IPv4 da instância.
3. Restrinja 443 ao CIDR do consumidor quando possível.
4. Instale Certbot e emita um certificado por DNS-01; se usar HTTP-01, abra 80
   para a internet somente durante emissão/renovação.
5. Faça proxy somente para `127.0.0.1:8000`.

Configuração base de `/etc/nginx/sites-available/whatsapp-notify`:

```nginx
server {
    listen 80;
    server_name <api.seudominio.com>;

    client_max_body_size 64k;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 90s;
        proxy_send_timeout 90s;
    }
}
```

Ative e valide:

```bash
sudo ln -s /etc/nginx/sites-available/whatsapp-notify \
  /etc/nginx/sites-enabled/whatsapp-notify
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <api.seudominio.com>
```

Depois de `certbot --nginx`, inspecione a configuração gerada, confirme que há
um listener TLS em 443 e teste a renovação com `sudo certbot renew --dry-run`.
Os timeouts de proxy precisam superar `WHATSAPP_TIMEOUT_SECONDS`. Não exponha
`/docs`, `/redoc`, `/openapi.json`, `/whatsapp/session/start`,
`/whatsapp/session/qrcode` ou `/whatsapp/session/stop` para a internet sem
autenticação. A restrição por IP é o controle mínimo temporário; a correção
aplicacional recomendada é autenticação forte antes do uso em produção.

## 25. Segurança obrigatória antes de produção

- mantenha entrada SSH fechada e administre por SSM;
- exija IMDSv2;
- limite 443 aos consumidores conhecidos;
- implemente autenticação/autorização na API;
- não coloque token estático no código, artefato, URL ou log;
- proteja o QR Code e aplique `Cache-Control: no-store`;
- preserve permissões `0700` no perfil e `0600` no arquivo de ambiente;
- use EBS criptografado;
- atualize Ubuntu, Python, Playwright e Chromium regularmente;
- não registre conteúdo da mensagem em logs;
- considere remover ou proteger Swagger, ReDoc e OpenAPI;
- revise os termos do WhatsApp aplicáveis ao uso e à automação.

O código atual registra o nome do destino. Avalie se esse dado é pessoal ou
sensível no seu contexto e remova-o ou masque-o antes da produção.

## 26. Persistência, backup e recuperação

O EBS persiste em reboot e stop/start, mas pode ser perdido se a instância for
terminada conforme a política `DeleteOnTermination`. Para o perfil:

1. pare a sessão com `/whatsapp/session/stop`;
2. pare o serviço;
3. crie snapshot criptografado do volume;
4. reinicie o serviço.

```bash
sudo systemctl stop whatsapp-notify
```

```powershell
$VolumeId = aws ec2 describe-instances `
  --instance-ids $InstanceId `
  --query "Reservations[0].Instances[0].BlockDeviceMappings[0].Ebs.VolumeId" `
  --output text `
  --region $AwsRegion `
  --profile $AwsProfile

aws ec2 create-snapshot `
  --volume-id $VolumeId `
  --description "whatsapp-notify profile backup" `
  --region $AwsRegion `
  --profile $AwsProfile
```

```bash
sudo systemctl start whatsapp-notify
```

Snapshots também são cobrados. Mantenha poucos e exclua os antigos. O perfil
contém material de sessão sensível; não o envie a S3 sem criptografia e controle
de acesso.

Esse snapshot de backup contém o estado da aplicação e é diferente do snapshot
associado à AMI-base da seção 11.1. A AMI-base deve estar higienizada e serve
para provisionamento; o snapshot de backup pode conter a sessão e serve somente
para recuperação controlada.

## 27. Observabilidade econômica

Comece com métricas básicas gratuitas da EC2 e `journalctl`. Não habilite
detailed monitoring automaticamente.

Verificações:

```bash
systemctl is-active whatsapp-notify
systemctl is-active nginx
journalctl -u whatsapp-notify --since "30 minutes ago" --no-pager
free -h
df -h
```

Monitore no CloudWatch:

- `CPUUtilization`;
- `CPUCreditBalance`;
- `CPUSurplusCreditsCharged`;
- `StatusCheckFailed`;
- tráfego de rede.

Memória e disco não são métricas nativas da EC2. Instalar CloudWatch Agent pode
ajudar, mas logs e métricas customizadas podem gerar custo. Para o Free Tier,
publique apenas o necessário, defina retenção curta e configure alarmes de
billing.

## 28. Processo de atualização

Para cada atualização:

1. execute os testes no projeto local;
2. gere novo `ArtifactVersion`, ZIP e SHA-256 conforme a seção 7.1;
3. envie para uma nova chave S3, sem sobrescrever a versão anterior;
4. instale pela sessão SSM conforme a seção 20;
5. execute o smoke test;
6. mantenha `app-previous` e o ZIP anterior até confirmar estabilidade;
7. remova versões antigas conscientemente para limitar custo do S3.

Atualizações reiniciam o serviço e fecham o Chromium. O perfil fica fora do
diretório da aplicação e deve permitir reautenticação automática, mas o status
precisa ser validado.

## 29. Smoke test após deploy ou reboot

Execute nesta ordem:

1. `GET /whatsapp/session/status` responde HTTP 200.
2. `GET /whatsapp/session/start?headless=true` inicia a sessão.
3. Se necessário, `GET /whatsapp/session/qrcode` retorna PNG sem cache.
4. O status chega a `SESSAO_ABERTA`.
5. `POST /whatsapp/messages/send` envia para um destino de teste.
6. Uma segunda chamada de envio ocorre de forma serializada.
7. `GET /whatsapp/session/stop` fecha a sessão.
8. Reiniciar o systemd não apaga o perfil.
9. Reboot da instância inicia a API automaticamente.
10. Nenhum endpoint está acessível fora dos CIDRs autorizados.

## 30. Rollback

Antes de agir, identifique qual rollback é necessário:

| Situação | Procedimento |
| --- | --- |
| Falha após atualização manual pelo ZIP do S3 | Restaurar `app-previous` ou reinstalar o ZIP anterior |
| Falha em uma release implantada com `template-ami.yaml` | Atualizar a stack com o `AmiId` anterior |
| Perfil do WhatsApp corrompido | Restaurar um snapshot de backup ou autenticar novamente |
| Desistência completa do ambiente | Remover a stack e depois revisar os recursos externos |

### 30.1 Rollback do código usando o S3

Alterar `ArtifactKey` no CloudFormation não reinstala o código na instância
existente. Se a atualização manual da seção 20 falhar, restaure primeiro o
diretório anterior dentro da EC2:

```bash
test -d /opt/whatsapp-notify/app-previous
sudo systemctl stop whatsapp-notify
sudo mv /opt/whatsapp-notify/app /opt/whatsapp-notify/app-failed
sudo mv /opt/whatsapp-notify/app-previous /opt/whatsapp-notify/app
sudo systemctl start whatsapp-notify
sudo systemctl status whatsapp-notify --no-pager
```

Execute o smoke test da seção 29. Se o diretório anterior não existir, no
PowerShell localize uma release anterior sem alterar ou excluir objetos:

```powershell
aws s3api list-objects-v2 `
  --bucket $ArtifactBucket `
  --prefix "whatsapp-notify/releases/" `
  --query "Contents[].{Key:Key,Modified:LastModified,Size:Size}" `
  --output table `
  --region $AwsRegion `
  --profile $AwsProfile
```

Escolha uma chave conhecida e recupere o SHA-256 gravado no metadata:

```powershell
$PreviousArtifactKey = "whatsapp-notify/releases/<versao-anterior>/whatsapp-notify.zip"
$PreviousArtifactSha256 = aws s3api head-object `
  --bucket $ArtifactBucket `
  --key $PreviousArtifactKey `
  --query "Metadata.sha256" `
  --output text `
  --region $AwsRegion `
  --profile $AwsProfile

$PreviousArtifactKey
$PreviousArtifactSha256
```

Se a chave ou o hash estiver vazio, não prossiga. Use esses dois valores no
procedimento manual da seção 20 e execute novamente o smoke test. Preserve o
ZIP atual até concluir o diagnóstico; rollback não exige apagar a release com
problema.

### 30.2 Rollback para uma AMI anterior

Este procedimento substitui a EC2. O volume raiz da instância atual pode ser
excluído durante a substituição. Antes do deploy, pare envios e crie um snapshot
de backup caso precise preservar o perfil do WhatsApp. Não execute duas cópias
ativas do mesmo perfil simultaneamente.

Confirme que a AMI anterior ainda está disponível:

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

Se a imagem estiver desabilitada, habilite-a antes do rollback:

```powershell
aws ec2 enable-image `
  --image-id $PreviousAmiId `
  --region $AwsRegion `
  --profile $AwsProfile
```

Atualize a stack da AMI informando todos os parâmetros obrigatórios. Revise o
change set e confirme que `ApplicationInstance` será substituída:

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
    AllowedCidr=$AllowedCidr `
    RootVolumeSize=16
```

Aguarde `UPDATE_COMPLETE`, conecte pelo Session Manager e execute o smoke test.
Se nenhum backup de perfil for restaurado, autentique o WhatsApp novamente.

### 30.3 Rollback do perfil por snapshot

Se o perfil for corrompido, restaure o snapshot com a instância parada ou mova
o diretório atual e refaça a autenticação. Mantenha o snapshot até validar
mensagens e um reboot. Somente depois, confira o ID e exclua o backup que não
for mais necessário:

```powershell
$SnapshotId = "snap-<id-confirmado>"

aws ec2 describe-snapshots `
  --snapshot-ids $SnapshotId `
  --region $AwsRegion `
  --profile $AwsProfile

aws ec2 delete-snapshot `
  --snapshot-id $SnapshotId `
  --region $AwsRegion `
  --profile $AwsProfile
```

> **Atenção:** excluir snapshots, objetos S3 ou uma AMI registrada é uma ação
> separada do rollback. Faça a limpeza somente após confirmar a recuperação.

### 30.4 Inventariar recursos criados fora do SAM

O `sam delete` remove apenas os recursos pertencentes à stack. Neste projeto,
os seguintes itens podem ter sido criados manualmente:

| Recurso externo | Como verificar | Quando remover |
| --- | --- | --- |
| Bucket e releases no S3 | `aws s3 ls s3://$ArtifactBucket --recursive` | Quando nenhuma instalação ou reversão depender dos ZIPs |
| AMIs da aplicação | `aws ec2 describe-images --owners self` | Depois que nenhuma instância ou rollback usar a imagem |
| Snapshots de AMI e backup | `aws ec2 describe-snapshots --owner-ids self` | Depois de identificar a finalidade de cada snapshot |
| Elastic IP | `aws ec2 describe-addresses` | Quando não estiver associado nem reservado para o serviço |
| Registro DNS | Console Route 53 ou provedor do domínio | Quando não deve mais apontar para a aplicação |
| Budget manual | Billing and Cost Management | Somente se o alerta não for mais útil |

Inventário não gera rollback nem remove recursos. Registre os IDs e confirme a
propriedade antes de executar qualquer exclusão.

### 30.5 Limpar releases e bucket S3

Para remover apenas uma release, confira a chave exata e depois exclua somente
esse objeto:

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

Para remover o bucket inteiro, primeiro confira o nome, o conteúdo e o estado
de versionamento:

```powershell
aws s3api get-bucket-versioning `
  --bucket $ArtifactBucket `
  --region $AwsRegion `
  --profile $AwsProfile

aws s3 ls "s3://$ArtifactBucket" --recursive `
  --region $AwsRegion `
  --profile $AwsProfile

aws s3 rb "s3://$ArtifactBucket" `
  --force `
  --region $AwsRegion `
  --profile $AwsProfile
```

O roteiro cria o bucket sem versionamento. Se `get-bucket-versioning` retornar
`Enabled` ou `Suspended`, o comando `--force` não é suficiente para apagar
versões e delete markers. Não remova um bucket compartilhado ou que contenha
releases necessárias.

### 30.6 Desabilitar ou remover uma AMI e seus snapshots

Prefira `disable-image` enquanto ainda existir possibilidade de rollback. Para
remoção definitiva, primeiro confirme que nenhuma instância usa a AMI e capture
os IDs dos snapshots **antes** de desregistrá-la:

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

Anote cada `snap-...`. Se a consulta de instâncias retornar algum resultado,
não desregistre a AMI. Quando a imagem não tiver consumidores nem utilidade para
rollback:

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

Desregistrar a AMI não exclui automaticamente os snapshots associados. Sem uma
regra prévia do Recycle Bin, o deregistro deve ser tratado como permanente.

### 30.7 Outros recursos externos

- **Elastic IP:** confira `AllocationId` e `AssociationId`. Desassocie com
  `aws ec2 disassociate-address --association-id <eipassoc-id>` e libere com
  `aws ec2 release-address --allocation-id <eipalloc-id>`. IPv4 público pode
  gerar cobrança enquanto permanecer alocado.
- **DNS:** remova somente o registro `A` criado para a aplicação, no Route 53 ou
  no provedor usado. Não exclua a hosted zone nem o domínio se forem
  compartilhados.
- **Budget:** budgets foram criados fora da stack. Exclua-os pelo console de
  Billing apenas se os alertas não forem mais necessários.
- **Certificado Certbot:** fica no disco da EC2 e normalmente desaparece com o
  volume raiz. Remova separadamente apenas desafios ou registros DNS criados
  fora da instância.

## 31. Remover a stack e evitar cobranças

Parar a instância interrompe cobrança de compute, mas EBS e IPv4 reservado
continuam sujeitos a cobrança. Terminar remove a instância e, normalmente, o
volume raiz.

Antes de remover, crie snapshot se precisar preservar a sessão. Depois:

```powershell
sam delete `
  --stack-name $StackName `
  --region $AwsRegion `
  --profile $AwsProfile
```

Confirme no console que o CloudFormation removeu a instância, Security Group,
role e instance profile. Budgets criados separadamente não são removidos com a
stack. Em seguida siga a conferência:

1. pare o serviço e confirme que não há envio em andamento;
2. faça backup somente se necessário;
3. termine a instância;
4. faça o inventário de recursos externos da seção 30.4;
5. exclua snapshots desnecessários somente após registrar sua finalidade;
6. exclua volumes EBS órfãos;
7. libere Elastic IP, se houver;
8. remova DNS e budgets externos somente quando apropriado;
9. confirme em **Cost Explorer** e **Free Tier** que não restaram recursos.

O bucket de artefatos, as AMIs e seus snapshots não pertencem à stack. Siga as
seções 30.5 e 30.6 para removê-los com conferência prévia. Não use exclusões
recursivas em buckets compartilhados.

## 32. Checklist final

- [ ] Modalidade, créditos e expiração do Free Tier conferidos.
- [ ] Conta legada tratada como paga em 2026, salvo crédito confirmado no console.
- [ ] Budget e alertas de uso configurados separadamente, caso desejados.
- [ ] Tipo EC2 elegível escolhido e créditos T configurados conscientemente.
- [ ] Arquitetura da AMI (`amd64`) compatível com o tipo `t3.*` do template.
- [ ] ZIP local exclui `.env`, perfil, controle de versão, ambiente virtual, caches e logs.
- [ ] Bucket S3 privado, com Block Public Access e SSE-S3.
- [ ] SHA-256 calculado localmente e validado no bootstrap.
- [ ] Instance role limitada a `s3:GetObject` no prefixo de releases do projeto.
- [ ] EBS criptografado e perfil persistente fora do diretório do código.
- [ ] IMDSv2 obrigatório.
- [ ] SSM operacional, sem porta 22 e sem key pair.
- [ ] `template.yaml` e `template-ami.yaml` validados com SAM.
- [ ] AMI-base criada sem perfil do WhatsApp, credenciais ou outros segredos.
- [ ] Snapshot associado à AMI identificado e incluído no controle de custos.
- [ ] AMI contém a release testada; `template-ami.yaml` não baixa nem reinstala o código.
- [ ] Primeiro deploy com `template-ami.yaml` feito em uma stack separada.
- [ ] `CreationPolicy` recebeu o sinal de sucesso do bootstrap.
- [ ] Chromium e dependências instalados pelo Playwright.
- [ ] API executada por usuário sem login e por systemd.
- [ ] Uvicorn com exatamente um worker.
- [ ] Swap criado se a instância tiver 1 GiB.
- [ ] Homologação feita primeiro por túnel SSM.
- [ ] HTTPS e origem restrita antes da exposição pública.
- [ ] Porta 80 removida após HTTP-01, ou DNS-01 adotado.
- [ ] Autenticação adicionada antes de tratar a API como produção.
- [ ] QR Code, mensagens e perfil ausentes de logs e artefatos.
- [ ] Smoke test aprovado após deploy e reboot.
- [ ] Procedimentos de backup, rollback e remoção testados.
- [ ] Releases S3 e AMIs anteriores preservadas até a aprovação do smoke test.
- [ ] Recursos externos à stack inventariados antes de qualquer exclusão.
- [ ] Custos de IPv4, EBS, snapshots e tráfego acompanhados.
- [ ] `sam delete` testado em ambiente descartável.

## Referências oficiais

- [AWS Free Tier](https://aws.amazon.com/free/)
- [Perguntas frequentes do AWS Free Tier](https://aws.amazon.com/free/free-tier-faqs/)
- [AWS SAM - conceitos](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html)
- [AWS SAM CLI - deploy](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-deploy.html)
- [Recursos CloudFormation do EC2](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/AWS_EC2.html)
- [Criar uma AMI baseada em EBS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-an-ami-ebs.html)
- [Planos do AWS Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html)
- [Monitorar o uso gratuito do EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html)
- [Preços de IPv4 público](https://aws.amazon.com/vpc/pricing/)
- [Preços do Amazon EC2](https://aws.amazon.com/ec2/pricing/)
- [Segurança no Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security.html)
- [Preços do Amazon S3](https://aws.amazon.com/s3/pricing/)
- [Bundles e preços do Amazon Lightsail](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html)
- [Práticas recomendadas de segurança do EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-security.html)
- [Conectar ao EC2 com Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)
- [Exigir IMDSv2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html)
- [Playwright para Python](https://playwright.dev/python/docs/intro)
- [Autenticação persistente do Playwright](https://playwright.dev/python/docs/auth)
- [Implantação do FastAPI](https://fastapi.tiangolo.com/deployment/)
