# Self Managed Active Directory + Windows EC2 + FSx for Windows Server

このプロジェクトは、AWS CDK（Python）を使用してActive Directory ドメインコントローラー、Windows EC2インスタンス、FSx for Windows File Serverを作成するIaCテンプレートです。

## 構成内容

### インフラストラクチャ
- **VPC**: 2つのアベイラビリティゾーンに跨るVPC
- **サブネット**: パブリックサブネットとプライベートサブネット（NAT経由でインターネットアクセス可能）
- **NATゲートウェイ**: プライベートサブネットからのインターネットアクセス用（1つ）
- **セキュリティグループ**: AD、Windows EC2、FSx用の最適化されたセキュリティグループ設定
  - アウトバウンドアクセス: HTTPS(443)、DNS(53)、NTP(123)のみ許可
  - FSx用RPC動的ポート範囲（49152-65535）対応
- **VPCエンドポイント**: SSM、EC2、S3アクセス用

### リソース
1. **Active Directory ドメインコントローラー (AD DC)**
   - Windows Server EC2インスタンス（t3.medium）
   - Active Directory Domain Servicesの自動インストール
   - 新しいフォレスト `example.com` の自動作成

2. **Windows EC2インスタンス**
   - 一般的なWindows Server EC2インスタンス（t3.medium）
   - ドメイン参加準備済み（手動でドメイン参加が必要）

3. **FSx for Windows File Server**
   - 32GB SSDストレージ
   - シングルAZ展開（SINGLE_AZ_2）
   - 自動バックアップ設定

## 動作環境・前提条件

### 1. 必要なソフトウェア環境
以下のソフトウェアが事前にインストールされている必要があります：

- **Python 3.7以上** - CDKアプリケーション実行用
- **Node.js 18以上 & npm** - AWS CDKランタイム（CDKはNode.js製）
- **AWS CLI v2** - AWS認証・操作用
- **AWS CDK CLI** - スタック管理用
  ```bash
  npm install -g aws-cdk
  ```

### 2. AWSアカウント・認証情報
- **AWSアカウント** - デプロイ先環境
- **AWS認証情報** - AWS CLIプロファイルまたは環境変数で設定
  ```bash
  # AWS CLIプロファイルの設定
  aws configure --profile your-profile-name
  
  # または環境変数で設定
  export AWS_ACCESS_KEY_ID=your-access-key
  export AWS_SECRET_ACCESS_KEY=your-secret-key
  export AWS_DEFAULT_REGION=ap-northeast-1
  ```

### 3. 必要なAWSサービス権限
デプロイを実行するIAMユーザー/ロールには以下の権限が必要です：
- **VPC・EC2** - ネットワーク・インスタンス作成
- **FSx** - FSx for Windows Server作成・管理
- **CloudFormation** - スタック管理・リソース作成
- **IAM** - サービスロール・ポリシー作成
- **Systems Manager (SSM)** - Session Manager・パラメータストア

### 4. プロジェクト固有設定
- **EC2キーペア** - RDPアクセス用（オプション）
  ```bash
  # 新規キーペア作成例
  aws ec2 create-key-pair --key-name my-key-pair --query 'KeyMaterial' --output text > my-key-pair.pem
  ```
- **cdk.json設定** - `key-pair-name`を環境に合わせて変更
- **Python仮想環境** - プロジェクト依存関係の管理
  ```bash
  # Python仮想環境の作成（推奨）
  python -m venv .venv
  # Windowsの場合
  .venv\\Scripts\\activate
  # macOS/Linuxの場合
  source .venv/bin/activate
  
  # 依存関係のインストール
  pip install -r requirements.txt
  ```

### 5. CDK Bootstrap（初回のみ）
```bash
# デフォルトプロファイル使用の場合
cdk bootstrap

# 特定のプロファイル使用の場合
cdk bootstrap --profile your-profile-name
```

## デプロイ方法

### スタックのデプロイ（順次実行が必要）

⚠️ **重要**: スタックは順次デプロイし、手動設定完了後にFSxスタックをデプロイしてください。

#### 方法A: deploy_stacks.sh使用（推奨）

```bash
# インタラクティブモードで段階的デプロイ（推奨）
./deploy_stacks.sh

# 特定のプロファイル使用の場合
./deploy_stacks.sh --profile your-profile-name

# または段階的実行
./deploy_stacks.sh --phase 2
# 手動設定完了後
./deploy_stacks.sh --phase 3
```

#### 方法B: 直接CDKコマンド使用

