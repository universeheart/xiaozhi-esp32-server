-- Account domain for the companion mobile client. Existing sys_user remains the
-- authentication principal so manager-web compatibility is preserved.
ALTER TABLE `sys_user`
  ADD COLUMN `account_status` VARCHAR(24) NOT NULL DEFAULT 'ACTIVE' COMMENT 'PENDING/ACTIVE/LOCKED/SUSPENDED/DELETION_PENDING/DELETED',
  ADD COLUMN `registered_at` DATETIME NULL,
  ADD COLUMN `last_login_at` DATETIME NULL,
  ADD COLUMN `combination_changed_at` DATETIME NULL,
  ADD COLUMN `deletion_scheduled_at` DATETIME NULL,
  ADD COLUMN `deleted_at` DATETIME NULL,
  ADD COLUMN `token_version` INT NOT NULL DEFAULT 1;

CREATE TABLE `account_phone` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NOT NULL,
  `country_code` VARCHAR(8) NOT NULL,
  `phone_number` VARCHAR(32) NOT NULL,
  `phone_lookup_hash` CHAR(64) NOT NULL,
  `is_primary` TINYINT(1) NOT NULL DEFAULT 0,
  `verified_at` DATETIME NULL,
  `unbound_at` DATETIME NULL,
  `active_phone_hash` CHAR(64) GENERATED ALWAYS AS
    (CASE WHEN `unbound_at` IS NULL THEN `phone_lookup_hash` ELSE NULL END) STORED,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_account_phone_active` (`active_phone_hash`),
  KEY `idx_account_phone_account` (`account_id`),
  CONSTRAINT `fk_account_phone_account` FOREIGN KEY (`account_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账户手机号及换绑历史';

