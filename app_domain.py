#!/usr/bin/env python3
import os
import aws_cdk as cdk
from ad_windows_fsx.ad_domain_stack import AdDomainStack

app = cdk.App()

# CDKコンテキストからパラメータを取得（cdk.jsonで一元管理）
windows_version = app.node.try_get_context("windows-version") or "2022"
windows_language = app.node.try_get_context("windows-language") or "Japanese"
key_pair_name = app.node.try_get_context("key-pair-name")

# Stack名にユーザー名を追加（リソース名の一意性確保）
# スタック名は英数字とハイフンのみ許可されるため、ドットをハイフンに置換
stack_suffix = os.getenv('USER', 'Unknown').replace('.', '-')

AdDomainStack(
    app, f"AdWindowsFsxDomainStack-{stack_suffix}",
    windows_version=windows_version,
    windows_language=windows_language,
    key_pair_name=key_pair_name,
    description="Active Directory Domain Controller stack with verification",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'), 
        region=os.getenv('CDK_DEFAULT_REGION')
    )
)

app.synth()