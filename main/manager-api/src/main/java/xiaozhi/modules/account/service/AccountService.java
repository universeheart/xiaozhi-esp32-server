package xiaozhi.modules.account.service;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import cn.hutool.crypto.digest.DigestUtil;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.account.dto.AccountRequests;
import xiaozhi.modules.account.repository.AccountRepository;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.security.password.PasswordUtils;
import xiaozhi.modules.security.service.SysUserTokenService;

@Service
@RequiredArgsConstructor
public class AccountService {
    private final AccountRepository repository;
    private final AccountAuthService auth;
    private final DeviceService deviceService;
    private final SysUserTokenService tokenService;

    public Map<String, Object> profile(long id) { return repository.profile(id); }
    public void updateProfile(long id, AccountRequests.Profile p) {
        repository.updateProfile(id, p.displayName(), p.avatarAssetId(), p.gender(), p.birthDate(), p.locale(), p.timezone());
    }
    public Map<String, Object> privacy(long id) { return repository.privacy(id); }
    public void updatePrivacy(long id, AccountRequests.Privacy p) {
        if (p.recentMemoryDays() != null && (p.recentMemoryDays() < 0 || p.recentMemoryDays() > 365))
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        if (p.patrolRetentionDays() != null && (p.patrolRetentionDays() < 0 || p.patrolRetentionDays() > 30))
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        Map<String, Object> v = new LinkedHashMap<>();
        v.put("cross", p.crossDeviceSyncEnabled()); v.put("redaction", p.sensitiveWordRedaction());
        v.put("memory", p.conversationMemoryEnabled()); v.put("memoryDays", p.recentMemoryDays());
        v.put("patrol", p.patrolRecordingEnabled()); v.put("patrolDays", p.patrolRetentionDays());
        v.put("cache", p.localCacheEnabled()); v.put("voice", p.personalizedVoiceEnabled());
        v.put("face", p.faceRecognitionEnabled()); repository.updatePrivacy(id, v);
    }

    public List<Map<String, Object>> members(long id) { return repository.members(id); }
    public Map<String, Object> addMember(long id, AccountRequests.Member m) {
        String memberId = UUID.randomUUID().toString();
        repository.addMember(memberId, repository.householdId(id), new Object[]{m.familyNickname(), m.familyRole(),
                m.customRoleName(), m.robotSalutation(), m.gender(), m.birthDate(), m.avatarAssetId(),
                m.voiceProfileId(), m.visibilityScope() == null ? "HOUSEHOLD" : m.visibilityScope()});
        return Map.of("id", memberId);
    }
    public void updateMember(long id, String memberId, AccountRequests.Member m) {
        int n = repository.updateMember(id, memberId, new Object[]{m.familyNickname(), m.familyRole(),
                m.customRoleName(), m.robotSalutation(), m.gender(), m.birthDate(), m.avatarAssetId(),
                m.voiceProfileId(), m.visibilityScope()});
        if (n != 1) throw new RenException(ErrorCode.ACCOUNT_RESOURCE_NO_PERMISSION);
    }
    public void removeMember(long id, String memberId) {
        if (repository.removeMember(id, memberId) != 1) throw new RenException(ErrorCode.ACCOUNT_RESOURCE_NO_PERMISSION);
    }

    public void setPin(long id, AccountRequests.GuardianPin p) {
        repository.upsertCredential(id, "GUARDIAN_PIN", PasswordUtils.encode(p.pin()));
    }
    public Map<String, Object> verifyPin(long id, AccountRequests.GuardianPin p) {
        Map<String, Object> c = repository.credential(id, "GUARDIAN_PIN")
                .orElseThrow(() -> new RenException(ErrorCode.GUARDIAN_PIN_INVALID));
        Timestamp locked = (Timestamp) c.get("locked_until");
        if (locked != null && locked.toLocalDateTime().isAfter(LocalDateTime.now()))
            throw new RenException(ErrorCode.GUARDIAN_PIN_LOCKED);
        if (!PasswordUtils.matches(p.pin(), String.valueOf(c.get("secret_hash")))) {
            int attempts = ((Number) c.getOrDefault("failed_attempts", 0)).intValue() + 1;
            repository.pinFailure(id, attempts >= 5);
            throw new RenException(attempts >= 5 ? ErrorCode.GUARDIAN_PIN_LOCKED : ErrorCode.GUARDIAN_PIN_INVALID);
        }
        repository.pinSuccess(id); return Map.of("verified", true);
    }

