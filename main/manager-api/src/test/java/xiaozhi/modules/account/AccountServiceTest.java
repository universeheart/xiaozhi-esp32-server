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
import xiaozhi.modules.account.dto.AccountRequests;
import xiaozhi.modules.account.repository.AccountRepository;
import xiaozhi.modules.account.service.AccountAuthService;
import xiaozhi.modules.account.service.AccountService;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.security.password.PasswordUtils;
import xiaozhi.modules.security.service.SysUserTokenService;

class AccountServiceTest {
    @Mock AccountRepository repository;
    @Mock AccountAuthService auth;
    @Mock DeviceService devices;
    @Mock SysUserTokenService tokens;
    AccountService service;

    @BeforeEach void setup() {
        MockitoAnnotations.openMocks(this);
        service = new AccountService(repository, auth, devices, tokens);
    }

    @Test void guardianPinSuccessAndFailureAreTracked() {
        when(repository.credential(7L, "GUARDIAN_PIN")).thenReturn(Optional.of(Map.of(
                "secret_hash", PasswordUtils.encode("1234"), "failed_attempts", 0)));
        assertTrue((Boolean) service.verifyPin(7L, new AccountRequests.GuardianPin("1234")).get("verified"));
        verify(repository).pinSuccess(7L);
        assertEquals(ErrorCode.GUARDIAN_PIN_INVALID, assertThrows(RenException.class,
                () -> service.verifyPin(7L, new AccountRequests.GuardianPin("9999"))).getCode());
        verify(repository).pinFailure(7L, false);
    }

    @Test void deletionRequiresRiskAcknowledgement() {
        AccountRequests.Deletion request = new AccountRequests.Deletion("ticket", null, false, null, null);
        assertEquals(ErrorCode.DELETION_REQUEST_INVALID,
                assertThrows(RenException.class, () -> service.requestDeletion(7L, request)).getCode());
        verifyNoInteractions(auth);
    }

    @Test void deletionRequiresCombinationWhenConfigured() {
        when(auth.consumeForAccount("ticket", "DELETE_ACCOUNT", 7L)).thenReturn(Map.of("account_id", 7L));
        when(repository.credential(7L, "LOGIN_COMBINATION")).thenReturn(Optional.of(Map.of("secret_hash", PasswordUtils.encode("Strong123"))));
        AccountRequests.Deletion request = new AccountRequests.Deletion("ticket", "Wrong123A", true, "OTHER", null);
        assertEquals(ErrorCode.COMBINATION_INVALID,
                assertThrows(RenException.class, () -> service.requestDeletion(7L, request)).getCode());
    }

    @Test void cannotUnbindAnotherAccountsDevice() {
        when(repository.device(7L, "device-x")).thenReturn(Optional.empty());
        assertEquals(ErrorCode.ACCOUNT_RESOURCE_NO_PERMISSION,
                assertThrows(RenException.class, () -> service.unbindDevice(7L, "device-x")).getCode());
        verifyNoInteractions(devices);
    }
}
