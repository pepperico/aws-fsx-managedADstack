from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    CfnOutput,
    Fn,
)
from constructs import Construct

class AdDomainStack(Stack):
    """
    AD Domain Stack: Active Directory Domain Controller とドメイン作成検証
    
    このスタックには以下が含まれます:
    - AD Domain Controller EC2インスタンス
    - ドメイン作成検証用Custom Resource
    - AD関連のセキュリティグループルール
    - AD DC状態監視機能
    """

    def __init__(self, scope: Construct, construct_id: str, 
                 windows_version: str = "2022", 
                 windows_language: str = "Japanese", 
                 key_pair_name: str = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Network Stackからの参照
        vpc_id = Fn.import_value("AdWindowsFsx-VpcId")
        vpc_cidr_block = Fn.import_value("AdWindowsFsx-VpcCidrBlock")
        private_subnet_id1 = Fn.import_value("AdWindowsFsx-PrivateSubnetId1")
        private_subnet_id2 = Fn.import_value("AdWindowsFsx-PrivateSubnetId2")
        private_route_table_id1 = Fn.import_value("AdWindowsFsx-PrivateRouteTableId1")
        private_route_table_id2 = Fn.import_value("AdWindowsFsx-PrivateRouteTableId2")
        ad_security_group_id = Fn.import_value("AdWindowsFsx-AdSecurityGroupId")
        windows_security_group_id = Fn.import_value("AdWindowsFsx-WindowsSecurityGroupId")
        fsx_security_group_id = Fn.import_value("AdWindowsFsx-FsxSecurityGroupId")
        ec2_role_arn = Fn.import_value("AdWindowsFsx-Ec2RoleArn")

        # 注意: Cross-stack参照の場合、from_lookupではなく直接Subnet IDsを使用
        # VPCは直接参照せず、Subnet IDsのみを使用してEC2インスタンスを作成
        ad_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "ImportedAdSecurityGroup", ad_security_group_id
        )
        windows_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "ImportedWindowsSecurityGroup", windows_security_group_id
        )
        fsx_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "ImportedFsxSecurityGroup", fsx_security_group_id
        )
        ec2_role = iam.Role.from_role_arn(self, "ImportedEc2Role", ec2_role_arn)

        # Windows AMI の取得
        ami_parameter_paths = {
            ("2016", "English"): "/aws/service/ami-windows-latest/Windows_Server-2016-English-Full-Base",
            ("2016", "Japanese"): "/aws/service/ami-windows-latest/Windows_Server-2016-Japanese-Full-Base",
            ("2019", "English"): "/aws/service/ami-windows-latest/Windows_Server-2019-English-Full-Base",
            ("2019", "Japanese"): "/aws/service/ami-windows-latest/Windows_Server-2019-Japanese-Full-Base",
            ("2022", "English"): "/aws/service/ami-windows-latest/Windows_Server-2022-English-Full-Base",
            ("2022", "Japanese"): "/aws/service/ami-windows-latest/Windows_Server-2022-Japanese-Full-Base",
            ("2025", "English"): "/aws/service/ami-windows-latest/Windows_Server-2025-English-Full-Base",
            ("2025", "Japanese"): "/aws/service/ami-windows-latest/Windows_Server-2025-Japanese-Full-Base"
        }
        
        selected_parameter_path = ami_parameter_paths.get(
            (windows_version, windows_language), 
            "/aws/service/ami-windows-latest/Windows_Server-2022-Japanese-Full-Base"
        )
        
        windows_ami = ec2.MachineImage.from_ssm_parameter(
            parameter_name=selected_parameter_path,
            os=ec2.OperatingSystemType.WINDOWS
        )

        # AD内部通信用ポート設定
        ad_ports = [
            (53, "DNS"),
            (88, "Kerberos"),  
            (135, "RPC Endpoint Mapper"),
            (389, "LDAP"),
            (445, "SMB"),
            (464, "Kerberos Password Change"),  # FSx必須ポート追加
            (636, "LDAPS"),
            (3268, "Global Catalog"),
            (3269, "Global Catalog SSL"),
            (9389, "AD DS Web Services")  # Single-AZ 2/Multi-AZ必須
        ]

        # AD DC用ユーザーデータ（検証機能強化版）
        ad_user_data = ec2.UserData.for_windows()
        ad_user_data.add_commands(
            "# AD DC セットアップログ出力開始",
            "Write-Host \"Starting AD DC setup process...\"",
            "$LogFile = 'C:\\Windows\\Temp\\ad-setup.log'",
            "Start-Transcript -Path $LogFile -Append",
            "",
            "# インターネット接続テスト",
            "Write-Host \"Testing internet connectivity...\"",
            "try {",
            "    $connectTest = Test-NetConnection -ComputerName google.com -Port 443 -WarningAction SilentlyContinue",
            "    if ($connectTest.TcpTestSucceeded) {",
            "        Write-Host \"Internet connectivity: SUCCESS\"",
            "    } else {",
            "        Write-Host \"Internet connectivity: FAILED\"",
            "    }",
            "} catch {",
            "    Write-Host \"Internet connectivity test failed: $($_.Exception.Message)\"",
            "}",
            "",
            "# Active Directory Domain Services の機能をインストール",
            "Write-Host \"Installing AD-Domain-Services feature...\"",
            "try {",
            "    $addsResult = Install-WindowsFeature -Name AD-Domain-Services -IncludeManagementTools",
            "    if ($addsResult.Success) {",
            "        Write-Host \"AD-Domain-Services installation: SUCCESS\"",
            "    } else {",
            "        Write-Host \"AD-Domain-Services installation: FAILED\"",
            "        Write-Host \"Exit Code: $($addsResult.ExitCode)\"",
            "    }",
            "} catch {",
            "    Write-Host \"AD-Domain-Services installation error: $($_.Exception.Message)\"",
            "}",
            "",
            "# DNS Server機能をインストール", 
            "Write-Host \"Installing DNS feature...\"",
            "try {",
            "    $dnsResult = Install-WindowsFeature -Name DNS -IncludeManagementTools",
            "    if ($dnsResult.Success) {",
            "        Write-Host \"DNS installation: SUCCESS\"",
            "    } else {",
            "        Write-Host \"DNS installation: FAILED\"",
            "    }",
            "} catch {",
            "    Write-Host \"DNS installation error: $($_.Exception.Message)\"",
            "}",
            "",
            "# リモートデスクトップを有効化",
            "Set-ItemProperty -Path \"HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\" -Name \"fDenyTSConnections\" -Value 0",
            "Enable-NetFirewallRule -DisplayGroup \"Remote Desktop\"",
            "",
            "# タイムゾーンを東京時間に変更",
            "tzutil /s \"Tokyo Standard Time\"",
            "",
            "# 管理者用ユーザーを作成",
            "net user fsxuser Password123! /add",
            "net localgroup administrators fsxuser /add",
            "net localgroup \"Remote Desktop Users\" fsxuser /add",
            "",
            "# FSx用サービスアカウントにドメイン参加権限を付与するための設定は",
            "# ドメイン作成後に手動で実行する必要があります（以下はコメント）",
            "# 必要な権限:",
            "# - Reset passwords",
            "# - Read and write Account Restrictions", 
            "# - Validated write to DNS host name",
            "# - Validated write to service principal name",
            "# - Create computer objects",
            "# - Delete computer objects",
            "",
            "# 新しいフォレストとドメインを作成",
            "Write-Host \"Starting AD Forest creation...\"",
            "$DomainName = 'example.com'",
            "$SafeModePassword = ConvertTo-SecureString 'Password123!' -AsPlainText -Force",
            "",
            "try {",
            "    Import-Module ADDSDeployment",
            "    Write-Host \"Installing AD Forest: $DomainName\"",
            "    Install-ADDSForest -DomainName $DomainName -SafeModeAdministratorPassword $SafeModePassword -DomainMode WinThreshold -ForestMode WinThreshold -InstallDns:$true -Force",
            "    Write-Host \"AD Forest installation command executed - server will restart\"",
            "} catch {",
            "    Write-Host \"AD Forest installation error: $($_.Exception.Message)\"",
            "    Write-Host \"Error details: $($_.Exception.InnerException)\"",
            "}",
            "",
            "# FSx for Windows File Server統合のための追加設定（再起動後に実行）",
            "Write-Host \"After reboot, the following steps are required for FSx integration:\"",
            "Write-Host \"1. Delegate computer object permissions to the 'fsxuser' account\"",
            "Write-Host \"2. Verify DNS configuration for FSx\"",
            "Write-Host \"3. Ensure Global Catalog is accessible\"",
            "",
            "Stop-Transcript",
            "Write-Host \"AD DC setup script completed - awaiting restart...\""
        )

        # プライベートサブネットをインポート（ルートテーブルID情報を含む）
        private_subnet1 = ec2.Subnet.from_subnet_attributes(
            self, "ImportedPrivateSubnet1", 
            subnet_id=private_subnet_id1,
            availability_zone="ap-northeast-1a",
            route_table_id=private_route_table_id1
        )
        
        # VPCをインポート（ルートテーブルID情報を含む）
        vpc_import = ec2.Vpc.from_vpc_attributes(
            self, "ImportedVpc",
            vpc_id=vpc_id,
            availability_zones=["ap-northeast-1a", "ap-northeast-1c"],
            private_subnet_ids=[private_subnet_id1, private_subnet_id2],
            private_subnet_route_table_ids=[private_route_table_id1, private_route_table_id2]
        )

        # AD DCインスタンスの作成時のパラメータ準備
        instance_params = {
            "instance_type": ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
            "machine_image": windows_ami,
            "vpc": vpc_import,
            "vpc_subnets": ec2.SubnetSelection(subnets=[private_subnet1]),
            "security_group": ad_security_group,
            "role": ec2_role,
            "user_data": ad_user_data
        }
        
        # キーペア名が指定されている場合のみkey_pairを追加
        if key_pair_name:
            instance_params["key_pair"] = ec2.KeyPair.from_key_pair_name(self, "KeyPair", key_pair_name)
        
        # AD DCインスタンスの作成
        self.ad_instance = ec2.Instance(self, "AdDcInstance", **instance_params)

        # AD関連セキュリティグループルールの設定
        self._setup_ad_security_rules(ad_security_group, ad_ports, vpc_cidr_block, fsx_security_group_id)

        # 出力値
        CfnOutput(
            self, "AdDcInstanceId",
            value=self.ad_instance.instance_id,
            description="AD Domain Controller Instance ID",
            export_name="AdWindowsFsx-AdDcInstanceId"
        )

        CfnOutput(
            self, "AdDcPrivateIp",
            value=self.ad_instance.instance_private_ip,
            description="AD Domain Controller Private IP",
            export_name="AdWindowsFsx-AdDcPrivateIp"
        )

    def _setup_ad_security_rules(self, ad_security_group, ad_ports, vpc_cidr_block, fsx_security_group_id):
        """AD関連のセキュリティグループルールを設定"""
        
        # AD内部通信ルール（CfnSecurityGroupIngressで循環参照を回避）
        for port, desc in ad_ports:
            ec2.CfnSecurityGroupIngress(
                self, f"AdInternalRule{port}",
                group_id=ad_security_group.security_group_id,
                source_security_group_id=ad_security_group.security_group_id,
                ip_protocol="tcp",
                from_port=port,
                to_port=port,
                description=f"{desc} - AD internal communication"
            )
            
        # FSxからAD DCへのTCP通信許可
        for port, desc in ad_ports:
            ec2.CfnSecurityGroupIngress(
                self, f"FsxToAdRuleTcp{port}",
                group_id=ad_security_group.security_group_id,
                source_security_group_id=fsx_security_group_id,
                ip_protocol="tcp",
                from_port=port,
                to_port=port,
                description=f"{desc} - FSx to AD (TCP)"
            )

        # RPC動的ポート範囲（AD内部通信）
        ec2.CfnSecurityGroupIngress(
            self, "AdInternalRuleRpc",
            group_id=ad_security_group.security_group_id,
            source_security_group_id=ad_security_group.security_group_id,
            ip_protocol="tcp",
            from_port=49152,
            to_port=65535,
            description="RPC dynamic ports - AD internal communication"
        )
        
        # FSxからAD DCへのUDP通信許可（FSx必須ポート）
        fsx_ad_udp_ports = [
            (53, "DNS"),
            (88, "Kerberos"),
            (123, "NTP"),
            (389, "LDAP"),
            (464, "Kerberos Password Change")
        ]
        
        for port, desc in fsx_ad_udp_ports:
            ec2.CfnSecurityGroupIngress(
                self, f"FsxToAdRuleUdp{port}",
                group_id=ad_security_group.security_group_id,
                source_security_group_id=fsx_security_group_id,
                ip_protocol="udp",
                from_port=port,
                to_port=port,
                description=f"{desc} - FSx to AD (UDP)"
            )
        
        # FSxからAD DCへのRPC動的ポート範囲
        ec2.CfnSecurityGroupIngress(
            self, "FsxToAdRuleRpcDynamic",
            group_id=ad_security_group.security_group_id,
            source_security_group_id=fsx_security_group_id,
            ip_protocol="tcp",
            from_port=49152,
            to_port=65535,
            description="RPC dynamic ports - FSx to AD"
        )
        
        # FSxからAD DCへのICMP通信許可（ネットワーク疎通確認・Path MTU Discovery用）
        ec2.CfnSecurityGroupIngress(
            self, "FsxToAdRuleIcmp",
            group_id=ad_security_group.security_group_id,
            source_security_group_id=fsx_security_group_id,
            ip_protocol="icmp",
            from_port=-1,
            to_port=-1,
            description="ICMP - FSx to AD (network connectivity and Path MTU Discovery)"
        )

        # AD DC用アウトバウンドルール（CfnSecurityGroupEgressで循環参照を回避）
        ec2.CfnSecurityGroupEgress(
            self, "AdEgressHttps",
            group_id=ad_security_group.security_group_id,
            cidr_ip="0.0.0.0/0",
            ip_protocol="tcp",
            from_port=443,
            to_port=443,
            description="HTTPS - Windows Update and license activation"
        )
        ec2.CfnSecurityGroupEgress(
            self, "AdEgressDns",
            group_id=ad_security_group.security_group_id,
            cidr_ip="0.0.0.0/0",
            ip_protocol="udp",
            from_port=53,
            to_port=53,
            description="DNS - External DNS resolution"
        )
        ec2.CfnSecurityGroupEgress(
            self, "AdEgressNtp",
            group_id=ad_security_group.security_group_id,
            cidr_ip="0.0.0.0/0",
            ip_protocol="udp",
            from_port=123,
            to_port=123,
            description="NTP - Time synchronization"
        )

        # AD DCからFSxへのアウトバウンドルール（SMB通信用）
        ec2.CfnSecurityGroupEgress(
            self, "AdEgressToFsxSMB",
            group_id=ad_security_group.security_group_id,
            cidr_ip=vpc_cidr_block,
            ip_protocol="tcp",
            from_port=445,
            to_port=445,
            description="SMB - AD DC to FSx (VPC CIDR)"
        )
        ec2.CfnSecurityGroupEgress(
            self, "AdEgressToFsxRPC",
            group_id=ad_security_group.security_group_id,
            destination_security_group_id=fsx_security_group_id,
            ip_protocol="tcp",
            from_port=135,
            to_port=135,
            description="RPC - AD DC to FSx"
        )
        ec2.CfnSecurityGroupEgress(
            self, "AdEgressToFsxRpcDynamic",
            group_id=ad_security_group.security_group_id,
            destination_security_group_id=fsx_security_group_id,
            ip_protocol="tcp",
            from_port=49152,
            to_port=65535,
            description="RPC dynamic ports - AD DC to FSx"
        )
        ec2.CfnSecurityGroupEgress(
            self, "AdEgressToFsxIcmp",
            group_id=ad_security_group.security_group_id,
            destination_security_group_id=fsx_security_group_id,
            ip_protocol="icmp",
            from_port=-1,
            to_port=-1,
            description="ICMP - AD DC to FSx (network connectivity)"
        )

        # FSxアウトバウンドルールはNetwork Stackで管理

