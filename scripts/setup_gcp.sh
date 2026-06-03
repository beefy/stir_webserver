#!/bin/bash

# GCP Deployment Setup Script
# This script helps set up the necessary GCP resources for deploying the webserver

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID=""
REGION="us-central1"
SERVICE_NAME="stir-webserver"
SERVICE_ACCOUNT_NAME="github-actions-sa"
REPOSITORY_NAME="stir-webserver"

if [ "$1" = "staging" ] || [ "$1" = "--staging" ]; then
    echo -e "${BLUE}Setting up STAGING environment${NC}"
    SERVICE_NAME="stir-webserver-staging"
    SERVICE_ACCOUNT_NAME="github-actions-staging-sa"
    REPOSITORY_NAME="stir-webserver-staging"
fi

print_header() {
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}  GCP Deployment Setup for stir_webserver${NC}"
    if [ "$1" = "staging" ] || [ "$1" = "--staging" ]; then
        echo -e "${BLUE}       STAGING ENVIRONMENT${NC}"
    else
        echo -e "${BLUE}      PRODUCTION ENVIRONMENT${NC}"
    fi
    echo -e "${BLUE}======================================${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    print_step "Checking prerequisites..."

    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        print_error "gcloud CLI is not installed. Please install it from: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi

    # Check if user is authenticated
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        print_error "You are not authenticated with gcloud. Please run: gcloud auth login"
        exit 1
    fi

    print_info "Prerequisites check passed!"
}

get_project_id() {
    if [ -z "$PROJECT_ID" ]; then
        CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "")
        if [ -n "$CURRENT_PROJECT" ]; then
            echo -e "Current project: ${GREEN}$CURRENT_PROJECT${NC}"
            read -p "Use this project? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                PROJECT_ID=$CURRENT_PROJECT
            fi
        fi

        if [ -z "$PROJECT_ID" ]; then
            read -p "Enter your GCP Project ID: " PROJECT_ID
        fi
    fi

    # Set the project
    gcloud config set project $PROJECT_ID
    print_info "Using project: $PROJECT_ID"
}

enable_apis() {
    print_step "Enabling required APIs..."

    gcloud services enable run.googleapis.com
    gcloud services enable artifactregistry.googleapis.com
    gcloud services enable cloudbuild.googleapis.com
    gcloud services enable iam.googleapis.com
    gcloud services enable cloudresourcemanager.googleapis.com

    print_info "APIs enabled successfully!"
}

create_artifact_registry() {
    print_step "Creating Artifact Registry repository..."

    # Check if repository already exists
    if gcloud artifacts repositories describe $REPOSITORY_NAME --location=$REGION &>/dev/null; then
        print_warning "Repository $REPOSITORY_NAME already exists in $REGION"
    else
        gcloud artifacts repositories create $REPOSITORY_NAME \
            --repository-format=docker \
            --location=$REGION \
            --description="stir_webserver container images"
        print_info "Artifact Registry repository created!"
    fi
}

create_service_account() {
    print_step "Creating service account for GitHub Actions..."

    # Check if service account already exists
    if gcloud iam service-accounts describe "${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" &>/dev/null; then
        print_warning "Service account $SERVICE_ACCOUNT_NAME already exists"
    else
        gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
            --display-name="GitHub Actions Service Account"
        print_info "Service account created!"
    fi

    # Grant necessary permissions
    print_info "Granting permissions to service account..."

    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/run.admin"

    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/artifactregistry.writer"

    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/iam.serviceAccountUser"
}

