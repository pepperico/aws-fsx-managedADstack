from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    CfnOutput,
)
from constructs import Construct

class AdNetworkStack(Stack):
    """
    Network Stack: AD + Windows + FSx環境の基盤ネットワークリソース
    
    このスタックには以下が含まれます:
    - VPC, Subnets, Internet Gateway, NAT Gateway
    - セキュリティグループ（ルールは他スタックで追加）
    - VPCエンドポイント（SSM, EC2, S3）
    - 共通IAMロール
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPCの作成
        self.vpc = ec2.Vpc(
            self, "AdWindowsFsxVpc",
            max_azs=2,
            nat_gateways=1,  # NAT Gatewayを有効化（インターネットアクセス用）
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PUBLIC,
                    name="Public",
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    name="PrivateWithEgress",
                    cidr_mask=24
                )
            ]
        )

        # Active Directory用セキュリティグループ
        self.ad_security_group = ec2.SecurityGroup(
            self, "AdSecurityGroup", 
            vpc=self.vpc,
            description="Security group for Active Directory Domain Controller",
            allow_all_outbound=False
        )

        # Windows EC2用セキュリティグループ
        self.windows_security_group = ec2.SecurityGroup(
            self, "WindowsSecurityGroup",
            vpc=self.vpc,
            description="Security group for Windows EC2 instance",
            allow_all_outbound=False
        )

        # FSx用セキュリティグループ
        self.fsx_security_group = ec2.SecurityGroup(
            self, "FsxSecurityGroup",
            vpc=self.vpc,
            description="Security group for FSx file system", 
            allow_all_outbound=False
        )

        # FSxからADへの必須アウトバウンドルール（修正版）
        fsx_required_tcp_ports = [53, 88, 135, 389, 445, 464, 636, 3268, 3269, 9389]  # 9389追加
        fsx_required_udp_ports = [53, 88, 123, 389, 464]
        
        # TCP アウトバウンドルール（VPC内のAD DCに限定）
        for port in fsx_required_tcp_ports:
            self.fsx_security_group.add_egress_rule(
                peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(port),
                description=f"FSx to AD - TCP {port}"
            )
        
        # UDP アウトバウンドルール（VPC内のAD DCに限定）
        for port in fsx_required_udp_ports:
            self.fsx_security_group.add_egress_rule(
                peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
                connection=ec2.Port.udp(port),
                description=f"FSx to AD - UDP {port}"
            )

        # RPC動的ポート範囲
        self.fsx_security_group.add_egress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp_range(49152, 65535),
            description="RPC dynamic ports - FSx to AD"
        )

        # ICMP通信（VPC内のAD DCとの疎通確認・Path MTU Discovery用）
        # 注意: 255.255.255.255/32 への ICMP拒否ルールは不要（AWS VPCで既に制限済み）
        self.fsx_security_group.add_egress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.all_icmp(),
            description="ICMP - FSx to AD (network connectivity and Path MTU Discovery)"
        )

        # FSx用基本アウトバウンドルール（インターネット向け）
        self.fsx_security_group.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="HTTPS - FSx license activation and updates"
        )
        self.fsx_security_group.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.udp(53),
            description="DNS - External DNS resolution"
        )
        self.fsx_security_group.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.udp(123),
            description="NTP - External time synchronization"
        )

        # EC2インスタンス用IAMロール（共通利用）
        self.ec2_role = iam.Role(
            self, "Ec2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="IAM role for EC2 instances"
        )

        # SSM Session Managerアクセス
        self.ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )

        # Directory Service権限（必要に応じて）
        self.ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMDirectoryServiceAccess")
        )

        # EC2 ReadOnly権限（インスタンス自身の情報アクセス用）
        self.ec2_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ReadOnlyAccess")
        )

        # VPCエンドポイントの作成（SSMアクセス用）
        self.vpc.add_interface_endpoint(
            "SsmVpcEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        self.vpc.add_interface_endpoint(
            "SsmMessagesVpcEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # EC2エンドポイント（インスタンスメタデータアクセス用）
        self.vpc.add_interface_endpoint(
            "Ec2VpcEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.EC2,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )


        # クロススタック参照用の出力値
        CfnOutput(
            self, "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID for AD Windows FSx environment",
            export_name="AdWindowsFsx-VpcId"
        )

        CfnOutput(
            self, "VpcCidrBlock",
            value=self.vpc.vpc_cidr_block,
            description="VPC CIDR Block for AD Windows FSx environment",
            export_name="AdWindowsFsx-VpcCidrBlock"
        )

        CfnOutput(
            self, "PrivateSubnetId1",
            value=self.vpc.private_subnets[0].subnet_id,
            description="Private Subnet ID (AZ-A)",
            export_name="AdWindowsFsx-PrivateSubnetId1"
        )

        CfnOutput(
            self, "PrivateSubnetId2", 
            value=self.vpc.private_subnets[1].subnet_id,
            description="Private Subnet ID (AZ-B)",
            export_name="AdWindowsFsx-PrivateSubnetId2"
        )

        # ルートテーブルIDのエクスポート（Warningを解決するため）
        CfnOutput(
            self, "PrivateRouteTableId1",
            value=self.vpc.private_subnets[0].route_table.route_table_id,
            description="Private Route Table ID (AZ-A)",
            export_name="AdWindowsFsx-PrivateRouteTableId1"
        )

        CfnOutput(
            self, "PrivateRouteTableId2",
            value=self.vpc.private_subnets[1].route_table.route_table_id,
            description="Private Route Table ID (AZ-B)",
            export_name="AdWindowsFsx-PrivateRouteTableId2"
        )

        CfnOutput(
            self, "AdSecurityGroupId",
            value=self.ad_security_group.security_group_id,
            description="Security Group ID for Active Directory",
            export_name="AdWindowsFsx-AdSecurityGroupId"
        )

        CfnOutput(
            self, "WindowsSecurityGroupId",
            value=self.windows_security_group.security_group_id,
            description="Security Group ID for Windows EC2",
            export_name="AdWindowsFsx-WindowsSecurityGroupId"
        )

        CfnOutput(
            self, "FsxSecurityGroupId",
            value=self.fsx_security_group.security_group_id,
            description="Security Group ID for FSx",
            export_name="AdWindowsFsx-FsxSecurityGroupId"
        )


        CfnOutput(
            self, "Ec2RoleArn",
            value=self.ec2_role.role_arn,
            description="IAM Role ARN for EC2 instances",
            export_name="AdWindowsFsx-Ec2RoleArn"
        )