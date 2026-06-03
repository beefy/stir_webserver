#!/bin/bash

# Custom Domain Setup Script for Cloud Run
# This script helps set up a custom domain for the stir_webserver service

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
MAIN_DOMAIN="api.stirdotcom.net"
STAGING_DOMAIN="staging-api.stirdotcom.net"

if [ "$1" = "staging" ] || [ "$1" = "--staging" ]; then
    echo -e "${BLUE}Setting up STAGING environment${NC}"
    SERVICE_NAME="stir-webserver-staging"
    MAIN_DOMAIN="$STAGING_DOMAIN"
fi

print_header() {
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}  Custom Domain Setup for Cloud Run${NC}"
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
    CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "")
    if [ -n "$CURRENT_PROJECT" ]; then
        PROJECT_ID=$CURRENT_PROJECT
        print_info "Using project: $PROJECT_ID"
    else
        read -p "Enter your GCP Project ID: " PROJECT_ID
        gcloud config set project $PROJECT_ID
    fi
}

verify_service_exists() {
    print_step "Checking Cloud Run services..."

    SERVICES_EXIST=true

    # Check service
    if gcloud run services describe $SERVICE_NAME --region=$REGION &>/dev/null; then
        print_info "Service '$SERVICE_NAME' found in region '$REGION'"
        SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')
        print_info "Current service URL: $SERVICE_URL"
    else
        print_warning "Service '$SERVICE_NAME' not found in region '$REGION'"
        SERVICES_EXIST=false
    fi

    if [ "$SERVICES_EXIST" = false ]; then
        print_warning "Services not yet deployed. Domain mappings will be created anyway."
        print_info "After deploying your services with GitHub Actions, you can run this script again"
        print_info "or the domain mappings will automatically work once services are deployed."
        echo ""
        read -p "Continue with domain setup anyway? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Exiting. Deploy your services first, then run this script again."
            exit 0
        fi
    fi
}

verify_domain_ownership() {
    print_step "Checking domain ownership..."

    print_info "Make sure you own the domain '$MAIN_DOMAIN'"
    read -p "Do you own the domain '$MAIN_DOMAIN'? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_error "You must own the domain to continue"
        exit 1
    fi
}

create_domain_mapping() {
    print_step "Creating domain mappings for Cloud Run..."

    # Create mapping for the domain
    if gcloud beta run domain-mappings describe --domain=$MAIN_DOMAIN --region=$REGION &>/dev/null; then
        print_warning "Domain mapping for '$MAIN_DOMAIN' already exists"
    else
        print_info "Creating domain mapping for '$MAIN_DOMAIN' -> service..."
        gcloud beta run domain-mappings create \
            --service=$SERVICE_NAME \
            --domain=$MAIN_DOMAIN \
            --region=$REGION
        print_info "Domain mapping created successfully!"
    fi
}

get_dns_records() {
    print_step "Getting DNS records to configure..."

    print_info "Fetching required DNS records..."

    echo ""
    echo -e "${YELLOW}DNS Records to configure in Google Domains:${NC}"
    echo "========================="

    # Get DNS records for the domain
    print_info "For $MAIN_DOMAIN:"
    DNS_RECORDS=$(gcloud beta run domain-mappings describe --domain=$MAIN_DOMAIN --region=$REGION --format="value(status.resourceRecords[].name,status.resourceRecords[].type,status.resourceRecords[].rrdata)" 2>/dev/null || echo "")

    if [ -n "$DNS_RECORDS" ]; then
        echo "$DNS_RECORDS" | while IFS=$'\t' read -r name type rrdata; do
            if [ -n "$type" ] && [ -n "$rrdata" ]; then
                echo "Name: ${name:-@}"
                echo "Type: $type"
                echo "Value: $rrdata"
                echo "TTL: 300"
                echo "---"
            fi
        done
    fi

    if [ -z "$DNS_RECORDS" ]; then
        print_warning "Could not retrieve DNS records automatically"
        print_info "You can get them manually with:"
        echo "gcloud beta run domain-mappings describe --domain=$MAIN_DOMAIN --region=$REGION"
    fi
}

