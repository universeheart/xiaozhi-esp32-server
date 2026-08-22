CREATE TABLE IF NOT EXISTS `memory_profile` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `mac_address` varchar(64) NOT NULL COMMENT '硬件唯一ID（MAC地址）',
  `member_id` varchar(120) DEFAULT NULL COMMENT '画像中的用户ID',
  `username` varchar(100) DEFAULT NULL COMMENT '用户名',
  `occupation` varchar(255) DEFAULT NULL COMMENT '职业',
  `primary_occupation` varchar(255) DEFAULT NULL COMMENT '主职业',
  `interests` text COMMENT '兴趣',
  `favorite_role` varchar(255) DEFAULT NULL COMMENT '喜欢的角色',
  `favorite_tv_show` varchar(255) DEFAULT NULL COMMENT '喜欢的美剧',
  `chinese_name` varchar(100) DEFAULT NULL COMMENT '中文名字',
  `english_name` varchar(100) DEFAULT NULL COMMENT '英文名字',
  `profile_md` longtext NOT NULL COMMENT 'profile.md完整快照',
  `create_date` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_date` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_memory_profile_mac_address` (`mac_address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='硬件用户长期记忆画像';

INSERT INTO `memory_profile`
  (`mac_address`, `member_id`, `username`, `occupation`, `primary_occupation`, `interests`,
   `favorite_role`, `favorite_tv_show`, `chinese_name`, `english_name`, `profile_md`,
   `create_date`, `update_date`)
SELECT
  `mac_address`, `member_id`, `username`, `occupation`, `primary_occupation`, `interests`,
  `favorite_role`, `favorite_tv_show`, `chinese_name`, `english_name`, `profile_md`,
  `create_date`, `update_date`
FROM `member_profile`
ON DUPLICATE KEY UPDATE
  `member_id` = VALUES(`member_id`),
  `username` = VALUES(`username`),
  `occupation` = VALUES(`occupation`),
  `primary_occupation` = VALUES(`primary_occupation`),
  `interests` = VALUES(`interests`),
  `favorite_role` = VALUES(`favorite_role`),
  `favorite_tv_show` = VALUES(`favorite_tv_show`),
  `chinese_name` = VALUES(`chinese_name`),
  `english_name` = VALUES(`english_name`),
  `profile_md` = VALUES(`profile_md`),
  `update_date` = VALUES(`update_date`);
