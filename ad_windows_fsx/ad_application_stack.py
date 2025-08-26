from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_fsx as fsx,
    CfnOutput,
    Fn,
)
from constructs import Construct

class AdApplicationStack(Stack):
    """
    Application Stack: Windows EC2, FSx などのアプリケーション層リソース
    
    このスタックには以下が含まれます:
    - Windows EC2インスタンス（ドメインメンバー用）
    - FSx for Windows File Server（AD統合）
    - アプリケーション関連のセキュリティグループルール
    """

    def __init__(self, scope: Construct, construct_id: str, 
                 windows_version: str = "2022", 
                 windows_language: str = "Japanese", 
                 key_pair_name: str = None,
                 fsx_storage_capacity: int = 32,
                 fsx_storage_type: str = "SSD",
                 fsx_deployment_type: str = "SINGLE_AZ_2",
                 fsx_throughput_capacity: int = 8,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Network Stackからの参照
        vpc_id = Fn.import_value("AdWindowsFsx-VpcId")
        vpc_cidr_block = Fn.import_value("AdWindowsFsx-VpcCidrBlock")
        private_subnet_id1 = Fn.import_value("AdWindowsFsx-PrivateSubnetId1")
        private_subnet_id2 = Fn.import_value("AdWindowsFsx-PrivateSubnetId2")
        private_route_table_id1 = Fn.import_value("AdWindowsFsx-PrivateRouteTableId1")
        private_route_table_id2 = Fn.import_value("AdWindowsFsx-PrivateRouteTableId2")
        windows_security_group_id = Fn.import_value("AdWindowsFsx-WindowsSecurityGroupId")
        fsx_security_group_id = Fn.import_value("AdWindowsFsx-FsxSecurityGroupId")
        ad_security_group_id = Fn.import_value("AdWindowsFsx-AdSecurityGroupId")
        ec2_role_arn = Fn.import_value("AdWindowsFsx-Ec2RoleArn")

        # AD Stackからの参照
        ad_dc_private_ip = Fn.import_value("AdWindowsFsx-AdDcPrivateIp")
        # domain_status = Fn.import_value("AdWindowsFsx-DomainStatus")  # 必要に応じて使用

        # Cross-stack参照でのインポート（VPCは直接参照せず、Subnet IDsのみ使用）
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
            (636, "LDAPS"),
            (3268, "Global Catalog"),
            (3269, "Global Catalog SSL"),
            (9389, "AD DS Web Services")  # Single-AZ 2/Multi-AZ必須
        ]

        # Windows EC2用ユーザーデータ（AD DC IPアドレスを取得）
        windows_user_data = ec2.UserData.for_windows()
        
        # CloudFormation関数でAD DC IPを取得
        ad_dc_ip_ref = Fn.import_value("AdWindowsFsx-AdDcPrivateIp")
        
        windows_user_data.add_commands(
            "# Windows EC2 セットアップログ出力開始",
            "Write-Host \"Starting Windows EC2 setup process...\"",
            "$LogFile = 'C:\\Windows\\Temp\\windows-setup.log'",
            "Start-Transcript -Path $LogFile -Append",
            "",
            "# インターネット接続テスト",
            "Write-Host \"Testing internet connectivity...\"",
            "try {",
            "    $connectTest = Test-NetConnection -ComputerName microsoft.com -Port 443 -WarningAction SilentlyContinue",
            "    if ($connectTest.TcpTestSucceeded) {",
            "        Write-Host \"Internet connectivity: SUCCESS\"",
            "    } else {",
            "        Write-Host \"Internet connectivity: FAILED\"",
            "    }",
            "} catch {",
            "    Write-Host \"Internet connectivity test failed: $($_.Exception.Message)\"",
            "}",
            "",
            "# Windows Update有効性確認",
            "Write-Host \"Checking Windows Update service...\"",
            "try {",
            "    $wuService = Get-Service -Name wuauserv",
            "    Write-Host \"Windows Update service status: $($wuService.Status)\"",
            "} catch {",
            "    Write-Host \"Windows Update service check failed: $($_.Exception.Message)\"",
            "}",
            "",
            "# AD DC 接続テスト",
            "$AdDcIp = '${AdDcPrivateIp}'",
            "Write-Host \"Testing connection to AD DC: $AdDcIp\"",
            "try {",
            "    $adTest = Test-NetConnection -ComputerName $AdDcIp -Port 389 -WarningAction SilentlyContinue",
            "    if ($adTest.TcpTestSucceeded) {",
            "        Write-Host \"AD DC connectivity: SUCCESS\"",
            "    } else {",
            "        Write-Host \"AD DC connectivity: FAILED\"",
            "    }",
            "} catch {",
            "    Write-Host \"AD DC connectivity test failed: $($_.Exception.Message)\"",
            "}",
            "",
            "# リモートデスクトップを有効化",
            "Set-ItemProperty -Path \"HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\" -Name \"fDenyTSConnections\" -Value 0",
            "Enable-NetFirewallRule -DisplayGroup \"Remote Desktop\"",
            "",
            "# タイムゾーンを東京時間に変更", 
            "tzutil /s \"Tokyo Standard Time\"",
            "",
            "# 一般ユーザーを作成",
            "net user winuser Password123! /add",
            "net localgroup administrators winuser /add", 
            "net localgroup \"Remote Desktop Users\" winuser /add",
            "",
            "# DNS設定をAD DCに変更",
            "$AdDcIp = '${AdDcPrivateIp}'",
            "Write-Host \"Setting DNS server to AD DC: $AdDcIp\"",
            "try {",
            "    $adapter = Get-NetAdapter | Where-Object {$_.Status -eq 'Up' -and $_.InterfaceDescription -like '*Elastic*'}",
            "    if ($adapter) {",
            "        Set-DnsClientServerAddress -InterfaceIndex $adapter.InterfaceIndex -ServerAddresses $AdDcIp",
            "        Write-Host \"DNS server set successfully to: $AdDcIp\"",
            "    } else {",
            "        Write-Host \"ERROR: No suitable network adapter found\"",
            "    }",
            "} catch {",
            "    Write-Host \"ERROR setting DNS: $($_.Exception.Message)\"",
            "}",
            "",
            "# DNS設定確認",
            "Write-Host \"Current DNS configuration:\"",
            "Get-DnsClientServerAddress -AddressFamily IPv4",
            "",
            "# ドメイン参加（自動実行）",
            "Write-Host \"Starting domain join process...\"",
            "$domainName = 'example.com'",
            "$domainUser = 'Administrator'",
            "$domainPassword = ConvertTo-SecureString 'Password123!' -AsPlainText -Force",
            "$credential = New-Object System.Management.Automation.PSCredential($domainUser, $domainPassword)",
            "",
            "# ドメイン参加前にAD DCとの接続を再度確認",
            "Write-Host \"Final connectivity test to AD DC before domain join...\"",
            "try {",
            "    $finalTest = Test-NetConnection -ComputerName $AdDcIp -Port 389 -WarningAction SilentlyContinue",
            "    if ($finalTest.TcpTestSucceeded) {",
            "        Write-Host \"AD DC connectivity confirmed. Proceeding with domain join...\"",
            "        ",
            "        # ドメイン参加実行",
            "        try {",
            "            Add-Computer -DomainName $domainName -Credential $credential -Force -Restart",
            "            Write-Host \"Domain join initiated successfully. System will restart...\"",
            "        } catch {",
            "            Write-Host \"ERROR during domain join: $($_.Exception.Message)\"",
            "            Write-Host \"Manual domain join may be required using: Add-Computer -DomainName $domainName -Credential (Get-Credential) -Restart\"",
            "        }",
            "    } else {",
            "        Write-Host \"ERROR: Cannot connect to AD DC. Domain join skipped.\"",
            "        Write-Host \"Manual domain join required after connectivity is established.\"",
            "    }",
            "} catch {",
            "    Write-Host \"ERROR during connectivity test: $($_.Exception.Message)\"",
            "}",
            "",
            "Stop-Transcript",
            "Write-Host \"Windows EC2 setup completed\""
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

        # UserDataにCloudFormation変数を置換
        user_data_with_substitution = ec2.UserData.custom(
            Fn.sub(
                windows_user_data.render(),
                {
                    "AdDcPrivateIp": ad_dc_private_ip
                }
            )
        )

        # Windows EC2インスタンスの作成時のパラメータ準備
        instance_params = {
            "instance_type": ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.LARGE),
            "machine_image": windows_ami,
            "vpc": vpc_import,
            "vpc_subnets": ec2.SubnetSelection(subnets=[private_subnet1]),
            "security_group": windows_security_group,
            "role": ec2_role,
            "user_data": user_data_with_substitution
        }
        
        # キーペア名が指定されている場合のみkey_pairを追加
        if key_pair_name:
            instance_params["key_pair"] = ec2.KeyPair.from_key_pair_name(self, "KeyPair", key_pair_name)
        
        # Windows EC2インスタンスの作成
        self.windows_instance = ec2.Instance(self, "WindowsInstance", **instance_params)

        # デプロイメントタイプに応じたサブネット設定
        if fsx_deployment_type == "MULTI_AZ":
            fsx_subnet_ids = [private_subnet_id1, private_subnet_id2]  # Multi-AZは2つのサブネット
        else:  # SINGLE_AZ_1 または SINGLE_AZ_2
            fsx_subnet_ids = [private_subnet_id1]  # Single-AZは1つのサブネット

        # FSx for Windows File Serverの作成
        self.fsx_file_system = fsx.CfnFileSystem(
            self, "FsxFileSystem",
            file_system_type="WINDOWS",
            subnet_ids=fsx_subnet_ids,
            security_group_ids=[fsx_security_group.security_group_id],
            storage_capacity=fsx_storage_capacity,  # cdk.jsonから設定
            storage_type=fsx_storage_type,  # cdk.jsonから設定
            windows_configuration=fsx.CfnFileSystem.WindowsConfigurationProperty(
                # Self-managed Active Directory設定
                self_managed_active_directory_configuration=fsx.CfnFileSystem.SelfManagedActiveDirectoryConfigurationProperty(
                    domain_name="example.com",
                    dns_ips=[ad_dc_private_ip],  # AD DCのプライベートIP
                    file_system_administrators_group="Domain Admins",
                    # organizational_unit_distinguished_name を省略（デフォルトのComputersコンテナを使用）
                    user_name="fsxuser",  # ドメイン修飾名を使用
                    password="Password123!"  # 本番環境では AWS Secrets Manager を使用推奨
                ),
                deployment_type=fsx_deployment_type,  # cdk.jsonから設定
                throughput_capacity=fsx_throughput_capacity,  # cdk.jsonから設定
                automatic_backup_retention_days=7,
                copy_tags_to_backups=True,
                daily_automatic_backup_start_time="03:00",
                weekly_maintenance_start_time="7:03:00"
            )
        )


        # アプリケーション関連のセキュリティグループルールを設定
        self._setup_application_security_rules(
            windows_security_group_id, fsx_security_group_id, 
            ad_security_group_id, ad_ports, vpc_cidr_block
        )

        # 出力値
        CfnOutput(
            self, "WindowsInstanceId", 
            value=self.windows_instance.instance_id,
            description="Windows EC2 Instance ID"
        )

        CfnOutput(
            self, "FsxFileSystemId",
            value=self.fsx_file_system.ref,
            description="FSx File System ID"
        )


    def _setup_application_security_rules(self, windows_sg_id, fsx_sg_id, ad_sg_id, ad_ports, vpc_cidr_block):
        """アプリケーション関連のセキュリティグループルールを設定"""
        
        # Windows EC2用インバウンドルール（AD DCからの応答受信用）
        for port, desc in ad_ports:
            ec2.CfnSecurityGroupIngress(
                self, f"AdToWindowsRule{port}",
                group_id=windows_sg_id,
                source_security_group_id=ad_sg_id,
                ip_protocol="tcp",
                from_port=port,
                to_port=port,
                description=f"{desc} - AD to Windows EC2 (response)"
            )
        
        # Windows EC2用追加インバウンドルール（RDP、管理用）
        ec2.CfnSecurityGroupIngress(
            self, "WindowsInboundRdp",
            group_id=windows_sg_id,
            cidr_ip=vpc_cidr_block,
            ip_protocol="tcp", 
            from_port=3389,
            to_port=3389,
            description="RDP - Remote Desktop access from VPC"
        )

        # Windows EC2用インバウンドルール（ICMP）
        ec2.CfnSecurityGroupIngress(
            self, "WindowsInboundIcmp",
            group_id=windows_sg_id,
            cidr_ip=vpc_cidr_block,
            ip_protocol="icmp",
            from_port=-1,
            to_port=-1,
            description="ICMP - Network connectivity from VPC"
        )

        # Windows EC2からADへのアクセス許可（アウトバウンド用のインバウンド許可）
        for port, desc in ad_ports:
            ec2.CfnSecurityGroupIngress(
                self, f"WindowsToAdRule{port}",
                group_id=ad_sg_id,
                source_security_group_id=windows_sg_id,
                ip_protocol="tcp",
                from_port=port,
                to_port=port,
                description=f"{desc} - Windows EC2 to AD"
            )

        # FSxからADへのアクセス許可はDomain Stackで管理（重複を回避）
        # Domain StackでFSx→ADの全ルール（TCP/UDP/ICMP）を設定済み

        # FSxファイル共有アクセス用ポート（Windows EC2からのアクセス）
        ec2.CfnSecurityGroupIngress(
            self, "WindowsToFsxRuleSMB",
            group_id=fsx_sg_id,
            cidr_ip=vpc_cidr_block,
            ip_protocol="tcp",
            from_port=445,
            to_port=445,
            description="SMB - Windows EC2 to FSx (VPC CIDR)"
        )

        ec2.CfnSecurityGroupIngress(
            self, "WindowsToFsxRuleRPC",
            group_id=fsx_sg_id,
            source_security_group_id=windows_sg_id,
            ip_protocol="tcp",
            from_port=135,
            to_port=135,
            description="RPC - Windows EC2 to FSx"
        )

        ec2.CfnSecurityGroupIngress(
            self, "WindowsToFsxRuleRpcDynamic",
            group_id=fsx_sg_id,
            source_security_group_id=windows_sg_id,
            ip_protocol="tcp",
            from_port=49152,
            to_port=65535,
            description="RPC dynamic ports - Windows EC2 to FSx"
        )

        # FSxファイル共有アクセス用ポート（AD DCからのアクセス）
        ec2.CfnSecurityGroupIngress(
            self, "AdToFsxRuleSMB",
            group_id=fsx_sg_id,
            cidr_ip=vpc_cidr_block,
            ip_protocol="tcp",
            from_port=445,
            to_port=445,
            description="SMB - AD DC to FSx (VPC CIDR)"
        )

        ec2.CfnSecurityGroupIngress(
            self, "AdToFsxRuleRPC",
            group_id=fsx_sg_id,
            source_security_group_id=ad_sg_id,
            ip_protocol="tcp",
            from_port=135,
            to_port=135,
            description="RPC - AD DC to FSx"
        )

        ec2.CfnSecurityGroupIngress(
            self, "AdToFsxRuleRpcDynamic",
            group_id=fsx_sg_id,
            source_security_group_id=ad_sg_id,
            ip_protocol="tcp",
            from_port=49152,
            to_port=65535,
            description="RPC dynamic ports - AD DC to FSx"
        )

        # ICMP通信許可（AD DC ↔ FSx）
        ec2.CfnSecurityGroupIngress(
            self, "AdToFsxRuleIcmp",
            group_id=fsx_sg_id,
            source_security_group_id=ad_sg_id,
            ip_protocol="icmp",
            from_port=-1,
            to_port=-1,
            description="ICMP - AD DC to FSx (network connectivity)"
        )

        # ICMP通信許可（Windows EC2 ↔ FSx）
        ec2.CfnSecurityGroupIngress(
            self, "WindowsToFsxRuleIcmp",
            group_id=fsx_sg_id,
            source_security_group_id=windows_sg_id,
            ip_protocol="icmp",
            from_port=-1,
            to_port=-1,
            description="ICMP - Windows EC2 to FSx (network connectivity)"
        )


        # Windows EC2からADへのアウトバウンドルール（ドメイン参加用）
        for port, desc in ad_ports:
            ec2.CfnSecurityGroupEgress(
                self, f"WindowsEgressToAd{port}",
                group_id=windows_sg_id,
                destination_security_group_id=ad_sg_id,
                ip_protocol="tcp",
                from_port=port,
                to_port=port,
                description=f"{desc} - Windows EC2 to AD"
            )

        # Windows EC2からADへのアウトバウンドルール（UDP）
        udp_ad_ports = [
            (53, "DNS"),
            (88, "Kerberos"),
            (123, "NTP"), 
            (389, "LDAP"),
            (464, "Kerberos Password Change")
        ]
        
        for port, desc in udp_ad_ports:
            ec2.CfnSecurityGroupEgress(
                self, f"WindowsEgressToAdUdp{port}",
                group_id=windows_sg_id,
                destination_security_group_id=ad_sg_id,
                ip_protocol="udp",
                from_port=port,
                to_port=port,
                description=f"{desc} - Windows EC2 to AD (UDP)"
            )

        # Windows EC2からADへのICMP通信
        ec2.CfnSecurityGroupEgress(
            self, "WindowsEgressToAdIcmp",
            group_id=windows_sg_id,
            destination_security_group_id=ad_sg_id,
            ip_protocol="icmp",
            from_port=-1,
            to_port=-1,
            description="ICMP - Windows EC2 to AD (network connectivity)"
        )

        # Windows EC2用基本アウトバウンドルール
        ec2.CfnSecurityGroupEgress(
            self, "WindowsEgressHttps",
            group_id=windows_sg_id,
            cidr_ip="0.0.0.0/0",
            ip_protocol="tcp",
            from_port=443,
            to_port=443,
            description="HTTPS - Windows Update and software downloads"
        )
        ec2.CfnSecurityGroupEgress(
            self, "WindowsEgressDns",
            group_id=windows_sg_id,
            cidr_ip="0.0.0.0/0",
            ip_protocol="udp",
            from_port=53,
            to_port=53,
            description="DNS - External DNS resolution"
        )
        ec2.CfnSecurityGroupEgress(
            self, "WindowsEgressNtp",
            group_id=windows_sg_id,
            cidr_ip="0.0.0.0/0",
            ip_protocol="udp",
            from_port=123,
            to_port=123,
            description="NTP - Time synchronization"
        )

        # Windows EC2からFSxへのアウトバウンドルール（SMB通信用）
        ec2.CfnSecurityGroupEgress(
            self, "WindowsEgressToFsxSMB",
            group_id=windows_sg_id,
            cidr_ip=vpc_cidr_block,
            ip_protocol="tcp",
            from_port=445,
            to_port=445,
            description="SMB - Windows EC2 to FSx (VPC CIDR)"
        )
        ec2.CfnSecurityGroupEgress(
            self, "WindowsEgressToFsxRPC",
            group_id=windows_sg_id,
            destination_security_group_id=fsx_sg_id,
            ip_protocol="tcp",
            from_port=135,
            to_port=135,
            description="RPC - Windows EC2 to FSx"
        )
        ec2.CfnSecurityGroupEgress(
            self, "WindowsEgressToFsxRpcDynamic",
            group_id=windows_sg_id,
            destination_security_group_id=fsx_sg_id,
            ip_protocol="tcp",
            from_port=49152,
            to_port=65535,
            description="RPC dynamic ports - Windows EC2 to FSx"
        )
        ec2.CfnSecurityGroupEgress(
            self, "WindowsEgressToFsxIcmp",
            group_id=windows_sg_id,
            destination_security_group_id=fsx_sg_id,
            ip_protocol="icmp",
            from_port=-1,
            to_port=-1,
            description="ICMP - Windows EC2 to FSx (network connectivity)"
        )

        # FSx用アウトバウンドルールはDomain Stackで一元管理