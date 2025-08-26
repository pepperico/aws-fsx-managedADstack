#!/bin/bash

# AD + Windows + FSx 3段階スタック クリーンアップスクリプト
# Usage: ./cleanup_stacks.sh [OPTIONS]
# Options:
#   --force                     Force cleanup without confirmation
#   --profile PROFILE           AWS profile name
#   --help                      Show this help message

set -e  # エラー時に停止

# カラー出力用
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# デフォルト値
FORCE=false
AWS_PROFILE=""

# ヘルプ表示
show_help() {
    echo "AD + Windows + FSx 3段階スタック クリーンアップスクリプト"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --force                     Force cleanup without confirmation"
    echo "  --profile PROFILE           AWS profile name"
    echo "  --help                      Show this help message"
    echo ""
    echo "Example:"
    echo "  $0                          # Interactive cleanup"
    echo "  $0 --force                  # Force cleanup"
    echo "  $0 --profile cm --force     # Force cleanup with specific profile"
}

# パラメータ解析
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE=true
            shift
            ;;
        --profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# AWS認証情報の確認
echo -e "${BLUE}[INFO]${NC} Checking AWS credentials..."
AWS_CLI_OPTS=""
if [[ -n "$AWS_PROFILE" ]]; then
    AWS_CLI_OPTS="--profile $AWS_PROFILE"
    export AWS_PROFILE
    echo -e "${BLUE}[INFO]${NC} Using AWS profile: $AWS_PROFILE"
fi

if ! aws sts get-caller-identity $AWS_CLI_OPTS > /dev/null 2>&1; then
    echo -e "${RED}[ERROR]${NC} AWS credentials not configured or expired."
    echo "Please run: aws configure or source your credentials"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity $AWS_CLI_OPTS --query Account --output text)
REGION=${AWS_DEFAULT_REGION:-$(aws configure get region $AWS_CLI_OPTS)}
# スタック名は英数字とハイフンのみ許可されるため、ドットをハイフンに置換
USER_NAME=${USER:-"Unknown"}
USER_NAME=${USER_NAME//\./-}

echo -e "${GREEN}[SUCCESS]${NC} AWS Account: $ACCOUNT_ID, Region: $REGION"
echo -e "${BLUE}[INFO]${NC} User: $USER_NAME"

# スタック一覧表示
echo -e "${BLUE}[INFO]${NC} Checking existing stacks..."
STACKS_TO_DELETE=(
    "AdWindowsFsxApplicationStack-$USER_NAME"
    "AdWindowsFsxDomainStack-$USER_NAME" 
    "AdWindowsFsxNetworkStack-$USER_NAME"
)

EXISTING_STACKS=()
for stack in "${STACKS_TO_DELETE[@]}"; do
    if aws cloudformation describe-stacks $AWS_CLI_OPTS --stack-name "$stack" > /dev/null 2>&1; then
        EXISTING_STACKS+=("$stack")
        status=$(aws cloudformation describe-stacks $AWS_CLI_OPTS --stack-name "$stack" --query 'Stacks[0].StackStatus' --output text)
        echo -e "${YELLOW}[FOUND]${NC} $stack ($status)"
    fi
done

if [[ ${#EXISTING_STACKS[@]} -eq 0 ]]; then
    echo -e "${GREEN}[INFO]${NC} No stacks found to delete."
    exit 0
fi

# 確認プロンプト
if [[ "$FORCE" != "true" ]]; then
    echo ""
    echo -e "${YELLOW}[WARNING]${NC} This will delete the following stacks and ALL their resources:"
    for stack in "${EXISTING_STACKS[@]}"; do
        echo "  - $stack"
    done
    echo ""
    echo -e "${RED}[WARNING]${NC} This action cannot be undone!"
    echo ""
    read -p "Are you sure you want to continue? (y/n): " confirmation
    
    if [[ ! "$confirmation" =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}[INFO]${NC} Cleanup cancelled."
        exit 0
    fi
fi

# 仮想環境の確認
if [[ -d ".venv" ]]; then
    source .venv/bin/activate
fi

# スタック削除関数
delete_stack() {
    local stack_name=$1
    local description=$2
    
    echo -e "${BLUE}[INFO]${NC} Deleting $description..."
    echo "Stack: $stack_name"
    
    if aws cloudformation describe-stacks $AWS_CLI_OPTS --stack-name "$stack_name" > /dev/null 2>&1; then
        echo "Command: aws cloudformation delete-stack $AWS_CLI_OPTS --stack-name $stack_name"
        
        if aws cloudformation delete-stack $AWS_CLI_OPTS --stack-name "$stack_name"; then
            echo -e "${BLUE}[INFO]${NC} Deletion initiated for $description"
            
            # 削除完了を待機
            echo -e "${BLUE}[INFO]${NC} Waiting for stack deletion to complete..."
            if aws cloudformation wait stack-delete-complete $AWS_CLI_OPTS --stack-name "$stack_name"; then
                echo -e "${GREEN}[SUCCESS]${NC} $description deleted successfully!"
            else
                echo -e "${RED}[ERROR]${NC} Failed to delete $description"
                echo "Please check AWS Console for detailed error information."
                return 1
            fi
        else
            echo -e "${RED}[ERROR]${NC} Failed to initiate deletion for $description"
            return 1
        fi
    else
        echo -e "${YELLOW}[WARN]${NC} Stack $stack_name not found (may have been already deleted)"
    fi
    
    echo ""
}

# クリーンアップ開始（逆順で削除）
echo -e "${BLUE}[INFO]${NC} Starting stack cleanup (reverse order)..."
echo ""

# Application Stack から削除
for stack in "${EXISTING_STACKS[@]}"; do
    case $stack in
        *ApplicationStack*)
            delete_stack "$stack" "Application Stack (Windows EC2, FSx)"
            ;;
    esac
done

# Domain Stack を削除
for stack in "${EXISTING_STACKS[@]}"; do
    case $stack in
        *DomainStack*)
            delete_stack "$stack" "Domain Stack (Active Directory)"
            ;;
    esac
done

# Network Stack を削除
for stack in "${EXISTING_STACKS[@]}"; do
    case $stack in
        *NetworkStack*)
            delete_stack "$stack" "Network Stack (VPC, Subnets, NAT)"
            ;;
    esac
done

# 最終確認
echo -e "${GREEN}=== Cleanup Completed Successfully! ===${NC}"
echo ""
echo "All stacks have been deleted:"
for stack in "${EXISTING_STACKS[@]}"; do
    echo "  ✓ $stack"
done
echo ""
echo -e "${BLUE}[INFO]${NC} All AWS resources have been cleaned up."
echo -e "${YELLOW}[INFO]${NC} Please verify in AWS Console that no unexpected resources remain."