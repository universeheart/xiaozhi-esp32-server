package xiaozhi.modules.member.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class MemberProfileUpsertDTO {
    @NotBlank
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
    @NotBlank
    private String profileMd;
}
