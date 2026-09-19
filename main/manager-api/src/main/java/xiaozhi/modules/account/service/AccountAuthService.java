package xiaozhi.modules.account.service;

import java.time.LocalDateTime;
import java.util.Base64;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import cn.hutool.crypto.digest.DigestUtil;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.TokenDTO;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.account.dto.AccountRequests;
import xiaozhi.modules.account.repository.AccountRepository;
import xiaozhi.modules.security.password.PasswordUtils;
import xiaozhi.modules.security.service.CaptchaService;
import xiaozhi.modules.security.service.SysUserTokenService;
import xiaozhi.modules.sys.dto.SysUserDTO;
import xiaozhi.modules.sys.service.SysUserService;

@Service
@RequiredArgsConstructor
public class AccountAuthService {
    private static final java.util.Set<String> SCENES = java.util.Set.of(
            "REGISTER", "LOGIN", "PHONE_CHANGE_OLD", "PHONE_CHANGE_NEW", "DELETE_ACCOUNT", "RESET_COMBINATION");
    private final AccountRepository repository;
    private final CaptchaService captchaService;
    private final SysUserService userService;
    private final SysUserTokenService tokenService;

    public Map<String, Object> status(AccountRequests.Phone request) {
        var found = repository.accountByPhone(normalize(request.countryCode(), request.phone()));
        if (found.isEmpty()) return Map.of("status", "NOT_REGISTERED", "registered", false);
        String state = String.valueOf(found.get().getOrDefault("account_status", "ACTIVE"));
        return Map.of("status", state, "registered", true);
    }

    public void send(AccountRequests.SmsSend request) {
        String scene = scene(request.scene());
        String phone = normalize(request.countryCode(), request.phone());
        var account = repository.accountByPhone(phone);
        boolean mustBeNew = "REGISTER".equals(scene) || "PHONE_CHANGE_NEW".equals(scene);
        if (mustBeNew && account.isPresent())
            throw new RenException(ErrorCode.PHONE_ALREADY_REGISTERED);
        if (!mustBeNew && account.isEmpty()) throw new RenException(ErrorCode.PHONE_NOT_REGISTERED);
        captchaService.sendSMSValidateCode(phone);
    }

    public Map<String, Object> verify(AccountRequests.SmsVerify request) {
        String scene = scene(request.scene());
        String phone = normalize(request.countryCode(), request.phone());
        if (!captchaService.validateSMSValidateCode(phone, request.code(), true))
            throw new RenException(ErrorCode.SMS_CODE_ERROR);
        Long accountId = repository.accountByPhone(phone)
                .map(row -> ((Number) row.get("id")).longValue()).orElse(null);
        String ticket = randomToken();
        repository.createTicket(UUID.randomUUID().toString(), scene, phone, accountId,
                hash(ticket), LocalDateTime.now().plusMinutes(10));
        return Map.of("ticket", ticket, "scene", scene, "expiresIn", 600);
    }

    @Transactional
    public Result<TokenDTO> register(AccountRequests.Register request) {
        Map<String, Object> ticket = consume(request.ticket(), "REGISTER");
        String phone = String.valueOf(ticket.get("phone_number"));
        if (repository.accountByPhone(phone).isPresent()) throw new RenException(ErrorCode.PHONE_ALREADY_REGISTERED);
        boolean supplied = request.combination() != null && !request.combination().isBlank();
        String combination = supplied ? request.combination() : "Generated" + randomToken().substring(0, 12) + "1aA";
        validateCombination(combination);
        SysUserDTO user = new SysUserDTO();
        user.setUsername(phone); user.setMobile(phone);
        user.setRealName(request.displayName() == null ? phone : request.displayName());
        user.setPassword(combination); user.setStatus(1);
        userService.saveMobileAccount(user);
        SysUserDTO saved = userService.getByUsername(phone);
        repository.initialize(saved.getId(), phone.startsWith("+") ? "INTERNATIONAL" : "+86", phone,
                hash(phone.toLowerCase(Locale.ROOT)), request.displayName(), UUID.randomUUID().toString(),
                UUID.randomUUID().toString(), supplied, supplied ? PasswordUtils.encode(combination) : null);
        return tokenService.createToken(saved.getId());
    }

    public Result<TokenDTO> loginByTicket(AccountRequests.TicketLogin request) {
        String phone = String.valueOf(consume(request.ticket(), "LOGIN").get("phone_number"));
        return login(repository.accountByPhone(phone).orElseThrow(() -> new RenException(ErrorCode.PHONE_NOT_REGISTERED)));
    }

