package xiaozhi.modules.member.service;

import xiaozhi.modules.member.dto.MemberProfileUpsertDTO;

public interface MemberProfileService {
    boolean upsert(MemberProfileUpsertDTO dto);
}
