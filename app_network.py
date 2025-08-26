#!/usr/bin/env python3
import os
import aws_cdk as cdk
from ad_windows_fsx.ad_network_stack import AdNetworkStack

app = cdk.App()

# CDKコンテキストからパラメータを取得
windows_version = app.node.try_get_context("windows-version") or "2022"
windows_language = app.node.try_get_context("windows-language") or "Japanese"
key_pair_name = app.node.try_get_context("key-pair-name")

# Stack名にユーザー名を追加（リソース名の一意性確保）
# スタック名は英数字とハイフンのみ許可されるため、ドットをハイフンに置換
stack_suffix = os.getenv('USER', 'Unknown').replace('.', '-')

AdNetworkStack(
    app, f"AdWindowsFsxNetworkStack-{stack_suffix}",
    description="Network infrastructure stack for AD + Windows + FSx environment",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'), 
        region=os.getenv('CDK_DEFAULT_REGION')
    )
)

app.synth()