```bash
# ステップ1: ネットワークスタックのデプロイ
cdk deploy -a "python app_network.py" AdWindowsFsxNetworkStack-<your-name>

# ステップ2: ドメインスタック（AD DC）のデプロイ  
cdk deploy -a "python app_domain.py" AdWindowsFsxDomainStack-<your-name>

# ステップ3: AD DCの完全起動を待機（5-10分）
# SSM Session Managerでログイン確認：
aws ssm start-session --target <AD-DC-instance-id>

# ステップ4: 【重要】手動でfsxuserに権限委任（後述の手順）

# ステップ5: FSxスタックのデプロイ（手動設定完了後）
cdk deploy -a "python app_application.py" AdWindowsFsxApplicationStack-<your-name>
```

### 注意事項
- **手動権限設定なしでFSxスタックをデプロイすると失敗します**
- FSxスタックは必ずステップ4完了後に実行してください
- 方法Aは手動設定の確認機能があるため推奨

### 3. 設定可能なパラメータ
- `windows-version`: Windows Serverのバージョン（2016, 2019, 2022, 2025）
- `windows-language`: 言語設定（English, Japanese）
- `key-pair-name`: EC2キーペア名（RDPアクセス用）

## デプロイ後の設定

### 1. AD DCの設定確認
1. SSM Session Managerを使用してAD DCにアクセス
2. Active Directory Users and Computersでドメイン設定を確認

### 2. Windows EC2のドメイン参加
```powershell
# PowerShellで実行（管理者権限）
Add-Computer -DomainName example.com -Credential (Get-Credential) -Restart
```

### 3. FSx用サービスアカウント権限設定（重要）
FSxが正常に動作するために、fsxuserアカウントに権限を委任する必要があります。