configure_google_domains() {
    print_step "Instructions for configuring DNS in Google Domains..."

    echo ""
    echo -e "${YELLOW}To configure DNS in Google Domains:${NC}"
    echo "===================================="
    echo "1. Go to https://domains.google.com"
    echo "2. Find your domain 'stirdotcom.net'"
    echo "3. Click on it and go to 'DNS' tab"
    echo "4. Scroll down to 'Custom records'"
    echo "5. Add the DNS records shown above for $MAIN_DOMAIN"
    echo ""
    echo -e "${BLUE}Important:${NC} Since $MAIN_DOMAIN is a subdomain of stirdotcom.net,"
    echo "you need to add records to the stirdotcom.net DNS zone."
    echo "The 'Name' field should be 'api' (not the full domain)."
    echo ""
    echo "For example, if the record says:"
    echo "  Name: api.stirdotcom.net"
    echo "  Type: A"
    echo "  Value: 123.456.789.0"
    echo ""
    echo "In Google Domains, enter:"
    echo "  Name: api"
    echo "  Type: A"
    echo "  Value: 123.456.789.0"
    echo "  TTL: 300"
    echo ""
    echo "6. Set TTL to 300 seconds for faster propagation"
    echo "7. Click Save"
    echo ""
    echo -e "${BLUE}DNS propagation info:${NC} Can take up to 48 hours, but usually 5-10 minutes"
    echo -e "${BLUE}Tip:${NC} Use 'dig $MAIN_DOMAIN' to check DNS propagation"
}

test_domain_setup() {
    print_step "Testing domain setup..."

    echo ""
    print_info "Once DNS propagation is complete, test your setup:"
    echo "1. Health check: https://$MAIN_DOMAIN/docs"
    echo ""
    print_info "You can check DNS propagation with:"
    echo "nslookup $MAIN_DOMAIN"
    echo "dig $MAIN_DOMAIN"
}

print_next_steps() {
    print_step "Next steps and summary..."

    echo ""
    echo -e "${GREEN}Summary:${NC}"
    echo "========"
    echo "✅ Domain mapping created for: $MAIN_DOMAIN"
    echo "✅ DNS records retrieved"
    echo "✅ Configuration instructions provided"
    echo ""
    echo -e "${YELLOW}What you need to do next:${NC}"
    echo "========================="
    echo "1. Go to https://domains.google.com"
    echo "2. Click on 'stirdotcom.net'"
    echo "3. Go to the 'DNS' tab"
    echo "4. Under 'Custom records', add the records shown above"
    echo "5. Wait for DNS propagation (5-10 minutes usually)"
    echo "6. Test the domain:"
    echo "   - Swagger Docs: https://$MAIN_DOMAIN/docs"
    echo ""
    echo -e "${BLUE}Useful commands:${NC}"
    echo "================"
    echo "# Check domain mapping status"
    echo "gcloud beta run domain-mappings describe $MAIN_DOMAIN --region=$REGION"
    echo ""
    echo "# Check DNS resolution"
    echo "nslookup $MAIN_DOMAIN"
    echo ""
    echo "# Test SSL certificates (after DNS propagation)"
    echo "curl -I https://$MAIN_DOMAIN/docs"
    echo ""
    echo -e "${GREEN}🎉 Your API service will be available at:${NC}"
    echo -e "${GREEN}   https://$MAIN_DOMAIN${NC}"
}

# Main execution
main() {
    print_header "$1"
    check_prerequisites
    get_project_id
    verify_service_exists
    verify_domain_ownership "$1"
    create_domain_mapping
    get_dns_records
    configure_google_domains
    test_domain_setup
    print_next_steps
}

# Run main function
main "$@"
