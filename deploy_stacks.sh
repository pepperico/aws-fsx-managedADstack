#!/bin/bash

# AD + Windows + FSx 3-Phase Stack Deployment Script
# Usage: ./deploy_stacks.sh [OPTIONS]
# Options:
#   --profile PROFILE           AWS profile name
#   --help                      Show this help message

set -e  # Exit on error

# Default values
AWS_PROFILE=""
DRY_RUN=false
MAX_PHASE=3
INTERACTIVE=true

# Color output definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Help display function
show_help() {
    echo "AD + Windows + FSx 3-Phase Stack Deployment Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --profile PROFILE           AWS profile name"
    echo "  --phase PHASE               Deploy up to specified phase (1, 2, or 3)"
    echo "  --dry-run                   Dry run mode (syntax check only)"
    echo "  --non-interactive, --batch  Non-interactive mode (for automation)"
    echo "  --help                      Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 --profile cm                     # Default: Interactive mode with phased deployment"
    echo "  $0 --profile cm --non-interactive   # For automation scripts"
    echo "  $0 --phase 1                        # Deploy Phase 1 only (Network)"
    echo "  $0 --phase 2                        # Deploy Phase 1-2 (Network + AD Domain)"
    echo "  $0 --phase 3                        # Phase 3 only with manual confirmation"
    echo "  $0 --dry-run                        # Syntax check only"
    echo ""
    echo "Note: Interactive mode is default due to mandatory manual FSx configuration steps."
    echo ""
}

# Parameter parsing
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        --phase)
            MAX_PHASE="$2"
            if [[ ! "$MAX_PHASE" =~ ^[1-3]$ ]]; then
                echo -e "${RED}[ERROR]${NC} Invalid phase number: $MAX_PHASE. Use 1, 2, or 3."
                exit 1
            fi
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --non-interactive|--batch)
            INTERACTIVE=false
            shift
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

# 仮想環境の確認
echo -e "${BLUE}[INFO]${NC} Checking Python virtual environment..."
if [[ ! -d ".venv" ]]; then
    echo -e "${YELLOW}[WARN]${NC} Virtual environment not found. Creating..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

# Check AWS credentials (skip for dry run)
if [[ "$DRY_RUN" == "false" ]]; then
    echo -e "${BLUE}[INFO]${NC} Checking AWS credentials..."
    AWS_CLI_OPTS=""
    if [[ -n "$AWS_PROFILE" ]]; then
        AWS_CLI_OPTS="--profile $AWS_PROFILE"
        export AWS_PROFILE
    fi

    if ! aws sts get-caller-identity $AWS_CLI_OPTS > /dev/null 2>&1; then
        echo -e "${RED}[ERROR]${NC} AWS credentials not configured or expired."
        echo "Please run: aws configure or source your credentials"
        exit 1
    fi

    ACCOUNT_ID=$(aws sts get-caller-identity $AWS_CLI_OPTS --query Account --output text)
    REGION=${AWS_DEFAULT_REGION:-$(aws configure get region $AWS_CLI_OPTS)}
    echo -e "${GREEN}[SUCCESS]${NC} AWS Account: $ACCOUNT_ID, Region: $REGION"

    # Check CDK bootstrap
    echo -e "${BLUE}[INFO]${NC} Checking CDK bootstrap..."
    if [[ -n "$AWS_PROFILE" ]]; then
        cdk bootstrap aws://$ACCOUNT_ID/$REGION --profile $AWS_PROFILE
    else
        cdk bootstrap aws://$ACCOUNT_ID/$REGION
    fi
else
    echo -e "${BLUE}[INFO]${NC} Skipping AWS credentials check (dry run mode)"
fi

# Display parameters
echo -e "${BLUE}[INFO]${NC} Deployment parameters:"
echo "  - AWS Profile: ${AWS_PROFILE:-'default'}"
echo "  - Max Phase: $MAX_PHASE"
echo "  - Interactive Mode: $INTERACTIVE"
echo "  - Dry Run: $DRY_RUN"
echo ""

# Warning for non-interactive mode
if [[ "$INTERACTIVE" == "false" && "$DRY_RUN" == "false" ]]; then
    echo -e "${YELLOW}[WARNING]${NC} Non-interactive mode detected!"
    echo -e "${RED}[IMPORTANT]${NC} FSx for Windows Server requires mandatory manual configuration:"
    echo "  1. AD DC full startup verification"
    echo "  2. Service account permission delegation to 'fsxuser'"
    echo "  3. Manual confirmation before Phase 3 execution"
    echo ""
    echo -e "${YELLOW}[NOTICE]${NC} Please ensure all manual steps are completed before deployment."
    echo "Continuing in 10 seconds... (Ctrl+C to cancel)"
    sleep 10