    public Result<TokenDTO> loginByCombination(AccountRequests.CombinationLogin request) {
        Map<String, Object> account = repository.accountByPhone(normalize(request.countryCode(), request.phone()))
                .orElseThrow(() -> new RenException(ErrorCode.PHONE_NOT_REGISTERED));
        long id = ((Number) account.get("id")).longValue();
        Map<String, Object> credential = repository.credential(id, "LOGIN_COMBINATION")
                .orElseThrow(() -> new RenException(ErrorCode.COMBINATION_NOT_SET));
        if (!PasswordUtils.matches(request.combination(), String.valueOf(credential.get("secret_hash"))))
            throw new RenException(ErrorCode.COMBINATION_INVALID);
        return login(account);
    }

    @Transactional
    public void changeCombination(long accountId, AccountRequests.CombinationChange request) {
        validateCombination(request.newCombination());
        Map<String, Object> current = repository.credential(accountId, "LOGIN_COMBINATION").orElse(null);
        boolean currentOk = current != null && request.currentCombination() != null &&
                PasswordUtils.matches(request.currentCombination(), String.valueOf(current.get("secret_hash")));
        boolean ticketOk = false;
        if (request.verificationTicket() != null && !request.verificationTicket().isBlank()) {
            Map<String, Object> ticket = consume(request.verificationTicket(), "RESET_COMBINATION");
            ticketOk = ticket.get("account_id") != null && ((Number) ticket.get("account_id")).longValue() == accountId;
        }
        if (!currentOk && !ticketOk) throw new RenException(ErrorCode.COMBINATION_INVALID);
        userService.changePasswordDirectly(accountId, request.newCombination());
        repository.upsertCredential(accountId, "LOGIN_COMBINATION", PasswordUtils.encode(request.newCombination()));
        tokenService.logout(accountId);
    }

    public Map<String, Object> consumeForAccount(String raw, String scene, long accountId) {
        Map<String, Object> ticket = consume(raw, scene);
        if (ticket.get("account_id") == null || ((Number) ticket.get("account_id")).longValue() != accountId)
            throw new RenException(ErrorCode.VERIFICATION_TICKET_INVALID);
        return ticket;
    }

    public Map<String, Object> consumeTicket(String raw, String scene) { return consume(raw, scene); }

    private Result<TokenDTO> login(Map<String, Object> account) {
        String state = String.valueOf(account.getOrDefault("account_status", "ACTIVE"));
        if ("DELETION_PENDING".equals(state)) {
            repository.cancelDeletion(((Number) account.get("id")).longValue());
            state = "ACTIVE";
        }
        if (!"ACTIVE".equals(state) || ((Number) account.getOrDefault("status", 0)).intValue() != 1)
            throw new RenException(ErrorCode.ACCOUNT_STATE_INVALID);
        long id = ((Number) account.get("id")).longValue();
        repository.loginSuccess(id);
        return tokenService.createToken(id);
    }

    private Map<String, Object> consume(String raw, String scene) {
        return repository.consumeTicket(hash(raw), scene)
                .orElseThrow(() -> new RenException(ErrorCode.VERIFICATION_TICKET_INVALID));
    }
    private String scene(String value) {
        String normalized = value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
        if (!SCENES.contains(normalized)) throw new RenException(ErrorCode.VERIFICATION_SCENE_INVALID);
        return normalized;
    }
    public static String normalize(String countryCode, String raw) {
        String cc = countryCode.replaceAll("[^0-9+]", "");
        if (!cc.startsWith("+")) cc = "+" + cc;
        String digits = raw.replaceAll("\\D", "");
        if ("+86".equals(cc)) {
            if (!digits.matches("1\\d{10}")) throw new RenException(ErrorCode.PHONE_FORMAT_ERROR);
            return digits;
        }
        if (digits.length() < 6 || digits.length() > 15) throw new RenException(ErrorCode.PHONE_FORMAT_ERROR);
        return cc + digits;
    }
    public static void validateCombination(String value) {
        if (value == null || value.length() < 8 || value.length() > 72 || !value.matches(".*[A-Z].*") ||
                !value.matches(".*[a-z].*") || !value.matches(".*\\d.*"))
            throw new RenException(ErrorCode.PASSWORD_WEAK_ERROR);
    }
    private static String randomToken() {
        byte[] bytes = new byte[32]; new java.security.SecureRandom().nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }
    private static String hash(String value) { return DigestUtil.sha256Hex(value); }
}
