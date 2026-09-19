package xiaozhi.modules.hardware;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.jdbc.core.JdbcTemplate;

import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.account.repository.AccountRepository;
import xiaozhi.modules.agent.service.AgentChatHistoryService;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.hardware.dto.HardwareLifecycleRequests;
import xiaozhi.modules.hardware.service.HardwareLifecycleService;
import xiaozhi.modules.security.service.SysUserTokenService;
import xiaozhi.modules.sys.dto.SysUserDTO;

class HardwareLifecycleServiceTest {
    @Mock JdbcTemplate jdbc;
    @Mock SysUserTokenService tokens;
    @Mock AgentService agents;
    @Mock DeviceService devices;
    @Mock AgentChatHistoryService chats;
    @Mock AccountRepository accounts;
    HardwareLifecycleService service;

    @BeforeEach void setup() {
        MockitoAnnotations.openMocks(this);
        service = new HardwareLifecycleService(jdbc, tokens, agents, devices, chats, accounts);
    }

    @Test void macNormalizationRejectsInvalidInput() {
        assertEquals("fc:0c:70:20:83:a6", HardwareLifecycleService.normalizeMac("FC-0C-70-20-83-A6"));
        assertEquals(ErrorCode.HARDWARE_ACTIVATION_INVALID,
                assertThrows(RenException.class, () -> HardwareLifecycleService.normalizeMac("bad")).getCode());
    }

    @Test void activationRejectsHardwareOutsideFactoryRegistry() {
        user();
        when(jdbc.queryForObject(startsWith("SELECT COUNT"), eq(Integer.class), any(Object[].class))).thenReturn(0);
        when(jdbc.queryForList(startsWith("SELECT * FROM hardware_product_unit"), any(Object[].class))).thenReturn(List.of());
        var request = new HardwareLifecycleRequests.Activate("request-1", "token", "P1", "SN1",
                "fc:0c:70:20:83:a6", "123456", "esp32", "1.0", null);
        assertEquals(ErrorCode.HARDWARE_NOT_OURS, assertThrows(RenException.class, () -> service.activate(request)).getCode());
        verifyNoInteractions(agents, devices);
    }

    @Test void activationCreatesAgentAndBindsDevice() {
        user();
        when(jdbc.queryForObject(startsWith("SELECT COUNT"), eq(Integer.class), any(Object[].class))).thenReturn(0);
        when(jdbc.queryForList(startsWith("SELECT * FROM hardware_product_unit"), any(Object[].class)))
                .thenReturn(List.of(Map.of("id", 3L, "status", "PROVISIONED", "board", "esp32")));
        when(agents.createAgentForUser(any(), eq(7L))).thenReturn("agent-1");
        DeviceEntity device = new DeviceEntity(); device.setId("device-1");
        when(devices.getDeviceByMacAddress("fc:0c:70:20:83:a6")).thenReturn(device);
        when(jdbc.update(startsWith("UPDATE hardware_product_unit SET status='ACTIVATED'"), any(), any(), any())).thenReturn(1);
        var result = service.activate(new HardwareLifecycleRequests.Activate("request-1", "token", "P1", "SN1",
                "fc:0c:70:20:83:a6", "123456", "esp32", "1.0", "客厅小伴"));
        assertEquals("ACTIVATED", result.get("status"));
        verify(devices).deviceActivationForUser("agent-1", "123456", 7L, "fc:0c:70:20:83:a6");
        verify(accounts).bindingHistory("device-1", 7L, "fc:0c:70:20:83:a6", "SIGNED_QR");
    }

    @Test void unbindRequiresExplicitConfirmation() {
        var request = new HardwareLifecycleRequests.Unbind("request-2", "token", "fc:0c:70:20:83:a6", "NO");
        assertEquals(ErrorCode.HARDWARE_UNBIND_INVALID,
                assertThrows(RenException.class, () -> service.unbind(request)).getCode());
        verifyNoInteractions(tokens, devices, chats);
    }

    @Test void unbindPurgesHistoryProfileMemoryAndAssociations() {
        user();
        when(jdbc.queryForObject(startsWith("SELECT COUNT"), eq(Integer.class), any(Object[].class))).thenReturn(0);
        when(jdbc.queryForList(startsWith("SELECT * FROM hardware_product_unit"), any(Object[].class)))
                .thenReturn(List.of(Map.of("id", 3L, "status", "ACTIVATED", "activated_account_id", 7L)));
        DeviceEntity device = new DeviceEntity();
        device.setId("device-1"); device.setUserId(7L); device.setAgentId("agent-1");
        when(devices.getDeviceByMacAddress("fc:0c:70:20:83:a6")).thenReturn(device);
        var result = service.unbind(new HardwareLifecycleRequests.Unbind("request-2", "token",
                "fc:0c:70:20:83:a6", "UNBIND"));
        assertEquals("UNBOUND", result.get("status"));
        verify(chats).deleteByAgentId("agent-1", true, true);
        verify(jdbc).update(startsWith("DELETE FROM memory_profile"), eq("fc:0c:70:20:83:a6"));
        verify(accounts).unbindingHistory("device-1", 7L);
        verify(devices).unbindDevice(7L, "device-1");
        verify(agents).deleteById("agent-1");
    }

    private void user() {
        SysUserDTO user = new SysUserDTO(); user.setId(7L);
        when(tokens.getUserByToken("token")).thenReturn(user);
    }
}
