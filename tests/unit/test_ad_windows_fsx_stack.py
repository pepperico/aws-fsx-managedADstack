import aws_cdk as core
import aws_cdk.assertions as assertions

from ad_windows_fsx.ad_windows_fsx_stack import AdWindowsFsxStack

# サンプルテスト。
# これを実行するには、プロジェクトのルートディレクトリから `python -m pytest` を実行してください

def test_vpc_created():
    app = core.App()
    stack = AdWindowsFsxStack(app, "ad-windows-fsx")
    template = assertions.Template.from_stack(stack)

    # VPCが作成されることを確認
    template.has_resource_properties("AWS::EC2::VPC", {
        "CidrBlock": "10.0.0.0/16"
    })

def test_ec2_instances_created():
    app = core.App()
    stack = AdWindowsFsxStack(app, "ad-windows-fsx")
    template = assertions.Template.from_stack(stack)

    # AD DCとWindows EC2インスタンスが作成されることを確認
    template.resource_count_is("AWS::EC2::Instance", 2)

def test_fsx_file_system_created():
    app = core.App()
    stack = AdWindowsFsxStack(app, "ad-windows-fsx")
    template = assertions.Template.from_stack(stack)

    # FSx File Systemが作成されることを確認
    template.has_resource_properties("AWS::FSx::FileSystem", {
        "FileSystemType": "WINDOWS"
    })

def test_security_groups_created():
    app = core.App()
    stack = AdWindowsFsxStack(app, "ad-windows-fsx")
    template = assertions.Template.from_stack(stack)

    # セキュリティグループが適切に作成されることを確認（3つ：AD、Windows、FSx）
    template.resource_count_is("AWS::EC2::SecurityGroup", 3)

def test_vpc_endpoints_created():
    app = core.App()
    stack = AdWindowsFsxStack(app, "ad-windows-fsx")
    template = assertions.Template.from_stack(stack)

    # VPCエンドポイントが作成されることを確認（SSM、SSM Messages）
    template.resource_count_is("AWS::EC2::VPCEndpoint", 2)