**AWS公式ドキュメント**: [Delegating permissions to the Amazon FSx service account](https://docs.aws.amazon.com/fsx/latest/WindowsGuide/assign-permissions-to-service-account.html)

#### 手順（「Delegate Control / 権限の委任」使用）:
1. AD DCに管理者でログイン
2. **Active Directory ユーザーとコンピューター / Users and Computers** を開く
3. ドメインノードを展開
4. 対象OU（デフォルトでは Computers）を右クリック → **Delegate Control**
5. **Add** で `fsxuser` を追加 → **Next**
6. **Create a custom task to delegate** → **Next**
7. **Only the following objects in the folder** → **Computer objects** → **Next**
8. **Create selected objects** と **Delete selected objects** をチェック → **Next**
9. **Permissions** で以下を選択：
   - ☑ **Reset Password**
   - ☑ **Read and write Account Restrictions**
   - ☑ **Validated write to DNS host name**
   - ☑ **Validated write to service principal name**
10. **Finish** で完了

### 4. FSxファイルシステムのマウント
```powershell
# PowerShellで実行
# FSx DNSエンドポイントを確認してマウント
net use Z: \\fs-xxxxxxxxx.example.com\share
```

## アクセス方法

### 1. SSM Session Manager経由のアクセス
```bash
# Session Manager経由でアクセス
aws ssm start-session --target i-xxxxxxxxx
# ユーザー: fsxuser (AD DC) / winuser (Windows EC2)
# パスワード: Password123!
```

### 2. RDPクライアント経由（ポートフォワード）
```bash
# Session Managerでポートフォワード設定
aws ssm start-session --target i-xxxxxxxxx --document-name AWS-StartPortForwardingSession --parameters "portNumber=3389,localPortNumber=13389"
# RDPクライアントで localhost:13389 に接続
```

## 注意事項

### セキュリティ
- デフォルトパスワード（Password123!）は本番環境では変更してください
- セキュリティグループは必要最小限のポートのみを開放しています
- プライベートサブネットに配置されており、NATゲートウェイ経由のみインターネットアクセス可能
- アウトバウンドアクセスはHTTPS、DNS、NTPのみに制限（セキュリティ最適化済み）
- Windows Update、ライセンス認証が正常に動作するよう設定済み

### コスト
- AD DC EC2インスタンス: 約$30-50/月（t3.medium）
- Windows EC2インスタンス: 約$30-50/月（t3.medium）  
- FSx File System: 約$10-15/月（32GB SSD）
- NATゲートウェイ: 約$32-45/月（データ転送量による）
- VPCエンドポイント: 約$7-10/月（3つのエンドポイント）

### トラブルシューティング
- AD DCの設定に時間がかかる場合があります（5-10分）
- ドメイン参加前にAD DCが完全に起動していることを確認してください
- FSxマウントにはAD認証が必要です

#### インターネット接続確認
```powershell
# PowerShellでのインターネット接続テスト
Test-NetConnection -ComputerName google.com -Port 443
Test-NetConnection -ComputerName microsoft.com -Port 443

# Windows Updateサービス確認
Get-Service -Name wuauserv
```

#### これまで直面した問題
- **Windows Updateが動作しない**: NATゲートウェイとセキュリティグループの設定を確認
- **FSx接続エラー**: RPC動的ポート範囲（49152-65535）が開放されているか確認
- **AD認証エラー**: DNS設定とドメイン参加状況を確認
- **FSxドメイン参加失敗**: 
  - fsxuserアカウントに適切な権限が設定されているか確認
  - ドメイン名がexample.comで統一されているか確認
  - TCP 9389（AD DS Web Services）ポートが開放されているか確認

#### セキュリティグループに関する注意事項
- **不要なルールの削除**: `255.255.255.255/32` への ICMP拒否ルールは AWS VPC環境では無意味なため削除推奨
- **ブロードキャスト通信**: AWS VPCでは元々ブロードキャスト通信は制限されているため、明示的な拒否ルールは不要

## クリーンアップ

### 方法A: cleanup_stacks.sh使用（推奨）

```bash
# 対話的削除（推奨）
./cleanup_stacks.sh

# 特定のプロファイル使用の場合
./cleanup_stacks.sh --profile your-profile-name

# 確認なしで強制削除
./cleanup_stacks.sh --force

# プロファイル指定 + 強制削除
./cleanup_stacks.sh --profile your-profile-name --force
```

**cleanup_stacks.shの特徴:**
- **依存関係を考慮した削除順序**: Application → Domain → Network の順で安全に削除
- **既存スタック自動検出**: 存在するスタックのみを対象として効率的に削除
- **削除進行状況の表示**: 各スタックの削除状況をリアルタイムで確認
- **エラーハンドリング**: 削除失敗時の詳細なエラー情報表示
- **確認プロンプト**: 誤削除防止のための確認機能（`--force`で無効化可能）

### 方法B: 直接CDKコマンド使用

```bash
# 個別削除（逆順で実行が必要）
cdk destroy -a "python app_application.py" AdWindowsFsxApplicationStack-<your-name>
cdk destroy -a "python app_domain.py" AdWindowsFsxDomainStack-<your-name>
cdk destroy -a "python app_network.py" AdWindowsFsxNetworkStack-<your-name>

# 確認プロンプトをスキップする場合
cdk destroy --force
```

### 方法C: AWSマネジメントコンソールから削除

GUIを使用してブラウザから削除する場合：

1. **AWSマネジメントコンソールにログイン**
2. **CloudFormation**に移動
3. **スタック削除順序**（依存関係に注意）：
   
   **ステップ1: Application Stackの削除**
   - `AdWindowsFsxApplicationStack-<your-name>` を選択
   - **削除**ボタンをクリック → 確認後**削除**
   - 削除完了を待機（5-10分程度）
   
   **ステップ2: Domain Stackの削除**
   - `AdWindowsFsxDomainStack-<your-name>` を選択  
   - **削除**ボタンをクリック → 確認後**削除**
   - 削除完了を待機（5-10分程度）
   
   **ステップ3: Network Stackの削除**
   - `AdWindowsFsxNetworkStack-<your-name>` を選択
   - **削除**ボタンをクリック → 確認後**削除**
   - 削除完了を待機（5-10分程度）

4. **削除進行状況の確認**
   - **イベント**タブで削除進行状況を確認
   - エラーが発生した場合は**イベント**タブで詳細を確認

**メリット:**
- GUIによる直感的な操作
- 削除進行状況の視覚的確認
- エラー詳細の確認が容易

**デメリット:**
- 手動操作による人的ミスの可能性
- 削除順序の管理が必要
- 複数スタックの一括処理ができない

⚠️ **重要**: 
- スタックは**逆順**（Application → Domain → Network）で削除する必要があります
- 依存関係があるため、順序を間違えると削除に失敗する場合があります
- cleanup_stacks.shの使用を強く推奨します

## ファイル構造

```
.
├── ad_windows_fsx/
│   ├── __init__.py
│   ├── ad_network_stack.py         # ネットワークインフラスタック
│   ├── ad_domain_stack.py          # ADドメインコントローラスタック
│   └── ad_application_stack.py     # アプリケーション層スタック（Windows EC2、FSx）
├── docs/
│   └── images/                     # README.md用の画像ファイル置き場
├── tests/
│   └── unit/
│       ├── __init__.py
│       └── test_ad_windows_fsx_stack.py
├── app_network.py                  # ネットワークスタック用エントリーポイント
├── app_domain.py                   # ドメインスタック用エントリーポイント
├── app_application.py              # アプリケーションスタック用エントリーポイント
├── deploy_stacks.sh                # デプロイスクリプト（段階的デプロイ対応）
├── cleanup_stacks.sh               # クリーンアップスクリプト
├── cdk.json                        # CDK設定ファイル
├── requirements.txt                # Python依存関係
├── requirements-dev.txt            # 開発用依存関係
└── README.md                       # このファイル
```

### 画像ファイル管理

- **docs/images/**: README.mdで使用する画像ファイル（スクリーンショット、アーキテクチャ図など）を格納
- 使用例: `![アーキテクチャ図](docs/images/architecture.png)`
- 大きな画像ファイルの管理方法については`.gitignore`を参照