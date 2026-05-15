resource "aws_db_subnet_group" "aurora" {
  name       = local.name_prefix
  subnet_ids = aws_subnet.private_db[*].id

  tags = { Name = "${local.name_prefix}-aurora-subnet-group" }
}

resource "aws_rds_cluster" "aurora" {
  cluster_identifier = local.name_prefix
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned" # required for Serverless v2
  engine_version     = "15.8"
  database_name      = var.db_name
  master_username    = var.db_username

  # Secrets Manager manages and rotates the master password automatically
  manage_master_user_password = true

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 2.0
  }

  vpc_security_group_ids = [aws_security_group.aurora.id]
  db_subnet_group_name   = aws_db_subnet_group.aurora.name

  backup_retention_period      = 7
  preferred_backup_window      = "03:00-04:00"
  preferred_maintenance_window = "sun:04:00-sun:05:00"

  enabled_cloudwatch_logs_exports = ["postgresql"]

  skip_final_snapshot = var.environment != "prod"
  deletion_protection = var.environment == "prod"

  tags = { Name = "${local.name_prefix}-aurora" }
}

resource "aws_rds_cluster_instance" "aurora" {
  identifier           = "${local.name_prefix}-1"
  cluster_identifier   = aws_rds_cluster.aurora.id
  instance_class       = "db.serverless"
  engine               = aws_rds_cluster.aurora.engine
  engine_version       = aws_rds_cluster.aurora.engine_version
  db_subnet_group_name = aws_db_subnet_group.aurora.name

  tags = { Name = "${local.name_prefix}-aurora-instance" }
}

resource "aws_cloudwatch_log_group" "aurora" {
  name              = "/aws/rds/cluster/${local.name_prefix}/postgresql"
  retention_in_days = 14
}
