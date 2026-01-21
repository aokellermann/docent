resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.deployment}-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name       = "${var.project_name}-${var.deployment}-db-subnet-group"
    Deployment = var.deployment
  }
}

resource "aws_db_instance" "postgres" {
  identifier = "${var.project_name}-${var.deployment}-postgres"

  engine         = "postgres"
  engine_version = "15.12"
  instance_class = var.rds_instance_class

  allocated_storage     = 20
  max_allocated_storage = var.rds_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = local.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  multi_az = var.rds_multi_az

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"
  apply_immediately       = false # Changes are applied at the next maintenance window.

  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project_name}-${var.deployment}-postgres-final-snapshot"

  tags = {
    Name       = "${var.project_name}-${var.deployment}-postgres"
    Deployment = var.deployment
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu_utilization" {
  count = var.rds_alarm_sns_topic_arn != "" ? 1 : 0

  alarm_name          = "${var.project_name}-${var.deployment}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS CPU utilization exceeds 80%"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  alarm_actions = [var.rds_alarm_sns_topic_arn]
  ok_actions    = [var.rds_alarm_sns_topic_arn]

  tags = {
    Deployment = var.deployment
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_freeable_memory" {
  count = var.rds_alarm_sns_topic_arn != "" ? 1 : 0

  alarm_name          = "${var.project_name}-${var.deployment}-rds-memory-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "FreeableMemory"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 268435456 # 256 MB in bytes
  alarm_description   = "RDS freeable memory below 256 MB"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  alarm_actions = [var.rds_alarm_sns_topic_arn]
  ok_actions    = [var.rds_alarm_sns_topic_arn]

  tags = {
    Deployment = var.deployment
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_disk_queue_depth" {
  count = var.rds_alarm_sns_topic_arn != "" ? 1 : 0

  alarm_name          = "${var.project_name}-${var.deployment}-rds-io-queue-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DiskQueueDepth"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 64
  alarm_description   = "RDS disk queue depth exceeds 64"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  alarm_actions = [var.rds_alarm_sns_topic_arn]
  ok_actions    = [var.rds_alarm_sns_topic_arn]

  tags = {
    Deployment = var.deployment
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage_space" {
  count = var.rds_alarm_sns_topic_arn != "" ? 1 : 0

  alarm_name          = "${var.project_name}-${var.deployment}-rds-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 5368709120 # 5 GB in bytes
  alarm_description   = "RDS free storage space below 5 GB"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  alarm_actions = [var.rds_alarm_sns_topic_arn]
  ok_actions    = [var.rds_alarm_sns_topic_arn]

  tags = {
    Deployment = var.deployment
  }
}
