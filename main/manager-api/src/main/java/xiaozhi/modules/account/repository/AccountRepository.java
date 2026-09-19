package xiaozhi.modules.account.repository;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import lombok.RequiredArgsConstructor;

@Repository
@RequiredArgsConstructor
public class AccountRepository {
    private final JdbcTemplate jdbc;

    public Optional<Map<String, Object>> accountByPhone(String phone) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT id,username,status,account_status,deletion_scheduled_at FROM sys_user WHERE username=? LIMIT 1",
                phone);
        return rows.stream().findFirst();
    }

    public Optional<Map<String, Object>> account(long accountId) {
        return jdbc.queryForList("SELECT * FROM sys_user WHERE id=?", accountId).stream().findFirst();
    }

    public void initialize(long accountId, String countryCode, String phone, String phoneHash,
            String displayName, String householdId, String memberId, boolean combinationSet, String combinationHash) {
        jdbc.update("UPDATE sys_user SET account_status='ACTIVE',registered_at=NOW() WHERE id=?", accountId);
        jdbc.update("INSERT INTO account_phone(account_id,country_code,phone_number,phone_lookup_hash,is_primary,verified_at) VALUES(?,?,?,?,1,NOW())",
                accountId, countryCode, phone, phoneHash);
        jdbc.update("INSERT INTO account_profile(account_id,display_name) VALUES(?,?)", accountId, displayName);
        jdbc.update("INSERT INTO household(id,name,owner_account_id) VALUES(?,?,?)", householdId,
                displayName == null || displayName.isBlank() ? "我的家庭" : displayName + "的家庭", accountId);
        jdbc.update("INSERT INTO household_member(id,household_id,account_id,family_nickname,family_role,robot_salutation) VALUES(?,?,?,?,?,?)",
                memberId, householdId, accountId, displayName, "OWNER", displayName);
        jdbc.update("INSERT INTO account_privacy_setting(account_id) VALUES(?)", accountId);
        if (combinationSet) upsertCredential(accountId, "LOGIN_COMBINATION", combinationHash);
    }

    public void upsertCredential(long accountId, String type, String hash) {
        jdbc.update("INSERT INTO account_credential(account_id,credential_type,secret_hash) VALUES(?,?,?) " +
                "ON DUPLICATE KEY UPDATE secret_hash=VALUES(secret_hash),enabled=1,failed_attempts=0,locked_until=NULL",
                accountId, type, hash);
    }

    public Optional<Map<String, Object>> credential(long accountId, String type) {
        return jdbc.queryForList("SELECT * FROM account_credential WHERE account_id=? AND credential_type=? AND enabled=1",
                accountId, type).stream().findFirst();
    }

    public void createTicket(String id, String scene, String phone, Long accountId, String hash,
            LocalDateTime expiresAt) {
        jdbc.update("INSERT INTO account_verification_ticket(id,scene,phone_number,account_id,ticket_hash,expires_at) VALUES(?,?,?,?,?,?)",
                id, scene, phone, accountId, hash, Timestamp.valueOf(expiresAt));
    }

    public Optional<Map<String, Object>> consumeTicket(String hash, String scene) {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT * FROM account_verification_ticket WHERE ticket_hash=? AND scene=? AND consumed_at IS NULL AND expires_at>NOW()",
                hash, scene);
        if (rows.isEmpty()) return Optional.empty();
        int changed = jdbc.update("UPDATE account_verification_ticket SET consumed_at=NOW() WHERE id=? AND consumed_at IS NULL",
                rows.getFirst().get("id"));
        return changed == 1 ? Optional.of(rows.getFirst()) : Optional.empty();
    }

    public Map<String, Object> profile(long accountId) {
        return jdbc.queryForMap("SELECT p.*,u.username AS phone,u.account_status,u.registered_at,u.deletion_scheduled_at " +
                "FROM account_profile p JOIN sys_user u ON u.id=p.account_id WHERE p.account_id=?", accountId);
    }

    public void updateProfile(long id, String name, String avatar, String gender, Object birthDate,
            String locale, String timezone) {
        jdbc.update("UPDATE account_profile SET display_name=COALESCE(?,display_name),avatar_asset_id=COALESCE(?,avatar_asset_id)," +
                "gender=COALESCE(?,gender),birth_date=COALESCE(?,birth_date),locale=COALESCE(?,locale),timezone=COALESCE(?,timezone) WHERE account_id=?",
                name, avatar, gender, birthDate, locale, timezone, id);
    }

    public Map<String, Object> privacy(long id) {
        return jdbc.queryForMap("SELECT * FROM account_privacy_setting WHERE account_id=?", id);
    }

    public void updatePrivacy(long id, Map<String, Object> values) {
        jdbc.update("UPDATE account_privacy_setting SET cross_device_sync_enabled=COALESCE(?,cross_device_sync_enabled)," +
                "sensitive_word_redaction=COALESCE(?,sensitive_word_redaction),conversation_memory_enabled=COALESCE(?,conversation_memory_enabled)," +
                "recent_memory_days=COALESCE(?,recent_memory_days),patrol_recording_enabled=COALESCE(?,patrol_recording_enabled)," +
                "patrol_retention_days=COALESCE(?,patrol_retention_days),local_cache_enabled=COALESCE(?,local_cache_enabled)," +
                "personalized_voice_enabled=COALESCE(?,personalized_voice_enabled),face_recognition_enabled=COALESCE(?,face_recognition_enabled) WHERE account_id=?",
                values.get("cross"), values.get("redaction"), values.get("memory"), values.get("memoryDays"),
                values.get("patrol"), values.get("patrolDays"), values.get("cache"), values.get("voice"), values.get("face"), id);
    }

    public String householdId(long accountId) {
        return jdbc.queryForObject("SELECT id FROM household WHERE owner_account_id=? LIMIT 1", String.class, accountId);
    }

    public List<Map<String, Object>> members(long accountId) {
        return jdbc.queryForList("SELECT m.* FROM household_member m JOIN household h ON h.id=m.household_id WHERE h.owner_account_id=? AND m.member_status='ACTIVE'", accountId);
    }

    public void addMember(String id, String householdId, Object[] p) {
        jdbc.update("INSERT INTO household_member(id,household_id,family_nickname,family_role,custom_role_name,robot_salutation,gender,birth_date,avatar_asset_id,voice_profile_id,visibility_scope) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                id, householdId, p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8]);
    }

    public int updateMember(long accountId, String memberId, Object[] p) {
        return jdbc.update("UPDATE household_member m JOIN household h ON h.id=m.household_id SET " +
                "m.family_nickname=COALESCE(?,m.family_nickname),m.family_role=COALESCE(?,m.family_role)," +
                "m.custom_role_name=COALESCE(?,m.custom_role_name),m.robot_salutation=COALESCE(?,m.robot_salutation)," +
                "m.gender=COALESCE(?,m.gender),m.birth_date=COALESCE(?,m.birth_date),m.avatar_asset_id=COALESCE(?,m.avatar_asset_id)," +
                "m.voice_profile_id=COALESCE(?,m.voice_profile_id),m.visibility_scope=COALESCE(?,m.visibility_scope) " +
                "WHERE m.id=? AND h.owner_account_id=? AND m.member_status='ACTIVE'",
                p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], memberId, accountId);
    }

    public int removeMember(long accountId, String memberId) {
        return jdbc.update("UPDATE household_member m JOIN household h ON h.id=m.household_id SET m.member_status='REMOVED' WHERE m.id=? AND h.owner_account_id=? AND m.account_id IS NULL",
                memberId, accountId);
    }

    public String startPhoneChange(String id, long accountId, String oldPhone) {
        jdbc.update("INSERT INTO account_phone_change_request(id,account_id,old_phone_number,old_phone_verified_at,status,expires_at) VALUES(?,?,?,NOW(),'VERIFY_NEW',DATE_ADD(NOW(),INTERVAL 30 MINUTE))",
                id, accountId, oldPhone);
        return id;
    }

    public int finishPhoneChange(long accountId, String requestId, String countryCode, String phone, String phoneHash) {
        int n = jdbc.update("UPDATE account_phone_change_request SET new_country_code=?,new_phone_number=?,new_phone_verified_at=NOW(),status='COMPLETED',completed_at=NOW() WHERE id=? AND account_id=? AND status='VERIFY_NEW' AND expires_at>NOW()",
                countryCode, phone, requestId, accountId);
        if (n == 0) return 0;
        jdbc.update("UPDATE account_phone SET unbound_at=NOW(),is_primary=0 WHERE account_id=? AND unbound_at IS NULL", accountId);
        jdbc.update("INSERT INTO account_phone(account_id,country_code,phone_number,phone_lookup_hash,is_primary,verified_at) VALUES(?,?,?,?,1,NOW())",
                accountId, countryCode, phone, phoneHash);
        jdbc.update("UPDATE sys_user SET username=? WHERE id=?", phone, accountId);
        return 1;
    }

    public String requestDeletion(String id, long accountId, String reasonCode, String reasonText) {
        jdbc.update("INSERT INTO account_deletion_request(id,account_id,status,reason_code,reason_text,combination_verified_at,sms_verified_at,risk_acknowledged_at,requested_at,scheduled_purge_at) VALUES(?,?,'COOLING_OFF',?,?,NOW(),NOW(),NOW(),NOW(),DATE_ADD(NOW(),INTERVAL 15 DAY))",
                id, accountId, reasonCode, reasonText);
        jdbc.update("UPDATE sys_user SET account_status='DELETION_PENDING',deletion_scheduled_at=DATE_ADD(NOW(),INTERVAL 15 DAY) WHERE id=?", accountId);
        return id;
    }

    public int cancelDeletion(long accountId) {
        int n = jdbc.update("UPDATE account_deletion_request SET status='CANCELLED',cancelled_at=NOW() WHERE account_id=? AND status='COOLING_OFF'", accountId);
        if (n > 0) jdbc.update("UPDATE sys_user SET account_status='ACTIVE',deletion_scheduled_at=NULL WHERE id=?", accountId);
        return n;
    }

    public void loginSuccess(long id) { jdbc.update("UPDATE sys_user SET last_login_at=NOW() WHERE id=?", id); }

    public List<Map<String, Object>> devices(long accountId) {
        return jdbc.queryForList("SELECT id,mac_address,board,alias,agent_id,app_version,last_connected_at,auto_update FROM ai_device WHERE user_id=? ORDER BY create_date DESC", accountId);
    }

    public Optional<Map<String, Object>> device(long accountId, String deviceId) {
        return jdbc.queryForList("SELECT * FROM ai_device WHERE id=? AND user_id=?", deviceId, accountId).stream().findFirst();
    }

    public void bindingHistory(String deviceId, long accountId, String mac, String method) {
        jdbc.update("INSERT INTO account_device_binding_history(device_id,account_id,mac_address,bind_method,bound_at) VALUES(?,?,?,?,NOW())",
                deviceId, accountId, mac, method);
    }

    public void unbindingHistory(String deviceId, long accountId) {
        jdbc.update("UPDATE account_device_binding_history SET unbound_at=NOW(),unbind_reason='USER' WHERE device_id=? AND account_id=? AND unbound_at IS NULL",
                deviceId, accountId);
    }

    public void pinFailure(long accountId, boolean lock) {
        jdbc.update("UPDATE account_credential SET failed_attempts=failed_attempts+1,locked_until=IF(?,DATE_ADD(NOW(),INTERVAL 15 MINUTE),locked_until) WHERE account_id=? AND credential_type='GUARDIAN_PIN'",
                lock, accountId);
    }

    public void pinSuccess(long accountId) {
        jdbc.update("UPDATE account_credential SET failed_attempts=0,locked_until=NULL WHERE account_id=? AND credential_type='GUARDIAN_PIN'", accountId);
    }

    public void createMedia(String id, long accountId, String type, String purpose, String objectKey,
            String filename, String contentType, long size, String sha256) {
        jdbc.update("INSERT INTO account_media_asset(id,owner_account_id,media_type,purpose,object_key,original_filename,content_type,size_bytes,sha256,status,scan_status) VALUES(?,?,?,?,?,?,?,?,?,'READY','NOT_REQUIRED')",
                id, accountId, type, purpose, objectKey, filename, contentType, size, sha256);
    }

    public Optional<Map<String, Object>> media(long accountId, String assetId) {
        return jdbc.queryForList("SELECT * FROM account_media_asset WHERE id=? AND owner_account_id=? AND deleted_at IS NULL AND status='READY'",
                assetId, accountId).stream().findFirst();
    }

    public int deleteMedia(long accountId, String assetId) {
        return jdbc.update("UPDATE account_media_asset SET deleted_at=NOW(),status='DELETED' WHERE id=? AND owner_account_id=? AND deleted_at IS NULL",
                assetId, accountId);
    }

    public String createVoiceProfile(String id, long accountId, String memberId, String sampleAssetId,
            String consentVersion) {
        int inserted = jdbc.update("INSERT INTO account_voice_profile(id,account_id,household_member_id,sample_asset_id,status,consent_version,consented_at) " +
                "SELECT ?,?,?,?,'READY',?,NOW() FROM household_member m JOIN household h ON h.id=m.household_id " +
                "WHERE m.id=? AND h.owner_account_id=? AND EXISTS(SELECT 1 FROM account_media_asset a WHERE a.id=? AND a.owner_account_id=? AND a.media_type='AUDIO' AND a.status='READY')",
                id, accountId, memberId, sampleAssetId, consentVersion, memberId, accountId, sampleAssetId, accountId);
        if (inserted == 0) return null;
        jdbc.update("UPDATE household_member SET voice_profile_id=? WHERE id=?", id, memberId);
        return id;
    }

    public List<Map<String, Object>> voiceProfiles(long accountId) {
        return jdbc.queryForList("SELECT * FROM account_voice_profile WHERE account_id=? AND revoked_at IS NULL", accountId);
    }

    public int revokeVoiceProfile(long accountId, String profileId) {
        jdbc.update("UPDATE household_member SET voice_profile_id=NULL WHERE voice_profile_id=?", profileId);
        return jdbc.update("UPDATE account_voice_profile SET status='REVOKED',revoked_at=NOW() WHERE id=? AND account_id=? AND revoked_at IS NULL", profileId, accountId);
    }
}
