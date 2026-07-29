-- P0 业务库初始化（UTF-8）
CREATE DATABASE IF NOT EXISTS ai_platform
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE ai_platform;

CREATE TABLE IF NOT EXISTS tenant (
  id VARCHAR(32) PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS tenant_quota (
  tenant_id VARCHAR(32) PRIMARY KEY,
  rpm_limit INT NOT NULL DEFAULT 60,
  token_daily_limit BIGINT NOT NULL DEFAULT 1000000,
  budget_monthly DECIMAL(18, 2) NULL,
  rpm_used_window INT NOT NULL DEFAULT 0,
  token_used_daily BIGINT NOT NULL DEFAULT 0,
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  CONSTRAINT fk_quota_tenant FOREIGN KEY (tenant_id) REFERENCES tenant(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS role (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  name VARCHAR(64) NOT NULL,
  permissions JSON NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_role_tenant (tenant_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_account (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  account VARCHAR(64) NOT NULL,
  display_name VARCHAR(128) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  UNIQUE KEY uk_user_tenant_account (tenant_id, account),
  INDEX idx_user_tenant (tenant_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_role (
  user_id VARCHAR(32) NOT NULL,
  role_id VARCHAR(32) NOT NULL,
  PRIMARY KEY (user_id, role_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS api_credential (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  name VARCHAR(64) NOT NULL,
  key_hash VARCHAR(128) NOT NULL,
  key_prefix VARCHAR(16) NOT NULL,
  scopes JSON NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  expires_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_cred_tenant (tenant_id),
  INDEX idx_cred_prefix (key_prefix)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS model_config (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  name VARCHAR(128) NOT NULL,
  provider VARCHAR(32) NOT NULL,
  model_type VARCHAR(16) NOT NULL,
  model_name VARCHAR(128) NOT NULL,
  base_url VARCHAR(512) NULL,
  api_key_cipher TEXT NULL,
  dimension INT NULL,
  extra JSON NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'enabled',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_model_tenant_type (tenant_id, model_type)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS knowledge_base (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  name VARCHAR(128) NOT NULL,
  embedding_model_id VARCHAR(32) NOT NULL,
  dimension INT NOT NULL,
  vector_store VARCHAR(32) NOT NULL DEFAULT 'qdrant',
  vector_collection VARCHAR(128) NOT NULL,
  chunk_size INT NOT NULL DEFAULT 800,
  chunk_overlap INT NOT NULL DEFAULT 100,
  status VARCHAR(16) NOT NULL DEFAULT 'enabled',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_kb_tenant (tenant_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS document (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  kb_id VARCHAR(32) NOT NULL,
  title VARCHAR(256) NOT NULL,
  source_type VARCHAR(32) NOT NULL,
  uri VARCHAR(1024) NULL,
  content_hash VARCHAR(64) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  error_message VARCHAR(1024) NULL,
  chunk_count INT NOT NULL DEFAULT 0,
  meta JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_doc_kb_status (kb_id, status),
  INDEX idx_doc_tenant (tenant_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS document_chunk (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  kb_id VARCHAR(32) NOT NULL,
  doc_id VARCHAR(32) NOT NULL,
  ordinal INT NOT NULL,
  content MEDIUMTEXT NOT NULL,
  token_estimate INT NULL,
  meta JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_chunk_doc (doc_id, ordinal),
  INDEX idx_chunk_kb (kb_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS app (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  name VARCHAR(128) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'enabled',
  primary_model_id VARCHAR(32) NULL,
  fallback_model_id VARCHAR(32) NULL,
  prompt_id VARCHAR(32) NULL,
  prompt_version INT NULL,
  rag_top_k INT NOT NULL DEFAULT 5,
  rag_rerank TINYINT NOT NULL DEFAULT 0,
  agent_max_steps INT NOT NULL DEFAULT 8,
  safety_policy JSON NULL,
  extra JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_app_tenant (tenant_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS app_knowledge_base (
  app_id VARCHAR(32) NOT NULL,
  kb_id VARCHAR(32) NOT NULL,
  weight INT NOT NULL DEFAULT 1,
  PRIMARY KEY (app_id, kb_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS app_tool (
  app_id VARCHAR(32) NOT NULL,
  tool_id VARCHAR(32) NOT NULL,
  enabled TINYINT NOT NULL DEFAULT 1,
  PRIMARY KEY (app_id, tool_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_workspace (
  slug VARCHAR(128) PRIMARY KEY,
  app_id VARCHAR(32) NOT NULL UNIQUE,
  tenant_id VARCHAR(32) NOT NULL,
  name VARCHAR(128) NOT NULL,
  description TEXT NULL,
  workspace_path VARCHAR(512) NOT NULL,
  coordinator_agent_id VARCHAR(64) NOT NULL,
  load_status VARCHAR(16) NOT NULL,
  validation_error TEXT NULL,
  loaded_at DATETIME(3) NULL,
  file_digest VARCHAR(64) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_agent_workspace_tenant (tenant_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_member (
  app_id VARCHAR(32) NOT NULL,
  agent_id VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  role VARCHAR(16) NOT NULL,
  description TEXT NULL,
  system_prompt_path VARCHAR(512) NOT NULL,
  allowed_tools_json JSON NOT NULL,
  max_steps INT NOT NULL DEFAULT 8,
  source_path VARCHAR(512) NOT NULL,
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (app_id, agent_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_prompt (
  id VARCHAR(32) PRIMARY KEY,
  app_id VARCHAR(32) NOT NULL,
  agent_id VARCHAR(64) NOT NULL,
  prompt_key VARCHAR(128) NOT NULL,
  source_path VARCHAR(512) NOT NULL,
  content MEDIUMTEXT NOT NULL,
  content_hash VARCHAR(64) NOT NULL,
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uq_agent_prompt (app_id, agent_id, prompt_key)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_tool (
  id VARCHAR(128) NOT NULL,
  app_id VARCHAR(32) NOT NULL,
  name VARCHAR(128) NOT NULL,
  description TEXT NULL,
  risk_level VARCHAR(16) NOT NULL,
  entrypoint VARCHAR(512) NOT NULL,
  parameters_json JSON NOT NULL,
  source_path VARCHAR(512) NOT NULL,
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (app_id, id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS chat_session (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  app_id VARCHAR(128) NOT NULL COMMENT 'workspace slug',
  user_id VARCHAR(64) NULL,
  title VARCHAR(256) NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_session_tenant_app (tenant_id, app_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS chat_message (
  id VARCHAR(32) PRIMARY KEY,
  session_id VARCHAR(32) NOT NULL,
  role VARCHAR(16) NOT NULL,
  content MEDIUMTEXT NOT NULL,
  token_count INT NULL,
  request_id VARCHAR(64) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_msg_session (session_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS run_trace (
  request_id VARCHAR(64) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  app_id VARCHAR(128) NULL COMMENT 'workspace slug',
  session_id VARCHAR(32) NULL,
  run_type VARCHAR(16) NOT NULL,
  model_id VARCHAR(32) NULL,
  status VARCHAR(16) NOT NULL,
  latency_ms INT NULL,
  prompt_tokens INT NULL,
  completion_tokens INT NULL,
  error_code VARCHAR(64) NULL,
  detail JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_trace_tenant_time (tenant_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(32) NOT NULL,
  actor VARCHAR(64) NOT NULL,
  action VARCHAR(64) NOT NULL,
  resource_type VARCHAR(32) NULL,
  resource_id VARCHAR(64) NULL,
  request_id VARCHAR(64) NULL,
  ip VARCHAR(64) NULL,
  payload JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_audit_tenant_time (tenant_id, created_at),
  INDEX idx_audit_request (request_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ingest_job (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  doc_id VARCHAR(32) NOT NULL,
  job_type VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0,
  last_error VARCHAR(1024) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_job_doc (doc_id),
  INDEX idx_job_status (status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_run (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  workspace_slug VARCHAR(128) NOT NULL,
  session_id VARCHAR(32) NULL,
  request_id VARCHAR(64) NOT NULL,
  status VARCHAR(16) NOT NULL,
  answer MEDIUMTEXT NULL,
  error_message VARCHAR(1024) NULL,
  prompt_tokens INT NULL,
  completion_tokens INT NULL,
  latency_ms INT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uq_agent_run_request (request_id),
  INDEX idx_agent_run_slug (tenant_id, workspace_slug, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_run_step (
  id VARCHAR(32) PRIMARY KEY,
  run_id VARCHAR(32) NOT NULL,
  step_no INT NOT NULL,
  agent_id VARCHAR(64) NOT NULL,
  type VARCHAR(16) NOT NULL,
  tool_id VARCHAR(128) NULL,
  args_json JSON NULL,
  output_json MEDIUMTEXT NULL,
  duration_ms INT NULL,
  error VARCHAR(1024) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  UNIQUE KEY uq_agent_run_step (run_id, step_no),
  INDEX idx_agent_run_step_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS vector_namespace (
  namespace VARCHAR(256) NOT NULL,
  tenant_id VARCHAR(32) NOT NULL,
  collection VARCHAR(128) NOT NULL,
  dimension INT NOT NULL,
  chunk_count INT NOT NULL DEFAULT 0,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (tenant_id, namespace)
) ENGINE=InnoDB;

-- 剧本业务表由 Alembic 管理（仓库根目录 alembic/），不在此建表。

-- 本地开发种子数据（密码：Admin@123456，仅开发环境）
INSERT INTO tenant (id, name, status) VALUES ('ten_demo', '演示租户', 'active')
  ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT INTO tenant_quota (tenant_id, rpm_limit, token_daily_limit)
VALUES ('ten_demo', 120, 5000000)
  ON DUPLICATE KEY UPDATE rpm_limit=VALUES(rpm_limit);

INSERT INTO role (id, tenant_id, name, permissions) VALUES (
  'role_admin',
  'ten_demo',
  '租户管理员',
  JSON_ARRAY(
    'model:read', 'model:write',
    'kb:read', 'kb:write',
    'app:read', 'app:write',
    'audit:read'
  )
) ON DUPLICATE KEY UPDATE permissions=VALUES(permissions);

-- 本地 APP_ENV=dev 登录不校验密码；password_hash 仅非 dev 环境使用（种子 Admin@123456）
INSERT INTO user_account (id, tenant_id, account, display_name, password_hash, status)
VALUES (
  'usr_admin',
  'ten_demo',
  'admin',
  '管理员',
  '$2b$12$p2ZlVuv0VNCd5E/4tmQm1.sWHECX.fEsDSKYN0xAiQ6IdP24xgflG',
  'active'
) ON DUPLICATE KEY UPDATE display_name=VALUES(display_name);

INSERT INTO user_role (user_id, role_id) VALUES ('usr_admin', 'role_admin')
  ON DUPLICATE KEY UPDATE role_id=VALUES(role_id);
