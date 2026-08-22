package xiaozhi.modules.member.dao;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Insert;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;

import xiaozhi.modules.member.entity.MemberProfileEntity;

@Mapper
public interface MemberProfileDao extends BaseMapper<MemberProfileEntity> {
    @Insert("""
            INSERT INTO memory_profile
              (mac_address, member_id, username, occupation, primary_occupation, interests,
               favorite_role, favorite_tv_show, chinese_name, english_name, profile_md,
               create_date, update_date)
            VALUES
              (#{macAddress}, #{memberId}, #{username}, #{occupation}, #{primaryOccupation}, #{interests},
               #{favoriteRole}, #{favoriteTvShow}, #{chineseName}, #{englishName}, #{profileMd},
               #{createDate}, #{updateDate})
            ON DUPLICATE KEY UPDATE
              member_id = COALESCE(VALUES(member_id), member_id),
              username = COALESCE(VALUES(username), username),
              occupation = COALESCE(VALUES(occupation), occupation),
              primary_occupation = COALESCE(VALUES(primary_occupation), primary_occupation),
              interests = COALESCE(VALUES(interests), interests),
              favorite_role = COALESCE(VALUES(favorite_role), favorite_role),
              favorite_tv_show = COALESCE(VALUES(favorite_tv_show), favorite_tv_show),
              chinese_name = COALESCE(VALUES(chinese_name), chinese_name),
              english_name = COALESCE(VALUES(english_name), english_name),
              profile_md = VALUES(profile_md),
              update_date = VALUES(update_date)
            """)
    int upsert(MemberProfileEntity entity);
}
