package xiaozhi.modules.member.service.impl;

import java.util.Date;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.utils.ConvertUtils;
import xiaozhi.modules.member.dao.MemberProfileDao;
import xiaozhi.modules.member.dto.MemberProfileUpsertDTO;
import xiaozhi.modules.member.entity.MemberProfileEntity;
import xiaozhi.modules.member.service.MemberProfileService;

@Service
@RequiredArgsConstructor
public class MemberProfileServiceImpl implements MemberProfileService {
    private final MemberProfileDao memberProfileDao;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public boolean upsert(MemberProfileUpsertDTO dto) {
        MemberProfileEntity entity = ConvertUtils.sourceToTarget(dto, MemberProfileEntity.class);
        Date now = new Date();
        entity.setCreateDate(now);
        entity.setUpdateDate(now);
        return memberProfileDao.upsert(entity) > 0;
    }
}
