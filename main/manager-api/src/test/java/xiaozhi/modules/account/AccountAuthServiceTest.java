package xiaozhi.modules.account;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.TokenDTO;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.account.dto.AccountRequests;
import xiaozhi.modules.account.repository.AccountRepository;
import xiaozhi.modules.account.service.AccountAuthService;
import xiaozhi.modules.security.password.PasswordUtils;
import xiaozhi.modules.security.service.CaptchaService;
import xiaozhi.modules.security.service.SysUserTokenService;
import xiaozhi.modules.sys.service.SysUserService;

class AccountAuthServiceTest {
    @Mock AccountRepository repository;
    @Mock CaptchaService captcha;
    @Mock SysUserService users;
    @Mock SysUserTokenService tokens;
    AccountAuthService service;

    @BeforeEach void setup() {
        MockitoAnnotations.openMocks(this);
        service = new AccountAuthService(repository, captcha, users, tokens);
    }

    @Test void statusReturnsNotRegistered() {
        when(repository.accountByPhone("13800138000")).thenReturn(Optional.empty());
        assertEquals("NOT_REGISTERED", service.status(new AccountRequests.Phone("+86", "13800138000")).get("status"));
    }

    @Test void invalidPhoneFails() {
        RenException e = assertThrows(RenException.class,
                () -> service.status(new AccountRequests.Phone("+86", "123")));
        assertEquals(ErrorCode.PHONE_FORMAT_ERROR, e.getCode());
    }

    @Test void registerSmsRejectsExistingAccount() {
        when(repository.accountByPhone(anyString())).thenReturn(Optional.of(Map.of("account_status", "ACTIVE")));
        RenException e = assertThrows(RenException.class,
                () -> service.send(new AccountRequests.SmsSend("+86", "13800138000", "REGISTER")));
        assertEquals(ErrorCode.PHONE_ALREADY_REGISTERED, e.getCode());
        verifyNoInteractions(captcha);
    }

    @Test void newPhoneSceneAllowsUnregisteredNumber() {
        when(repository.accountByPhone(anyString())).thenReturn(Optional.empty());
        service.send(new AccountRequests.SmsSend("+86", "13800138000", "PHONE_CHANGE_NEW"));
        verify(captcha).sendSMSValidateCode("13800138000");
    }

    @Test void incorrectSmsCodeFailsWithoutTicket() {
        when(captcha.validateSMSValidateCode(anyString(), anyString(), eq(true))).thenReturn(false);
        RenException e = assertThrows(RenException.class,
                () -> service.verify(new AccountRequests.SmsVerify("+86", "13800138000", "LOGIN", "000000")));
        assertEquals(ErrorCode.SMS_CODE_ERROR, e.getCode());
        verify(repository, never()).createTicket(anyString(), anyString(), anyString(), any(), anyString(), any());
    }

    @Test void correctSmsCodeCreatesSingleUseTicket() {
        when(captcha.validateSMSValidateCode(anyString(), anyString(), eq(true))).thenReturn(true);
        when(repository.accountByPhone(anyString())).thenReturn(Optional.of(Map.of("id", 9L)));
        Map<String,Object> result = service.verify(new AccountRequests.SmsVerify("86", "13800138000", "login", "123456"));
        assertNotNull(result.get("ticket"));
        verify(repository).createTicket(anyString(), eq("LOGIN"), eq("13800138000"), eq(9L), anyString(), any());
    }

    @Test void combinationLoginSucceeds() {
        String hash = PasswordUtils.encode("Strong123");
        when(repository.accountByPhone(anyString())).thenReturn(Optional.of(Map.of("id", 9L, "status", 1, "account_status", "ACTIVE")));
        when(repository.credential(9L, "LOGIN_COMBINATION")).thenReturn(Optional.of(Map.of("secret_hash", hash)));
        Result<TokenDTO> expected = new Result<TokenDTO>().ok(new TokenDTO());
        when(tokens.createToken(9L)).thenReturn(expected);
        assertSame(expected, service.loginByCombination(new AccountRequests.CombinationLogin("+86", "13800138000", "Strong123")));
        verify(repository).loginSuccess(9L);
    }

    @Test void wrongCombinationFailsAndLoginCancelsPendingDeletion() {
        when(repository.accountByPhone(anyString())).thenReturn(Optional.of(Map.of("id", 9L, "status", 1, "account_status", "ACTIVE")));
        when(repository.credential(9L, "LOGIN_COMBINATION")).thenReturn(Optional.of(Map.of("secret_hash", PasswordUtils.encode("Strong123"))));
        assertEquals(ErrorCode.COMBINATION_INVALID, assertThrows(RenException.class,
                () -> service.loginByCombination(new AccountRequests.CombinationLogin("+86", "13800138000", "Wrong123A"))).getCode());

        when(repository.consumeTicket(anyString(), eq("LOGIN"))).thenReturn(Optional.of(Map.of("phone_number", "13800138000")));
        when(repository.accountByPhone("13800138000")).thenReturn(Optional.of(Map.of("id", 9L, "status", 1, "account_status", "DELETION_PENDING")));
        when(tokens.createToken(9L)).thenReturn(new Result<TokenDTO>().ok(new TokenDTO()));
        assertNotNull(service.loginByTicket(new AccountRequests.TicketLogin("ticket")));
        verify(repository).cancelDeletion(9L);
    }

    @Test void consumedOrExpiredTicketFails() {
        when(repository.consumeTicket(anyString(), eq("LOGIN"))).thenReturn(Optional.empty());
        RenException e = assertThrows(RenException.class,
                () -> service.loginByTicket(new AccountRequests.TicketLogin("expired")));
        assertEquals(ErrorCode.VERIFICATION_TICKET_INVALID, e.getCode());
    }
}