fi

# CDKコンテキスト設定（cdk.jsonで一元管理）
CDK_CONTEXT=""

# Dry run モード
if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${YELLOW}[DRY RUN]${NC} Performing syntax check only..."
    
    profile_opt=""
    if [[ -n "$AWS_PROFILE" ]]; then
        profile_opt="--profile $AWS_PROFILE"
    fi
    
    echo -e "${BLUE}[INFO]${NC} Checking Network Stack syntax..."
    cdk synth -a "python app_network.py" $CDK_CONTEXT $profile_opt --quiet
    
    echo -e "${BLUE}[INFO]${NC} Checking Domain Stack syntax..."
    cdk synth -a "python app_domain.py" $CDK_CONTEXT $profile_opt --quiet
    
    echo -e "${BLUE}[INFO]${NC} Checking Application Stack syntax..."
    cdk synth -a "python app_application.py" $CDK_CONTEXT $profile_opt --quiet
    
    echo -e "${GREEN}[SUCCESS]${NC} All stacks passed syntax check!"
    exit 0
fi

# デプロイ実行関数
deploy_stack() {
    local stack_name=$1
    local app_file=$2
    local description=$3
    
    echo -e "${BLUE}[INFO]${NC} Deploying $description..."
    echo "Stack: $stack_name"
    echo "App: $app_file"
    profile_opt=""
    if [[ -n "$AWS_PROFILE" ]]; then
        profile_opt="--profile $AWS_PROFILE"
    fi
    echo "Command: cdk deploy -a \"python $app_file\" $CDK_CONTEXT $profile_opt --require-approval never"
    echo ""
    
    if cdk deploy -a "python $app_file" $CDK_CONTEXT $profile_opt --require-approval never; then
        echo -e "${GREEN}[SUCCESS]${NC} $description deployed successfully!"
        echo ""
    else
        echo -e "${RED}[ERROR]${NC} Failed to deploy $description"
        echo "Please check the error messages above and resolve the issues."
        exit 1
    fi
}

# ユーザー確認プロンプト関数
confirm_continue() {
    local message="$1"
    
    if [[ "$INTERACTIVE" == "true" ]]; then
        echo -e "${YELLOW}[CONFIRM]${NC} $message"
        read -p "Do you want to continue? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}[INFO]${NC} Deployment cancelled by user."
            exit 0
        fi
    fi
}

