module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.29"

  name               = "healthcare-eks"
  kubernetes_version = "1.36"

  # Only your workstation can reach the Kubernetes API
  endpoint_public_access       = true
  endpoint_public_access_cidrs = [var.admin_cidr]

  # The identity running terraform becomes cluster admin
  enable_cluster_creator_admin_permissions = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  addons = {
    vpc-cni                = { before_compute = true }
    eks-pod-identity-agent = { before_compute = true } # per-carrier IAM roles
    kube-proxy             = {}
    coredns                = {}
  }

  eks_managed_node_groups = {
    workers = {
      name           = "carrier-worker"
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = ["t3.medium"]
      min_size       = 3
      max_size       = 6
      desired_size   = 3
    }
  }
}

output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "configure_kubectl" {
  value = "aws eks update-kubeconfig --region us-east-1 --name ${module.eks.cluster_name}"
}