setup_workload_identity() {
    print_step "Setting up Workload Identity Federation..."

    # Create workload identity pool
    if gcloud iam workload-identity-pools describe "github-actions-pool" --location="global" &>/dev/null; then
        print_warning "Workload identity pool already exists"
    else
        gcloud iam workload-identity-pools create "github-actions-pool" \
            --location="global" \
            --display-name="GitHub Actions Pool"
        print_info "Workload identity pool created!"
    fi

    # Create workload identity provider
    if gcloud iam workload-identity-pools providers describe "github-actions-provider" \
        --location="global" \
        --workload-identity-pool="github-actions-pool" &>/dev/null; then
        print_warning "Workload identity provider already exists"
    else
        gcloud iam workload-identity-pools providers create-oidc "github-actions-provider" \
            --location="global" \
            --workload-identity-pool="github-actions-pool" \
            --display-name="GitHub Actions Provider" \
            --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
            --attribute-condition="assertion.repository_owner == 'beefy'" \
            --issuer-uri="https://token.actions.githubusercontent.com"
        print_info "Workload identity provider created!"
    fi

    # Get project number
    PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

    # Allow GitHub Actions to impersonate the service account
    gcloud iam service-accounts add-iam-policy-binding \
        "${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/iam.workloadIdentityUser" \
        --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-actions-pool/attribute.repository/beefy/stir_webserver"

    print_info "Workload Identity Federation configured!"
}

grant_secret_manager_access() {
    print_step "Granting Cloud Run runtime service account access to Secret Manager..."

    # The default Compute Engine service account is used by Cloud Run
    # when no custom service account is specified.
    COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

    print_info "Granting roles/secretmanager.secretAccessor to $COMPUTE_SA..."

    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${COMPUTE_SA}" \
        --role="roles/secretmanager.secretAccessor"

    print_info "Secret Manager access granted!"
    print_warning "This allows the auth microservice (stir-auth-server) to read Firebase service account secrets from Secret Manager on startup."
}

print_summary() {
    print_step "Setup completed! Here's what you need to configure in GitHub:"
    echo ""
    echo -e "${YELLOW}GitHub Secrets to add:${NC}"
    echo "=============================="
    echo "GCP_PROJECT_ID: $PROJECT_ID"
    echo "SERVICE_ACCOUNT_EMAIL: ${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

    # Get the full workload identity provider name
    PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
    WORKLOAD_IDENTITY_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-actions-pool/providers/github-actions-provider"
    echo "WORKLOAD_IDENTITY_PROVIDER: $WORKLOAD_IDENTITY_PROVIDER"
    echo ""
    echo -e "${YELLOW}Additional GitHub Secrets needed:${NC}"
    echo "=============================="
    echo "MONGODB_CONNECTION_STRING: Your MongoDB Atlas connection string"
    echo "MONGODB_DATABASE_NAME: Your MongoDB database name (e.g. stir_webserver)"
    echo "AUTH_SERVICE_URL: URL of the auth microservice (e.g. https://auth.stirdotcom.net)"
    echo ""
    echo -e "${GREEN}Your Cloud Run service will be available at:${NC}"
    echo "Webserver: https://${SERVICE_NAME}-${PROJECT_NUMBER}.${REGION}.run.app"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo "1. Add the secrets above to your GitHub repository"
    echo "2. Set up MongoDB Atlas (or your MongoDB provider) and get a connection string"
    echo "3. Push to main branch to trigger deployment"
    echo "4. After deployment, run ./scripts/setup_domain.sh to configure api.stirdotcom.net"
    echo "5. Check the Actions tab in GitHub to monitor the deployment"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo "If the container fails to start with 'failed to start and listen on the port',"
    echo "the auth microservice (stir-auth-server) likely can't read Firebase secrets"
    echo "from Secret Manager. Run this command to fix:"
    echo ""
    echo "gcloud projects add-iam-policy-binding $PROJECT_ID \\"
    echo "  --member=\"serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com\" \\"
    echo "  --role=\"roles/secretmanager.secretAccessor\""
    echo ""
    echo "This grants the Cloud Run runtime service account access to read secrets."
    echo ""
    echo -e "${YELLOW}For staging environment:${NC}"
    echo "Run this script again with: ./scripts/setup_gcp.sh staging"
    echo "Then run: ./scripts/setup_domain.sh staging"
}

# Main execution
main() {
    print_header "$1"
    check_prerequisites
    get_project_id
    enable_apis
    create_artifact_registry
    create_service_account
    setup_workload_identity
    grant_secret_manager_access
    print_summary
}

# Run main function
main "$@"
