variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-west-1"
}

variable "key_name" {
  description = "Existing EC2 key pair name for SSH access"
  type        = string
  default     = "docent"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "m5.8xlarge"
}

variable "ebs_volume_size" {
  description = "Size of the EBS volume in GiB"
  type        = number
  default     = 100
}

variable "ebs_volume_type" {
  description = "Type of EBS volume (gp3, gp2, io1, io2, st1, sc1)"
  type        = string
  default     = "gp3"
}

variable "ebs_encrypted" {
  description = "Whether to encrypt the EBS volume"
  type        = bool
  default     = true
}

variable "db_username" {
  description = "Master username for Postgres"
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "Master password for Postgres"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.m5.8xlarge"
}

variable "db_allocated_storage" {
  description = "RDS storage (GiB)"
  type        = number
  default     = 200
}
