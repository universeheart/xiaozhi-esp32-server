package xiaozhi.modules.member.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

@Data
@TableName("memory_profile")
public class MemberProfileEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String macAddress;
    private String memberId;
    private String username;
    private String occupation;
    private String primaryOccupation;
    private String interests;
    private String favoriteRole;
    private String favoriteTvShow;
    private String chineseName;
    private String englishName;
    private String profileMd;
    private Date createDate;
    private Date updateDate;
}
