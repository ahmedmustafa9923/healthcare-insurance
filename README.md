# Healthcare Insurance Infrastructure Platform

A multi-tenant, HIPAA-compliant Infrastructure as Code (IaC) and containerized deployment blueprint. This platform orchestrates isolated environments for multiple healthcare insurance carriers (**Blue Cross**, **Hartford**, and **Allstate**) across both **Personal** and **Business** lines of business.

---

## 🏗️ Repository Architecture

The codebase is organized using a centralized module strategy. This ensures that while code is maintained in a unified repository, the deployed infrastructure components remain strictly separated.

```text
├── 1_providers_and_facilities/      # Medical configurations & clinical triage protocols
├── 2_insurance_operations/          # Carrier configurations (.tf directories)
│   ├── all_state/
│   ├── blue_cross/
│   └── hartford/
├── 3_crm_and_patients/              # Electronic Health Records (EHR) & histories
├── 4_underwriting_finance/          # Broker commissions & disbursements
├── terraform_modules/
│   └── carrier_app/                 # Reusable secure S3 + IAM structural module
├── Dockerfile                       # Core Application container image
├── app.py                           # Python backend logic layer
├── k8s-deployment.yaml              # Kubernetes namespace & multi-tenant pods
├── main.tf                          # Master Root Terraform Orchestrator
├── providers.tf                     # Global AWS Provider definition
└── README.md                        # Platform documentation
```

---

## 🔐 Multi-Tenancy & HIPAA Compliance Design

To prevent data cross-contamination and ensure strict adherence to HIPAA guidelines, the platform enforces data isolation at multiple architectural tiers:

1. **Storage Isolation (AWS S3):** Every carrier and line of business receives its own dedicated S3 bucket appended with a cryptographically unique `random_id` suffix. Buckets are explicitly isolated—there is no shared object space.
2. **Data-at-Rest Encryption:** Every generated S3 storage bucket enforces `AES256` server-side encryption by default.
3. **Public Access Prevention:** All carrier buckets deploy with a strict `aws_s3_bucket_public_access_block`, entirely blocking public ACLs or bucket policies from exposure to the open internet.
4. **Least Privilege Identity Management (AWS IAM):** Every tenant application receives an isolated IAM Execution Role. A container running Hartford operations physically lacks the AWS token permissions required to read or write to a Blue Cross storage bucket.
5. **Network Segment Isolation (Kubernetes):** The `k8s-deployment.yaml` initializes completely independent network boundaries using **Kubernetes Namespaces** (`blue-cross`, `hartford`, `all-state`), ensuring containers are network-isolated.

---

## 🛠️ Infrastructure Operations (Terraform)

The architecture leverages a single-account mockup configuration with root-controlled variables that can easily scale out to an AWS Organizations multi-account structure.

### Active Pipeline Commands

To initialize, validate, or update the cloud tier, navigate to the root directory and execute the workflow sequentially:

```bash
# Initialize the backend and download official HashiCorp AWS providers
terraform init

# Run a systematic formatting check across all directories
terraform fmt -recursive

# Verify that code syntax and configuration bindings are flawless
terraform validate

# Generate a dry-run preview of the 6 carrier tiers (S3 buckets & IAM roles)
terraform plan

# Deploy the configuration live to your active AWS footprint
terraform apply
```

---

## 🚀 Containerization & Orchestration (Docker & K8s)

* **Application Layer (`Dockerfile`):** Packs the `app.py` microservice backend into an optimized image ready to process regional healthcare streams.
* **Orchestration (`k8s-deployment.yaml`):** Provisions the tenant namespaces and scaffolds the cluster deployment pods, binding carrier identity flags right into the container runtime configuration parameters.
