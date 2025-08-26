#!/usr/bin/env python3
import os
import aws_cdk as cdk
from ad_windows_fsx.ad_application_stack import AdApplicationStack

app = cdk.App()

# CDKコンテキストからパラメータを取得（cdk.jsonで一元管理）
windows_version = app.node.try_get_context("windows-version") or "2022"
windows_language = app.node.try_get_context("windows-language") or "Japanese"
key_pair_name = app.node.try_get_context("key-pair-name")

# FSx設定をコンテキストから取得（cdk.jsonで一元管理）
fsx_storage_capacity = app.node.try_get_context("fsx-storage-capacity") or 32
fsx_storage_type = app.node.try_get_context("fsx-storage-type") or "SSD"
fsx_deployment_type = app.node.try_get_context("fsx-deployment-type") or "SINGLE_AZ_2"
fsx_throughput_capacity = app.node.try_get_context("fsx-throughput-capacity") or 8

# Stack名にユーザー名を追加（リソース名の一意性確保）
# スタック名は英数字とハイフンのみ許可されるため、ドットをハイフンに置換
stack_suffix = os.getenv('USER', 'Unknown').replace('.', '-')

AdApplicationStack(
    app, f"AdWindowsFsxApplicationStack-{stack_suffix}",
    windows_version=windows_version,
    windows_language=windows_language,
    key_pair_name=key_pair_name,
    fsx_storage_capacity=fsx_storage_capacity,
    fsx_storage_type=fsx_storage_type,
    fsx_deployment_type=fsx_deployment_type,
    fsx_throughput_capacity=fsx_throughput_capacity,
    description="Application stack with Windows EC2 and FSx",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'), 
        region=os.getenv('CDK_DEFAULT_REGION')
    )
)

app.synth()