# Comprehensive Neo4j EC2 Instance Setup Guide

This guide details how to provision, configure, and initialize a secure Neo4j graph database instance on AWS EC2, complete with IAM permissions, security hardening, and bulk data loading procedures.

---

## 1. Architecture & Resource Requirements

* **Cloud Provider:** Amazon Web Services (AWS)
* **Operating System:** Amazon Linux 2023
* **Instance Type:** `r5.xlarge` (4 vCPUs, 32 GB RAM) — *Recommended because Neo4j relies heavily on memory for caching graphs and executing complex queries.*
* **Storage:** 30 GB EBS disk minimum.
* **Access Model:** AWS Systems Manager (SSM) Session Manager (No public SSH keys or inbound firewall rules required).

---

## 2. Infrastructure Setup (AWS Console / Terraform)

### A. Create the IAM Role
Create an IAM role named **`is459-aml-neo4j-ec2-role`** and attach the following:
1. **`AmazonSSMManagedInstanceCore`**: Enables remote management via the AWS Systems Manager console without needing an SSH key pair.
2. **Custom S3 Policy**: Restricts read access strictly to your data bucket and write access to your results bucket:
   * Read: `arn:aws:s3:::your-bucket-name/exports/neo4j/*`
   * Write: `arn:aws:s3:::your-bucket-name/results/neo4j/*`

### B. Create the Security Group
Create a security group named **`is459-neo4j-sg`**:
* **Inbound Rules:** None (completely locked down from the public internet).
* **Outbound Rules:** Standard full outbound access (or restricted to S3 VPC endpoints if required by compliance).

### C. Launch the EC2 Instance
Launch the EC2 instance with these parameters:
* **AMI:** Amazon Linux 2023
* **Instance Type:** `r5.xlarge`
* **Storage:** 30 GB gp3 root volume
* **Key Pair:** None
* **IAM Instance Profile:** `is459-aml-neo4j-ec2-role`
* **Security Group:** `is459-neo4j-sg`

---

## 3. Preparing Data in S3

Organize your source files within your S3 bucket under the `exports/neo4j/` prefix:
* `exports/neo4j/headers/`: CSV files containing column headers and schema definitions.
* `exports/neo4j/golden/`: A tiny test dataset for quick pipeline validation.
* `exports/neo4j/dev/`: A single-day sample dataset (e.g., Sep 5) for intermediate testing.
* `exports/neo4j/full/`: The full production dataset (e.g., accounts mapped as nodes, transfers mapped as relationships/edges).

---

## 4. Installing Neo4j via SSM Run Command

Log into the AWS Systems Manager console, navigate to **Run Command**, select your target EC2 instance, and execute the initialization script:

```bash
# 1. Update system and install Docker
sudo yum update -y
sudo amazon-linux-extras install docker -y || sudo dnf install docker -y
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# 2. Create local directory for passwords
sudo mkdir -p /neo4j
sudo chmod 700 /neo4j

# 3. Generate and save a secure random password
openssl rand -base64 32 | sudo tee /neo4j/.pass > /dev/null

# 4. Pull the official Neo4j Community Docker image
sudo docker pull neo4j:5-community
```

---

## 5. Bulk Loading the Graph Data

To load large datasets (e.g., millions of accounts and transfers) efficiently, use Neo4j's native bulk importer via Docker:

1. Sync or copy your CSV files from S3 to the EC2 local disk (e.g., via AWS CLI).
2. Run the `neo4j-admin database import` command pointing to your headers and data CSV files:

```bash
sudo docker run --rm \
  -v /path/to/local/data:/var/lib/neo4j/import \
  -v /var/lib/neo4j/data:/data \
  neo4j:5-community \
  neo4j-admin database import full \
  --nodes=Account=/var/lib/neo4j/import/headers/accounts_header.csv,/var/lib/neo4j/import/full/accounts.csv \
  --relationships=TRANSFER=/var/lib/neo4j/import/headers/transfers_header.csv,/var/lib/neo4j/import/full/transfers.csv \
  --delimiter="," --array-delimiter="|"
```

---

## 6. Running the Pipeline & Connecting

### Start the Container
```bash
sudo docker run -d \
  --name neo4j \
  --publish 7474:7474 --publish 7687:7687 \
  --env NEO4J_AUTH=neo4j/$(cat /neo4j/.pass) \
  -v /var/lib/neo4j/data:/data \
  neo4j:5-community
```

### Connecting Locally via SSM Port Forwarding (for Management/Pipelines)
If you need to connect from your local development machine without opening public ports:
```bash
aws ssm start-session \
    --target <YOUR_EC2_INSTANCE_ID> \
    --document-name AWS-StartPortForwardingSession \
    --parameters '{"portNumber":["7474"],"localPortNumber":["7474"]}'
```
Then access `http://localhost:7474` in your browser.