CREATE TABLE `account_profile` (
  `account_id` BIGINT NOT NULL,
  `display_name` VARCHAR(64) NULL,
  `avatar_asset_id` CHAR(36) NULL,
  `gender` VARCHAR(16) NULL,
  `birth_date` DATE NULL,
  `locale` VARCHAR(16) NOT NULL DEFAULT 'zh-CN',
  `timezone` VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
  `update_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`account_id`),
  CONSTRAINT `fk_account_profile_account` FOREIGN KEY (`account_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账户资料';

CREATE TABLE `account_credential` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NOT NULL,
  `credential_type` VARCHAR(24) NOT NULL COMMENT 'LOGIN_COMBINATION/GUARDIAN_PIN',
  `secret_hash` VARCHAR(120) NOT NULL,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `failed_attempts` INT NOT NULL DEFAULT 0,
  `locked_until` DATETIME NULL,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_account_credential` (`account_id`, `credential_type`),
  CONSTRAINT `fk_account_credential_account` FOREIGN KEY (`account_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账户组合密码与家长PIN凭证';

CREATE TABLE `account_verification_ticket` (
  `id` CHAR(36) NOT NULL,
  `scene` VARCHAR(40) NOT NULL,
  `phone_number` VARCHAR(32) NOT NULL,
  `account_id` BIGINT NULL,
  `ticket_hash` CHAR(64) NOT NULL,
  `expires_at` DATETIME NOT NULL,
  `consumed_at` DATETIME NULL,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_account_ticket_hash` (`ticket_hash`),
  KEY `idx_account_ticket_phone_scene` (`phone_number`, `scene`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='短信验证后的短期业务票据';

CREATE TABLE `household` (
  `id` CHAR(36) NOT NULL,
  `name` VARCHAR(64) NULL,
  `owner_account_id` BIGINT NOT NULL,
  `storage_quota_bytes` BIGINT NOT NULL DEFAULT 8589934592,
  `storage_used_bytes` BIGINT NOT NULL DEFAULT 0,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_household_owner` (`owner_account_id`),
  CONSTRAINT `fk_household_owner` FOREIGN KEY (`owner_account_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='家庭';

CREATE TABLE `household_member` (
  `id` CHAR(36) NOT NULL,
  `household_id` CHAR(36) NOT NULL,
  `account_id` BIGINT NULL,
  `family_nickname` VARCHAR(64) NULL,
  `family_role` VARCHAR(32) NULL,
  `custom_role_name` VARCHAR(32) NULL,
  `robot_salutation` VARCHAR(64) NULL,
  `gender` VARCHAR(16) NULL,
  `birth_date` DATE NULL,
  `avatar_asset_id` CHAR(36) NULL,
  `voice_profile_id` CHAR(36) NULL,
  `visibility_scope` VARCHAR(24) NOT NULL DEFAULT 'HOUSEHOLD',
  `member_status` VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_household_member_household` (`household_id`),
  KEY `idx_household_member_account` (`account_id`),
  CONSTRAINT `fk_household_member_household` FOREIGN KEY (`household_id`) REFERENCES `household` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='家庭成员与身份映射';

CREATE TABLE `account_media_asset` (
  `id` CHAR(36) NOT NULL,
  `owner_account_id` BIGINT NOT NULL,
  `household_id` CHAR(36) NULL,
  `media_type` VARCHAR(24) NOT NULL,
  `purpose` VARCHAR(48) NOT NULL,
  `storage_provider` VARCHAR(24) NOT NULL DEFAULT 'LOCAL',
  `bucket_name` VARCHAR(128) NULL,
  `object_key` VARCHAR(512) NOT NULL,
  `original_filename` VARCHAR(255) NULL,
  `content_type` VARCHAR(128) NOT NULL,
  `size_bytes` BIGINT NOT NULL,
  `sha256` CHAR(64) NOT NULL,
  `width` INT NULL,
  `height` INT NULL,
  `duration_ms` BIGINT NULL,
  `codec` VARCHAR(32) NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'UPLOADING',
  `scan_status` VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  `retention_until` DATETIME NULL,
  `deleted_at` DATETIME NULL,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_account_media_object` (`object_key`),
  KEY `idx_account_media_owner` (`owner_account_id`, `purpose`),
  CONSTRAINT `fk_account_media_owner` FOREIGN KEY (`owner_account_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='头像音视频及导出文件元数据';

CREATE TABLE `account_voice_profile` (
  `id` CHAR(36) NOT NULL,
  `account_id` BIGINT NOT NULL,
  `household_member_id` CHAR(36) NULL,
  `sample_asset_id` CHAR(36) NULL,
  `model_asset_id` CHAR(36) NULL,
  `provider` VARCHAR(32) NULL,
  `provider_model_id` VARCHAR(128) NULL,
  `match_score` DECIMAL(5,2) NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'PROCESSING',
  `consent_version` VARCHAR(32) NULL,
  `consented_at` DATETIME NULL,
  `activated_at` DATETIME NULL,
  `revoked_at` DATETIME NULL,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_voice_profile_account` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='成员声纹模型映射';

CREATE TABLE `account_privacy_setting` (
  `account_id` BIGINT NOT NULL,
  `cross_device_sync_enabled` TINYINT(1) NOT NULL DEFAULT 0,
  `sensitive_word_redaction` TINYINT(1) NOT NULL DEFAULT 1,
  `conversation_memory_enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `recent_memory_days` INT NOT NULL DEFAULT 7,
  `patrol_recording_enabled` TINYINT(1) NOT NULL DEFAULT 0,
  `patrol_retention_days` INT NOT NULL DEFAULT 3,
  `local_cache_enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `personalized_voice_enabled` TINYINT(1) NOT NULL DEFAULT 0,
  `face_recognition_enabled` TINYINT(1) NOT NULL DEFAULT 0,
  `update_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`account_id`),
  CONSTRAINT `fk_privacy_account` FOREIGN KEY (`account_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='隐私与记忆策略';

CREATE TABLE `account_phone_change_request` (
  `id` CHAR(36) NOT NULL,
  `account_id` BIGINT NOT NULL,
  `old_phone_number` VARCHAR(32) NOT NULL,
  `new_country_code` VARCHAR(8) NULL,
  `new_phone_number` VARCHAR(32) NULL,
  `old_phone_verified_at` DATETIME NULL,
  `new_phone_verified_at` DATETIME NULL,
  `status` VARCHAR(24) NOT NULL DEFAULT 'VERIFY_OLD',
  `expires_at` DATETIME NOT NULL,
  `completed_at` DATETIME NULL,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_phone_change_account` (`account_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='手机号换绑事务';

CREATE TABLE `account_deletion_request` (
  `id` CHAR(36) NOT NULL,
  `account_id` BIGINT NOT NULL,
  `status` VARCHAR(24) NOT NULL DEFAULT 'COOLING_OFF',
  `reason_code` VARCHAR(64) NULL,
  `reason_text` VARCHAR(500) NULL,
  `combination_verified_at` DATETIME NULL,
  `sms_verified_at` DATETIME NULL,
  `risk_acknowledged_at` DATETIME NULL,
  `requested_at` DATETIME NOT NULL,
  `scheduled_purge_at` DATETIME NOT NULL,
  `cancelled_at` DATETIME NULL,
  `completed_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  KEY `idx_deletion_account_status` (`account_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账户注销与十五天冷静期';

CREATE TABLE `account_security_event` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `account_id` BIGINT NULL,
  `event_type` VARCHAR(64) NOT NULL,
  `result` VARCHAR(16) NOT NULL,
  `device_id` VARCHAR(32) NULL,
  `risk_level` VARCHAR(16) NULL,
  `metadata` JSON NULL,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_security_event_account` (`account_id`, `create_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账户安全审计事件';

CREATE TABLE `account_device_binding_history` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `device_id` VARCHAR(32) NOT NULL,
  `account_id` BIGINT NOT NULL,
  `mac_address` VARCHAR(50) NOT NULL,
  `bind_method` VARCHAR(32) NULL,
  `bound_at` DATETIME NOT NULL,
  `unbound_at` DATETIME NULL,
  `unbind_reason` VARCHAR(64) NULL,
  PRIMARY KEY (`id`),
  KEY `idx_binding_account` (`account_id`, `bound_at`),
  KEY `idx_binding_mac` (`mac_address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备绑定历史';

ALTER TABLE `ai_device`
  ADD UNIQUE KEY `uk_ai_device_mac_address` (`mac_address`);
