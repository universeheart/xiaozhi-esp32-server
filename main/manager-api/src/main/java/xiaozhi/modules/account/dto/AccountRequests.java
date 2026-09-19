package xiaozhi.modules.account.dto;

import java.time.LocalDate;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** Request contracts for the mobile account API. Password terminology is intentionally avoided. */
public final class AccountRequests {
    private AccountRequests() {}

    public record Phone(@NotBlank String countryCode, @NotBlank String phone) {}
    public record SmsSend(@NotBlank String countryCode, @NotBlank String phone,
            @NotBlank String scene) {}
    public record SmsVerify(@NotBlank String countryCode, @NotBlank String phone,
            @NotBlank String scene, @NotBlank String code) {}
    public record Register(@NotBlank String ticket,
            @Size(min = 8, max = 72) String combination, String displayName) {}
    public record TicketLogin(@NotBlank String ticket) {}
    public record CombinationLogin(@NotBlank String countryCode, @NotBlank String phone,
            @NotBlank String combination) {}
    public record CombinationChange(String currentCombination,
            @NotBlank @Size(min = 8, max = 72) String newCombination,
            String verificationTicket) {}
    public record GuardianPin(@NotBlank @Pattern(regexp = "\\d{4}") String pin) {}
    public record Profile(String displayName, String avatarAssetId, String gender,
            LocalDate birthDate, String locale, String timezone) {}
    public record Privacy(Boolean crossDeviceSyncEnabled, Boolean sensitiveWordRedaction,
            Boolean conversationMemoryEnabled, Integer recentMemoryDays,
            Boolean patrolRecordingEnabled, Integer patrolRetentionDays,
            Boolean localCacheEnabled, Boolean personalizedVoiceEnabled,
            Boolean faceRecognitionEnabled) {}
    public record Member(String familyNickname, String familyRole, String customRoleName,
            String robotSalutation, String gender, LocalDate birthDate,
            String avatarAssetId, String voiceProfileId, String visibilityScope) {}
    public record PhoneChangeStart(@NotBlank String oldPhoneTicket) {}
    public record PhoneChangeComplete(@NotBlank String requestId, @NotBlank String newPhoneTicket) {}
    public record Deletion(@NotBlank String verificationTicket, String combination,
            @NotNull Boolean riskAcknowledged, String reasonCode, String reasonText) {}
    public record DeviceBind(@NotBlank String agentId, @NotBlank String activationCode) {}
    public record VoiceProfile(@NotBlank String householdMemberId, @NotBlank String sampleAssetId,
            @NotBlank String consentVersion) {}
}
