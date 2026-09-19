CREATE TABLE `hardware_product_unit` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `product_code` VARCHAR(64) NOT NULL,
  `serial_number` VARCHAR(96) NOT NULL,
  `mac_address` VARCHAR(50) NOT NULL,
  `board` VARCHAR(64) NULL,
  `manufacture_batch` VARCHAR(64) NULL,
  `status` VARCHAR(24) NOT NULL DEFAULT 'PROVISIONED' COMMENT 'PROVISIONED/ACTIVATED/REVOKED/SCRAPPED',
  `activated_account_id` BIGINT NULL,
  `activated_agent_id` VARCHAR(32) NULL,
  `activated_at` DATETIME NULL,
  `last_unbound_at` DATETIME NULL,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_hardware_serial` (`serial_number`),
  UNIQUE KEY `uk_hardware_mac` (`mac_address`),
  KEY `idx_hardware_product_status` (`product_code`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出厂硬件可信清单';

CREATE TABLE `hardware_lifecycle_event` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `hardware_id` BIGINT NOT NULL,
  `account_id` BIGINT NULL,
  `agent_id` VARCHAR(32) NULL,
  `event_type` VARCHAR(24) NOT NULL,
  `request_id` CHAR(36) NOT NULL,
  `result` VARCHAR(16) NOT NULL,
  `detail` VARCHAR(500) NULL,
  `create_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_hardware_request` (`request_id`),
  KEY `idx_hardware_event` (`hardware_id`, `create_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='硬件激活解绑审计';