# FSx前提条件チェック関数
check_fsx_prerequisites() {
    local stack_name="$1"
    
    echo -e "${BLUE}[INFO]${NC} FSx for Windows Server prerequisites check..."
    
    # Get AD DC instance ID
    profile_opt=""
    if [[ -n "$AWS_PROFILE" ]]; then
        profile_opt="--profile $AWS_PROFILE"
    fi
    
    local ad_instance_id=$(aws cloudformation describe-stacks $profile_opt \
        --stack-name "AdWindowsFsxDomainStack-$USER_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`AdDcInstanceId`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [[ -z "$ad_instance_id" ]]; then
        echo -e "${RED}[ERROR]${NC} AD DC instance ID not found. Please verify that Domain Stack is deployed successfully."
        return 1
    fi
    
    echo -e "${GREEN}[SUCCESS]${NC} AD DC instance ID: $ad_instance_id"
    
    # Display FSx important requirements
    echo ""
    echo -e "${RED}[IMPORTANT]${NC} The following manual steps are required for FSx for Windows Server:"
    echo ""
    echo -e "${YELLOW}1. Verify AD DC full startup${NC}"
    echo "   Connect via SSM and confirm domain creation completion:"
    echo "   aws ssm start-session --target $ad_instance_id $profile_opt"
    echo ""
    echo -e "${YELLOW}2. Delegate permissions to 'fsxuser' account${NC}"
    echo "   Set the following permissions in Active Directory Users and Computers:"
    echo "   - Reset Password"
    echo "   - Read and write Account Restrictions"
    echo "   - Validated write to DNS host name"
    echo "   - Validated write to service principal name"
    echo "   - Create Computer Objects"
    echo "   - Delete Computer Objects"
    echo ""
    echo -e "${YELLOW}3. Configuration guide${NC}"
    echo "   Detailed steps: https://docs.aws.amazon.com/fsx/latest/WindowsGuide/assign-permissions-to-service-account.html"
    echo ""
    
    if [[ "$INTERACTIVE" == "true" ]]; then
        echo -e "${RED}[WARNING]${NC} FSx creation will fail if the above manual configuration is not completed."
        echo ""
        read -p "Have you completed the manual configuration? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}[INFO]${NC} Please complete manual configuration and then resume FSx deployment with:"
            echo "./deploy_stacks.sh --phase 3 $([[ -n "$AWS_PROFILE" ]] && echo "--profile $AWS_PROFILE")"
            exit 0
        fi
    else
        echo -e "${YELLOW}[NOTICE]${NC} Non-interactive mode. Please ensure manual configuration is completed."
        echo "Continuing deployment in 5 seconds..."
        sleep 5
    fi
}

# スタック状態確認関数
check_stack_status() {
    local stack_name=$1
    local expected_status=$2
    
    echo -e "${BLUE}[INFO]${NC} Checking stack status: $stack_name"
    
    profile_opt=""
    if [[ -n "$AWS_PROFILE" ]]; then
        profile_opt="--profile $AWS_PROFILE"
    fi
    status=$(aws cloudformation describe-stacks $profile_opt --stack-name "$stack_name" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$status" == "$expected_status" ]]; then
        echo -e "${GREEN}[SUCCESS]${NC} Stack $stack_name is in $status state"
        return 0
    else
        echo -e "${YELLOW}[WARN]${NC} Stack $stack_name status: $status (expected: $expected_status)"
        return 1
    fi
}

# ユーザー名取得（スタック名に使用）
# スタック名は英数字とハイフンのみ許可されるため、ドットをハイフンに置換
USER_NAME=${USER:-"Unknown"}
USER_NAME=${USER_NAME//\./-}

# デプロイ開始
echo -e "${BLUE}[INFO]${NC} Starting deployment (Phase 1-$MAX_PHASE)..."
echo "User: $USER_NAME"
echo "Max Phase: $MAX_PHASE"
echo ""

# Phase 1: Network Stack
echo -e "${YELLOW}=== Phase 1: Network Infrastructure ===${NC}"
confirm_continue "Deploy Network Stack."
deploy_stack "AdWindowsFsxNetworkStack-$USER_NAME" "app_network.py" "Network Infrastructure"

if [[ $MAX_PHASE -ge 2 ]]; then
    # Phase 2: AD Domain Stack
    echo -e "${YELLOW}=== Phase 2: Active Directory Domain ===${NC}"
    confirm_continue "Deploy AD Domain Controller Stack."
    deploy_stack "AdWindowsFsxDomainStack-$USER_NAME" "app_domain.py" "Active Directory Domain Controller"

    # AD Domain creation verification (up to 15 minutes wait)
    echo -e "${BLUE}[INFO]${NC} AD Domain creation is in progress (up to ~15 minutes)..."
    echo -e "${YELLOW}[IMPORTANT]${NC} Please wait for AD DC full startup and domain creation completion."
    
    if [[ $MAX_PHASE -ge 3 ]]; then
        echo ""
        echo -e "${RED}[NEXT STEPS]${NC} Manual configuration required before Phase 3 (FSx) execution:"
        echo ""
        
        # Get and display AD DC instance ID
        profile_opt=""
        if [[ -n "$AWS_PROFILE" ]]; then
            profile_opt="--profile $AWS_PROFILE"
        fi
        
        echo "1. Connect to AD DC via SSM and confirm domain creation completion:"
        ad_instance_id=$(aws cloudformation describe-stacks $profile_opt \
            --stack-name "AdWindowsFsxDomainStack-$USER_NAME" \
            --query 'Stacks[0].Outputs[?OutputKey==`AdDcInstanceId`].OutputValue' \
            --output text 2>/dev/null || echo "<Retrieving...>")
        echo "   aws ssm start-session --target $ad_instance_id $profile_opt"
        echo ""
        echo "2. Delegate permissions to 'fsxuser' account in Active Directory Users and Computers:"
        echo "   Detailed steps: See 'FSx Service Account Permissions' in README.md"
        echo ""
        
        if [[ "$INTERACTIVE" == "true" ]]; then
            echo -e "${YELLOW}[CHOICE]${NC} Do you want to continue with Phase 3 (FSx) deployment?"
            echo "y: Execute Phase 3 (with manual configuration confirmation)"
            echo "n: Stop at Phase 2 (manually execute Phase 3 later)"
            read -p "Please choose (y/N): " -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                MAX_PHASE=2
                echo -e "${BLUE}[INFO]${NC} Stopping at Phase 2. Continue after manual configuration with:"
                echo "./deploy_stacks.sh --phase 3 $([[ -n "$AWS_PROFILE" ]] && echo "--profile $AWS_PROFILE")"
            fi
        fi
    fi
else
    echo -e "${BLUE}[INFO]${NC} Stopping at Phase 1 as requested (--phase $MAX_PHASE)"
fi

if [[ $MAX_PHASE -ge 3 ]]; then
    # Phase 3: Application Stack
    echo -e "${YELLOW}=== Phase 3: Application Layer ===${NC}"
    
    # FSx前提条件チェック
    check_fsx_prerequisites "AdWindowsFsxApplicationStack-$USER_NAME"
    
    confirm_continue "Deploy FSx for Windows Server and Windows EC2 Stack."
    deploy_stack "AdWindowsFsxApplicationStack-$USER_NAME" "app_application.py" "Application Layer (Windows EC2, FSx)"
else
    echo -e "${BLUE}[INFO]${NC} Stopping at Phase $MAX_PHASE as requested"
fi

# 最終確認
echo -e "${GREEN}=== Deployment Completed Successfully (Phase 1-$MAX_PHASE)! ===${NC}"
echo ""
echo "Deployed Stacks:"
echo "1. Network Stack: AdWindowsFsxNetworkStack-$USER_NAME"
if [[ $MAX_PHASE -ge 2 ]]; then
    echo "2. Domain Stack:  AdWindowsFsxDomainStack-$USER_NAME"
fi
if [[ $MAX_PHASE -ge 3 ]]; then
    echo "3. App Stack:     AdWindowsFsxApplicationStack-$USER_NAME"
fi
echo ""

# Phase別のNext Steps
if [[ $MAX_PHASE -eq 1 ]]; then
    echo -e "${BLUE}[Next Steps]${NC}"
    echo "1. Execute next phase:"
    echo "   ./deploy_stacks.sh --phase 2 $([[ -n "$AWS_PROFILE" ]] && echo "--profile $AWS_PROFILE")"
    echo "   or"
    echo "   ./deploy_stacks.sh --interactive $([[ -n "$AWS_PROFILE" ]] && echo "--profile $AWS_PROFILE") # Recommended"
elif [[ $MAX_PHASE -eq 2 ]]; then
    echo -e "${BLUE}[Next Steps]${NC}"
    echo -e "${RED}[IMPORTANT]${NC} Manual configuration required before FSx deployment:"
    echo ""
    echo "1. Verify AD DC full startup (wait 5-15 minutes):"
    profile_opt=""
    if [[ -n "$AWS_PROFILE" ]]; then
        profile_opt="--profile $AWS_PROFILE"
    fi
    ad_instance_id=$(aws cloudformation describe-stacks $profile_opt \
        --stack-name "AdWindowsFsxDomainStack-$USER_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`AdDcInstanceId`].OutputValue' \
        --output text 2>/dev/null || echo "<Retrieval failed>")
    echo "   aws ssm start-session --target $ad_instance_id $profile_opt"
    echo ""
    echo "2. Delegate permissions to 'fsxuser' account (Active Directory Users and Computers):"
    echo "   Detailed steps: See '3. FSx Service Account Permissions' in README.md"
    echo ""
    echo "3. Execute FSx deployment after manual configuration:"
    echo "   ./deploy_stacks.sh --phase 3 $([[ -n "$AWS_PROFILE" ]] && echo "--profile $AWS_PROFILE")"
    echo "   or"
    echo "   ./deploy_stacks.sh --phase 3 --interactive $([[ -n "$AWS_PROFILE" ]] && echo "--profile $AWS_PROFILE") # Recommended"
else
    echo -e "${BLUE}[Next Steps]${NC}"
    echo "1. Verify AD DC domain creation completion (if needed)"
    echo "2. Join Windows EC2 to domain (manual):"
    echo "   Add-Computer -DomainName example.com -Credential (Get-Credential) -Restart"
    echo "3. Mount FSx file system:"
    echo "   net use Z: \\\\fs-<fsxid>.example.com\\share"
    echo ""
    echo -e "${GREEN}[COMPLETED]${NC} All stacks have been deployed successfully!"
fi
echo ""
echo -e "${BLUE}[INFO]${NC} Access the instances via Session Manager or direct RDP connection."
echo -e "${BLUE}[INFO]${NC} Check CloudWatch Logs for AD DC setup progress."