    public Map<String, Object> startPhoneChange(long id, AccountRequests.PhoneChangeStart p) {
        Map<String, Object> t = auth.consumeForAccount(p.oldPhoneTicket(), "PHONE_CHANGE_OLD", id);
        String requestId = repository.startPhoneChange(UUID.randomUUID().toString(), id, String.valueOf(t.get("phone_number")));
        return Map.of("requestId", requestId, "expiresIn", 1800);
    }
    @Transactional
    public void completePhoneChange(long id, AccountRequests.PhoneChangeComplete p) {
        Map<String, Object> t = auth.consumeTicket(p.newPhoneTicket(), "PHONE_CHANGE_NEW");
        String phone = String.valueOf(t.get("phone_number"));
        if (repository.accountByPhone(phone).isPresent()) throw new RenException(ErrorCode.PHONE_ALREADY_REGISTERED);
        if (repository.finishPhoneChange(id, p.requestId(), phone.startsWith("+") ? "INTERNATIONAL" : "+86",
                phone, DigestUtil.sha256Hex(phone)) != 1) throw new RenException(ErrorCode.PHONE_CHANGE_INVALID);
        tokenService.logout(id);
    }

    public List<Map<String, Object>> devices(long id) { return repository.devices(id); }
    public void bindDevice(long id, AccountRequests.DeviceBind p) {
        if (!Boolean.TRUE.equals(deviceService.deviceActivation(p.agentId(), p.activationCode())))
            throw new RenException(ErrorCode.ACTIVATION_CODE_ERROR);
        repository.devices(id).stream().filter(d -> p.agentId().equals(d.get("agent_id"))).findFirst()
                .ifPresent(d -> repository.bindingHistory(String.valueOf(d.get("id")), id,
                        String.valueOf(d.get("mac_address")), "ACTIVATION_CODE"));
    }
    public void unbindDevice(long id, String deviceId) {
        if (repository.device(id, deviceId).isEmpty()) throw new RenException(ErrorCode.ACCOUNT_RESOURCE_NO_PERMISSION);
        deviceService.unbindDevice(id, deviceId); repository.unbindingHistory(deviceId, id);
    }

    public Map<String, Object> requestDeletion(long id, AccountRequests.Deletion p) {
        if (!Boolean.TRUE.equals(p.riskAcknowledged())) throw new RenException(ErrorCode.DELETION_REQUEST_INVALID);
        auth.consumeForAccount(p.verificationTicket(), "DELETE_ACCOUNT", id);
        Map<String, Object> credential = repository.credential(id, "LOGIN_COMBINATION").orElse(null);
        if (credential != null && (p.combination() == null ||
                !PasswordUtils.matches(p.combination(), String.valueOf(credential.get("secret_hash")))))
            throw new RenException(ErrorCode.COMBINATION_INVALID);
        String requestId = repository.requestDeletion(UUID.randomUUID().toString(), id, p.reasonCode(), p.reasonText());
        tokenService.logout(id);
        return Map.of("requestId", requestId, "coolingOffDays", 15);
    }
    public void cancelDeletion(long id) {
        if (repository.cancelDeletion(id) == 0) throw new RenException(ErrorCode.DELETION_REQUEST_INVALID);
    }

    public List<Map<String,Object>> voiceProfiles(long id) { return repository.voiceProfiles(id); }
    public Map<String,Object> createVoiceProfile(long id, AccountRequests.VoiceProfile p) {
        String profileId = repository.createVoiceProfile(UUID.randomUUID().toString(), id,
                p.householdMemberId(), p.sampleAssetId(), p.consentVersion());
        if (profileId == null) throw new RenException(ErrorCode.MEDIA_ASSET_INVALID);
        return Map.of("id", profileId, "status", "READY");
    }
    public void revokeVoiceProfile(long id, String profileId) {
        if (repository.revokeVoiceProfile(id, profileId) != 1)
            throw new RenException(ErrorCode.ACCOUNT_RESOURCE_NO_PERMISSION);
    }
}
