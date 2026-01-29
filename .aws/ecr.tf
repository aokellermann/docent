resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}/${var.deployment}/backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "${var.project_name}-${var.deployment}-backend-ecr"
    Deployment = var.deployment
  }
}
