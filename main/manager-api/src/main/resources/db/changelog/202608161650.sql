CREATE TABLE IF NOT EXISTS `member_profile` (
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
  UNIQUE KEY `uk_member_profile_mac_address` (`mac_address`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='硬件用户画像';
